#src/infrastructure/platform/verification_service.py
"""
Windows implementation of the verification service.

This service verifies that Cold Turkey Blocker is properly configured
to block trading platforms, using UI automation to check block status.
"""
import time
from typing import Dict, Any, List

from src.domain.services.i_verification_service import IVerificationService
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_background_task_service import IBackgroundTaskService, Worker
from src.domain.services.i_cold_turkey_service import IColdTurkeyService
from src.domain.services.i_ui_service import IUIService
from src.domain.common.result import Result


class VerificationWorker(Worker[bool]):
    """Worker for verifying Cold Turkey Blocker configuration."""

    def __init__(self,
                 platform: str,
                 block_name: str,
                 cold_turkey_service: IColdTurkeyService,
                 logger: ILoggerService):
        """Initialize the verification worker."""
        super().__init__()
        self.platform = platform
        self.block_name = block_name
        self.cold_turkey_service = cold_turkey_service
        self.logger = logger

    def execute(self) -> bool:
        """Execute the verification process."""
        try:
            self.logger.info(f"Verifying block '{self.block_name}' for platform '{self.platform}'")

            # Check for cancellation
            self.check_cancellation()

            # Use cold_turkey_service for verification
            verify_result = self.cold_turkey_service.verify_block(
                block_name=self.block_name,
                platform=self.platform,
                register_if_valid=True
            )

            # Check for cancellation again
            self.check_cancellation()

            if verify_result.is_failure:
                error_message = str(verify_result.error)
                self.logger.error(f"Verification failed: {error_message}")
                self.report_error(error_message)
                return False

            return verify_result.value

        except Exception as e:
            self.logger.error(f"Unexpected error in verification: {e}")
            self.report_error(f"Unexpected error: {e}")
            return False


class WindowsVerificationService(IVerificationService):
    """
    Windows implementation of the verification service.

    This service coordinates the verification process, handling rate limiting,
    background threading, and user feedback for Cold Turkey Blocker verification.
    """

    def __init__(self, logger: ILoggerService, cold_turkey_service: IColdTurkeyService,
                 thread_service: IBackgroundTaskService, ui_service: IUIService):
        """
        Initialize the verification service.

        Args:
            logger: Logger service for diagnostic output
            cold_turkey_service: Service for interacting with Cold Turkey Blocker
            thread_service: Service for managing background tasks
            ui_service: Service for UI operations  # <-- Add this doc
        """
        self.logger = logger
        self.cold_turkey_service = cold_turkey_service
        self.thread_service = thread_service
        self.ui_service = ui_service  # <-- Store the UI service
        self.verification_task_id = "verify_block"

        # Add cooldown tracking to prevent rapid verifications
        self._last_verification_time = 0
        self._cooldown_seconds = 60  # 1 minute cooldown

        self.logger.info("Windows Verification Service initialized")



    def verify_platform_block(self, platform: str, block_name: str,
                              cancellable: bool = True) -> Result[bool]:
        """
        Verify that a Cold Turkey block exists and is properly configured for a specific trading platform.

        Args:
            platform: The trading platform name (e.g., "Quantower")
            block_name: Name of the block in Cold Turkey Blocker
            cancellable: Whether the verification process can be cancelled

        Returns:
            Result containing True if verification succeeded, False otherwise
        """
        # Validate prerequisites
        if not self.cold_turkey_service.is_blocker_path_configured():
            return Result.fail("Cold Turkey Blocker path not configured")

        if not block_name:
            return Result.fail("Block name is empty")

        # Check if a verification is already running
        if self.thread_service.is_task_running(self.verification_task_id):
            return Result.fail("Verification already in progress")

        # Check cooldown period
        cooldown_remaining = self.get_cooldown_remaining()
        if cooldown_remaining > 0:
            return Result.fail(f"Please wait {cooldown_remaining} seconds before verifying again")

        try:
            # Create a worker for verification
            worker = VerificationWorker(
                platform=platform,
                block_name=block_name,
                cold_turkey_service=self.cold_turkey_service,
                logger=self.logger
            )

            # Set up completion callback to capture the worker's result and update cooldown
            verification_result = None

            def on_verification_completed(result):
                nonlocal verification_result
                verification_result = result
                self._last_verification_time = time.time()  # Update last verification time

                # Activate main application window
                activate_result = self.ui_service.activate_application_window()
                if activate_result.is_failure:
                    self.logger.warning(f"Failed to activate main window: {activate_result.error}")

            worker.set_on_completed(on_verification_completed)

            # Execute task with auto cleanup
            task_result = self.thread_service.execute_task_with_auto_cleanup(
                self.verification_task_id, worker
            )

            if task_result.is_failure:
                self.logger.error(f"Failed to start verification: {task_result.error}")
                return task_result

            # If not cancellable, wait for completion
            if not cancellable:
                wait_result = self.thread_service.wait_for_task(
                    self.verification_task_id,
                    timeout_ms=30000  # 30 seconds timeout
                )

                if wait_result.is_failure:
                    return Result.fail(wait_result.error)

                # If verification completed successfully
                if verification_result is not None:
                    return Result.ok(verification_result)
                else:
                    return Result.fail("Verification failed or was cancelled")

            # For cancellable verifications, return success to indicate the task was started
            return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Unexpected error starting verification: {e}")
            return Result.fail(f"Unexpected error: {e}")

    def cancel_verification(self) -> Result[bool]:
        """
        Cancel any running verification task.

        Returns:
            Result containing True if a task was cancelled, False if no task was running
        """
        if not self.thread_service.is_task_running(self.verification_task_id):
            return Result.ok(False)  # Nothing to cancel

        return self.thread_service.cancel_task(self.verification_task_id)

    def is_verification_in_progress(self) -> bool:
        """
        Check if a verification task is currently running.

        Returns:
            True if verification is in progress, False otherwise
        """
        return self.thread_service.is_task_running(self.verification_task_id)

    def get_cooldown_remaining(self) -> int:
        """
        Get the remaining cooldown time in seconds before another verification can be started.

        Returns:
            Seconds remaining in cooldown, or 0 if no cooldown is active
        """
        if self._last_verification_time == 0:
            return 0

        current_time = time.time()
        time_since_last = current_time - self._last_verification_time

        if time_since_last >= self._cooldown_seconds:
            return 0

        return int(self._cooldown_seconds - time_since_last)

    def get_verified_blocks(self) -> Result[List[Dict[str, Any]]]:
        """
        Get list of verified platform blocks.

        Returns:
            Result containing a list of platform block configurations
        """
        return self.cold_turkey_service.get_verified_blocks()

    def remove_verified_block(self, platform: str) -> Result[bool]:
        """
        Remove a verified platform block from the saved configuration.

        Args:
            platform: Platform to remove verification for

        Returns:
            Result containing True if removal succeeded, False otherwise
        """
        return self.cold_turkey_service.remove_verified_block(platform)

    def clear_verified_blocks(self) -> Result[bool]:
        """
        Clear all verified platform blocks.

        Returns:
            Result containing True if clearing succeeded, False otherwise
        """
        return self.cold_turkey_service.clear_verified_blocks()

    def is_blocker_path_configured(self) -> bool:
        """
        Check if Cold Turkey Blocker path is configured.

        Returns:
            True if Cold Turkey Blocker path is configured, False otherwise
        """
        return self.cold_turkey_service.is_blocker_path_configured()

    def is_verification_complete(self) -> bool:
        """
        Check if at least one platform block has been verified.

        Returns:
            True if at least one platform has been verified
        """
        verified_blocks_result = self.cold_turkey_service.get_verified_blocks()
        if verified_blocks_result.is_failure:
            return False
        return len(verified_blocks_result.value) > 0