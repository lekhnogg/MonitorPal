# src/presentation/view_models/dashboard_view_model.py

import time
from typing import List, Optional, Dict, Any, Tuple

# --- Qt Imports ---
from PySide6.QtCore import QObject, Signal, Slot, QTimer

from src.domain.common.errors import PlatformNotRunningError, UnknownPlatformError
from src.domain.services.i_cold_turkey_service import IColdTurkeyService
# --- Application Imports ---
from PySide6.QtWidgets import QApplication

from src.domain.services.i_history_service import IHistoryService
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_monitoring_service import IMonitoringService
from src.domain.services.i_lockout_service import ILockoutService # If manual flatten needed
from src.domain.services.i_flash_service import IFlashService
from src.domain.services.i_platform_selection_service import IPlatformSelectionService
from src.domain.services.i_config_repository_service import IConfigRepository
from src.domain.services.i_region_service import IRegionService
from src.domain.services.i_profile_service import IProfileService
from src.domain.models.monitoring_result import MonitoringResult
from src.domain.common.result import Result # For type hinting
from src.infrastructure.ui.qt_flash_service import QtFlashService


class DashboardViewModel(QObject):
    """
    ViewModel for the main Dashboard tab.
    Manages the state and actions related to monitoring overview,
    quick actions, and activity logging.
    """

    # --- Signals for View updates ---

    # For the Consolidated "Live Status Card"
    current_pnl_text_changed = Signal(str)                # For the large P&L text value itself (e.g., "+$123.45")
                                                          # The View will use this text to set its QSS 'state' property too.
    status_indicator_icon_info_changed = Signal(str, str) # Emits: icon_key (str like "active", "error"), tooltip_text (str)
    monitoring_target_text_changed = Signal(str)          # Emits: text_to_display (str like "Quantower - Region: Defined")

    # Prerequisites Panel
    prerequisite_status_updated = Signal(str, str, str, bool) # key, status_text, status_state ("ok", "error"), show_action_button
    prerequisites_completion_changed = Signal(str)            # e.g., "4/5 Complete"

    # Quick Actions Button Enablement
    can_start_monitoring_changed = Signal(bool)
    can_stop_monitoring_changed = Signal(bool)
    can_test_flash_changed = Signal(bool)

    # Alerts and Logs
    recent_alerts_updated = Signal(list)      # List of strings for the alerts box
    activity_log_appended = Signal(str, str)  # message, level (e.g., "INFO", "ERROR")

    # General Status/Error Message for Main Window Status Bar
    status_message_changed = Signal(str, str) # message, level ("INFO", "ERROR", etc.)

    monitoring_session_activity_changed = Signal(bool, object)
    # --- Signals potentially for Main Window Status Bar (Consider if MainViewModel handles these) ---
    # If these were used by DashboardView directly for other purposes, keep them.
    # If they were only for data that MainViewModel now shows in the main status bar, they can be removed from here.
    # selected_platform_name_changed = Signal(str)
    # pnl_format_display_changed = Signal(str)

    def __init__(self,
                 logger: ILoggerService,
                 monitoring_service: IMonitoringService,
                 lockout_service: ILockoutService,
                 flash_service: IFlashService,
                 platform_selection_service: IPlatformSelectionService,
                 config_repo: IConfigRepository,
                 region_service: IRegionService,
                 profile_service: IProfileService,
                 cold_turkey_service: IColdTurkeyService,
                 history_service: IHistoryService,
                 parent: Optional[QObject] = None):
        super().__init__(parent)

        # --- Store Services ---
        self._logger = logger
        self._monitoring_service = monitoring_service
        self._lockout_service = lockout_service
        self._flash_service = flash_service
        self._platform_selection_service = platform_selection_service
        self._config_repo = config_repo
        self._region_service = region_service
        self._profile_service = profile_service
        self._cold_turkey_service = cold_turkey_service
        self._history_service = history_service

        # --- Internal State Attributes ---
        self._selected_platform: Optional[str] = None
        self._current_session_id: Optional[str] = None
        self._is_monitoring_globally_active: bool = False
        self._monitoring_platform: Optional[str] = None  # Platform currently being monitored
        self._current_pnl_text: str = "N/A"  # For self.pnl_display_label

        # --- NEW State for Consolidated Live Status Card ---
        self._status_indicator_icon_key: str = "inactive"  # e.g., "active", "inactive", "error", "busy"
        self._status_indicator_tooltip: str = "Monitoring Inactive"
        self._monitoring_target_text: str = "Platform: N/A - Region: N/A"


        # Other existing states
        self._can_start: bool = False
        self._can_stop: bool = False
        self._can_test_flash: bool = False
        self._recent_alerts: List[str] = []
        self._monitor_region_defined: bool = False
        self._flatten_regions_defined: bool = False
        self._last_monitor_result: Optional[MonitoringResult] = None

        # --- NEW State for managing flash operation ---
        self._is_flash_test_in_progress: bool = False
        self._current_flash_task_id: Optional[str] = None
        # --- End NEW State ---

        self._prerequisite_keys_list = [
            "ct_path", "ct_block_setup", "monitor_region",
            "flatten_regions", "pnl_detector"
        ]
        self._prerequisite_states: Dict[str, str] = {key: "pending" for key in self._prerequisite_keys_list}
        self._total_prerequisites_count = len(self._prerequisite_keys_list)

        # --- Initialization ---
        self._logger.debug("Initializing DashboardViewModel...")
        self._platform_selection_service.register_platform_change_listener(
            self._handle_platform_selection_change
        )

        # --- Connect to signals from QtFlashService ---
        # This is crucial for knowing when the flash animation completes or fails.
        # We check if the provided flash_service is an instance of QtFlashService
        # or at least has the expected signals, to make the connection.
        if isinstance(self._flash_service, QtFlashService):  # Check if it's the concrete type that has signals
            self._logger.debug("Connecting to QtFlashService signals for flash completion/failure.")
            self._flash_service.flash_animation_completed.connect(self._handle_flash_animation_completed)
            self._flash_service.flash_animation_failed.connect(self._handle_flash_animation_failed)
        else:
            self._logger.warning(
                "Flash service is not an instance of QtFlashService or does not have expected signals. "
                "Flash button state during animation might not work correctly."
            )
        # --- End Connection to QtFlashService signals ---

        # Load initial data for the currently selected platform
        # This will call _update_state_for_platform, which in turn will call
        # the new _update_dashboard_display_state helper later.
        initial_platform = self._platform_selection_service.get_current_platform()
        if initial_platform:  # Ensure initial call if a platform is already selected
            self._update_state_for_platform(initial_platform)
        else:  # If no platform initially, ensure display state is default
            self._update_state_for_platform(None)

        # Emit initial log message via QTimer
        def emit_initial_log():
            try:
                app_instance = QApplication.instance()
                app_version = app_instance.applicationVersion() if app_instance else "N/A"
                initial_msg = f"MonitorPal v{app_version} initialized. Ready."
                self._logger.debug(f"Emitting initial log via timer: '{initial_msg}'")
                self.activity_log_appended.emit(initial_msg, "INFO")
            except Exception as e:
                self._logger.error(f"Error emitting initial log message: {e}", exc_info=True)

        QTimer.singleShot(0, emit_initial_log)

        self._logger.debug("DashboardViewModel initialized.")


    def _update_dashboard_display_state(self):
        """
        Updates all internal state variables for the consolidated live status card
        and button enablement, then emits all corresponding signals.
        This should be the primary method called when monitoring state or platform changes.
        """
        self._logger.debug(
            f"DashboardVM: Updating all dashboard display states for platform: '{self._selected_platform or 'None'}' "
            f"(Globally active: {self._is_monitoring_globally_active}, for platform: '{self._monitoring_platform or 'None'}'). "
            f"Current PNL text before this method: '{self._current_pnl_text}'."
        )

        # --- 1. DETERMINE AND SET P&L TEXT ---
        # This section now more actively determines what _current_pnl_text should be
        # based on the overall state, before emitting it.

        if self._is_monitoring_globally_active:
            if self._monitoring_platform == self._selected_platform:
                # Monitoring is active for the currently selected platform.
                # _current_pnl_text should have been updated by _handle_monitoring_result (for live P&L)
                # or by start_monitoring ("Waiting for data...").
                # No change to _current_pnl_text needed here; it reflects the live state.
                self._logger.debug(
                    f"_update_dashboard_display_state: Monitoring active for selected platform. Current PNL: '{self._current_pnl_text}' (should be live).")
            else:
                # Monitoring is active, but for a DIFFERENT platform than selected in the UI.
                # The P&L display for the *selected* (but not monitored) platform should indicate this.
                self._current_pnl_text = "N/A (Other active)"  # Or simply "N/A"
                self._logger.debug(
                    f"_update_dashboard_display_state: Monitoring active for other platform. PNL for '{self._selected_platform}' set to '{self._current_pnl_text}'.")
        else:
            # Monitoring is NOT globally active.
            # _current_pnl_text could be "N/A" (after stop), "LOCKOUT", "Error", or
            # "Waiting for data..." if just started and immediately failed before first result.
            # If it's "Waiting for data..." but we're not active, it likely means a start attempt failed.
            # This part relies on stop_monitoring, _handle_threshold_exceeded, _handle_monitoring_error
            # having already set _current_pnl_text appropriately.
            # If no specific error/lockout state, default to "N/A".
            if self._current_pnl_text not in ["Error",
                                              "LOCKOUT"] and "LOCKOUT (" not in self._current_pnl_text:  # Avoid overwriting critical states
                if not self._selected_platform:
                    self._current_pnl_text = "N/A"  # No platform selected
                elif self._current_pnl_text == "Waiting for data..." or self._current_pnl_text == "No P&L data":
                    # If it was waiting or couldn't read, and now we are not active, it should be N/A.
                    self._current_pnl_text = "N/A"
                # If it's already "N/A", "Error", "LOCKOUT", leave it.
                # If _current_pnl_text is some PNL value from a previous session, reset to "N/A".
                elif self._current_pnl_text.startswith("$"):  # A previous P&L value
                    self._current_pnl_text = "N/A"

            self._logger.debug(
                f"_update_dashboard_display_state: Monitoring not active. PNL: '{self._current_pnl_text}'.")

        # Now, emit the determined P&L text.
        self.current_pnl_text_changed.emit(self._current_pnl_text)

        # --- 2. DETERMINE STATUS INDICATOR ICON KEY AND TOOLTIP ---
        current_icon_key = "inactive"
        current_tooltip = "Monitoring Inactive. Select platform and ensure prerequisites are met."

        if self._is_monitoring_globally_active:
            if self._monitoring_platform == self._selected_platform:
                current_icon_key = "active"
                current_tooltip = f"Monitoring Active for {self._selected_platform}"
            elif self._monitoring_platform:
                current_icon_key = "busy"
                current_tooltip = f"Monitoring active for {self._monitoring_platform} (not the currently viewed platform)"
            else:
                current_icon_key = "busy"
                current_tooltip = "Monitoring status is currently indeterminate."
        elif "ERROR" in self._current_pnl_text.upper():
            current_icon_key = "error"
            current_tooltip = f"Monitoring Error for {self._selected_platform or 'last session'}. Check logs."
        elif "LOCKOUT" in self._current_pnl_text.upper() or "LOCKOUT (" in self._current_pnl_text:
            current_icon_key = "error"
            current_tooltip = f"Lockout Active for {self._selected_platform or 'last session'}."
        elif not self._selected_platform:
            current_icon_key = "info"
            current_tooltip = "No platform selected. Please select a platform."
        elif not self._monitor_region_defined:
            current_icon_key = "warning"
            current_tooltip = f"Monitor region not defined for {self._selected_platform}. Go to Visual Setup."

        self._status_indicator_icon_key = current_icon_key
        self._status_indicator_tooltip = current_tooltip
        self.status_indicator_icon_info_changed.emit(self._status_indicator_icon_key, self._status_indicator_tooltip)

        # --- 3. DETERMINE MONITORING TARGET TEXT ---

        platform_name_display = self._selected_platform or "N/A"
        region_status_display = "Defined" if self._monitor_region_defined else "Not Set"
        self._monitoring_target_text = f"{platform_name_display} - Region: {region_status_display}"
        self.monitoring_target_text_changed.emit(self._monitoring_target_text)

        # --- 4. UPDATE BUTTON ENABLEMENT STATES ---
        self._update_button_states()

        # --- 5. NEW: DETERMINE AND EMIT MAIN WINDOW STATUS BAR MESSAGE ---
        if self._is_monitoring_globally_active:
            # When monitoring is active, specific events (start, stop, errors, P&L updates)
            # should set their own transient messages. Avoid setting a generic "Active"
            # message here that might overwrite more specific, temporary statuses.
            # If the last message was an error, but monitoring is now active and fine,
            # perhaps a general "Monitoring [Platform]..." could be set if no other
            # BUSY or specific status update message is pending.
            # For now, let's assume active monitoring messages are handled elsewhere.
            pass
        else:
            # Monitoring is NOT globally active. Set a clear inactive/ready/error state.
            if "LOCKOUT" in self._current_pnl_text.upper():
                # Lockout state is dominant. _handle_threshold_exceeded already set the status bar.
                # No change needed here; let the lockout message persist.
                pass
            elif self._current_pnl_text == "Error":
                # An error occurred that stopped monitoring.
                # _handle_monitoring_error (with is_stopped=True) or the pre-check failure
                # in start_monitoring would have already emitted a specific error message.
                # Let that specific error persist.
                pass
            elif not self._selected_platform:
                self.status_message_changed.emit("Ready. Please select a platform.", "INFO")
            elif not self._monitor_region_defined:
                self.status_message_changed.emit(f"Ready. Monitor region for {self._selected_platform} needs setup.",
                                                 "WARNING")
            # Add other "not ready because of prerequisite X" checks here if desired
            else:
                # All prerequisites for the selected platform seem okay, monitoring is just not active.
                self.status_message_changed.emit("Ready.", "INFO")

    def _update_button_states(self):
        """Updates the internal state and emits signals for button enablement."""
        self._logger.info(
            f"DASHBOARD_VM: _update_button_states - Called. _is_monitoring_globally_active: {self._is_monitoring_globally_active}, "
            f"_selected_platform: {self._selected_platform}, _monitor_region_defined: {self._monitor_region_defined}"
        )
        all_prereqs_met = True
        if self._selected_platform:
            if not self._monitor_region_defined: # Using simplified check for now
                all_prereqs_met = False
        else:
            all_prereqs_met = False

        self._can_start = (
                not self._is_monitoring_globally_active and
                bool(self._selected_platform) and
                all_prereqs_met
        )
        self._can_stop = self._is_monitoring_globally_active

        # Calculate _can_test_flash correctly ONCE
        self._can_test_flash = (
                bool(self._selected_platform) and
                (self._monitor_region_defined or self._flatten_regions_defined) and
                not self._is_flash_test_in_progress  # Disable if a flash test is currently running
        )

        self.can_start_monitoring_changed.emit(self._can_start)
        self.can_stop_monitoring_changed.emit(self._can_stop)
        self.can_test_flash_changed.emit(self._can_test_flash) # Emit the correct value

        # Also, update your logger line here to include the FlashInProgress state for better debugging
        self._logger.debug(
            f"Button states updated: CanStart={self._can_start}, CanStop={self._can_stop}, "
            f"CanFlash={self._can_test_flash} (FlashInProgress={self._is_flash_test_in_progress})"
        )

    # --- Command Slots (Called by the View) ---

    @Slot()
    def start_monitoring(self):
        self._logger.debug(f"DashboardVM: start_monitoring called for platform '{self._selected_platform or 'None'}'")

        # --- 1. PRE-START VALIDATIONS (ViewModel Level) ---
        if not self._selected_platform:
            self.status_message_changed.emit("No platform selected. Cannot start monitoring.", "ERROR")
            self._logger.warning("Start monitoring attempt with no platform selected.")
            return

        if self._is_monitoring_globally_active:
            self.status_message_changed.emit(
                f"Monitoring is already active for '{self._monitoring_platform}'. Please stop it first.", "WARNING")
            self._logger.warning(f"Start monitoring attempt while already active for '{self._monitoring_platform}'.")
            return

        if not self._monitor_region_defined:
            self.status_message_changed.emit(f"Cannot start: Monitor region not defined for {self._selected_platform}.",
                                             "ERROR")
            self.activity_log_appended.emit(f"Start monitoring failed: Monitor region not defined.", "ERROR")
            self._logger.warning(
                f"Start monitoring attempt for {self._selected_platform} but monitor region not defined.")
            return

        # --- 1.5. NEW: PLATFORM READINESS PRE-CHECK (Service Level) ---
        self._logger.info(f"DashboardVM: Performing platform readiness pre-check for '{self._selected_platform}'.")
        readiness_check_result = self._monitoring_service.check_platform_readiness(self._selected_platform)

        if readiness_check_result.is_failure:
            error_object = readiness_check_result.error
            error_message_str = str(error_object)
            user_facing_error_message = f"Cannot start monitoring: {error_message_str}"

            level_for_status_bar = "ERROR"
            if isinstance(error_object, PlatformNotRunningError):
                level_for_status_bar = "WARNING"

            self.status_message_changed.emit(user_facing_error_message, level_for_status_bar)
            self.activity_log_appended.emit(user_facing_error_message, "ERROR")
            self._logger.warning(
                f"Monitoring start aborted for '{self._selected_platform}' due to pre-check failure: {error_message_str}")

            # --- ADD TO RECENT ALERTS for pre-check failure ---
            timestamp = time.strftime("%H:%M:%S")
            # Use the core error_message_str for the alert, not the user_facing_error_message with "Cannot start..."
            alert_msg_for_list = f"{timestamp}: [ERROR] {error_message_str}"
            self._recent_alerts.append(alert_msg_for_list)
            if len(self._recent_alerts) > 5: self._recent_alerts = self._recent_alerts[-5:]
            self.recent_alerts_updated.emit(self._recent_alerts.copy())
            # No flag needed here as _handle_monitoring_error is not involved in this path.

            if self._is_monitoring_globally_active:  # Safeguard
                self._is_monitoring_globally_active = False
                self._monitoring_platform = None
                self.monitoring_session_activity_changed.emit(False, None)

            self._current_pnl_text = "Error"
            self._update_dashboard_display_state()
            return
        # --- 2. FETCH CONFIGURATION (Threshold, Interval) ---
        self._logger.debug(f"Fetching configuration for starting monitoring on {self._selected_platform}.")
        threshold_res = self._config_repo.get_platform_stop_loss_threshold(self._selected_platform)
        if threshold_res.is_failure:
            err_msg = f"Error getting threshold for {self._selected_platform}: {threshold_res.error}"
            self.status_message_changed.emit(err_msg, "ERROR")
            self.activity_log_appended.emit(err_msg, "ERROR")
            self._logger.error(err_msg)
            return
        platform_threshold = threshold_res.value

        interval = self._config_repo.get_global_setting("monitor_interval_seconds", 2.0)
        self._logger.debug(f"Using threshold: {platform_threshold}, interval: {interval}s.")

        # --- 3. START HISTORY SESSION ---
        self._logger.debug(f"Attempting to start history session for {self._selected_platform}.")
        try:
            self._current_session_id = self._history_service.start_session(
                platform=self._selected_platform,
                threshold=platform_threshold
            )
            self._logger.info(f"HistoryService started session: {self._current_session_id}")
        except Exception as e_hist_start:
            self._logger.error(f"CRITICAL: Failed to start history session: {e_hist_start}", exc_info=True)
            self.status_message_changed.emit("Failed to start history session. Monitoring aborted.", "ERROR")
            self._current_pnl_text = "Error"  # Set PNL text to reflect error
            self._is_monitoring_globally_active = False
            self._monitoring_platform = None
            self._update_dashboard_display_state()  # Refresh UI to show error state
            return

        # --- 4. INITIATE MONITORING SERVICE ---
        self.status_message_changed.emit(f"Starting monitoring for {self._selected_platform}...", "BUSY")
        self.activity_log_appended.emit(f"Attempting to start monitoring for {self._selected_platform}...", "INFO")
        self._logger.info(
            f"Calling MonitoringService.start_monitoring for {self._selected_platform} "
            f"(Session: {self._current_session_id})."
        )

        start_result = self._monitoring_service.start_monitoring(
            platform=self._selected_platform,
            threshold=platform_threshold,
            session_id=self._current_session_id,
            interval_seconds=interval,
            on_status_update=self._handle_monitoring_status_update,
            on_threshold_exceeded=self._handle_threshold_exceeded,
            on_error=self._handle_monitoring_error,
            on_individual_check_complete=self._handle_monitoring_result  # <<< MODIFIED: ADDED THIS LINE
        )

        # --- 5. UPDATE STATE BASED ON MONITORING START RESULT ---
        if start_result.is_success:
            self._logger.info(
                f"Monitoring task successfully submitted for {self._selected_platform} (Session: {self._current_session_id}).")
            self._is_monitoring_globally_active = True
            self._monitoring_platform = self._selected_platform  # Track which platform is being monitored
            self.monitoring_session_activity_changed.emit(True, self._monitoring_platform)  # <<< EMIT SIGNAL
            self._current_pnl_text = "Waiting for data..."  # Initial P&L text
        else:
            self._logger.error(f"Failed to submit monitoring task for {self._selected_platform}: {start_result.error}")
            self.status_message_changed.emit(f"Failed to start monitoring task: {start_result.error}", "ERROR")
            self.activity_log_appended.emit(f"Failed to start monitoring task: {start_result.error}", "ERROR")

            # End the history session that was just started, as monitoring task failed to launch
            if self._current_session_id:
                self._logger.debug(
                    f"Ending history session {self._current_session_id} due to monitoring start failure.")
                try:
                    # Provide a sensible default for final_pnl if no data was ever recorded
                    last_known_pnl = 0.0
                    if self._last_monitor_result and self._last_monitor_result.has_values:  # Defensive check
                        last_known_pnl = self._last_monitor_result.minimum_value

                    self._history_service.end_session(
                        session_id=self._current_session_id,
                        final_pnl=last_known_pnl,  # Or 0.0 if no data
                        lockout_triggered=False,
                        final_screenshot_path=None
                    )
                    self._logger.info(
                        f"History session {self._current_session_id} ended due to monitoring task start failure.")
                except Exception as e_hist_end_fail:
                    self._logger.error(
                        f"Failed to end history session {self._current_session_id} after monitoring task start failure: {e_hist_end_fail}",
                        exc_info=True)
                self._current_session_id = None

            # Reset monitoring state
            self._is_monitoring_globally_active = False
            self._monitoring_platform = None
            self._current_pnl_text = "Error"  # PNL text reflects the failure

        # Finally, update all dashboard display elements based on the new state.
        # This will emit current_pnl_text_changed, status_indicator_icon_info_changed, etc.
        self._update_dashboard_display_state()

    @Slot()
    def stop_monitoring(self):
        """Stops any active monitoring."""
        if not self._is_monitoring_globally_active:
            self.status_message_changed.emit("Monitoring is not active.", "WARNING")
            self._logger.warning("Stop monitoring requested but not active.")
            return

        # Capture necessary info BEFORE states are cleared or service is called
        session_id_to_end = self._current_session_id
        platform_that_was_monitored = self._monitoring_platform  # Use for logging
        last_pnl_before_stop = 0.0
        if self._last_monitor_result:
            last_pnl_before_stop = self._last_monitor_result.minimum_value

        self._logger.info(
            f"User requested stop monitoring for platform '{platform_that_was_monitored}' (Session: {session_id_to_end}).")
        self.status_message_changed.emit("Stopping monitoring...", "BUSY")  # Use "BUSY"
        self.activity_log_appended.emit(f"Attempting to stop monitoring for {platform_that_was_monitored}...", "INFO")

        stop_request_result = self._monitoring_service.stop_monitoring()

        # --- End History Session for Normal Stop ---
        if session_id_to_end:
            try:
                self._history_service.end_session(
                    session_id=session_id_to_end,
                    final_pnl=last_pnl_before_stop,
                    lockout_triggered=False,
                    final_screenshot_path=None
                )
                self._logger.info(f"History session {session_id_to_end} ended due to manual stop.")
            except Exception as e_hist_end:
                self._logger.error(
                    f"Failed to properly end history session {session_id_to_end} on normal stop: {e_hist_end}",
                    exc_info=True)
            self._current_session_id = None
        else:
            # This case might happen if stop is clicked very rapidly after an error/auto-stop
            self._logger.warning(
                "Stop monitoring called but no active session ID was tracked in ViewModel (might have been cleared by another handler).")
        # --- END End History Session ---

        # Update internal state primarily
        self._is_monitoring_globally_active = False
        self._monitoring_platform = None
        self.monitoring_session_activity_changed.emit(False, None)  # <<< EMIT HERE
        self._current_pnl_text = "N/A"  # Monitoring stopped, so P&L is no longer "live"
        self._last_monitor_result = None  # Clear the last result

        # Report outcome of the stop request
        if stop_request_result.is_success:
            self._logger.info(f"Monitoring stop request sent successfully for {platform_that_was_monitored}.")
            self.status_message_changed.emit("Monitoring stopped.", "SUCCESS")  # Change from INFO to SUCCESS
            self.activity_log_appended.emit(f"Monitoring stopped for {platform_that_was_monitored}.", "SUCCESS")
        else:
            self._logger.error(
                f"Failed to send stop monitoring request gracefully for {platform_that_was_monitored}: {stop_request_result.error}")
            self.status_message_changed.emit(
                f"Monitoring stop request failed for {platform_that_was_monitored}: ({stop_request_result.error}).",
                "WARNING")
            self.activity_log_appended.emit(
                f"Error sending stop request for {platform_that_was_monitored}: {stop_request_result.error}", "ERROR")

        # Update all relevant dashboard display elements based on the new state
        self._update_dashboard_display_state()

    @Slot()
    def test_flash_regions(self):
        """
        Collects coordinates for defined regions and initiates a flash effect.
        The 'Test Flash' button will be disabled during the flash animation.
        """
        # --- Prevent multiple concurrent flash tests ---
        if self._is_flash_test_in_progress:
            self._logger.info("Flash test is already in progress. Ignoring new request.")
            self.status_message_changed.emit("Flash test already running.", "INFO")
            return

        # 1. Check platform selection
        if not self._selected_platform:
            self.status_message_changed.emit("No platform selected to test flash.", "ERROR")
            self.activity_log_appended.emit("Flash test failed: No platform selected.", "ERROR")
            self._logger.warning("test_flash_regions: Attempted with no platform selected.")  # Added log
            return

        # 2. Check if any regions are defined
        if not self._monitor_region_defined and not self._flatten_regions_defined:
            msg = f"No regions defined for {self._selected_platform} to flash."
            self.status_message_changed.emit(msg, "ERROR")
            self.activity_log_appended.emit(f"Flash test failed: {msg}", "ERROR")
            self._logger.warning(f"test_flash_regions: {msg}")  # Added log
            return

        self._logger.info(f"Initiating flash test for all regions on {self._selected_platform}")
        self.activity_log_appended.emit(f"Initiating flash test for {self._selected_platform}...", "INFO")

        # 4. Collect coordinates
        coords_to_flash: List[Tuple[int, int, int, int]] = []
        try:
            if self._monitor_region_defined:
                monitor_result = self._region_service.get_monitor_region(self._selected_platform)
                if monitor_result.is_success and monitor_result.value and isinstance(monitor_result.value.coordinates,
                                                                                     tuple) and len(
                    monitor_result.value.coordinates) == 4:
                    coords_to_flash.append(monitor_result.value.coordinates)
            if self._flatten_regions_defined:
                flatten_result = self._region_service.get_regions_by_platform(self._selected_platform, "flatten")
                if flatten_result.is_success and flatten_result.value:
                    for region in flatten_result.value:
                        if region and isinstance(region.coordinates, tuple) and len(region.coordinates) == 4:
                            coords_to_flash.append(region.coordinates)
        except Exception as e:
            self._logger.error(f"Error collecting regions for flash: {e}", exc_info=True)
            self.status_message_changed.emit("Error preparing regions for flash. Check logs.", "ERROR")
            return

        if not coords_to_flash:
            msg = f"No valid regions with coordinates found for {self._selected_platform} to flash."
            self.status_message_changed.emit(msg, "ERROR");
            self.activity_log_appended.emit(f"Flash test failed: {msg}", "ERROR")
            self._logger.error(f"test_flash_regions: {msg}")  # Added log
            return

        # --- Set state to indicate flash is in progress & update button ---
        self._logger.debug("test_flash_regions: >>> Setting _is_flash_test_in_progress = True")  # NEW DEBUG LOG
        self._is_flash_test_in_progress = True
        self._current_flash_task_id = None  # Will be set if start is successful

        self._logger.debug(
            "test_flash_regions: >>> Calling _update_button_states() to disable flash button.")  # NEW DEBUG LOG
        self._update_button_states()  # This will disable the 'Test Flash' button
        # The _update_button_states method itself has a debug log that will show the CanFlash state
        self._logger.debug(
            f"test_flash_regions: >>> After _update_button_states(). Current _is_flash_test_in_progress: {self._is_flash_test_in_progress}")  # NEW DEBUG LOG

        self.status_message_changed.emit(f"Flashing {len(coords_to_flash)} region(s)...", "BUSY")  # Use BUSY

        # --- Call the flash service ---
        # The flash_service.flash_regions should return Result[str] where str is task_id
        flash_start_result: Result[str] = self._flash_service.flash_regions(coords_to_flash)

        if flash_start_result.is_success:
            self._current_flash_task_id = flash_start_result.value  # Store the task_id
            msg = f"Flash test initiated (Task ID: {self._current_flash_task_id}) for {len(coords_to_flash)} region(s)."
            self.activity_log_appended.emit(msg, "INFO")
            self._logger.info(msg)
            # Button remains disabled as _is_flash_test_in_progress is True.
            # Status message will be updated upon completion/failure via signals.
        else:
            # Flash task failed to START
            msg = f"Failed to start flash test task: {flash_start_result.error}"
            self.status_message_changed.emit(msg, "ERROR")
            self.activity_log_appended.emit(f"Flash test START FAILED: {msg}", "ERROR")
            self._logger.error(msg)

            # --- Reset flashing state as it failed to start ---
            self._logger.debug(
                "test_flash_regions: >>> Flash start FAILED. Resetting flag and updating buttons.")  # NEW DEBUG LOG
            self._is_flash_test_in_progress = False
            self._current_flash_task_id = None
            self._update_button_states()  # This will re-enable the 'Test Flash' button
            self._logger.debug(
                f"test_flash_regions: >>> After FAILED start, _is_flash_test_in_progress: {self._is_flash_test_in_progress}")  # NEW DEBUG

    # --- NEW SLOTS for Flash Service Signals ---
    @Slot(str)  # Receives task_id
    def _handle_flash_animation_completed(self, task_id: str):
        """
        Called when the QtFlashService signals that the flash animation has completed.
        """
        self._logger.info(f"Received flash animation completed signal for task: {task_id}")
        # Check if this is the task we are currently tracking
        if self._is_flash_test_in_progress and (
                self._current_flash_task_id is None or self._current_flash_task_id == task_id):
            self._is_flash_test_in_progress = False
            self._current_flash_task_id = None
            self._update_button_states()  # Re-enable the 'Test Flash' button
            self.status_message_changed.emit("Flash test completed.", "SUCCESS")
            self.activity_log_appended.emit(f"Flash test (Task: {task_id}) completed successfully.", "SUCCESS")
        elif not self._is_flash_test_in_progress:
            self._logger.warning(
                f"Flash animation completed for task '{task_id}', but no flash test was marked as in progress. State inconsistency?")
        elif self._current_flash_task_id != task_id:
            self._logger.warning(
                f"Flash animation completed for task '{task_id}', but current tracked task is '{self._current_flash_task_id}'. Ignoring stale signal.")

    @Slot(str, str)  # Receives task_id, error_message
    def _handle_flash_animation_failed(self, task_id: str, error_msg: str):
        """
        Called when the QtFlashService signals that the flash animation has failed.
        This can be due to an error during the animation itself, or if the task failed to start.
        """
        self._logger.error(f"Received flash animation failed signal for task: {task_id}, Error: {error_msg}")
        if self._is_flash_test_in_progress and (
                self._current_flash_task_id is None or self._current_flash_task_id == task_id):
            self._is_flash_test_in_progress = False
            self._current_flash_task_id = None
            self._update_button_states()  # Re-enable the 'Test Flash' button
            self.status_message_changed.emit(f"Flash test error: {error_msg}", "ERROR")
            self.activity_log_appended.emit(f"Flash test (Task: {task_id}) FAILED: {error_msg}", "ERROR")
        elif not self._is_flash_test_in_progress:
            self._logger.warning(
                f"Flash animation failed for task '{task_id}', but no flash test was marked as in progress. State inconsistency?")
        elif self._current_flash_task_id != task_id:
            self._logger.warning(
                f"Flash animation failed for task '{task_id}', but current tracked task is '{self._current_flash_task_id}'. Ignoring stale signal.")

    # --- Private Helper / Update Methods ---

    @Slot(str)
    def _handle_platform_selection_change(self, platform: str):
        """Connected to PlatformSelectionService signal."""
        self._logger.debug(f"DashboardViewModel received platform change: {platform}")
        self._update_state_for_platform(platform)

    def _update_state_for_platform(self, platform: Optional[str]):  # platform can be None
        """Updates the ViewModel's state based on the selected platform."""
        self._logger.info(f"DashboardViewModel._update_state_for_platform: Updating for '{platform or 'None'}'")

        # If the selected platform is changing AND monitoring is not globally active,
        # clear any lingering PNL text that might indicate an error from a previous attempt/platform.
        if self._selected_platform != platform and not self._is_monitoring_globally_active:
            if self._current_pnl_text == "Error" or \
                    self._current_pnl_text == "Waiting for data..." or \
                    self._current_pnl_text == "No P&L data":  # Clear these non-live states
                self._logger.debug(
                    f"Platform changed while inactive from '{self._selected_platform}' to '{platform}'. "
                    f"Resetting _current_pnl_text from '{self._current_pnl_text}' to 'N/A'.")
                self._current_pnl_text = "N/A"
            self._last_monitor_result = None  # Also clear any stale result from a different context

        self._selected_platform = platform

        if not platform:
            self._logger.debug("Platform is None. Resetting relevant states.")
            self._monitor_region_defined = False
            self._flatten_regions_defined = False
            # Ensure PNL text is neutral if no platform and not actively monitoring
            if not self._is_monitoring_globally_active:
                self._current_pnl_text = "N/A"
            # _update_prerequisite_statuses will be called by refresh_ui_signals (or _update_dashboard_display_state)
            # _update_button_states will be called by _update_dashboard_display_state
        else:
            # Platform is valid, load its specific region status
            try:
                monitor_region_res = self._region_service.get_monitor_region(platform)
                self._monitor_region_defined = monitor_region_res.is_success and monitor_region_res.value is not None
                self._logger.debug(f"  Monitor region defined for {platform}: {self._monitor_region_defined}")

                flatten_regions_res = self._region_service.get_regions_by_platform(platform, "flatten")
                self._flatten_regions_defined = flatten_regions_res.is_success and bool(flatten_regions_res.value)
                self._logger.debug(f"  Flatten regions defined for {platform}: {self._flatten_regions_defined}")
            except Exception as e:
                self._logger.error(f"Error checking regions for {platform}: {e}", exc_info=True)
                self._monitor_region_defined = False
                self._flatten_regions_defined = False

        # Centralize UI updates after state is prepared.
        # refresh_ui_signals calls _update_prerequisite_statuses and _update_dashboard_display_state.
        self.refresh_ui_signals()

    @Slot()
    def refresh_ui_signals(self):
        """Emits all signals reflecting the current state for initial UI sync or full refresh."""
        self._logger.info(f"DashboardViewModel: Executing refresh_ui_signals for {self._selected_platform or 'None'}")

        # 1. Update prerequisite display first, as it might inform other states.
        self._logger.debug(f"refresh_ui_signals -> calling _update_prerequisite_statuses.")
        self._update_prerequisite_statuses(self._selected_platform)

        # 2. Call the main state update method to ensure all card elements and status bar are signaled.
        self._logger.debug(f"refresh_ui_signals -> calling _update_dashboard_display_state.")
        self._update_dashboard_display_state()  # This calculates and emits PNL, Target, Icon, Buttons, AND STATUS BAR.

        # 3. Emit signals for other UI elements not directly handled by _update_dashboard_display_state.
        self.recent_alerts_updated.emit(self._recent_alerts.copy())

        # 4. Emit the monitoring activity state for MainViewModel.
        self._logger.debug(
            f"refresh_ui_signals -> emitting monitoring_session_activity_changed ({self._is_monitoring_globally_active}, {self._monitoring_platform}).")
        self.monitoring_session_activity_changed.emit(self._is_monitoring_globally_active, self._monitoring_platform)

        self._logger.info(f"DashboardViewModel: refresh_ui_signals complete.")

    # --- Callback Handlers for Monitoring Service ---

    def _handle_monitoring_status_update(self, message: str, level: str):
        """Callback for status updates from MonitoringService."""
        self._logger.debug(f"Monitoring Status Update: [{level}] {message}")
        self.activity_log_appended.emit(message, level)

        # Add to recent alerts if it's a warning/error
        if level.upper() in ["WARNING", "ERROR"]:
            timestamp = time.strftime("%H:%M:%S")
            # Include level in the message for better type detection
            alert_msg = f"{timestamp}: [{level.upper()}] {message}"
            self._recent_alerts.append(alert_msg)
            # Keep only last 5 alerts
            if len(self._recent_alerts) > 5:
                self._recent_alerts = self._recent_alerts[-5:]
            self.recent_alerts_updated.emit(self._recent_alerts.copy())

    def _handle_monitoring_result(self, result: MonitoringResult):
        """
        Callback for when MonitoringService completes an individual check.
        This method updates the live P&L display if the result pertains to
        the currently selected and actively monitored platform.
        """
        self._logger.debug(
            f"DashboardVM: _handle_monitoring_result received for session '{result.session_id if hasattr(result, 'session_id') else 'N/A'}'. "
            f"Platform in result (if available via session): {self._history_service.get_session_summary(result.session_id)['platform'] if hasattr(result, 'session_id') and result.session_id else 'N/A'}. "
            f"Selected UI platform: '{self._selected_platform}'. "
            f"Globally active: {self._is_monitoring_globally_active}, for platform: '{self._monitoring_platform}'. "
            f"Result has values: {result.has_values}, MinValue: {result.minimum_value if result.has_values else 'N/A'}."
        )

        # Store the absolute latest result, regardless of platform.
        # This might be useful for diagnostics or if _last_monitor_result needs to be truly global.
        self._last_monitor_result = result

        # --- CRITICAL LOGIC FOR UPDATING LIVE P&L DISPLAY ---
        # Only update the _current_pnl_text (and thus the live display via signal emission)
        # IF the monitoring is globally active AND the platform being monitored (_monitoring_platform)
        # matches the platform currently selected in the UI (_selected_platform).
        if self._is_monitoring_globally_active and self._monitoring_platform == self._selected_platform:
            if result.has_values:
                self._current_pnl_text = f"${result.minimum_value:,.2f}"
                self._logger.debug(
                    f"Live P&L text for '{self._selected_platform}' updated to: {self._current_pnl_text}.")
            else:
                # No numeric P&L value was extracted in this specific check.
                self._current_pnl_text = "No P&L data"  # Or "Reading..." or "Extraction Failed"
                self._logger.debug(
                    f"Live P&L text for '{self._selected_platform}' set to '{self._current_pnl_text}' (no values in this result).")

            # Emit the signal for the P&L display label to update.
            # The DashboardView's slot will also handle setting the QSS 'state' property.
            self.current_pnl_text_changed.emit(self._current_pnl_text)
        else:
            # If monitoring is not active, or is active for a *different* platform than the one
            # currently selected in the UI, then this specific MonitoringResult should not
            # directly dictate the _current_pnl_text for the *selected UI platform's* display.
            # The _update_dashboard_display_state() method is responsible for setting the
            # P&L text to "N/A", "Error", or reflecting the status of a different monitored platform
            # when the UI is refreshed.
            self._logger.debug(
                "Skipping direct P&L text update from _handle_monitoring_result because monitoring conditions "
                f"(active: {self._is_monitoring_globally_active}, "
                f"monitored_platform: '{self._monitoring_platform}', "
                f"selected_platform: '{self._selected_platform}') "
                "are not met for this result to update the current view's P&L."
            )

    def _handle_threshold_exceeded(self, result: MonitoringResult):  # result is MonitoringResult from the service
        """Callback from MonitoringService when threshold is breached."""
        # Capture platform name BEFORE clearing state, as it's needed for history and lockout
        active_monitoring_platform = self._monitoring_platform

        self._logger.error(
            f"DashboardViewModel: THRESHOLD EXCEEDED! Value: {result.minimum_value}, Platform: {active_monitoring_platform}")

        # --- End History Session for Lockout (DO THIS FIRST) ---
        session_id_to_end = self._current_session_id
        final_screenshot_path_on_breach = result.screenshot_path

        if session_id_to_end:
            try:
                self._history_service.end_session(
                    session_id=session_id_to_end,
                    final_pnl=result.minimum_value,  # Value that triggered lockout
                    lockout_triggered=True,
                    final_screenshot_path=final_screenshot_path_on_breach
                )
                self._logger.info(f"History session {session_id_to_end} ended due to threshold exceeded.")
            except Exception as e_hist_end:
                self._logger.error(
                    f"Failed to properly end history session {session_id_to_end} on threshold exceeded: {e_hist_end}",
                    exc_info=True)
            self._current_session_id = None  # Clear session ID after attempting to end
        else:
            self._logger.error(
                "Threshold exceeded callback received, but no active session ID was tracked in ViewModel!")
        # --- END End History Session ---
        active_monitoring_platform = self._monitoring_platform  # Capture before clearing

        # --- Now, update internal state and UI signals AFTER history is handled ---
        was_monitoring_platform = self._monitoring_platform
        self._is_monitoring_globally_active = False
        self._monitoring_platform = None  # Clear which platform was being monitored
        self._current_pnl_text = f"LOCKOUT (${result.minimum_value:,.2f})"
        # self.current_pnl_text_changed.emit(self._current_pnl_text) # This will be emitted by _update_dashboard_display_state
        self._last_monitor_result = None  # Clear last result

        # Add to UI alerts list
        timestamp = time.strftime("%H:%M:%S")
        alert_msg = f"{timestamp}: LOCKOUT TRIGGERED! P&L: ${result.minimum_value:.2f}"
        self._recent_alerts.append(alert_msg)
        if len(self._recent_alerts) > 5: self._recent_alerts = self._recent_alerts[-5:]
        self.recent_alerts_updated.emit(self._recent_alerts.copy())

        # Log and update main status bar message
        self.activity_log_appended.emit(
            f"THRESHOLD EXCEEDED! Detected: ${result.minimum_value:.2f}. Initiating lockout for {active_monitoring_platform}.",
            "ERROR")
        self.status_message_changed.emit("Lockout triggered!", "ERROR")

        # Update the consolidated card and button states
        self._update_dashboard_display_state()  # This will also call _update_button_states

        self.monitoring_session_activity_changed.emit(False, None)  # <<< EMIT SIGNAL

        # --- Trigger automatic lockout ---
        if active_monitoring_platform:
            self._logger.info(f"Threshold exceeded for {active_monitoring_platform}. Triggering automatic lockout.")
            self.activity_log_appended.emit(
                f"Initiating automatic lockout sequence for {active_monitoring_platform}...", "INFO")

            duration_res = self._config_repo.get_platform_lockout_duration(active_monitoring_platform)
            if duration_res.is_failure:
                self._logger.error(
                    f"Could not get lockout duration for {active_monitoring_platform}: {duration_res.error}")
                self.activity_log_appended.emit(f"LOCKOUT FAILED: Could not get duration.", "ERROR")
                # Optionally emit status_message_changed here too
                return
            duration = duration_res.value

            flatten_res = self._region_service.get_regions_by_platform(active_monitoring_platform, "flatten")
            if flatten_res.is_failure or not flatten_res.value:
                err = flatten_res.error if flatten_res.is_failure else "No flatten regions found"
                self._logger.error(f"Cannot perform automatic lockout: Failed to get flatten regions: {err}")
                self.activity_log_appended.emit(f"LOCKOUT FAILED: Could not get flatten regions: {err}", "ERROR")
                self.status_message_changed.emit(
                    f"Lockout Failed: Missing flatten regions for {active_monitoring_platform}", "ERROR")
                return

            flatten_positions_for_service = [{"coords": (
            r.coordinates[0], r.coordinates[1], r.coordinates[0] + r.coordinates[2],
            r.coordinates[1] + r.coordinates[3])} for r in flatten_res.value]
            fullscreen_enabled = self._config_repo.get_global_setting("fullscreen_overlay", True)

            lockout_start_res = self._lockout_service.perform_lockout(
                platform=active_monitoring_platform,
                flatten_positions=flatten_positions_for_service,
                lockout_duration=duration,
                fullscreen=fullscreen_enabled,
                on_status_update=self._handle_monitoring_status_update  # Pass status updates for lockout process
            )

            if lockout_start_res.is_failure:
                self._logger.error(f"Failed to initiate automatic lockout task: {lockout_start_res.error}")
                self.activity_log_appended.emit(f"LOCKOUT START FAILED: {lockout_start_res.error}", "ERROR")
                self.status_message_changed.emit(f"Lockout Start Failed: {lockout_start_res.error}", "ERROR")
            else:
                self._logger.info(
                    f"Automatic lockout sequence task initiated successfully for {active_monitoring_platform}.")
                self.activity_log_appended.emit(
                    f"Automatic lockout sequence initiated for {active_monitoring_platform}.", "INFO")
        else:
            self._logger.error(
                "Threshold exceeded but could not determine which platform was being monitored. Lockout not triggered.")
            self.activity_log_appended.emit("Threshold exceeded but monitoring platform unknown. Lockout skipped.",
                                            "ERROR")

    def _handle_monitoring_error(self, error_msg: str, is_task_definitively_stopped: bool):
        self._logger.info(
            f"DASHBOARD_VM: _handle_monitoring_error ENTERED. Error: '{error_msg}'. "
            f"Is task definitively stopped: {is_task_definitively_stopped}. "
            f"Prior _is_monitoring_globally_active: {self._is_monitoring_globally_active}."
        )

        # --- Determine UI message levels ---
        level_for_status_bar = "ERROR"
        # (keep your existing known_platform_detection_phrases logic for level_for_status_bar)
        known_platform_detection_phrases = ["failed to detect", "platform not running", "window not found"]
        if any(phrase.lower() in error_msg.lower() for phrase in known_platform_detection_phrases):
            level_for_status_bar = "WARNING"

        activity_log_level = "ERROR" if is_task_definitively_stopped else "WARNING"
        activity_log_prefix = "Monitoring stopped due to error: " if is_task_definitively_stopped else "Monitoring error: "

        self.activity_log_appended.emit(f"{activity_log_prefix}{error_msg}", activity_log_level)
        self.status_message_changed.emit(f"Monitoring error: {error_msg}", level_for_status_bar)

        # --- Add to _recent_alerts ---
        # This method is now the primary handler for errors from an active/failing worker.
        # Add the error message it received.
        timestamp = time.strftime("%H:%M:%S")
        alert_level_prefix = "[ERROR]" if is_task_definitively_stopped else "[WARNING]"  # Reflect severity in alert
        alert_msg_for_list = f"{timestamp}: {alert_level_prefix} {error_msg}"

        self._recent_alerts.append(alert_msg_for_list)
        if len(self._recent_alerts) > 5:
            self._recent_alerts = self._recent_alerts[-5:]
        self.recent_alerts_updated.emit(self._recent_alerts.copy())

        # --- Perform full stop actions if task is definitively stopped ---
        if is_task_definitively_stopped:
            if self._is_monitoring_globally_active:
                self._logger.info(
                    f"DASHBOARD_VM: Task definitively stopped by this error event. Performing full UI stop. Error: {error_msg}")

                session_id_to_end = self._current_session_id
                if session_id_to_end:
                    # ... (end history session logic) ...
                    self._history_service.end_session(...)  # Fill in params
                    self._logger.info(f"History session {session_id_to_end} ended due to error: {error_msg}")
                    self._current_session_id = None

                self._is_monitoring_globally_active = False
                self._monitoring_platform = None
                self._current_pnl_text = "Error"
                self._last_monitor_result = None

                self.monitoring_session_activity_changed.emit(False, None)
                self._update_prerequisite_statuses(self._selected_platform)
                self._update_dashboard_display_state()
                self._logger.info(f"DASHBOARD_VM: Full UI stop procedures complete.")
            else:
                # Already inactive, but this error confirms it. Ensure UI is consistent.
                self._logger.info(
                    f"DASHBOARD_VM: Received definitive stop error, but already inactive. Ensuring UI reflects error. Error: {error_msg}")
                if self._current_pnl_text != "Error" and "LOCKOUT" not in self._current_pnl_text.upper():
                    self._current_pnl_text = "Error"
                self._update_dashboard_display_state()  # Refresh UI
        else:
            # Recoverable error reported by worker
            self._logger.info(
                f"DASHBOARD_VM: Recoverable error reported: '{error_msg}'. Monitoring UI state remains active.")


    def _update_prerequisite_statuses(self, platform: Optional[str]):
        if not platform:
            for key in self._prerequisite_keys_list:
                self._prerequisite_states[key] = "info"
                # ViewModel now sends only the status description for "no platform"
                self.prerequisite_status_updated.emit(key, "Select Platform", "info", False)
            self._update_prerequisite_completion_badge()
            return

        self._logger.debug(f"Dashboard VM: Updating prerequisite checks for {platform} (Simplified Text)")

        # --- 1. Cold Turkey Path ---
        ct_path_ok = self._cold_turkey_service.is_blocker_path_configured()
        self._prerequisite_states["ct_path"] = "ok" if ct_path_ok else "error"
        status_desc_ctp = "Set"
        if not ct_path_ok:
            ct_path_val = self._config_repo.get_cold_turkey_path()
            status_desc_ctp = "Not Set" if not ct_path_val else "Invalid/Missing"
        self.prerequisite_status_updated.emit(  # Emitting status_desc_ctp as status_text
            "ct_path", status_desc_ctp, self._prerequisite_states["ct_path"], not ct_path_ok
        )

        # --- 2. Cold Turkey Block Setup ---
        ct_block_setup_state = "error";
        status_desc_ct_block = "Path Not Set";
        ct_block_setup_show_action = True
        if ct_path_ok:
            platform_settings = self._config_repo.get_platform_settings(platform)
            block_name = platform_settings.get("cold_turkey_block_name")
            if not block_name:
                status_desc_ct_block = "Block Name Not Set"
            else:
                verified_block_res = self._config_repo.get_verified_block(platform)
                if verified_block_res.is_success and verified_block_res.value:
                    if verified_block_res.value == block_name:
                        status_desc_ct_block = f"Verified (Block: {block_name})"
                        ct_block_setup_state = "ok";
                        ct_block_setup_show_action = False
                    else:
                        status_desc_ct_block = f"Mismatch! Set: '{block_name}', Verified: '{verified_block_res.value}'"
                else:
                    status_desc_ct_block = f"Not Verified (Block: {block_name})"
        self._prerequisite_states["ct_block_setup"] = ct_block_setup_state
        self.prerequisite_status_updated.emit(
            "ct_block_setup", status_desc_ct_block, ct_block_setup_state, ct_block_setup_show_action
        )

        # --- 3. P&L Monitor Region ---
        region_res = self._region_service.get_monitor_region(platform)
        region_defined = region_res.is_success and region_res.value is not None
        self._prerequisite_states["monitor_region"] = "ok" if region_defined else "error"
        status_desc_mr = "Defined" if region_defined else "Not Defined"
        self.prerequisite_status_updated.emit(
            "monitor_region", status_desc_mr, self._prerequisite_states["monitor_region"], not region_defined
        )

        # --- 4. Flatten Regions ---
        flatten_res = self._region_service.get_regions_by_platform(platform, "flatten")
        flatten_defined = flatten_res.is_success and bool(flatten_res.value)
        self._prerequisite_states["flatten_regions"] = "ok" if flatten_defined else "warning"
        status_desc_fr = "Defined" if flatten_defined else "Missing (Optional for lockout)"
        self.prerequisite_status_updated.emit(
            "flatten_regions", status_desc_fr, self._prerequisite_states["flatten_regions"], not flatten_defined
        )

        # --- 5. P&L Detector ---
        profile_res = self._profile_service.get_profile(platform)
        status_desc_pnl_detector = "Configuration Error";
        pnl_detector_state = "error";
        pnl_detector_show_action = True
        if profile_res.is_success and profile_res.value:
            is_default_patterns = False
            try:
                default_patterns = self._profile_service._get_default_patterns_for_platform(platform)
                if profile_res.value.numeric_patterns == default_patterns or not profile_res.value.numeric_patterns:
                    is_default_patterns = True
            except AttributeError:
                self._logger.warning("Cannot check P&L Detector patterns")
            if is_default_patterns:
                status_desc_pnl_detector = "Default Settings (Calibration Recommended)";
                pnl_detector_state = "warning"
            else:
                status_desc_pnl_detector = "Custom Settings Applied";
                pnl_detector_state = "ok";
                pnl_detector_show_action = True
        else:
            status_desc_pnl_detector = "Not Configured"
        self._prerequisite_states["pnl_detector"] = pnl_detector_state
        self.prerequisite_status_updated.emit(
            "pnl_detector", status_desc_pnl_detector, pnl_detector_state, pnl_detector_show_action
        )

        self._update_prerequisite_completion_badge()

    def _update_prerequisite_completion_badge(self):
        """Calculates prerequisite completion and emits the signal."""
        if not self._prerequisite_states:  # Not initialized yet
            self.prerequisites_completion_changed.emit("Loading...")
            return

        # Count "ok" states. You might define "warning" as partially complete if desired.
        # For now, only "ok" counts as complete.
        completed_count = sum(1 for state in self._prerequisite_states.values() if state == "ok")
        total_count = len(self._prerequisite_keys_list)  # Use the stored list length

        completion_text = f"{completed_count}/{total_count} Complete"
        if completed_count == total_count:
            completion_text = "All Checks OK"  # Or just "6/6 Complete"

        self.prerequisites_completion_changed.emit(completion_text)
        self._logger.debug(f"Prerequisites completion updated: {completion_text}")

    @Slot()
    def on_theme_refresh_requested(self):
        self._logger.info("DashboardViewModel: Theme refresh requested. Re-evaluating UI states.")
        # Re-emitting all signals will re-trigger view updates,
        # including prerequisite rows which might have theme-dependent colors.
        self.refresh_ui_signals()
