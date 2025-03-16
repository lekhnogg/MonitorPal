"""
Monitoring service interface for monitoring trading platform P&L.

Defines the contract for monitoring services in the application.
"""
from abc import ABC, abstractmethod
from typing import Tuple, Optional, List, Callable

from src.domain.common.result import Result
from src.domain.models.monitoring_result import MonitoringResult


class IMonitoringService(ABC):
    """
    Interface for monitoring services.

    Defines methods for monitoring trading platform P&L and managing the monitoring lifecycle.
    """

    @abstractmethod
    def start_monitoring(self,
                         platform: str,
                         region: Tuple[int, int, int, int],
                         threshold: float,
                         interval_seconds: float = 5.0,
                         on_status_update: Optional[Callable[[str, str], None]] = None,
                         on_threshold_exceeded: Optional[Callable[[MonitoringResult], None]] = None,
                         on_error: Optional[Callable[[str], None]] = None) -> Result[bool]:
        """
        Start monitoring the specified region for P&L values.

        Args:
            platform: The platform being monitored (e.g., "Quantower")
            region: The region to monitor (left, top, width, height)
            threshold: The threshold value (negative number, losses below this trigger alerts)
            interval_seconds: How often to check (in seconds)
            on_status_update: Callback for status updates (message, level)
            on_threshold_exceeded: Callback for when threshold is exceeded
            on_error: Callback for monitoring errors

        Returns:
            Result indicating success or failure
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

    @abstractmethod
    def get_latest_result(self) -> Optional[MonitoringResult]:
        """
        Get the latest monitoring result.

        Returns:
            The most recent monitoring result, or None if no monitoring has occurred
        """
        pass

    @abstractmethod
    def select_monitoring_region(self) -> Result[Tuple[int, int, int, int]]:
        """
        Open a UI for the user to select a monitoring region.

        Returns:
            Result containing the selected region (left, top, width, height)
        """
        pass

    @abstractmethod
    def get_monitoring_history(self) -> Result[List[MonitoringResult]]:
        """
        Get the history of monitoring results.

        Returns:
            Result containing the list of monitoring results
        """
        pass