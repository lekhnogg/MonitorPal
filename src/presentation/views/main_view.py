# src/presentation/views/main_view.py

import sys
from typing import Optional, Dict, Any, List

# --- Qt Imports ---
from PySide6.QtGui import QColor, QIcon, QPixmap  # QIcon for create_colored_svg_icon, QPixmap for tooltip
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QEvent, QFile  # For image to base64
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QTabWidget, QStatusBar, QLabel,
    QComboBox, QToolBar, QSizePolicy, QApplication, QPushButton, QMessageBox, QButtonGroup, QStackedWidget, QHBoxLayout
)
from PySide6.QtCore import Slot, QSize, Qt, QTimer

# --- Application Imports ---
from src.domain.common.di_container import DIContainer
from src.domain.services.i_history_service import IHistoryService
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_background_task_service import IBackgroundTaskService  # For closeEvent

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
from src.domain.services.i_platform_selection_service import IPlatformSelectionService

# Import your custom icon coloring function
from src.presentation.components.ui_components import create_colored_svg_icon, ActionButton, DangerButton, StyledButton

# Import ViewModels
from src.presentation.view_models.main_view_model import MainViewModel
from src.presentation.view_models.dashboard_view_model import DashboardViewModel
from src.presentation.view_models.visual_setup_view_model import VisualSetupViewModel  # NEW
from src.presentation.view_models.settings_view_model import SettingsViewModel
from src.presentation.view_models.history_view_model import HistoryViewModel

# Import Views
from src.presentation.views.dashboard_view import DashboardView
from src.presentation.views.visual_setup_view import VisualSetupView  # NEW
from src.presentation.views.settings_view import SettingsView
from src.presentation.views.history_view import HistoryView


# Import StyleManager if you need to call its methods directly (e.g., for dynamic re-apply)
# from src.presentation.styles.style_manager import StyleManager

class MainView(QMainWindow):
    # --- UI Element Attributes ---
    platform_toolbar: Optional[QToolBar] = None
    platform_combo: Optional[QComboBox] = None
    theme_toggle_button: Optional[QPushButton] = None

    stacked_widget: Optional[QStackedWidget] = None  # REPLACES QTabWidget
    tab_buttons: Dict[str, QPushButton] = {}  # For custom tab buttons
    tab_button_group: Optional[QButtonGroup] = None  # To manage tab button exclusivity

    status_bar: Optional[QStatusBar] = None
    status_bar_main_status_label: Optional[QLabel] = None
    status_bar_region_label: Optional[QLabel] = None
    status_bar_threshold_label: Optional[QLabel] = None
    status_bar_duration_label: Optional[QLabel] = None
    _status_clear_timer: Optional[QTimer] = None

    DEFAULT_STATUS_TEXT = "✓ Ready"
    DEFAULT_STATUS_STYLE_LIGHT = "color: #27ae60; padding: 2px 5px;"
    DEFAULT_STATUS_STYLE_DARK = "color: #4ade80; padding: 2px 5px;"
    INFO_BUSY_STYLE_LIGHT = "color: #3498db; padding: 2px 5px;"
    INFO_BUSY_STYLE_DARK = "color: #60a5fa; padding: 2px 5px;"

    # --- ViewModel Attributes ---
    main_view_model: Optional[MainViewModel] = None
    dashboard_vm: Optional[DashboardViewModel] = None
    visual_setup_vm: Optional[VisualSetupViewModel] = None
    settings_vm: Optional[SettingsViewModel] = None
    history_vm: Optional[HistoryViewModel] = None

    _tab_references: Dict[str, QWidget] = {}
    _tab_button_icon_paths: Dict[str, str] = {  # Store icon paths for tab buttons
        "Dashboard": ":/icons/home.svg",
        "Visual Setup": ":/icons/sliders.svg",  # Or tool, edit etc.
        "Settings": ":/icons/settings.svg",
        "History": ":/icons/bar-chart-2.svg"  # Or file-text
    }

    toolbar_start_button: Optional[QPushButton] = None  # Or ActionButton if type hinting strictly
    toolbar_stop_button: Optional[QPushButton] = None  # Or DangerButton
    toolbar_test_flash_button: Optional[QPushButton] = None # If you also move Test Flash

    def __init__(self, container: DIContainer, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._container = container
        self._logger = self._container.resolve(ILoggerService)
        self._background_task_service = self._container.resolve(IBackgroundTaskService)

        self._logger.info("Initializing MainView...")
        self._instantiate_view_models()

        self._setup_ui()
        self._connect_signals()

        if self.main_view_model:
            self._logger.debug("MainView: Scheduling initial UI refresh via MainViewModel.refresh_ui_signals.")
            QTimer.singleShot(0, self.main_view_model.refresh_ui_signals)
        else:
            self._logger.error("MainView: MainViewModel is None, cannot schedule initial UI refresh.")

        self._logger.info("MainView initialized successfully.")

    def _instantiate_view_models(self):
        self._logger.debug("Instantiating ViewModels...")
        try:
            # MainViewModel (ensure all its dependencies are resolved correctly)
            self.main_view_model = MainViewModel(
                logger=self._logger,
                config_repo=self._container.resolve(IConfigRepository),
                platform_selection_service=self._container.resolve(IPlatformSelectionService),
                region_service=self._container.resolve(IRegionService),
                profile_service=self._container.resolve(IProfileService),  # MainVM uses this for summary_patterns
                parent=self
            )
            # DashboardViewModel
            self.dashboard_vm = DashboardViewModel(
                logger=self._logger, monitoring_service=self._container.resolve(IMonitoringService),
                lockout_service=self._container.resolve(ILockoutService),
                flash_service=self._container.resolve(IFlashService),
                platform_selection_service=self._container.resolve(IPlatformSelectionService),
                config_repo=self._container.resolve(IConfigRepository),
                region_service=self._container.resolve(IRegionService),
                profile_service=self._container.resolve(IProfileService),
                cold_turkey_service=self._container.resolve(IColdTurkeyService),
                history_service=self._container.resolve(IHistoryService),  # <-- RESOLVE & PASS
                parent=self
            )
            # VisualSetupViewModel
            self.visual_setup_vm = VisualSetupViewModel(
                logger=self._logger, region_service=self._container.resolve(IRegionService),
                platform_selection_service=self._container.resolve(IPlatformSelectionService),
                flash_service=self._container.resolve(IFlashService), ui_service=self._container.resolve(IUIService),
                screenshot_service=self._container.resolve(IScreenshotService),
                profile_service=self._container.resolve(IProfileService),
                ocr_service=self._container.resolve(IOcrService),
                ocr_analysis_service=self._container.resolve(IOcrAnalysisService),
                thread_service=self._container.resolve(IBackgroundTaskService), parent=self
            )
            # SettingsViewModel
            self.settings_vm = SettingsViewModel(
                logger=self._logger, config_repo=self._container.resolve(IConfigRepository),
                platform_selection_service=self._container.resolve(IPlatformSelectionService),
                cold_turkey_service=self._container.resolve(IColdTurkeyService),
                verification_service=self._container.resolve(IVerificationService),
                path_service=self._container.resolve(IPathService),
                ui_service=self._container.resolve(IUIService), parent=self
            )
            # HistoryViewModel
            self.history_vm = HistoryViewModel(
                logger=self._logger,
                config_repo=self._container.resolve(IConfigRepository),
                platform_selection_service=self._container.resolve(IPlatformSelectionService),
                history_service=self._container.resolve(IHistoryService),
                ui_service=self._container.resolve(IUIService),
                parent=self
            )
            self._logger.debug("All ViewModels instantiated.")
        except Exception as e:
            self._logger.critical(f"FATAL: Failed to instantiate ViewModels: {e}", exc_info=True)
            QMessageBox.critical(self, "Initialization Error",
                                 f"Could not create essential application components:\n{e}")
            raise RuntimeError("ViewModel instantiation failed.") from e

    def _setup_ui(self):
        if not self.main_view_model:
            self._logger.error("Cannot setup UI - MainViewModel not instantiated.")
            return

        self.setWindowTitle("MonitorPal")
        self.setMinimumSize(QSize(900, 700))
        self.resize(QSize(1200, 850))

        central_widget = QWidget(self)
        central_widget.setObjectName("mainCentralWidget")
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Top Toolbar (Tabs, Platform, Theme Toggle) ---
        self.platform_toolbar = QToolBar("Main Toolbar")
        self.platform_toolbar.setObjectName("platformToolbar")
        self.platform_toolbar.setMovable(False)
        self.platform_toolbar.setFloatable(False)
        self.platform_toolbar.setIconSize(QSize(16, 16)) # Default size for tab icons
        self.platform_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        # --- START: ADD LOGO/TITLE ---
        logo_widget = QWidget()
        logo_widget.setObjectName("toolbarLogoWidget") # Optional: for potential specific container styling
        logo_layout = QHBoxLayout(logo_widget)
        logo_layout.setContentsMargins(5, 0, 10, 0) # Left 5, Right 10
        logo_layout.setSpacing(6)

        # Logo Icon Label
        logo_icon_label = QLabel()
        logo_icon_label.setObjectName("toolbarLogoIcon")
        logo_icon_label.setFixedSize(24, 24) # Adjust size as needed
        # Icon pixmap will be set in _update_ui_for_theme_change
        logo_layout.addWidget(logo_icon_label)

        # Logo Text Label
        logo_text_label = QLabel("MonitorPal")
        logo_text_label.setObjectName("toolbarLogoText")
        # Styling (font size, weight, color) should be done via QSS
        logo_layout.addWidget(logo_text_label)

        self.platform_toolbar.addWidget(logo_widget)
        self.platform_toolbar.addSeparator() # Separator after logo/title
        # --- END: ADD LOGO/TITLE ---

        # Custom Tab Buttons
        self.tab_buttons = {}
        self.tab_button_group = QButtonGroup(self)
        self.tab_button_group.setExclusive(True)

        tab_keys_in_order = ["Dashboard", "Visual Setup", "Settings", "History"]

        for tab_key in tab_keys_in_order:
            button = QPushButton(tab_key)
            button.setProperty("class", "toolbarTabButton")
            button.setCheckable(True)
            button.setObjectName(f"tabBtn{tab_key.replace(' ', '')}")
            # Icon will be set in _update_ui_for_theme_change
            button.clicked.connect(self._on_toolbar_tab_selected)
            self.platform_toolbar.addWidget(button)
            self.tab_buttons[tab_key] = button
            self.tab_button_group.addButton(button)

        self.platform_toolbar.addSeparator() # Separator after tabs (optional)

        # Spacer Widget to push items to the right
        toolbar_spacer = QWidget()
        toolbar_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.platform_toolbar.addWidget(toolbar_spacer)

        # Create Start Button
        self.toolbar_start_button = ActionButton("Start", icon=":/icons/play.svg")
        self.toolbar_start_button.setObjectName("toolbarStartButton")
        self.toolbar_start_button.setToolTip("Start monitoring for the selected platform")
        # You can adjust padding via QSS if needed for toolbar specifically:
        # self.toolbar_start_button.setStyleSheet("padding: 4px 8px;") # Example
        self.platform_toolbar.addWidget(self.toolbar_start_button)

        # Create Stop Button
        self.toolbar_stop_button = DangerButton("Stop", icon=":/icons/stop-circle.svg")
        self.toolbar_stop_button.setObjectName("toolbarStopButton")
        self.toolbar_stop_button.setToolTip("Stop active monitoring")
        # self.toolbar_stop_button.setStyleSheet("padding: 4px 8px;") # Example
        self.platform_toolbar.addWidget(self.toolbar_stop_button)

        # Create Flash Button
        self.toolbar_test_flash_button = StyledButton("Flash", icon=":/icons/zap.svg")
        self.toolbar_test_flash_button.setObjectName("toolbarTestFlashButton")
        self.toolbar_test_flash_button.setToolTip("Test flash for defined regions")
        self.platform_toolbar.addWidget(self.toolbar_test_flash_button)

        self.platform_toolbar.addSeparator() # Optional: Separator after action buttons

        # Theme Toggle Button
        self.theme_toggle_button = QPushButton()
        self.theme_toggle_button.setObjectName("themeToggleButton")
        self.theme_toggle_button.setFlat(True) # Makes background transparent by default
        self.theme_toggle_button.setIconSize(QSize(18, 18)) # Theme icon size
        # Icon will be set in _update_ui_for_theme_change
        self.platform_toolbar.addWidget(self.theme_toggle_button)

        # Separator before platform selector
        self.platform_toolbar.addSeparator()

        # Create a custom platform selector with icon
        platform_container = QWidget()
        platform_container.setObjectName("platformContainer")
        platform_layout = QHBoxLayout(platform_container)
        platform_layout.setContentsMargins(3, 3, 8, 3)
        platform_layout.setSpacing(6)

        # Platform icon in colored background
        platform_icon_container = QWidget()
        platform_icon_container.setObjectName("platformIconContainer")
        platform_icon_container.setFixedSize(24, 24)
        platform_icon_layout = QHBoxLayout(platform_icon_container)
        platform_icon_layout.setContentsMargins(4, 4, 4, 4)
        platform_icon_layout.setSpacing(0)

        platform_icon = QLabel()
        platform_icon.setObjectName("platformIcon")
        platform_icon_layout.addWidget(platform_icon)
        platform_layout.addWidget(platform_icon_container)

        # Initialize icon - will be properly colored in _update_ui_for_theme_change
        icon_color = QColor("#60a5fa") if self.property("darkTheme") else QColor("#2563eb")
        try:
            colored_icon = create_colored_svg_icon(":/icons/server.svg", icon_color, QSize(16, 16))
            platform_icon.setPixmap(colored_icon.pixmap(QSize(16, 16)))
        except Exception as e:
            self._logger.error(f"Error setting platform icon: {e}")

        # Platform dropdown
        self.platform_combo = QComboBox()
        self.platform_combo.setObjectName("platformComboBox")
        self.platform_combo.setMinimumWidth(180)
        platform_layout.addWidget(self.platform_combo)

        self.platform_toolbar.addWidget(platform_container)

        # Add the toolbar to the main window
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.platform_toolbar)

        # --- Content Area (using QStackedWidget) ---
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.setObjectName("mainStackedWidget")
        main_layout.addWidget(self.stacked_widget, 1) # Give stretch factor

        # --- Status Bar ---
        # Status Bar with modern styling
        self.status_bar = QStatusBar()
        self.status_bar.setObjectName("statusBar")
        self.setStatusBar(self.status_bar)

        # Status Badge (left side) - "System Ready"
        status_badge = QLabel(self.DEFAULT_STATUS_TEXT)
        status_badge.setObjectName("statusBarMainStatusLabel")
        self.status_bar_main_status_label = status_badge  # Store reference
        self.status_bar.addWidget(status_badge)

        # Add spacer to push status items to right
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.status_bar.addWidget(spacer)

        # Status metrics (right side)
        # Create containers for each info item so we can separate label from value
        # 1. Region with clickable value
        region_container = QWidget()
        region_layout = QHBoxLayout(region_container)
        region_layout.setContentsMargins(4, 0, 4, 0)
        region_layout.setSpacing(0)

        region_label = QLabel("")
        region_label.setObjectName("statusItemLabel")
        region_layout.addWidget(region_label)

        self.status_bar_region_label = QLabel("N/A")
        self.status_bar_region_label.setObjectName("statusBarRegionLabel")
        self.status_bar_region_label.setCursor(Qt.CursorShape.PointingHandCursor)
        region_layout.addWidget(self.status_bar_region_label)

        self.status_bar.addPermanentWidget(region_container)

        # Separator
        sep1 = QLabel("|")
        sep1.setObjectName("statusBarSeparator")
        self.status_bar.addPermanentWidget(sep1)

        # 2. Threshold with colored value
        threshold_container = QWidget()
        threshold_layout = QHBoxLayout(threshold_container)
        threshold_layout.setContentsMargins(4, 0, 4, 0)
        threshold_layout.setSpacing(0)

        threshold_label = QLabel("")
        threshold_label.setObjectName("statusItemLabel")
        threshold_layout.addWidget(threshold_label)

        self.status_bar_threshold_label = QLabel("N/A")
        self.status_bar_threshold_label.setObjectName("statusBarThresholdLabel")
        threshold_layout.addWidget(self.status_bar_threshold_label)

        self.status_bar.addPermanentWidget(threshold_container)

        # Separator
        sep2 = QLabel("|")
        sep2.setObjectName("statusBarSeparator")
        self.status_bar.addPermanentWidget(sep2)

        # 3. Duration with colored value
        duration_container = QWidget()
        duration_layout = QHBoxLayout(duration_container)
        duration_layout.setContentsMargins(4, 0, 4, 0)
        duration_layout.setSpacing(0)

        duration_label = QLabel("")
        duration_label.setObjectName("statusItemLabel")
        duration_layout.addWidget(duration_label)

        self.status_bar_duration_label = QLabel("N/A")
        self.status_bar_duration_label.setObjectName("statusBarDurationLabel")
        duration_layout.addWidget(self.status_bar_duration_label)

        self.status_bar.addPermanentWidget(duration_container)

        # --- Instantiate Views and Add to StackedWidget ---
        self._logger.debug("Instantiating Views and adding to StackedWidget...")
        self._tab_references.clear()
        try:
            # Order of adding to stacked_widget determines initial index if not set otherwise
            vm_view_map = {
                "Dashboard": (self.dashboard_vm, DashboardView),
                "Visual Setup": (self.visual_setup_vm, VisualSetupView),
                "Settings": (self.settings_vm, SettingsView),
                "History": (self.history_vm, HistoryView),
            }
            for tab_key in tab_keys_in_order: # Add in defined order
                vm, ViewClass = vm_view_map.get(tab_key)
                if vm and ViewClass:
                    view_instance = ViewClass(vm, self)
                    view_instance.setObjectName(f"view{tab_key.replace(' ', '')}") # Set object name for view
                    self.stacked_widget.addWidget(view_instance)
                    self._tab_references[tab_key] = view_instance
                else:
                    # Handle case where VM or View class might be None - critical error
                    raise ValueError(f"Missing ViewModel or ViewClass for tab '{tab_key}'")

            self._logger.debug("Views created and added to StackedWidget.")

            # Set initial active tab/button (e.g., Dashboard)
            if "Dashboard" in self.tab_buttons and "Dashboard" in self._tab_references:
                self.tab_buttons["Dashboard"].setChecked(True) # Visually check button
                self.stacked_widget.setCurrentWidget(self._tab_references["Dashboard"]) # Set active page
                # Style update for buttons will happen on first theme change or refresh signal
                # Or call it explicitly here if needed immediately:
                # self._update_toolbar_tab_button_styles("Dashboard")
            else:
                self._logger.warning("Could not set initial 'Dashboard' tab as active.")

        except Exception as e:
            self._logger.critical(f"FATAL: Failed to instantiate Views or add to StackedWidget: {e}", exc_info=True)
            QMessageBox.critical(self, "UI Creation Error", f"Could not create application UI sections:\n{e}")
            # Depending on severity, you might want to exit or disable parts of the UI
            return # Prevent further setup if views failed

    def _connect_signals(self):
        self._logger.debug("Attempting to connect MainView signals...")

        # --- Initial Checks for Essential Components ---
        if not (self.platform_combo and self.main_view_model and
                self.status_bar_main_status_label and self.status_bar_region_label and
                self.status_bar_threshold_label and self.status_bar_duration_label):
            self._logger.error(
                "CRITICAL: Essential UI elements or MainViewModel not initialized. Aborting signal connections.")
            return

        required_vm_attributes = ['dashboard_vm', 'visual_setup_vm', 'settings_vm', 'history_vm']
        for vm_attr_name in required_vm_attributes:
            if not hasattr(self, vm_attr_name) or getattr(self, vm_attr_name, None) is None:
                self._logger.error(
                    f"CRITICAL: ViewModel '{vm_attr_name}' not initialized. Aborting signal connections.")
                return
        self._logger.info("All critical UI/VMs present. Proceeding with signal connections.")

        # --- Platform ComboBox & MainVM Summary (Existing Connections) ---
        self.platform_combo.currentTextChanged.connect(self.main_view_model.user_selected_platform)
        self.main_view_model.selected_platform_changed.connect(self._update_platform_combo)
        self.main_view_model.available_platforms_changed.connect(self._update_available_platforms)

        if self.main_view_model and hasattr(self.main_view_model, 'platform_selection_enabled_changed'):
            self.main_view_model.platform_selection_enabled_changed.connect(self._set_platform_combo_enabled_state)
            self._logger.debug(
                "Connected MainVM.platform_selection_enabled_changed to MainView._set_platform_combo_enabled_state.")
        else:
            self._logger.warning(
                "MainViewModel does not have 'platform_selection_enabled_changed' signal for Platform ComboBox.")

        self.main_view_model.summary_region_changed.connect(self.status_bar_region_label.setText)
        self.main_view_model.summary_threshold_changed.connect(self.status_bar_threshold_label.setText)
        self.main_view_model.summary_duration_changed.connect(self.status_bar_duration_label.setText)

        # --- Region Preview Tooltip (Existing Connection) ---
        if self.visual_setup_vm and hasattr(self.visual_setup_vm, 'monitor_region_preview_changed'):
            self.visual_setup_vm.monitor_region_preview_changed.connect(self._update_summary_region_tooltip)

        # --- Status Bar Main Message (Existing Connections) ---
        for vm_attr_name in required_vm_attributes: # dashboard_vm is in this list
            vm_instance = getattr(self, vm_attr_name)
            if hasattr(vm_instance, 'status_message_changed'):
                vm_instance.status_message_changed.connect(self._show_status_message)

        # --- Dashboard Navigation & Summary Refresh Triggers (Existing Connections) ---
        if "Dashboard" in self._tab_references and isinstance(self._tab_references["Dashboard"], DashboardView):
            if hasattr(self._tab_references["Dashboard"], 'request_tab_navigation'):
                self._tab_references["Dashboard"].request_tab_navigation.connect(self.handle_tab_navigation_request)
        if self.settings_vm and hasattr(self.settings_vm, 'settings_saved'):
            self.settings_vm.settings_saved.connect(
                lambda s: self.main_view_model.refresh_summary_data() if s else None)
        if self.visual_setup_vm and hasattr(self.visual_setup_vm, 'visual_setup_profile_changed'):
            self.visual_setup_vm.visual_setup_profile_changed.connect(self.main_view_model.refresh_summary_data)

        # --- Theme Toggle & Refresh (Existing Connections) ---
        if self.theme_toggle_button:
            self.theme_toggle_button.clicked.connect(self.main_view_model.toggle_theme)
        self.main_view_model.current_theme_changed.connect(self._update_ui_for_theme_change)

        child_vms_for_theme_refresh = {"DashboardVM": self.dashboard_vm, "VisualSetupVM": self.visual_setup_vm,
                                       "SettingsVM": self.settings_vm, "HistoryVM": self.history_vm}
        for vm_name, vm_instance in child_vms_for_theme_refresh.items():
            if vm_instance and hasattr(vm_instance, 'on_theme_refresh_requested'):
                self.main_view_model.theme_refresh_requested.connect(vm_instance.on_theme_refresh_requested)
                self._logger.debug(f"Connected MainVM.theme_refresh_requested to {vm_name}.on_theme_refresh_requested.")
            elif vm_instance: # Log even if it doesn't have the slot, for completeness
                self._logger.debug(f"{vm_name} has no on_theme_refresh_requested slot.")

        # --- QStackedWidget currentChanged (Existing Connection) ---
        if self.stacked_widget:
            self.stacked_widget.currentChanged.connect(self._on_stacked_widget_changed)

        # --------------------------------------------------------------------
        # --- NEW CONNECTIONS for Toolbar Buttons (Start/Stop Toggle & Test Flash) ---
        # --------------------------------------------------------------------

        # --- NEW CONNECTIONS for Toolbar Start/Stop Buttons ---
        if hasattr(self, 'toolbar_start_button') and self.toolbar_start_button:
            if self.dashboard_vm and hasattr(self.dashboard_vm, 'start_monitoring'):
                self.toolbar_start_button.clicked.connect(self.dashboard_vm.start_monitoring)
                self._logger.debug("Connected toolbar_start_button.clicked to DashboardVM.start_monitoring")
            else:
                self._logger.error(
                    "FAILED to connect toolbar_start_button.clicked: DashboardVM or start_monitoring slot missing.")

            if self.dashboard_vm and hasattr(self.dashboard_vm, 'can_start_monitoring_changed'):
                self.dashboard_vm.can_start_monitoring_changed.connect(self.toolbar_start_button.setEnabled)
                self._logger.debug(
                    "Connected DashboardVM.can_start_monitoring_changed to toolbar_start_button.setEnabled")
            else:
                self._logger.error(
                    "FAILED to connect can_start_monitoring_changed for toolbar_start_button: DashboardVM or signal missing.")
        else:
            self._logger.warning(
                "MainView: self.toolbar_start_button not found. Toolbar Start button connections skipped.")

        if hasattr(self, 'toolbar_stop_button') and self.toolbar_stop_button:
            if self.dashboard_vm and hasattr(self.dashboard_vm, 'stop_monitoring'):
                self.toolbar_stop_button.clicked.connect(self.dashboard_vm.stop_monitoring)
                self._logger.debug("Connected toolbar_stop_button.clicked to DashboardVM.stop_monitoring")
            else:
                self._logger.error(
                    "FAILED to connect toolbar_stop_button.clicked: DashboardVM or stop_monitoring slot missing.")

            if self.dashboard_vm and hasattr(self.dashboard_vm, 'can_stop_monitoring_changed'):
                self.dashboard_vm.can_stop_monitoring_changed.connect(self.toolbar_stop_button.setEnabled)
                self._logger.debug(
                    "Connected DashboardVM.can_stop_monitoring_changed to toolbar_stop_button.setEnabled")
            else:
                self._logger.error(
                    "FAILED to connect can_stop_monitoring_changed for toolbar_stop_button: DashboardVM or signal missing.")
        else:
            self._logger.warning(
                "MainView: self.toolbar_stop_button not found. Toolbar Stop button connections skipped.")

        # 3. Test Flash Button (if moved to toolbar)
        if hasattr(self, 'toolbar_test_flash_button') and self.toolbar_test_flash_button:
            # Connect button click to ViewModel's action slot
            if self.dashboard_vm and hasattr(self.dashboard_vm, 'test_flash_regions'):
                self.toolbar_test_flash_button.clicked.connect(self.dashboard_vm.test_flash_regions)
                self._logger.debug("Connected toolbar_test_flash_button.clicked to DashboardVM.test_flash_regions")
            else:
                self._logger.error(
                    "FAILED to connect toolbar_test_flash_button.clicked: DashboardVM or test_flash_regions slot missing.")

            # Connect ViewModel's state signal (for enablement) to the button's setEnabled slot
            if self.dashboard_vm and hasattr(self.dashboard_vm, 'can_test_flash_changed'):
                self.dashboard_vm.can_test_flash_changed.connect(self.toolbar_test_flash_button.setEnabled)
                self._logger.debug(
                    "Connected DashboardVM.can_test_flash_changed to toolbar_test_flash_button.setEnabled")
            else:
                self._logger.error(
                    "FAILED to connect can_test_flash_changed for toolbar_test_flash_button: DashboardVM or signal missing.")
        else:
            # This means the button wasn't created in _setup_ui, which is fine if you decided against moving it.
            self._logger.info(
                "MainView: self.toolbar_test_flash_button not found. Toolbar Test Flash button connections skipped.")

        self._logger.info("MainView signal connections process completed.")


    @Slot(bool)
    def _set_platform_combo_enabled_state(self, enabled: bool):
        """
        Sets the enabled state of the platform selection ComboBox.
        Also provides a tooltip when disabled.
        """
        if self.platform_combo:
            is_currently_enabled = self.platform_combo.isEnabled()
            if is_currently_enabled != enabled:  # Only update if state actually changes
                self.platform_combo.setEnabled(enabled)
                self._logger.info(f"Platform ComboBox enabled state set to: {enabled}")
                if not enabled:
                    self.platform_combo.setToolTip(
                        "Platform selection is disabled while monitoring is active.\n"
                        "Stop monitoring to change platforms."
                    )
                else:
                    self.platform_combo.setToolTip("")  # Clear tooltip
            else:
                self._logger.debug(f"Platform ComboBox already in desired enabled state: {enabled}. No change.")
        else:
            self._logger.error("MainView: platform_combo is None. Cannot set enabled state.")

    @Slot(str)
    def _handle_platform_selection_change(self, platform: str):
        if not platform or not self.main_view_model: return
        self.main_view_model.user_selected_platform(platform)

    @Slot(list)
    def _update_available_platforms(self, platforms: List[str]):
        if not self.platform_combo: return
        current_text = self.platform_combo.currentText()
        self.platform_combo.blockSignals(True)
        self.platform_combo.clear();
        self.platform_combo.addItems(platforms)
        if current_text in platforms:
            self.platform_combo.setCurrentText(current_text)
        elif platforms:
            self.platform_combo.setCurrentIndex(0)
        self.platform_combo.blockSignals(False)
        self._logger.debug(f"Platform combo box updated: {platforms}")

    @Slot(str)
    def _update_platform_combo(self, platform: str):
        if self.platform_combo and self.platform_combo.currentText() != platform:
            self.platform_combo.blockSignals(True)
            self.platform_combo.setCurrentText(platform or "")
            self.platform_combo.blockSignals(False)
            self._logger.debug(f"Platform combo display updated to: {platform}")

    def _get_default_status_style(self) -> str:
        is_dark = self.property("darkTheme") == True
        return self.DEFAULT_STATUS_STYLE_DARK if is_dark else self.DEFAULT_STATUS_STYLE_LIGHT

    def _get_info_busy_style(self) -> str:
        is_dark = self.property("darkTheme") == True
        return self.INFO_BUSY_STYLE_DARK if is_dark else self.INFO_BUSY_STYLE_LIGHT

    def _reset_main_status_label(self):
        if self.status_bar_main_status_label:
            self.status_bar_main_status_label.setText(self.DEFAULT_STATUS_TEXT)
            self.status_bar_main_status_label.setStyleSheet(self._get_default_status_style())

    @Slot(str, str)
    def _show_status_message(self, message: str, level: str):
        if not self.status_bar_main_status_label: return
        if self._status_clear_timer and self._status_clear_timer.isActive(): self._status_clear_timer.stop()
        persistent_message = False;
        timeout_ms = 5000
        is_dark = self.property("darkTheme") == True
        prefix, style_sheet_str = "", self._get_default_status_style()
        level_upper = level.upper()

        if level_upper == "ERROR":
            prefix, style_sheet_str = "⚠️ ", "color: white; font-weight: bold; padding: 2px 5px; background-color: #e74c3c; border-radius: 3px;"
            persistent_message = True
        elif level_upper == "WARNING":
            prefix, style_sheet_str = "⚠ ", "color: black; font-weight: bold; padding: 2px 5px; background-color: #f39c12; border-radius: 3px;"
            timeout_ms = 7000
        elif level_upper == "SUCCESS":
            prefix = "✓ "
            style_sheet_str = (
                "color: #ffffff; font-weight: bold; padding: 2px 5px; background-color: #22c55e; border-radius: 3px;" if is_dark else
                "color: white; font-weight: bold; padding: 2px 5px; background-color: #27ae60; border-radius: 3px;")
            timeout_ms = 5000
        elif level_upper == "BUSY" or level_upper == "INFO":
            prefix = "⏳ " if level_upper == "BUSY" else "ℹ️ "
            style_sheet_str = self._get_info_busy_style()
            if not message.endswith("..."): message += "..."

        self.status_bar_main_status_label.setText(f"{prefix}{message}")
        self.status_bar_main_status_label.setStyleSheet(style_sheet_str)

        if not persistent_message:
            if self._status_clear_timer is None:
                self._status_clear_timer = QTimer(self);
                self._status_clear_timer.setSingleShot(True)
                self._status_clear_timer.timeout.connect(self._reset_main_status_label)
            self._status_clear_timer.start(timeout_ms)
        elif self._status_clear_timer and self._status_clear_timer.isActive():
            self._status_clear_timer.stop()

    @Slot(str)
    def handle_tab_navigation_request(self, target_tab_key: str):
        if target_tab_key in self.tab_buttons and target_tab_key in self._tab_references:
            self._logger.info(f"Programmatic navigation to tab: {target_tab_key}")
            # self.tab_buttons[target_tab_key].setChecked(True) # QButtonGroup handles this on click
            self.tab_buttons[target_tab_key].click()  # Simulate click to trigger full logic
        else:
            self._logger.warning(f"Programmatic navigation requested to unknown tab key: '{target_tab_key}'")

    def closeEvent(self, event: QEvent):  # Added QEvent type hint
        self._logger.info("Close event received. Cleaning up...")
        try:
            if self._background_task_service:
                self._background_task_service.cancel_all_tasks()
                self._logger.debug("Background task cancellation requested.")
        except Exception as e:
            self._logger.error(f"Error cancelling background tasks on close: {e}", exc_info=True)
        finally:
            self._logger.info("Cleanup attempt finished. Accepting close event.")
            event.accept()

    @Slot(str)
    def _update_ui_for_theme_change(self, theme: str):
        if not self.main_view_model:
            self._logger.warning("MainVM not ready in _update_ui_for_theme_change.");
            return

        self._logger.debug(f"MainView: Updating UI elements for theme change to '{theme}'.")
        is_dark = (theme == "dark")

        # 1. Update Theme Toggle Button Icon
        if self.theme_toggle_button:
            icon_path = ":/icons/sun.svg" if is_dark else ":/icons/moon.svg"
            icon_color = QColor("#f0f0f0") if is_dark else QColor("#2d3436")
            tooltip = "Switch to Light Theme" if is_dark else "Switch to Dark Theme"
            try:
                self._logger.debug(f"Theme button path exists: {QFile.exists(icon_path)}")
                colored_icon = create_colored_svg_icon(icon_path, icon_color, QSize(18, 18))
                self.theme_toggle_button.setIcon(colored_icon)
                self.theme_toggle_button.setToolTip(tooltip)
            except Exception as e:
                self._logger.error(f"Error setting theme toggle icon: {e}", exc_info=True)

        # --- IMPROVED LOGO ICON UPDATE WITH DEBUGGING ---
        logo_icon_label = self.platform_toolbar.findChild(QLabel, "toolbarLogoIcon")
        if logo_icon_label:
            logo_icon_path = ":/icons/server.svg"  # Verify this path exists in resources.qrc
            self._logger.debug(f"Logo path exists: {QFile.exists(logo_icon_path)}")

            # Try reading and logging part of SVG
            try:
                file = QFile(logo_icon_path)
                if file.open(QIODevice.OpenModeFlag.ReadOnly | QIODevice.OpenModeFlag.Text):
                    svg_data = file.readAll().data().decode('utf-8')
                    file.close()
                    self._logger.debug(f"SVG sample (first 100 chars): {svg_data[:100]}")

                    # Check if SVG contains color attributes
                    contains_fill = "fill=" in svg_data
                    contains_stroke = "stroke=" in svg_data
                    contains_style = "style=" in svg_data
                    self._logger.debug(
                        f"SVG color attributes: fill={contains_fill}, stroke={contains_stroke}, style={contains_style}")
            except Exception as e:
                self._logger.error(f"Error inspecting SVG: {e}")

            # Use high contrast colors for better visibility
            logo_color = QColor("#ffffff") if is_dark else QColor("#000000")  # Pure white/black
            try:
                colored_logo_icon = create_colored_svg_icon(logo_icon_path, logo_color, QSize(20, 20))
                logo_icon_label.setPixmap(colored_logo_icon.pixmap(QSize(20, 20)))
                # Force immediate update
                logo_icon_label.update()
            except Exception as e:
                self._logger.error(f"Error setting toolbar logo icon: {e}", exc_info=True)
        # --- END IMPROVED LOGO ICON UPDATE ---

        # 2. Update 'darkTheme' property on MainView
        if self.property("darkTheme") != is_dark:
            self.setProperty("darkTheme", is_dark)
            self.style().unpolish(self)
            self.style().polish(self)
            self.update()
            self._logger.debug(f"MainView: 'darkTheme' property set to {is_dark} for MainView itself.")

        # Update Platform Icon
        platform_icon = self.findChild(QLabel, "platformIcon")
        if platform_icon:
            icon_color = QColor("#60a5fa") if is_dark else QColor("#2563eb")
            try:
                colored_icon = create_colored_svg_icon(":/icons/server.svg", icon_color, QSize(16, 16))
                platform_icon.setPixmap(colored_icon.pixmap(QSize(16, 16)))
            except Exception as e:
                self._logger.error(f"Error updating platform icon: {e}")

        # Update Platform Icon Container
        platform_icon_container = self.findChild(QWidget, "platformIconContainer")
        if platform_icon_container:
            bg_color = QColor(59, 130, 246, 40) if is_dark else QColor(59, 130, 246, 25)
            platform_icon_container.setStyleSheet(f"background-color: {bg_color.name(QColor.NameFormat.HexArgb)};")

        # 3. Update custom tab button icons and styles
        self._update_toolbar_tab_button_styles(self.current_active_tab_key())

        # 4. Update styles for default status messages
        self._reset_main_status_label()

        # 5. Force processing events to ensure updates are visible
        from PySide6.QtCore import QCoreApplication
        QCoreApplication.processEvents()

    @Slot(QPixmap)
    def _update_summary_region_tooltip(self, pixmap: QPixmap):
        if not self.status_bar_region_label: return
        if pixmap and not pixmap.isNull():
            tooltip_width = 200
            scaled_pixmap = pixmap.scaledToWidth(tooltip_width, Qt.AspectRatioMode.KeepAspectRatio,
                                                 Qt.TransformationMode.SmoothTransformation) \
                if pixmap.width() > tooltip_width else pixmap
            byte_array = QByteArray();
            buffer = QBuffer(byte_array)
            buffer.open(QIODevice.OpenModeFlag.WriteOnly);
            scaled_pixmap.save(buffer, "PNG");
            buffer.close()
            base64_data = byte_array.toBase64().data().decode('utf-8')
            tooltip_html = f"<img src='data:image/png;base64,{base64_data}'>"
            self.status_bar_region_label.setToolTip(tooltip_html)
        else:
            self.status_bar_region_label.setToolTip("P&L Monitor Region: Not defined or no preview available.")

    # --- New methods for Toolbar Tab Navigation ---
    @Slot()
    def _on_toolbar_tab_selected(self):
        clicked_button = self.sender()
        if not isinstance(clicked_button, QPushButton): return

        active_tab_name = None
        for name, button in self.tab_buttons.items():
            if button == clicked_button:
                active_tab_name = name
                if name in self._tab_references:
                    target_widget = self._tab_references[name]
                    if self.stacked_widget and self.stacked_widget.currentWidget() != target_widget:
                        self.stacked_widget.setCurrentWidget(target_widget)
                        self._logger.debug(f"Switched to tab: {name} via button click.")
                else:
                    self._logger.warning(f"Tab button '{name}' clicked, no corresponding view.")
                break

        if active_tab_name:
            self._update_toolbar_tab_button_styles(active_tab_name)

    @Slot(int)
    def _on_stacked_widget_changed(self, index: int):
        if not self.stacked_widget: return
        current_widget = self.stacked_widget.widget(index)
        active_tab_name = None
        for name, view_widget in self._tab_references.items():
            if view_widget == current_widget:
                active_tab_name = name
                break

        if active_tab_name:
            if not self.tab_buttons[active_tab_name].isChecked():
                self.tab_buttons[active_tab_name].setChecked(True)  # Sync button state
            self._update_toolbar_tab_button_styles(active_tab_name)  # Update styles
            self._logger.debug(f"StackedWidget changed to '{active_tab_name}', updated tab button styles.")

    def _update_toolbar_tab_button_styles(self, active_tab_name: Optional[str]):
        is_dark = self.property("darkTheme") == True
        # Define icon colors based on theme and active state
        active_icon_color = QColor("#60a5fa") if is_dark else QColor("#3498db")  # Active color
        inactive_icon_color = QColor("#9ca3af") if is_dark else QColor("#7f8c8d")  # Inactive color

        for name, button in self.tab_buttons.items():
            is_active = (name == active_tab_name)
            button.setProperty("activeTab", is_active)  # For QSS: QPushButton[activeTab="true"]

            icon_path = self._tab_button_icon_paths.get(name)
            if icon_path:
                current_icon_color = active_icon_color if is_active else inactive_icon_color
                try:
                    colored_icon = create_colored_svg_icon(icon_path, current_icon_color, QSize(16, 16))
                    button.setIcon(colored_icon)
                except Exception as e:
                    self._logger.error(f"Error setting icon for tab button '{name}': {e}")

            button.style().unpolish(button)
            button.style().polish(button)

    def current_active_tab_key(self) -> Optional[str]:
        """Helper to get the key of the currently active tab based on QStackedWidget."""
        if not self.stacked_widget: return None
        current_widget_in_stack = self.stacked_widget.currentWidget()
        for name, view_widget in self._tab_references.items():
            if view_widget == current_widget_in_stack:
                return name
        return None

    @Slot(str, str, bool, str)
    def _update_monitoring_action_button(self, text: str, icon_name: str, enabled: bool, style_key: str):
        if not self.monitoring_action_button:
            self._logger.error("MainView: monitoring_action_button is None, cannot update.")
            return

        self.monitoring_action_button.setText(text)
        self.monitoring_action_button.setEnabled(enabled)

        # --- Icon Logic ---
        icon_path = ""
        is_dark = self.property("darkTheme") == True
        # Define colors based on style_key and theme (simplified)
        # You might want to use colors from your ui_components.ActionButton/DangerButton if accessible
        color_map = {
            "action": QColor("#2ecc71") if is_dark else QColor("#27ae60"),  # Green
            "danger": QColor("#e74c3c") if is_dark else QColor("#c0392b"),  # Red
            "action_disabled": QColor("#7f8c8d")  # Grey
        }
        current_icon_color = color_map.get(style_key, color_map["action_disabled"])

        if icon_name == "play":
            icon_path = ":/icons/play.svg"
        elif icon_name == "stop-circle":
            icon_path = ":/icons/stop-circle.svg"

        if icon_path and QFile.exists(icon_path):
            try:
                colored_icon = create_colored_svg_icon(icon_path, current_icon_color,
                                                       self.monitoring_action_button.iconSize())
                self.monitoring_action_button.setIcon(colored_icon)
            except Exception as e:
                self._logger.error(f"Error setting icon '{icon_name}' for monitoring action button: {e}")
                self.monitoring_action_button.setIcon(QIcon())
        else:
            self.monitoring_action_button.setIcon(QIcon())
            if icon_path: self._logger.warning(f"Icon path not found for monitoring action button: {icon_path}")

        # --- Style Logic ---
        # Map style_key to QSS classes if your ActionButton, DangerButton are styled by class
        # For simplicity, we set a property that QSS can target: QPushButton[styleKey="danger"]
        self.monitoring_action_button.setProperty("styleKey", style_key)
        self.monitoring_action_button.style().unpolish(self.monitoring_action_button)
        self.monitoring_action_button.style().polish(self.monitoring_action_button)

        # self._logger.debug(f"MainView: Monitoring action button updated - Text: {text}, Icon: {icon_name}, Enabled: {enabled}, StyleKey: {style_key}")