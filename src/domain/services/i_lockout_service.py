#src/domain/services/i_config_repository_service.py

"""
Lockout service interface for handling trading platform lockouts.

Defines the contract for the lockout sequence when thresholds are exceeded.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Callable

from src.domain.common.result import Result


class ILockoutService(ABC):
    """
    Interface for lockout services.

    Defines methods for executing the lockout sequence when a threshold is exceeded.
    """

    @abstractmethod
    def perform_lockout(self,
                       platform: str,
                       flatten_positions: List[Dict[str, Any]],
                       lockout_duration: int,
                       on_status_update: Optional[Callable[[str, str], None]] = None) -> Result[bool]:
        """
        Perform the lockout sequence for a trading platform.

        Args:
            platform: Platform name (e.g., "Quantower")
            flatten_positions: List of dictionaries with "coords" for flatten buttons
            lockout_duration: Lockout duration in minutes
            on_status_update: Optional callback for status updates (message, level)

        Returns:
            Result indicating success or failure
        """
        pass

    @abstractmethod
    def verify_blocker_configuration(self, platform: str, block_name: str) -> Result[bool]:
        """
        Verify that Cold Turkey Blocker is properly configured for the platform.

        Args:
            platform: Platform name
            block_name: Name of the block in Cold Turkey Blocker

        Returns:
            Result indicating whether verification succeeded
        """
        pass

    @abstractmethod
    def get_blocker_path(self) -> Result[str]:
        """
        Get the path to the Cold Turkey Blocker executable.

        Returns:
            Result containing the path to the executable
        """
        pass

    @abstractmethod
    def set_blocker_path(self, path: str) -> Result[bool]:
        """
        Set the path to the Cold Turkey Blocker executable.

        Args:
            path: Path to the Cold Turkey Blocker executable

        Returns:
            Result indicating success or failure
        """
        pass