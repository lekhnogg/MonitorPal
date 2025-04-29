# src/presentation/view_models/settings_view_model.py

import os
# import re # No longer needed here
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
from src.domain.services.i_ui_service import IUIService
from src.domain.common.result import Result
from src.domain.common.errors import ConfigurationError


class SettingsViewModel(QObject):
    """
    ViewModel for the Settings tab.

    Manages configuration settings like paths, monitoring parameters,
    Cold Turkey integration, and platform executable paths for verification.
    """

    # --- Signals for View updates ---
    cold_turkey_path_changed = Signal(str)

    cold_turkey_block_name_changed = Signal(str)

    platform_executable_path_changed = Signal(str)

    verification_status_changed = Signal(str, str)
    can_verify_block_changed = Signal(bool)
    can_remove_verification_changed = Signal(bool)
    block_name_input_read_only_changed = Signal(bool)
    stop_loss_threshold_changed = Signal(float)
    check_interval_changed = Signal(float)
    lockout_duration_changed = Signal(int)

    data_directory_changed = Signal(str)

    status_message_changed = Signal(str, str)
    settings_saved = Signal(bool)
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
        self._ct_path: str = ""
        self._ct_block_name: str = ""
        # --- ADDED STATE ---
        self._platform_exe_path: str = "" # Store path as string, empty if not set
        # --- END ADDED ---
        self._threshold: float = -100.0
        self._interval: float = 2.0
        self._duration: int = 15
        self._data_dir: str = ""

        self._logger.debug("Initializing SettingsViewModel...")
        self._platform_selection_service.register_platform_change_listener(
            self._handle_platform_selection_change
        )

        initial_platform = self._platform_selection_service.get_current_platform()
        self._load_settings_for_platform(initial_platform)
        self._logger.debug("SettingsViewModel initialized.")

    # --- Command Slots (Called by the View) ---

    @Slot()
    def browse_cold_turkey_path(self):
        # (Unchanged)
        self._logger.debug("Browse for Cold Turkey path requested.")
        result = self._ui_service.select_file(
            "Select Cold Turkey Blocker Executable",
            "Executables (*.exe);;All Files (*)"
        )
        if result.is_success and result.value:
            new_path = result.value
            self._logger.info(f"Cold Turkey path selected: {new_path}")
            self._set_cold_turkey_path(new_path)
            self._update_verification_status()
        elif result.is_failure:
            self.status_message_changed.emit(f"Could not open file dialog: {result.error}", "ERROR")
        else:
             self.status_message_changed.emit("File selection cancelled.", "INFO")

    @Slot(str)
    def set_cold_turkey_path_text(self, path: str):
        # (Unchanged)
        path = path.strip() # Ensure leading/trailing whitespace removed
        if path and path.lower().endswith(".exe") and os.path.exists(path):
             if path != self._ct_path:
                  self._logger.debug(f"Setting Cold Turkey path from text input: {path}")
                  self._set_cold_turkey_path(path)
                  self._update_verification_status()
        elif path and path != self._ct_path:
             # Path entered but invalid or doesn't exist
             self._logger.warning(f"Invalid CT path input ignored: {path}")
             self.status_message_changed.emit(f"Invalid path: {path}", "WARNING")
             # Optionally revert the input field visually
             # self.cold_turkey_path_changed.emit(self._ct_path) # Revert UI
        elif not path and self._ct_path:
             # Path cleared
             self._logger.debug("Clearing Cold Turkey path.")
             self._set_cold_turkey_path("")
             self._update_verification_status()

    @Slot(str)
    def set_cold_turkey_block_name(self, block_name: str):
        # (Unchanged)
        block_name = block_name.strip()
        if block_name != self._ct_block_name:
            self._logger.debug(f"Setting configured Cold Turkey block name for '{self._selected_platform}' to: '{block_name}'")
            self._ct_block_name = block_name
            self.cold_turkey_block_name_changed.emit(self._ct_block_name)
            self._update_verification_status()

    # --- NEW SLOTS for Platform Exe Path ---
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
            self._set_platform_executable_path(new_path)
            self._update_verification_status() # Path affects verification prerequisites
        elif result.is_failure:
            self.status_message_changed.emit(f"Could not open file dialog: {result.error}", "ERROR")
        else:
            self.status_message_changed.emit("File selection cancelled.", "INFO")

    @Slot(str)
    def set_platform_executable_path_text(self, path: str):
        """Sets the platform executable path from text input, with validation."""
        path = path.strip()
        # Validate: Check if it ends with .exe and exists (basic check)
        if path and path.lower().endswith(".exe") and os.path.exists(path):
            if path != self._platform_exe_path:
                self._logger.debug(f"Setting Platform executable path from text input: {path}")
                self._set_platform_executable_path(path)
                self._update_verification_status()
        elif path and path != self._platform_exe_path:
            # Path entered but invalid or doesn't exist
            self._logger.warning(f"Invalid Platform executable path input ignored: {path}")
            self.status_message_changed.emit(f"Invalid path: {path}", "WARNING")
            # Optionally revert the input field visually
            # self.platform_executable_path_changed.emit(self._platform_exe_path) # Revert UI
        elif not path and self._platform_exe_path:
             # Path cleared
             self._logger.debug("Clearing Platform executable path.")
             self._set_platform_executable_path("") # Treat empty as "not set"
             self._update_verification_status()
    # --- END NEW SLOTS ---


    @Slot()
    def verify_block_configuration(self):
        # --- MODIFIED: Added check for platform exe path ---
        if not self._selected_platform:
            self.status_message_changed.emit("Select a platform first.", "ERROR"); return
        if not self._ct_block_name:
            self.status_message_changed.emit("Enter a Cold Turkey Block Name.", "ERROR"); return
        if not self._ct_path or not os.path.exists(self._ct_path):
            self.status_message_changed.emit("Cold Turkey path is not valid.", "ERROR"); return
        if not self._platform_exe_path or not os.path.exists(self._platform_exe_path): # <-- ADDED CHECK
             self.status_message_changed.emit("Trading Platform executable path is not valid.", "ERROR"); return
        # --- END MODIFIED ---

        # Check if platform is running (handled within verification service now)

        self.status_message_changed.emit(f"Starting verification for '{self._ct_block_name}'...", "INFO")

        # The VerificationService now needs the platform exe path
        start_result = self._verification_service.verify_platform_block(
            platform=self._selected_platform,
            block_name=self._ct_block_name,
            # --- ADDED PARAMETER ---
            platform_executable_path=self._platform_exe_path,
            # --- END ADDED ---
            on_started=self._handle_verification_started,
            on_completed=self._handle_verification_completed,
            on_error=self._handle_verification_error
        )
        if start_result.is_failure:
            self._logger.error(f"Failed to start verification request: {start_result.error}")
            self._handle_verification_error(f"{start_result.error}", self._selected_platform or "")

    @Slot()
    def remove_verification_for_current_platform(self):
        # (Unchanged)
        if not self._selected_platform:
            self.status_message_changed.emit("No platform selected to remove verification from.", "WARNING"); return

        platform_to_remove = self._selected_platform
        verified_block_res = self._config_repo.get_verified_block(platform_to_remove)
        verified_block_name = verified_block_res.value if verified_block_res.is_success else None

        if not verified_block_name:
            self.status_message_changed.emit(f"No verification found for '{platform_to_remove}' to remove.", "INFO"); return

        confirm_res = self._ui_service.show_confirmation("Confirm Remove Verification", f"Remove verified status ('{verified_block_name}') for '{platform_to_remove}'?")
        if confirm_res.is_failure or not confirm_res.value:
            self.status_message_changed.emit("Remove verified status cancelled.", "INFO"); return

        self.status_message_changed.emit(f"Removing verified status for {platform_to_remove}...", "INFO")
        remove_res = self._config_repo.set_verified_block(platform_to_remove, None)

        if remove_res.is_success:
            self.status_message_changed.emit(f"Verified status for '{platform_to_remove}' removed.", "SUCCESS")
            self._logger.info(f"Successfully removed verified status for {platform_to_remove}")
            # Refresh the verification status, which will now also make input editable
            self._update_verification_status()  # <--- Updates labels/buttons AND read-only state
        else:
            self.status_message_changed.emit(f"Failed to remove verified status: {remove_res.error}", "ERROR")


    @Slot(float)
    def set_stop_loss_threshold(self, value: float):
        # (Unchanged)
        value = -abs(value)
        if value != self._threshold:
            self._threshold = value; self.stop_loss_threshold_changed.emit(self._threshold)

    @Slot(float)
    def set_check_interval(self, value: float):
        # (Unchanged)
        value = max(0.5, value)
        if value != self._interval:
            self._interval = value; self.check_interval_changed.emit(self._interval)

    @Slot(int)
    def set_lockout_duration(self, value: int):
        # (Unchanged)
        value = max(1, value)
        if value != self._duration:
             self._duration = value; self.lockout_duration_changed.emit(self._duration)

    @Slot()
    def save_settings(self):
        # --- MODIFIED: Save platform exe path ---
        self._logger.info("Saving settings...")
        self.status_message_changed.emit("Saving settings...", "INFO")

        any_failed = False
        failure_messages = []

        # Save Global Settings
        results_global = [
            self._config_repo.set_global_setting("cold_turkey_blocker", self._ct_path),
            self._config_repo.set_global_setting("stop_loss_threshold", self._threshold),
            self._config_repo.set_global_setting("lockout_duration", self._duration),
            self._config_repo.set_global_setting("monitor_interval_seconds", self._interval),
        ]
        for res in results_global:
            if res.is_failure: any_failed = True; failure_messages.append(f"Global: {res.error}")

            # Save Platform-Specific Settings (Block Name AND Exe Path)
            if self._selected_platform:
                try:
                    # 1. Get current settings
                    platform_settings = self._config_repo.get_platform_settings(self._selected_platform)

                    # 2. Update the dictionary with current VM state
                    platform_settings["cold_turkey_block_name"] = self._ct_block_name
                    platform_settings[
                        "platform_executable_path"] = self._platform_exe_path or None  # Ensure None if empty

                    # 3. Save the entire updated dictionary
                    res_plat = self._config_repo.save_platform_settings(self._selected_platform, platform_settings)
                    if res_plat.is_failure:
                        any_failed = True
                        failure_messages.append(f"Platform '{self._selected_platform}': {res_plat.error}")

                except Exception as e:
                    # Catch potential errors during get/update/save for platform settings
                    self._logger.error(f"Error saving platform settings for '{self._selected_platform}': {e}",
                                       exc_info=True)
                    any_failed = True
                    failure_messages.append(f"Platform '{self._selected_platform}': Unexpected error {e}")
        else:
             self._logger.warning("No platform selected, platform-specific settings not saved.")

        # Emit final status
        if any_failed:
            full_error_msg = "Failed to save settings:\n- " + "\n- ".join(failure_messages)
            self.status_message_changed.emit(full_error_msg, "ERROR")
            self.settings_saved.emit(False)
        else:
            self.status_message_changed.emit("Settings saved successfully.", "SUCCESS")
            self.settings_saved.emit(True)
            self._load_settings_for_platform(self._selected_platform) # Reload to ensure consistency
        # --- END MODIFIED ---


    @Slot()
    def reset_to_defaults(self):
        # --- MODIFIED: Clear platform exe path ---
        self._logger.warning("Resetting settings to defaults (ViewModel state only).")
        self.status_message_changed.emit("Resetting settings to defaults...", "INFO")
        default_config = self._config_repo.DEFAULT_CONFIG
        self._set_cold_turkey_path(default_config.get("cold_turkey_blocker", ""))
        self._ct_block_name = ""
        self.cold_turkey_block_name_changed.emit(self._ct_block_name)
        # --- ADDED ---
        self._set_platform_executable_path("") # Clear platform path
        # --- END ADDED ---
        self.set_stop_loss_threshold(default_config.get("stop_loss_threshold", -100.0))
        self.set_check_interval(default_config.get("monitor_interval_seconds", 2.0))
        self.set_lockout_duration(default_config.get("lockout_duration", 15))
        self._data_dir = self._path_service.get_base_data_path() # Re-fetch default data dir
        self.data_directory_changed.emit(self._data_dir)
        self._update_verification_status() # Update status for the cleared state
        self.settings_reset.emit()
        self.status_message_changed.emit("Settings reset to defaults. Click 'Save Settings' to apply.", "INFO")
        # --- END MODIFIED ---

    # --- Internal Slots / Callback Handlers ---

    @Slot(str)
    def _handle_platform_selection_change(self, platform: str):
        # (Unchanged)
        self._logger.debug(f"SettingsViewModel received platform change: {platform}")
        self._load_settings_for_platform(platform)

    @Slot()
    def _handle_verification_started(self):
        # (Unchanged)
        self._logger.debug("Verification started callback executed.")
        self.verification_status_changed.emit("Verifying...", "orange")
        self.can_verify_block_changed.emit(False)
        self.can_remove_verification_changed.emit(False)

    @Slot(bool, str)
    def _handle_verification_completed(self, success: bool, platform: str):
        # Handles completion callback from the verification service
        if platform == self._selected_platform:
            self._logger.debug(f"Verification completed callback executed for {platform}. Overall Success: {success}")

            if success:
                self.status_message_changed.emit("Block verification successful!", "SUCCESS")
                # --- ADDED: Save the configured block name now that it's verified ---
                try:
                    self.status_message_changed.emit("Saving verified block name to configuration...", "INFO")
                    platform_settings = self._config_repo.get_platform_settings(self._selected_platform)
                    platform_settings[
                        "cold_turkey_block_name"] = self._ct_block_name  # Save the name that was just verified
                    save_res = self._config_repo.save_platform_settings(self._selected_platform, platform_settings)
                    if save_res.is_failure:
                        self._logger.error(
                            f"Failed to save configured block name '{self._ct_block_name}' after successful verification: {save_res.error}")
                        self.status_message_changed.emit(
                            f"Verification succeeded, but failed to save block name setting: {save_res.error}", "ERROR")
                        # Also clear verified status if saving config name failed, to maintain consistency
                        self._config_repo.set_verified_block(self._selected_platform, None)
                    else:
                        self._logger.info(
                            f"Successfully saved configured block name '{self._ct_block_name}' for {self._selected_platform}")
                except Exception as e:
                    self._logger.error(
                        f"Unexpected error saving configured block name for '{self._selected_platform}': {e}",
                        exc_info=True)
                    self.status_message_changed.emit(f"Error saving block name setting: {e}", "ERROR")
                    self._config_repo.set_verified_block(self._selected_platform, None)  # Clear verification on error
                # --- END ADDED ---

            # Let _update_verification_status handle the final label state and button enablement based on the LATEST config state
            self._update_verification_status()
            # Error message for verification failure itself is handled by _handle_verification_error or status change within _update_verification_status

        else:
            self._logger.debug(f"Ignoring verification completion callback for different platform: {platform}")

    @Slot(str, str)
    def _handle_verification_error(self, error_msg: str, platform: str):
        # (Unchanged)
        if platform == self._selected_platform:
            self._logger.error(f"Verification error callback executed for {platform}: {error_msg}")
            self.status_message_changed.emit(f"Verification Error: {error_msg}", "ERROR")
            self.verification_status_changed.emit("Error", "red")
            self.can_verify_block_changed.emit(True) # Allow retry
            self.can_remove_verification_changed.emit(False)
        else:
             self._logger.debug(f"Ignoring verification error callback for different platform: {platform}")

    # --- Private Helper Methods ---

    def _load_settings_for_platform(self, platform: Optional[str]):
        # --- MODIFIED: Load platform exe path ---
        self._selected_platform = platform
        self._logger.info(f"Loading settings for platform: {platform or 'None'}")

        # Load Global Settings
        self._ct_path = self._config_repo.get_cold_turkey_path()
        self._threshold = self._config_repo.get_stop_loss_threshold()
        self._interval = self._config_repo.get_global_setting("monitor_interval_seconds", 2.0)
        self._duration = self._config_repo.get_lockout_duration()
        self._data_dir = self._path_service.get_base_data_path()

        # Load Platform-Specific Settings
        if platform:
            platform_settings = self._config_repo.get_platform_settings(platform)
            self._ct_block_name = platform_settings.get("cold_turkey_block_name", "")
            # --- ADDED ---
            # Fetch path using the dedicated config repo method
            exe_path_res = self._config_repo.get_platform_executable_path(platform)
            if exe_path_res.is_success:
                 self._platform_exe_path = exe_path_res.value or "" # Use empty string if None
            else:
                 self._logger.error(f"Failed to load platform exe path for {platform}: {exe_path_res.error}")
                 self._platform_exe_path = "" # Default to empty on error
            # --- END ADDED ---
        else:
             self._ct_block_name = ""
             self._platform_exe_path = "" # Clear if no platform

        # Emit signals for loaded values
        self.cold_turkey_path_changed.emit(self._ct_path)
        self.cold_turkey_block_name_changed.emit(self._ct_block_name)
        # --- ADDED ---
        self.platform_executable_path_changed.emit(self._platform_exe_path)
        # --- END ADDED ---
        self.stop_loss_threshold_changed.emit(self._threshold)
        self.check_interval_changed.emit(self._interval)
        self.lockout_duration_changed.emit(self._duration)
        self.data_directory_changed.emit(self._data_dir)

        self._update_verification_status() # Update derived state
        self._logger.debug(f"Settings loaded and signals emitted for {platform or 'None'}.")
        # --- END MODIFIED ---

    def _set_cold_turkey_path(self, path: str):
        # (Unchanged)
        path = path or ""
        if path != self._ct_path:
            self._ct_path = path; self.cold_turkey_path_changed.emit(self._ct_path)

    # --- NEW HELPER ---
    def _set_platform_executable_path(self, path: str):
        """Internal helper to set platform exe path and emit signal."""
        path = path or "" # Ensure it's never None internally, just empty string
        if path != self._platform_exe_path:
            self._platform_exe_path = path
            self.platform_executable_path_changed.emit(self._platform_exe_path)
    # --- END NEW ---


    def _update_verification_status(self):
        # Checks verification status for the selected platform and emits signals
        status = "N/A"
        color = "gray"
        can_verify = False # Can the Verify button be enabled?
        can_remove = False # Can the Remove button be enabled?
        is_read_only = False # Should the input be read-only?
        block_name_to_display = self._ct_block_name # Start with current input text

        if self._selected_platform:
            # --- Check Verification Status FIRST ---
            verified_block_res = self._config_repo.get_verified_block(self._selected_platform)
            if verified_block_res.is_failure:
                status = "Error Reading Status"; color = "red"
                can_verify = False
                can_remove = False
                is_read_only = False # Allow editing if status read fails? Maybe.
            else:
                verified_block_name = verified_block_res.value # Name (str) or None

                if verified_block_name:
                    # --- A block IS verified ---
                    status = "Verified"; color = "green"
                    block_name_to_display = verified_block_name # Display the verified name
                    is_read_only = True # Input should be read-only
                    can_verify = False # Cannot verify when already verified
                    can_remove = True # Can remove the existing verification
                else:
                    # --- No block is verified ---
                    status = "Not Verified"; color = "red"
                    block_name_to_display = self._ct_block_name # Keep displaying user input
                    is_read_only = False # Input should be editable
                    can_remove = False # Nothing to remove

                    # Check prerequisites ONLY if not verified, to enable Verify button
                    ct_path_ok = bool(self._ct_path and os.path.exists(self._ct_path))
                    block_name_in_input_ok = bool(self._ct_block_name) # Check if input field has text
                    platform_exe_ok = bool(self._platform_exe_path and os.path.exists(self._platform_exe_path))
                    can_verify_prereqs_met = ct_path_ok and block_name_in_input_ok and platform_exe_ok

                    if can_verify_prereqs_met:
                        can_verify = True # Enable Verify button if all prereqs met
                    else:
                        can_verify = False # Keep Verify disabled if prereqs not met
                        # Optionally refine status message based on missing prereq
                        if not ct_path_ok: status = "Set CT Path"
                        elif not platform_exe_ok: status = "Set Platform Exe Path"
                        elif not block_name_in_input_ok: status = "Enter Block Name"
                        else: status = "Not Verified" # Fallback if prereqs check logic fails

        else: # No platform selected
            status = "Select Platform"
            color = "gray"
            can_verify = False
            can_remove = False
            is_read_only = True # Read-only if no platform selected
            block_name_to_display = "" # Clear input display

        # Check if verification task is currently running
        is_verifying = self._verification_service.is_verification_in_progress()

        # Emit status and enablement signals
        self.verification_status_changed.emit(status, color)
        # Only enable Verify if prerequisites met, not already verified, and not busy
        self.can_verify_block_changed.emit(can_verify and not is_verifying)
        # Only enable Remove if verified and not busy
        self.can_remove_verification_changed.emit(can_remove and not is_verifying)
        # Emit read-only state for input field
        self.block_name_input_read_only_changed.emit(is_read_only)

        # --- ADDED: Ensure input field displays the correct name ---
        # If the name to display (either verified or current input) is different
        # from the ViewModel's internal state reflecting the input, update the signal.
        # This handles the case where we load a verified name.
        if block_name_to_display != self._ct_block_name:
             self._ct_block_name = block_name_to_display # Update internal state
             self.cold_turkey_block_name_changed.emit(self._ct_block_name) # Update UI input field