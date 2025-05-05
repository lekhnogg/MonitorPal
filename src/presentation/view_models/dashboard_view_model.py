# src/presentation/view_models/dashboard_view_model.py

import time
from typing import List, Optional, Dict, Any, Tuple

# --- Qt Imports ---
from PySide6.QtCore import QObject, Signal, Slot, QTimer

from src.domain.services.i_cold_turkey_service import IColdTurkeyService
# --- Application Imports ---
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

    # --- NEW: Prerequisite Status Signals ---
    # Payload: (prerequisite_key: str, status_text: str, status_state: str, show_action: bool)
    # status_state can be: "ok", "warning", "error", "missing", "pending", "info"
    prerequisite_status_updated = Signal(str, str, str, bool)
    # --- END NEW ---

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
                 lockout_service: ILockoutService, # Assuming manual flatten uses this
                 flash_service: IFlashService,
                 platform_selection_service: IPlatformSelectionService,
                 config_repo: IConfigRepository, # Needed for threshold/duration display
                 region_service: IRegionService, # Needed for region check/flash
                 profile_service: IProfileService, # Needed for P&L format display
                 cold_turkey_service: IColdTurkeyService,
                 parent: Optional[QObject] = None):
        """
        Initialize the DashboardViewModel.

        Args:
            logger: Logger service instance.
            monitoring_service: Monitoring service instance.
            lockout_service: Lockout service instance.
            flash_service: Flash service instance.
            platform_selection_service: Platform selection service instance.
            config_repo: Configuration repository instance.
            region_service: Region service instance.
            profile_service: Profile service instance.
            parent: Optional parent QObject.
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
        self._cold_turkey_service = cold_turkey_service

        # --- Internal State Attributes ---
        self._selected_platform: Optional[str] = None
        self._is_monitoring_globally_active: bool = False # Is *any* monitoring active?
        self._monitoring_platform: Optional[str] = None # Which platform *is* being monitored?
        self._current_pnl_text: str = "N/A"
        self._monitoring_status_text: str = "Inactive"
        self._monitoring_details_text: str = "Load platform..."
        self._can_start: bool = False
        self._can_stop: bool = False
        self._can_test_flash: bool = False
        self._recent_alerts: List[str] = []
        self._pnl_format_display: str = "N/A"
        self._monitor_region_defined: bool = False
        self._flatten_regions_defined: bool = False
        self._last_monitor_result: Optional[MonitoringResult] = None


        # --- Initialization ---
        self._logger.debug("Initializing DashboardViewModel...")
        # Register listener for platform changes
        self._platform_selection_service.register_platform_change_listener(
            self._handle_platform_selection_change
        )
        # Load initial data for the currently selected platform
        initial_platform = self._platform_selection_service.get_current_platform()
        self._update_state_for_platform(initial_platform)

        # Timer to periodically update monitoring status if MonitoringService doesn't push updates
        # self._status_update_timer = QTimer(self)
        # self._status_update_timer.timeout.connect(self._check_monitoring_status)
        # self._status_update_timer.start(2000) # Check every 2 seconds

        self._logger.debug("DashboardViewModel initialized.")


    # --- Command Slots (Called by the View) ---

    @Slot()
    def start_monitoring(self):
        """Starts monitoring for the currently selected platform."""
        if not self._selected_platform:
            self.status_message_changed.emit("No platform selected.", "ERROR");
            return
        if self._is_monitoring_globally_active:
            self.status_message_changed.emit(f"Monitoring already active for {self._monitoring_platform}.", "WARNING");
            return

        self.status_message_changed.emit(f"Starting monitoring for {self._selected_platform}...", "INFO")
        self.activity_log_appended.emit(f"Starting monitoring for {self._selected_platform}...", "INFO")

        # --- Use NEW platform-specific getter ---
        threshold_res = self._config_repo.get_platform_stop_loss_threshold(self._selected_platform)
        if threshold_res.is_failure:
            # Cannot start monitoring without a threshold
            self.status_message_changed.emit(
                f"Error getting threshold for {self._selected_platform}: {threshold_res.error}", "ERROR")
            self.activity_log_appended.emit(
                f"Error getting threshold for {self._selected_platform}: {threshold_res.error}", "ERROR")
            return
        platform_threshold = threshold_res.value
        # --- END NEW ---

        # Get global interval
        interval = self._config_repo.get_global_setting("monitor_interval_seconds", 2.0)

        start_result = self._monitoring_service.start_monitoring(
            platform=self._selected_platform,
            threshold=platform_threshold,  # <<< Pass platform-specific threshold
            interval_seconds=interval,
            on_status_update=self._handle_monitoring_status_update,
            on_threshold_exceeded=self._handle_threshold_exceeded,
            on_error=self._handle_monitoring_error
        )

        # --- Update State Based on Result ---
        if start_result.is_success:
            self._logger.info(f"Monitoring started successfully for {self._selected_platform}.")
            # Update internal state ONLY after success
            self._is_monitoring_globally_active = True
            self._monitoring_platform = self._selected_platform # Track which platform is monitored
            self.status_message_changed.emit(f"Monitoring active for {self._selected_platform}.", "INFO")
            self._update_button_states() # Update button enable states
        else:
            self._logger.error(f"Failed to start monitoring for {self._selected_platform}: {start_result.error}")
            self.status_message_changed.emit(f"Failed to start monitoring: {start_result.error}", "ERROR")
            self.activity_log_appended.emit(f"Failed to start monitoring: {start_result.error}", "ERROR")
            # Ensure state reflects failure
            self._is_monitoring_globally_active = False
            self._monitoring_platform = None
            self._update_button_states()


    @Slot()
    def stop_monitoring(self):
        """Stops any active monitoring."""
        if not self._is_monitoring_globally_active:
            self.status_message_changed.emit("Monitoring is not active.", "WARNING")
            self._logger.warning("Stop monitoring requested but not active.")
            return

        self._logger.info(f"Attempting to stop monitoring (was active for {self._monitoring_platform}).")
        self.status_message_changed.emit("Stopping monitoring...", "INFO")
        self.activity_log_appended.emit("Stopping monitoring...", "INFO")

        stop_result = self._monitoring_service.stop_monitoring()

        # Update state regardless of result (to reflect intent)
        self._is_monitoring_globally_active = False
        stopped_platform = self._monitoring_platform
        self._monitoring_platform = None
        self._current_pnl_text = "N/A" # Reset P&L display
        self.current_pnl_text_changed.emit(self._current_pnl_text)

        if stop_result.is_success:
            self._logger.info(f"Monitoring stopped successfully for {stopped_platform}.")
            self.status_message_changed.emit("Monitoring stopped.", "INFO")
            self.activity_log_appended.emit("Monitoring stopped.", "SUCCESS")
        else:
            self._logger.error(f"Failed to stop monitoring gracefully: {stop_result.error}")
            self.status_message_changed.emit(f"Monitoring stopped (with error: {stop_result.error}).", "WARNING")
            self.activity_log_appended.emit(f"Error stopping monitoring: {stop_result.error}", "ERROR")

        # Update UI state
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

        # No need to re-emit status_message_changed unless there's an initial one

    # --- Callback Handlers for Monitoring Service ---

    def _handle_monitoring_status_update(self, message: str, level: str):
        """Callback for status updates from MonitoringService."""
        self._logger.debug(f"Monitoring Status Update: [{level}] {message}")
        self.activity_log_appended.emit(message, level)

        # Add to recent alerts if it's a warning/error
        if level.upper() in ["WARNING", "ERROR"]:
             timestamp = time.strftime("%H:%M:%S")
             alert_msg = f"{timestamp}: {message}"
             self._recent_alerts.append(alert_msg)
             # Keep only last 5 alerts
             if len(self._recent_alerts) > 5:
                  self._recent_alerts = self._recent_alerts[-5:]
             self.recent_alerts_updated.emit(self._recent_alerts.copy()) # Emit copy

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
        active_monitoring_platform = self._monitoring_platform # Store before clearing state

        self._logger.error(f"THRESHOLD EXCEEDED reported by MonitoringService! Value: {result.minimum_value}, Platform: {active_monitoring_platform}")

        # --- Update internal state and UI signals ---
        self._is_monitoring_globally_active = False
        self._monitoring_platform = None # Clear which platform IS monitored
        self._current_pnl_text = f"LOCKOUT (${result.minimum_value:,.2f})"
        self.current_pnl_text_changed.emit(self._current_pnl_text)

        # Add alert
        timestamp = time.strftime("%H:%M:%S")
        alert_msg = f"{timestamp}: LOCKOUT TRIGGERED! P&L: ${result.minimum_value:.2f}"
        self._recent_alerts.append(alert_msg)
        if len(self._recent_alerts) > 5: self._recent_alerts = self._recent_alerts[-5:]
        self.recent_alerts_updated.emit(self._recent_alerts.copy())

        # Log and update status bar
        self.activity_log_appended.emit(f"THRESHOLD EXCEEDED! Detected: ${result.minimum_value:.2f}. Initiating lockout for {active_monitoring_platform}.", "ERROR")
        self.status_message_changed.emit("Lockout triggered!", "ERROR")
        self._update_button_states() # Reflect inactive monitoring state


        # --- Trigger automatic lockout ---
        if active_monitoring_platform: # Ensure we know which platform triggered it
            self._logger.info(f"Threshold exceeded for {active_monitoring_platform}. Triggering automatic lockout.")
            self.activity_log_appended.emit(f"Initiating automatic lockout sequence for {active_monitoring_platform}...", "INFO")
            # Fetch necessary data
            duration = self._config_repo.get_lockout_duration()
            flatten_res = self._region_service.get_regions_by_platform(active_monitoring_platform, "flatten")

            if flatten_res.is_failure or not flatten_res.value:
                err = flatten_res.error if flatten_res.is_failure else "No flatten regions found"
                self._logger.error(f"Cannot perform automatic lockout: Failed to get flatten regions: {err}")
                self.activity_log_appended.emit(f"LOCKOUT FAILED: Could not get flatten regions: {err}", "ERROR")
                self.status_message_changed.emit(f"Lockout Failed: Missing flatten regions for {active_monitoring_platform}", "ERROR")
                return # Stop if flatten regions are missing

            # Format flatten positions
            flatten_positions_for_service = []
            for region in flatten_res.value:
                x, y, w, h = region.coordinates
                flatten_positions_for_service.append({"coords": (x, y, x + w, y + h)})

            # Check fullscreen setting (example - adjust key if different)
            fullscreen_enabled = self._config_repo.get_global_setting("fullscreen_overlay", True)

            # --- *** THE CRUCIAL CALL *** ---
            # Call lockout service to perform the actual lockout
            lockout_start_res = self._lockout_service.perform_lockout(
                platform=active_monitoring_platform,
                flatten_positions=flatten_positions_for_service,
                lockout_duration=duration,
                fullscreen=fullscreen_enabled,
                # Pass the status update callback so lockout steps are logged in UI
                on_status_update=self._handle_monitoring_status_update
            )
            # --- *** END CRUCIAL CALL *** ---

            if lockout_start_res.is_failure:
                self._logger.error(f"Failed to initiate automatic lockout task: {lockout_start_res.error}")
                self.activity_log_appended.emit(f"LOCKOUT START FAILED: {lockout_start_res.error}", "ERROR")
                self.status_message_changed.emit(f"Lockout Start Failed: {lockout_start_res.error}", "ERROR")
            else:
                self._logger.info(f"Automatic lockout sequence task initiated successfully for {active_monitoring_platform}.")
                self.activity_log_appended.emit(f"Automatic lockout sequence initiated for {active_monitoring_platform}.", "INFO")
                # Status bar already shows "Lockout triggered!"
        else:
             # This case should be rare if monitoring was active
             self._logger.error("Threshold exceeded but could not determine which platform was being monitored. Lockout not triggered.")
             self.activity_log_appended.emit("Threshold exceeded but monitoring platform unknown. Lockout skipped.", "ERROR")

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
        """Checks prerequisites for the given platform and emits status signals."""
        if not platform:
            # Emit "Select Platform" status for all prerequisites if none is selected
            keys = ["monitor_region", "ct_path", "ct_block_name", "ct_verified", "flatten_regions", "ocr_profile"]
            for key in keys:
                self.prerequisite_status_updated.emit(key, "Select Platform", "info", False)
            return

        self._logger.debug(f"Dashboard VM: Updating prerequisite checks for {platform}")

        # 1. P&L Monitor Region
        region_res = self._region_service.get_monitor_region(platform)
        region_defined = region_res.is_success and region_res.value is not None
        if region_defined:
            self.prerequisite_status_updated.emit("monitor_region", "P&L Region Defined", "ok", False)
        else:
            self.prerequisite_status_updated.emit("monitor_region", "P&L Region Not Defined", "error",
                                                  True)  # Show button

        # 2. Cold Turkey Path (Global Check)
        # Use the service method that already checks existence
        ct_path_ok = self._cold_turkey_service.is_blocker_path_configured()
        if ct_path_ok:
            self.prerequisite_status_updated.emit("ct_path", "Cold Turkey Path Set", "ok", False)
        else:
            ct_path = self._config_repo.get_cold_turkey_path()  # Get path to see *why* it failed
            status_text = "Cold Turkey Path Not Set" if not ct_path else "Cold Turkey Path Invalid/Missing"
            self.prerequisite_status_updated.emit("ct_path", status_text, "error", True)  # Show button

        # 3. CT Block Name (Platform Specific)
        settings = self._config_repo.get_platform_settings(platform)  # Reuse settings if needed or fetch again
        block_name_set = bool(settings.get("cold_turkey_block_name"))
        if block_name_set:
            self.prerequisite_status_updated.emit("ct_block_name", "CT Block Name Set", "ok", False)
        else:
            self.prerequisite_status_updated.emit("ct_block_name", "CT Block Name Not Set", "error",
                                                  True)  # Show button

        # 4. CT Block Verification (Platform Specific)
        verified_block_res = self._config_repo.get_verified_block(platform)
        is_verified = verified_block_res.is_success and verified_block_res.value is not None
        if is_verified:
            verified_name = verified_block_res.value  # Get the actual verified name
            self.prerequisite_status_updated.emit("ct_verified", f"CT Block Verified ({verified_name})", "ok", False)
        else:
            # Only show action button if path and block name are set (prereqs for verification)
            can_verify_now = ct_path_ok and block_name_set
            self.prerequisite_status_updated.emit("ct_verified", "CT Block Not Verified", "error",
                                                  can_verify_now)  # Show button only if possible

        # 5. Flatten Regions (Bonus - Warning if missing)
        flatten_res = self._region_service.get_regions_by_platform(platform, "flatten")
        flatten_defined = flatten_res.is_success and bool(flatten_res.value)
        if flatten_defined:
            self.prerequisite_status_updated.emit("flatten_regions", "Flatten Regions Defined", "ok", False)
        else:
            self.prerequisite_status_updated.emit("flatten_regions", "Flatten Regions Missing", "warning",
                                                  True)  # Show button

        # 6. OCR Profile (Bonus - Warning if default)
        profile_res = self._profile_service.get_profile(platform)
        ocr_status = "N/A"
        ocr_state = "error"
        ocr_show_action = True
        if profile_res.is_success:
            # Add logic to check if it's default vs calibrated/saved if desired
            # For now, just check existence
            ocr_status = "OCR Profile Loaded"
            ocr_state = "ok"
            ocr_show_action = False  # Don't show action if loaded (can refine later)
        else:
            ocr_status = "OCR Profile Error/Missing"
            ocr_state = "error"
            ocr_show_action = False  # Cannot calibrate if profile missing

        self.prerequisite_status_updated.emit("ocr_profile", ocr_status, ocr_state, ocr_show_action)
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
