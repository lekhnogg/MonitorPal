# src/domain/services/i_cold_turkey_service.py

"""
Interface for interacting with Cold Turkey Blocker.
"""
from abc import ABC, abstractmethod
from typing import Optional

# Import Result for type hinting
from src.domain.common.result import Result


class IColdTurkeyService(ABC):
    """
    Interface for services that interact with Cold Turkey Blocker.
    """

    @abstractmethod
    def execute_block_command(self, block_name: str, duration_minutes: int) -> Result[bool]:
        """
        Executes the command-line instruction to start a specific block
        for a given duration.

        Args:
            block_name: The name of the block defined in Cold Turkey.
            duration_minutes: The duration for the block in minutes.

        Returns:
            Result.ok(True) if the command was executed successfully (doesn't guarantee block effectiveness).
            Result.fail(error) if the command execution failed (e.g., process error, timeout).
        """
        pass

    # REMOVED: verify_block method signature

    @abstractmethod
    def get_blocker_path(self) -> Result[str]:
        """
        Gets the configured path to the Cold Turkey Blocker executable.

        Returns:
            Result containing the path string or an error if not configured/found.
        """
        pass

    @abstractmethod
    def set_blocker_path(self, path: str) -> Result[bool]:
        """
        Sets and persists the path to the Cold Turkey Blocker executable.

        Args:
            path: The full path to the executable.

        Returns:
            Result indicating success or failure of saving the path.
        """
        pass

    @abstractmethod
    def is_blocker_path_configured(self) -> bool:
        """
        Checks if the Cold Turkey Blocker path is configured and points
        to an existing file.

        Returns:
            True if configured and exists, False otherwise.
        """
        pass