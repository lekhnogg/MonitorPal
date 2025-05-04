# src/presentation/view_models/settings_view_model.py

import os
from typing import Optional, List, Dict, Any

# --- Qt Imports ---
from PySide6.QtCore import QObject, Signal, Slot, QTimer

# --- Application Imports ---
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_config_repository_service import IConfigRepository
from src.domain.services.i_platform_selection_service import IPlatformSelectionService
from src.domain.services.i_cold_turkey_service import IColdTurkeyService
from src.domain.services.i_verification_service import IVerificationService
from src.domain.services.i_path_service import IPathService
from src.domain.services.i_ui_service import IUIService
from src.domain.common.result import Result
from src.domain.common.errors import ConfigurationError, ValidationError # Added ValidationError


class SettingsViewModel(QObject):
    """
    ViewModel for the Settings tab.

    Manages global configuration (paths, interval) and platform-specific
    settings (block name, exe path, risk parameters).
    """

    # --- Signals for View updates ---
    # Global Settings
    cold_turkey_path_changed = Signal(str)
    check_interval_changed = Signal(float) # Global monitoring interval
    data_directory_changed = Signal(str)

    # Platform-Specific Settings
    cold_turkey_block_name_changed = Signal(str)
    platform_executable_path_changed = Signal(str)
    stop_loss_threshold_changed = Signal(float) # Now Platform-Specific
    lockout_duration_changed = Signal(int)      # Now Platform-Specific

    # Verification Status (depends on platform-specific block name & exe path, and global CT path)
    verification_status_changed = Signal(str, str) # status_text, color_state
    can_verify_block_changed = Signal(bool)
    can_remove_verification_changed = Signal(bool)
    block_name_input_read_only_changed = Signal(bool)

    # General Status & Actions
    status_message_changed = Signal(str, str) # message, level
    settings_saved = Signal(bool) # True if all saves succeeded
    settings_reset = Signal()


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

        # --- Internal state ---
        self._selected_platform: Optional[str] = None

        # Platform Specific State
        self._platform_ct_block_name: str = ""
        self._platform_exe_path: str = ""
        # Initialize platform specifics with defaults until loaded
        self._platform_threshold: float = self._config_repo.DEFAULT_PLATFORM_THRESHOLD
        self._platform_duration: int = self._config_repo.DEFAULT_PLATFORM_DURATION

        # Global State (Loaded once)
        self._global_ct_path: str = self._config_repo.get_cold_turkey_path()
        self._global_interval: float = self._config_repo.get_global_setting("monitor_interval_seconds", 2.0)
        self._global_data_dir: str = self._path_service.get_base_data_path()
        # --- Old global _threshold and _duration attributes removed ---

        self._logger.debug("Initializing SettingsViewModel...")
        self._platform_selection_service.register_platform_change_listener(
            self._handle_platform_selection_change # This will call _load_platform_specific_settings
        )

        initial_platform = self._platform_selection_service.get_current_platform()
        # Load initial platform-specific settings
        self._load_platform_specific_settings(initial_platform)

        self._logger.debug("SettingsViewModel initialized.")

    # --- Platform Specific Loading ---
    def _load_platform_specific_settings(self, platform: Optional[str]):
        """Loads settings specific to the given platform and updates internal state."""
        self._selected_platform = platform

        if platform:
            self._logger.info(f"Loading platform-specific settings for: {platform}")
            # Load Block Name and Exe Path
            settings = self._config_repo.get_platform_settings(platform) # Gets dict with defaults merged
            self._platform_ct_block_name = settings.get("cold_turkey_block_name", "")
            self._platform_exe_path = settings.get("platform_executable_path") or ""

            # Load Platform Threshold and Duration using specific getters
            threshold_res = self._config_repo.get_platform_stop_loss_threshold(platform)
            self._platform_threshold = threshold_res.value if threshold_res.is_success else self._config_repo.DEFAULT_PLATFORM_THRESHOLD
            if threshold_res.is_failure: self._logger.warning(f"Failed load threshold for {platform}: {threshold_res.error}")

            duration_res = self._config_repo.get_platform_lockout_duration(platform)
            self._platform_duration = duration_res.value if duration_res.is_success else self._config_repo.DEFAULT_PLATFORM_DURATION
            if duration_res.is_failure: self._logger.warning(f"Failed load duration for {platform}: {duration_res.error}")

        else:
            self._logger.info("No platform selected, clearing platform-specific settings state.")
            self._platform_ct_block_name = ""
            self._platform_exe_path = ""
            self._platform_threshold = self._config_repo.DEFAULT_PLATFORM_THRESHOLD
            self._platform_duration = self._config_repo.DEFAULT_PLATFORM_DURATION

        # Emit signals ONLY for platform-specific settings
        self.cold_turkey_block_name_changed.emit(self._platform_ct_block_name)
        self.platform_executable_path_changed.emit(self._platform_exe_path)
        self.stop_loss_threshold_changed.emit(self._platform_threshold)
        self.lockout_duration_changed.emit(self._platform_duration)

        # Update verification status which depends on these settings
        self._update_verification_status()

    def _emit_all_settings_signals(self):
        """Emits all signals reflecting the current combined global and platform state."""
        self._logger.debug("Emitting all settings signals...")
        # Global
        self.cold_turkey_path_changed.emit(self._global_ct_path)
        self.check_interval_changed.emit(self._global_interval)
        self.data_directory_changed.emit(self._global_data_dir)
        # Platform Specific
        self.cold_turkey_block_name_changed.emit(self._platform_ct_block_name)
        self.platform_executable_path_changed.emit(self._platform_exe_path)
        self.stop_loss_threshold_changed.emit(self._platform_threshold)
        self.lockout_duration_changed.emit(self._platform_duration)
        # Verification status updated separately by _update_verification_status
        self._update_verification_status()

    @Slot()
    def refresh_ui_signals(self):
        """Emits all signals reflecting the current state for initial UI sync."""
        self._logger.debug(f"SettingsViewModel Refreshing UI signals for {self._selected_platform or 'None'}")
        # Call the existing helper method that emits all signals
        self._emit_all_settings_signals()

    # --- Handlers ---
    @Slot(str)
    def _handle_platform_selection_change(self, platform: str):
        self._logger.debug(f"SettingsViewModel received platform change: {platform}")
        self._load_platform_specific_settings(platform)

    # --- Command Slots (Triggered by View) ---

    @Slot()
    def browse_cold_turkey_path(self):
        self._logger.debug("Browse for Cold Turkey path requested.")
        result = self._ui_service.select_file(
            "Select Cold Turkey Blocker Executable",
            "Executables (*.exe);;All Files (*)"
        )
        if result.is_success and result.value:
            new_path = result.value
            self._logger.info(f"Cold Turkey path selected: {new_path}")
            # Update internal state directly, Save button will handle persistence
            self.update_ct_path_state(new_path)
            # Also emit change to update UI immediately
            self.cold_turkey_path_changed.emit(self._global_ct_path)
        elif result.is_failure:
            self.status_message_changed.emit(f"Could not open file dialog: {result.error}", "ERROR")
        else:
             self.status_message_changed.emit("File selection cancelled.", "INFO")

    # Slot connected to ct_path_input.editingFinished
    @Slot(str)
    def update_ct_path_state(self, path: str):
        """Updates internal CT path state FROM VIEW editingFinished signal."""
        path = path.strip() or ""
        if path != self._global_ct_path:
            is_valid = path and path.lower().endswith(".exe") and os.path.exists(path)
            self._logger.debug(f"Internal CT path state updated to: {path} (Valid: {is_valid})")
            self._global_ct_path = path
            self._update_verification_status() # Verification depends on path validity
            if not is_valid and path: # Show warning if path entered but invalid
                 self.status_message_changed.emit(f"Warning: Entered CT path may be invalid.", "WARNING")
            # Note: We don't re-emit cold_turkey_path_changed here,
            # as the input field already reflects the change. It updates on load/save/reset.

    @Slot()
    def browse_platform_executable_path(self):
        """Handles browsing for the trading platform executable."""
        self._logger.debug("Browse for Platform executable path requested.")
        result = self._ui_service.select_file(
            "Select Trading Platform Executable",
            "Executables (*.exe);;All Files (*)"
        )
        if result.is_success and result.value:
            new_path = result.value
            self._logger.info(f"Platform executable path selected: {new_path}")
            # Update internal state directly, Save button handles persistence
            self.update_platform_exe_path_state(new_path)
             # Also emit change to update UI immediately
            self.platform_executable_path_changed.emit(self._platform_exe_path)
        elif result.is_failure:
            self.status_message_changed.emit(f"Could not open file dialog: {result.error}", "ERROR")
        else:
            self.status_message_changed.emit("File selection cancelled.", "INFO")

    # Slot connected to platform_exe_input.editingFinished
    @Slot(str)
    def update_platform_exe_path_state(self, path: str):
        """Updates internal platform exe path state FROM VIEW editingFinished signal."""
        path = path.strip() or ""
        if path != self._platform_exe_path:
            is_valid = path and path.lower().endswith(".exe") and os.path.exists(path)
            self._logger.debug(f"Internal platform exe path state updated to: {path} (Valid: {is_valid})")
            self._platform_exe_path = path
            self._update_verification_status() # Verification depends on path validity
            if not is_valid and path: # Show warning if path entered but invalid
                 self.status_message_changed.emit(f"Warning: Entered platform exe path may be invalid.", "WARNING")
            # Don't re-emit platform_executable_path_changed here

    # Slot connected to ct_block_name_input.editingFinished
    @Slot(str)
    def update_platform_block_name_state(self, block_name: str):
        """Updates internal block name state FROM VIEW editingFinished signal."""
        block_name = block_name.strip()
        if block_name != self._platform_ct_block_name:
            self._logger.debug(f"Internal block name state for '{self._selected_platform}' updated to: '{block_name}'")
            self._platform_ct_block_name = block_name
            # No immediate emit, save button handles persistence.
            # Update verification status as it depends on the block name being present.
            self._update_verification_status()

    # Slot connected to threshold_spinbox.editingFinished
    @Slot(float)
    def update_platform_threshold_state(self, value: float):
        """Updates internal platform threshold state FROM VIEW editingFinished signal."""
        value = -abs(value) # Ensure negative
        if value != self._platform_threshold:
            self._logger.debug(f"Internal threshold state for '{self._selected_platform}' updated to: {value}")
            self._platform_threshold = value
            # No immediate emit

    # Slot connected to interval_spinbox.editingFinished
    @Slot(float)
    def update_global_interval_state(self, value: float):
        """Updates internal global interval state FROM VIEW editingFinished signal."""
        value = max(0.5, value) # Ensure minimum
        if value != self._global_interval:
            self._logger.debug(f"Internal global interval state updated to: {value}")
            self._global_interval = value
            # No immediate emit

    # Slot connected to duration_spinbox.editingFinished
    @Slot(int)
    def update_platform_duration_state(self, value: int):
        """Updates internal platform duration state FROM VIEW editingFinished signal."""
        value = max(1, value) # Ensure minimum
        if value != self._platform_duration:
             self._logger.debug(f"Internal duration state for '{self._selected_platform}' updated to: {value}")
             self._platform_duration = value
             # No immediate emit

    @Slot()
    def verify_block_configuration(self):
        """Starts the block verification process."""
        if not self._selected_platform: self.status_message_changed.emit("Select a platform first.", "ERROR"); return
        if not self._platform_ct_block_name: self.status_message_changed.emit("Enter a Cold Turkey Block Name.", "ERROR"); return
        if not self._global_ct_path or not os.path.exists(self._global_ct_path): self.status_message_changed.emit("Cold Turkey path is not valid.", "ERROR"); return
        if not self._platform_exe_path or not os.path.exists(self._platform_exe_path): self.status_message_changed.emit("Trading Platform executable path is not valid.", "ERROR"); return

        self.status_message_changed.emit(f"Starting verification for '{self._platform_ct_block_name}'...", "INFO")
        start_result = self._verification_service.verify_platform_block(
            platform=self._selected_platform,
            block_name=self._platform_ct_block_name, # Use platform-specific internal state
            platform_executable_path=self._platform_exe_path, # Use platform-specific internal state
            on_started=self._handle_verification_started,
            on_completed=self._handle_verification_completed,
            on_error=self._handle_verification_error
        )
        if start_result.is_failure:
            self._logger.error(f"Failed to start verification request: {start_result.error}")
            self._handle_verification_error(f"{start_result.error}", self._selected_platform or "")

    @Slot()
    def remove_verification_for_current_platform(self):
        """Removes the verified status for the currently selected platform."""
        if not self._selected_platform: self.status_message_changed.emit("No platform selected.", "WARNING"); return

        platform_to_remove = self._selected_platform
        verified_block_res = self._config_repo.get_verified_block(platform_to_remove)
        verified_block_name = verified_block_res.value if verified_block_res.is_success else None

        if not verified_block_name: self.status_message_changed.emit(f"No verification found for '{platform_to_remove}'.", "INFO"); return

        confirm_res = self._ui_service.show_confirmation("Confirm Remove Verification", f"Remove verified status ('{verified_block_name}') for '{platform_to_remove}'?")
        if confirm_res.is_failure or not confirm_res.value: self.status_message_changed.emit("Remove verified status cancelled.", "INFO"); return

        self.status_message_changed.emit(f"Removing verified status for {platform_to_remove}...", "INFO")
        remove_res = self._config_repo.set_verified_block(platform_to_remove, None)

        if remove_res.is_success:
            self.status_message_changed.emit(f"Verified status for '{platform_to_remove}' removed.", "SUCCESS")
            self._logger.info(f"Successfully removed verified status for {platform_to_remove}")
            self._update_verification_status() # Refresh status display and input read-only state
        else:
            self.status_message_changed.emit(f"Failed to remove verified status: {remove_res.error}", "ERROR")

    @Slot()
    def save_settings(self):
        """Saves all current global and platform-specific settings."""
        self._logger.info("Saving settings...")
        self.status_message_changed.emit("Saving settings...", "INFO")
        any_failed = False
        failure_messages = []

        # --- Save Global Settings ---
        results_global = [
            self._config_repo.set_cold_turkey_path(self._global_ct_path), # Use repo method
            self._config_repo.set_global_setting("monitor_interval_seconds", self._global_interval),
            # Base data path usually not set via UI
        ]
        for res in results_global:
            if res.is_failure: any_failed = True; failure_messages.append(f"Global Setting: {res.error}")

        # --- Save Platform-Specific Settings ---
        if self._selected_platform:
            results_platform = [
                 self._config_repo.set_platform_executable_path(self._selected_platform, self._platform_exe_path),
                 self._config_repo.set_platform_stop_loss_threshold(self._selected_platform, self._platform_threshold),
                 self._config_repo.set_platform_lockout_duration(self._selected_platform, self._platform_duration),
                 # Save block name by updating the platform settings dictionary
                 # (Less direct, but avoids needing a dedicated repo method just for block name)
                 self._save_platform_block_name(self._selected_platform, self._platform_ct_block_name)
            ]
            for res in results_platform:
                if res.is_failure: any_failed = True; failure_messages.append(f"Platform '{self._selected_platform}': {res.error}")
        else:
            self._logger.debug("No platform selected, platform-specific settings not saved.")

        # Emit final status
        if any_failed:
            full_error_msg = "Failed to save some settings:\n- " + "\n- ".join(failure_messages)
            self.status_message_changed.emit(full_error_msg, "ERROR")
            self.settings_saved.emit(False)
        else:
            self.status_message_changed.emit("Settings saved successfully.", "SUCCESS")
            self.settings_saved.emit(True)
            # Re-emit signals to ensure UI reflects exactly what was saved (optional)
            # self._emit_all_settings_signals()

    # Helper to save just the block name within the platform settings dict
    def _save_platform_block_name(self, platform: str, block_name: str) -> Result[bool]:
         try:
              settings = self._config_repo.get_platform_settings(platform)
              settings["cold_turkey_block_name"] = block_name
              return self._config_repo.save_platform_settings(platform, settings)
         except Exception as e:
              self._logger.error(f"Error saving block name for {platform}: {e}", exc_info=True)
              return Result.fail(ConfigurationError(f"Failed to save block name: {e}"))

    @Slot()
    def reset_to_defaults(self):
        """Resets ViewModel state to application defaults WITHOUT saving immediately."""
        self._logger.warning("Resetting settings state display to defaults.")
        self.status_message_changed.emit("Resetting settings display to defaults...", "INFO")

        # --- Get Global Defaults ---
        try:
            default_config = self._config_repo.DEFAULT_CONFIG
            base_data_path = self._path_service.get_base_data_path()
        except AttributeError:
            self._logger.error("Could not access DEFAULT_CONFIG on repository for reset.")
            default_config = {} # Fallback
            base_data_path = os.getcwd() # Basic fallback

        # Reset internal global state attributes
        self._global_ct_path = default_config.get("cold_turkey_blocker", "")
        self._global_interval = default_config.get("monitor_interval_seconds", 2.0)
        self._global_data_dir = base_data_path

        # --- Reset internal platform-specific state attributes ---
        self._platform_ct_block_name = ""
        self._platform_exe_path = ""
        # Use class constants for platform defaults
        self._platform_threshold = self._config_repo.DEFAULT_PLATFORM_THRESHOLD
        self._platform_duration = self._config_repo.DEFAULT_PLATFORM_DURATION

        # Update UI by emitting all signals with default values
        self._emit_all_settings_signals()

        # Update verification status based on reset state (will likely show 'Not Verified')
        self._update_verification_status()

        self.settings_reset.emit()
        self.status_message_changed.emit("Settings display reset to defaults. Click 'Save Settings' to apply.", "INFO")


    # --- Verification Callback Handlers (Remain largely the same) ---
    @Slot()
    def _handle_verification_started(self):
        self._logger.debug("Verification started callback executed.")
        self.verification_status_changed.emit("Verifying...", "orange") # Use orange/busy state
        self.can_verify_block_changed.emit(False)
        self.can_remove_verification_changed.emit(False)
        self.block_name_input_read_only_changed.emit(True) # Read-only during verification

    @Slot(bool, str)
    def _handle_verification_completed(self, success: bool, platform: str):
        # Handles completion callback from the verification service
        if platform == self._selected_platform:
            self._logger.debug(f"Verification completed callback executed for {platform}. Success: {success}")
            if success:
                self.status_message_changed.emit("Block verification successful!", "SUCCESS")
                # No need to save block name here, save_settings handles it.
                # The repo's set_verified_block was already called by the service.
            # Update status display based on the latest config state
            self._update_verification_status() # This handles labels, buttons, read-only state
        else:
            self._logger.debug(f"Ignoring verification completion for different platform: {platform}")

    @Slot(str, str)
    def _handle_verification_error(self, error_msg: str, platform: str):
        if platform == self._selected_platform:
            self._logger.error(f"Verification error callback executed for {platform}: {error_msg}")
            self.status_message_changed.emit(f"Verification Error: {error_msg}", "ERROR")
            # Update status display based on the latest config state (should show error)
            self._update_verification_status() # This handles labels, buttons, read-only state
        else:
             self._logger.debug(f"Ignoring verification error for different platform: {platform}")

    # --- Private Helper: Update Verification Status Display ---
    def _update_verification_status(self):
        """Checks verification status and updates relevant UI signals."""
        status = "N/A"
        color = "gray"
        can_verify = False
        can_remove = False
        is_read_only = False
        block_name_to_display = self._platform_ct_block_name # Default to current input

        if self._selected_platform:
            verified_block_res = self._config_repo.get_verified_block(self._selected_platform)
            if verified_block_res.is_failure:
                status = "Error Reading Status"; color = "red"
            else:
                verified_block_name = verified_block_res.value
                if verified_block_name:
                    status = f"Verified ({verified_block_name})"; color = "green"
                    block_name_to_display = verified_block_name # Display verified name
                    is_read_only = True
                    can_remove = True
                else: # Not verified
                    status = "Not Verified"; color = "red"
                    is_read_only = False
                    can_remove = False
                    # Check prerequisites for enabling Verify button
                    ct_path_ok = bool(self._global_ct_path and os.path.exists(self._global_ct_path) and os.path.isfile(self._global_ct_path))
                    block_name_ok = bool(self._platform_ct_block_name)
                    exe_path_ok = bool(self._platform_exe_path and os.path.exists(self._platform_exe_path) and os.path.isfile(self._platform_exe_path))
                    if ct_path_ok and block_name_ok and exe_path_ok:
                        can_verify = True
                    else: # Refine status message if prereqs not met
                        if not ct_path_ok: status = "Set Valid CT Path"
                        elif not exe_path_ok: status = "Set Valid Platform Exe Path"
                        elif not block_name_ok: status = "Enter Block Name"
                        else: status = "Not Verified" # Fallback
                        color = "orange" # Indicate incomplete setup

        else: # No platform selected
            status = "Select Platform"; color = "gray"
            is_read_only = True
            block_name_to_display = ""

        is_verifying = self._verification_service.is_verification_in_progress()

        # Emit status and enablement signals
        self.verification_status_changed.emit(status, color)
        self.can_verify_block_changed.emit(can_verify and not is_verifying)
        self.can_remove_verification_changed.emit(can_remove and not is_verifying)
        self.block_name_input_read_only_changed.emit(is_read_only or is_verifying) # Readonly if verified or verifying

        # Ensure block name input displays the correct value (verified or current input)
        # Check if the UI needs an update based on verification status change
        if self.cold_turkey_block_name_changed is not None and block_name_to_display != self._platform_ct_block_name:
             # If verified name is different from current input, force UI update
             self._platform_ct_block_name = block_name_to_display # Update internal state first
             self.cold_turkey_block_name_changed.emit(block_name_to_display)