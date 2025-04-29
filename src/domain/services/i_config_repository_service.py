# src/domain/services/i_config_repository_service.py

"""
Interface for configuration repository service.

Defines methods for accessing and modifying application settings.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Callable # Keep Callable for observers

# Import Result for type hinting return values
from src.domain.common.result import Result

class IConfigRepository(ABC):
    """Interface for managing application configuration."""

    @abstractmethod
    def load_config(self, force_reload: bool = False) -> Result[Dict[str, Any]]:
        """Load configuration from storage."""
        pass

    @abstractmethod
    def save_config(self, config: Dict[str, Any]) -> Result[bool]:
        """Save configuration to storage."""
        pass

    # --- Global Settings ---

    @abstractmethod
    def get_global_setting(self, key: str, default: Any = None) -> Any:
        """Get a global configuration setting."""
        pass

    @abstractmethod
    def set_global_setting(self, key: str, value: Any) -> Result[bool]:
        """Set a global configuration setting."""
        pass

    # --- Platform Specific Settings ---

    @abstractmethod
    def get_platform_settings(self, platform: str) -> Dict[str, Any]:
        """Get all settings for a specific platform."""
        pass

    @abstractmethod
    def save_platform_settings(self, platform: str, settings: Dict[str, Any]) -> Result[bool]:
        """Save all settings for a specific platform."""
        pass

    # --- NEW: Platform Executable Path Methods ---
    @abstractmethod
    def get_platform_executable_path(self, platform: str) -> Result[Optional[str]]:
        """Gets the configured executable path for a specific platform."""
        pass

    @abstractmethod
    def set_platform_executable_path(self, platform: str, path: Optional[str]) -> Result[bool]:
        """Sets the executable path for a specific platform."""
        pass
    # --- END NEW ---

    # --- Region Management ---

    @abstractmethod
    def get_monitor_region(self, platform: str) -> Result[Optional[Dict[str, Any]]]:
        """Get the monitor region data for a platform."""
        pass

    @abstractmethod
    def get_flatten_region(self, platform: str, region_name: str) -> Result[Optional[Dict[str, Any]]]:
        """Get a specific flatten region data for a platform."""
        pass

    @abstractmethod
    def get_regions_by_platform(self, platform: str, region_type: str) -> Result[List[Dict[str, Any]]]:
        """Get all regions of a specific type for a platform."""
        pass

    @abstractmethod
    def save_region(self, platform: str, region_data: Dict[str, Any]) -> Result[bool]:
        """Save region data for a platform."""
        pass

    @abstractmethod
    def delete_region(self, platform: str, region_type: str, region_name: str) -> Result[bool]:
        """Delete region data for a platform."""
        pass

    # --- Verified Block Management ---

    @abstractmethod
    def get_verified_block(self, platform: str) -> Result[Optional[str]]:
        """Gets the name of the verified Cold Turkey block for a specific platform."""
        pass

    @abstractmethod
    def set_verified_block(self, platform: str, block_name: Optional[str]) -> Result[bool]:
        """Sets or clears the verified Cold Turkey block name for a specific platform."""
        pass

    @abstractmethod
    def clear_all_verified_blocks(self) -> Result[bool]:
        """Clears the verified block name for ALL configured platforms."""
        pass

    # --- Simple Getters (Convenience) ---

    @abstractmethod
    def get_current_platform(self) -> str:
        """Get the currently selected platform name."""
        pass

    @abstractmethod
    def get_all_platforms(self) -> Result[List[str]]:
        """Gets list of platforms present in the configuration."""
        pass

    @abstractmethod
    def get_stop_loss_threshold(self) -> float:
        """Get the stop loss threshold value."""
        pass

    @abstractmethod
    def get_lockout_duration(self) -> int:
        """Get the lockout duration in minutes."""
        pass

    @abstractmethod
    def get_cold_turkey_path(self) -> str:
        """Get the configured path to the Cold Turkey Blocker executable."""
        pass

    # --- Simple Setters (Convenience) ---

    @abstractmethod
    def set_stop_loss_threshold(self, value: float) -> Result[bool]:
        """Set the stop loss threshold value."""
        pass

    @abstractmethod
    def set_lockout_duration(self, minutes: int) -> Result[bool]:
        """Set the lockout duration in minutes."""
        pass

    @abstractmethod
    def set_cold_turkey_path(self, path: str) -> Result[bool]:
        """Set the path to the Cold Turkey Blocker executable."""
        pass

    # --- Observer Pattern ---

    @abstractmethod
    def register_observer(self, callback: Callable[[], None]) -> None:
        """Register an observer to be notified of config changes."""
        pass

    @abstractmethod
    def unregister_observer(self, callback: Callable[[], None]) -> None:
        """Unregister an observer."""
        pass