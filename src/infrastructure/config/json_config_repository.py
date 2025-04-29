# src/infrastructure/config/json_config_repository.py

"""
JSON-based implementation of the configuration repository.

Stores configuration in a JSON file on disk. Supports one verified block per platform
and stores the platform's executable path.
"""
import os
import json
import threading
from typing import Dict, Any, List, Optional, Callable # Added Callable back

# --- Application Imports ---
from src.domain.services.i_config_repository_service import IConfigRepository
from src.domain.services.i_logger_service import ILoggerService
from src.domain.common.result import Result
from src.domain.common.errors import ResourceError, ConfigurationError, ValidationError
from src.domain.services.i_path_service import IPathService


class JsonConfigRepository(IConfigRepository):
    """
    JSON-based implementation of the configuration repository.

    Stores configuration in a JSON file and provides thread-safe access.
    Handles one verified block per platform and platform executable paths.
    """

    def __init__(self, path_service: IPathService, logger: ILoggerService):
        """
        Initialize the repository.

        Args:
            path_service: Path service to determine file locations.
            logger: Logger service.
        """
        self.path_service = path_service
        self.config_file = self.path_service.get_config_file_path()
        self.logger = logger
        self._config_cache: Optional[Dict[str, Any]] = None
        self._last_modified: float = 0.0
        self._lock = threading.RLock()
        self._observers: List[Callable[[], None]] = []

        # Default configuration structure
        try:
            default_base_data_path = self.path_service.get_base_data_path()
        except Exception as e:
            self.logger.error(f"Failed to get default base data path during init: {e}. Using fallback.")
            default_base_data_path = os.path.join(os.getcwd(), "monitorpal_data_fallback")

        self.DEFAULT_CONFIG: Dict[str, Any] = {
            # Global settings
            "app_version": "1.0.0",
            "first_run": True,
            "base_data_path": default_base_data_path,
            "cold_turkey_blocker": "",
            "stop_loss_threshold": -500.0,
            "lockout_duration": 5,
            "monitor_interval_seconds": 2.0,
            "current_platform": "",
            # Platform-specific settings structure (key is platform name)
            "platforms": {
                # Structure will be populated dynamically, no example needed here
            }
        }

        self.logger.debug(f"JsonConfigRepository initialized. Config path: {self.config_file}")
        self.load_config(force_reload=True) # Load initial config

    def load_config(self, force_reload: bool = False) -> Result[Dict[str, Any]]:
        """Load configuration from storage, merging with defaults."""
        with self._lock:
            try:
                should_reload = force_reload
                if os.path.exists(self.config_file):
                    mtime = os.path.getmtime(self.config_file)
                    if mtime > self._last_modified:
                        should_reload = True
                        self._last_modified = mtime
                else:
                    should_reload = True

                if self._config_cache is not None and not should_reload:
                    return Result.ok(self._config_cache)

                config: Dict[str, Any] = {}
                if os.path.exists(self.config_file):
                    try:
                        with open(self.config_file, "r", encoding='utf-8') as f:
                            config = json.load(f)
                        self.logger.info(f"Config loaded successfully from {self.config_file}")
                        self._last_modified = os.path.getmtime(self.config_file)
                    except json.JSONDecodeError as e:
                        self.logger.error(f"Error decoding JSON from config file '{self.config_file}': {e}. Using defaults.")
                        config = self.DEFAULT_CONFIG.copy()
                        self.save_config(config)
                    except Exception as e:
                        self.logger.error(f"Error loading config from {self.config_file}: {e}. Using defaults.")
                        config = self.DEFAULT_CONFIG.copy()
                else:
                    self.logger.warning(f"Config file '{self.config_file}' not found. Creating with default settings.")
                    config = self.DEFAULT_CONFIG.copy()
                    save_result = self.save_config(config)
                    if save_result.is_failure:
                        return Result.fail(save_result.error)

                config = self._merge_and_normalize(config)
                self._config_cache = config
                return Result.ok(config)

            except Exception as e:
                msg = f"Unexpected error during config load: {e}"
                self.logger.error(msg, exc_info=True)
                self._config_cache = self.DEFAULT_CONFIG.copy()
                return Result.fail(ConfigurationError(msg, inner_error=e))

    def _merge_and_normalize(self, loaded_config: Dict[str, Any]) -> Dict[str, Any]:
        """Merges loaded config with defaults and ensures correct types."""
        final_config = self.DEFAULT_CONFIG.copy()

        for key, default_value in self.DEFAULT_CONFIG.items():
            if key in loaded_config:
                loaded_value = loaded_config[key]
                if isinstance(default_value, dict) and isinstance(loaded_value, dict):
                    if key == "platforms":
                         merged_platforms = default_value.copy()
                         for plat_key, plat_loaded_val in loaded_value.items():
                              if isinstance(plat_loaded_val, dict):
                                   plat_defaults = {
                                        "cold_turkey_block_name": "",
                                        "verified_cold_turkey_block": None,
                                        # --- ADDED DEFAULT ---
                                        "platform_executable_path": None, # Default to None if not set
                                        # --- END ADDED ---
                                        "monitor_region": None,
                                        "flatten_regions": {},
                                        "platform_profile": None
                                   }
                                   merged_platform_entry = plat_defaults.copy()
                                   merged_platform_entry.update(plat_loaded_val)
                                   merged_platforms[plat_key] = merged_platform_entry
                              else:
                                   self.logger.warning(f"Ignoring non-dictionary value for platform '{plat_key}' in config.")
                         final_config[key] = merged_platforms
                    else:
                         merged_dict = default_value.copy()
                         merged_dict.update(loaded_value)
                         final_config[key] = merged_dict
                elif isinstance(default_value, list) and isinstance(loaded_value, list):
                     final_config[key] = loaded_value
                else:
                    final_config[key] = loaded_value

        # Type Normalization
        try: final_config["stop_loss_threshold"] = float(final_config.get("stop_loss_threshold", 0.0))
        except (ValueError, TypeError): final_config["stop_loss_threshold"] = 0.0
        try: final_config["lockout_duration"] = int(final_config.get("lockout_duration", 15))
        except (ValueError, TypeError): final_config["lockout_duration"] = 15
        try: final_config["monitor_interval_seconds"] = float(final_config.get("monitor_interval_seconds", 2.0))
        except (ValueError, TypeError): final_config["monitor_interval_seconds"] = 2.0
        final_config["base_data_path"] = str(final_config.get("base_data_path", self.DEFAULT_CONFIG["base_data_path"]))
        final_config["cold_turkey_blocker"] = str(final_config.get("cold_turkey_blocker", ""))
        final_config["current_platform"] = str(final_config.get("current_platform", ""))

        # Normalize nested platform settings
        if "platforms" in final_config and isinstance(final_config["platforms"], dict):
            for plat_key, plat_settings in final_config["platforms"].items():
                 if isinstance(plat_settings, dict):
                     plat_settings["cold_turkey_block_name"] = str(plat_settings.get("cold_turkey_block_name", ""))
                     verified_block = plat_settings.get("verified_cold_turkey_block")
                     if verified_block is not None:
                          plat_settings["verified_cold_turkey_block"] = str(verified_block)
                     # --- ADDED NORMALIZATION ---
                     exec_path = plat_settings.get("platform_executable_path")
                     if exec_path is not None:
                          plat_settings["platform_executable_path"] = str(exec_path)
                     else:
                          plat_settings["platform_executable_path"] = None # Ensure it's None if missing/null
                     # --- END ADDED ---


        return final_config

    def save_config(self, config: Dict[str, Any]) -> Result[bool]:
        """Save configuration to storage."""
        with self._lock:
            try:
                config_dir = os.path.dirname(self.config_file)
                if config_dir and not os.path.exists(config_dir):
                    os.makedirs(config_dir, exist_ok=True)
                temp_path = f"{self.config_file}.tmp"
                with open(temp_path, "w", encoding='utf-8') as f:
                    json.dump(config, f, indent=4, ensure_ascii=False)
                os.replace(temp_path, self.config_file)
                self.logger.info(f"Config saved successfully to {self.config_file}")
                self._config_cache = config
                self._last_modified = os.path.getmtime(self.config_file)
                self._notify_observers()
                return Result.ok(True)
            except PermissionError as e:
                error = ResourceError("Permission denied saving config", {"file": self.config_file}, e)
                self.logger.error(str(error))
                return Result.fail(error)
            except IOError as e:
                error = ResourceError("I/O error saving config", {"file": self.config_file}, e)
                self.logger.error(str(error))
                return Result.fail(error)
            except Exception as e:
                error = ConfigurationError("Failed to save config", {"file": self.config_file}, e)
                self.logger.error(str(error), exc_info=True)
                return Result.fail(error)

    # --- Global Settings ---
    def get_global_setting(self, key: str, default: Any = None) -> Any:
        with self._lock:
            config_result = self.load_config()
            if config_result.is_failure:
                self.logger.error(f"Error loading config for get_global_setting: {config_result.error}")
                return default
            return config_result.value.get(key, default)

    def set_global_setting(self, key: str, value: Any) -> Result[bool]:
        with self._lock:
            config_result = self.load_config()
            if config_result.is_failure:
                return Result.fail(config_result.error)
            config = config_result.value
            config[key] = value
            return self.save_config(config)

    # --- Platform Settings ---
    def get_platform_settings(self, platform: str) -> Dict[str, Any]:
        """Gets settings for a platform, ensuring default keys exist."""
        with self._lock:
            config_result = self.load_config()
            if config_result.is_failure:
                self.logger.error(f"Error loading config for get_platform_settings: {config_result.error}")
                return {
                    "cold_turkey_block_name": "",
                    "verified_cold_turkey_block": None,
                    "platform_executable_path": None, # <-- Added default
                    "monitor_region": None,
                    "flatten_regions": {},
                    "platform_profile": None
                }
            config = config_result.value
            platforms_node = config.setdefault("platforms", {})
            platform_settings = platforms_node.setdefault(platform, {})

            # Ensure essential keys exist
            platform_settings.setdefault("cold_turkey_block_name", "")
            platform_settings.setdefault("verified_cold_turkey_block", None)
            # --- ADDED SETDEFAULT ---
            platform_settings.setdefault("platform_executable_path", None)
            # --- END ADDED ---
            platform_settings.setdefault("monitor_region", None)
            platform_settings.setdefault("flatten_regions", {})
            platform_settings.setdefault("platform_profile", None)

            return platform_settings

    def save_platform_settings(self, platform: str, settings: Dict[str, Any]) -> Result[bool]:
        """Saves settings for a specific platform."""
        with self._lock:
            config_result = self.load_config()
            if config_result.is_failure:
                return Result.fail(config_result.error)
            config = config_result.value
            platforms_node = config.setdefault("platforms", {})
            platforms_node[platform] = settings
            return self.save_config(config)

    # --- NEW: Platform Executable Path Implementation ---
    def get_platform_executable_path(self, platform: str) -> Result[Optional[str]]:
        """Gets the configured executable path for a specific platform."""
        with self._lock:
            try:
                platform_settings = self.get_platform_settings(platform) # Ensures structure
                exec_path = platform_settings.get("platform_executable_path")
                # Ensure it's string or None before returning
                if exec_path is not None and not isinstance(exec_path, str):
                     self.logger.warning(f"Invalid type for platform executable path for {platform}: {type(exec_path)}. Returning None.")
                     return Result.ok(None)
                # Log if path is empty/None but not an error
                if not exec_path:
                     self.logger.debug(f"Platform executable path not configured for {platform}.")
                return Result.ok(exec_path) # Returns str or None
            except Exception as e:
                return Result.fail(ConfigurationError(f"Error getting platform executable path: {e}", inner_error=e))

    def set_platform_executable_path(self, platform: str, path: Optional[str]) -> Result[bool]:
        """Sets the executable path for a specific platform."""
        with self._lock:
            if path is not None and not isinstance(path, str):
                 return Result.fail(ValidationError("Executable path must be a string or None"))
            if path is not None and not path.strip(): # Treat empty string as None
                 path = None

            config_result = self.load_config()
            if config_result.is_failure: return Result.fail(config_result.error)
            config = config_result.value
            try:
                platforms_node = config.setdefault("platforms", {})
                platform_settings = platforms_node.setdefault(platform, {})
                platform_settings["platform_executable_path"] = path # Set str or None
                self.logger.info(f"Set platform_executable_path for '{platform}' to '{path}'")
                return self.save_config(config)
            except Exception as e:
                return Result.fail(ConfigurationError(f"Error setting platform executable path: {e}", inner_error=e))
    # --- END NEW ---


    # --- Region Management (Unchanged) ---
    def get_monitor_region(self, platform: str) -> Result[Optional[Dict[str, Any]]]:
        with self._lock:
            try:
                platform_settings = self.get_platform_settings(platform)
                monitor_region_data = platform_settings.get("monitor_region")
                return Result.ok(monitor_region_data)
            except Exception as e:
                msg = f"Error retrieving monitor region for {platform}: {e}"
                self.logger.error(msg, exc_info=True)
                return Result.fail(ConfigurationError(msg, inner_error=e))

    def get_flatten_region(self, platform: str, region_name: str) -> Result[Optional[Dict[str, Any]]]:
        with self._lock:
            try:
                platform_settings = self.get_platform_settings(platform)
                flatten_regions_dict = platform_settings.get("flatten_regions", {})
                return Result.ok(flatten_regions_dict.get(region_name))
            except Exception as e:
                msg = f"Error retrieving flatten region '{region_name}' for {platform}: {e}"
                self.logger.error(msg, exc_info=True)
                return Result.fail(ConfigurationError(msg, inner_error=e))

    def get_regions_by_platform(self, platform: str, region_type: str) -> Result[List[Dict[str, Any]]]:
        with self._lock:
            try:
                platform_settings = self.get_platform_settings(platform)
                if region_type == "monitor":
                    monitor_region_data = platform_settings.get("monitor_region")
                    return Result.ok([monitor_region_data] if monitor_region_data else [])
                elif region_type == "flatten":
                    flatten_regions_dict = platform_settings.get("flatten_regions", {})
                    return Result.ok(list(flatten_regions_dict.values()))
                else:
                    return Result.fail(ValidationError(f"Unknown region type '{region_type}'"))
            except Exception as e:
                msg = f"Error retrieving regions type '{region_type}' for {platform}: {e}"
                self.logger.error(msg, exc_info=True)
                return Result.fail(ConfigurationError(msg, inner_error=e))

    def save_region(self, platform: str, region_data: Dict[str, Any]) -> Result[bool]:
        with self._lock:
            if not isinstance(region_data, dict) or "type" not in region_data:
                return Result.fail(ConfigurationError("Invalid region data"))
            region_type = region_data["type"]
            region_name = region_data.get("name")

            config_result = self.load_config()
            if config_result.is_failure: return Result.fail(config_result.error)
            config = config_result.value

            try:
                platforms_node = config.setdefault("platforms", {})
                platform_settings = platforms_node.setdefault(platform, {})
                platform_settings.setdefault("monitor_region", None)
                platform_settings.setdefault("flatten_regions", {})

                if region_type == "monitor":
                    platform_settings["monitor_region"] = region_data
                elif region_type == "flatten":
                    if not region_name: return Result.fail(ConfigurationError("Flatten region needs name"))
                    platform_settings["flatten_regions"][region_name] = region_data
                else:
                    return Result.fail(ConfigurationError(f"Unknown region type '{region_type}'"))

                return self.save_config(config)
            except Exception as e:
                return Result.fail(ConfigurationError(f"Error preparing region: {e}", inner_error=e))

    def delete_region(self, platform: str, region_type: str, region_name: str) -> Result[bool]:
        with self._lock:
            config_result = self.load_config()
            if config_result.is_failure: return Result.fail(config_result.error)
            config = config_result.value

            try:
                platforms_node = config.get("platforms", {})
                platform_settings = platforms_node.get(platform)
                if not platform_settings: return Result.ok(True)

                deleted = False
                if region_type == "monitor":
                    if platform_settings.get("monitor_region") is not None:
                        platform_settings["monitor_region"] = None
                        deleted = True
                elif region_type == "flatten":
                    flatten_regions = platform_settings.get("flatten_regions", {})
                    if region_name in flatten_regions:
                        del flatten_regions[region_name]
                        deleted = True
                else:
                    return Result.fail(ConfigurationError(f"Unknown region type '{region_type}'"))

                if deleted:
                    return self.save_config(config)
                else:
                    return Result.ok(True)
            except Exception as e:
                return Result.fail(ConfigurationError(f"Error deleting region: {e}", inner_error=e))

    # --- Verified Block Management (Unchanged) ---
    def get_verified_block(self, platform: str) -> Result[Optional[str]]:
        with self._lock:
            try:
                platform_settings = self.get_platform_settings(platform)
                verified_name = platform_settings.get("verified_cold_turkey_block")
                if verified_name is not None and not isinstance(verified_name, str):
                     self.logger.warning(f"Invalid type for verified block for {platform}: {type(verified_name)}")
                     return Result.ok(None)
                return Result.ok(verified_name)
            except Exception as e:
                return Result.fail(ConfigurationError(f"Error getting verified block: {e}", inner_error=e))

    def set_verified_block(self, platform: str, block_name: Optional[str]) -> Result[bool]:
        with self._lock:
            if block_name is not None and not isinstance(block_name, str):
                 return Result.fail(ValidationError("block_name must be a string or None"))
            config_result = self.load_config()
            if config_result.is_failure: return Result.fail(config_result.error)
            config = config_result.value
            try:
                platforms_node = config.setdefault("platforms", {})
                platform_settings = platforms_node.setdefault(platform, {})
                platform_settings.setdefault("verified_cold_turkey_block", None)
                platform_settings["verified_cold_turkey_block"] = block_name
                self.logger.info(f"Set verified_cold_turkey_block for '{platform}' to '{block_name}'")
                return self.save_config(config)
            except Exception as e:
                return Result.fail(ConfigurationError(f"Error setting verified block: {e}", inner_error=e))

    def clear_all_verified_blocks(self) -> Result[bool]:
        with self._lock:
            config_result = self.load_config()
            if config_result.is_failure: return Result.fail(config_result.error)
            config = config_result.value
            try:
                platforms_node = config.get("platforms", {})
                modified = False
                for plat_settings in platforms_node.values():
                    if isinstance(plat_settings, dict) and plat_settings.get("verified_cold_turkey_block") is not None:
                        plat_settings["verified_cold_turkey_block"] = None
                        modified = True
                if modified:
                    self.logger.info("Clearing verified blocks for all platforms.")
                    return self.save_config(config)
                else:
                    self.logger.info("No verified blocks found to clear.")
                    return Result.ok(False)
            except Exception as e:
                return Result.fail(ConfigurationError(f"Error clearing all verified blocks: {e}", inner_error=e))

    # --- Simple Getters (Unchanged) ---
    def get_current_platform(self) -> str:
        return self.get_global_setting("current_platform", "")

    def get_all_platforms(self) -> Result[List[str]]:
        with self._lock:
            config_result = self.load_config()
            if config_result.is_failure:
                self.logger.error(f"Error loading config for get_all_platforms: {config_result.error}")
                return Result.ok([])
            config = config_result.value
            platforms = list(config.get("platforms", {}).keys())
            return Result.ok(platforms)

    def get_stop_loss_threshold(self) -> float:
        return self.get_global_setting("stop_loss_threshold", 0.0)

    def get_lockout_duration(self) -> int:
        return self.get_global_setting("lockout_duration", 15)

    def get_cold_turkey_path(self) -> str:
        return self.get_global_setting("cold_turkey_blocker", "")

    # --- Simple Setters (Unchanged) ---
    def set_stop_loss_threshold(self, value: float) -> Result[bool]:
        try: value = float(value)
        except (ValueError, TypeError): return Result.fail("Invalid threshold value")
        return self.set_global_setting("stop_loss_threshold", value)

    def set_lockout_duration(self, minutes: int) -> Result[bool]:
        try:
            minutes = int(minutes)
            if minutes < 1: minutes = 1
        except (ValueError, TypeError): return Result.fail("Invalid duration value")
        return self.set_global_setting("lockout_duration", minutes)

    def set_cold_turkey_path(self, path: str) -> Result[bool]:
        return self.set_global_setting("cold_turkey_blocker", path)

    # --- Observer Pattern (Unchanged) ---
    def register_observer(self, callback: Callable[[], None]) -> None:
        with self._lock:
            if callback not in self._observers:
                self._observers.append(callback)
                self.logger.debug(f"Observer registered: {callback.__qualname__}")

    def unregister_observer(self, callback: Callable[[], None]) -> None:
        with self._lock:
            if callback in self._observers:
                self._observers.remove(callback)
                self.logger.debug(f"Observer unregistered: {callback.__qualname__}")

    def _notify_observers(self) -> None:
        with self._lock:
            observers_copy = self._observers.copy()
        for callback in observers_copy:
            try: callback()
            except Exception as e: self.logger.error(f"Error notifying observer {callback.__qualname__}: {e}")