# src/domain/services/i_config_repository_service.py
"""
Configuration repository interface for application settings.

Defines the contract for storing and retrieving application configuration.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List

from src.domain.common.result import Result


class IConfigRepository(ABC):
    """
    Interface for configuration repository.

    Defines methods for loading, saving, and accessing configuration settings.
    """

    @abstractmethod
    def load_config(self, force_reload: bool = False) -> Result[Dict[str, Any]]:
        """
        Load configuration from storage.

        Args:
            force_reload: Whether to force a reload from storage

        Returns:
            Result containing the configuration dictionary
        """
        pass

    @abstractmethod
    def save_config(self, config: Dict[str, Any]) -> Result[bool]:
        """
        Save configuration to storage.

        Args:
            config: Configuration dictionary

        Returns:
            Result indicating success or failure
        """
        pass

    @abstractmethod
    def get_global_setting(self, key: str, default: Any = None) -> Any:
        """
        Get a global application setting.

        Args:
            key: Setting key
            default: Default value if key not found

        Returns:
            Setting value or default
        """
        pass

    @abstractmethod
    def set_global_setting(self, key: str, value: Any) -> Result[bool]:
        """
        Set a global application setting.

        Args:
            key: Setting key
            value: Setting value

        Returns:
            Result indicating success or failure
        """
        pass

    @abstractmethod
    def get_platform_settings(self, platform: str) -> Dict[str, Any]:
        """
        Get settings for a specific platform.

        Args:
            platform: Platform name

        Returns:
            Dictionary of platform settings
        """
        pass

    @abstractmethod
    def save_platform_settings(self, platform: str, settings: Dict[str, Any]) -> Result[bool]:
        """
        Save settings for a specific platform.

        Args:
            platform: Platform name
            settings: Platform settings dictionary

        Returns:
            Result indicating success or failure
        """
        pass

    @abstractmethod
    def get_current_platform(self) -> str:
        """
        Get the currently selected platform.

        Returns:
            Current platform name
        """
        pass

    @abstractmethod
    def get_all_platforms(self) -> List[str]:
        """
        Get a list of all configured platforms.

        Returns:
            List of platform names
        """
        pass

    @abstractmethod
    def get_stop_loss_threshold(self) -> float:
        """
        Get the stop loss threshold as a float.

        Returns:
            Stop loss threshold value
        """
        pass

    @abstractmethod
    def get_lockout_duration(self) -> int:
        """
        Get the lockout duration in minutes.

        Returns:
            Lockout duration in minutes
        """
        pass

    @abstractmethod
    def get_cold_turkey_path(self) -> str:
        """
        Get path to Cold Turkey Blocker executable.

        Returns:
            Path to Cold Turkey Blocker
        """
        pass

    @abstractmethod
    def set_stop_loss_threshold(self, value: float) -> Result[bool]:
        """
        Set the stop loss threshold.

        Args:
            value: New threshold value

        Returns:
            Result indicating success or failure
        """
        pass

    @abstractmethod
    def set_lockout_duration(self, minutes: int) -> Result[bool]:
        """
        Set the lockout duration in minutes.

        Args:
            minutes: Lockout duration

        Returns:
            Result indicating success or failure
        """
        pass

    @abstractmethod
    def set_cold_turkey_path(self, path: str) -> Result[bool]:
        """
        Set path to Cold Turkey Blocker executable.

        Args:
            path: Path to Cold Turkey Blocker

        Returns:
            Result indicating success or failure
        """
        pass

    @abstractmethod
    def register_observer(self, callback: callable) -> None:
        """
        Register a callback function to be notified of config changes.

        Args:
            callback: Function to call when config changes
        """
        pass

    @abstractmethod
    def unregister_observer(self, callback: callable) -> None:
        """
        Unregister a previously registered observer callback.

        Args:
            callback: Previously registered callback function
        """
        pass