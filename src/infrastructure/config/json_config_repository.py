#NewLayout/src/infrastructure/config/json_config_repository.py

"""
JSON-based implementation of the configuration repository.

Stores configuration in a JSON file on disk.
"""
import os
import json
import threading
from typing import Dict, Any, List

from src.domain.services.i_config_repository_service import IConfigRepository
from src.domain.services.i_logger_service import ILoggerService
from src.domain.common.result import Result


class JsonConfigRepository(IConfigRepository):
    """
    JSON-based implementation of the configuration repository.

    Stores configuration in a JSON file and provides thread-safe access.
    """

    def __init__(self, config_file: str, logger: ILoggerService):
        """
        Initialize the repository.

        Args:
            config_file: Path to the JSON configuration file
            logger: Logger service
        """
        self.config_file = config_file
        self.logger = logger
        self._config_cache = None
        self._last_modified = 0
        self._lock = threading.RLock()
        self._observers = []

        # Default configuration with consistent types
        self.DEFAULT_CONFIG = {
            "default_platforms": ["Quantower", "NinjaTrader", "Tradovate", "TradingView"],
            "platforms": {},
            "cold_turkey_blocker": "",
            "block_settings": {},
            "verified_blocks": [],
            "stop_loss_threshold": 0.0,  # Always store as float
            "lockout_duration": 15,  # Always store as int
            "current_platform": "",  # Ensures this key always exists
            "first_run": True,
            "app_version": "1.0.0"
        }

    def load_config(self, force_reload: bool = False) -> Result[Dict[str, Any]]:
        """
        Load configuration from storage.

        Args:
            force_reload: Whether to force a reload from storage

        Returns:
            Result containing the configuration dictionary
        """
        with self._lock:
            # Check if we should reload due to file modification
            try:
                if os.path.exists(self.config_file):
                    mtime = os.path.getmtime(self.config_file)
                    if mtime > self._last_modified:
                        force_reload = True
                        self._last_modified = mtime
            except Exception as e:
                self.logger.debug(f"Error checking config file modification time: {e}")

            # Return cached config if available and not forced to reload
            if self._config_cache is not None and not force_reload:
                return Result.ok(self._config_cache)

            # Try multiple paths to locate the config file
            config_paths = [
                self.config_file,  # Provided path
                os.path.join(os.getcwd(), os.path.basename(self.config_file)),  # Current directory
                os.path.join(os.path.dirname(os.getcwd()), os.path.basename(self.config_file))  # Parent directory
            ]

            config_found = False
            config = None

            for path in config_paths:
                if os.path.exists(path):
                    try:
                        with open(path, "r") as f:
                            config = json.load(f)
                        self.logger.info(f"Config loaded successfully from {path}")
                        self.config_file = path  # Remember the actual path for future saves
                        config_found = True
                        self._last_modified = os.path.getmtime(path)
                        break
                    except Exception as e:
                        self.logger.error(f"Error loading config from {path}: {e}")

            if not config_found:
                self.logger.warning("Config file not found. Creating new configuration with default settings.")
                config = self.DEFAULT_CONFIG.copy()
                save_result = self.save_config(config)
                if save_result.is_failure:
                    return Result.fail(save_result.error)
            else:
                # Merge missing default keys if any
                updated = False
                for key, default_value in self.DEFAULT_CONFIG.items():
                    if key not in config:
                        config[key] = default_value
                        updated = True

                # Normalize critical data types
                if "stop_loss_threshold" in config and not isinstance(config["stop_loss_threshold"], float):
                    try:
                        config["stop_loss_threshold"] = float(config["stop_loss_threshold"])
                        updated = True
                    except (ValueError, TypeError):
                        config["stop_loss_threshold"] = 0.0
                        updated = True

                if "lockout_duration" in config and not isinstance(config["lockout_duration"], int):
                    try:
                        config["lockout_duration"] = int(config["lockout_duration"])
                        updated = True
                    except (ValueError, TypeError):
                        config["lockout_duration"] = 15
                        updated = True

                if updated:
                    save_result = self.save_config(config)
                    if save_result.is_failure:
                        return Result.fail(save_result.error)

            self._config_cache = config
            return Result.ok(config)

    def save_config(self, config: Dict[str, Any]) -> Result[bool]:
        """
        Save configuration to storage.

        Args:
            config: Configuration dictionary

        Returns:
            Result indicating success or failure
        """
        with self._lock:
            try:
                # Ensure the directory exists
                config_dir = os.path.dirname(self.config_file)
                if config_dir and not os.path.exists(config_dir):
                    os.makedirs(config_dir, exist_ok=True)

                # Write to temporary file first
                temp_path = f"{self.config_file}.tmp"
                with open(temp_path, "w") as f:
                    json.dump(config, f, indent=4)

                # Atomically replace the original file
                # (os.replace is atomic on modern operating systems)
                os.replace(temp_path, self.config_file)

                self.logger.info(f"Config saved successfully to {self.config_file}")
                self._config_cache = config  # Update the cache
                self._last_modified = os.path.getmtime(self.config_file)

                # Notify observers after successful save
                self._notify_observers()
                return Result.ok(True)
            except Exception as e:
                self.logger.error(f"Error saving config: {e}")
                return Result.fail(f"Failed to save config: {e}")

    def get_global_setting(self, key: str, default: Any = None) -> Any:
        """
        Get a global application setting.

        Args:
            key: Setting key
            default: Default value if key not found

        Returns:
            Setting value or default
        """
        with self._lock:
            config_result = self.load_config()
            if config_result.is_failure:
                self.logger.error(f"Error loading config: {config_result.error}")
                return default

            config = config_result.value
            return config.get(key, default)

    def set_global_setting(self, key: str, value: Any) -> Result[bool]:
        """
        Set a global application setting.

        Args:
            key: Setting key
            value: Setting value

        Returns:
            Result indicating success or failure
        """
        with self._lock:
            config_result = self.load_config()
            if config_result.is_failure:
                return Result.fail(config_result.error)

            config = config_result.value
            config[key] = value
            return self.save_config(config)

    def get_platform_settings(self, platform: str) -> Dict[str, Any]:
        """
        Get settings for a specific platform.

        Args:
            platform: Platform name

        Returns:
            Dictionary of platform settings
        """
        with self._lock:
            config_result = self.load_config()
            if config_result.is_failure:
                self.logger.error(f"Error loading config: {config_result.error}")
                return {}

            config = config_result.value
            return config.get("platforms", {}).get(platform, {})

    def save_platform_settings(self, platform: str, settings: Dict[str, Any]) -> Result[bool]:
        """
        Save settings for a specific platform.

        Args:
            platform: Platform name
            settings: Platform settings dictionary

        Returns:
            Result indicating success or failure
        """
        with self._lock:
            config_result = self.load_config()
            if config_result.is_failure:
                return Result.fail(config_result.error)

            config = config_result.value
            if "platforms" not in config:
                config["platforms"] = {}

            config["platforms"][platform] = settings
            return self.save_config(config)

    def get_current_platform(self) -> str:
        """
        Get the currently selected platform.

        Returns:
            Current platform name
        """
        with self._lock:
            config_result = self.load_config()
            if config_result.is_failure:
                self.logger.error(f"Error loading config: {config_result.error}")
                return ""

            config = config_result.value
            current = config.get("current_platform", "")

            # If current platform is not set, try to determine one
            if not current:
                # Try to get from verified blocks
                verified_blocks = config.get("verified_blocks", [])
                for block in verified_blocks:
                    if "platform" in block and block["platform"]:
                        current = block["platform"]
                        break

                # If still not set, use first default platform
                if not current:
                    default_platforms = config.get("default_platforms", ["Quantower"])
                    if default_platforms:
                        current = default_platforms[0]

            return current

    def get_all_platforms(self) -> List[str]:
        """
        Get a list of all configured platforms.

        Returns:
            List of platform names
        """
        with self._lock:
            config_result = self.load_config()
            if config_result.is_failure:
                self.logger.error(f"Error loading config: {config_result.error}")
                return []

            config = config_result.value
            return list(config.get("platforms", {}).keys())

    def get_stop_loss_threshold(self) -> float:
        """
        Get the stop loss threshold as a float.

        Returns:
            Stop loss threshold value
        """
        with self._lock:
            threshold = self.get_global_setting("stop_loss_threshold", 0.0)
            try:
                return float(threshold)
            except (ValueError, TypeError):
                return 0.0

    def get_lockout_duration(self) -> int:
        """
        Get the lockout duration in minutes.

        Returns:
            Lockout duration in minutes
        """
        with self._lock:
            duration = self.get_global_setting("lockout_duration", 15)
            try:
                duration = int(duration)
                if duration < 5:
                    duration = 5
                if duration > 720:
                    duration = 720
                return duration
            except (ValueError, TypeError):
                return 15

    def get_cold_turkey_path(self) -> str:
        """
        Get path to Cold Turkey Blocker executable.

        Returns:
            Path to Cold Turkey Blocker
        """
        with self._lock:
            return self.get_global_setting("cold_turkey_blocker", "")

    def set_stop_loss_threshold(self, value: float) -> Result[bool]:
        """
        Set the stop loss threshold.

        Args:
            value: New threshold value

        Returns:
            Result indicating success or failure
        """
        with self._lock:
            try:
                value = float(value)
            except (ValueError, TypeError):
                return Result.fail("Invalid threshold value, must be a number")

            return self.set_global_setting("stop_loss_threshold", value)

    def set_lockout_duration(self, minutes: int) -> Result[bool]:
        """
        Set the lockout duration in minutes.

        Args:
            minutes: Lockout duration

        Returns:
            Result indicating success or failure
        """
        with self._lock:
            try:
                minutes = int(minutes)
                if minutes < 5:
                    minutes = 5
                if minutes > 720:
                    minutes = 720
                return self.set_global_setting("lockout_duration", minutes)
            except (ValueError, TypeError):
                return Result.fail("Invalid duration value, must be an integer")

    def set_cold_turkey_path(self, path: str) -> Result[bool]:
        """
        Set path to Cold Turkey Blocker executable.

        Args:
            path: Path to Cold Turkey Blocker

        Returns:
            Result indicating success or failure
        """
        with self._lock:
            return self.set_global_setting("cold_turkey_blocker", path)

    def register_observer(self, callback: callable) -> None:
        """
        Register a callback function to be notified of config changes.

        Args:
            callback: Function to call when config changes
        """
        with self._lock:
            if callback not in self._observers:
                self._observers.append(callback)
                self.logger.debug(f"Observer registered: {callback.__qualname__}")

    def unregister_observer(self, callback: callable) -> None:
        """
        Unregister a previously registered observer callback.

        Args:
            callback: Previously registered callback function
        """
        with self._lock:
            if callback in self._observers:
                self._observers.remove(callback)
                self.logger.debug(f"Observer unregistered: {callback.__qualname__}")

    def _notify_observers(self) -> None:
        """Call all registered observer functions."""
        with self._lock:
            observers = self._observers.copy()

        for callback in observers:
            try:
                callback()
            except Exception as e:
                self.logger.error(f"Error notifying observer {callback.__qualname__}: {e}")