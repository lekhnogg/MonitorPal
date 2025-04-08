# src/infrastructure/platform/window_manager.py
"""
Windows implementation of the window management abstraction.

Implements window operations using Windows-specific APIs (win32gui, win32con, etc.).
"""
import ctypes
import time
import struct
import atexit # For cleanup on exit
from ctypes import wintypes
from typing import List, Tuple, Optional, Dict, Any

from src.infrastructure import logging

# Attempt to import pywin32 modules, provide guidance if they fail
try:
    import win32gui
    import win32con
    import win32process
except ImportError:
    print("ERROR: pywin32 library not found.")
    print("Please install it using: pip install pywin32")
    # Optionally raise the error again or exit
    raise

from src.domain.services.i_window_manager_service import IWindowManager
from src.domain.services.i_logger_service import ILoggerService
from src.domain.common.result import Result
from src.domain.common.errors import PlatformError, ResourceError

# Define LRESULT which might not be in wintypes on all systems/versions
try:
    LRESULT = wintypes.LRESULT
except AttributeError:
    LRESULT = ctypes.c_ssize_t # Or ctypes.c_long based on architecture if needed

# --- Win32 & Ctypes definitions for creating the layered window ---
WS_EX_LAYERED = 0x00080000
WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020 # Might be needed if holes don't work as expected
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
        ("bmiColors", RGBQUAD * 1), # For BI_RGB, bmiColors is not used, but struct needs it
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

# Define window procedure type
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

# Define the actual window procedure function
def default_overlay_wndproc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
    """Minimalist window procedure for the overlay window."""
    user32 = ctypes.windll.user32
    if msg == win32con.WM_DESTROY:
        # Optional: PostQuitMessage(0) might interfere if used in a GUI app
        # print("Overlay WM_DESTROY received")
        pass
    elif msg == win32con.WM_NCHITTEST:
        # Make the window non-interactable except where alpha is 0 (handled by WS_EX_LAYERED)
        # Returning HTTRANSPARENT lets mouse events pass through
        return win32con.HTTRANSPARENT
    # Use DefWindowProcW for default handling
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

# --- Main Window Manager Class ---

class WindowsWindowManager(IWindowManager):
    """Windows implementation of window management operations."""

    # Class variables for singleton registration
    _window_class_atom = None
    _window_class_name = "MonitorPalOverlayClass_v1" # Make it unique
    _hInstance = None
    _logger_instance = None # To allow class method cleanup logging

    def __init__(self, logger: ILoggerService):
        """
        Initialize the Windows window manager and register the overlay class once.
        """
        self.logger = logger
        WindowsWindowManager._logger_instance = logger # Store for static cleanup method
        self._user32 = ctypes.windll.user32
        self._gdi32 = ctypes.windll.gdi32
        self._kernel32 = ctypes.windll.kernel32

        if WindowsWindowManager._hInstance is None:
             WindowsWindowManager._hInstance = self._kernel32.GetModuleHandleW(None)
             if not WindowsWindowManager._hInstance:
                 logger.error("Fatal: GetModuleHandleW(None) failed during WindowManager init.")
                 raise PlatformError("Failed to get module handle for WindowManager.")

        # --- Register Window Class ONCE per process ---
        if WindowsWindowManager._window_class_atom is None:
            logger.debug(f"Attempting to register window class: {WindowsWindowManager._window_class_name}")
            try:
                wndClass = win32gui.WNDCLASS()
                wndClass.hInstance = WindowsWindowManager._hInstance
                wndClass.lpszClassName = WindowsWindowManager._window_class_name
                wndClass.lpfnWndProc = WNDPROC(default_overlay_wndproc) # Use function pointer type
                # Set cursor to standard arrow (optional)
                wndClass.hCursor = self._user32.LoadCursorW(0, win32con.IDC_ARROW)
                # Set background to null (layered window draws everything) (optional)
                # wndClass.hbrBackground = self._gdi32.GetStockObject(win32con.NULL_BRUSH)

                atom = win32gui.RegisterClass(wndClass)
                if not atom:
                     error_code = self._kernel32.GetLastError()
                     logger.error(f"RegisterClass failed with error code: {error_code}")
                     raise PlatformError(f"Failed to register overlay window class. Error: {error_code}")

                WindowsWindowManager._window_class_atom = atom
                logger.info(f"Window class '{WindowsWindowManager._window_class_name}' registered successfully (Atom: {atom}).")

                # Register cleanup function to run at Python exit
                atexit.register(WindowsWindowManager._cleanup_class_registration)

            except Exception as e:
                # Check if it's specifically the "already exists" error
                is_already_exists = False
                if isinstance(e, win32gui.error):
                    # pywin32 error format: (error_code, function_name, message)
                    if e.winerror == 1410: # ERROR_CLASS_ALREADY_EXISTS
                        is_already_exists = True

                if is_already_exists:
                    logger.warning(f"Window class '{WindowsWindowManager._window_class_name}' already registered (Error 1410). Assuming valid.")
                    # Mark as "done" even without the specific atom for cleanup robustness
                    WindowsWindowManager._window_class_atom = True
                else:
                    logger.error(f"Failed to register window class '{WindowsWindowManager._window_class_name}'. Exception: {e}", exc_info=True)
                    # This is likely fatal for overlay functionality
                    raise PlatformError(f"Failed to initialize WindowManager: Cannot register window class. Error: {e}")
        else:
             logger.debug(f"Window class '{WindowsWindowManager._window_class_name}' already registered by a manager instance.")

    @classmethod
    def _cleanup_class_registration(cls):
        """Static method to unregister the window class upon application exit."""
        logger = cls._logger_instance or logging.getLogger(__name__) # Fallback logger
        atom = cls._window_class_atom
        instance = cls._hInstance

        # Only attempt unregister if we have a valid atom (not None or True) and instance handle
        if isinstance(atom, int) and atom != 0 and instance:
            logger.debug(f"Unregistering window class '{cls._window_class_name}' (Atom: {atom})")
            try:
                success = win32gui.UnregisterClass(atom, instance)
                if success:
                    logger.info(f"Window class '{cls._window_class_name}' unregistered successfully.")
                else:
                    error_code = ctypes.windll.kernel32.GetLastError()
                    logger.error(f"Failed to unregister window class '{cls._window_class_name}'. Error Code: {error_code}")
                cls._window_class_atom = None # Reset atom status
            except Exception as e:
                logger.error(f"Exception during window class unregistration: {e}", exc_info=True)
        elif atom is True:
            logger.debug(f"Skipping unregistration for class '{cls._window_class_name}' as atom value indicates prior registration.")
        else:
            logger.debug(f"Skipping unregistration for class '{cls._window_class_name}', class was likely never registered successfully.")

    # --- Standard Window Management Methods ---

    def find_window_by_title(self, title_pattern: str) -> Result[Optional[int]]:
        """Find a window by its title pattern (exact first, then partial)."""
        try:
            # Try exact match first (faster)
            handle = win32gui.FindWindow(None, title_pattern)
            if handle != 0:
                return Result.ok(handle)

            # Try partial match using EnumWindows
            found_handle = None
            def enum_callback(hwnd, _):
                nonlocal found_handle
                # Check if window is potentially valid and visible
                if hwnd and win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd):
                    try:
                        window_title = win32gui.GetWindowText(hwnd)
                        if title_pattern in window_title:
                            found_handle = hwnd
                            return False # Stop enumeration
                    except Exception:
                        pass # Ignore errors getting text for specific windows
                return True # Continue enumeration

            win32gui.EnumWindows(enum_callback, None)

            if found_handle:
                return Result.ok(found_handle)
            else:
                # Explicitly log if not found after partial search
                self.logger.debug(f"Window with title pattern '{title_pattern}' not found (exact or partial).")
                return Result.ok(None) # Not found is not an error state

        except Exception as e:
            error = PlatformError(
                message=f"Error finding window by title",
                details={"title_pattern": title_pattern},
                inner_error=e
            )
            self.logger.error(str(error), exc_info=True)
            return Result.fail(error)

    def find_window_by_process_id(self, process_id: int) -> Result[Optional[int]]:
        """Find the main window associated with a process ID."""
        found_hwnd = None
        try:
            def enum_windows_callback(hwnd, lParam):
                nonlocal found_hwnd
                if hwnd and win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd):
                    try:
                        _, pid = win32process.GetWindowThreadProcessId(hwnd)
                        if pid == process_id:
                            # Basic check: does it have a title? Might indicate a main window.
                            if win32gui.GetWindowTextLength(hwnd) > 0:
                                found_hwnd = hwnd
                                return False # Stop enumeration
                    except Exception:
                        pass # Ignore errors for specific windows
                return True
            win32gui.EnumWindows(enum_windows_callback, None)
            return Result.ok(found_hwnd)
        except Exception as e:
            error = PlatformError(
                message=f"Error finding window by process ID",
                details={"process_id": process_id},
                inner_error=e
            )
            self.logger.error(str(error), exc_info=True)
            return Result.fail(error)

    def get_all_windows_for_process(self, process_id: int) -> Result[List[int]]:
        """Get handles of all visible windows belonging to a process ID."""
        window_handles = []
        try:
            def enum_windows_callback(hwnd, lParam):
                if hwnd and win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd):
                    try:
                        _, pid = win32process.GetWindowThreadProcessId(hwnd)
                        if pid == process_id:
                            window_handles.append(hwnd)
                    except Exception:
                         pass # Ignore errors for specific windows
                return True
            win32gui.EnumWindows(enum_windows_callback, None)
            return Result.ok(window_handles)
        except Exception as e:
            error = PlatformError(
                message=f"Error getting windows for process",
                details={"process_id": process_id},
                inner_error=e
            )
            self.logger.error(str(error), exc_info=True)
            return Result.fail(error)

    def get_window_title(self, window_handle: int) -> Result[str]:
        """Get the title of a window handle."""
        if not window_handle or not win32gui.IsWindow(window_handle):
             return Result.fail(PlatformError(f"Invalid window handle: {window_handle}"))
        try:
            title = win32gui.GetWindowText(window_handle)
            return Result.ok(title)
        except Exception as e:
            error = PlatformError(
                message=f"Error getting window title",
                details={"window_handle": window_handle},
                inner_error=e
            )
            self.logger.error(str(error), exc_info=True)
            return Result.fail(error)

    def is_window_visible(self, window_handle: int) -> Result[bool]:
        """Check if a window handle points to a visible window."""
        if not window_handle or not win32gui.IsWindow(window_handle):
             return Result.fail(PlatformError(f"Invalid window handle: {window_handle}"))
        try:
            is_visible = win32gui.IsWindowVisible(window_handle)
            return Result.ok(bool(is_visible))
        except Exception as e:
            error = PlatformError(
                message=f"Error checking window visibility",
                details={"window_handle": window_handle},
                inner_error=e
            )
            self.logger.error(str(error), exc_info=True)
            return Result.fail(error)

    def get_foreground_window(self) -> Result[int]:
        """Get the handle of the window currently in the foreground."""
        try:
            hwnd = win32gui.GetForegroundWindow()
            return Result.ok(hwnd)
        except Exception as e:
            error = PlatformError(
                message=f"Error getting foreground window",
                inner_error=e
            )
            self.logger.error(str(error), exc_info=True)
            return Result.fail(error)

    def set_foreground_window(self, window_handle: int) -> Result[bool]:
        """Bring a window to the foreground, attempting to restore if minimized."""
        if not window_handle or not win32gui.IsWindow(window_handle):
             return Result.fail(PlatformError(f"Invalid window handle: {window_handle}"))
        try:
            # Check if window is minimized and restore it
            if win32gui.IsIconic(window_handle):
                self.logger.debug(f"Window {window_handle} is minimized, restoring...")
                win32gui.ShowWindow(window_handle, win32con.SW_RESTORE)
                time.sleep(0.1) # Short pause to allow window restoration

            # Technique to steal focus: temporarily make topmost, then not topmost
            win32gui.SetWindowPos(window_handle, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
            win32gui.SetWindowPos(window_handle, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)

            # Final attempt to set foreground
            win32gui.SetForegroundWindow(window_handle)

            # Verification step (optional but recommended)
            time.sleep(0.1) # Pause for focus change
            foreground_hwnd = win32gui.GetForegroundWindow()
            success = (foreground_hwnd == window_handle)
            if not success:
                 self.logger.warning(f"SetForegroundWindow called for {window_handle}, but foreground window is now {foreground_hwnd}.")

            return Result.ok(success)

        except Exception as e:
            error = PlatformError(
                message=f"Error setting foreground window",
                details={"window_handle": window_handle},
                inner_error=e
            )
            self.logger.error(str(error), exc_info=True)
            return Result.fail(error)

    def get_window_process_id(self, window_handle: int) -> Result[int]:
        """Get the process ID associated with a window handle."""
        if not window_handle or not win32gui.IsWindow(window_handle):
            return Result.fail(PlatformError(f"Invalid window handle: {window_handle}"))
        try:
            _, process_id = win32process.GetWindowThreadProcessId(window_handle)
            return Result.ok(process_id)
        except Exception as e:
            error = PlatformError(
                message=f"Error getting window process ID",
                details={"window_handle": window_handle},
                inner_error=e
            )
            self.logger.error(str(error), exc_info=True)
            return Result.fail(error)

    # --- Overlay Methods ---

    def _fill_alpha_bitmap(self, ppv_bits: ctypes.c_void_p, width: int, height: int,
                           flatten_positions: List[dict], alpha_block: int):
        """
        Efficiently fill bitmap with alpha values while preserving click-through regions.

        Args:
            ppv_bits: Pointer to bitmap bits
            width: Bitmap width
            height: Bitmap height
            flatten_positions: List of click-through regions (flatten button positions)
            alpha_block: Alpha value for blocked areas (0-255)
        """

        # Create bytes for a pixel with specified alpha
        def create_pixel(alpha):
            return struct.pack("BBBB", 0, 0, 0, alpha)  # BGRA format

        # Fill the entire bitmap with blocked pixels
        buffer_size = width * height * 4  # 4 bytes per pixel (BGRA)
        blocked_pixel = create_pixel(alpha_block)
        transparent_pixel = create_pixel(0)  # Completely transparent (alpha=0)

        # Fill entire screen with blocked pixel
        buffer = blocked_pixel * (width * height)
        ctypes.memmove(ppv_bits, buffer, buffer_size)

        # Carve out holes for flatten buttons - preserve this crucial functionality!
        self.logger.debug(f"Creating {len(flatten_positions)} click-through regions")
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

            if not coords:
                continue

            x1, y1, x2, y2 = coords
            # Ensure proper ordering
            if x2 < x1:
                x1, x2 = x2, x1
            if y2 < y1:
                y1, y2 = y2, y1

            self.logger.debug(f"Creating transparent region at ({x1},{y1}) to ({x2},{y2})")

            # Fill region row by row for better performance
            for y in range(y1, y2):
                # Calculate offset for this row
                # Note: In DIB, rows start from bottom (height-1) to top
                row_offset = ((height - 1 - y) * width + x1) * 4
                row_length = (x2 - x1) * 4

                # Create a buffer for this row with transparent pixels
                row_buffer = transparent_pixel * (x2 - x1)

                # Copy row buffer to bitmap
                ctypes.memmove(ppv_bits.value + row_offset, row_buffer, row_length)


    def create_transparent_overlay(self,
                                   size: Tuple[int, int],
                                   position: Tuple[int, int],
                                   click_through_regions: List[Tuple[int, int, int, int]]) -> Result[int]:
        """
        Create a transparent overlay window with click-through holes.

        Args:
            size: Tuple (width, height) of the overlay.
            position: Tuple (x, y) top-left position of the overlay.
            click_through_regions: List of tuples (x, y, width, height) relative
                                    to the overlay's top-left corner.
        Returns:
            Result containing the window handle (int) or an error.
        """
        screen_w, screen_h = size
        x_pos, y_pos = position
        self.logger.debug(
            f"Initiating overlay creation: Size=({screen_w}x{screen_h}), Pos=({x_pos},{y_pos}), Regions={len(click_through_regions)}"
        )

        # Convert click_through_regions from (x,y,w,h) to required (x1,y1,x2,y2) format
        overlay_relative_coords = []
        for region in click_through_regions:
            if isinstance(region, tuple) and len(region) == 4:
                x, y, w, h = region
                # Ensure width and height are non-negative
                if w < 0 or h < 0:
                     self.logger.warning(f"Skipping region with negative dimensions: {region}")
                     continue
                x1, y1 = x, y
                x2, y2 = x + w, y + h
                overlay_relative_coords.append({"coords": (x1, y1, x2, y2)})
            else:
                self.logger.warning(f"Skipping invalid click_through_region format: {region}")

        if not overlay_relative_coords:
             self.logger.warning("No valid click_through_regions provided for overlay.")
             # Proceed with fully blocked overlay or return error? Let's proceed.

        # --- Call the implementation method ---
        # Wrap the call to the implementation in a try/except to catch errors
        # from _create_layered_window_impl itself
        try:
            hwnd = self._create_layered_window_impl(
                flatten_positions=overlay_relative_coords, # Pass the converted list
                screen_w=screen_w,
                screen_h=screen_h,
                position=(x_pos, y_pos)
                # alpha_block uses default
            )

            if hwnd != 0:
                return Result.ok(hwnd)
            else:
                # Error logged inside _create_layered_window_impl
                return Result.fail(ResourceError(
                    message="Failed to create overlay window (hwnd=0)",
                    details={"size": size, "position": position}
                ))

        except Exception as e:
            # Catch any unexpected error from _create_layered_window_impl
            error = PlatformError(
                message=f"Unexpected error during overlay creation: {e}",
                details={"size": size, "position": position},
                inner_error=e
            )
            self.logger.error(str(error), exc_info=True)
            return Result.fail(error)


    def _create_layered_window_impl(self,
                                    flatten_positions: List[dict],
                                    screen_w: int,
                                    screen_h: int,
                                    position: Tuple[int, int] = (0, 0),
                                    alpha_block: int = 200) -> int:
        """Internal implementation: Creates the layered window using Win32 API."""
        # --- Initialize resources ---
        hWnd = 0
        hdcScreen = 0
        hdcMem = 0
        hBmp = 0
        old_obj = 0
        ppvBits = ctypes.c_void_p()

        try:
            # --- Window Creation ---
            self.logger.debug(f"Creating window with class '{self._window_class_name}'")
            styleEx = WS_EX_LAYERED | WS_EX_TOPMOST
            style = WS_POPUP
            x_pos, y_pos = position
            hWnd = self._user32.CreateWindowExW(
                styleEx, self._window_class_name, "LockoutOverlay", style,
                x_pos, y_pos, screen_w, screen_h, 0, 0, self._hInstance, None
            )
            if not hWnd:
                 error_code = self._kernel32.GetLastError()
                 self.logger.error(f"_create_layered_window_impl: CreateWindowExW failed. Error Code: {error_code}")
                 return 0

            # --- GDI Object Creation ---
            hdcScreen = self._user32.GetDC(0)
            if not hdcScreen:
                 self.logger.error("_create_layered_window_impl: GetDC(0) failed.")
                 self._user32.DestroyWindow(hWnd)
                 return 0

            hdcMem = self._gdi32.CreateCompatibleDC(hdcScreen)
            if not hdcMem:
                 self.logger.error("_create_layered_window_impl: CreateCompatibleDC failed.")
                 self._user32.ReleaseDC(0, hdcScreen)
                 self._user32.DestroyWindow(hWnd)
                 return 0

            # --- Bitmap Creation ---
            bmi = BITMAPINFO()
            bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth = screen_w
            bmi.bmiHeader.biHeight = screen_h
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            bmi.bmiHeader.biCompression = win32con.BI_RGB

            hBmp = self._gdi32.CreateDIBSection(
                hdcScreen, ctypes.byref(bmi), win32con.DIB_RGB_COLORS,
                ctypes.byref(ppvBits), None, 0
            )
            if not hBmp or not ppvBits.value:
                 self.logger.error("_create_layered_window_impl: CreateDIBSection failed.")
                 self._gdi32.DeleteDC(hdcMem)
                 self._user32.ReleaseDC(0, hdcScreen)
                 self._user32.DestroyWindow(hWnd)
                 return 0

            # --- Select Bitmap into DC ---
            old_obj = self._gdi32.SelectObject(hdcMem, hBmp)
            if not old_obj:
                 self.logger.error("_create_layered_window_impl: SelectObject failed.")
                 self._gdi32.DeleteObject(hBmp)
                 self._gdi32.DeleteDC(hdcMem)
                 self._user32.ReleaseDC(0, hdcScreen)
                 self._user32.DestroyWindow(hWnd)
                 return 0

            # --- Fill Bitmap Data (using helper method) ---
            self.logger.debug("_create_layered_window_impl: Calling _fill_alpha_bitmap...")
            try:
                self._fill_alpha_bitmap(ppvBits, screen_w, screen_h, flatten_positions, alpha_block)
            except Exception as e_fill:
                 self.logger.error(f"_create_layered_window_impl: Error during call to _fill_alpha_bitmap: {e_fill}", exc_info=True)
                 # Perform FULL cleanup before returning
                 self._gdi32.SelectObject(hdcMem, old_obj)
                 self._gdi32.DeleteObject(hBmp)
                 self._gdi32.DeleteDC(hdcMem)
                 self._user32.ReleaseDC(0, hdcScreen)
                 self._user32.DestroyWindow(hWnd)
                 return 0

            # --- Update Layered Window ---
            self.logger.debug("_create_layered_window_impl: Calling UpdateLayeredWindow...")
            sizeWin = SIZE(screen_w, screen_h)
            ptSrc = POINT(0, 0)
            ptWinPos = POINT(x_pos, y_pos)
            blend = BLENDFUNCTION(BlendOp=AC_SRC_OVER, BlendFlags=0, SourceConstantAlpha=255, AlphaFormat=AC_SRC_ALPHA)

            update_success = self._user32.UpdateLayeredWindow(
                hWnd, hdcScreen, ctypes.byref(ptWinPos), ctypes.byref(sizeWin),
                hdcMem, ctypes.byref(ptSrc), 0, ctypes.byref(blend), ULW_ALPHA
            )
            if not update_success:
                 error_code = self._kernel32.GetLastError()
                 self.logger.error(f"_create_layered_window_impl: UpdateLayeredWindow failed. Error Code: {error_code}")
                 # Perform FULL cleanup before returning
                 self._gdi32.SelectObject(hdcMem, old_obj)
                 self._gdi32.DeleteObject(hBmp)
                 self._gdi32.DeleteDC(hdcMem)
                 self._user32.ReleaseDC(0, hdcScreen)
                 self._user32.DestroyWindow(hWnd)
                 return 0

            # --- Cleanup GDI resources specific to the update ---
            self.logger.debug("_create_layered_window_impl: Cleaning up temporary GDI objects.")
            self._gdi32.SelectObject(hdcMem, old_obj)
            old_obj = 0 # Mark as cleaned
            self._gdi32.DeleteObject(hBmp)
            hBmp = 0 # Mark as cleaned
            self._gdi32.DeleteDC(hdcMem)
            hdcMem = 0 # Mark as cleaned
            self._user32.ReleaseDC(0, hdcScreen)
            hdcScreen = 0 # Mark as cleaned

            # --- Show Window ---
            self.logger.debug(f"_create_layered_window_impl: Showing window {hWnd}.")
            self._user32.ShowWindow(hWnd, win32con.SW_SHOWNORMAL)
            self._user32.UpdateWindow(hWnd)

            self.logger.info(f"_create_layered_window_impl: Overlay window {hWnd} created successfully.")
            return hWnd # Return the handle on success

        except Exception as e:
            self.logger.error(f"_create_layered_window_impl: Unhandled exception: {e}", exc_info=True)
            # --- Attempt Robust Cleanup on Exception ---
            if old_obj and 'hdcMem' in locals() and hdcMem:
                try: self._gdi32.SelectObject(hdcMem, old_obj)
                except Exception as e_sel: self.logger.error(f"Cleanup exception (SelectObject): {e_sel}")
            if hBmp:
                try: self._gdi32.DeleteObject(hBmp)
                except Exception as e_bmp: self.logger.error(f"Cleanup exception (DeleteObject): {e_bmp}")
            if hdcMem:
                try: self._gdi32.DeleteDC(hdcMem)
                except Exception as e_dc: self.logger.error(f"Cleanup exception (DeleteDC): {e_dc}")
            if hdcScreen:
                try: self._user32.ReleaseDC(0, hdcScreen)
                except Exception as e_rdc: self.logger.error(f"Cleanup exception (ReleaseDC): {e_rdc}")
            if hWnd:
                try: self._user32.DestroyWindow(hWnd)
                except Exception as e_destroy: self.logger.error(f"Cleanup exception (DestroyWindow): {e_destroy}")
            return 0 # Return 0 on any exception


    def process_messages(self, window_handle: int, duration_ms: int) -> Result[bool]:
        """Process Windows messages for the overlay window's thread."""
        if not window_handle or not self._user32.IsWindow(window_handle):
             # Log this clearly, as it might explain loop exits
             self.logger.warning(f"process_messages called with invalid or destroyed window handle: {window_handle}")
             return Result.ok(False) # Indicate window is gone/invalid

        try:
            class MSG(ctypes.Structure):
                 _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                            ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                            ("time", wintypes.DWORD), ("pt", wintypes.POINT)]

            PM_REMOVE = 0x0001
            WM_QUIT = 0x0012

            msg = MSG()
            start_time = time.time()
            end_time = start_time + (duration_ms / 1000.0)
            self.logger.debug(f"process_messages: Starting loop for handle {window_handle} for {duration_ms}ms.")

            while time.time() < end_time:
                # Check window validity inside the loop as well
                if not self._user32.IsWindow(window_handle):
                    self.logger.debug(f"process_messages: Window {window_handle} destroyed during loop.")
                    return Result.ok(False) # Window gone

                # Process all pending messages for the current thread
                while self._user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, PM_REMOVE):
                    if msg.message == WM_QUIT:
                        self.logger.info("process_messages: WM_QUIT received, exiting loop.")
                        # Optional: Re-post if needed? Usually not for this kind of loop.
                        return Result.ok(False) # Quit requested

                    # Let the default window procedure handle most messages
                    self._user32.TranslateMessage(ctypes.byref(msg))
                    self._user32.DispatchMessageW(ctypes.byref(msg))

                # Prevent busy-waiting, yield CPU time
                time.sleep(0.01) # 10ms sleep

            self.logger.debug(f"process_messages: Loop finished for handle {window_handle} (timeout).")
            return Result.ok(True) # Timeout reached normally

        except Exception as e:
            error = PlatformError(
                message=f"Error processing window messages",
                details={"window_handle": window_handle, "duration_ms": duration_ms},
                inner_error=e
            )
            self.logger.error(str(error), exc_info=True)
            return Result.fail(error)


    def destroy_window(self, window_handle: int) -> Result[bool]:
        """Destroy a window handle."""
        self.logger.debug(f"Attempting to destroy window {window_handle}")
        if not window_handle or not self._user32.IsWindow(window_handle):
             self.logger.warning(f"Attempted to destroy invalid or already destroyed window handle: {window_handle}")
             # Return success as the desired state (window gone) is achieved
             return Result.ok(True)
        try:
            # DestroyWindow posts WM_DESTROY, which our wndproc sees (but doesn't need to Quit)
            result = self._user32.DestroyWindow(window_handle)
            if result == 0: # Check return value (non-zero indicates success)
                 error_code = self._kernel32.GetLastError()
                 self.logger.error(f"DestroyWindow failed for handle {window_handle}. Error Code: {error_code}")
                 return Result.fail(PlatformError(f"DestroyWindow failed with code {error_code}"))
            else:
                 self.logger.info(f"Window {window_handle} destroyed successfully.")
                 return Result.ok(True)
        except Exception as e:
            # This might happen if the handle becomes invalid between IsWindow and DestroyWindow
            error = PlatformError(
                message=f"Error destroying window",
                details={"window_handle": window_handle},
                inner_error=e
            )
            self.logger.error(str(error), exc_info=True)
            # Consider returning success if the error indicates the window is already gone?
            # For now, fail on any exception during the call.
            return Result.fail(error)

    def get_virtual_screen_dimensions(self) -> Result[Tuple[int, int, int, int]]:
        """Get the dimensions of the entire virtual screen (all monitors)."""
        try:
            x = self._user32.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN)
            y = self._user32.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN)
            width = self._user32.GetSystemMetrics(win32con.SM_CXVIRTUALSCREEN)
            height = self._user32.GetSystemMetrics(win32con.SM_CYVIRTUALSCREEN)
            return Result.ok((x, y, width, height))
        except Exception as e:
            error = PlatformError(
                message="Error getting virtual screen dimensions",
                inner_error=e
            )
            self.logger.error(str(error), exc_info=True)
            return Result.fail(error)

    def create_fullscreen_overlay(self, click_through_regions: List[Tuple[int, int, int, int]]) -> Result[int]:
        """Create a transparent overlay across all monitors with click-through holes."""
        dimensions_result = self.get_virtual_screen_dimensions()
        if dimensions_result.is_failure:
            return dimensions_result.convert(lambda _: 0)  # Convert error to int result

        x, y, width, height = dimensions_result.value
        return self.create_transparent_overlay(
            size=(width, height),
            position=(x, y),
            click_through_regions=click_through_regions
        )