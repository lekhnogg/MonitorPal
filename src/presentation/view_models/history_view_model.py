# src/presentation/view_models/history_view_model.py

import time
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta

# --- Qt Imports ---
from PySide6.QtCore import QObject, Signal, Slot

# --- Application Imports ---
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_config_repository_service import IConfigRepository
from src.domain.services.i_platform_selection_service import IPlatformSelectionService
# Import other services if needed, e.g., a dedicated History Service
# from src.domain.services.i_history_service import IHistoryService
from src.domain.common.result import Result

# Define data structures for clarity
GraphDataType = List[Tuple[float, float]] # Example: [(timestamp, pnl_value), ...]
SessionHistoryType = List[Dict[str, Any]] # Example: [{'date': '...', 'start_time': '...', ...}, ...]

class HistoryViewModel(QObject):
    """
    ViewModel for the History tab.

    Manages fetching, processing, and exposing historical monitoring data
    for display in graphs and tables.
    """

    # --- Signals for View updates ---
    # Graph Data
    pnl_graph_data_updated = Signal(object) # Emits GraphDataType (list of tuples)
    graph_time_range_options_changed = Signal(list) # e.g., ["Last Hour", "Last 4 Hours", "Today"]
    graph_current_time_range_changed = Signal(str)
    graph_threshold_line_visibility_changed = Signal(bool)
    graph_threshold_value_changed = Signal(float) # To draw the line

    # Session History Table
    session_history_updated = Signal(object) # Emits SessionHistoryType (list of dicts)

    # Actions / Status
    can_clear_history_changed = Signal(bool)
    can_generate_report_changed = Signal(bool)
    status_message_changed = Signal(str, str) # message, level

    def __init__(self,
                 logger: ILoggerService,
                 config_repo: IConfigRepository, # Needed for threshold, maybe history source?
                 platform_selection_service: IPlatformSelectionService,
                 # history_service: Optional[IHistoryService] = None, # Optional dedicated service
                 parent: Optional[QObject] = None):
        """
        Initialize the HistoryViewModel.
        """
        super().__init__(parent)
        self._logger = logger
        self._config_repo = config_repo
        self._platform_selection_service = platform_selection_service
        # self._history_service = history_service # Store if using dedicated service

        # --- Internal State ---
        self._selected_platform: Optional[str] = None
        self._graph_data: GraphDataType = []
        self._session_history: SessionHistoryType = []
        self._current_time_range: str = "Last 4 Hours" # Default time range
        self._time_range_options: List[str] = ["Last Hour", "Last 4 Hours", "Today", "Yesterday", "Last 7 Days"]
        self._show_threshold_line: bool = True
        self._current_threshold: float = 0.0

        self._logger.debug("Initializing HistoryViewModel...")
        self._platform_selection_service.register_platform_change_listener(
            self._handle_platform_selection_change
        )
        initial_platform = self._platform_selection_service.get_current_platform()
        self._load_history_for_platform(initial_platform) # Load initial state
        self._logger.debug("HistoryViewModel initialized.")


    # --- Command Slots (Called by the View) ---

    @Slot(str)
    def set_graph_time_range(self, time_range: str):
        """Sets the time range for the graph and triggers data reload."""
        if time_range != self._current_time_range and time_range in self._time_range_options:
            self._logger.info(f"Setting graph time range to: {time_range}")
            self._current_time_range = time_range
            self.graph_current_time_range_changed.emit(self._current_time_range)
            self._load_graph_data() # Reload graph data for the new range
        else:
            self._logger.debug(f"Time range unchanged or invalid: {time_range}")

    @Slot(bool)
    def set_threshold_line_visibility(self, visible: bool):
        """Sets the visibility of the threshold line on the graph."""
        if visible != self._show_threshold_line:
            self._show_threshold_line = visible
            self.graph_threshold_line_visibility_changed.emit(self._show_threshold_line)

    @Slot()
    def clear_history(self):
        """Clears the history data for the current platform."""
        if not self._selected_platform:
            self.status_message_changed.emit("No platform selected.", "ERROR")
            return

        # TODO: Implement history clearing logic
        # This would likely involve:
        # 1. Confirmation dialog via UIService.
        # 2. Calling a method on ConfigRepository or a dedicated HistoryService
        #    to delete the relevant data (e.g., monitoring log files, database entries).
        # 3. Reloading the (now empty) history data.
        self._logger.warning(f"Clear History for {self._selected_platform} requested (Not Implemented Yet).")
        self.status_message_changed.emit("Clear History feature not yet implemented.", "INFO")
        # Example of reloading after clearing:
        # self._load_history_for_platform(self._selected_platform)

    @Slot()
    def generate_report(self):
        """Generates a report based on the current history view."""
        if not self._selected_platform:
            self.status_message_changed.emit("No platform selected.", "ERROR")
            return

        # TODO: Implement report generation logic
        # This could involve:
        # 1. Selecting a file path via UIService.select_save_file(...)
        # 2. Formatting the current _session_history and/or _graph_data.
        # 3. Writing the data to a file (e.g., CSV, PDF).
        self._logger.warning(f"Generate Report for {self._selected_platform} requested (Not Implemented Yet).")
        self.status_message_changed.emit("Generate Report feature not yet implemented.", "INFO")

    @Slot(int) # Assuming the View passes the row index
    def show_session_details(self, row_index: int):
        """Shows detailed information about a specific historical session."""
        if row_index < 0 or row_index >= len(self._session_history):
            self._logger.warning(f"Invalid row index for session details: {row_index}")
            return

        session_data = self._session_history[row_index]
        # TODO: Implement details display
        # This could involve:
        # 1. Creating a new dialog window.
        # 2. Passing `session_data` to the dialog.
        # 3. Displaying details like specific alerts, min/max P&L during session, etc.
        self._logger.warning(f"Show Session Details requested for row {row_index} (Not Implemented Yet). Data: {session_data}")
        self.status_message_changed.emit(f"Details view for session on {session_data.get('date')} not yet implemented.", "INFO")

    @Slot()
    def refresh_ui_signals(self):
        """Emits all signals reflecting the current state for initial UI sync."""
        self._logger.debug(f"HistoryViewModel Refreshing UI signals for {self._selected_platform or 'None'}")
        # Emit all relevant signals based on current internal state
        self.pnl_graph_data_updated.emit(self._graph_data)
        self.graph_time_range_options_changed.emit(self._time_range_options)
        self.graph_current_time_range_changed.emit(self._current_time_range)
        self.graph_threshold_line_visibility_changed.emit(self._show_threshold_line)
        self.graph_threshold_value_changed.emit(self._current_threshold)
        self.session_history_updated.emit(self._session_history)
        # Calculate button states based on current data
        has_data = bool(self._graph_data) or bool(self._session_history)
        self.can_clear_history_changed.emit(has_data)
        self.can_generate_report_changed.emit(has_data)

    # --- Private Helper / Update Methods ---



    @Slot(str)
    def _handle_platform_selection_change(self, platform: str):
        """Reloads history when the globally selected platform changes."""
        self._logger.debug(f"HistoryViewModel received platform change: {platform}")
        self._load_history_for_platform(platform)

    def _load_history_for_platform(self, platform: str):
        """Loads graph and session data for the specified platform."""
        self._selected_platform = platform
        self._logger.info(f"Loading history for platform: {platform}")

        # Reset state before loading
        self._graph_data = []
        self._session_history = []
        # Keep button states disabled until data potentially loaded
        # self.can_clear_history_changed.emit(False)
        # self.can_generate_report_changed.emit(False)

        if not platform:
            # Clear displays if no platform selected
            self.pnl_graph_data_updated.emit(self._graph_data)
            self.session_history_updated.emit(self._session_history)
            self.graph_threshold_value_changed.emit(0.0) # Reset threshold line value
            self.can_clear_history_changed.emit(False) # Disable buttons
            self.can_generate_report_changed.emit(False)
            return

        # --- Load PLATFORM-SPECIFIC Threshold for Graph ---
        threshold_res = self._config_repo.get_platform_stop_loss_threshold(platform)
        # Use default from repo if loading fails
        self._current_threshold = threshold_res.value if threshold_res.is_success else self._config_repo.DEFAULT_PLATFORM_THRESHOLD
        if threshold_res.is_failure:
            self._logger.warning(f"History View: Failed load threshold for {platform}: {threshold_res.error}. Using default.")
        # Emit the threshold value for the graph line
        self.graph_threshold_value_changed.emit(self._current_threshold)
        # --- END Load Threshold ---

        # --- Load Graph and Session Data ---
        # (Keep your existing logic or placeholder logic here)
        self._load_graph_data()
        self._load_session_history()

        # --- Update Button States based on loaded data ---
        has_data = bool(self._graph_data) or bool(self._session_history)
        self.can_clear_history_changed.emit(has_data)
        self.can_generate_report_changed.emit(has_data)

        # --- Emit other initial states for the view ---
        self.graph_time_range_options_changed.emit(self._time_range_options)
        self.graph_current_time_range_changed.emit(self._current_time_range)
        self.graph_threshold_line_visibility_changed.emit(self._show_threshold_line)


    def _load_graph_data(self):
        """Loads P&L graph data based on the current platform and time range."""
        if not self._selected_platform:
            self.pnl_graph_data_updated.emit([])
            return

        self._logger.debug(f"Loading graph data for {self._selected_platform} - Range: {self._current_time_range}")

        # --- Placeholder Data Generation ---
        # Replace this with actual data fetching logic
        end_time = time.time()
        start_time = self._calculate_start_time(end_time, self._current_time_range)
        num_points = 100
        timestamps = [start_time + i * (end_time - start_time) / num_points for i in range(num_points)]
        # Simulate P&L fluctuating around -50 with noise and occasional dips
        pnl_values = [
            -50 + 20 * ((i / num_points) - 0.5) + 15 * (time.time() % (i + 1)) / (i + 1) - (20 if i % 20 == 0 else 0)
            for i in range(num_points)
        ]
        self._graph_data = list(zip(timestamps, pnl_values))
        # --- End Placeholder ---

        self.pnl_graph_data_updated.emit(self._graph_data)
        self._logger.debug(f"Loaded {len(self._graph_data)} points for graph.")


    def _load_session_history(self):
        """Loads the session history table data."""
        if not self._selected_platform:
            self.session_history_updated.emit([])
            return

        self._logger.debug(f"Loading session history for {self._selected_platform}")

        # --- Placeholder Data Generation ---
        # Replace this with actual data fetching logic
        self._session_history = [
            {'date': '2023-10-27', 'start_time': '09:30 AM', 'duration': '2h 45m', 'min_pnl': '-$134.50', 'threshold': f"{self._current_threshold:,.2f}", 'locked': True},
            {'date': '2023-10-26', 'start_time': '10:15 AM', 'duration': '3h 20m', 'min_pnl': '-$87.25', 'threshold': f"{self._current_threshold:,.2f}", 'locked': False},
            {'date': '2023-10-25', 'start_time': '09:45 AM', 'duration': '4h 10m', 'min_pnl': '-$45.75', 'threshold': f"{self._current_threshold:,.2f}", 'locked': False},
        ]
        # --- End Placeholder ---

        self.session_history_updated.emit(self._session_history)
        self._logger.debug(f"Loaded {len(self._session_history)} session history entries.")


    def _calculate_start_time(self, end_time: float, time_range: str) -> float:
        """Helper to calculate start timestamp based on time range string."""
        now = datetime.fromtimestamp(end_time)
        if time_range == "Last Hour":
            return end_time - 3600
        elif time_range == "Last 4 Hours":
            return end_time - (4 * 3600)
        elif time_range == "Today":
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return today_start.timestamp()
        elif time_range == "Yesterday":
            yesterday = now - timedelta(days=1)
            yesterday_start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            return yesterday_start.timestamp()
        elif time_range == "Last 7 Days":
            return end_time - (7 * 24 * 3600)
        else: # Default to Last 4 Hours
            return end_time - (4 * 3600)