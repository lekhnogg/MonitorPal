# src/infrastructure/config/json_config_repository.py

"""
JSON-based implementation of the configuration repository.

Stores configuration in a JSON file on disk. Supports platform-specific
settings including risk parameters, verified blocks, executable paths,
regions, and profiles.
"""
import os
import json
import threading
from typing import Dict, Any, List, Optional, Callable

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
    """

    # --- Defaults for platform-specific risk params ---
    DEFAULT_PLATFORM_THRESHOLD = -100.0
    DEFAULT_PLATFORM_DURATION = 15
    # --- End Defaults ---

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

        # Determine default base path early
        try:
            default_base_data_path = self.path_service.get_base_data_path()
        except Exception as e:
            self.logger.error(f"Failed to get default base data path during init: {e}. Using fallback.")
            default_base_data_path = os.path.join(os.getcwd(), "monitorpal_data_fallback")

        # Define the structure, removing legacy and global risk params
        self.DEFAULT_CONFIG: Dict[str, Any] = {
            # Global settings
            "app_version": "1.0.0",
            "first_run": True,
            "base_data_path": default_base_data_path,
            "cold_turkey_blocker": "",
            # Global monitor interval (could be moved to platform if needed)
            "monitor_interval_seconds": 2.0,
            "current_platform": "",
            "theme": "dark",
            # Platform-specific settings structure (key is platform name)
            "platforms": {
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
                    try:
                        mtime = os.path.getmtime(self.config_file)
                        if mtime > self._last_modified:
                            should_reload = True
                            self._last_modified = mtime
                    except OSError as e:
                        self.logger.warning(f"Could not get modification time for {self.config_file}: {e}")
                        should_reload = True # Force reload if we can't check time
                else:
                    should_reload = True # File doesn't exist, need to load/create defaults

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
                        self.logger.error(f"Error decoding JSON from '{self.config_file}': {e}. Recreating with defaults.")
                        config = self.DEFAULT_CONFIG.copy()
                        # Attempt to save the default config immediately
                        save_res = self.save_config(config)
                        if save_res.is_failure: return Result.fail(save_res.error) # Return error if save fails
                    except Exception as e:
                        self.logger.error(f"Error loading config from {self.config_file}: {e}. Using defaults.")
                        config = self.DEFAULT_CONFIG.copy()
                else:
                    self.logger.warning(f"Config file '{self.config_file}' not found. Creating with default settings.")
                    config = self.DEFAULT_CONFIG.copy()
                    save_result = self.save_config(config)
                    if save_result.is_failure:
                        return Result.fail(save_result.error)

                # Ensure the loaded config conforms to the expected structure
                config = self._merge_and_normalize(config)
                self._config_cache = config
                return Result.ok(config)

            except Exception as e:
                msg = f"Unexpected error during config load: {e}"
                self.logger.error(msg, exc_info=True)
                # Fallback to default config in case of unexpected errors
                self._config_cache = self.DEFAULT_CONFIG.copy()
                return Result.fail(ConfigurationError(msg, inner_error=e))

    def _merge_and_normalize(self, loaded_config: Dict[str, Any]) -> Dict[str, Any]:
        """Merges loaded config with defaults and ensures correct types and structure."""
        # Start with a fresh copy of the default structure
        final_config = self.DEFAULT_CONFIG.copy()

        # Update top-level keys from loaded config
        for key, default_value in self.DEFAULT_CONFIG.items():
            if key != "platforms" and key in loaded_config:
                 # Simple assignment for non-dict/non-platform values
                 # Type normalization happens later
                 final_config[key] = loaded_config[key]

        # --- Handle the "platforms" dictionary specifically ---
        final_config["platforms"] = {} # Ensure it's an empty dict initially
        loaded_platforms = loaded_config.get("platforms", {})
        if isinstance(loaded_platforms, dict):
            for plat_key, plat_loaded_val in loaded_platforms.items():
                if isinstance(plat_loaded_val, dict):
                    # Define the default structure for EACH platform entry
                    plat_defaults = {
                        "cold_turkey_block_name": "",
                        "verified_cold_turkey_block": None,
                        "platform_executable_path": None,
                        "stop_loss_threshold": self.DEFAULT_PLATFORM_THRESHOLD, # Use class default
                        "lockout_duration": self.DEFAULT_PLATFORM_DURATION,   # Use class default
                        "monitor_region": None,
                        "flatten_regions": {},
                        "platform_profile": None # Profile itself has internal defaults handled by ProfileService
                    }
                    merged_platform_entry = plat_defaults.copy()
                    merged_platform_entry.update(plat_loaded_val) # Overwrite defaults with loaded values

                    # --- Normalize types within the platform entry ---
                    merged_platform_entry["cold_turkey_block_name"] = str(merged_platform_entry.get("cold_turkey_block_name", ""))
                    verified_block = merged_platform_entry.get("verified_cold_turkey_block")
                    merged_platform_entry["verified_cold_turkey_block"] = str(verified_block) if verified_block is not None else None
                    exec_path = merged_platform_entry.get("platform_executable_path")
                    merged_platform_entry["platform_executable_path"] = str(exec_path) if exec_path is not None else None
                    try: merged_platform_entry["stop_loss_threshold"] = float(merged_platform_entry.get("stop_loss_threshold", self.DEFAULT_PLATFORM_THRESHOLD))
                    except (ValueError, TypeError): merged_platform_entry["stop_loss_threshold"] = self.DEFAULT_PLATFORM_THRESHOLD
                    try: merged_platform_entry["lockout_duration"] = int(merged_platform_entry.get("lockout_duration", self.DEFAULT_PLATFORM_DURATION))
                    except (ValueError, TypeError): merged_platform_entry["lockout_duration"] = self.DEFAULT_PLATFORM_DURATION
                    # Region/profile validation happens when they are accessed/parsed by respective services
                    if not isinstance(merged_platform_entry.get("flatten_regions"), dict): merged_platform_entry["flatten_regions"] = {}
                    # --- End Platform Entry Normalization ---

                    final_config["platforms"][plat_key] = merged_platform_entry
                else:
                    self.logger.warning(f"Ignoring non-dictionary value for platform '{plat_key}' in loaded config.")
        else:
             self.logger.warning("Loaded 'platforms' key is not a dictionary. Ignoring.")


        # --- Normalize GLOBAL settings ---
        try: final_config["monitor_interval_seconds"] = float(final_config.get("monitor_interval_seconds", 2.0))
        except (ValueError, TypeError): final_config["monitor_interval_seconds"] = 2.0
        final_config["base_data_path"] = str(final_config.get("base_data_path", self.DEFAULT_CONFIG["base_data_path"]))
        final_config["cold_turkey_blocker"] = str(final_config.get("cold_turkey_blocker", ""))
        final_config["current_platform"] = str(final_config.get("current_platform", ""))
        final_config["first_run"] = bool(final_config.get("first_run", True))
        final_config["theme"] = str(final_config.get("theme", "dark")).lower()  # Ensure lowercase
        if final_config["theme"] not in ["light", "dark"]:
            self.logger.warning(f"Invalid theme value '{final_config['theme']}' found in config. Defaulting to 'dark'.")
            final_config["theme"] = "dark"  # Default to dark if invalid


        # Legacy migration code removed

        return final_config

    # Legacy migration method removed

    def save_config(self, config: Dict[str, Any]) -> Result[bool]:
        """Save configuration to storage."""
        with self._lock:
            try:
                # Ensure the config structure is reasonably valid before saving
                # (Simple check: ensure 'platforms' key exists and is a dict)
                if "platforms" not in config or not isinstance(config["platforms"], dict):
                     # This indicates a severe internal issue, maybe revert to cache or default?
                     self.logger.error("Attempted to save invalid config structure (missing 'platforms' dict). Aborting save.")
                     return Result.fail(ConfigurationError("Internal error: Invalid config structure prepared for saving."))

                config_dir = os.path.dirname(self.config_file)
                if config_dir and not os.path.exists(config_dir):
                    os.makedirs(config_dir, exist_ok=True)

                temp_path = f"{self.config_file}.tmp.{os.getpid()}" # Add PID for more robustness
                try:
                    with open(temp_path, "w", encoding='utf-8') as f:
                        json.dump(config, f, indent=4, ensure_ascii=False)
                    os.replace(temp_path, self.config_file) # Atomic replace on most OS
                except Exception as write_err:
                     # Ensure temp file is removed if writing or replacement fails
                     if os.path.exists(temp_path):
                          try: os.remove(temp_path)
                          except OSError as rm_err: self.logger.error(f"Failed to remove temp config file '{temp_path}': {rm_err}")
                     raise write_err # Re-raise the original error

                self.logger.info(f"Config saved successfully to {self.config_file}")
                self._config_cache = config.copy() # Update cache with the saved config
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
        # This method implicitly uses the normalized cache from load_config
        with self._lock:
            config_result = self.load_config()
            if config_result.is_failure:
                self.logger.error(f"Error loading config for get_global_setting: {config_result.error}")
                return default
            # Get directly from the top level of the cached config
            return config_result.value.get(key, default)

    def set_global_setting(self, key: str, value: Any) -> Result[bool]:
        with self._lock:
            config_result = self.load_config()
            if config_result.is_failure:
                return Result.fail(config_result.error)
            config = config_result.value
            # Prevent modification of the 'platforms' structure via this method
            if key == "platforms":
                 return Result.fail(ValidationError("Cannot modify 'platforms' structure via set_global_setting."))
            config[key] = value
            # Consider adding type normalization here based on DEFAULT_CONFIG if needed
            return self.save_config(config)

    # --- Platform Settings ---
    def get_platform_settings(self, platform: str) -> Dict[str, Any]:
        """
        Gets settings for a platform, ensuring default keys exist.
        Returns a copy to prevent direct modification of the cache.
        """
        with self._lock:
            config_result = self.load_config()
            # Define the default structure expected for *any* platform entry
            platform_defaults = {
                "cold_turkey_block_name": "",
                "verified_cold_turkey_block": None,
                "platform_executable_path": None,
                "stop_loss_threshold": self.DEFAULT_PLATFORM_THRESHOLD,
                "lockout_duration": self.DEFAULT_PLATFORM_DURATION,
                "monitor_region": None,
                "flatten_regions": {},
                "platform_profile": None
            }
            if config_result.is_failure:
                self.logger.error(f"Error loading config for get_platform_settings('{platform}'). Returning defaults.")
                return platform_defaults.copy()

            config = config_result.value
            platforms_node = config.setdefault("platforms", {})

            # Get the specific platform's settings, or an empty dict if it doesn't exist yet
            platform_settings = platforms_node.get(platform, {})

            # Ensure all essential keys exist by merging with defaults
            # This handles both new platforms and potentially corrupted existing entries
            merged_settings = platform_defaults.copy()
            merged_settings.update(platform_settings) # Overwrite defaults with loaded values

            # If the platform wasn't originally in the config, add it now with merged defaults
            if platform not in platforms_node:
                 platforms_node[platform] = merged_settings
                 # Save immediately? Or wait for explicit save? Let's wait.
                 # self.save_config(config) # Optionally save immediately upon first access

            return merged_settings.copy() # Return a copy

    def save_platform_settings(self, platform: str, settings: Dict[str, Any]) -> Result[bool]:
        """Saves the *entire* settings dictionary for a specific platform."""
        with self._lock:
            if not isinstance(settings, dict):
                 return Result.fail(ValidationError("Invalid 'settings' type provided, must be a dictionary."))

            config_result = self.load_config()
            if config_result.is_failure:
                return Result.fail(config_result.error)
            config = config_result.value
            platforms_node = config.setdefault("platforms", {})
            # Directly replace the platform's entry with the provided settings dictionary
            platforms_node[platform] = settings
            return self.save_config(config)

    # --- Platform Executable Path Implementation ---
    def get_platform_executable_path(self, platform: str) -> Result[Optional[str]]:
        with self._lock:
            try:
                platform_settings = self.get_platform_settings(platform) # Ensures structure and defaults
                exec_path = platform_settings.get("platform_executable_path")
                if exec_path is not None and not isinstance(exec_path, str):
                     self.logger.warning(f"Invalid type for platform executable path for {platform}: {type(exec_path)}. Returning None.")
                     return Result.ok(None)
                if not exec_path:
                     self.logger.debug(f"Platform executable path not configured for {platform}.")
                return Result.ok(exec_path)
            except Exception as e:
                return Result.fail(ConfigurationError(f"Error getting platform executable path for '{platform}': {e}", inner_error=e))

    def set_platform_executable_path(self, platform: str, path: Optional[str]) -> Result[bool]:
        with self._lock:
            if path is not None and not isinstance(path, str):
                 return Result.fail(ValidationError("Executable path must be a string or None"))
            path = path.strip() if path else None # Treat empty string as None

            try:
                platform_settings = self.get_platform_settings(platform) # Get existing/default settings
                platform_settings["platform_executable_path"] = path # Update the specific key
                # Save the entire updated settings dict back
                return self.save_platform_settings(platform, platform_settings)
            except Exception as e:
                return Result.fail(ConfigurationError(f"Error setting platform executable path for '{platform}': {e}", inner_error=e))

    # --- NEW Platform-Specific Risk Parameter Methods ---
    def get_platform_stop_loss_threshold(self, platform: str) -> Result[float]:
        """Gets the stop loss threshold for a specific platform."""
        with self._lock:
            try:
                settings = self.get_platform_settings(platform)
                value = settings.get("stop_loss_threshold", self.DEFAULT_PLATFORM_THRESHOLD)
                # Ensure correct type
                try: return Result.ok(float(value))
                except (ValueError, TypeError):
                    self.logger.warning(f"Invalid stop_loss_threshold type for {platform} ('{value}'). Returning default.")
                    return Result.ok(self.DEFAULT_PLATFORM_THRESHOLD)
            except Exception as e:
                return Result.fail(ConfigurationError(f"Error getting threshold for {platform}: {e}", inner_error=e))

    def set_platform_stop_loss_threshold(self, platform: str, value: float) -> Result[bool]:
        """Sets the stop loss threshold for a specific platform."""
        with self._lock:
            try:
                # Validate type
                value = float(value)
                # Ensure negative
                value = -abs(value)
            except (ValueError, TypeError):
                return Result.fail(ValidationError("Invalid threshold value provided."))

            try:
                settings = self.get_platform_settings(platform)
                settings["stop_loss_threshold"] = value
                return self.save_platform_settings(platform, settings)
            except Exception as e:
                return Result.fail(ConfigurationError(f"Error setting threshold for {platform}: {e}", inner_error=e))

    def get_platform_lockout_duration(self, platform: str) -> Result[int]:
        """Gets the lockout duration in minutes for a specific platform."""
        with self._lock:
            try:
                settings = self.get_platform_settings(platform)
                value = settings.get("lockout_duration", self.DEFAULT_PLATFORM_DURATION)
                # Ensure correct type
                try: return Result.ok(int(value))
                except (ValueError, TypeError):
                    self.logger.warning(f"Invalid lockout_duration type for {platform} ('{value}'). Returning default.")
                    return Result.ok(self.DEFAULT_PLATFORM_DURATION)
            except Exception as e:
                return Result.fail(ConfigurationError(f"Error getting duration for {platform}: {e}", inner_error=e))

    def set_platform_lockout_duration(self, platform: str, minutes: int) -> Result[bool]:
        """Sets the lockout duration in minutes for a specific platform."""
        with self._lock:
            try:
                # Validate type and range
                minutes = int(minutes)
                if minutes < 1: minutes = 1 # Ensure minimum duration
            except (ValueError, TypeError):
                return Result.fail(ValidationError("Invalid duration value provided."))

            try:
                settings = self.get_platform_settings(platform)
                settings["lockout_duration"] = minutes
                return self.save_platform_settings(platform, settings)
            except Exception as e:
                return Result.fail(ConfigurationError(f"Error setting duration for {platform}: {e}", inner_error=e))
    # --- END NEW ---


    # --- Region Management (Largely Unchanged, uses save_platform_settings indirectly) ---
    def get_monitor_region(self, platform: str) -> Result[Optional[Dict[str, Any]]]:
        with self._lock:
            try:
                platform_settings = self.get_platform_settings(platform)
                monitor_region_data = platform_settings.get("monitor_region")
                # Basic validation on retrieve
                if monitor_region_data is not None and not isinstance(monitor_region_data, dict):
                     self.logger.warning(f"Invalid monitor_region data type for {platform}. Returning None.")
                     return Result.ok(None)
                return Result.ok(monitor_region_data)
            except Exception as e:
                return Result.fail(ConfigurationError(f"Error retrieving monitor region for {platform}: {e}", inner_error=e))

    def get_flatten_region(self, platform: str, region_name: str) -> Result[Optional[Dict[str, Any]]]:
        with self._lock:
            try:
                platform_settings = self.get_platform_settings(platform)
                flatten_regions_dict = platform_settings.get("flatten_regions", {})
                region_data = flatten_regions_dict.get(region_name)
                if region_data is not None and not isinstance(region_data, dict):
                     self.logger.warning(f"Invalid flatten_region data type for {platform}/{region_name}. Returning None.")
                     return Result.ok(None)
                return Result.ok(region_data)
            except Exception as e:
                 return Result.fail(ConfigurationError(f"Error retrieving flatten region '{region_name}' for {platform}: {e}", inner_error=e))

    def get_regions_by_platform(self, platform: str, region_type: str) -> Result[List[Dict[str, Any]]]:
        with self._lock:
            try:
                platform_settings = self.get_platform_settings(platform)
                if region_type == "monitor":
                    monitor_region_data = platform_settings.get("monitor_region")
                    return Result.ok([monitor_region_data] if monitor_region_data else [])
                elif region_type == "flatten":
                    flatten_regions_dict = platform_settings.get("flatten_regions", {})
                    # Ensure we return a list of valid dictionaries
                    valid_regions = [v for v in flatten_regions_dict.values() if isinstance(v, dict)]
                    return Result.ok(valid_regions)
                else:
                    return Result.fail(ValidationError(f"Unknown region type '{region_type}'"))
            except Exception as e:
                return Result.fail(ConfigurationError(f"Error retrieving regions type '{region_type}' for {platform}: {e}", inner_error=e))

    def save_region(self, platform: str, region_data: Dict[str, Any]) -> Result[bool]:
        # Saves region data within the platform's settings structure
        with self._lock:
            if not isinstance(region_data, dict) or "type" not in region_data:
                return Result.fail(ConfigurationError("Invalid region data format"))
            region_type = region_data["type"]
            region_name = region_data.get("name") # Name is crucial for flatten

            try:
                settings = self.get_platform_settings(platform) # Get current settings dict

                if region_type == "monitor":
                    settings["monitor_region"] = region_data
                elif region_type == "flatten":
                    if not region_name: return Result.fail(ConfigurationError("Flatten region must have a name"))
                    # Ensure flatten_regions key exists and is a dict
                    if "flatten_regions" not in settings or not isinstance(settings["flatten_regions"], dict):
                        settings["flatten_regions"] = {}
                    settings["flatten_regions"][region_name] = region_data
                else:
                    return Result.fail(ConfigurationError(f"Unknown region type '{region_type}'"))

                # Save the entire modified settings dict back
                return self.save_platform_settings(platform, settings)
            except Exception as e:
                return Result.fail(ConfigurationError(f"Error preparing/saving region for {platform}: {e}", inner_error=e))

    def delete_region(self, platform: str, region_type: str, region_name: str) -> Result[bool]:
        with self._lock:
            try:
                settings = self.get_platform_settings(platform)
                modified = False

                if region_type == "monitor":
                    if settings.get("monitor_region") is not None:
                        settings["monitor_region"] = None
                        modified = True
                elif region_type == "flatten":
                    flatten_regions = settings.get("flatten_regions", {})
                    if isinstance(flatten_regions, dict) and region_name in flatten_regions:
                        del flatten_regions[region_name]
                        # No need to reassign flatten_regions back to settings dict
                        # as we are modifying the dict obtained from settings in-place
                        modified = True
                else:
                    return Result.fail(ConfigurationError(f"Unknown region type '{region_type}'"))

                if modified:
                    return self.save_platform_settings(platform, settings)
                else:
                    self.logger.debug(f"Region '{region_name}' ({region_type}) not found for {platform}, no deletion needed.")
                    return Result.ok(True) # Indicate success (desired state achieved)
            except Exception as e:
                return Result.fail(ConfigurationError(f"Error deleting region for {platform}: {e}", inner_error=e))

    # --- Verified Block Management (Unchanged, operates on platform settings) ---
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
                return Result.fail(ConfigurationError(f"Error getting verified block for {platform}: {e}", inner_error=e))

    def set_verified_block(self, platform: str, block_name: Optional[str]) -> Result[bool]:
        with self._lock:
            if block_name is not None and not isinstance(block_name, str):
                 return Result.fail(ValidationError("block_name must be a string or None"))
            try:
                settings = self.get_platform_settings(platform)
                settings["verified_cold_turkey_block"] = block_name
                self.logger.info(f"Set verified_cold_turkey_block for '{platform}' to '{block_name}'")
                return self.save_platform_settings(platform, settings)
            except Exception as e:
                return Result.fail(ConfigurationError(f"Error setting verified block for {platform}: {e}", inner_error=e))

    def clear_all_verified_blocks(self) -> Result[bool]:
        with self._lock:
            config_result = self.load_config()
            if config_result.is_failure: return Result.fail(config_result.error)
            config = config_result.value
            modified = False
            try:
                platforms_node = config.get("platforms", {})
                for plat_key, plat_settings in platforms_node.items():
                    if isinstance(plat_settings, dict) and plat_settings.get("verified_cold_turkey_block") is not None:
                        plat_settings["verified_cold_turkey_block"] = None
                        modified = True
                if modified:
                    self.logger.info("Clearing verified blocks for all platforms.")
                    return self.save_config(config)
                else:
                    self.logger.info("No verified blocks found to clear.")
                    return Result.ok(False) # Indicate no change was made
            except Exception as e:
                return Result.fail(ConfigurationError(f"Error clearing all verified blocks: {e}", inner_error=e))

    # --- Simple Getters ---
    def get_current_platform(self) -> str:
        # Uses global setting
        return self.get_global_setting("current_platform", "")

    def get_all_platforms(self) -> Result[List[str]]:
        # Reads keys from the 'platforms' dictionary
        with self._lock:
            config_result = self.load_config()
            if config_result.is_failure:
                self.logger.error(f"Error loading config for get_all_platforms: {config_result.error}")
                return Result.ok([]) # Return empty list on error
            config = config_result.value
            platforms = list(config.get("platforms", {}).keys())
            return Result.ok(platforms)

    def get_cold_turkey_path(self) -> str:
        # Uses global setting
        return self.get_global_setting("cold_turkey_blocker", "")

    # --- Simple Setters (Only global ones remain here) ---
    def set_cold_turkey_path(self, path: str) -> Result[bool]:
        # Uses global setting
        path = path.strip() if path else ""
        return self.set_global_setting("cold_turkey_blocker", path)

    # Removed set_stop_loss_threshold and set_lockout_duration (now platform-specific)

    # --- Observer Pattern (Unchanged) ---
    def register_observer(self, callback: Callable[[], None]) -> None:
        with self._lock:
            if callback not in self._observers:
                self._observers.append(callback)
                self.logger.debug(f"Observer registered: {callback.__qualname__}")

    def unregister_observer(self, callback: Callable[[], None]) -> None:
        with self._lock:
            try:
                self._observers.remove(callback)
                self.logger.debug(f"Observer unregistered: {callback.__qualname__}")
            except ValueError:
                self.logger.debug(f"Attempted to unregister observer not found: {callback.__qualname__}")


    def _notify_observers(self) -> None:
        # Must be called *without* the main lock held to prevent deadlocks
        # if an observer tries to access the config repository.
        with self._lock:
            # Make a copy of the observer list while holding the lock
            observers_copy = self._observers[:]
        # Release the lock before calling callbacks
        self.logger.debug(f"Notifying {len(observers_copy)} observers of config change.")
        for callback in observers_copy:
            try:
                callback()
            except Exception as e:
                self.logger.error(f"Error notifying observer {getattr(callback, '__qualname__', repr(callback))}: {e}", exc_info=True)