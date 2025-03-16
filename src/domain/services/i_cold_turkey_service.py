#src/domain/services/i_cold_turkey_service.py

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from src.domain.common.result import Result


class IColdTurkeyService(ABC):
    """Interface for Cold Turkey Blocker integration."""

    @abstractmethod
    def execute_block_command(self, block_name: str, duration_minutes: int) -> Result[bool]:
        """Execute a block command to lock a specific block."""
        pass

    @abstractmethod
    def verify_block(self, block_name: str, platform: Optional[str] = None,
                     register_if_valid: bool = False) -> Result[bool]:
        """
        Verify that a block exists and is properly configured in Cold Turkey.

        Args:
            block_name: Name of the block in Cold Turkey Blocker
            platform: Optional platform name to associate with the block
            register_if_valid: Whether to register the block if verification succeeds

        Returns:
            Result containing True if verification succeeded, False otherwise
        """
        pass

    @abstractmethod
    def get_blocker_path(self) -> Result[str]:
        """Get the path to the Cold Turkey executable."""
        pass

    @abstractmethod
    def set_blocker_path(self, path: str) -> Result[bool]:
        """Set the path to the Cold Turkey executable."""
        pass

    @abstractmethod
    def get_verified_blocks(self) -> Result[List[Dict[str, Any]]]:
        """Get list of verified platform blocks."""
        pass

    @abstractmethod
    def add_verified_block(self, platform: str, block_name: str) -> Result[bool]:
        """Add a verified platform block to the saved configuration."""
        pass

    @abstractmethod
    def remove_verified_block(self, platform: str) -> Result[bool]:
        """Remove a verified platform block from the saved configuration."""
        pass

    @abstractmethod
    def clear_verified_blocks(self) -> Result[bool]:
        """Clear all verified platform blocks."""
        pass

    @abstractmethod
    def is_blocker_path_configured(self) -> bool:
        """Check if Cold Turkey Blocker path is configured."""
        pass