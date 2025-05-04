# src/presentation/view_models/main_view_model.py

# src/presentation/view_models/main_view_model.py

import os
from typing import Optional, List, Dict, Any

# --- Qt Imports ---
from PySide6.QtCore import QObject, Signal, Slot

# --- Application Imports ---
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_config_repository_service import IConfigRepository
from src.domain.services.i_platform_selection_service import IPlatformSelectionService
from src.domain.services.i_region_service import IRegionService
from src.domain.services.i_profile_service import IProfileService
from src.domain.models.platform_profile import PlatformProfile # For default patterns comparison

class MainViewModel(QObject):
    """
    ViewModel for the MainView.

    Manages shared state like platform selection and provides formatted
    summary data for the MainView's toolbar.
    """

    # --- Signals for MainView UI updates ---
    available_platforms_changed = Signal(list) # List of platform names
    selected_platform_changed = Signal(str)   # Currently selected platform name for combo box sync

    summary_region_changed = Signal(str)      # Formatted region coordinates string
    summary_threshold_changed = Signal(str)   # Formatted threshold string (e.g., "$-100.00")
    summary_duration_changed = Signal(str)    # Formatted duration string (e.g., "15 min")
    summary_patterns_changed = Signal(str)    # Formatted patterns description (e.g., "Default", "Custom")

    # Signal to potentially pass status messages up if needed, though individual VMs might handle this
    # status_message_request = Signal(str, str) # message, level

    def __init__(self,
                 logger: ILoggerService,
                 config_repo: IConfigRepository,
                 platform_selection_service: IPlatformSelectionService,
                 region_service: IRegionService,
                 profile_service: IProfileService,
                 parent: Optional[QObject] = None):
        """Initialize the MainViewModel."""
        super().__init__(parent)
        self._logger = logger
        self._config_repo = config_repo
        self._platform_selection_service = platform_selection_service
        self._region_service = region_service
        self._profile_service = profile_service

        # --- Internal State ---
        self._available_platforms: List[str] = []
        self._selected_platform: Optional[str] = None

        # State for summary labels
        self._summary_region_text: str = "N/A"
        self._summary_threshold_text: str = "N/A"
        self._summary_duration_text: str = "N/A"
        self._summary_patterns_text: str = "N/A"

        self._logger.debug("Initializing MainViewModel...")

        # Connect to platform service changes
        self._platform_selection_service.register_platform_change_listener(
            self._handle_platform_change_from_service # Renamed slot for clarity
        )

        # Load initial state
        self._load_available_platforms()
        self._load_initial_platform_and_summary()

        self._logger.debug("MainViewModel initialized.")

    # --- Public Slots (Called by MainView) ---

    @Slot(str)
    def user_selected_platform(self, platform_name: str):
        """Handles platform selection change initiated by the user via the ComboBox."""
        self._logger.debug(f"MainViewModel: User selected platform '{platform_name}' in ComboBox.")
        # Check if it's actually a change
        if platform_name and platform_name != self._selected_platform:
            # Tell the service to update the platform
            set_result = self._platform_selection_service.set_current_platform(platform_name)
            if set_result.is_failure:
                # If setting fails (e.g., config save error), log it and potentially revert UI
                self._logger.error(f"Failed to set current platform via service: {set_result.error}")
                # Re-emit the *previous* platform to potentially reset the ComboBox
                self.selected_platform_changed.emit(self._selected_platform or "")
                # self.status_message_request.emit(f"Error setting platform: {set_result.error}", "ERROR")
            # If setting succeeded, the service will notify us via the listener
            # which triggers _handle_platform_change_from_service -> _update_summary
        else:
             self._logger.debug("User selection matches current platform, no action needed.")

    @Slot()
    def refresh_summary_data(self):
         """Explicitly refreshes summary data for the current platform."""
         self._logger.debug(f"Explicit refresh summary data requested for {self._selected_platform}")
         self._update_summary(self._selected_platform)

    @Slot()
    def refresh_ui_signals(self):
        """Emits all signals reflecting the current state for initial MainView UI sync."""
        self._logger.debug(f"MainViewModel Refreshing UI signals for {self._selected_platform or 'None'}")
        # Emit signals based on current internal state
        self.available_platforms_changed.emit(self._available_platforms)
        self.selected_platform_changed.emit(self._selected_platform or "")
        self.summary_region_changed.emit(self._summary_region_text)
        self.summary_threshold_changed.emit(self._summary_threshold_text)
        self.summary_duration_changed.emit(self._summary_duration_text)
        self.summary_patterns_changed.emit(self._summary_patterns_text)
    # --- Internal Slots / Methods ---

    @Slot(str)
    def _handle_platform_change_from_service(self, platform: str):
        """Handles platform change notifications from the PlatformSelectionService."""
        self._logger.debug(f"MainViewModel: Received platform change from service: {platform}")
        if platform != self._selected_platform:
            self._selected_platform = platform
            self.selected_platform_changed.emit(platform or "") # Update ComboBox display
            self._update_summary(platform) # Update summary labels
        else:
            self._logger.debug("Platform change notification matches current state.")

    def _load_available_platforms(self):
        """Loads the list of available platforms."""
        self._available_platforms = self._platform_selection_service.get_available_platforms()
        self.available_platforms_changed.emit(self._available_platforms)
        self._logger.debug(f"Loaded available platforms: {self._available_platforms}")

    def _load_initial_platform_and_summary(self):
        """Gets the initially selected platform and loads its summary data."""
        initial_platform = self._platform_selection_service.get_current_platform()
        self._selected_platform = initial_platform
        # Emit initial platform selection for ComboBox sync
        self.selected_platform_changed.emit(initial_platform or "")
        # Load and emit initial summary data
        self._update_summary(initial_platform)

    def _update_summary(self, platform: Optional[str]):
        """Fetches and updates all summary data for the given platform."""
        self._logger.debug(f"Updating summary display for platform: {platform or 'None'}")

        if not platform:
            # Reset summary labels if no platform is selected
            self._summary_region_text = "N/A"
            self._summary_threshold_text = "N/A"
            self._summary_duration_text = "N/A"
            self._summary_patterns_text = "N/A"
        else:
            # Fetch data from services/repository
            # --- Region ---
            region_res = self._region_service.get_monitor_region(platform)
            if region_res.is_success and region_res.value:
                coords = region_res.value.coordinates
                self._summary_region_text = f"({coords[0]},{coords[1]},{coords[2]},{coords[3]})"
            else:
                self._summary_region_text = "Not Defined"

            # --- Threshold ---
            threshold_res = self._config_repo.get_platform_stop_loss_threshold(platform)
            threshold_val = threshold_res.value if threshold_res.is_success else self._config_repo.DEFAULT_PLATFORM_THRESHOLD
            self._summary_threshold_text = f"${threshold_val:,.2f}"

            # --- Duration ---
            duration_res = self._config_repo.get_platform_lockout_duration(platform)
            duration_val = duration_res.value if duration_res.is_success else self._config_repo.DEFAULT_PLATFORM_DURATION
            self._summary_duration_text = f"{duration_val} min"

            # --- Patterns ---
            profile_res = self._profile_service.get_profile(platform)
            patterns_dict = {}
            if profile_res.is_success:
                patterns_dict = profile_res.value.numeric_patterns or {}
            # Use helper to format description
            self._summary_patterns_text = self._format_patterns_description(patterns_dict)

        # --- Emit signals for the summary bar ---
        self.summary_region_changed.emit(self._summary_region_text)
        self.summary_threshold_changed.emit(self._summary_threshold_text)
        self.summary_duration_changed.emit(self._summary_duration_text)
        self.summary_patterns_changed.emit(self._summary_patterns_text)

    def _format_patterns_description(self, patterns: Dict[str, str]) -> str:
        """Helper function to create a short description of the OCR number patterns."""
        # This logic is moved from MainView._update_patterns_label_from_dict
        description = "N/A"
        patterns = patterns or {}
        try:
            # Get default patterns for comparison
            default_patterns_dict = self._profile_service._get_default_patterns_for_platform(None)
            is_default = (patterns == default_patterns_dict)

            if not patterns or is_default:
                description = "Default"
            elif len(patterns) == 1 and "dollar" in patterns: description = "Currency $"
            elif len(patterns) == 1 and "negative" in patterns: description = "ParensNeg ()"
            elif len(patterns) == 1 and "negative_dash" in patterns: description = "DashNeg -"
            elif len(patterns) == 1 and "regular" in patterns: description = "Number +/-"
            else: description = "Custom"
        except Exception as e:
            self._logger.error(f"Error formatting pattern description: {e}", exc_info=True)
            description = "Error"
        return description