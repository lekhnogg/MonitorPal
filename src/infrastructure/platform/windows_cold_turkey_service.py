# src/infrastructure/platform/windows_cold_turkey_service.py

import os
import subprocess
import time # Keep time if needed for any waits, though execute_block_command typically doesn't wait
from typing import Optional # Keep Optional if used in signatures, though not needed now

# --- REMOVED UI Automation related imports ---
# try:
#     import win32gui
#     import win32con
# except ImportError:
#     # ... (Error message handling removed)
#     raise
# try:
#     import pywinauto
#     PYWINAUTO_AVAILABLE = True
# except ImportError:
#     PYWINAUTO_AVAILABLE = False
# --- END REMOVED ---

# --- Domain Imports ---
from src.domain.services.i_cold_turkey_service import IColdTurkeyService
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_config_repository_service import IConfigRepository
# REMOVED: from src.domain.services.i_window_manager_service import IWindowManager
from src.domain.common.result import Result
from src.domain.common.errors import ConfigurationError, PlatformError, ValidationError


class WindowsColdTurkeyService(IColdTurkeyService):
    """
    Windows implementation of Cold Turkey Blocker integration.
    Focuses on executing block commands via the command line.
    """

    # Constants for command execution
    BLOCK_TRIGGER_TIMEOUT = 10 # Increased timeout slightly for robustness

    def __init__(self,
                 logger: ILoggerService,
                 config_repository: IConfigRepository):
                 # REMOVED: window_manager: IWindowManager): # No longer needed
        """Initialize the service."""
        self.logger = logger
        self.config_repository = config_repository
        # REMOVED: self.window_manager = window_manager
        # REMOVED: pywinauto availability check

    def execute_block_command(self, block_name: str, duration_minutes: int) -> Result[bool]:
        """Execute a block command to lock a specific block."""
        # Fetch path using the repo interface method
        path_result = self.get_blocker_path() # Use own method which uses repo
        if path_result.is_failure:
             # Propagate the ConfigurationError from get_blocker_path
             return Result.fail(path_result.error)
        blocker_path = path_result.value

        # Normalize path (still good practice)
        normalized_path = os.path.normpath(blocker_path)

        self.logger.info(f"Executing Cold Turkey block command for '{block_name}' duration {duration_minutes} minutes using path '{normalized_path}'")
        try:
             # Ensure duration is a string for the command line argument
             duration_str = str(duration_minutes)
             # Command list
             command = [normalized_path, "-start", block_name, "-lock", duration_str]
             self.logger.debug(f"Running command: {command}")

             # Execute the command
             result = subprocess.run(
                 command,
                 check=True, # Raises CalledProcessError on non-zero exit
                 capture_output=True, # Capture stdout/stderr
                 text=True, # Decode stdout/stderr as text
                 timeout=self.BLOCK_TRIGGER_TIMEOUT,
                 creationflags=subprocess.CREATE_NO_WINDOW # Attempt to hide console
             )

             # Log output even on success
             if result.stdout:
                  self.logger.debug(f"Cold Turkey command stdout for '{block_name}': {result.stdout.strip()}")
             if result.stderr:
                  self.logger.warning(f"Cold Turkey command stderr for '{block_name}': {result.stderr.strip()}") # Log stderr as warning

             self.logger.info(f"Cold Turkey command for block '{block_name}' executed successfully.")
             return Result.ok(True) # Return success

        except subprocess.CalledProcessError as e:
             # Log specific details from the error
             self.logger.error(f"Cold Turkey command failed for block '{block_name}'. Exit code: {e.returncode}. Stderr: {e.stderr.strip() if e.stderr else 'N/A'}")
             error = PlatformError(
                 message=f"Cold Turkey command failed for block '{block_name}' (Exit Code: {e.returncode})",
                 details={"exit_code": e.returncode, "stderr": e.stderr.strip() if e.stderr else ''},
                 inner_error=e
             )
             return Result.fail(error)
        except subprocess.TimeoutExpired as e:
             self.logger.error(f"Cold Turkey command timed out after {self.BLOCK_TRIGGER_TIMEOUT}s for block '{block_name}'. Command: {e.cmd}")
             error = PlatformError(
                  message=f"Cold Turkey command timed out for block '{block_name}'",
                  details={"timeout": self.BLOCK_TRIGGER_TIMEOUT},
                  inner_error=e
             )
             return Result.fail(error)
        except FileNotFoundError as e:
             # This error happens if normalized_path is wrong
             self.logger.error(f"Cold Turkey executable not found at path during execution: {normalized_path}")
             error = ConfigurationError(
                 message=f"Cold Turkey executable not found at path: {normalized_path}",
                 details={"path": normalized_path},
                 inner_error=e
             )
             return Result.fail(error)
        except Exception as e:
             # Catch other potential errors (e.g., permissions)
             self.logger.error(f"Unexpected error executing Cold Turkey command for block '{block_name}': {e}", exc_info=True)
             error = PlatformError(
                 message=f"Unexpected error executing Cold Turkey for block '{block_name}'",
                 inner_error=e
             )
             return Result.fail(error)

    # --- REMOVED: verify_block method ---
    # --- REMOVED: _verify_cold_turkey_ui method ---
    # --- REMOVED: _find_cold_turkey_window method ---
    # --- REMOVED: _safely_activate_window method ---

    # --- Config-related methods remain unchanged ---
    def get_blocker_path(self) -> Result[str]:
        """Get the path to the Cold Turkey executable from config."""
        path = self.config_repository.get_cold_turkey_path()
        if not path:
            return Result.fail(ConfigurationError("Cold Turkey Blocker path not configured"))
        if not os.path.exists(path):
             return Result.fail(ConfigurationError(f"Configured Cold Turkey path not found: {path}"))
        return Result.ok(path)

    def set_blocker_path(self, path: str) -> Result[bool]:
        """Set the path to the Cold Turkey executable in config."""
        # Basic validation could happen here, e.g., check if path is empty
        if not path or not path.strip():
            return Result.fail(ValidationError("Blocker path cannot be empty."))
        # Further validation (like os.path.exists) could be added but might
        # prevent setting a path before CT is installed. Let the repo handle saving.
        return self.config_repository.set_cold_turkey_path(path.strip())

    def is_blocker_path_configured(self) -> bool:
        """Check if Cold Turkey Blocker path is configured and exists."""
        # Get path from repository
        path = self.config_repository.get_cold_turkey_path()
        # Check if path is non-empty AND the file exists AND it's a file
        is_configured_and_exists = bool(path and os.path.exists(path) and os.path.isfile(path))
        if not is_configured_and_exists:
            # Optional: Log why the check failed for easier debugging
            self.logger.debug(f"Blocker path check failed. Path='{path}', Exists/IsFile={os.path.exists(path) and os.path.isfile(path) if path else 'N/A'}")
        return is_configured_and_exists