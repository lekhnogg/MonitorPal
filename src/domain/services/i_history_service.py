# src/domain/services/history_service.py
"""
Defines the interface for services managing historical monitoring data.
"""

import abc
from typing import List, Dict, Optional, Tuple, Any
from src.domain.common.result import Result # Assuming Result is appropriate for export status

class IHistoryService(abc.ABC):
    """
    Interface for managing historical monitoring session data.
    Implementations handle storing, retrieving, and clearing session details
    and associated P&L time-series data.
    """

    @abc.abstractmethod
    def start_session(self, platform: str, threshold: float) -> str:
        """
        Starts tracking a new monitoring session.

        Args:
            platform: The name of the platform being monitored.
            threshold: The stop-loss threshold used for this session.

        Returns:
            A unique session identifier (str) for this session.
        """
        pass

    @abc.abstractmethod
    def record_pnl(self, session_id: str, timestamp: float, pnl_value: float) -> None:
        """
        Records a single P&L data point for a specific session.

        Args:
            session_id: The unique identifier of the session.
            timestamp: The epoch timestamp of the data point.
            pnl_value: The P&L value recorded at the timestamp.
        """
        pass

    @abc.abstractmethod
    def end_session(self, session_id: str, final_pnl: float, lockout_triggered: bool) -> None:
        """
        Marks a session as ended and records final summary information.

        Args:
            session_id: The unique identifier of the session to end.
            final_pnl: The last recorded P&L value for the session (or min value if more relevant).
            lockout_triggered: Boolean indicating if a lockout occurred during this session.
        """
        pass

    @abc.abstractmethod
    def get_current_session_pnl_data(self, session_id: str) -> Optional[List[Tuple[float, float]]]:
        """
        Gets all recorded P&L data points (timestamp, value) for the specified
        currently active or just completed session.

        Used primarily for live graph updates during monitoring.

        Args:
            session_id: The unique identifier of the session.

        Returns:
            A list of (timestamp, pnl_value) tuples, or None if the session ID is invalid.
        """
        pass

    @abc.abstractmethod
    def get_session_summary(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Gets the summary information for a specific completed session.

        Args:
            session_id: The unique identifier of the session.

        Returns:
            A dictionary containing summary data (platform, start, end, duration, min_pnl,
            threshold, locked), or None if the session ID is invalid or not completed.
        """
        pass

    @abc.abstractmethod
    def get_all_completed_session_summaries(self) -> List[Dict[str, Any]]:
        """
        Gets a list of summary dictionaries for all completed sessions
        currently stored (in memory for this phase).

        Returns:
            A list of session summary dictionaries, ordered typically by start time descending.
        """
        pass

    @abc.abstractmethod
    def clear_specific_session_data(self, session_id: str) -> None:
        """
        Removes all data (summary and P&L points) associated with a specific session ID.

        Args:
            session_id: The unique identifier of the session to clear.
        """
        pass

    @abc.abstractmethod
    def clear_all_session_data(self) -> None:
        """
        Removes all historical session data currently stored.
        """
        pass

    @abc.abstractmethod
    def export_session_to_csv(self, session_id: str, file_path: str) -> Result[bool]:
        """
        Exports the detailed P&L time-series data for a specific session to a CSV file.

        Args:
            session_id: The unique identifier of the session to export.
            file_path: The full path where the CSV file should be saved.

        Returns:
            A Result object indicating success (True) or failure (with an error).
        """
        pass