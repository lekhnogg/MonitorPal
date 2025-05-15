#src/domain/services/i_monitoring_service.py
"""
Monitoring service interface for monitoring trading platform P&L.

Defines the contract for monitoring services in the application.
"""
from abc import ABC, abstractmethod
from typing import Tuple, Optional, List, Callable

from src.domain.common.result import Result
from src.domain.models.monitoring_result import MonitoringResult
from src.domain.services.i_history_service import IHistoryService


class IMonitoringService(ABC):
    """
    Interface for monitoring services.

    Defines methods for monitoring trading platform P&L and managing the monitoring lifecycle.
    """

    @abstractmethod
    def start_monitoring(self,
                         platform: str,
                         region: Tuple[int, int, int, int],  # Kept
                         region_name: str,  # Kept
                         threshold: float,
                         session_id: str,
                         interval_seconds: float = 5.0,
                         on_status_update: Optional[Callable[[str, str], None]] = None,
                         on_threshold_exceeded: Optional[Callable[[MonitoringResult], None]] = None,
                         on_error: Optional[Callable[[str], None]] = None,
                         on_individual_check_complete: Optional[Callable[[MonitoringResult], None]] = None) -> Result[
        bool]:  # <<< ADDED LINE
        """
        Starts the monitoring process for a given platform and threshold.

        Args:
            platform: The name of the platform to monitor.
            region: The screen coordinates (x, y, w, h) of the P&L region.
            region_name: A descriptive name for the P&L region.
            threshold: The loss threshold to monitor against.
            session_id: The unique identifier for this monitoring session.
            interval_seconds: How often to check, in seconds.
            on_status_update: Callback for general status updates.
            on_threshold_exceeded: Callback for when the loss threshold is breached.
            on_error: Callback for errors during monitoring.
            on_individual_check_complete: Callback for when each monitoring check is complete. # <<< ADDED DOC
        """
        pass

    @abstractmethod
    def stop_monitoring(self) -> Result[bool]:
        """
        Stop the current monitoring process.

        Returns:
            Result indicating success or failure
        """
        pass

    @abstractmethod
    def is_monitoring(self) -> bool:
        """
        Check if monitoring is currently active.

        Returns:
            True if monitoring is active, False otherwise
        """
        pass
