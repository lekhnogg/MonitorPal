#src/domain/services/i_verification_service.py

from abc import ABC, abstractmethod
from typing import List, Dict, Any
from src.domain.common.result import Result


class IVerificationService(ABC):
    """
    Service for verifying platform blocks in Cold Turkey Blocker.

    This service coordinates the verification process, handling rate limiting,
    background threading, and user feedback for Cold Turkey Blocker verification.
    """

    @abstractmethod
    def verify_platform_block(self, platform: str, block_name: str, cancellable: bool = True) -> Result[bool]:
        """
        Verify that a Cold Turkey block exists and is properly configured for a specific trading platform.

        This method coordinates the verification process in a background thread, with rate limiting
        and cancellation support.

        Args:
            platform: The trading platform name (e.g., "Quantower")
            block_name: Name of the block in Cold Turkey Blocker
            cancellable: Whether the verification process can be cancelled

        Returns:
            Result containing True if verification succeeded, False otherwise
        """
        pass

    @abstractmethod
    def cancel_verification(self) -> Result[bool]:
        """
        Cancel any running verification task.

        Returns:
            Result containing True if a task was cancelled, False if no task was running
        """
        pass

    @abstractmethod
    def is_verification_in_progress(self) -> bool:
        """
        Check if a verification task is currently running.

        Returns:
            True if verification is in progress, False otherwise
        """
        pass

    @abstractmethod
    def get_cooldown_remaining(self) -> int:
        """
        Get the remaining cooldown time in seconds before another verification can be started.

        Returns:
            Seconds remaining in cooldown, or 0 if no cooldown is active
        """
        pass

    @abstractmethod
    def get_verified_blocks(self) -> Result[List[Dict[str, Any]]]:
        """
        Get list of verified platform blocks.

        Returns:
            Result containing a list of platform block configurations
        """
        pass

    @abstractmethod
    def remove_verified_block(self, platform: str) -> Result[bool]:
        """
        Remove a verified platform block from the saved configuration.

        Args:
            platform: Platform to remove verification for

        Returns:
            Result containing True if removal succeeded, False otherwise
        """
        pass

    @abstractmethod
    def clear_verified_blocks(self) -> Result[bool]:
        """
        Clear all verified platform blocks.

        Returns:
            Result containing True if clearing succeeded, False otherwise
        """
        pass

    @abstractmethod
    def is_verification_complete(self) -> bool:
        """
        Check if at least one platform block has been verified.

        Returns:
            True if at least one platform has been verified
        """
        pass

    @abstractmethod
    def is_blocker_path_configured(self) -> bool:
        """
        Check if Cold Turkey Blocker path is configured.

        Returns:
            True if Cold Turkey Blocker path is configured, False otherwise
        """
        pass