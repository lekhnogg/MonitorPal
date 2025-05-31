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
                         threshold: float,
                         session_id: str,
                         interval_seconds: float = 5.0,
                         on_status_update: Optional[Callable[[str, str], None]] = None,
                         on_threshold_exceeded: Optional[Callable[[MonitoringResult], None]] = None,
                         on_error: Optional[Callable[[str, bool], None]] = None, # <<< CHANGED: (error_message, is_fatal)
                         on_individual_check_complete: Optional[Callable[[MonitoringResult], None]] = None
                         ) -> Result[bool]:
        """
        ...
        Args:
            ...
            on_error: Callback for errors during monitoring.
                      Args: (error_message: str, is_task_definitively_stopped: bool) # <<< UPDATED DOC
            ...
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
    def check_platform_readiness(self, platform: str) -> Result[bool]:  # Returns True if ready, False with error if not
        """
        Performs a quick check to see if the specified platform is
        running and detectable, as a prerequisite for starting monitoring.

        Args:
            platform: The name of the platform to check.

        Returns:
            Result.ok(True) if the platform is ready for monitoring.
            Result.fail(error_message) if the platform is not ready (e.g., not running).
        """
        pass