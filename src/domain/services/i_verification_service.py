# src/domain/services/i_verification_service.py

"""
Interface for the Verification Service.

Defines methods for verifying Cold Turkey Blocker configuration and integration.
"""
from abc import ABC, abstractmethod
from typing import Optional, Callable

# Import Result for type hinting
from src.domain.common.result import Result


class IVerificationService(ABC):
    """
    Interface for verifying platform blocking configurations.
    """

    @abstractmethod
    def verify_platform_block(self,
                              platform: str,
                              block_name: str,
                              # --- ADDED PARAMETER ---
                              platform_executable_path: str,
                              # --- END ADDED ---
                              on_started: Callable[[], None],
                              on_completed: Callable[[bool, str], None],
                              on_error: Callable[[str, str], None]) -> Result[bool]:
        """
        Starts the asynchronous verification process for a block/platform.

        Implementations should trigger checks (e.g., UI, file monitoring,
        process launch checks) to confirm the specified block effectively
        prevents the target platform (identified by platform_executable_path)
        from running or being accessed. Updates configuration repository
        via callbacks upon successful verification.

        Args:
            platform: Name of the trading platform.
            block_name: Name of the Cold Turkey block to verify.
            platform_executable_path: Full path to the trading platform's executable.
            on_started: Callback function executed when verification starts.
            on_completed: Callback function executed on completion
                          (args: overall_success (bool), platform_name (str)).
            on_error: Callback function executed on error
                      (args: error_message (str), platform_name (str)).

        Returns:
            Result.ok(True) if the verification task was started successfully.
            Result.fail(error) if starting the task failed immediately.
        """
        pass

    @abstractmethod
    def cancel_verification(self) -> Result[bool]:
        """
        Request cancellation of any ongoing verification task.

        Returns:
            Result indicating if cancellation request was successful.
            Does not guarantee immediate termination.
        """
        pass

    @abstractmethod
    def is_verification_in_progress(self) -> bool:
        """Check if a verification task is currently running."""
        pass

    @abstractmethod
    def get_cooldown_remaining(self) -> int:
        """
        Get the remaining cooldown time in seconds before another
        verification can be started.
        """
        pass

    # --- Optional Helper Methods ---

    @abstractmethod
    def is_blocker_path_configured(self) -> bool:
        """Check if the path to the blocker executable is configured and valid."""
        pass

    @abstractmethod
    def is_verification_complete(self) -> bool:
        """
        Check if the currently selected platform is considered verified
        based on stored configuration.
        """
        pass