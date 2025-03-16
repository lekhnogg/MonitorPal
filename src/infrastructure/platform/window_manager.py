#src/infrastructure/platform/window_manager.py
"""
Windows implementation of the window management abstraction.

Implements window operations using Windows-specific APIs (win32gui, win32con, etc.).
"""
import ctypes
from ctypes import wintypes
from typing import List, Tuple, Optional

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
            # Convert the click_through_regions to the format expected by the implementation
            screen_w, screen_h = size
            x_pos, y_pos = position

            # Format conversion: [(x1,y1,w,h)] -> [{coords: (x1,y1,x2,y2)}]
            flatten_positions = []
            for region in click_through_regions:
                x, y, w, h = region
                flatten_positions.append({"coords": (x, y, x+w, y+h)})

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
        atom_class = 0

        try:
            className = "LayeredLockoutWindow"
            hInstance = self._kernel32.GetModuleHandleW(None)
            if not hInstance:
                self.logger.error("GetModuleHandleW(None) failed")
                return 0

            # Register window class
            wc = win32gui.WNDCLASS()
            wc.style = 0
            wc.lpfnWndProc = WNDPROC(wndproc)
            wc.cbClsExtra = 0
            wc.cbWndExtra = 0
            wc.hInstance = hInstance
            wc.hIcon = 0
            wc.hCursor = 0
            wc.hbrBackground = 0
            wc.lpszMenuName = 0
            wc.lpszClassName = className
            atom_class = win32gui.RegisterClass(wc)

            # Create window
            styleEx = WS_EX_LAYERED | WS_EX_TOPMOST
            style = WS_POPUP

            x_pos, y_pos = position

            hWnd = self._user32.CreateWindowExW(
                styleEx,
                atom_class,
                "LockoutOverlay",
                style,
                x_pos, y_pos,
                screen_w, screen_h,
                0, 0,
                hInstance,
                None
            )
            if not hWnd:
                self.logger.error("CreateWindowExW failed for layered window")
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
                coords = pos.get("coords")
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
                self.logger.error(f"UpdateLayeredWindow failed: {ctypes.GetLastError()}")

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

            if atom_class:
                win32gui.UnregisterClass(atom_class, self._kernel32.GetModuleHandleW(None))

            return 0