#src/infrastructure/platform/window_manager.py
"""
Windows implementation of the window management abstraction.

Implements window operations using Windows-specific APIs (win32gui, win32con, etc.).
"""
import ctypes
import time
from ctypes import wintypes
from typing import List, Tuple, Optional, Dict, Any

import win32gui
import win32con
import win32process

# Define LRESULT which is not in wintypes
LRESULT = ctypes.c_long
from src.domain.services.i_window_manager_service import IWindowManager
from src.domain.services.i_logger_service import ILoggerService
from src.domain.common.result import Result
from src.domain.common.errors import PlatformError, ResourceError


# Win32 & Ctypes definitions for creating the layered window
WS_EX_LAYERED = 0x00080000
WS_EX_TOPMOST = 0x00000008
WS_POPUP = 0x80000000

ULW_ALPHA = 0x02
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01

# Define required structures for the layered window
class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class RGBQUAD(ctypes.Structure):
    _fields_ = [
        ("rgbBlue", wintypes.BYTE),
        ("rgbGreen", wintypes.BYTE),
        ("rgbRed", wintypes.BYTE),
        ("rgbReserved", wintypes.BYTE),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", RGBQUAD * 1),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", wintypes.BYTE),
        ("BlendFlags", wintypes.BYTE),
        ("SourceConstantAlpha", wintypes.BYTE),
        ("AlphaFormat", wintypes.BYTE),
    ]


# Define window procedure
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


def wndproc(hwnd, msg, wparam, lparam):
    """Window procedure for the overlay window."""
    if msg == win32con.WM_DESTROY:
        user32 = ctypes.windll.user32
        user32.PostQuitMessage(0)
    return ctypes.windll.user32.DefWindowProcW(hwnd, msg, wparam, lparam)


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
            error = PlatformError(
                message=f"Error finding window by title",
                details={"title_pattern": title_pattern},
                inner_error=e
            )
            self.logger.error(str(error))
            return Result.fail(error)

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
            error = PlatformError(
                message=f"Error finding window by process ID",
                details={"process_id": process_id},
                inner_error=e
            )
            self.logger.error(str(error))
            return Result.fail(error)

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
            error = PlatformError(
                message=f"Error getting windows for process",
                details={"process_id": process_id},
                inner_error=e
            )
            self.logger.error(str(error))
            return Result.fail(error)

    def get_window_title(self, window_handle: int) -> Result[str]:
        """Get the title of a window."""
        try:
            title = win32gui.GetWindowText(window_handle)
            return Result.ok(title)
        except Exception as e:
            error = PlatformError(
                message=f"Error getting window title",
                details={"window_handle": window_handle},
                inner_error=e
            )
            self.logger.error(str(error))
            return Result.fail(error)

    def is_window_visible(self, window_handle: int) -> Result[bool]:
        """Check if a window is visible."""
        try:
            is_visible = win32gui.IsWindowVisible(window_handle)
            return Result.ok(bool(is_visible))
        except Exception as e:
            error = PlatformError(
                message=f"Error checking window visibility",
                details={"window_handle": window_handle},
                inner_error=e
            )
            self.logger.error(str(error))
            return Result.fail(error)

    def get_foreground_window(self) -> Result[int]:
        """Get the handle of the foreground window."""
        try:
            hwnd = win32gui.GetForegroundWindow()
            return Result.ok(hwnd)
        except Exception as e:
            error = PlatformError(
                message=f"Error getting foreground window",
                inner_error=e
            )
            self.logger.error(str(error))
            return Result.fail(error)

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
            error = PlatformError(
                message=f"Error setting foreground window",
                details={"window_handle": window_handle},
                inner_error=e
            )
            self.logger.error(str(error))
            return Result.fail(error)

    def get_window_process_id(self, window_handle: int) -> Result[int]:
        """Get the process ID for a window."""
        try:
            _, process_id = win32process.GetWindowThreadProcessId(window_handle)
            return Result.ok(process_id)
        except Exception as e:
            error = PlatformError(
                message=f"Error getting window process ID",
                details={"window_handle": window_handle},
                inner_error=e
            )
            self.logger.error(str(error))
            return Result.fail(error)

    def create_transparent_overlay(self,
                                   size: Tuple[int, int],
                                   position: Tuple[int, int],
                                   click_through_regions: List[Tuple[int, int, int, int]]) -> Result[int]:
        """Create a transparent overlay window with click-through holes."""
        try:
            # Log the input parameters for debugging
            self.logger.debug(
                f"Creating overlay with size={size}, position={position}, regions={click_through_regions}")

            # Convert the click_through_regions to the format expected by the implementation
            screen_w, screen_h = size
            x_pos, y_pos = position

            # The overlay expects regions as a list of dict objects with "coords" key
            # But we're receiving them as (x, y, w, h) tuples, so we'll convert them
            flatten_positions = []
            for region in click_through_regions:
                x, y, w, h = region
                flatten_positions.append({"coords": (x, y, x + w, y + h)})

            # Call the implementation
            hwnd = self._create_layered_window_impl(
                flatten_positions,
                screen_w,
                screen_h,
                position=(x_pos, y_pos)
            )

            if hwnd:
                return Result.ok(hwnd)
            else:
                error = ResourceError(
                    message="Failed to create overlay window",
                    details={"size": size, "position": position}
                )
                return Result.fail(error)
        except Exception as e:
            error = PlatformError(
                message=f"Error creating transparent overlay",
                details={"size": size, "position": position},
                inner_error=e
            )
            self.logger.error(str(error))
            return Result.fail(error)

    def process_messages(self, window_handle: int, duration_ms: int) -> Result[bool]:
        """
        Process Windows messages for a specific window for a given duration.

        Args:
            window_handle: Handle of the window to process messages for
            duration_ms: Maximum time to process messages in milliseconds

        Returns:
            Result indicating success or failure
        """
        try:
            # Define Windows message structure if not already defined
            class MSG(ctypes.Structure):
                _fields_ = [
                    ("hwnd", wintypes.HWND),
                    ("message", wintypes.UINT),
                    ("wParam", wintypes.WPARAM),
                    ("lParam", wintypes.LPARAM),
                    ("time", wintypes.DWORD),
                    ("pt", wintypes.POINT),
                ]

            # Constants
            PM_REMOVE = 0x0001
            WM_QUIT = 0x0012

            # Prepare for message loop
            msg = MSG()
            start_time = time.time()
            end_time = start_time + (duration_ms / 1000.0)

            # Process messages until timeout
            while time.time() < end_time:
                # Check if window is still valid
                if window_handle and not self._user32.IsWindow(window_handle):
                    self.logger.debug(f"Window {window_handle} is no longer valid")
                    return Result.ok(False)

                # Process all pending messages
                while self._user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, PM_REMOVE):
                    if msg.message == WM_QUIT:
                        self.logger.debug("Received WM_QUIT message")
                        return Result.ok(False)

                    self._user32.TranslateMessage(ctypes.byref(msg))
                    self._user32.DispatchMessageW(ctypes.byref(msg))

                # Sleep briefly to avoid high CPU usage
                time.sleep(0.01)

            return Result.ok(True)

        except Exception as e:
            error = PlatformError(
                message=f"Error processing window messages",
                details={"window_handle": window_handle, "duration_ms": duration_ms},
                inner_error=e
            )
            self.logger.error(str(error))
            return Result.fail(error)

    def destroy_window(self, window_handle: int) -> Result[bool]:
        """Destroy a window."""
        try:
            result = win32gui.DestroyWindow(window_handle)
            return Result.ok(bool(result))
        except Exception as e:
            error = PlatformError(
                message=f"Error destroying window",
                details={"window_handle": window_handle},
                inner_error=e
            )
            self.logger.error(str(error))
            return Result.fail(error)

    def _create_layered_window_impl(self,
                                    flatten_positions: List[dict],
                                    screen_w: int,
                                    screen_h: int,
                                    position: Tuple[int, int] = (0, 0),
                                    alpha_block: int = 200) -> int:
        """
        Implementation of the layered window creation.

        Args:
            flatten_positions: List of dictionaries with "coords" specifying rectangles as (x1, y1, x2, y2)
            screen_w: Width of the window
            screen_h: Height of the window
            position: Position (x, y) of the window (0, 0 for fullscreen)
            alpha_block: Alpha value for blocked areas (0-255)

        Returns:
            Window handle (HWND) as integer, or 0 on failure
        """
        hWnd = 0
        hdcScreen = 0
        hdcMem = 0
        hBmp = 0
        atomClass = 0

        try:
            # Following the working approach more closely
            className = "LayeredLockoutWindow"
            hInstance = self._kernel32.GetModuleHandleW(None)
            if not hInstance:
                self.logger.error("GetModuleHandleW(None) failed")
                return 0

            # Create a simpler WNDCLASS structure like in the working code
            wndClass = win32gui.WNDCLASS()
            wndClass.hInstance = hInstance
            wndClass.lpszClassName = className
            wndClass.lpfnWndProc = WNDPROC(wndproc)

            # Register the class and get the atom
            atomClass = win32gui.RegisterClass(wndClass)
            if not atomClass:
                error_code = ctypes.windll.kernel32.GetLastError()
                self.logger.error(f"RegisterClass failed with error code: {error_code}")
                return 0

            # Create window using atomClass (critical change)
            styleEx = WS_EX_LAYERED | WS_EX_TOPMOST
            style = WS_POPUP

            x_pos, y_pos = position

            hWnd = self._user32.CreateWindowExW(
                styleEx,
                atomClass,  # Use atomClass here, not className or atom_class
                "LockoutOverlay",
                style,
                x_pos, y_pos,
                screen_w, screen_h,
                0, 0,
                hInstance,
                None
            )

            if not hWnd:
                error_code = ctypes.windll.kernel32.GetLastError()
                self.logger.error(f"CreateWindowExW failed with error code: {error_code}")
                return 0

            # Get device contexts
            hdcScreen = self._user32.GetDC(0)
            hdcMem = self._gdi32.CreateCompatibleDC(hdcScreen)

            # Create bitmap info
            bmi = BITMAPINFO()
            bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth = screen_w
            bmi.bmiHeader.biHeight = screen_h
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            bmi.bmiHeader.biCompression = win32con.BI_RGB

            # Create DIB section
            ppvBits = ctypes.c_void_p()
            hBmp = self._gdi32.CreateDIBSection(
                hdcScreen,
                ctypes.byref(bmi),
                win32con.DIB_RGB_COLORS,
                ctypes.byref(ppvBits),
                None,
                0
            )
            if not hBmp:
                self.logger.error("CreateDIBSection failed")
                return 0

            # Select bitmap into DC
            old_obj = self._gdi32.SelectObject(hdcMem, hBmp)
            if not old_obj:
                self.logger.error("SelectObject failed")

            # Fill bitmap
            import struct

            # Helper function to fill a rectangle with a specific alpha value
            def fill_rect_alpha(x1, y1, x2, y2, alpha, color=(0, 0, 0)):
                b, g, r = color
                for yy in range(y1, y2):
                    for xx in range(x1, x2):
                        offset = ((screen_h - 1 - yy) * screen_w + xx) * 4
                        pixel = struct.pack("BBBB", b, g, r, alpha)
                        ctypes.memmove(ppvBits.value + offset, pixel, 4)

            # First fill entire screen with alpha_block
            fill_rect_alpha(0, 0, screen_w, screen_h, alpha_block, (0, 0, 0))

            # Carve out holes for flatten buttons
            for pos in flatten_positions:
                # Handle both dictionary with "coords" and direct tuple formats
                if isinstance(pos, dict) and "coords" in pos:
                    coords = pos["coords"]
                elif isinstance(pos, tuple) and len(pos) == 4:
                    # If it's already a (x, y, w, h) tuple
                    x, y, w, h = pos
                    coords = (x, y, x + w, y + h)
                else:
                    # Skip invalid formats
                    self.logger.warning(f"Skipping invalid flatten position format: {pos}")
                    continue

                if coords:
                    x1, y1, x2, y2 = coords
                    if x2 < x1:
                        x1, x2 = x2, x1
                    if y2 < y1:
                        y1, y2 = y2, y1
                    fill_rect_alpha(x1, y1, x2, y2, 0, (0, 0, 0))

            # Update layered window
            sizeWin = SIZE(screen_w, screen_h)
            ptSrc = POINT(0, 0)
            ptWinPos = POINT(x_pos, y_pos)
            blend = BLENDFUNCTION()
            blend.BlendOp = AC_SRC_OVER
            blend.BlendFlags = 0
            blend.SourceConstantAlpha = 255
            blend.AlphaFormat = AC_SRC_ALPHA

            result = self._user32.UpdateLayeredWindow(
                hWnd,
                hdcScreen,
                ctypes.byref(ptWinPos),
                ctypes.byref(sizeWin),
                hdcMem,
                ctypes.byref(ptSrc),
                0,
                ctypes.byref(blend),
                ULW_ALPHA
            )

            if not result:
                error_code = ctypes.windll.kernel32.GetLastError()
                self.logger.error(f"UpdateLayeredWindow failed with error code: {error_code}")

            # Clean up GDI resources used for creation, now that window is updated
            if old_obj:
                self._gdi32.SelectObject(hdcMem, old_obj)

            if hdcScreen:
                self._user32.ReleaseDC(0, hdcScreen)
                hdcScreen = 0

            if hdcMem:
                self._gdi32.DeleteDC(hdcMem)
                hdcMem = 0

            if hBmp:
                self._gdi32.DeleteObject(hBmp)
                hBmp = 0

            # Show the window
            self._user32.ShowWindow(hWnd, win32con.SW_SHOWNORMAL)
            self._user32.UpdateWindow(hWnd)

            return hWnd

        except Exception as e:
            self.logger.error(f"Error creating layered window: {e}")

            # Clean up resources on failure
            if hdcScreen:
                self._user32.ReleaseDC(0, hdcScreen)

            if hdcMem:
                self._gdi32.DeleteDC(hdcMem)

            if hBmp:
                self._gdi32.DeleteObject(hBmp)

            if hWnd:
                self._user32.DestroyWindow(hWnd)

            if atomClass:
                # Unregister the class if needed
                try:
                    win32gui.UnregisterClass(atomClass, self._kernel32.GetModuleHandleW(None))
                except Exception as e:
                    self.logger.warning(f"Error unregistering window class: {e}")

            return 0