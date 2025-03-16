# src/infrastructure/platform/overlay_window.py
"""
Layered window implementation for creating transparent overlays with click-through regions.
"""
import ctypes
from ctypes import wintypes
from typing import List, Dict, Any, Tuple

import win32gui
import win32con

# Win32 & Ctypes definitions for creating the layered window
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

# Window style constants
WS_EX_LAYERED = 0x00080000
WS_EX_TOPMOST = 0x00000008
WS_POPUP = 0x80000000

ULW_ALPHA = 0x02
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01

WM_QUIT = 0x0012
PM_REMOVE = 0x0001


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
WNDPROC = ctypes.WINFUNCTYPE(wintypes.LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

def wndproc(hwnd, msg, wparam, lparam):
    """Window procedure for the overlay window."""
    if msg == win32con.WM_DESTROY:
        user32.PostQuitMessage(0)
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def create_layered_window(flatten_positions: List[Dict[str, Any]], screen_w: int, screen_h: int, alpha_block: int = 200) -> int:
    """
    Create a layered window with click-through holes for flatten buttons.

    Args:
        flatten_positions: List of dictionaries with "coords" specifying rectangles
        screen_w: Screen width
        screen_h: Screen height
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
        hInstance = kernel32.GetModuleHandleW(None)
        if not hInstance:
            raise OSError("GetModuleHandleW(None) failed")

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

        hWnd = user32.CreateWindowExW(
            styleEx,
            atom_class,
            "LockoutOverlay",
            style,
            0, 0,
            screen_w, screen_h,
            0, 0,
            hInstance,
            None
        )
        if not hWnd:
            raise OSError("CreateWindowExW failed for layered window.")

        # Get device contexts
        hdcScreen = user32.GetDC(0)
        hdcMem = gdi32.CreateCompatibleDC(hdcScreen)

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
        hBmp = gdi32.CreateDIBSection(
            hdcScreen,
            ctypes.byref(bmi),
            win32con.DIB_RGB_COLORS,
            ctypes.byref(ppvBits),
            None,
            0
        )
        if not hBmp:
            raise OSError("CreateDIBSection failed")

        # Select bitmap into DC
        old_obj = gdi32.SelectObject(hdcMem, hBmp)
        if not old_obj:
            print("SelectObject failed")

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
        ptWinPos = POINT(0, 0)
        blend = BLENDFUNCTION()
        blend.BlendOp = AC_SRC_OVER
        blend.BlendFlags = 0
        blend.SourceConstantAlpha = 255
        blend.AlphaFormat = AC_SRC_ALPHA

        result = user32.UpdateLayeredWindow(
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
            print(f"UpdateLayeredWindow failed: {ctypes.GetLastError()}")

        # Clean up GDI resources used for creation, now that window is updated
        if old_obj:
            gdi32.SelectObject(hdcMem, old_obj)

        if hdcScreen:
            user32.ReleaseDC(0, hdcScreen)
            hdcScreen = 0

        if hdcMem:
            gdi32.DeleteDC(hdcMem)
            hdcMem = 0

        if hBmp:
            gdi32.DeleteObject(hBmp)
            hBmp = 0

        # Show the window
        user32.ShowWindow(hWnd, win32con.SW_SHOWNORMAL)
        user32.UpdateWindow(hWnd)

        return hWnd

    except Exception as e:
        print(f"Error creating layered window: {e}")

        # Clean up resources on failure
        if hdcScreen:
            user32.ReleaseDC(0, hdcScreen)

        if hdcMem:
            gdi32.DeleteDC(hdcMem)

        if hBmp:
            gdi32.DeleteObject(hBmp)

        if hWnd:
            user32.DestroyWindow(hWnd)

        if atom_class:
            win32gui.UnregisterClass(atom_class, kernel32.GetModuleHandleW(None))

        return 0