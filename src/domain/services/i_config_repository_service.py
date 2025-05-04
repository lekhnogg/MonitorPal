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

    # --- Platform Executable Path Methods ---
    @abstractmethod
    def get_platform_executable_path(self, platform: str) -> Result[Optional[str]]:
        """Gets the configured executable path for a specific platform."""
        pass

    @abstractmethod
    def set_platform_executable_path(self, platform: str, path: Optional[str]) -> Result[bool]:
        """Sets the executable path for a specific platform."""
        pass

    # --- NEW: Platform-Specific Risk Parameter Methods ---
    @abstractmethod
    def get_platform_stop_loss_threshold(self, platform: str) -> Result[float]:
        """Gets the stop loss threshold for a specific platform."""
        pass

    @abstractmethod
    def set_platform_stop_loss_threshold(self, platform: str, value: float) -> Result[bool]:
        """Sets the stop loss threshold for a specific platform."""
        pass

    @abstractmethod
    def get_platform_lockout_duration(self, platform: str) -> Result[int]:
        """Gets the lockout duration in minutes for a specific platform."""
        pass

    @abstractmethod
    def set_platform_lockout_duration(self, platform: str, minutes: int) -> Result[bool]:
        """Sets the lockout duration in minutes for a specific platform."""
        pass
    # --- END NEW ---

    # --- Region Management ---
    @abstractmethod
    def get_monitor_region(self, platform: str) -> Result[Optional[Dict[str, Any]]]: pass
    @abstractmethod
    def get_flatten_region(self, platform: str, region_name: str) -> Result[Optional[Dict[str, Any]]]: pass
    @abstractmethod
    def get_regions_by_platform(self, platform: str, region_type: str) -> Result[List[Dict[str, Any]]]: pass
    @abstractmethod
    def save_region(self, platform: str, region_data: Dict[str, Any]) -> Result[bool]: pass
    @abstractmethod
    def delete_region(self, platform: str, region_type: str, region_name: str) -> Result[bool]: pass

    # --- Verified Block Management ---
    @abstractmethod
    def get_verified_block(self, platform: str) -> Result[Optional[str]]: pass
    @abstractmethod
    def set_verified_block(self, platform: str, block_name: Optional[str]) -> Result[bool]: pass
    @abstractmethod
    def clear_all_verified_blocks(self) -> Result[bool]: pass

    # --- Simple Getters (Convenience) ---
    @abstractmethod
    def get_current_platform(self) -> str: pass
    @abstractmethod
    def get_all_platforms(self) -> Result[List[str]]: pass

    @abstractmethod
    def get_cold_turkey_path(self) -> str: pass # Keep Global
    # Keep get_global_setting("monitor_interval_seconds", ...) for interval

    # --- Simple Setters (Convenience) ---

    @abstractmethod
    def set_cold_turkey_path(self, path: str) -> Result[bool]: pass # Keep Global
    # Keep set_global_setting("monitor_interval_seconds", ...) for interval

    # --- Observer Pattern ---
    @abstractmethod
    def register_observer(self, callback: Callable[[], None]) -> None: pass
    @abstractmethod
    def unregister_observer(self, callback: Callable[[], None]) -> None: pass