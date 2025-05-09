# src/presentation/view_models/dashboard_view_model.py

import time
from typing import List, Optional, Dict, Any, Tuple

# --- Qt Imports ---
from PySide6.QtCore import QObject, Signal, Slot, QTimer

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
from src.domain.models.platform_profile import PlatformProfile # For checking patterns
from src.domain.common.result import Result # For type hinting


class DashboardViewModel(QObject):
    """
    ViewModel for the main Dashboard tab.

    Manages the state and actions related to monitoring overview,
    quick actions, and activity logging.
    """

    # --- Signals for View updates ---
    # P&L Display
    current_pnl_text_changed = Signal(str)
    # TODO: Add signal for graph data update if implemented
    # pnl_history_updated = Signal(list) # Example: list of (timestamp, value) tuples

    # Monitoring Status Block
    monitoring_status_text_changed = Signal(str) # e.g., "Active", "Inactive", "Error"

    # Payload: (prerequisite_key: str, status_text: str, status_state: str, show_action: bool)
    # status_state can be: "ok", "warning", "error", "missing", "pending", "info"
    prerequisite_status_updated = Signal(str, str, str, bool)


    prerequisites_completion_changed = Signal(str) # <<< NEW SIGNAL: e.g., "4/6 Complete"

    # Quick Actions Button Enablement
    can_start_monitoring_changed = Signal(bool)
    can_stop_monitoring_changed = Signal(bool)
    can_test_flash_changed = Signal(bool) # Enable state for test flash button

    # Alerts and Logs
    recent_alerts_updated = Signal(list) # List of strings for the alerts box
    activity_log_appended = Signal(str, str) # message, level (e.g., "INFO", "ERROR")

    # Bottom Bar Info
    selected_platform_name_changed = Signal(str)
    pnl_format_display_changed = Signal(str) # e.g., "Default", "$1,234.56", "Custom"

    # General Status/Error Message for Status Bar
    status_message_changed = Signal(str, str) # message, level ("INFO", "ERROR", etc.)


    def __init__(self,
                 logger: ILoggerService,
                 monitoring_service: IMonitoringService,
                 lockout_service: ILockoutService,
                 flash_service: IFlashService,
                 platform_selection_service: IPlatformSelectionService,
                 config_repo: IConfigRepository,
                 region_service: IRegionService,
                 profile_service: IProfileService,
                 cold_turkey_service: IColdTurkeyService, # Ensure this is included
                 history_service: IHistoryService,  # <-- ADD PARAMETER
                 parent: Optional[QObject] = None):
        """
        Initialize the DashboardViewModel.
        # ... (full docstring) ...
        """
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
        self._cold_turkey_service = cold_turkey_service # Store it
        self._history_service = history_service  # <-- STORE INSTANCE

        # --- Internal State Attributes ---
        self._selected_platform: Optional[str] = None
        self._current_session_id: Optional[str] = None  # <-- ADDED: Track active session ID
        self._is_monitoring_globally_active: bool = False
        self._monitoring_platform: Optional[str] = None
        self._current_pnl_text: str = "N/A"
        self._monitoring_status_text: str = "Inactive"
        self._can_start: bool = False
        self._can_stop: bool = False
        self._can_test_flash: bool = False
        self._recent_alerts: List[str] = []
        self._pnl_format_display: str = "N/A"
        self._monitor_region_defined: bool = False
        self._flatten_regions_defined: bool = False
        self._last_monitor_result: Optional[MonitoringResult] = None
        # --- Pre-req checklsit counter thing

        # Or calculate dynamically if the list can change
        self._prerequisite_keys_list = [
            "ct_path",
            "ct_block_setup",
            "monitor_region",
            "flatten_regions",
            "pnl_detector"  # <<< CHANGED from pnl_value_reader (was ocr_profile)
        ]
        self._prerequisite_states: Dict[str, str] = {key: "pending" for key in
                                                     self._prerequisite_keys_list}  # Stores state like "ok", "error" for each key
        self._total_prerequisites_count = len(self._prerequisite_keys_list)  # Based on your prerequisite_keys list

        # --- Initialization ---
        self._logger.debug("Initializing DashboardViewModel...")
        self._platform_selection_service.register_platform_change_listener(
            self._handle_platform_selection_change
        )
        initial_platform = self._platform_selection_service.get_current_platform()
        self._update_state_for_platform(initial_platform)
        # Load initial data for the currently selected platform
        initial_platform = self._platform_selection_service.get_current_platform()
        self._update_state_for_platform(initial_platform) # This now triggers prerequisite updates too

        for key in self._prerequisite_keys_list:
            self._prerequisite_states[key] = "pending"  # Initial state before first check

        # --- Emit initial log message using QTimer.singleShot (cleaned up) ---
        def emit_initial_log():
            try:
                # Ensure QApplication instance exists before getting version
                app_instance = QApplication.instance()
                app_version = app_instance.applicationVersion() if app_instance else "N/A"
                initial_msg = f"MonitorPal v{app_version} initialized. Ready."
                # Use logger to announce the emission if desired at DEBUG level
                self._logger.debug(f"Emitting initial log via timer: '{initial_msg}'")
                self.activity_log_appended.emit(initial_msg, "INFO")
            except Exception as e:
                 # Log any error during emission
                 self._logger.error(f"Error emitting initial log message: {e}", exc_info=True)

        # Schedule the emission function to run shortly after initialization completes
        QTimer.singleShot(0, emit_initial_log)

        # Final log message indicating the ViewModel init is done
        self._logger.debug("DashboardViewModel initialized.")




    # --- Command Slots (Called by the View) ---

    @Slot()
    def start_monitoring(self):
        """Starts monitoring for the currently selected platform."""
        if not self._selected_platform:
            self.status_message_changed.emit("No platform selected.", "ERROR")
            return
        if self._is_monitoring_globally_active:
            self.status_message_changed.emit(f"Monitoring already active for {self._monitoring_platform}.", "WARNING")
            return

        # --- Get platform-specific threshold and global interval FIRST ---
        threshold_res = self._config_repo.get_platform_stop_loss_threshold(self._selected_platform)
        if threshold_res.is_failure:
            err_msg = f"Error getting threshold for {self._selected_platform}: {threshold_res.error}"
            self.status_message_changed.emit(err_msg, "ERROR")
            self.activity_log_appended.emit(err_msg, "ERROR")
            self._logger.error(err_msg)
            return
        platform_threshold = threshold_res.value  # Now defined

        interval = self._config_repo.get_global_setting("monitor_interval_seconds", 2.0)
        # --- End fetching config ---

        self.status_message_changed.emit(f"Starting monitoring for {self._selected_platform}...", "INFO")
        self.activity_log_appended.emit(f"Starting monitoring for {self._selected_platform}...", "INFO")
        self._logger.info(
            f"Attempting to start monitoring for {self._selected_platform} with threshold {platform_threshold}, interval {interval}s")

        # --- Start History Session ---
        try:
            self._current_session_id = self._history_service.start_session(
                platform=self._selected_platform,
                threshold=platform_threshold  # Use platform-specific threshold
            )
            self._logger.info(f"HistoryService started session: {self._current_session_id}")
        except Exception as e_hist_start:
            self._logger.error(f"CRITICAL: Failed to start history session: {e_hist_start}", exc_info=True)
            self.status_message_changed.emit("Failed to start history session. Monitoring aborted.", "ERROR")
            return  # Abort if history can't start
        # --- End Start History Session ---

        # --- Call Monitoring Service ---
        start_result = self._monitoring_service.start_monitoring(
            platform=self._selected_platform,
            threshold=platform_threshold,
            session_id=self._current_session_id,  # Pass session_id
            # history_service=self._history_service, # REMOVED - Worker gets it via DI or constructor
            interval_seconds=interval,
            on_status_update=self._handle_monitoring_status_update,
            on_threshold_exceeded=self._handle_threshold_exceeded,
            on_error=self._handle_monitoring_error
        )

        # --- Update State Based on Result ---
        if start_result.is_success:
            self._logger.info(f"Monitoring start request successful for {self._selected_platform}.")
            self._is_monitoring_globally_active = True
            self._monitoring_platform = self._selected_platform
            self._update_button_states()
        else:
            self._logger.error(f"Failed to start monitoring for {self._selected_platform}: {start_result.error}")
            self.status_message_changed.emit(f"Failed to start monitoring: {start_result.error}", "ERROR")
            self.activity_log_appended.emit(f"Failed to start monitoring: {start_result.error}", "ERROR")
            # End failed history session
            if self._current_session_id:
                try:
                    self._history_service.end_session(self._current_session_id, 0.0, False)
                except Exception as e_hist_end:
                    self._logger.error(
                        f"Failed to end history session {self._current_session_id} after monitoring start failure: {e_hist_end}")
                self._current_session_id = None
            self._is_monitoring_globally_active = False
            self._monitoring_platform = None
            self._update_button_states()

    @Slot()
    def stop_monitoring(self):
        if not self._is_monitoring_globally_active:
            self.status_message_changed.emit("Monitoring is not active.", "WARNING")
            self._logger.warning("Stop monitoring requested but not active.")
            return

        self._logger.info(f"User requested stop monitoring (was active for {self._monitoring_platform}).")
        self.status_message_changed.emit("Stopping monitoring...", "INFO")
        self.activity_log_appended.emit("Stopping monitoring...", "INFO")

        # --- Capture state needed for history BEFORE requesting stop ---
        session_id_to_end = self._current_session_id
        current_monitoring_platform_when_stopped = self._monitoring_platform
        last_pnl_before_stop = 0.0
        if self._last_monitor_result:  # self._last_monitor_result is updated by _handle_monitoring_result
            last_pnl_before_stop = self._last_monitor_result.minimum_value
        # --- End Capture State ---

        stop_request_result = self._monitoring_service.stop_monitoring()  # Request worker to cancel

        # --- End History Session for Normal Stop ---
        if session_id_to_end:
            try:
                self._history_service.end_session(
                    session_id=session_id_to_end,
                    final_pnl=last_pnl_before_stop,
                    lockout_triggered=False,
                    final_screenshot_path=None  # No specific "lockout" screenshot on normal stop
                )
                self._logger.info(f"History session {session_id_to_end} ended due to manual stop.")
            except Exception as e_hist_end:
                self._logger.error(
                    f"Failed to properly end history session {session_id_to_end} on normal stop: {e_hist_end}",
                    exc_info=True)
            self._current_session_id = None  # Clear stored session ID
        else:
            self._logger.warning("Stop monitoring called but no active session ID was tracked in ViewModel.")
        # --- END End History Session ---

        # Update internal state AFTER ending history session and processing stop_request_result
        self._is_monitoring_globally_active = False
        self._monitoring_platform = None  # Clear which platform *was* monitored
        self._current_pnl_text = "N/A"
        self.current_pnl_text_changed.emit(self._current_pnl_text)
        self._last_monitor_result = None

        if stop_request_result.is_success:
            self._logger.info(
                f"Monitoring stop request sent successfully for {current_monitoring_platform_when_stopped}.")
            self.status_message_changed.emit("Monitoring stopped.", "INFO")
            self.activity_log_appended.emit("Monitoring stopped.", "SUCCESS")
        else:
            self._logger.error(f"Failed to send stop monitoring request gracefully: {stop_request_result.error}")
            self.status_message_changed.emit(f"Monitoring stop request failed: ({stop_request_result.error}).",
                                             "WARNING")
            self.activity_log_appended.emit(f"Error sending stop request: {stop_request_result.error}", "ERROR")

        self._update_button_states()

    @Slot()
    def test_flash_regions(self):
        """
        Collects coordinates for all defined regions (monitor and flatten)
        for the currently selected platform and initiates a simultaneous
        flash effect for all of them using the FlashService.
        """
        # 1. Check if a platform is selected
        if not self._selected_platform:
            self.status_message_changed.emit("No platform selected to test flash.", "ERROR")
            self.activity_log_appended.emit("Flash test failed: No platform selected.", "ERROR")
            return

        # 2. Check if any regions are defined (using internal flags updated by _update_state_for_platform)
        if not self._monitor_region_defined and not self._flatten_regions_defined:
            msg = f"No regions defined for {self._selected_platform} to flash."
            self.status_message_changed.emit(msg, "ERROR")
            self.activity_log_appended.emit(f"Flash test failed: {msg}", "ERROR")
            return

        # 3. Log initiation
        self._logger.info(f"Testing flash for all regions on {self._selected_platform}")  # Use _logger
        self.status_message_changed.emit(f"Gathering regions for {self._selected_platform}...", "INFO")
        self.activity_log_appended.emit(f"Initiating flash test for {self._selected_platform}...", "INFO")

        # 4. Collect *Coordinate Tuples* for all valid defined regions
        coords_to_flash: List[Tuple[int, int, int, int]] = []

        # Get Monitor Region Coords
        try:
            if self._monitor_region_defined:
                monitor_result = self._region_service.get_monitor_region(self._selected_platform)
                # Check result is success, has a value, and coordinates are valid
                if monitor_result.is_success and monitor_result.value and isinstance(monitor_result.value.coordinates,
                                                                                     tuple) and len(
                        monitor_result.value.coordinates) == 4:
                    coords_to_flash.append(monitor_result.value.coordinates)
                    self._logger.debug(
                        f"Added monitor region coords for flash: {monitor_result.value.coordinates}")  # Use _logger
                elif monitor_result.is_failure:
                    self._logger.warning(
                        f"Failed to get monitor region details during flash test: {monitor_result.error}")  # Use _logger
                else:
                    self._logger.warning(
                        f"Monitor region object or coordinates invalid: {monitor_result.value}")  # Use _logger
        except Exception as e:
            self._logger.error(f"Unexpected error getting monitor region for flash: {e}", exc_info=True)  # Use _logger

        # Get Flatten Regions Coords
        try:
            if self._flatten_regions_defined:
                flatten_result = self._region_service.get_regions_by_platform(self._selected_platform, "flatten")
                if flatten_result.is_success and flatten_result.value:
                    for region in flatten_result.value:
                        # Check region and coordinates are valid before appending
                        if region and isinstance(region.coordinates, tuple) and len(region.coordinates) == 4:
                            coords_to_flash.append(region.coordinates)
                            self._logger.debug(
                                f"Added flatten region '{region.name}' coords for flash: {region.coordinates}")  # Use _logger
                        else:
                            self._logger.warning(
                                f"Skipping invalid flatten region data during flash test: {region}")  # Use _logger
                elif flatten_result.is_failure:
                    self._logger.warning(
                        f"Failed to get flatten region details during flash test: {flatten_result.error}")  # Use _logger
        except Exception as e:
            self._logger.error(f"Unexpected error getting flatten regions for flash: {e}", exc_info=True)  # Use _logger

        # 5. Check if any coordinates were actually gathered
        if not coords_to_flash:
            msg = f"No valid regions with coordinates found for {self._selected_platform} to flash."
            self.status_message_changed.emit(msg, "ERROR")
            self.activity_log_appended.emit(f"Flash test failed: {msg}", "ERROR")
            self._logger.error(msg)  # Use _logger
            return

        # 6. Call the SINGLE flash service method with the LIST of coordinates
        self.status_message_changed.emit(f"Flashing {len(coords_to_flash)} region(s)...", "INFO")
        # --- Ensure this is the correct method name in your IFlashService/QtFlashService ---
        flash_result = self._flash_service.flash_regions(coords_to_flash)
        # --- End method call ---

        # 7. Handle the result of *starting* the flash task
        if flash_result.is_success:
            msg = f"Flash test initiated successfully for {len(coords_to_flash)} region(s)."
            # Optional: Status bar message might be too brief, rely on logs/visual flash
            # self.status_message_changed.emit(msg, "INFO")
            self.activity_log_appended.emit(msg, "INFO")
            self._logger.info(msg)  # Use _logger
        else:
            msg = f"Failed to start flash test task: {flash_result.error}"
            self.status_message_changed.emit(msg, "ERROR")
            self.activity_log_appended.emit(msg, "ERROR")
            self._logger.error(msg)  # Use _logger

    # --- Private Helper / Update Methods ---

    @Slot(str)
    def _handle_platform_selection_change(self, platform: str):
        """Connected to PlatformSelectionService signal."""
        self._logger.debug(f"DashboardViewModel received platform change: {platform}")
        self._update_state_for_platform(platform)

    def _update_state_for_platform(self, platform: str):
        """Updates the ViewModel's state based on the selected platform."""
        self._logger.info(f"DashboardViewModel._update_state_for_platform: Updating for '{platform or 'None'}'")
        self._selected_platform = platform
        self.selected_platform_name_changed.emit(platform or "None Selected")

        if not platform:
            self._logger.debug("Platform is None. Resetting state and calling _update_prerequisite_statuses(None)")
            # Reset prerequisite status display
            keys = ["monitor_region", "ct_path", "ct_block_name", "ct_verified", "flatten_regions", "ocr_profile"]
            for key in keys:
                self.prerequisite_status_updated.emit(key, "Select Platform", "info", False)

            # Reset internal flags and other relevant state
            self._monitor_region_defined = False
            self._flatten_regions_defined = False
            self._pnl_format_display = "N/A"
            self.pnl_format_display_changed.emit(self._pnl_format_display)
            # Update button states for 'no platform' state
            self._update_button_states()
            return  # Exit early

        # --- Platform is valid, proceed with loading ---

        # 1. Check region status FIRST to update internal flags
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

        # 2. Get P&L Format Display
        try:
            profile_res = self._profile_service.get_profile(platform)
            if profile_res.is_success:
                patterns = profile_res.value.numeric_patterns
                # Check against default patterns (ensure _get_default_patterns_for_platform is accessible or reimplement check)
                try:
                    # Assuming ProfileService instance has this helper or accessing directly
                    # If ProfileService doesn't expose it, you might need a simple check here
                    default_patterns = self._profile_service._get_default_patterns_for_platform(
                        platform)  # Or None if method is protected
                    is_default = (patterns == default_patterns) if default_patterns else False  # Basic check
                except AttributeError:
                    self._logger.warning("Cannot access default patterns method directly, doing basic check.")
                    # Simplified check if direct access isn't possible
                    is_default = patterns is None or len(patterns) == 4  # A guess

                if is_default:
                    self._pnl_format_display = "Default"
                elif patterns and "negative" in patterns:
                    self._pnl_format_display = "ParensNeg ()"
                elif patterns and "negative_dash" in patterns:
                    self._pnl_format_display = "DashNeg -"
                elif patterns and "dollar" in patterns:
                    self._pnl_format_display = "Currency $"
                elif patterns and "regular" in patterns:
                    self._pnl_format_display = "Number +/-"
                else:
                    self._pnl_format_display = "Custom/None" if patterns else "Not Set"
            else:
                self._pnl_format_display = "Error"
                self._logger.warning(
                    f"Could not load profile for {platform} to determine P&L format: {profile_res.error}")
            self.pnl_format_display_changed.emit(self._pnl_format_display)
        except Exception as e:
            self._logger.error(f"Error getting PnL format display: {e}", exc_info=True)
            self._pnl_format_display = "Error"
            self.pnl_format_display_changed.emit(self._pnl_format_display)

        # 3. Update Button States (uses flags set in step 1)
        self._update_button_states()

        # 4. Update Prerequisite Status Display
        self._logger.debug(f"Calling _update_prerequisite_statuses('{platform}')...")
        self._update_prerequisite_statuses(platform)

    def _update_button_states(self):
        """Updates the internal state and emits signals for button enablement."""  # Modified docstring
        # Calculate states
        self._can_start = (  # Store result
                not self._is_monitoring_globally_active and
                bool(self._selected_platform) and
                self._monitor_region_defined
        )
        self._can_stop = self._is_monitoring_globally_active  # Store result
        self._can_test_flash = bool(self._selected_platform) and (
                    self._monitor_region_defined or self._flatten_regions_defined)  # Store result

        # Emit signals using stored state
        self.can_start_monitoring_changed.emit(self._can_start)
        self.can_stop_monitoring_changed.emit(self._can_stop)
        self.can_test_flash_changed.emit(self._can_test_flash)

    @Slot()
    def refresh_ui_signals(self):
        """Emits all signals reflecting the current state for initial UI sync."""
        self._logger.debug(f"DashboardViewModel Refreshing UI signals for {self._selected_platform or 'None'}")

        # --- Emit standard state signals ---
        self.current_pnl_text_changed.emit(self._current_pnl_text)
        self.monitoring_status_text_changed.emit(self._monitoring_status_text)
        self.can_start_monitoring_changed.emit(self._can_start)
        self.can_stop_monitoring_changed.emit(self._can_stop)
        self.can_test_flash_changed.emit(self._can_test_flash)
        self.recent_alerts_updated.emit(self._recent_alerts.copy())  # Emit copy
        self.selected_platform_name_changed.emit(self._selected_platform or "None Selected")
        self.pnl_format_display_changed.emit(self._pnl_format_display)

        # --- Explicitly trigger prerequisite status calculation and emission ---
        # Call the helper method that contains the logic and emit calls
        self._logger.debug("Refresh UI: Triggering prerequisite status update...")
        self._update_prerequisite_statuses(self._selected_platform)
        # --- END explicit trigger ---

        self._update_prerequisite_completion_badge()

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
        """Callback for when MonitoringService completes a check."""
        # Note: This might not be strictly needed if the service only calls
        # on_threshold_exceeded or on_error. But if it does provide results
        # periodically, we can update the P&L display here.
        self._logger.debug(f"Monitoring Result Received: Min Value {result.minimum_value}")
        self._last_monitor_result = result
        self._current_pnl_text = f"${result.minimum_value:,.2f}"
        self.current_pnl_text_changed.emit(self._current_pnl_text)
        # TODO: Update P&L history for graph if implementing
        # self.pnl_history_updated.emit(...)

    def _handle_threshold_exceeded(self, result: MonitoringResult):
        """Callback for when MonitoringService detects threshold breach."""
        active_monitoring_platform = self._monitoring_platform

        self._logger.error(
            f"DashboardViewModel: THRESHOLD EXCEEDED! Value: {result.minimum_value}, Platform: {active_monitoring_platform}")

        # --- End History Session for Lockout ---
        session_id_to_end = self._current_session_id
        final_screenshot_path_on_breach = result.screenshot_path

        if session_id_to_end:
            try:
                self._history_service.end_session(
                    session_id=session_id_to_end,
                    final_pnl=result.minimum_value,
                    lockout_triggered=True,
                    final_screenshot_path=final_screenshot_path_on_breach
                )
                self._logger.info(f"History session {session_id_to_end} ended due to threshold exceeded.")
            except Exception as e_hist_end:
                self._logger.error(
                    f"Failed to properly end history session {session_id_to_end} on threshold exceeded: {e_hist_end}",
                    exc_info=True)
            self._current_session_id = None
        else:
            self._logger.error(
                "Threshold exceeded callback received, but no active session ID was tracked in ViewModel!")
        # --- END End History Session ---

        # --- Update internal state and UI signals AFTER ending history session ---
        self._is_monitoring_globally_active = False
        self._monitoring_platform = None  # Clear this AFTER using it to get active_monitoring_platform
        self._current_pnl_text = f"LOCKOUT (${result.minimum_value:,.2f})"
        self.current_pnl_text_changed.emit(self._current_pnl_text)
        self._last_monitor_result = None

        # Add to UI alerts list
        timestamp = time.strftime("%H:%M:%S")
        alert_msg = f"{timestamp}: LOCKOUT TRIGGERED! P&L: ${result.minimum_value:.2f}"
        self._recent_alerts.append(alert_msg)
        if len(self._recent_alerts) > 5: self._recent_alerts = self._recent_alerts[-5:]
        self.recent_alerts_updated.emit(self._recent_alerts.copy())

        self.activity_log_appended.emit(
            f"THRESHOLD EXCEEDED! Detected: ${result.minimum_value:.2f}. Initiating lockout for {active_monitoring_platform}.",
            "ERROR")  # Use original variable
        self.status_message_changed.emit("Lockout triggered!", "ERROR")
        self._update_button_states()


        # --- Trigger automatic lockout ---
        if active_monitoring_platform:  # Use original variable
            self._logger.info(f"Threshold exceeded for {active_monitoring_platform}. Triggering automatic lockout.")
            self.activity_log_appended.emit(
                f"Initiating automatic lockout sequence for {active_monitoring_platform}...", "INFO")

            duration_res = self._config_repo.get_platform_lockout_duration(active_monitoring_platform)
            if duration_res.is_failure:
                self._logger.error(
                    f"Could not get lockout duration for {active_monitoring_platform}: {duration_res.error}")
                self.activity_log_appended.emit(f"LOCKOUT FAILED: Could not get duration.", "ERROR")
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

            flatten_positions_for_service = []
            for region in flatten_res.value:
                x, y, w, h = region.coordinates
                flatten_positions_for_service.append({"coords": (x, y, x + w, y + h)})

            fullscreen_enabled = self._config_repo.get_global_setting("fullscreen_overlay", True)

            lockout_start_res = self._lockout_service.perform_lockout(
                platform=active_monitoring_platform,
                flatten_positions=flatten_positions_for_service,
                lockout_duration=duration,
                fullscreen=fullscreen_enabled,
                on_status_update=self._handle_monitoring_status_update
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

    def _handle_monitoring_error(self, error_msg: str):
        """Callback for errors reported by MonitoringService."""
        self._logger.error(f"Monitoring Service Error: {error_msg}")
        self._logger.critical(f"!!!! _handle_monitoring_error TRIGGERED: {error_msg} !!!!")  # ADD THIS
        # Update state to reflect monitoring likely stopped due to error
        self._is_monitoring_globally_active = False
        stopped_platform = self._monitoring_platform
        self._monitoring_platform = None
        self._current_pnl_text = "ERROR" # Update P&L display
        self.current_pnl_text_changed.emit(self._current_pnl_text)

        # --- ADD End History Session ---
        session_id_to_end = self._current_session_id
        if session_id_to_end:
            last_pnl = 0.0  # Placeholder - ideally get from last recorded history point?
            if self._last_monitor_result:  # Use the VM's tracking if available
                last_pnl = self._last_monitor_result.minimum_value

            try:
                self._history_service.end_session(
                    session_id=session_id_to_end,
                    final_pnl=last_pnl,
                    lockout_triggered=False,  # Error, not lockout
                    final_screenshot_path=None
                )
            except Exception as e_hist_end:
                self._logger.error(f"Failed to properly end history session {session_id_to_end} on error: {e_hist_end}",
                                   exc_info=True)
            self._current_session_id = None  # Clear stored session ID
        else:
            self._logger.error("Monitoring error occurred but no active session ID found in ViewModel!")
        # --- END End History Session ---

        # Add alert
        timestamp = time.strftime("%H:%M:%S")
        alert_msg = f"{timestamp}: Monitoring Error: {error_msg}"
        self._recent_alerts.append(alert_msg)
        if len(self._recent_alerts) > 5: self._recent_alerts = self._recent_alerts[-5:]
        self.recent_alerts_updated.emit(self._recent_alerts.copy())

        # Log and update status
        self.activity_log_appended.emit(f"Monitoring stopped due to error: {error_msg}", "ERROR")
        self.status_message_changed.emit(f"Monitoring error: {error_msg}", "ERROR")
        self._update_button_states()

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


    # --- Optional: Periodic Status Check (If needed) ---
    # def _check_monitoring_status(self):
    #     """Periodically check the status from the monitoring service."""
    #     is_active = self._monitoring_service.is_monitoring()
    #     if is_active != self._is_monitoring_globally_active:
    #         self._logger.warning("Monitoring state mismatch detected, synchronizing...")
    #         self._is_monitoring_globally_active = is_active
    #         # If monitoring stopped unexpectedly, figure out which platform it was (might need state in MonitoringService)
    #         if not is_active:
    #             self._monitoring_platform = None
    #             self._current_pnl_text = "N/A"
    #             self.current_pnl_text_changed.emit(self._current_pnl_text)
    #         # Update UI state
    #         self._update_button_states()

    # --- NEW Slot to handle theme refresh requests ---
    @Slot()
    def on_theme_refresh_requested(self):
        self._logger.info("DashboardViewModel: Theme refresh requested. Re-evaluating UI states.")
        # Re-emitting all signals will re-trigger view updates,
        # including prerequisite rows which might have theme-dependent colors.
        self.refresh_ui_signals()
