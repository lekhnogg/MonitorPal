# src/presentation/view_models/history_view_model.py

import time
import os  # For file path manipulation in export
import csv
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta

# --- Qt Imports ---
from PySide6.QtCore import QObject, Signal, Slot

# --- Application Imports ---
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_config_repository_service import IConfigRepository
from src.domain.services.i_platform_selection_service import IPlatformSelectionService
from src.domain.services.i_history_service import IHistoryService
from src.domain.services.i_ui_service import IUIService  # For file dialog
from src.domain.common.result import Result

GraphDataType = List[Tuple[float, float]]
SessionHistoryType = List[Dict[str, Any]]


class HistoryViewModel(QObject):
    # --- Signals for View updates ---
    # Graph Data
    pnl_graph_data_updated = Signal(object)  # Emits GraphDataType (list of tuples)
    #graph_time_range_options_changed = Signal(list)  # e.g., ["Session"]
    #graph_current_time_range_changed = Signal(str)
    graph_threshold_line_visibility_changed = Signal(bool)
    graph_threshold_value_changed = Signal(float)  # To draw the line

    # Session History Table
    session_history_updated = Signal(object)  # Emits SessionHistoryType (list of dicts)

    # Actions / Status
    can_clear_history_changed = Signal(bool)
    can_generate_report_changed = Signal(bool)
    status_message_changed = Signal(str, str)  # message, level

    def __init__(self,
                 logger: ILoggerService,
                 config_repo: IConfigRepository,
                 platform_selection_service: IPlatformSelectionService,
                 history_service: IHistoryService,  # Already added
                 ui_service: IUIService,  # <<< ADD UIService for file dialogs
                 parent: Optional[QObject] = None):
        super().__init__(parent)
        self._logger = logger
        self._config_repo = config_repo
        self._platform_selection_service = platform_selection_service
        self._history_service = history_service  # Already stored
        self._ui_service = ui_service  # <<< STORE UIService

        # --- Internal State ---
        self._selected_platform: Optional[str] = None
        self._graph_data: GraphDataType = []
        self._session_history: SessionHistoryType = []  # List of formatted dicts for the table
        self._raw_session_summaries: List[Dict[str, Any]] = []  # Store raw summaries from service
        self._current_time_range: str = "Last 4 Hours"  # Default, though less relevant if graph is per-session
        self._time_range_options: List[str] = ["Session"]  # Simplified for per-session graph
        self._show_threshold_line: bool = True
        self._current_graph_threshold: float = 0.0  # Threshold for the currently displayed graph

        self._logger.debug("Initializing HistoryViewModel...")
        self._platform_selection_service.register_platform_change_listener(
            self._handle_platform_selection_change
        )

        # --- Connect to HistoryService's signal ---
        if isinstance(self._history_service, QObject) and hasattr(self._history_service, 'session_data_changed'):
            # Type cast for signal connection if PyCharm complains, or use # type: ignore
            qobject_history_service = self._history_service  # type: IHistoryService & QObject
            qobject_history_service.session_data_changed.connect(self._trigger_data_load_from_service_signal)
            self._logger.debug("Connected to HistoryService.session_data_changed signal.")
        else:
            self._logger.warning(
                "HistoryService is not a QObject or lacks session_data_changed signal. History will not auto-update.")
        # --- End Connection ---

        initial_platform = self._platform_selection_service.get_current_platform()
        self._load_history_for_platform(initial_platform)
        self._logger.debug("HistoryViewModel initialized.")

    @Slot()
    def _trigger_data_load_from_service_signal(self):
        self._logger.debug("HistoryViewModel: Received session_data_changed signal from HistoryService. Refreshing.")
        # Reload for the *currently selected platform* in this view
        self._load_history_for_platform(self._selected_platform)

    @Slot(str)
    def set_graph_time_range(self, time_range: str):
        # This might be less relevant if graph is always per-selected-session
        # For now, we can keep it simple or even remove if time_range_combo is removed.
        if time_range != self._current_time_range and time_range in self._time_range_options:
            self._logger.info(f"Graph time range changed to: {time_range}")
            self._current_time_range = time_range
            self.graph_current_time_range_changed.emit(self._current_time_range)
            # If a session is selected, reload its graph data (though typically "Session" will be the only option)
            # For now, this method might not do much if the graph always shows the selected session.
            if self._current_time_range == "Session" and self.history_table.selectedItems():  # Assuming history_table is accessible
                # This logic is better handled in load_graph_for_selected_session
                pass

    @Slot(bool)
    def set_threshold_line_visibility(self, visible: bool):
        if visible != self._show_threshold_line:
            self._show_threshold_line = visible
            self.graph_threshold_line_visibility_changed.emit(self._show_threshold_line)

    @Slot()
    def clear_history(self):
        if not self._selected_platform:
            msg = "No platform selected to clear history for."
            self.status_message_changed.emit(msg, "WARNING")
            self._logger.warning(msg)
            return

        confirm_res = self._ui_service.show_confirmation(
            "Confirm Clear History",
            f"Are you sure you want to clear all session history for {self._selected_platform} (from this app run)?\nThis action cannot be undone."
        )
        if confirm_res.is_success and confirm_res.value:
            self._logger.info(f"User confirmed clearing history for {self._selected_platform}.")
            # For in-memory, we might clear all or filter by platform if service supported it
            # Current MemoryHistoryService clears all.
            self._history_service.clear_all_session_data()  # Clears all data in MemoryHistoryService
            self._load_history_for_platform(self._selected_platform)  # Reload (will be empty)
            self.status_message_changed.emit(f"History cleared for {self._selected_platform}.", "SUCCESS")
        else:
            self.status_message_changed.emit("Clear history cancelled.", "INFO")

    @Slot()
    def generate_report(self):
        if not self._selected_platform:
            self.status_message_changed.emit("No platform selected.", "ERROR");
            return

        # Determine which session to export - let's assume the selected one for now
        # This requires the View to tell us which one is selected.
        # For now, let's try to get the session_id from the last graph load,
        # or default to exporting all summaries if no specific session is "active" for graph.

        # --- This part needs refinement based on how you want to select the export target ---
        # For now, let's just try to enable the dialog.
        # If you want to export the "graphed" session:
        # session_id_to_export = None
        # if self._graph_data and self._raw_session_summaries: # Check if graph has data from a loaded session
        #     # This is a bit indirect. It might be better to store the
        #     # last_selected_session_id when show_session_details is called.
        #     # For now, we'll just make a placeholder.
        #     pass # Needs a way to get the ID of the session whose data is in _graph_data

        # If exporting ALL summaries for the current platform (as previously)
        default_filename_base = f"MonitorPal_History_{self._selected_platform}_{datetime.now().strftime('%Y%m%d')}"
        # --- End Refinement ---

        # --- MODIFIED: Call select_save_file ---
        file_path_res = self._ui_service.select_save_file(  # <<< --- CHANGED METHOD NAME
            title="Save Session History Report",
            filter_pattern="CSV files (*.csv);;All Files (*)",
            default_filename=f"{default_filename_base}.csv"  # Pass the full suggested filename
        )
        # --- END MODIFICATION ---

        if file_path_res.is_success and file_path_res.value:
            file_path = file_path_res.value
            # Ensure .csv if user didn't type it
            if not file_path.lower().endswith(".csv"):
                file_path += ".csv"

            # --- Decide what to export. For now, simplified to export summaries of current platform ---
            # You could later have a self.last_selected_session_id for detailed export
            sessions_to_export_summaries = [
                s for s in self._history_service.get_all_completed_session_summaries()
                if s.get('platform') == self._selected_platform
            ]

            if not sessions_to_export_summaries:
                self.status_message_changed.emit("No session summaries to export for this platform.", "INFO");
                return

            try:
                with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                    if not sessions_to_export_summaries:
                        writer = csv.writer(csvfile)
                        writer.writerow(["No session data available."])
                        self.status_message_changed.emit(f"Report generated (empty): {file_path}", "INFO");
                        return

                    # Use fieldnames from the summary dicts
                    # Ensure all dicts have the same keys or handle missing ones gracefully
                    fieldnames = []
                    if sessions_to_export_summaries:
                        fieldnames = list(sessions_to_export_summaries[0].keys())
                        # Optional: Add readable timestamp columns if not already present
                        if 'start_timestamp' in fieldnames and 'start_timestamp_readable' not in fieldnames:
                            fieldnames.append('start_timestamp_readable')
                        if 'end_timestamp' in fieldnames and 'end_timestamp_readable' not in fieldnames:
                            fieldnames.append('end_timestamp_readable')

                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
                    writer.writeheader()

                    for session_summary in sessions_to_export_summaries:
                        # Create a copy to add readable timestamps without modifying original
                        summary_to_write = session_summary.copy()
                        if 'start_timestamp' in summary_to_write and summary_to_write['start_timestamp']:
                            summary_to_write['start_timestamp_readable'] = datetime.fromtimestamp(
                                summary_to_write['start_timestamp']).strftime('%Y-%m-%d %H:%M:%S')
                        if 'end_timestamp' in summary_to_write and summary_to_write['end_timestamp']:
                            summary_to_write['end_timestamp_readable'] = datetime.fromtimestamp(
                                summary_to_write['end_timestamp']).strftime('%Y-%m-%d %H:%M:%S')
                        writer.writerow(summary_to_write)

                self.status_message_changed.emit(f"Report generated successfully: {file_path}", "SUCCESS")
                self._logger.info(f"Report generated to {file_path}")
            except Exception as e:
                self.status_message_changed.emit(f"Failed to generate report: {e}", "ERROR")
                self._logger.error(f"Error generating report: {e}", exc_info=True)

        elif file_path_res.is_failure:
            self.status_message_changed.emit(f"Could not get save path: {file_path_res.error}", "ERROR")
        else:  # User cancelled
            self.status_message_changed.emit("Report generation cancelled.", "INFO")

    @Slot(int)
    def show_session_details(self, row_index: int):
        """Shows detailed P&L data for the selected session by loading it into the graph."""
        if row_index < 0 or row_index >= len(self._raw_session_summaries):  # Use raw summaries for ID
            self._logger.warning(f"Invalid row index for session details: {row_index}")
            self.pnl_graph_data_updated.emit([])  # Clear graph
            self.graph_threshold_value_changed.emit(0.0)
            return

        selected_session_summary = self._raw_session_summaries[row_index]
        session_id = selected_session_summary.get("session_id")
        platform_threshold = selected_session_summary.get("threshold_value", 0.0)

        if not session_id:
            self._logger.error("Selected session summary is missing a session_id.")
            self.pnl_graph_data_updated.emit([])
            return

        self._logger.info(f"Loading P&L graph for session: {session_id}")
        pnl_points = self._history_service.get_current_session_pnl_data(session_id)

        self._graph_data = pnl_points if pnl_points else []
        self.pnl_graph_data_updated.emit(self._graph_data)
        self._current_graph_threshold = platform_threshold  # Store threshold for this specific graph
        self.graph_threshold_value_changed.emit(self._current_graph_threshold)
        # Time range is implicitly "Selected Session" now
        if "Session" not in self._time_range_options: self._time_range_options.append("Session")
        #self.graph_current_time_range_changed.emit("Session")
        self.set_threshold_line_visibility(True)  # Default to show threshold for session graph

    @Slot()
    def refresh_ui_signals(self):
        self._logger.debug(f"HistoryViewModel Refreshing UI signals for {self._selected_platform or 'None'}")
        # These emit current state. _load_history_for_platform populates the state.
        self.pnl_graph_data_updated.emit(self._graph_data)  # Initially empty or last viewed
        #self.graph_time_range_options_changed.emit(self._time_range_options)
        #self.graph_current_time_range_changed.emit(self._current_time_range)
        self.graph_threshold_line_visibility_changed.emit(self._show_threshold_line)
        self.graph_threshold_value_changed.emit(self._current_graph_threshold)
        self.session_history_updated.emit(self._session_history)
        has_data = bool(self._session_history)
        self.can_clear_history_changed.emit(has_data)
        self.can_generate_report_changed.emit(has_data)

    @Slot(str)
    def _handle_platform_selection_change(self, platform: str):
        self._logger.debug(f"HistoryViewModel received platform change: {platform}")
        self._load_history_for_platform(platform)

    def _load_history_for_platform(self, platform: str):
        self._selected_platform = platform
        self._logger.info(f"Loading history for platform: {platform or 'None'}")

        self._graph_data = []
        self._session_history = []
        self._raw_session_summaries = []
        self._current_graph_threshold = 0.0  # Reset graph specific threshold

        if not platform:
            self.refresh_ui_signals()  # Emit empty/default states
            return

        # Fetch all completed session summaries from the service
        all_summaries_raw = self._history_service.get_all_completed_session_summaries()
        self._raw_session_summaries = [s for s in all_summaries_raw if s.get('platform') == platform]

        # Format for the table view
        formatted_table_data: SessionHistoryType = []
        for summary in self._raw_session_summaries:
            start_ts = summary.get("start_timestamp")
            end_ts = summary.get("end_timestamp")
            duration_s = summary.get("duration_seconds")

            formatted_table_data.append({
                "session_id": summary.get("session_id"),  # Keep for internal use
                "date": datetime.fromtimestamp(start_ts).strftime('%Y-%m-%d') if start_ts else "N/A",
                "start_time": datetime.fromtimestamp(start_ts).strftime('%I:%M %p') if start_ts else "N/A",
                "duration": f"{int(duration_s // 60)}m {int(duration_s % 60)}s" if duration_s is not None else "N/A",
                "min_pnl": f"${summary.get('min_pnl_value', 0.0):,.2f}",
                "threshold": f"${summary.get('threshold_value', 0.0):,.2f}",
                "locked": summary.get("lockout_triggered", False)
            })
        self._session_history = formatted_table_data

        # Load platform-specific threshold for default graph view (might be overridden by session selection)
        threshold_res = self._config_repo.get_platform_stop_loss_threshold(platform)
        self._current_graph_threshold = threshold_res.value if threshold_res.is_success else self._config_repo.DEFAULT_PLATFORM_THRESHOLD

        self.refresh_ui_signals()  # Emit all updated states

    # _calculate_start_time can be removed if graph is always per-session
    # def _calculate_start_time(self, end_time: float, time_range: str) -> float: ...