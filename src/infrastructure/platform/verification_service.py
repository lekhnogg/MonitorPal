# src/infrastructure/platform/verification_service.py
"""
Windows implementation of the verification service.

Orchestrates the verification process: checks if the target platform is closed,
triggers the Cold Turkey block, attempts to launch the platform, checks if the launch
was blocked, and updates configuration via callbacks on success.
"""
import time
import traceback
import os # Added os for basename in is_process_running
import subprocess # For launching target platform
from typing import Callable, Optional

import psutil # For checking running processes

# --- Application Imports ---
from src.domain.services.i_verification_service import IVerificationService
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_background_task_service import IBackgroundTaskService, Worker
from src.domain.services.i_cold_turkey_service import IColdTurkeyService
from src.domain.services.i_config_repository_service import IConfigRepository
from src.domain.services.i_ui_service import IUIService
from src.domain.common.result import Result
from src.domain.common.errors import ConfigurationError, PlatformError, ValidationError


# --- Worker Definition (Major Rework) ---
class VerificationWorker(Worker[bool]):
    """
    Worker for verifying Cold Turkey block by attempting to launch the target platform.

    Checks if platform is closed, triggers CT block, attempts launch, verifies block effect.
    Returns True if the platform launch was successfully blocked, False otherwise.
    """
    # Define constants for timings (adjust as needed)
    WAIT_AFTER_TRIGGER = 5.0 # Seconds to wait after triggering CT block
    WAIT_AFTER_LAUNCH_ATTEMPT = 40.0 # Seconds to wait after attempting platform launch

    def __init__(self,
                 platform: str,
                 block_name: str,
                 platform_executable_path: str, # <-- ADDED
                 cold_turkey_service: IColdTurkeyService,
                 logger: ILoggerService):
        super().__init__()
        self.platform = platform
        self.block_name = block_name
        self.platform_executable_path = platform_executable_path # <-- STORED
        self.cold_turkey_service = cold_turkey_service
        self.logger = logger

    def _is_process_running(self, executable_path: str) -> bool:
        """Checks if a process with the given executable path is running."""
        try:
            # Normalize path for comparison
            target_path_norm = os.path.normpath(executable_path).lower()
            target_exe_name = os.path.basename(target_path_norm)

            for proc in psutil.process_iter(['pid', 'name', 'exe']):
                try:
                    proc_exe = proc.info.get('exe')
                    # Compare normalized full path if available, fallback to name comparison
                    if proc_exe:
                        if os.path.normpath(proc_exe).lower() == target_path_norm:
                            self.logger.debug(f"Process found running by full path: {proc.info['pid']} ({proc_exe})")
                            return True
                    # Fallback: compare executable name (less precise)
                    elif proc.info.get('name', '').lower() == target_exe_name:
                         self.logger.debug(f"Process potentially found running by name: {proc.info['pid']} ({proc.info['name']})")
                         # Maybe add extra checks here if name matching is too broad?
                         return True
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue # Ignore processes we can't access
                except Exception as e:
                    self.logger.warning(f"Error checking process {proc.pid}: {e}") # Log other errors
            return False
        except Exception as e:
             self.logger.error(f"Error iterating processes: {e}", exc_info=True)
             return False # Assume not running if process iteration fails


    def execute(self) -> bool:
        """
        Executes the verification sequence:
        1. Check if target platform is closed.
        2. Trigger CT block.
        3. Attempt to launch target platform.
        4. Check if launch was blocked.
        Returns True if launch was blocked, False otherwise.
        """
        launched_process = None  # To store the Popen object if launch succeeds

        try:
            self.report_started()
            self.logger.info(f"Verification Worker: Verifying block '{self.block_name}' "
                             f"by attempting launch of '{os.path.basename(self.platform_executable_path)}'")

            # --- RE-INSERTED CHECK ---
            self.report_progress(5, "Checking prerequisites...")  # Added progress step
            if self.cancel_requested: return False  # Early exit

            self.logger.debug(f"Checking if target platform '{self.platform_executable_path}' is running...")
            if self._is_process_running(self.platform_executable_path):
                error_msg = f"Verification Failed: Target platform '{os.path.basename(self.platform_executable_path)}' is currently running. Please close it first."
                self.logger.error(error_msg)
                self.report_error(error_msg)
                return False  # Fail verification if platform is running
            self.logger.debug("Target platform is not running.")
            # --- END RE-INSERTED CHECK ---

            self.report_progress(10, "Platform closed. Triggering block...")  # Keep this progress step
            if self.cancel_requested: return False

            # 2. Trigger Cold Turkey Block (using service method for consistency)
            # Use -lock 1 minute as a reasonable duration for the test
            block_result = self.cold_turkey_service.execute_block_command(self.block_name, 2)
            if block_result.is_failure:
                error_msg = f"Failed to trigger Cold Turkey block '{self.block_name}': {block_result.error}"
                self.logger.error(error_msg)
                self.report_error(error_msg)
                return False  # Fail if command execution fails
            self.logger.info(f"Cold Turkey block '{self.block_name}' triggered successfully.")
            self.report_progress(25, "Block triggered. Waiting...")
            if self.cancel_requested: return False

            # 3. Wait for Block to Apply
            time.sleep(self.WAIT_AFTER_TRIGGER)
            self.report_progress(40, f"Attempting to launch '{os.path.basename(self.platform_executable_path)}'...")
            if self.cancel_requested: return False

            # 4. Attempt to Launch Target Platform
            try:
                self.logger.debug(f"Executing subprocess.Popen('{self.platform_executable_path}')...")
                # Use Popen to start without waiting, hide window if possible
                flags = subprocess.CREATE_NO_WINDOW
                launched_process = subprocess.Popen([self.platform_executable_path], creationflags=flags)
                self.logger.info(
                    f"Attempted launch of '{os.path.basename(self.platform_executable_path)}' (PID if started: {launched_process.pid}).")
            except FileNotFoundError:
                error_msg = f"Verification Error: Platform executable not found at '{self.platform_executable_path}'."
                self.logger.error(error_msg)
                self.report_error(error_msg)
                return False  # Fail if the executable itself isn't found
            except PermissionError:
                error_msg = f"Verification Error: Permission denied launching '{self.platform_executable_path}'."
                self.logger.error(error_msg)
                self.report_error(error_msg)
                return False  # Fail on permission issues
            except Exception as launch_err:
                # Catch other potential errors during launch itself
                error_msg = f"Verification Error: Unexpected error launching '{self.platform_executable_path}': {launch_err}"
                self.logger.error(error_msg, exc_info=True)
                self.report_error(error_msg)
                return False  # Fail on other launch errors
            self.report_progress(60, "Launch attempted. Waiting to check block effect...")
            if self.cancel_requested: return False

            # 5. Wait Again to Check Block Effect
            time.sleep(self.WAIT_AFTER_LAUNCH_ATTEMPT)  # Using the potentially adjusted wait time
            self.report_progress(80, "Checking if platform launch was blocked...")
            if self.cancel_requested: return False

            # 6. Check if Launch Was Blocked (using psutil)
            self.logger.debug(f"Checking again if '{self.platform_executable_path}' is running...")
            is_running_after_wait = self._is_process_running(self.platform_executable_path)

            if is_running_after_wait:
                # Block FAILED! Platform is running.
                error_msg = f"Verification Failed: Platform '{os.path.basename(self.platform_executable_path)}' was launched successfully, indicating the block '{self.block_name}' is not effective or incorrect."
                self.logger.error(error_msg)
                self.report_error(error_msg)
                verification_succeeded = False
            else:
                # Block WORKED! Platform is not running.
                self.logger.info(
                    f"Verification Successful: Platform '{os.path.basename(self.platform_executable_path)}' launch appears to have been blocked.")
                self.report_progress(100, "Verification Successful: Platform Blocked.")
                verification_succeeded = True

            return verification_succeeded  # Return True if blocked, False if launched

        except Exception as e:
            # Catch-all for unexpected errors in the worker logic
            error_msg = f"Unexpected error during verification worker execution: {e}"
            self.logger.error(error_msg, exc_info=True)
            self.report_error(error_msg)
            return False
        finally:
            # 7. Cleanup: Ensure launched process (if any and verification failed) is terminated
            # Check if launch was attempted and if verification determined failure (platform running)
            # We check is_running_after_wait which is only defined if step 6 completed.
            # If verification_succeeded is False AND launched_process exists, we need cleanup.
            should_cleanup = False
            if 'verification_succeeded' in locals() and not verification_succeeded and launched_process:
                should_cleanup = True

            if should_cleanup:
                # Check if the process associated with Popen object still exists
                if launched_process.poll() is None:  # Check if it's still running before trying to terminate
                    try:
                        self.logger.info(
                            f"Cleaning up launched process {launched_process.pid} after failed verification...")
                        launched_process.terminate()  # Try graceful termination
                        try:
                            launched_process.wait(timeout=1.0)  # Wait briefly
                            self.logger.debug(f"Process {launched_process.pid} terminated.")
                        except subprocess.TimeoutExpired:
                            self.logger.warning(
                                f"Process {launched_process.pid} did not terminate gracefully, killing...")
                            launched_process.kill()  # Force kill if needed
                            self.logger.debug(f"Process {launched_process.pid} killed.")
                    except Exception as term_err:
                        # Log error during cleanup but don't change verification result
                        self.logger.error(f"Error cleaning up launched process {launched_process.pid}: {term_err}")
                else:
                    self.logger.debug(f"Cleanup not needed or already done for process {launched_process.pid}.")


# --- Service Implementation ---
class WindowsVerificationService(IVerificationService):
    """
    Windows implementation of the verification service using launch blocking check.
    """

    def __init__(self, logger: ILoggerService, cold_turkey_service: IColdTurkeyService,
                 thread_service: IBackgroundTaskService, ui_service: IUIService,
                 config_repository: IConfigRepository):
        """Initialize the service."""
        self.logger = logger
        self.cold_turkey_service = cold_turkey_service
        self.thread_service = thread_service
        self.ui_service = ui_service
        self.config_repository = config_repository
        self.verification_task_id = "verify_block_effect" # Changed ID slightly
        self._last_verification_time: float = 0.0
        self._cooldown_seconds: int = 15 # Reduced cooldown slightly as it involves launch

        self._on_started_callback: Optional[Callable[[], None]] = None
        self._on_completed_callback: Optional[Callable[[bool, str], None]] = None
        self._on_error_callback: Optional[Callable[[str, str], None]] = None

        self.logger.info("Windows Verification Service initialized (Launch Blocking Check)")

    # --- Interface Method Implementations ---

    # MODIFIED Signature
    def verify_platform_block(self, platform: str, block_name: str,
                              platform_executable_path: str, # <-- ADDED
                              on_started: Callable[[], None],
                              on_completed: Callable[[bool, str], None],
                              on_error: Callable[[str, str], None]) -> Result[bool]:
        """
        Starts the asynchronous verification process for a block/platform
        by attempting to launch the platform executable.
        """
        # 1. Prerequisite Checks (Basic)
        if not self.is_blocker_path_configured():
            return Result.fail(ConfigurationError("Cold Turkey Blocker path not configured"))
        if not block_name: return Result.fail(ValidationError("Block name cannot be empty"))
        if not platform: return Result.fail(ValidationError("Platform name cannot be empty"))
        if not platform_executable_path or not os.path.exists(platform_executable_path): # <-- ADDED
            return Result.fail(ConfigurationError(f"Platform executable path is invalid or not configured: {platform_executable_path}"))

        # 2. Cooldown / Already Running Checks
        if self.is_verification_in_progress():
            return Result.fail(PlatformError("Verification already in progress"))
        cooldown = self.get_cooldown_remaining()
        if cooldown > 0:
            return Result.fail(PlatformError(f"Please wait {cooldown}s before verifying again"))

        # 3. Prepare Worker and Callbacks
        self.logger.info(f"Starting verification task for {platform} / {block_name}")
        self._on_started_callback = on_started
        self._on_completed_callback = on_completed
        self._on_error_callback = on_error

        # Trigger on_started immediately if provided
        if self._on_started_callback:
            try: self._on_started_callback()
            except Exception as e: self.logger.error(f"Error in on_started callback: {e}", exc_info=True)

        # Create worker (pass new path)
        try:
            worker = VerificationWorker(
                platform=platform,
                block_name=block_name,
                platform_executable_path=platform_executable_path, # <-- PASS NEW PATH
                cold_turkey_service=self.cold_turkey_service,
                logger=self.logger
            )
        except Exception as e:
             # Handle error creating worker instance
             self.logger.error(f"Error creating VerificationWorker: {e}", exc_info=True)
             if self._on_error_callback:
                 try: self._on_error_callback(f"Internal setup error: {e}", platform)
                 except Exception as cb_e: self.logger.error(f"Error executing on_error callback: {cb_e}")
             self._clear_callbacks()
             return Result.fail(PlatformError(f"Internal setup error: {e}"))

        # --- Define internal completion handler ---
        # (This part remains largely the same - it processes the boolean result)
        def internal_on_complete(verification_success: bool):
            self.logger.info(f"Verification task completed internally. Block Effect Success: {verification_success}")
            self._last_verification_time = time.time()
            overall_success = False
            config_save_error_msg = None

            if verification_success:
                self.logger.info(f"Block effect verified for '{block_name}'. Saving to config for '{platform}'.")
                save_res = self.config_repository.set_verified_block(platform, block_name)
                if save_res.is_success:
                    overall_success = True
                    self.logger.info(f"Successfully saved verified block '{block_name}' for '{platform}'.")
                else:
                    config_save_error_msg = f"Verification succeeded, but failed to save configuration: {save_res.error}"
                    self.logger.error(config_save_error_msg)
            else:
                # Verification failed (platform launched or other worker error)
                self.logger.warning(f"Block effect verification FAILED for '{block_name}'. Clearing verified status for '{platform}'.")
                # Always clear verified status on failure
                clear_res = self.config_repository.set_verified_block(platform, None)
                if clear_res.is_failure:
                     self.logger.error(f"Also failed to clear verified block for {platform} after verification failure: {clear_res.error}")

            # Call appropriate ViewModel callback
            final_error_msg = config_save_error_msg if config_save_error_msg else "Verification Failed: Platform launch was not blocked."
            if overall_success:
                if self._on_completed_callback:
                    try: self._on_completed_callback(True, platform)
                    except Exception as e: self.logger.error(f"Error in on_completed callback: {e}", exc_info=True)
            else:
                 if self._on_error_callback:
                    try: self._on_error_callback(final_error_msg, platform)
                    except Exception as e: self.logger.error(f"Error in on_error callback: {e}", exc_info=True)
                 elif self._on_completed_callback: # Fallback to completed(False)
                      try: self._on_completed_callback(False, platform)
                      except Exception as e: self.logger.error(f"Error in on_completed(False) callback: {e}", exc_info=True)

            # Activate window (optional)
            activate_res = self.ui_service.activate_application_window()
            if activate_res.is_failure: self.logger.warning(f"Failed to activate window post-verification: {activate_res.error}")

            self._clear_callbacks()

        # --- Define internal error handler ---
        # (This also remains largely the same - handles errors from worker.report_error)
        def internal_on_error(error_msg: str):
            self.logger.error(f"Verification task error reported internally: {error_msg}")
            self._last_verification_time = time.time()

            # Always clear verified block status on any worker error
            self.logger.warning(f"Clearing verified status for platform '{platform}' due to error: {error_msg}")
            clear_res = self.config_repository.set_verified_block(platform, None)
            if clear_res.is_failure:
                 self.logger.error(f"Also failed to clear verified block for {platform} after error: {clear_res.error}")

            if self._on_error_callback:
                 try: self._on_error_callback(error_msg, platform)
                 except Exception as e: self.logger.error(f"Error executing on_error callback: {e}", exc_info=True)
            elif self._on_completed_callback:
                try: self._on_completed_callback(False, platform)
                except Exception as e: self.logger.error(f"Error executing on_completed(False) callback after error: {e}", exc_info=True)

            activate_res = self.ui_service.activate_application_window()
            if activate_res.is_failure: self.logger.warning(f"Failed to activate window post-verification error: {activate_res.error}")

            self._clear_callbacks()

        # Set worker callbacks
        worker.set_on_completed(internal_on_complete)
        worker.set_on_error(internal_on_error)

        # 4. Execute Task
        task_result = self.thread_service.execute_task(self.verification_task_id, worker)

        if task_result.is_failure:
            self.logger.error(f"Failed to start verification task via thread service: {task_result.error}")
            if self._on_error_callback:
                try: self._on_error_callback(f"Failed to start task: {task_result.error}", platform)
                except Exception as cb_e: self.logger.error(f"Error executing on_error callback: {cb_e}")
            self._clear_callbacks()
            return Result.fail(PlatformError(f"Failed to start verification: {task_result.error}"))
        else:
            self.logger.debug(f"Verification task '{self.verification_task_id}' successfully submitted.")
            return Result.ok(True) # Task started

    # --- Other methods (cancel, is_in_progress, cooldown, etc.) remain unchanged ---
    def cancel_verification(self) -> Result[bool]:
        self.logger.info("Attempting to cancel verification task.")
        if not self.is_verification_in_progress():
            return Result.ok(False) # Indicate already stopped
        return self.thread_service.cancel_task(self.verification_task_id)

    def is_verification_in_progress(self) -> bool:
        return self.thread_service.is_task_running(self.verification_task_id)

    def get_cooldown_remaining(self) -> int:
        if self._last_verification_time == 0: return 0
        elapsed = time.time() - self._last_verification_time
        remaining = self._cooldown_seconds - elapsed
        return int(remaining) if remaining > 0 else 0

    def is_blocker_path_configured(self) -> bool:
        # Delegate path check to the cold turkey service or check repo directly
        return self.cold_turkey_service.is_blocker_path_configured()
        # Or return self.cold_turkey_service.is_blocker_path_configured() # If CT service has this check

    def is_verification_complete(self) -> bool:
        current_platform = self._platform_selection_service.get_current_platform()
        if not current_platform: return False
        verified_block_res = self.config_repository.get_verified_block(current_platform)
        return verified_block_res.is_success and bool(verified_block_res.value)

    def _clear_callbacks(self):
         self.logger.debug("Clearing verification callbacks.")
         self._on_started_callback = None
         self._on_completed_callback = None
         self._on_error_callback = None