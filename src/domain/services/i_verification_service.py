# src/domain/services/i_verification_service.py
"""
Interface for verifying platform blocks in Cold Turkey Blocker.

This service verifies that Cold Turkey Blocker is properly configured
for blocking trading platforms.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

from src.domain.common.result import Result


class IVerificationService(ABC):
    """
    Service for verifying platform blocks in Cold Turkey Blocker.
    """

    @abstractmethod
    def verify_block(self, platform: str, block_name: str,
                     cancellable: bool = True) -> Result[bool]:
        """
        Verify that a Cold Turkey block exists and is properly configured.

        Args:
            platform: Platform name
            block_name: Cold Turkey block name
            cancellable: Whether the verification can be cancelled by the user

        Returns:
            Result indicating success or failure
        """
        pass

    @abstractmethod
    def cancel_verification(self) -> Result[bool]:
        """
        Cancel any running verification task.

        Returns:
            Result indicating success or failure
        """
        pass

    @abstractmethod
    def get_verified_blocks(self) -> Result[List[Dict[str, Any]]]:
        """
        Get list of verified platform blocks.

        Returns:
            Result containing list of verified blocks
        """
        pass

    @abstractmethod
    def add_verified_block(self, platform: str, block_name: str) -> Result[bool]:
        """
        Add a verified platform block to the saved configuration.

        Args:
            platform: Platform name
            block_name: Cold Turkey block name

        Returns:
            Result indicating success or failure
        """
        pass

    @abstractmethod
    def remove_verified_block(self, platform: str) -> Result[bool]:
        """
        Remove a verified platform block from the saved configuration.

        Args:
            platform: Platform name to remove

        Returns:
            Result indicating success or failure
        """
        pass

    @abstractmethod
    def clear_verified_blocks(self) -> Result[bool]:
        """
        Clear all verified platform blocks.

        Returns:
            Result indicating success or failure
        """
        pass

    @abstractmethod
    def is_blocker_path_configured(self) -> bool:
        """
        Check if Cold Turkey Blocker path is configured.

        Returns:
            True if path is configured, False otherwise
        """
        pass

    @abstractmethod
    def is_verification_complete(self) -> bool:
        """
        Check if at least one platform block has been verified.

        Returns:
            True if at least one block is verified, False otherwise
        """
        pass