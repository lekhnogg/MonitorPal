# src/presentation/views/main_view.py

import sys
from typing import Optional, Dict, Any, List

# --- Qt Imports ---
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QTabWidget, QStatusBar, QLabel,
    QComboBox, QToolBar, QSizePolicy, QApplication
)
# <<< Add QTimer Import (if not already there) >>>
from PySide6.QtCore import Slot, QSize, Qt, QTimer

# --- Application Imports ---
from src.domain.common.di_container import DIContainer
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_background_task_service import IBackgroundTaskService

# Import service interfaces needed for ViewModel instantiation
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
from src.domain.services.i_platform_selection_service import IPlatformSelectionService # Keep for VM

# --- Import the new MainViewModel ---
from src.presentation.view_models.main_view_model import MainViewModel

# --- Import the StyleManager ---
from src.presentation.styles.style_manager import StyleManager

# --- Import other ViewModels and Views ---.
from src.presentation.view_models.dashboard_view_model import DashboardViewModel
from src.presentation.view_models.region_setup_view_model import RegionSetupViewModel
from src.presentation.view_models.settings_view_model import SettingsViewModel
from src.presentation.view_models.ocr_calibration_view_model import OcrCalibrationViewModel
from src.presentation.view_models.history_view_model import HistoryViewModel
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
    # <<< Add main_view_model >>>
    main_view_model: Optional[MainViewModel] = None
    dashboard_vm: Optional[DashboardViewModel] = None
    region_setup_vm: Optional[RegionSetupViewModel] = None
    settings_vm: Optional[SettingsViewModel] = None
    ocr_calibration_vm: Optional[OcrCalibrationViewModel] = None
    history_vm: Optional[HistoryViewModel] = None

    def __init__(self, container: DIContainer, parent: Optional[QWidget] = None):
        """ Initializes the MainView. """
        super().__init__(parent)
        self._container = container
        # --- Resolve services needed directly by MainView OR for VM instantiation ---
        self._logger = self._container.resolve(ILoggerService)
        # Keep background task service if needed for closeEvent, otherwise remove
        self._background_task_service = self._container.resolve(IBackgroundTaskService)

        self._logger.info("Initializing MainView...")

        self._instantiate_view_models() # Instantiate VMs first
        self._setup_ui()                # Creates widgets
        self._connect_signals()         # Connects signals AFTER VMs/Views exist
        # Schedule the MainViewModel to re-emit its state now that the View is connected
        if self.main_view_model:  # Ensure VM exists
            self._logger.debug("MainView: Scheduling initial UI refresh via MainViewModel.refresh_ui_signals.")
            QTimer.singleShot(0, self.main_view_model.refresh_ui_signals)
        else:
            self._logger.error("MainView: Cannot schedule UI refresh, MainViewModel is None.")
        self._logger.info("MainView initialized successfully.")

    # --- NEW Method to Instantiate ViewModels ---
    def _instantiate_view_models(self):
        """Instantiates all ViewModels needed by the application."""
        self._logger.debug("Instantiating ViewModels...")
        try:
            # Instantiate MainViewModel first
            self.main_view_model = MainViewModel(
                logger=self._logger,
                config_repo=self._container.resolve(IConfigRepository),
                platform_selection_service=self._container.resolve(IPlatformSelectionService),
                region_service=self._container.resolve(IRegionService),
                profile_service=self._container.resolve(IProfileService),
                parent=self
            )
            # Instantiate other ViewModels (passing dependencies)
            self.dashboard_vm = DashboardViewModel( # Pass all dependencies
                logger=self._logger,
                monitoring_service=self._container.resolve(IMonitoringService),
                lockout_service=self._container.resolve(ILockoutService),
                flash_service=self._container.resolve(IFlashService),
                platform_selection_service=self._container.resolve(IPlatformSelectionService), # Use resolved instance
                config_repo=self._container.resolve(IConfigRepository),
                region_service=self._container.resolve(IRegionService),
                profile_service=self._container.resolve(IProfileService), # Use resolved instance
                parent=self
            )
            self.region_setup_vm = RegionSetupViewModel( # Pass all dependencies
                logger=self._logger,
                region_service=self._container.resolve(IRegionService),
                platform_selection_service=self._container.resolve(IPlatformSelectionService), # Use resolved instance
                flash_service=self._container.resolve(IFlashService),
                ui_service=self._container.resolve(IUIService),
                screenshot_service=self._container.resolve(IScreenshotService),
                parent=self
            )
            self.settings_vm = SettingsViewModel( # Pass all dependencies
                logger=self._logger,
                config_repo=self._container.resolve(IConfigRepository),
                platform_selection_service=self._container.resolve(IPlatformSelectionService), # Use resolved instance
                cold_turkey_service=self._container.resolve(IColdTurkeyService),
                verification_service=self._container.resolve(IVerificationService),
                path_service=self._container.resolve(IPathService),
                ui_service=self._container.resolve(IUIService),
                parent=self
            )
            self.ocr_calibration_vm = OcrCalibrationViewModel( # Pass all dependencies
                logger=self._logger,
                profile_service=self._container.resolve(IProfileService), # Use resolved instance
                ocr_service=self._container.resolve(IOcrService),
                ocr_analysis_service=self._container.resolve(IOcrAnalysisService),
                region_service=self._container.resolve(IRegionService),
                platform_selection_service=self._container.resolve(IPlatformSelectionService), # Use resolved instance
                thread_service=self._background_task_service,
                screenshot_service=self._container.resolve(IScreenshotService),
                ui_service=self._container.resolve(IUIService),
                parent=self
            )
            self.history_vm = HistoryViewModel( # Pass all dependencies
                logger=self._logger,
                config_repo=self._container.resolve(IConfigRepository),
                platform_selection_service=self._container.resolve(IPlatformSelectionService), # Use resolved instance
                parent=self
            )
            self._logger.debug("ViewModels instantiated.")
        except Exception as e:
             self._logger.error(f"FATAL: Failed to instantiate ViewModels: {e}", exc_info=True)
             from PySide6.QtWidgets import QMessageBox
             QMessageBox.critical(self, "Initialization Error",
                                  f"Could not create essential application components:\n{e}")
             # Rethrow or handle fatal error appropriately
             raise RuntimeError("ViewModel instantiation failed.") from e


    def _setup_ui(self):
        """Creates and arranges the main UI elements."""
        # --- Check if VMs are instantiated ---
        if not self.main_view_model:
             self._logger.error("Cannot setup UI - MainViewModel not instantiated.")
             return
        # Check other VMs if necessary before creating their views

        self.setWindowTitle("MonitorPal")
        self.setMinimumSize(QSize(900, 700))
        self.resize(QSize(1100, 800))

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(10)

        # --- Platform Selector Toolbar (TOP) ---
        self.platform_toolbar = QToolBar("Platform Selection")
        self.platform_toolbar.setObjectName("platformToolbar")
        self.platform_toolbar.setMovable(False); self.platform_toolbar.setFloatable(False)
        self.platform_toolbar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.platform_toolbar)

        # --- Add Summary Labels to Toolbar (Widgets only, text set by VM signals) ---
        # Add Descriptor Labels (Optionally set class property here too)
        region_desc_label = QLabel(" Region: ")
        region_desc_label.setProperty("class", "toolbarDescriptor")
        self.platform_toolbar.addWidget(region_desc_label)
        # Create Summary Labels (Object name no longer needed for styling)
        self.region_label = QLabel("N/A")
        self.platform_toolbar.addWidget(self.region_label)
        self.platform_toolbar.addSeparator()

        threshold_desc_label = QLabel(" Threshold: ")
        threshold_desc_label.setProperty("class", "toolbarDescriptor")
        self.platform_toolbar.addWidget(threshold_desc_label)
        self.threshold_label = QLabel("N/A")
        self.platform_toolbar.addWidget(self.threshold_label)
        self.platform_toolbar.addSeparator()

        duration_desc_label = QLabel(" Duration: ")
        duration_desc_label.setProperty("class", "toolbarDescriptor")
        self.platform_toolbar.addWidget(duration_desc_label)
        self.duration_label = QLabel("N/A")
        self.platform_toolbar.addWidget(self.duration_label)
        self.platform_toolbar.addSeparator()

        patterns_desc_label = QLabel(" Patterns: ")
        patterns_desc_label.setProperty("class", "toolbarDescriptor")
        self.platform_toolbar.addWidget(patterns_desc_label)
        self.patterns_label = QLabel("N/A")
        self.patterns_label.setToolTip("Detected number format patterns (Default/Custom/etc.)")
        self.platform_toolbar.addWidget(self.patterns_label)

        spacer = QWidget(); spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.platform_toolbar.addWidget(spacer)
        self.platform_toolbar.addWidget(QLabel(" Platform: "))
        self.platform_combo = QComboBox(); self.platform_combo.setObjectName("platformComboBox")
        self.platform_combo.setMinimumWidth(170)
        self.platform_toolbar.addWidget(self.platform_combo)
        # --- Platform list and initial selection will be handled by connecting to MainViewModel ---

        # --- Tab Widget ---
        self.tab_widget = QTabWidget()
        self.tab_widget.setObjectName("mainTabWidget")
        self.tab_widget.setTabPosition(QTabWidget.TabPosition.North)
        self.tab_widget.setMovable(False)
        main_layout.addWidget(self.tab_widget, 1)

        # --- Status Bar ---
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self._status_label = QLabel("Ready"); self._status_label.setObjectName("statusBarLabel")
        self.status_bar.addWidget(self._status_label, 1)

        # --- Instantiate Views and Add Tabs (Requires VMs to be ready) ---
        self._enhance_toolbar_styling()
        self._logger.debug("Instantiating Views and adding tabs...")
        try:
            # Check that VMs exist before creating Views that depend on them
            if not self.dashboard_vm: raise ValueError("DashboardViewModel not initialized")
            dashboard_view = DashboardView(self.dashboard_vm, self)
            self.tab_widget.addTab(dashboard_view, "Dashboard")

            if not self.region_setup_vm: raise ValueError("RegionSetupViewModel not initialized")
            region_setup_view = RegionSetupView(self.region_setup_vm, self)
            self.tab_widget.addTab(region_setup_view, "Region Setup")

            if not self.settings_vm: raise ValueError("SettingsViewModel not initialized")
            settings_view = SettingsView(self.settings_vm, self)
            self.tab_widget.addTab(settings_view, "Settings")

            if not self.ocr_calibration_vm: raise ValueError("OcrCalibrationViewModel not initialized")
            ocr_calibration_view = OcrCalibrationView(self.ocr_calibration_vm, self)
            self.tab_widget.addTab(ocr_calibration_view, "OCR Calibration")

            if not self.history_vm: raise ValueError("HistoryViewModel not initialized")
            history_view = HistoryView(self.history_vm, self)
            self.tab_widget.addTab(history_view, "History")

            self._logger.debug("Views created and added as tabs.")
        except Exception as e:
            self._logger.error(f"FATAL: Failed to instantiate Views or add tabs: {e}", exc_info=True)
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Initialization Error", f"Could not create application UI sections:\n{e}")
            # self.close()
            return

        self._enhance_toolbar_styling()

    def _enhance_toolbar_styling(self):
        """Apply styling properties to the toolbar labels."""
        # Set property for targeting in stylesheet
        for label in [self.region_label, self.threshold_label, self.duration_label, self.patterns_label]:
            if label:  # Check if label exists
                label.setProperty("class", "toolbarSummaryLabel")  # <<< This is the key line

    def _connect_signals(self):
        """Connect signals for the MainView UI elements and ViewModels."""
        # --- Guards ---
        if not self.platform_combo: self._logger.error("Platform combo box not initialized"); return
        if not self.main_view_model: self._logger.error("MainViewModel not initialized"); return
        # Check other VMs if needed
        vm_missing = False
        for vm_name in ['dashboard_vm', 'region_setup_vm', 'settings_vm', 'ocr_calibration_vm', 'history_vm']:
             if not getattr(self, vm_name, None):
                 self._logger.error(f"{vm_name} not initialized before connecting signals.")
                 vm_missing = True
        if vm_missing: return

        self._logger.debug("Connecting MainView signals...")

        # --- Platform ComboBox <-> MainViewModel ---
        self.platform_combo.currentTextChanged.connect(self.main_view_model.user_selected_platform)
        self.main_view_model.selected_platform_changed.connect(self._update_platform_combo)
        self.main_view_model.available_platforms_changed.connect(self._update_available_platforms)

        # --- Summary Labels <-> MainViewModel ---
        self.main_view_model.summary_region_changed.connect(self.region_label.setText)
        self.main_view_model.summary_threshold_changed.connect(self.threshold_label.setText)
        self.main_view_model.summary_duration_changed.connect(self.duration_label.setText)
        self.main_view_model.summary_patterns_changed.connect(self.patterns_label.setText)

        # --- Status Bar Messages (Connect ALL ViewModels) ---
        self.dashboard_vm.status_message_changed.connect(self._show_status_message)
        self.region_setup_vm.status_message_changed.connect(self._show_status_message)
        self.settings_vm.status_message_changed.connect(self._show_status_message)
        self.ocr_calibration_vm.status_message_changed.connect(self._show_status_message)
        self.history_vm.status_message_changed.connect(self._show_status_message)

        # --- NEW: Connect other VMs to MainViewModel's refresh summary signal if needed ---
        # If saving settings should trigger a summary refresh:
        self.settings_vm.settings_saved.connect(
            lambda success: self.main_view_model.refresh_summary_data() if success else None
        )
        # If saving OCR profile should trigger a summary refresh:
        self.ocr_calibration_vm.profile_potentially_changed.connect(
            lambda platform: self.main_view_model.refresh_summary_data() # Refresh always on profile change
        )
        # If saving a region should trigger a summary refresh:
        self.region_setup_vm.monitor_region_saved.connect(
             lambda platform: self.main_view_model.refresh_summary_data()
        )
        # Add similar connections if other VM actions should update the summary bar

        self._logger.debug("MainView signals connected.")

    # --- Platform Change Handlers ---
    @Slot(str)
    def _handle_platform_selection_change(self, platform: str):
        """Slot called when the user changes the platform in the main selector."""
        # This method now only needs to inform the MainViewModel
        if not platform or not self.main_view_model: return
        self.main_view_model.user_selected_platform(platform)

    @Slot(list)
    def _update_available_platforms(self, platforms: List[str]):
        """Updates the platform combo box choices."""
        if not self.platform_combo: return
        current_text = self.platform_combo.currentText() # Remember current selection
        self.platform_combo.blockSignals(True)
        self.platform_combo.clear()
        self.platform_combo.addItems(platforms)
        # Try to restore selection
        if current_text in platforms:
            self.platform_combo.setCurrentText(current_text)
        elif platforms:
            self.platform_combo.setCurrentIndex(0)
            # Inform VM if we had to default to the first item
            # self.main_view_model.user_selected_platform(self.platform_combo.currentText()) # Careful about loops
        self.platform_combo.blockSignals(False)
        self._logger.debug(f"Platform combo box updated with: {platforms}")

    @Slot(str)
    def _update_platform_combo(self, platform: str):
        """Slot called by the MainViewModel when the platform changes."""
        # Update the combo box display only if it's different
        if self.platform_combo and self.platform_combo.currentText() != platform:
            self._logger.debug(f"Updating platform combo display to reflect model change: {platform}")
            self.platform_combo.blockSignals(True) # Prevent feedback loop
            self.platform_combo.setCurrentText(platform or "") # Handle None/empty case
            self.platform_combo.blockSignals(False)

    # --- Slot for Status Bar Messages (Keep As Is) ---
    @Slot(str, str)
    def _show_status_message(self, message: str, level: str):
        """Displays a message in the status bar with appropriate styling."""
        # ... (Keep existing implementation) ...
        if not self._status_label: return
        # Map levels to specific styles
        if level.upper() == "ERROR":
            prefix, style, timeout = "⚠️ ", "color: white; font-weight: bold; padding: 2px 5px; background-color: #e74c3c; border-radius: 3px;", 8000
        elif level.upper() == "WARNING":
            prefix, style, timeout = "⚠ ", "color: black; font-weight: bold; padding: 2px 5px; background-color: #f39c12; border-radius: 3px;", 7000
        elif level.upper() == "SUCCESS":
            prefix, style, timeout = "✓ ", "color: white; font-weight: bold; padding: 2px 5px; background-color: #27ae60; border-radius: 3px;", 5000
        else:  # INFO or default
            prefix, style, timeout = "ℹ ", "color: #bdc3c7; padding: 2px 5px;", 5000 # Lighter color for info

        display_message = f"{prefix}{message}"
        self._status_label.setText(display_message)
        self._status_label.setStyleSheet(style) # Apply style directly
        if self.status_bar: self.status_bar.showMessage("", timeout)

    # --- closeEvent (Keep As Is, Ensure _background_task_service is resolved if needed) ---
    def closeEvent(self, event):
        """Handle the window close event."""
        # ... (Keep existing implementation) ...
        self._logger.info("Close event received. Cleaning up...")
        try:
            if hasattr(self, '_background_task_service') and self._background_task_service:
                self._logger.debug("Cancelling all background tasks...")
                self._background_task_service.cancel_all_tasks()
                self._logger.debug("Background task cancellation requested.")
            else:
                self._logger.warning("Background task service not available for cleanup.")
        except Exception as e:
            self._logger.error(f"Error cancelling background tasks on close: {e}", exc_info=True)
        finally:
             self._logger.info("Cleanup attempt finished. Accepting close event.")
             event.accept()