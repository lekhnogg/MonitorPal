# src/presentation/view_models/main_view_model.py

import os
from typing import Optional, List, Dict, Any, Iterable

# --- Qt Imports ---
from PySide6.QtCore import QObject, Signal, Slot # Ensure Signal is from QtCore
from PySide6.QtWidgets import QApplication, QWidget

# --- Application Imports ---
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_config_repository_service import IConfigRepository
from src.domain.services.i_platform_selection_service import IPlatformSelectionService
from src.domain.services.i_region_service import IRegionService
from src.domain.services.i_profile_service import IProfileService
from src.presentation.styles.style_manager import StyleManager

class MainViewModel(QObject): # Ensure QObject inheritance
    """
    ViewModel for the MainView.
    Manages shared state, provides summary data, and handles theme toggling.
    """

    # --- Signals MUST be defined at the CLASS LEVEL, outside of __init__ ---
    available_platforms_changed = Signal(list)
    selected_platform_changed = Signal(str)

    summary_region_changed = Signal(str)
    summary_threshold_changed = Signal(str)
    summary_duration_changed = Signal(str)
    summary_patterns_changed = Signal(str)

    current_theme_changed = Signal(str)     # Emits "light" or "dark"
    theme_refresh_requested = Signal()      # <<< THIS SIGNAL MUST BE HERE

    def __init__(self,
                 logger: ILoggerService,
                 config_repo: IConfigRepository,
                 platform_selection_service: IPlatformSelectionService,
                 region_service: IRegionService,
                 profile_service: IProfileService,
                 parent: Optional[QObject] = None):
        super().__init__(parent) # Crucial for QObject functionality (signals/slots)
        self._logger = logger
        self._config_repo = config_repo
        self._platform_selection_service = platform_selection_service
        self._region_service = region_service
        self._profile_service = profile_service

        # --- Internal State ---
        self._available_platforms: List[str] = []
        self._selected_platform: Optional[str] = None
        self._current_theme: str = "dark" # Internal default, overridden by config

        self._summary_region_text: str = "N/A"
        self._summary_threshold_text: str = "N/A"
        self._summary_duration_text: str = "N/A"
        self._summary_patterns_text: str = "N/A"

        self._logger.debug("Initializing MainViewModel...")

        self._platform_selection_service.register_platform_change_listener(
            self._handle_platform_change_from_service
        )

        self._load_available_platforms()
        self._load_initial_platform_and_summary()
        self._load_initial_theme()

        self._logger.debug("MainViewModel initialized.")

    def _load_initial_theme(self):
        self._current_theme = self._config_repo.get_global_setting("theme", "dark")
        self._logger.info(f"MainViewModel: Initial theme from config is '{self._current_theme}'.")

    def get_current_theme(self) -> str:
        return self._current_theme

    @Slot()
    def toggle_theme(self):
        new_theme = "light" if self._current_theme == "dark" else "dark"
        self._logger.info(f"User initiated theme toggle from '{self._current_theme}' to '{new_theme}'.")

        result = self._config_repo.set_global_setting("theme", new_theme)
        if result.is_success:
            self._current_theme = new_theme
            self._logger.info(f"Theme preference saved to config: '{self._current_theme}'.")

            app = QApplication.instance()
            if app:
                StyleManager.apply_application_style(app, use_dark_theme=(self._current_theme == "dark"))
                self._logger.debug("Global stylesheet re-applied for new theme.")
                self._update_view_theme_properties(app.topLevelWidgets(), self._current_theme == "dark")
            else:
                self._logger.error("Could not get QApplication instance to re-apply theme and update properties.")

            self.current_theme_changed.emit(self._current_theme)
            self.theme_refresh_requested.emit() # <<< Emitting the signal
            self._logger.info(f"Theme successfully toggled and UI update signaled: {self._current_theme}")
        else:
            self._logger.error(f"Failed to save new theme '{new_theme}' to config: {result.error}")

    def _update_view_theme_properties(self, root_widgets: Iterable[QWidget], is_dark: bool):
        from src.presentation.views.main_view import MainView
        from src.presentation.views.dashboard_view import DashboardView
        from src.presentation.views.settings_view import SettingsView
        from src.presentation.views.region_setup_view import RegionSetupView
        from src.presentation.views.ocr_calibration_view import OcrCalibrationView
        from src.presentation.views.history_view import HistoryView

        target_view_types = (
            MainView, DashboardView, SettingsView, RegionSetupView,
            OcrCalibrationView, HistoryView
        )
        widgets_to_process = list(root_widgets)
        processed_widgets = set()

        while widgets_to_process:
            widget = widgets_to_process.pop(0)
            if widget in processed_widgets:
                continue
            processed_widgets.add(widget)

            if isinstance(widget, target_view_types):
                current_prop = widget.property("darkTheme")
                if current_prop is None or current_prop != is_dark: # Check if update is needed
                    widget.setProperty("darkTheme", is_dark)
                    widget.style().unpolish(widget)
                    widget.style().polish(widget)
                    widget.update()
                    self._logger.debug(f"Updated 'darkTheme' property on "
                                       f"'{widget.objectName() or widget.__class__.__name__}' to {is_dark}.")

            for child_widget in widget.findChildren(QWidget):
                if child_widget not in processed_widgets:
                    widgets_to_process.append(child_widget)

    @Slot(str)
    def user_selected_platform(self, platform_name: str): # Renamed from _user_selected_platform
        self._logger.debug(f"MainViewModel: User selected platform '{platform_name}' in ComboBox.")
        if platform_name and platform_name != self._selected_platform:
            set_result = self._platform_selection_service.set_current_platform(platform_name)
            if set_result.is_failure:
                self._logger.error(f"Failed to set current platform via service: {set_result.error}")
                self.selected_platform_changed.emit(self._selected_platform or "")
        else:
             self._logger.debug("User selection matches current platform or is empty, no change propagated.")

    @Slot()
    def refresh_summary_data(self):
         self._logger.debug(f"Explicit refresh summary data requested for {self._selected_platform}")
         self._update_summary(self._selected_platform)

    @Slot()
    def refresh_ui_signals(self):
        self._logger.debug(f"MainViewModel Refreshing UI signals for {self._selected_platform or 'None'}")
        self.available_platforms_changed.emit(self._available_platforms)
        self.selected_platform_changed.emit(self._selected_platform or "")
        self.summary_region_changed.emit(self._summary_region_text)
        self.summary_threshold_changed.emit(self._summary_threshold_text)
        self.summary_duration_changed.emit(self._summary_duration_text)
        self.summary_patterns_changed.emit(self._summary_patterns_text)
        self.current_theme_changed.emit(self._current_theme)

    @Slot(str)
    def _handle_platform_change_from_service(self, platform: str):
        self._logger.debug(f"MainViewModel: Received platform change from service: {platform}")
        if platform != self._selected_platform:
            self._selected_platform = platform
            self.selected_platform_changed.emit(platform or "")
            self._update_summary(platform)
        else:
            self._logger.debug("Platform change notification matches current state or platform is unchanged.")

    def _load_available_platforms(self):
        self._available_platforms = self._platform_selection_service.get_available_platforms()
        self.available_platforms_changed.emit(self._available_platforms)
        self._logger.debug(f"Loaded available platforms: {self._available_platforms}")

    def _load_initial_platform_and_summary(self):
        initial_platform = self._platform_selection_service.get_current_platform()
        self._selected_platform = initial_platform
        # self.selected_platform_changed.emit(initial_platform or "") # refresh_ui_signals will do this
        self._update_summary(initial_platform)

    def _update_summary(self, platform: Optional[str]):
        self._logger.debug(f"Updating summary display for platform: {platform or 'None'}")
        if not platform:
            self._summary_region_text = "N/A"
            self._summary_threshold_text = "N/A"
            self._summary_duration_text = "N/A"
            self._summary_patterns_text = "N/A"
        else:
            region_res = self._region_service.get_monitor_region(platform)
            if region_res.is_success and region_res.value:
                coords = region_res.value.coordinates
                self._summary_region_text = f"({coords[0]},{coords[1]},{coords[2]},{coords[3]})"
            else:
                self._summary_region_text = "Not Defined"

            threshold_res = self._config_repo.get_platform_stop_loss_threshold(platform)
            threshold_val = threshold_res.value if threshold_res.is_success else self._config_repo.DEFAULT_PLATFORM_THRESHOLD
            self._summary_threshold_text = f"${threshold_val:,.2f}"

            duration_res = self._config_repo.get_platform_lockout_duration(platform)
            duration_val = duration_res.value if duration_res.is_success else self._config_repo.DEFAULT_PLATFORM_DURATION
            self._summary_duration_text = f"{duration_val} min"

            profile_res = self._profile_service.get_profile(platform)
            patterns_dict = {}
            if profile_res.is_success and profile_res.value:
                patterns_dict = profile_res.value.numeric_patterns or {}
            self._summary_patterns_text = self._format_patterns_description(patterns_dict, platform)

        # No need to emit here if refresh_ui_signals covers these or they are set before view is shown
        # self.summary_region_changed.emit(self._summary_region_text)
        # self.summary_threshold_changed.emit(self._summary_threshold_text)
        # self.summary_duration_changed.emit(self._summary_duration_text)
        # self.summary_patterns_changed.emit(self._summary_patterns_text)

    def _format_patterns_description(self, patterns: Dict[str, str], platform_name: Optional[str]) -> str:
        description = "N/A"
        patterns = patterns or {}
        try:
            default_patterns_dict = self._profile_service._get_default_patterns_for_platform(platform_name)
            is_default = (patterns == default_patterns_dict)

            if not patterns or is_default: description = "Default"
            elif len(patterns) == 1 and "dollar" in patterns: description = "Currency $"
            elif len(patterns) == 1 and "negative" in patterns: description = "ParensNeg ()"
            elif len(patterns) == 1 and "negative_dash" in patterns: description = "DashNeg -"
            elif len(patterns) == 1 and "regular" in patterns: description = "Number +/-"
            else: description = "Custom"
        except Exception as e:
            self._logger.error(f"Error formatting pattern description for platform '{platform_name}': {e}", exc_info=True)
            description = "Error"
        return description