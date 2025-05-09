# src/infrastructure/history/history_service.py
"""
In-memory implementation of the IHistoryService.

Stores session summaries and P&L data points in dictionaries during the
application's runtime. Data is lost when the application closes.
"""

import uuid
import time
import csv
import os
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any

# --- Qt Imports ---
from PySide6.QtCore import QObject, Signal

# --- Domain Imports ---
from src.domain.services.i_history_service import IHistoryService
from src.domain.common.result import Result
from src.domain.common.errors import ResourceError, ValidationError
from src.domain.services.i_logger_service import ILoggerService # Import logger


class MemoryHistoryService(QObject): # <<< INHERIT QObject, IHistoryService
    """
    In-memory implementation of IHistoryService. Data persists only for
    the current application run. Emits signals when data changes.
    """
    session_data_changed = Signal()  # Emitted when sessions are ended or cleared
    def __init__(self, logger: ILoggerService, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._logger = logger
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._pnl_data: Dict[str, List[Tuple[float, float]]] = {}
        self._active_session_id: Optional[str] = None
        self._logger.info("MemoryHistoryService (QObject) initialized.")

    def start_session(self, platform: str, threshold: float) -> str:
        """Starts tracking a new monitoring session."""
        # Ensure only one session is active at a time (for this simple implementation)
        if self._active_session_id:
            self._logger.warning(f"Cannot start new session for {platform}, session {self._active_session_id} is already active. Ending previous one implicitly.")
            # Optionally end the previous session gracefully here if needed,
            # though ideally MonitoringService ensures stop before start.
            # For now, we just overwrite the active_session_id.
            # Find the previous session to mark end time approximately? Might be complex.
            # Let's just log the warning and proceed.
            # Consider adding logic later if overlapping sessions become an issue.
            pass # Proceed to start new session


        session_id = f"session_{uuid.uuid4()}" # Generate a unique ID
        start_time = time.time()
        self._sessions[session_id] = {
            "session_id": session_id,
            "platform": platform,
            "start_timestamp": start_time,
            "threshold_value": threshold,
            "end_timestamp": None, # Mark as ongoing
            "duration_seconds": None,
            "min_pnl_value": None, # Track minimum P&L encountered
            "final_pnl_value": None, # Last known P&L value
            "lockout_triggered": False,
            "final_screenshot_path": None # Ensure this key is initialized# Default
        }
        self._pnl_data[session_id] = [] # Initialize empty list for P&L points
        self._active_session_id = session_id
        self._logger.info(f"Started new session {session_id} for {platform} at {datetime.fromtimestamp(start_time)}.")
        return session_id

    def record_pnl(self, session_id: str, timestamp: float, pnl_value: float) -> None:
        """Records a single P&L data point."""
        if session_id not in self._pnl_data:
            self._logger.warning(f"Attempted to record P&L for unknown or ended session: {session_id}")
            return

        self._pnl_data[session_id].append((timestamp, pnl_value))

        # Update the minimum P&L encountered so far for this session
        current_min = self._sessions[session_id].get("min_pnl_value")
        if current_min is None or pnl_value < current_min:
            self._sessions[session_id]["min_pnl_value"] = pnl_value

        # Store the latest P&L value as the potential 'final' value
        self._sessions[session_id]["final_pnl_value"] = pnl_value

        # Optional: Log every N points or based on time to avoid spamming logs
        # if len(self._pnl_data[session_id]) % 50 == 0: # Log every 50 points
        #    self._logger.debug(f"Recorded P&L point for {session_id}: ({timestamp}, {pnl_value})")

    def end_session(self,
                    session_id: str,
                    final_pnl: float,
                    lockout_triggered: bool,
                    final_screenshot_path: Optional[str] = None) -> None: # <<< ADDED parameter
        """Marks a session as ended and records final info."""
        if session_id not in self._sessions:
            self._logger.error(f"Cannot end session: ID {session_id} not found.")
            return
        if self._sessions[session_id]["end_timestamp"] is not None:
            self._logger.warning(f"Session {session_id} already ended.")
            return

        end_time = time.time()
        start_time = self._sessions[session_id]["start_timestamp"]
        duration = end_time - start_time

        # Ensure min_pnl is set before updating
        if self._sessions[session_id].get("min_pnl_value") is None:
             self._sessions[session_id]["min_pnl_value"] = final_pnl

        self._sessions[session_id].update({
            "end_timestamp": end_time,
            "duration_seconds": duration,
            "final_pnl_value": final_pnl,
            "lockout_triggered": lockout_triggered,
            "final_screenshot_path": final_screenshot_path # <<< STORE parameter
        })

        self._logger.info(
            f"Ended session {session_id}. Duration: {duration:.2f}s. Lockout: {lockout_triggered}. "
            f"Final PNL: {final_pnl:.2f}. Min PNL: {self._sessions[session_id].get('min_pnl_value', 'N/A'):.2f}. "
            f"Screenshot: {final_screenshot_path or 'N/A'}"
        )

        if self._active_session_id == session_id:
            self._active_session_id = None
        self.session_data_changed.emit()

    def get_current_session_pnl_data(self, session_id: str) -> Optional[List[Tuple[float, float]]]:
        """Gets P&L points for a specific session (active or completed)."""
        if session_id not in self._pnl_data:
            self._logger.warning(f"No P&L data found for session ID: {session_id}")
            return None
        # Return a copy to prevent external modification
        return self._pnl_data[session_id][:]

    def get_session_summary(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Gets summary info for a specific session."""
        if session_id not in self._sessions:
            self._logger.warning(f"No session summary found for session ID: {session_id}")
            return None
        # Return a copy
        return self._sessions[session_id].copy()

    def get_all_completed_session_summaries(self) -> List[Dict[str, Any]]:
        """Gets summaries for all completed sessions, ordered by start time descending."""
        completed_sessions = [
            data.copy() for data in self._sessions.values() if data.get("end_timestamp") is not None
        ]
        # Sort by start time, most recent first
        completed_sessions.sort(key=lambda x: x.get("start_timestamp", 0), reverse=True)
        self._logger.debug(f"Retrieved {len(completed_sessions)} completed session summaries.")
        return completed_sessions

    def clear_specific_session_data(self, session_id: str) -> None:
        """Removes data for a specific session."""
        removed = False
        if session_id in self._sessions:
            del self._sessions[session_id]
            removed = True
        if session_id in self._pnl_data:
            del self._pnl_data[session_id]
            removed = True
        if self._active_session_id == session_id:
            self._active_session_id = None

        if removed:
            self._logger.info(f"Cleared data for session: {session_id}")
            self.session_data_changed.emit()
        else:
            self._logger.warning(f"Attempted to clear non-existent session: {session_id}")

    def clear_all_session_data(self) -> None:
        """Removes all history data."""
        count = len(self._sessions)
        self._sessions.clear()
        self._pnl_data.clear()
        self._active_session_id = None
        self._logger.info(f"Cleared all ({count}) session history data from memory.")
        self.session_data_changed.emit()

    def export_session_to_csv(self, session_id: str, file_path: str) -> Result[bool]:
        """Exports detailed P&L data for a session to CSV."""
        if session_id not in self._pnl_data:
            return Result.fail(ValidationError(f"Session ID not found for export: {session_id}"))
        if not self._pnl_data[session_id]:
             return Result.fail(ValidationError(f"No P&L data points found to export for session: {session_id}"))

        try:
            pnl_points = self._pnl_data[session_id]
            summary = self._sessions.get(session_id, {})

            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)

                # --- Write Header / Summary Info ---
                writer.writerow(['Session ID:', session_id])
                writer.writerow(['Platform:', summary.get('platform', 'N/A')])
                start_dt = datetime.fromtimestamp(summary.get('start_timestamp', 0))
                end_dt = datetime.fromtimestamp(summary.get('end_timestamp', 0)) if summary.get('end_timestamp') else None
                writer.writerow(['Start Time:', start_dt.strftime('%Y-%m-%d %H:%M:%S') if start_dt else 'N/A'])
                writer.writerow(['End Time:', end_dt.strftime('%Y-%m-%d %H:%M:%S') if end_dt else 'N/A'])
                writer.writerow(['Duration (s):', f"{summary.get('duration_seconds', 0):.2f}"])
                writer.writerow(['Threshold:', f"{summary.get('threshold_value', 0):.2f}"])
                writer.writerow(['Min P&L:', f"{summary.get('min_pnl_value', 0):.2f}"])
                writer.writerow(['Lockout Triggered:', 'Yes' if summary.get('lockout_triggered', False) else 'No'])
                writer.writerow([]) # Blank row before data

                # --- Write Data Header ---
                writer.writerow(['Timestamp', 'DateTime', 'P&L Value'])

                # --- Write Data Points ---
                for timestamp, pnl_value in pnl_points:
                    dt_object = datetime.fromtimestamp(timestamp)
                    dt_string = dt_object.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3] # Milliseconds
                    writer.writerow([f"{timestamp:.3f}", dt_string, f"{pnl_value:.2f}"])

            self._logger.info(f"Successfully exported session {session_id} ({len(pnl_points)} points) to {file_path}")
            return Result.ok(True)

        except PermissionError as e:
            self._logger.error(f"Permission denied exporting session {session_id} to {file_path}: {e}")
            return Result.fail(ResourceError(f"Permission denied writing to file: {e}", inner_error=e))
        except IOError as e:
            self._logger.error(f"I/O error exporting session {session_id} to {file_path}: {e}")
            return Result.fail(ResourceError(f"Failed to write CSV file: {e}", inner_error=e))
        except Exception as e:
            self._logger.error(f"Unexpected error exporting session {session_id} to {file_path}: {e}", exc_info=True)
            return Result.fail(ResourceError(f"An unexpected error occurred during export: {e}", inner_error=e))

IHistoryService.register(MemoryHistoryService) # Register after class def