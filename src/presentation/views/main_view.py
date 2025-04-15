# src/presentation/views/main_view.py

import sys
from typing import Optional, Dict, Any  # <-- Added Dict

# --- Qt Imports ---
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QTabWidget, QStatusBar, QLabel,
    QComboBox, QToolBar, QSizePolicy # Ensure QSizePolicy is imported
)
from PySide6.QtCore import Slot, QSize, Qt # Ensure Qt is imported

# --- Application Imports ---
from src.domain.common.di_container import DIContainer
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_background_task_service import IBackgroundTaskService
from src.domain.services.i_platform_selection_service import IPlatformSelectionService
# Import necessary service interfaces for resolving dependencies
from src.domain.services.i_monitoring_service import IMonitoringService
from src.domain.services.i_lockout_service import ILockoutService
from src.domain.services.i_flash_service import IFlashService
from src.domain.services.i_config_repository_service import IConfigRepository
from src.domain.services.i_region_service import IRegionService
from src.domain.services.i_profile_service import IProfileService
from src.domain.services.i_cold_turkey_service import IColdTurkeyService
from src.domain.services.i_verification_service import IVerificationService
from src.domain.services.i_path_service import IPathService
from src.domain.services.i_ui_service import IUIService
from src.domain.services.i_ocr_service import IOcrService
from src.domain.services.i_ocr_analysis_service import IOcrAnalysisService
from src.domain.services.i_screenshot_service import IScreenshotService
# Import specific domain models needed for formatting logic if done here
from src.domain.models.platform_profile import PlatformProfile


# --- ViewModels ---
from src.presentation.view_models.dashboard_view_model import DashboardViewModel
from src.presentation.view_models.region_setup_view_model import RegionSetupViewModel
from src.presentation.view_models.settings_view_model import SettingsViewModel
from src.presentation.view_models.ocr_calibration_view_model import OcrCalibrationViewModel
from src.presentation.view_models.history_view_model import HistoryViewModel

# --- Views ---
from src.presentation.views.dashboard_view import DashboardView
from src.presentation.views.region_setup_view import RegionSetupView
from src.presentation.views.settings_view import SettingsView
from src.presentation.views.ocr_calibration_view import OcrCalibrationView
from src.presentation.views.history_view import HistoryView


class MainView(QMainWindow):
    """
    The main application window containing the tabbed interface for MonitorPal.
    """

    # --- Attributes for UI elements ---
    region_label: Optional[QLabel] = None
    threshold_label: Optional[QLabel] = None
    duration_label: Optional[QLabel] = None
    patterns_label: Optional[QLabel] = None
    platform_combo: Optional[QComboBox] = None
    tab_widget: Optional[QTabWidget] = None
    status_bar: Optional[QStatusBar] = None
    _status_label: Optional[QLabel] = None
    platform_toolbar: Optional[QToolBar] = None

    # --- Attributes for ViewModels ---
    dashboard_vm: Optional[DashboardViewModel] = None
    region_setup_vm: Optional[RegionSetupViewModel] = None
    settings_vm: Optional[SettingsViewModel] = None
    ocr_calibration_vm: Optional[OcrCalibrationViewModel] = None
    history_vm: Optional[HistoryViewModel] = None

    def __init__(self, container: DIContainer, parent: Optional[QWidget] = None):
        """ Initializes the MainView. """
        super().__init__(parent)
        self._container = container
        # Resolve services needed by MainView directly
        self._logger = self._container.resolve(ILoggerService)
        self._background_task_service = self._container.resolve(IBackgroundTaskService)
        self._platform_selection_service = self._container.resolve(IPlatformSelectionService)
        # Also resolve ProfileService if formatting patterns here
        self._profile_service = self._container.resolve(IProfileService) # Needed for pattern formatting Option B

        self._logger.info("Initializing MainView...")
        self._setup_ui() # Creates widgets AND instantiates VMs/Views
        self._connect_signals() # Connects signals AFTER VMs/Views exist
        self._load_initial_summary() # Populate summary labels initially
        self._logger.info("MainView initialized successfully.")


    def _setup_ui(self):
        """Creates and arranges the main UI elements."""
        self.setWindowTitle("MonitorPal")
        self.setMinimumSize(QSize(900, 700))
        self.resize(QSize(1100, 800))

        # --- Central Widget and Layout ---
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Platform Selector Toolbar (TOP) ---
        self.platform_toolbar = QToolBar("Platform Selection")
        self.platform_toolbar.setMovable(False)
        self.platform_toolbar.setFloatable(False)
        # Allow widgets in the toolbar to take up space
        self.platform_toolbar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.platform_toolbar)

        # --- Add Summary Labels to Toolbar ---
        self.platform_toolbar.addWidget(QLabel(" Region: "))
        self.region_label = QLabel("N/A")
        self.region_label.setStyleSheet("font-weight: bold; padding-right: 10px;") # Add padding
        self.platform_toolbar.addWidget(self.region_label)

        self.platform_toolbar.addSeparator()

        self.platform_toolbar.addWidget(QLabel(" Threshold: "))
        self.threshold_label = QLabel("N/A")
        self.threshold_label.setStyleSheet("font-weight: bold; padding-right: 10px;")
        self.platform_toolbar.addWidget(self.threshold_label)

        self.platform_toolbar.addSeparator()

        self.platform_toolbar.addWidget(QLabel(" Duration: "))
        self.duration_label = QLabel("N/A")
        self.duration_label.setStyleSheet("font-weight: bold; padding-right: 10px;")
        self.platform_toolbar.addWidget(self.duration_label)

        self.platform_toolbar.addSeparator()

        self.platform_toolbar.addWidget(QLabel(" Patterns: "))
        self.patterns_label = QLabel("N/A")
        self.patterns_label.setStyleSheet("font-weight: bold; padding-right: 10px;")
        self.patterns_label.setToolTip("Detected number format patterns (Default/Custom/etc.)")
        self.platform_toolbar.addWidget(self.patterns_label)
        # --- END Add Summary Labels ---

        # Add spacer to push dropdown to the right within the toolbar
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.platform_toolbar.addWidget(spacer)

        self.platform_toolbar.addWidget(QLabel(" Platform: "))

        # Create platform dropdown and add to toolbar
        self.platform_combo = QComboBox()
        self.platform_combo.setMinimumWidth(170)
        self.platform_toolbar.addWidget(self.platform_combo)

        # Populate initial platforms
        platforms = self._platform_selection_service.get_available_platforms()
        current = self._platform_selection_service.get_current_platform()
        self.platform_combo.blockSignals(True)
        self.platform_combo.addItems(platforms)
        if current and current in platforms:
            self.platform_combo.setCurrentText(current)
        elif platforms:
            self.platform_combo.setCurrentIndex(0)
            # Update service if we defaulted
            current = self.platform_combo.currentText()
            self._platform_selection_service.set_current_platform(current)
        self.platform_combo.blockSignals(False)
        self._logger.debug("Platform selector added to Toolbar.")


        # --- Tab Widget ---
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.North)
        self.tab_widget.setMovable(False)
        main_layout.addWidget(self.tab_widget) # Add AFTER toolbar

        # --- Status Bar ---
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self._status_label = QLabel("Ready")
        self.status_bar.addWidget(self._status_label)


        # --- Instantiate ViewModels ---
        self._logger.debug("Instantiating ViewModels...")
        try:
            # Store VM instances as attributes of MainView for signal connections
            self.dashboard_vm = DashboardViewModel(
                logger=self._logger,
                monitoring_service=self._container.resolve(IMonitoringService),
                lockout_service=self._container.resolve(ILockoutService),
                flash_service=self._container.resolve(IFlashService),
                platform_selection_service=self._platform_selection_service,
                config_repo=self._container.resolve(IConfigRepository),
                region_service=self._container.resolve(IRegionService),
                profile_service=self._profile_service, # Use already resolved one
            )
            self.region_setup_vm = RegionSetupViewModel(
                logger=self._logger,
                region_service=self._container.resolve(IRegionService),
                platform_selection_service=self._platform_selection_service,
                flash_service=self._container.resolve(IFlashService),
                ui_service=self._container.resolve(IUIService),
                screenshot_service=self._container.resolve(IScreenshotService),
            )
            self.settings_vm = SettingsViewModel(
                 logger=self._logger,
                 config_repo=self._container.resolve(IConfigRepository),
                 platform_selection_service=self._platform_selection_service,
                 cold_turkey_service=self._container.resolve(IColdTurkeyService),
                 verification_service=self._container.resolve(IVerificationService),
                 path_service=self._container.resolve(IPathService),
                 ui_service=self._container.resolve(IUIService),
            )
            self.ocr_calibration_vm = OcrCalibrationViewModel(
                 logger=self._logger,
                 profile_service=self._profile_service, # Use already resolved one
                 ocr_service=self._container.resolve(IOcrService),
                 ocr_analysis_service=self._container.resolve(IOcrAnalysisService),
                 region_service=self._container.resolve(IRegionService),
                 platform_selection_service=self._platform_selection_service,
                 thread_service=self._background_task_service,
                 screenshot_service=self._container.resolve(IScreenshotService),
                 ui_service=self._container.resolve(IUIService),
            )
            self.history_vm = HistoryViewModel(
                 logger=self._logger,
                 config_repo=self._container.resolve(IConfigRepository),
                 platform_selection_service=self._platform_selection_service,
            )
            self._logger.debug("ViewModels instantiated.")

        except Exception as e:
             self._logger.error(f"FATAL: Failed to instantiate ViewModels: {e}", exc_info=True)
             from PySide6.QtWidgets import QMessageBox
             QMessageBox.critical(self, "Initialization Error", f"Could not create essential application components:\n{e}")
             return


        # --- Instantiate Views and Add Tabs ---
        self._logger.debug("Instantiating Views and adding tabs...")
        try:
            # Pass the corresponding VM to each View's constructor
            dashboard_view = DashboardView(self.dashboard_vm, self)
            self.tab_widget.addTab(dashboard_view, "Dashboard")

            region_setup_view = RegionSetupView(self.region_setup_vm, self)
            self.tab_widget.addTab(region_setup_view, "Region Setup")

            settings_view = SettingsView(self.settings_vm, self)
            self.tab_widget.addTab(settings_view, "Settings")

            ocr_calibration_view = OcrCalibrationView(self.ocr_calibration_vm, self)
            self.tab_widget.addTab(ocr_calibration_view, "OCR Calibration")

            history_view = HistoryView(self.history_vm, self)
            self.tab_widget.addTab(history_view, "History")

            self._logger.debug("Views created and added as tabs.")

        except Exception as e:
             self._logger.error(f"FATAL: Failed to instantiate Views or add tabs: {e}", exc_info=True)
             from PySide6.QtWidgets import QMessageBox
             QMessageBox.critical(self, "Initialization Error", f"Could not create application UI sections:\n{e}")
             return


    def _connect_signals(self):
        """Connect signals for the MainView and summary updates."""
        if not self.platform_combo: # Guard against incomplete UI setup
            self._logger.error("Platform combo box not initialized before connecting signals.")
            return
        if not self.region_setup_vm or not self.settings_vm or not self.ocr_calibration_vm:
             self._logger.error("ViewModels not initialized before connecting signals.")
             return

        self._logger.debug("Connecting MainView signals...")
        # Connect platform selector combo box
        self.platform_combo.currentTextChanged.connect(self._handle_platform_selection_change)

        # Connect the platform service's notification signal back to update the combo
        self._platform_selection_service.register_platform_change_listener(self._update_platform_combo)

        # --- Connect ViewModel signals to update summary labels ---
        self.region_setup_vm.monitor_region_coords_text_changed.connect(self._update_region_label)
        self.settings_vm.stop_loss_threshold_changed.connect(self._update_threshold_label)
        self.settings_vm.lockout_duration_changed.connect(self._update_duration_label)
        # Connect to the signal emitting the pattern *dictionary* from OcrCalibrationViewModel
        self.ocr_calibration_vm.detected_patterns_changed.connect(self._update_patterns_label_from_dict)

        # Connect status messages from different VMs to the status bar
        self.dashboard_vm.status_message_changed.connect(self._show_status_message)
        self.region_setup_vm.status_message_changed.connect(self._show_status_message)
        self.settings_vm.status_message_changed.connect(self._show_status_message)
        self.ocr_calibration_vm.status_message_changed.connect(self._show_status_message)
        self.history_vm.status_message_changed.connect(self._show_status_message)


        self._logger.debug("MainView signals connected.")

    def _load_initial_summary(self):
         """Populates summary labels with initial values after VMs are created."""
         if not self.settings_vm or not self.region_setup_vm or not self.ocr_calibration_vm:
              self._logger.error("Cannot load initial summary, ViewModels not ready.")
              return

         self._logger.debug("Loading initial summary display...")
         # Get initial values directly from ViewModels or services
         current_platform = self._platform_selection_service.get_current_platform()

         # Threshold / Duration from Settings VM (or repo)
         self._update_threshold_label(self.settings_vm._threshold)
         self._update_duration_label(self.settings_vm._duration)

         # Region Coords from RegionSetup VM (it loads on init)
         # We need to access the loaded state within RegionSetupVM if possible,
         # or trigger its signal again, or fetch directly from service here.
         # Fetching directly for initial load might be simplest:
         if current_platform:
            region_res = self._container.resolve(IRegionService).get_monitor_region(current_platform)
            if region_res.is_success and region_res.value:
                 coords = region_res.value.coordinates
                 self._update_region_label(f"({coords[0]},{coords[1]},{coords[2]},{coords[3]})")
            else:
                 self._update_region_label("Not Defined")
         else:
            self._update_region_label("N/A")


         # Patterns from OcrCalibration VM state or Profile Service
         # Fetching directly from profile service for initial load:
         if current_platform:
            profile_res = self._profile_service.get_profile(current_platform)
            if profile_res.is_success:
                self._update_patterns_label_from_dict(profile_res.value.numeric_patterns)
            else:
                self._update_patterns_label_from_dict({}) # Empty dict if profile load fails
         else:
             self._update_patterns_label_from_dict({}) # Empty dict if no platform


    # --- Slots for updating summary labels ---
    @Slot(str)
    def _update_region_label(self, coords_text: str):
        if self.region_label: # Check if label exists
            self.region_label.setText(coords_text if coords_text else "N/A")

    @Slot(float)
    def _update_threshold_label(self, threshold_value: float):
        if self.threshold_label:
            display_threshold = threshold_value if threshold_value <= 0 else -threshold_value
            self.threshold_label.setText(f"${display_threshold:,.2f}")

    @Slot(int)
    def _update_duration_label(self, duration_minutes: int):
        if self.duration_label:
            self.duration_label.setText(f"{duration_minutes} min")

    # Slot to handle pattern dict and format description
    @Slot(dict)
    def _update_patterns_label_from_dict(self, patterns: Dict[str, Any]):
        if not self.patterns_label: return

        description = "N/A"
        if patterns is None: # Handle None case explicitly
             patterns = {}

        # Logic to determine summary string based on keys present in the dict
        # Requires PlatformProfile for default comparison
        try:
            # Use default profile for comparison
            is_default = (patterns == PlatformProfile("dummy").numeric_patterns)
            if not patterns or is_default:
                 description = "Default"
            # Describe based on detected keys (prioritize functional patterns)
            elif "negative" in patterns: description = "ParensNeg ()"
            elif "negative_dash" in patterns: description = "DashNeg -"
            elif "dollar" in patterns: description = "Currency $"
            elif "regular" in patterns: description = "Number +/-"
            elif patterns: # If patterns dict is not empty but doesn't match knowns
                 description = "Custom"
            else: # Should be covered by 'not patterns' but as fallback
                 description = "Default/None"
        except Exception as e:
             self._logger.error(f"Error formatting pattern description: {e}")
             description = "Error" # Indicate error determining format

        self.patterns_label.setText(description)
    # --- End Slots for updating summary labels ---


    @Slot(str)
    def _handle_platform_selection_change(self, platform: str):
        """Slot called when the user changes the platform in the main selector."""
        if not platform: return

        self._logger.info(f"User selected platform: {platform}")
        # Tell the service about the change. The service notifies listeners (VMs).
        set_result = self._platform_selection_service.set_current_platform(platform)
        if set_result.is_failure:
            self._logger.error(f"Failed to set platform via service: {set_result.error}")
            self._update_platform_combo(self._platform_selection_service.get_current_platform()) # Revert display

        # --- *** Trigger summary update AFTER platform is set *** ---
        # The service notification will trigger VMs to update, which in turn should
        # trigger the summary label slots. But we can also force an immediate refresh.
        self._load_initial_summary() # Reload summary for the new platform


    @Slot(str)
    def _update_platform_combo(self, platform: str):
        """Slot called by the PlatformSelectionService when the platform changes elsewhere."""
        # Update the combo box display only if it's different
        if self.platform_combo and self.platform_combo.currentText() != platform:
             self._logger.debug(f"Updating platform combo display to reflect external change: {platform}")
             self.platform_combo.blockSignals(True)
             self.platform_combo.setCurrentText(platform)
             self.platform_combo.blockSignals(False)
             # --- *** Trigger summary update on external change too *** ---
             self._load_initial_summary()


    # --- Slot for Status Bar Messages ---
    @Slot(str, str)
    def _show_status_message(self, message: str, level: str):
        """Displays a message in the status bar."""
        if not self.status_bar: return
        # Add styling/timeout based on level if desired
        timeout = 5000 # Default 5 seconds
        prefix = ""
        if level.upper() == "ERROR":
            prefix = "[ERROR] "
            timeout = 8000 # Longer for errors
            # Could also change status bar background color temporarily
        elif level.upper() == "WARNING":
             prefix = "[WARNING] "
             timeout = 7000
        elif level.upper() == "SUCCESS":
             prefix = "[OK] "

        display_message = f"{prefix}{message}"
        self.status_bar.showMessage(display_message, timeout)
        # Update the permanent label as well for less transient messages? Optional.
        # self._status_label.setText(display_message)


    def closeEvent(self, event):
        """Handle the window close event."""
        self._logger.info("Close event received. Cleaning up...")
        try:
            self._logger.debug("Cancelling all background tasks...")
            # Ensure background service exists before calling
            if self._background_task_service:
                self._background_task_service.cancel_all_tasks()
                self._logger.debug("Background task cancellation requested.")
            else:
                self._logger.warning("Background task service not available for cleanup.")
        except Exception as e:
            self._logger.error(f"Error cancelling background tasks on close: {e}", exc_info=True)
        self._logger.info("Cleanup finished. Accepting close event.")
        event.accept()