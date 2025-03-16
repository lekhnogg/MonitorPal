#src/domain/services/i_window_manager_service.py
"""
Window management abstraction for platform-independent operations.

This interface defines operations for window management that can be implemented
for different platforms.
"""
from abc import ABC, abstractmethod
from typing import List, Tuple, Optional

from src.domain.common.result import Result


class IWindowManager(ABC):
    """Interface for platform-independent window management operations."""

    @abstractmethod
    def find_window_by_title(self, title_pattern: str) -> Result[Optional[int]]:
        """
        Find a window by its title.

        Args:
            title_pattern: Pattern to match in window titles

        Returns:
            Result containing window handle if found, None otherwise
        """
        pass

    @abstractmethod
    def find_window_by_process_id(self, process_id: int) -> Result[Optional[int]]:
        """
        Find a window associated with a process ID.

        Args:
            process_id: Process ID to search for

        Returns:
            Result containing window handle if found, None otherwise
        """
        pass

    @abstractmethod
    def get_all_windows_for_process(self, process_id: int) -> Result[List[int]]:
        """
        Get all visible window handles for a process.

        Args:
            process_id: Process ID to search for

        Returns:
            Result containing list of window handles
        """
        pass

    @abstractmethod
    def get_window_title(self, window_handle: int) -> Result[str]:
        """
        Get the title of a window.

        Args:
            window_handle: Window handle

        Returns:
            Result containing window title
        """
        pass

    @abstractmethod
    def is_window_visible(self, window_handle: int) -> Result[bool]:
        """
        Check if a window is visible.

        Args:
            window_handle: Window handle

        Returns:
            Result containing visibility status
        """
        pass

    @abstractmethod
    def get_foreground_window(self) -> Result[int]:
        """
        Get the handle of the foreground window.

        Returns:
            Result containing foreground window handle
        """
        pass

    @abstractmethod
    def set_foreground_window(self, window_handle: int) -> Result[bool]:
        """
        Bring a window to the foreground.

        Args:
            window_handle: Window handle

        Returns:
            Result indicating success or failure
        """
        pass

    @abstractmethod
    def get_window_process_id(self, window_handle: int) -> Result[int]:
        """
        Get the process ID associated with a window.

        Args:
            window_handle: Window handle

        Returns:
            Result containing process ID
        """
        pass

    @abstractmethod
    def create_transparent_overlay(self,
                                  size: Tuple[int, int],
                                  position: Tuple[int, int],
                                  click_through_regions: List[Tuple[int, int, int, int]]) -> Result[int]:
        """
        Create a transparent overlay window with click-through regions.

        Args:
            size: Width and height of the overlay
            position: X and Y position of the overlay
            click_through_regions: List of regions (x, y, width, height) that should allow clicks to pass through

        Returns:
            Result containing window handle of the created overlay
        """
        pass

    @abstractmethod
    def destroy_window(self, window_handle: int) -> Result[bool]:
        """
        Destroy a window.

        Args:
            window_handle: Window handle

        Returns:
            Result indicating success or failure
        """
        pass