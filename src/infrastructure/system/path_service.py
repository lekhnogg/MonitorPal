# src/infrastructure/system/path_service.py
import os
import re

import platformdirs
from typing import Optional # <--- Added Optional

from src.domain.services.i_path_service import IPathService

# from src.domain.services.i_config_repository_service import IConfigRepository
from src.domain.common.di_container import DIContainer # <--- Import container if resolving lazily
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_config_repository_service import IConfigRepository # Keep for type hint

# Define your app name and author (used by platformdirs)
APP_NAME = "MonitorPal"
APP_AUTHOR = "GlebDev"

class PathService(IPathService):
    """Provides standard application paths using platformdirs."""


    def __init__(self, logger: ILoggerService): # Removed config_repository from constructor
        """ Initialize the PathService. Determines default paths immediately. """
        self.logger = logger
        # --- Removed config_repository storage ---
        # self.config_repository = config_repository
        self._base_data_path: Optional[str] = None # Cache the determined path
        self._config_file_path: Optional[str] = None
        self._override_checked: bool = False # Flag to check override only once

        # Determine paths immediately using defaults
        self._determine_default_paths()
        self._ensure_directories_exist()

    def _determine_default_paths(self):
        """Determine configuration and base data paths using defaults."""
        # Config File Path (using platformdirs)
        self._config_file_path = os.path.join(
            platformdirs.user_config_dir(APP_NAME, APP_AUTHOR),
            "config.json"
        )
        self.logger.debug(f"Default config file location determined: {self._config_file_path}")

        # Base Data Path (using platformdirs - NO override check here)
        self._base_data_path = platformdirs.user_data_dir(APP_NAME, APP_AUTHOR)
        self.logger.debug(f"Default base data path determined: {self._base_data_path}")

    def _ensure_directories_exist(self):
        """Ensures the base directories determined by default exist."""
        try:
            config_dir = os.path.dirname(self._config_file_path)
            if config_dir: os.makedirs(config_dir, exist_ok=True)

            if self._base_data_path: os.makedirs(self._base_data_path, exist_ok=True)
            else: self.logger.error("Base data path could not be determined by defaults.")

        except OSError as e:
            self.logger.error(f"Failed to create necessary default directories: {e}", exc_info=True)
            # Handle this critical failure appropriately

    def get_base_data_path(self) -> str:
        """
        Gets the root directory for user-specific application data.
        Checks config override on first call.
        """
        # --- Lazy check for config override ---
        if not self._override_checked:
            self._override_checked = True # Prevent re-checking
            try:
                # Need access to the container or config repo instance here
                # Passing the container is one way, though not ideal DI practice.
                # A better way might be a setter method called after init.
                # Let's try resolving lazily (requires DI container access):

                # --- Option A: Resolve lazily (if PathService gets container) ---
                # from src.application.app import get_container # Or pass container in __init__
                # container = get_container()
                # config_repo = container.resolve(IConfigRepository)
                # base_path_override = config_repo.get_global_setting("base_data_path", None)

                # --- Option B: Assume a setter was called (Preferred DI) ---
                # Requires adding a `set_config_repository` method and calling it in app.py
                if hasattr(self, '_config_repository') and self._config_repository:
                    base_path_override = self._config_repository.get_global_setting("base_data_path", None)
                    if base_path_override and os.path.isabs(base_path_override):
                        # Validate if path is writable? Optional.
                        self.logger.info(f"Applying base data path override from config: {base_path_override}")
                        self._base_data_path = base_path_override
                        # Ensure the overridden directory exists too
                        try:
                            os.makedirs(self._base_data_path, exist_ok=True)
                        except OSError as e:
                             self.logger.error(f"Failed to create overridden base data directory '{self._base_data_path}': {e}", exc_info=True)
                             # Decide how to handle this - fallback to default? Raise?
                    else:
                         # Config value exists but isn't valid, log warning
                         if base_path_override is not None: # Check it wasn't just missing
                              self.logger.warning(f"Config setting 'base_data_path' ('{base_path_override}') is not a valid absolute path. Using default: {self._base_data_path}")

            except Exception as e:
                self.logger.error(f"Error checking config for base_data_path override: {e}", exc_info=True)
                # Proceed with the default path determined earlier

        if not self._base_data_path:
             # This should ideally not happen if defaults work
             self.logger.error("Base data path is unexpectedly None.")
             # Fallback to a very basic default in case platformdirs failed
             return os.path.join(os.getcwd(), "trading_monitor_data_fallback")

        return self._base_data_path


    def set_config_repository(self, config_repo: IConfigRepository):
        """Allows setting the config repository after PathService initialization."""
        self.logger.debug("Config repository instance provided to PathService.")
        self._config_repository = config_repo

    def get_config_file_path(self) -> str:
        """Gets the full path to the main configuration file."""
        if not self._config_file_path:
             self.logger.error("Config file path was not determined during init.")
             # Fallback or raise error
             return os.path.join(os.getcwd(), "config_fallback.json")
        return self._config_file_path

    def get_platform_base_path(self, platform: str) -> str:
        path = os.path.join(self.get_base_data_path(), platform)
        return path

    def get_platform_regions_path(self, platform: str) -> str:
        path = os.path.join(self.get_platform_base_path(platform), "regions")
        try: os.makedirs(path, exist_ok=True)
        except OSError as e: self.logger.error(f"Failed create platform regions dir '{path}': {e}", exc_info=True)
        return path

    def get_platform_monitoring_path(self, platform: str) -> str:
        path = os.path.join(self.get_platform_base_path(platform), "monitoring")
        try: os.makedirs(path, exist_ok=True)
        except OSError as e: self.logger.error(f"Failed create platform monitoring dir '{path}': {e}", exc_info=True)
        return path

    def get_region_screenshot_path(self, platform: str, region_type: str, region_name: str) -> str:
        """
        Constructs the standard path for saving/finding a specific region's screenshot.
        Ensures the necessary directory structure exists.
        """
        if not platform or not region_type or not region_name:
            self.logger.error(
                f"Invalid arguments for get_region_screenshot_path: p={platform}, t={region_type}, n={region_name}")
            return os.path.join(self.get_screenshots_base_path(), "invalid_region_name.png")

        platform_dir = self.get_platform_regions_path(platform)  # Ensures creation
        safe_region_name = re.sub(r'[^\w\-]+', '_', region_name)
        filename = f"{platform}_{region_type}_{safe_region_name}_original.png"
        full_path = os.path.join(platform_dir, filename)
        self.logger.debug(f"Determined region screenshot path: {full_path}")
        return full_path