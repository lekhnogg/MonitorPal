# src/presentation/view_models/dashboard_view_model.py

import time
from typing import List, Optional, Dict, Any

# --- Qt Imports ---
from PySide6.QtCore import QObject, Signal, Slot, QTimer

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
    monitoring_details_text_changed = Signal(str) # e.g., "Threshold: X | Duration: Y | ..."

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
            self.status_message_changed.emit("No platform selected.", "ERROR")
            self._logger.warning("Start monitoring requested but no platform selected.")
            return
        if self._is_monitoring_globally_active:
            self.status_message_changed.emit(f"Monitoring is already active for {self._monitoring_platform}.", "WARNING")
            self._logger.warning(f"Start monitoring requested for {self._selected_platform}, but already active for {self._monitoring_platform}.")
            return

        self._logger.info(f"Attempting to start monitoring for platform: {self._selected_platform}")
        self.status_message_changed.emit(f"Starting monitoring for {self._selected_platform}...", "INFO")
        self.activity_log_appended.emit(f"Starting monitoring for {self._selected_platform}...", "INFO")


        # --- Call the monitoring service ---
        # Fetch necessary details (could also be cached in VM state)
        threshold = self._config_repo.get_stop_loss_threshold()
        interval = self._config_repo.get_global_setting("monitor_interval_seconds", 2.0) # Example: Get interval from config

        start_result = self._monitoring_service.start_monitoring(
            platform=self._selected_platform,
            threshold=threshold,
            interval_seconds=interval, # Pass interval
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
            self._update_status_display() # Update status text display
        else:
            self._logger.error(f"Failed to start monitoring for {self._selected_platform}: {start_result.error}")
            self.status_message_changed.emit(f"Failed to start monitoring: {start_result.error}", "ERROR")
            self.activity_log_appended.emit(f"Failed to start monitoring: {start_result.error}", "ERROR")
            # Ensure state reflects failure
            self._is_monitoring_globally_active = False
            self._monitoring_platform = None
            self._update_button_states()
            self._update_status_display()


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
        self._update_status_display()


    @Slot()
    def test_flash_regions(self):
        """Flashes all defined regions for the current platform."""
        if not self._selected_platform:
            self.status_message_changed.emit("No platform selected to test flash.", "ERROR")
            return

        if not self._monitor_region_defined and not self._flatten_regions_defined:
             self.status_message_changed.emit(f"No regions defined for {self._selected_platform} to flash.", "ERROR")
             return

        self._logger.info(f"Testing flash for all regions on {self._selected_platform}")
        self.status_message_changed.emit(f"Flashing regions for {self._selected_platform}...", "INFO")
        self.activity_log_appended.emit(f"Initiating flash test for {self._selected_platform}...", "INFO")

        regions_to_flash = []
        # Get Monitor Region
        if self._monitor_region_defined:
            monitor_result = self._region_service.get_monitor_region(self._selected_platform)
            if monitor_result.is_success and monitor_result.value:
                 regions_to_flash.append({"type": "monitor", "name": monitor_result.value.name})

        # Get Flatten Regions
        if self._flatten_regions_defined:
             flatten_result = self._region_service.get_regions_by_platform(self._selected_platform, "flatten")
             if flatten_result.is_success and flatten_result.value:
                  for region in flatten_result.value:
                       regions_to_flash.append({"type": "flatten", "name": region.name})

        if not regions_to_flash:
             self.status_message_changed.emit("Could not retrieve defined regions to flash.", "ERROR")
             self.activity_log_appended.emit("Error retrieving regions for flash test.", "ERROR")
             return

        # Call flash service for each region
        success_count = 0
        fail_count = 0
        for region_info in regions_to_flash:
             flash_result = self._flash_service.flash_region(
                  self._selected_platform,
                  region_info["type"],
                  region_info["name"]
             )
             if flash_result.is_success:
                  success_count += 1
             else:
                  fail_count += 1
                  self.activity_log_appended.emit(f"Failed to flash {region_info['type']} region '{region_info['name']}': {flash_result.error}", "ERROR")
            # Add a small delay between flashes if flashing multiple regions
             if len(regions_to_flash) > 1:
                time.sleep(0.8) # Adjust as needed

        msg = f"Flash test initiated. Success: {success_count}, Failed: {fail_count}."
        level = "INFO" if fail_count == 0 else "WARNING"
        self.status_message_changed.emit(msg, level)
        self.activity_log_appended.emit(msg, level)

    # --- Private Helper / Update Methods ---

    @Slot(str)
    def _handle_platform_selection_change(self, platform: str):
        """Connected to PlatformSelectionService signal."""
        self._logger.debug(f"DashboardViewModel received platform change: {platform}")
        self._update_state_for_platform(platform)

    def _update_state_for_platform(self, platform: str):
        """Updates the ViewModel's state based on the selected platform."""
        self._logger.debug(f"Updating DashboardViewModel state for platform: {platform}")
        self._selected_platform = platform
        self.selected_platform_name_changed.emit(platform or "None Selected")

        if not platform:
            # Reset state if no platform selected
            self._monitor_region_defined = False
            self._flatten_regions_defined = False
            self._pnl_format_display = "N/A"
            self.pnl_format_display_changed.emit(self._pnl_format_display)
            # Do not change monitoring status here, it's independent of selection
            self._update_button_states()
            self._update_status_display() # Update display text
            return

        # --- Check if regions are defined for this platform ---
        monitor_region_res = self._region_service.get_monitor_region(platform)
        self._monitor_region_defined = monitor_region_res.is_success and monitor_region_res.value is not None

        flatten_regions_res = self._region_service.get_regions_by_platform(platform, "flatten")
        self._flatten_regions_defined = flatten_regions_res.is_success and bool(flatten_regions_res.value)

        # --- Get P&L Format Display ---
        profile_res = self._profile_service.get_profile(platform)
        if profile_res.is_success:
            patterns = profile_res.value.numeric_patterns
            # Use logic similar to monitorPal_test._update_summary_display
            default_patterns = PlatformProfile("dummy").numeric_patterns
            is_default = (patterns == default_patterns)

            if is_default: self._pnl_format_display = "Default"
            elif "negative" in patterns: self._pnl_format_display = "ParensNeg ()"
            elif "negative_dash" in patterns: self._pnl_format_display = "DashNeg -"
            elif "dollar" in patterns: self._pnl_format_display = "Currency $"
            elif "regular" in patterns: self._pnl_format_display = "Number +/-"
            else: self._pnl_format_display = "Custom"
        else:
             self._pnl_format_display = "Error"
             self._logger.warning(f"Could not load profile for {platform} to determine P&L format: {profile_res.error}")
        self.pnl_format_display_changed.emit(self._pnl_format_display)

        # --- Update UI State ---
        self._update_button_states()
        self._update_status_display() # Update status based on potentially new threshold/duration etc.

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

    def _update_status_display(self):
        """Updates the monitoring status and details text signals."""
        if self._is_monitoring_globally_active:
            self._monitoring_status_text = f"Active"
            # Add duration if available (needs tracking in MonitoringService or here)
            # status_text += f" ({duration_str})" # Placeholder
        elif self._monitoring_platform and self._monitoring_platform != self._selected_platform:
            self._monitoring_status_text = f"Busy ({self._monitoring_platform})"
        else:
            self._monitoring_status_text = "Inactive"

        self.monitoring_status_text_changed.emit(self._monitoring_status_text)

        # Update details based on the SELECTED platform's config
        if self._selected_platform:
            threshold = self._config_repo.get_stop_loss_threshold()
            duration = self._config_repo.get_lockout_duration()
            region_info = "N/A"
            region_coords = ""
            monitor_region_res = self._region_service.get_monitor_region(self._selected_platform)
            if monitor_region_res.is_success and monitor_region_res.value:
                 region_info = monitor_region_res.value.name
                 coords = monitor_region_res.value.coordinates
                 region_coords = f"({coords[0]},{coords[1]},{coords[2]},{coords[3]})"
            elif not self._monitor_region_defined:
                 region_info = "Not Defined"

            self._monitoring_details_text = (
                f"Threshold: ${threshold:,.2f} | Duration: {duration} min | "
                f"Region: {region_info} {region_coords}"
            )
        else:
            self._monitoring_details_text = "Select a platform"

        self.monitoring_details_text_changed.emit(self._monitoring_details_text)

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
        self._update_status_display()

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
        self._update_status_display()

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
    #         self._update_status_display()