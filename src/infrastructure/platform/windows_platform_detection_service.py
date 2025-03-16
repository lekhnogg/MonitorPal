#src/infrastructure/platform/windows_platform_detection_service.py
"""
Windows Platform Detection Service Implementation

Implements platform detection services using Windows-specific APIs.
"""
import time
import psutil
import threading
from typing import Dict, Any, List, Optional

import win32gui
import win32con
import win32process

from src.domain.services.i_platform_detection_service import IPlatformDetectionService
from src.domain.services.i_logger_service import ILoggerService
from src.domain.common.result import Result
from src.domain.services.i_window_manager_service import IWindowManager
from src.domain.common.errors import PlatformError


class WindowsPlatformDetectionService(IPlatformDetectionService):

    """
    Windows-specific implementation of the platform detection service.

    Uses win32gui, win32process, and psutil to interact with Windows windows.
    """

    def __init__(self, logger: ILoggerService, window_manager: IWindowManager):
        """
        Initialize the service with dependencies.

        Args:
            logger: Logging service
            window_manager: Window management service
        """
        self.logger = logger
        self.window_manager = window_manager

        # Mapping from platform name to its executable name
        self._target_executables = {
            "Quantower": "Starter.exe",
            "NinjaTrader": "NinjaTrader.exe",
            "TradingView": "TradingView.exe",
            "Tradovate": "Tradovate.exe",
        }

    def detect_platform_window(self, platform: str, timeout: int = 10,
                               stop_event: Optional[threading.Event] = None) -> Result[Dict[str, Any]]:
        """Detect a window for the specified trading platform."""
        # Validate platform name
        if platform not in self._target_executables:
            error = PlatformError(
                message=f"Unknown platform: {platform}",
                details={
                    "platform": platform,
                    "supported_platforms": list(self._target_executables.keys())
                }
            )
            self.logger.error(str(error))
            return Result.fail(error)

        target_exe = self._target_executables[platform]
        self.logger.debug(f"Looking for {platform} window with executable: {target_exe}")

        # First check if the platform is running at all (fast check)
        running_result = self.is_platform_running(platform)
        if running_result.is_failure:
            return running_result  # Pass through the error

        if not running_result.value:
            error = PlatformError(
                message=f"Platform not running: {platform}",
                details={"platform": platform, "executable": target_exe}
            )
            self.logger.warning(str(error))
            return Result.fail(error)

        detected_info = None
        start_time = time.time()

        while not detected_info:
            # Check if detection should be canceled
            if stop_event and stop_event.is_set():
                error = PlatformError(
                    message="Window detection cancelled by user.",
                    details={"platform": platform}
                )
                return Result.fail(error)

            # Check for timeout
            if time.time() - start_time > timeout:
                error = PlatformError(
                    message=f"Timeout: {platform} window not detected within {timeout} seconds.",
                    details={"platform": platform, "timeout": timeout}
                )
                return Result.fail(error)

            # Look for processes matching the target executable
            try:
                for proc in psutil.process_iter(['pid', 'name']):
                    if proc.info['name'] and proc.info['name'].lower() == target_exe.lower():
                        pid = proc.info['pid']

                        # Create a copy of the PID to avoid any memory issues
                        safe_pid = int(pid)

                        # Get window handle
                        hwnd_result = self.get_window_by_pid(safe_pid)
                        if hwnd_result.is_failure:
                            continue

                        hwnd = hwnd_result.value
                        if hwnd:
                            try:
                                # Create a deep copy of all data to avoid Win32 handle problems
                                title = str(win32gui.GetWindowText(hwnd))

                                # Create a completely new dictionary with basic Python types
                                detected_info = {
                                    "hwnd": int(hwnd),  # Convert to integer
                                    "title": str(title),  # Convert to string
                                    "pid": int(safe_pid),  # Convert to integer
                                    "exe": str(proc.info['name'])  # Convert to string
                                }

                                self.logger.info(f"Detected {platform} window: {detected_info}")

                                # Return a new dictionary to avoid any reference issues
                                return Result.ok(detected_info.copy())
                            except Exception as e:
                                self.logger.debug(f"Error getting window title for hwnd {hwnd}: {e}")
                                continue
            except Exception as e:
                error = PlatformError(
                    message=f"Error enumerating processes for platform {platform}",
                    details={"platform": platform},
                    inner_error=e
                )
                self.logger.warning(f"{error}")

            # Wait before trying again - reduced wait time for more responsiveness
            time.sleep(0.5)  # Check more frequently (was 2 seconds)

        # This should never be reached due to timeout check, but just in case
        error = PlatformError(
            message=f"Failed to detect {platform} window.",
            details={"platform": platform}
        )
        return Result.fail(error)

    def get_window_by_pid(self, pid: int) -> Result[Optional[int]]:
        """
        Get window handle associated with a process ID.

        Args:
            pid: Process ID

        Returns:
            Result containing window handle (hwnd) or None if not found
        """
        try:
            # Use the window manager abstraction
            return self.window_manager.find_window_by_process_id(pid)
        except Exception as e:
            from src.domain.common.errors import PlatformError
            error = PlatformError(
                message=f"Failed to get window by PID {pid}",
                details={"pid": pid},
                inner_error=e
            )
            self.logger.error(str(error))
            return Result.fail(error)

    def is_platform_window_active(self, platform_info: Dict[str, Any]) -> Result[bool]:
        """
        Check if a platform window is currently active (in foreground).

        Args:
            platform_info: Dictionary with platform window information

        Returns:
            Result containing boolean indicating if window is active
        """
        try:
            # Get currently active window using the window manager
            active_window_result = self.window_manager.get_foreground_window()
            if active_window_result.is_failure:
                return Result.fail(active_window_result.error)

            hwnd_active = active_window_result.value
            if not hwnd_active:
                self.logger.debug("No active window detected.")
                return Result.ok(False)

            # Get PID of active window
            active_pid_result = self.window_manager.get_window_process_id(hwnd_active)
            if active_pid_result.is_failure:
                return Result.fail(active_pid_result.error)

            active_pid = active_pid_result.value

            # Get PID of target platform window
            target_pid = platform_info.get("pid")

            self.logger.debug(f"Active window PID: {active_pid}, Target window PID: {target_pid}")

            # Compare PIDs
            is_active = active_pid == target_pid
            if is_active:
                self.logger.debug("Match found: platform window is active.")
            else:
                self.logger.debug("No match: active window is not the target platform.")

            return Result.ok(is_active)
        except Exception as e:
            self.logger.error(f"Error checking if window is active: {e}")
            return Result.fail(f"Error checking if window is active: {e}")

    def get_all_windows_for_pid(self, pid: int) -> Result[List[int]]:
        """
        Get all visible window handles for the given process ID.

        Args:
            pid: Process ID

        Returns:
            Result containing a list of window handles (hwnds)
        """
        hwnds = []

        def enum_callback(hwnd, _):
            try:
                if win32gui.IsWindowVisible(hwnd):
                    try:
                        _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
                        if found_pid == pid:
                            hwnds.append(hwnd)
                    except Exception:
                        # Skip this window if we can't get its PID
                        pass
            except Exception:
                # Skip this window on any other error
                pass
            return True

        try:
            # Wrap EnumWindows in try-except and continue even if it fails
            try:
                win32gui.EnumWindows(enum_callback, None)
            except Exception as e:
                self.logger.error(f"Error enumerating windows: {e}")
                # Continue execution as we might have found some windows before the error

            return Result.ok(hwnds)
        except Exception as e:
            self.logger.error(f"Unexpected error in get_all_windows_for_pid: {e}")
            return Result.fail(f"Error getting windows for PID {pid}: {e}")

    def force_foreground_window(self, hwnd: int) -> Result[bool]:
        """
        Bring a window to the foreground (make it active).

        Args:
            hwnd: Window handle

        Returns:
            Result indicating success or failure
        """
        try:
            # Safety check: Valid window handle?
            import win32gui
            if not win32gui.IsWindow(hwnd):
                self.logger.warning(f"Handle {hwnd} is not a valid window")
                return Result.fail(f"Invalid window handle: {hwnd}")

            # Safety check: Is window visible?
            if not win32gui.IsWindowVisible(hwnd):
                self.logger.warning(f"Window {hwnd} is not visible")
                return Result.fail(f"Window {hwnd} is not visible")

            # Check if window is minimized and restore it
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                # Small delay to let the window restore
                import time
                time.sleep(0.1)

            # Basic approach - use Windows API directly through win32gui
            # Avoid mixing ctypes with win32gui in the same operation
            try:
                # Make window topmost, then disable topmost
                win32gui.SetWindowPos(
                    hwnd,
                    win32con.HWND_TOPMOST,
                    0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                )

                # Short delay
                import time
                time.sleep(0.2)

                # Remove topmost flag
                win32gui.SetWindowPos(
                    hwnd,
                    win32con.HWND_NOTOPMOST,
                    0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                )

                # Try to set as foreground
                try:
                    win32gui.SetForegroundWindow(hwnd)
                    return Result.ok(True)
                except Exception:
                    # Try alternative - Show + SW_RESTORE is sometimes more reliable
                    win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    return Result.ok(True)

            except Exception as window_ex:
                self.logger.debug(f"Window activation failed: {window_ex}")
                # Return failure but don't try additional unsafe methods
                return Result.fail(f"Failed to bring window to foreground: {window_ex}")

        except Exception as e:
            self.logger.warning(f"Failed to force foreground for window {hwnd}: {e}")
            return Result.fail(f"Failed to force foreground for window {hwnd}: {e}")

    def activate_platform_windows(self, platform: str) -> Result[bool]:
        """
        Activate all windows associated with a platform.

        Args:
            platform: Platform name

        Returns:
            Result indicating success or failure
        """
        try:
            if platform not in self._target_executables:
                return Result.fail(f"No mapping for platform '{platform}'.")

            target_exe = self._target_executables[platform]
            activated_count = 0

            # First find processes matching target executable
            matching_processes = []
            try:
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        if proc.info['name'] and proc.info['name'].lower() == target_exe.lower():
                            matching_processes.append(proc.info['pid'])
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue
            except Exception as e:
                self.logger.warning(f"Error enumerating processes: {e}")
                # Continue with any processes we found

            # Early return if no processes found
            if not matching_processes:
                self.logger.warning(f"No processes found for platform {platform}")
                return Result.fail(f"No processes found for platform {platform}")

            # Now try to activate windows for these processes
            # Try to focus on main window rather than activating all windows
            for pid in matching_processes:
                try:
                    windows_result = self.get_all_windows_for_pid(pid)

                    if windows_result.is_success:
                        hwnds = windows_result.value
                        for hwnd in hwnds:
                            try:
                                # Safe check here - is the window still valid?
                                if not win32gui.IsWindow(hwnd):
                                    continue

                                # Process one window at a time with deliberate delay
                                force_result = self.force_foreground_window(hwnd)
                                if force_result.is_success:
                                    activated_count += 1
                                    # Small delay between activations
                                    time.sleep(0.2)

                            except Exception as e:
                                self.logger.warning(f"Error activating window {hwnd}: {e}")
                except Exception as e:
                    self.logger.warning(f"Error processing PID {pid}: {e}")

            if activated_count > 0:
                self.logger.info(f"Activated {activated_count} windows for platform {platform}")
                return Result.ok(True)
            else:
                self.logger.warning(f"No windows found to activate for platform {platform}")
                return Result.fail(f"No windows found to activate for platform {platform}")
        except Exception as e:
            self.logger.error(f"Error activating platform windows: {e}")
            return Result.fail(f"Error activating platform windows: {e}")

    def get_supported_platforms(self) -> Result[Dict[str, str]]:
        """
        Get dictionary of supported platforms and their executable names.

        Returns:
            Result containing dictionary mapping platform names to executable names
        """
        return Result.ok(self._target_executables.copy())

    def is_platform_running(self, platform: str) -> Result[bool]:
        """
        Quickly check if a platform's process is running without full window detection.

        Args:
            platform: Platform name (e.g., "Quantower", "NinjaTrader")

        Returns:
            Result containing True if the platform is running, False otherwise
        """
        try:
            # Validate platform name
            if platform not in self._target_executables:
                error = PlatformError(
                    message=f"Unknown platform: {platform}",
                    details={
                        "platform": platform,
                        "supported_platforms": list(self._target_executables.keys())
                    }
                )
                self.logger.error(str(error))
                return Result.fail(error)

            target_exe = self._target_executables[platform]
            self.logger.debug(f"Checking if {platform} is running (executable: {target_exe})")

            # Check for processes matching the target executable
            import psutil
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['name'] and proc.info['name'].lower() == target_exe.lower():
                        self.logger.debug(f"Found running process for {platform}: PID {proc.info['pid']}")
                        return Result.ok(True)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue

            self.logger.debug(f"No running process found for {platform}")
            return Result.ok(False)

        except Exception as e:
            error = PlatformError(
                message=f"Error checking if platform is running: {platform}",
                details={"platform": platform},
                inner_error=e
            )
            self.logger.error(str(error))
            return Result.fail(error)