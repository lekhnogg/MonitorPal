"""
Windows implementation of the window management abstraction.

Implements window operations using Windows-specific APIs (win32gui, win32con, etc.).
"""
import ctypes
from typing import List, Tuple, Optional

import win32gui
import win32con
import win32process

from src.domain.services.i_window_manager_service import IWindowManager
from src.domain.services.i_logger_service import ILoggerService
from src.domain.common.result import Result


class WindowsWindowManager(IWindowManager):
    """Windows implementation of window management operations."""

    def __init__(self, logger: ILoggerService):
        """
        Initialize the Windows window manager.

        Args:
            logger: Logger service
        """
        self.logger = logger
        self._user32 = ctypes.windll.user32
        self._gdi32 = ctypes.windll.gdi32
        self._kernel32 = ctypes.windll.kernel32

    def find_window_by_title(self, title_pattern: str) -> Result[Optional[int]]:
        """Find a window by its title pattern."""
        try:
            handle = win32gui.FindWindow(None, title_pattern)
            if handle == 0:
                # Try partial match
                found_handle = None

                def enum_callback(hwnd, _):
                    nonlocal found_handle
                    if win32gui.IsWindowVisible(hwnd):
                        window_title = win32gui.GetWindowText(hwnd)
                        if title_pattern in window_title:
                            found_handle = hwnd
                            return False
                    return True

                win32gui.EnumWindows(enum_callback, None)

                if found_handle:
                    return Result.ok(found_handle)
                else:
                    return Result.ok(None)  # Not found but no error
            else:
                return Result.ok(handle)
        except Exception as e:
            self.logger.error(f"Error finding window by title: {e}")
            return Result.fail(f"Error finding window by title: {e}")

    def find_window_by_process_id(self, process_id: int) -> Result[Optional[int]]:
        """Find a window by its process ID."""
        try:
            found_hwnd = None

            def enum_windows_callback(hwnd, _):
                nonlocal found_hwnd
                try:
                    if win32gui.IsWindowVisible(hwnd):
                        _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
                        if window_pid == process_id:
                            found_hwnd = hwnd
                            return False  # Stop enumeration
                except Exception:
                    pass
                return True

            win32gui.EnumWindows(enum_windows_callback, None)
            return Result.ok(found_hwnd)
        except Exception as e:
            self.logger.error(f"Error finding window by process ID: {e}")
            return Result.fail(f"Error finding window by process ID: {e}")

    def get_all_windows_for_process(self, process_id: int) -> Result[List[int]]:
        """Get all windows for a process ID."""
        try:
            window_handles = []

            def enum_windows_callback(hwnd, _):
                try:
                    if win32gui.IsWindowVisible(hwnd):
                        _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
                        if window_pid == process_id:
                            window_handles.append(hwnd)
                except Exception:
                    pass
                return True

            win32gui.EnumWindows(enum_windows_callback, None)
            return Result.ok(window_handles)
        except Exception as e:
            self.logger.error(f"Error getting windows for process: {e}")
            return Result.fail(f"Error getting windows for process: {e}")

    def get_window_title(self, window_handle: int) -> Result[str]:
        """Get the title of a window."""
        try:
            title = win32gui.GetWindowText(window_handle)
            return Result.ok(title)
        except Exception as e:
            self.logger.error(f"Error getting window title: {e}")
            return Result.fail(f"Error getting window title: {e}")

    def is_window_visible(self, window_handle: int) -> Result[bool]:
        """Check if a window is visible."""
        try:
            is_visible = win32gui.IsWindowVisible(window_handle)
            return Result.ok(bool(is_visible))
        except Exception as e:
            self.logger.error(f"Error checking window visibility: {e}")
            return Result.fail(f"Error checking window visibility: {e}")

    def get_foreground_window(self) -> Result[int]:
        """Get the handle of the foreground window."""
        try:
            hwnd = win32gui.GetForegroundWindow()
            return Result.ok(hwnd)
        except Exception as e:
            self.logger.error(f"Error getting foreground window: {e}")
            return Result.fail(f"Error getting foreground window: {e}")

    def set_foreground_window(self, window_handle: int) -> Result[bool]:
        """Bring a window to the foreground."""
        try:
            # Check if window is minimized and restore it
            if win32gui.IsIconic(window_handle):
                win32gui.ShowWindow(window_handle, win32con.SW_RESTORE)

            # Make window topmost, then disable topmost
            win32gui.SetWindowPos(
                window_handle,
                win32con.HWND_TOPMOST,
                0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
            )
            win32gui.SetWindowPos(
                window_handle,
                win32con.HWND_NOTOPMOST,
                0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
            )

            # Set as foreground window
            result = win32gui.SetForegroundWindow(window_handle)
            return Result.ok(bool(result))
        except Exception as e:
            self.logger.error(f"Error setting foreground window: {e}")
            return Result.fail(f"Error setting foreground window: {e}")

    def get_window_process_id(self, window_handle: int) -> Result[int]:
        """Get the process ID for a window."""
        try:
            _, process_id = win32process.GetWindowThreadProcessId(window_handle)
            return Result.ok(process_id)
        except Exception as e:
            self.logger.error(f"Error getting window process ID: {e}")
            return Result.fail(f"Error getting window process ID: {e}")

    def create_transparent_overlay(self,
                                   size: Tuple[int, int],
                                   position: Tuple[int, int],
                                   click_through_regions: List[Tuple[int, int, int, int]]) -> Result[int]:
        """Create a transparent overlay window with click-through regions."""
        try:
            # This is a simplified version - the actual implementation would be more complex
            # and would need to include all the layered window creation code from lockout_service.py

            # For now, we'll just log the fact that this method would need a full implementation
            self.logger.info("create_transparent_overlay called - this would need to be fully implemented")

            # In a real implementation, this would create a layered window with the specified parameters
            # and return the window handle

            return Result.fail("Method not fully implemented")
        except Exception as e:
            self.logger.error(f"Error creating transparent overlay: {e}")
            return Result.fail(f"Error creating transparent overlay: {e}")

    def destroy_window(self, window_handle: int) -> Result[bool]:
        """Destroy a window."""
        try:
            result = win32gui.DestroyWindow(window_handle)
            return Result.ok(bool(result))
        except Exception as e:
            self.logger.error(f"Error destroying window: {e}")
            return Result.fail(f"Error destroying window: {e}")