#src/domain/services/i_platform_detection_service.py


"""
Platform Detection Service Interface

Defines the contract for detecting and interacting with trading platform windows.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import threading
from src.domain.common.result import Result


class IPlatformDetectionService(ABC):
    """
    Interface for detecting and interacting with trading platform windows.

    This service is responsible for:
    1. Detecting platform windows based on executable names
    2. Getting information about platform windows
    3. Checking if platform windows are active
    4. Activating platform windows
    """

    @abstractmethod
    def detect_platform_window(self, platform: str, timeout: int = 10,
                              stop_event: Optional[threading.Event] = None) -> Result[Dict[str, Any]]:
        """
        Detect a window for the specified trading platform.

        Args:
            platform: Platform name (e.g., "Quantower", "NinjaTrader")
            timeout: Maximum time to wait for detection (seconds)
            stop_event: Optional event to signal cancellation

        Returns:
            Result containing window information or error
        """
        pass

    @abstractmethod
    def get_window_by_pid(self, pid: int) -> Result[Optional[int]]:
        """
        Get window handle associated with a process ID.

        Args:
            pid: Process ID

        Returns:
            Result containing window handle (hwnd) or None if not found
        """
        pass

    @abstractmethod
    def is_platform_window_active(self, platform_info: Dict[str, Any]) -> Result[bool]:
        """
        Check if a platform window is currently active (in foreground).

        Args:
            platform_info: Dictionary with platform window information

        Returns:
            Result containing boolean indicating if window is active
        """
        pass

    @abstractmethod
    def get_all_windows_for_pid(self, pid: int) -> Result[List[int]]:
        """
        Get all visible window handles for the given process ID.

        Args:
            pid: Process ID

        Returns:
            Result containing a list of window handles (hwnds)
        """
        pass

    @abstractmethod
    def force_foreground_window(self, hwnd: int) -> Result[bool]:
        """
        Bring a window to the foreground (make it active).

        Args:
            hwnd: Window handle

        Returns:
            Result indicating success or failure
        """
        pass

    @abstractmethod
    def activate_platform_windows(self, platform: str) -> Result[bool]:
        """
        Activate all windows associated with a platform.

        Args:
            platform: Platform name

        Returns:
            Result indicating success or failure
        """
        pass

    @abstractmethod
    def get_supported_platforms(self) -> Result[Dict[str, str]]:
        """
        Get dictionary of supported platforms and their executable names.

        Returns:
            Result containing dictionary mapping platform names to executable names
        """
        pass

    @abstractmethod
    def is_platform_running(self, platform: str) -> Result[bool]:
        """
        Quickly check if a platform's process is running without full window detection.

        This is a lightweight check to determine if the executable associated with
        a platform is currently running on the system.

        Args:
            platform: Platform name (e.g., "Quantower", "NinjaTrader")

        Returns:
            Result containing True if the platform is running, False otherwise
        """
        pass