# src/presentation/view_models/settings_view_model.py

import os
from typing import Optional, List, Dict, Any

# --- Qt Imports ---
from PySide6.QtCore import QObject, Signal, Slot

# --- Application Imports ---
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_config_repository_service import IConfigRepository
from src.domain.services.i_platform_selection_service import IPlatformSelectionService
from src.domain.services.i_cold_turkey_service import IColdTurkeyService
from src.domain.services.i_verification_service import IVerificationService
from src.domain.services.i_path_service import IPathService
from src.domain.services.i_ui_service import IUIService # For file browsing/messages
from src.domain.common.result import Result


class SettingsViewModel(QObject):
    """
    ViewModel for the Settings tab.

    Manages configuration settings like paths, monitoring parameters,
    Cold Turkey integration, and other application options.
    """

    # --- Signals for View updates ---

    # Platform Integration Section
    # Note: Platform selection itself is handled globally, but we might display the selected one
    # selected_platform_name_changed = Signal(str) # Handled by MainView usually
    cold_turkey_path_changed = Signal(str)
    cold_turkey_block_name_changed = Signal(str)
    verification_status_changed = Signal(str, str) # status_text, color ("Verified"/"Not Verified"/"Error", "green"/"gray"/"red")
    can_verify_block_changed = Signal(bool) # Enable state for Verify button
    verified_blocks_changed = Signal(list)  # Add this signal
    can_clear_verified_blocks_changed = Signal(bool)  # Add this signal

    # Monitoring Settings Section
    stop_loss_threshold_changed = Signal(float)
    check_interval_changed = Signal(float) # Assuming interval is float seconds
    lockout_duration_changed = Signal(int)
    # auto_start_monitoring_changed = Signal(bool) # If implemented
    # sound_alerts_changed = Signal(bool) # If implemented
    # visual_alerts_changed = Signal(bool) # If implemented

    # Advanced Settings Section
    # log_level_changed = Signal(str) # If implemented
    data_directory_changed = Signal(str)
    # fullscreen_overlay_changed = Signal(bool) # If implemented
    # keep_history_days_changed = Signal(int) # If implemented
    # save_screenshots_changed = Signal(bool) # If implemented

    # General
    status_message_changed = Signal(str, str) # message, level ("INFO", "ERROR", etc.)
    settings_saved = Signal(bool) # True on success, False on failure
    settings_reset = Signal() # Signal that defaults have been applied


    def __init__(self,
                 logger: ILoggerService,
                 config_repo: IConfigRepository,
                 platform_selection_service: IPlatformSelectionService,
                 cold_turkey_service: IColdTurkeyService,
                 verification_service: IVerificationService,
                 path_service: IPathService,
                 ui_service: IUIService,
                 parent: Optional[QObject] = None):
        """Initialize the SettingsViewModel."""
        super().__init__(parent)
        self._logger = logger
        self._config_repo = config_repo
        self._platform_selection_service = platform_selection_service
        self._cold_turkey_service = cold_turkey_service
        self._verification_service = verification_service
        self._path_service = path_service
        self._ui_service = ui_service

        # Internal state - Needs to be loaded initially
        self._selected_platform: Optional[str] = None
        self._ct_path: str = ""
        self._ct_block_name: str = ""
        self._threshold: float = -100.0
        self._interval: float = 2.0
        self._duration: int = 15
        self._data_dir: str = ""
        self._verified_blocks_list: List[str] = []
        self._can_clear_verified: bool = False
        # Add other state variables as needed for advanced settings

        self._logger.debug("Initializing SettingsViewModel...")
        self._platform_selection_service.register_platform_change_listener(
            self._handle_platform_selection_change
        )
        initial_platform = self._platform_selection_service.get_current_platform()
        self._load_settings_for_platform(initial_platform) # Load initial state
        self._logger.debug("SettingsViewModel initialized.")

    # --- Command Slots (Called by the View) ---

    @Slot()
    def browse_cold_turkey_path(self):
        """Opens a file dialog to select the Cold Turkey executable."""
        self._logger.debug("Browse for Cold Turkey path requested.")
        current_path = self._ct_path or ""
        # Assuming UIService provides a blocking file selection method
        result = self._ui_service.select_file(
            "Select Cold Turkey Blocker Executable",
            "Executables (*.exe);;All Files (*)"
            # Add initial directory based on current_path if desired
        )

        if result.is_success and result.value:
            new_path = result.value
            self._logger.info(f"Cold Turkey path selected: {new_path}")
            # Update internal state and emit signal (will trigger view update)
            self._set_cold_turkey_path(new_path)
            # Check verification status again since path changed
            self._update_verification_status()
        elif result.is_failure:
            self.status_message_changed.emit(f"Could not open file dialog: {result.error}", "ERROR")
        else: # User cancelled
             self.status_message_changed.emit("File selection cancelled.", "INFO")

    @Slot(str)
    def set_cold_turkey_path_text(self, path: str):
        """Handles manual text input for CT path (less common)."""
        # Basic validation - check if path seems plausible (e.g., ends with .exe)
        if path and path.lower().endswith(".exe"):
            self._logger.debug(f"Setting Cold Turkey path from text input: {path}")
            # Update internal state and emit signal
            self._set_cold_turkey_path(path)
            self._update_verification_status()
        elif path:
             self._logger.warning(f"Ignoring potential invalid CT path input: {path}")
        # If path is empty, do nothing or reset to current saved path? Let's do nothing.

    @Slot(str)
    def set_cold_turkey_block_name(self, block_name: str):
        """Updates the Cold Turkey block name state."""
        block_name = block_name.strip()
        if block_name != self._ct_block_name:
            self._logger.debug(f"Setting Cold Turkey block name: {block_name}")
            self._ct_block_name = block_name
            self.cold_turkey_block_name_changed.emit(self._ct_block_name)
            # Update verification status as name changed
            self._update_verification_status()

    @Slot()
    def verify_block_configuration(self):
        """Starts the Cold Turkey block verification process."""
        if not self._selected_platform:
            self.status_message_changed.emit("Select a platform first.", "ERROR")
            return
        if not self._ct_block_name:
            self.status_message_changed.emit("Enter a Cold Turkey Block Name.", "ERROR")
            return
        if not self._ct_path or not os.path.exists(self._ct_path):
             self.status_message_changed.emit("Cold Turkey path is not valid.", "ERROR")
             return

        self.status_message_changed.emit(f"Verifying block '{self._ct_block_name}' for {self._selected_platform}...", "INFO")
        self.verification_status_changed.emit("Verifying...", "orange")
        self.can_verify_block_changed.emit(False) # Disable button during verification

        # --- Call Verification Service (non-cancellable for this button press) ---
        # Note: verify_platform_block might run in background if not cancellable=False
        # but here we assume it blocks or we wait. Let's assume we wait.
        verify_result = self._verification_service.verify_platform_block(
            platform=self._selected_platform,
            block_name=self._ct_block_name,
            cancellable=False # Make it block until done for simplicity here
        )

        # Update status based on result
        if verify_result.is_success and verify_result.value:
            self.status_message_changed.emit("Block verification successful!", "SUCCESS")
            self.verification_status_changed.emit("Verified", "green")
        else:
            err_msg = verify_result.error if verify_result.is_failure else "Verification conditions not met."
            self.status_message_changed.emit(f"Block verification failed: {err_msg}", "ERROR")
            self.verification_status_changed.emit("Verification Failed", "red")

        self.can_verify_block_changed.emit(True) # Re-enable button


    @Slot(float)
    def set_stop_loss_threshold(self, value: float):
        """Updates the stop loss threshold state."""
        # Ensure value is negative or zero
        value = -abs(value)
        if value != self._threshold:
            self._logger.debug(f"Setting Stop Loss Threshold: {value}")
            self._threshold = value
            self.stop_loss_threshold_changed.emit(self._threshold)

    @Slot(float)
    def set_check_interval(self, value: float):
        """Updates the monitoring check interval state."""
        value = max(0.5, value) # Ensure minimum interval
        if value != self._interval:
            self._logger.debug(f"Setting Check Interval: {value}s")
            self._interval = value
            self.check_interval_changed.emit(self._interval)

    @Slot(int)
    def set_lockout_duration(self, value: int):
        """Updates the lockout duration state."""
        value = max(1, value) # Ensure minimum duration
        if value != self._duration:
             self._logger.debug(f"Setting Lockout Duration: {value} min")
             self._duration = value
             self.lockout_duration_changed.emit(self._duration)

    # --- Add slots for other settings as needed (LogLevel, FullscreenOverlay, etc.) ---
    # @Slot(str) def set_log_level(self, level): ...
    # @Slot(bool) def set_fullscreen_overlay(self, enabled): ...

    @Slot()
    def save_settings(self):
        """Saves all current settings from the ViewModel state to the config repository."""
        self._logger.info("Saving settings...")
        self.status_message_changed.emit("Saving settings...", "INFO")

        # Use a flag to track if any save operation failed
        any_failed = False
        failure_messages = []

        # --- Save Global Settings ---
        results = [
            self._config_repo.set_global_setting("cold_turkey_blocker", self._ct_path),
            self._config_repo.set_global_setting("stop_loss_threshold", self._threshold),
            self._config_repo.set_global_setting("lockout_duration", self._duration),
            self._config_repo.set_global_setting("monitor_interval_seconds", self._interval),
            # Add other global settings here...
            # self._config_repo.set_global_setting("log_level", self._log_level),
        ]

        for res in results:
            if res.is_failure:
                any_failed = True
                failure_messages.append(f"Global setting save failed: {res.error}")
                self._logger.error(f"Global setting save failed: {res.error}")

        # --- Save Platform-Specific Settings (Cold Turkey Block Name) ---
        # Need to load current platform settings, update the block name, then save back
        if self._selected_platform:
            platform_settings = self._config_repo.get_platform_settings(self._selected_platform)
            # Ensure block name is saved per platform if needed, or handle globally if appropriate
            # Example: Storing it under the platform node
            platform_settings["cold_turkey_block_name"] = self._ct_block_name
            res_plat = self._config_repo.save_platform_settings(self._selected_platform, platform_settings)
            if res_plat.is_failure:
                any_failed = True
                failure_messages.append(f"Platform setting save failed: {res_plat.error}")
                self._logger.error(f"Platform setting save failed: {res_plat.error}")

        # --- Emit final status ---
        if any_failed:
            full_error_msg = "Failed to save one or more settings:\n- " + "\n- ".join(failure_messages)
            self.status_message_changed.emit(full_error_msg, "ERROR")
            self.settings_saved.emit(False)
        else:
            self.status_message_changed.emit("Settings saved successfully.", "SUCCESS")
            self.settings_saved.emit(True)
            # Optionally re-load settings to ensure consistency (though cache should be updated)
            self._load_settings_for_platform(self._selected_platform)

    @Slot()
    def reset_to_defaults(self):
        """Resets settings in the ViewModel to application defaults."""
        # Note: This resets the *ViewModel's state*. Saving is separate.
        self._logger.warning("Resetting settings to defaults (ViewModel state only).")
        self.status_message_changed.emit("Resetting settings to defaults...", "INFO")

        # Get default values from config repo's DEFAULT_CONFIG or service methods
        default_config = self._config_repo.DEFAULT_CONFIG # Access default structure
        self._set_cold_turkey_path(default_config.get("cold_turkey_blocker", ""))
        self._ct_block_name = "" # Reset block name for selected platform? Requires careful thought. Let's clear it.
        self.cold_turkey_block_name_changed.emit(self._ct_block_name)
        self.set_stop_loss_threshold(default_config.get("stop_loss_threshold", 0.0)) # Use setters to emit signals
        self.set_check_interval(default_config.get("monitor_interval_seconds", 2.0))
        self.set_lockout_duration(default_config.get("lockout_duration", 15))
        self._data_dir = self._path_service.get_base_data_path() # Get current effective data path
        self.data_directory_changed.emit(self._data_dir)
        # Reset other settings...

        self._update_verification_status() # Re-check verification
        self.settings_reset.emit() # Signal that reset happened
        self.status_message_changed.emit("Settings reset to defaults. Click 'Save Settings' to apply.", "INFO")

    @Slot()
    def clear_verified_blocks(self):
        """Clears all verified blocks via the service."""
        self._logger.warning("Clear all verified blocks requested.")

        # Optional: Confirmation dialog
        confirm_res = self._ui_service.show_confirmation(
            "Confirm Clear",
            "Are you sure you want to remove all verified block records?"
        )
        if confirm_res.is_failure or not confirm_res.value:
            self.status_message_changed.emit("Clear verified blocks cancelled.", "INFO")
            return

        self.status_message_changed.emit("Clearing verified blocks...", "INFO")
        clear_res = self._verification_service.clear_verified_blocks()

        if clear_res.is_success:
            self.status_message_changed.emit("Verified blocks cleared successfully.", "SUCCESS")
            self._load_verified_blocks_list()  # Reload the (now empty) list
        else:
            self.status_message_changed.emit(f"Failed to clear verified blocks: {clear_res.error}", "ERROR")

    # --- Private Helper / Update Methods ---

    @Slot(str)
    def _handle_platform_selection_change(self, platform: str):
        """Loads settings when the globally selected platform changes."""
        self._logger.debug(f"SettingsViewModel received platform change: {platform}")
        self._load_settings_for_platform(platform)

    def _load_settings_for_platform(self, platform: str):
        """Loads settings from the repository for the given platform and updates state."""
        self._selected_platform = platform
        self._logger.info(f"Loading settings for platform: {platform}")

        # --- Load Global Settings ---
        self._set_cold_turkey_path(self._config_repo.get_cold_turkey_path())  # Use helper setter
        self._threshold = self._config_repo.get_stop_loss_threshold()
        self._interval = self._config_repo.get_global_setting("monitor_interval_seconds", 2.0)
        self._duration = self._config_repo.get_lockout_duration()
        self._data_dir = self._path_service.get_base_data_path()  # Get effective path

        # --- Load Platform-Specific Settings ---
        if platform:
            platform_settings = self._config_repo.get_platform_settings(platform)
            # Load block name specific to this platform, default to empty if not found
            self._ct_block_name = platform_settings.get("cold_turkey_block_name", "")
        else:
            self._ct_block_name = ""  # No platform, no block name

        # --- Load Verified Blocks List --- ADDED THIS SECTION ---
        self._load_verified_blocks_list()
        # --- END ADDED SECTION ---

        # --- Emit Signals to Update View ---
        self.cold_turkey_block_name_changed.emit(self._ct_block_name)
        self.stop_loss_threshold_changed.emit(self._threshold)
        self.check_interval_changed.emit(self._interval)
        self.lockout_duration_changed.emit(self._duration)
        self.data_directory_changed.emit(self._data_dir)
        # Emit signals for other loaded settings...

        # --- Update derived state ---
        self._update_verification_status()  # This depends on block name/path loaded above

        self._logger.debug(f"Settings loaded for {platform}.")

    def _set_cold_turkey_path(self, path: str):
        """Internal helper to update CT path state and emit signal."""
        path = path or "" # Ensure empty string instead of None
        if path != self._ct_path:
            self._ct_path = path
            self.cold_turkey_path_changed.emit(self._ct_path)

    def _update_verification_status(self):
        """Checks if the current platform/block combination is verified."""
        status = "N/A"
        color = "gray"
        can_verify = False

        if self._selected_platform and self._ct_block_name and self._ct_path and os.path.exists(self._ct_path):
             can_verify = True # Enable button if we have the info needed
             verified_blocks_res = self._verification_service.get_verified_blocks()
             is_verified = False
             if verified_blocks_res.is_success:
                  for block in verified_blocks_res.value:
                       if block.get("platform") == self._selected_platform and \
                          block.get("block_name") == self._ct_block_name:
                            is_verified = True
                            break
             if is_verified:
                  status = "Verified"
                  color = "green"
             else:
                  status = "Not Verified"
                  color = "red"
        elif not self._selected_platform:
             status = "Select Platform"
        elif not self._ct_path or not os.path.exists(self._ct_path):
             status = "Set CT Path"
        elif not self._ct_block_name:
             status = "Enter Block Name"

        self.verification_status_changed.emit(status, color)
        self.can_verify_block_changed.emit(can_verify)

    def _load_verified_blocks_list(self):
        """Loads the list of verified blocks and updates state/signals."""
        self._logger.debug("Loading verified blocks list...")
        verified_blocks_res = self._verification_service.get_verified_blocks()
        formatted_list = []
        can_clear = False
        if verified_blocks_res.is_success:
            for block_info in verified_blocks_res.value:
                plat = block_info.get('platform', 'Unknown')
                name = block_info.get('block_name', 'Unknown')
                formatted_list.append(f"{plat}: {name}")
            can_clear = bool(formatted_list)  # Enable clear if list is not empty
            self._verified_blocks_list = formatted_list
        else:
            self.status_message_changed.emit(f"Failed to load verified blocks: {verified_blocks_res.error}", "ERROR")
            self._verified_blocks_list = ["Error loading list..."]
            can_clear = False

        self.verified_blocks_changed.emit(self._verified_blocks_list)
        self.can_clear_verified_blocks_changed.emit(can_clear)