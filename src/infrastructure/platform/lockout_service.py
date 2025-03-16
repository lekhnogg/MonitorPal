# src/infrastructure/platform/lockout_service.py
"""
Implementation of the lockout service for Windows.

This service creates an overlay window with click-through holes for flatten buttons
and executes Cold Turkey Blocker commands to lock out trading platforms.
"""
import os
import time
import subprocess
import ctypes
from typing import List, Dict, Any, Optional, Callable

import win32gui
import win32con
from PySide6.QtWidgets import QMessageBox, QApplication
from PySide6.QtCore import QThread, Signal, Slot, QObject, QTimer

from src.domain.services.i_lockout_service import ILockoutService
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_background_task_service import Worker, IBackgroundTaskService
from src.domain.services.i_platform_detection_service import IPlatformDetectionService
from src.domain.services.i_config_repository_service import IConfigRepository
from src.domain.common.result import Result
from src.domain.common.errors import ValidationError, ConfigurationError, PlatformError

# Win32 constants for layered window
WS_EX_LAYERED = 0x00080000
WS_EX_TOPMOST = 0x00000008
WS_POPUP = 0x80000000
ULW_ALPHA = 0x02
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01


class OverlaySignals(QObject):
    """Qt signals for overlay window operations."""
    overlay_created = Signal(int)  # hwnd
    overlay_closed = Signal()
    overlay_error = Signal(str)


class LockoutWorker(Worker[bool]):
    """Worker for executing the lockout sequence in a background thread."""

    def __init__(self,
                 platform: str,
                 flatten_positions: List[Dict[str, Any]],
                 lockout_duration: int,
                 blocker_path: str,
                 platform_detection_service: IPlatformDetectionService,
                 logger: ILoggerService,
                 on_status_update: Optional[Callable[[str, str], None]] = None):
        """Initialize the lockout worker."""
        super().__init__()
        self.platform = platform
        self.flatten_positions = flatten_positions
        self.lockout_duration = lockout_duration
        self.blocker_path = blocker_path
        self.platform_detection_service = platform_detection_service
        self.logger = logger
        self.on_status_update = on_status_update

        # Mapping from platform name to Cold Turkey block name (customizable)
        self.platform_mapping = {
            "NinjaTrader": "Ninja",
            # Other platforms use default (first word of platform name)
        }

        # Qt signals for cross-thread communication
        self.signals = OverlaySignals()
        self.overlay_hwnd = 0
        self.overlay_countdown_finished = False

    def execute(self) -> bool:
        """Execute the lockout sequence."""
        try:
            self.report_status(f"Bringing {self.platform} windows forward...", "INFO")

            # Step 1: Bring platform windows to foreground
            activate_result = self.platform_detection_service.activate_platform_windows(self.platform)
            if activate_result.is_failure:
                self.logger.warning(f"Window activation warning: {activate_result.error}")
                # Continue anyway, as this is not critical

            # Step 2: Show info dialog - this must be done in the main UI thread
            QTimer.singleShot(0, lambda: self._show_lockout_notice())

            # Wait a bit for the dialog to be displayed and closed
            time.sleep(1)

            # Step 3: Create overlay
            self.report_status(f"Creating overlay with flatten positions...", "INFO")

            # Get screen dimensions
            user32 = ctypes.windll.user32
            scr_w = user32.GetSystemMetrics(win32con.SM_CXSCREEN)
            scr_h = user32.GetSystemMetrics(win32con.SM_CYSCREEN)

            # Create overlay in the main thread via a signal
            overlay_created = False
            error_message = None

            def create_overlay_in_main_thread():
                nonlocal overlay_created, error_message
                try:
                    from src.infrastructure.platform.overlay_window import create_layered_window
                    hwnd = create_layered_window(self.flatten_positions, scr_w, scr_h)
                    if hwnd:
                        self.overlay_hwnd = hwnd
                        overlay_created = True
                    else:
                        error_message = "Failed to create overlay window"
                except Exception as e:
                    error_message = str(e)

            # Execute in main thread and wait for completion
            QTimer.singleShot(0, create_overlay_in_main_thread)

            # Wait for overlay creation
            countdown = 10  # 1 second timeout
            while not overlay_created and countdown > 0 and not error_message:
                time.sleep(0.1)
                countdown -= 1

            if error_message:
                self.report_error(f"Failed to create overlay: {error_message}")
                return False

            if not overlay_created:
                self.report_error("Timeout waiting for overlay window creation")
                return False

            # Step 4: Wait for 30 seconds (with cancelation support)
            self.report_status(f"Lockout countdown (30s) started for {self.platform}...", "INFO")
            for i in range(30):
                if self.cancel_requested:
                    break
                time.sleep(1)

            # Destroy overlay window
            if self.overlay_hwnd:
                try:
                    def destroy_overlay():
                        user32.DestroyWindow(self.overlay_hwnd)
                        self.overlay_hwnd = 0

                    QTimer.singleShot(0, destroy_overlay)
                    time.sleep(0.5)  # Give a moment for window destruction
                except Exception as e:
                    self.logger.error(f"Error destroying overlay window: {e}")

            # Check if we were cancelled
            if self.cancel_requested:
                self.report_status("Lockout sequence cancelled", "WARNING")
                return False

            # Step 5: Execute Cold Turkey command
            self.report_status(f"Locking {self.platform} for {self.lockout_duration} minute(s)...", "INFO")

            # Get platform command
            platform_cmd = self._get_platform_cmd(self.platform)

            # Execute command
            result = self._execute_blocker_command(self.blocker_path, platform_cmd, self.lockout_duration)

            if result:
                self.report_status(
                    f"Lockout executed successfully. {self.platform} locked for {self.lockout_duration} minute(s).",
                    "SUCCESS"
                )
                return True
            else:
                self.report_error("Failed to execute Cold Turkey blocker command")
                return False

        except Exception as e:
            self.logger.error(f"Lockout error: {e}")
            self.report_error(f"Lockout error: {e}")
            return False

    def _show_lockout_notice(self):
        """Show notice dialog about the lockout."""
        try:
            QMessageBox.information(
                None,
                "Lockout Notice",
                f"Stop Loss triggered on {self.platform}.\n\n"
                "You have 30 seconds to flatten positions by clicking in the designated holes.\n"
                "All other areas are blocked!"
            )
        except Exception as e:
            self.logger.error(f"Error showing lockout notice: {e}")

    def _get_platform_cmd(self, platform: str) -> str:
        """Get the platform command for Cold Turkey Blocker."""
        # Check mapping first
        if platform in self.platform_mapping:
            return self.platform_mapping[platform]

        # Default to capitalizing the first part
        return platform.split()[0].capitalize()

    def _execute_blocker_command(self, blocker_path: str, platform_cmd: str, lockout_duration: int) -> bool:
        """Execute the Cold Turkey Blocker command."""
        try:
            normalized_path = os.path.normpath(blocker_path)
            cmd = f'"{normalized_path}" -start "{platform_cmd}" -lock "{lockout_duration}"'
            self.logger.info(f"Executing command: {cmd}")

            # Execute command
            result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)

            self.logger.info(f"Cold Turkey command output: {result.stdout}")
            if result.stderr:
                self.logger.warning(f"Cold Turkey command stderr: {result.stderr}")

            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to execute Cold Turkey: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            return False

    def report_status(self, message: str, level: str) -> None:
        """Report status update to callback if available."""
        self.logger.info(message)
        if self.on_status_update:
            self.on_status_update(message, level)
        # Also report progress
        self.report_progress(50, message)


class WindowsLockoutService(ILockoutService):
    """Windows implementation of the lockout service."""

    def __init__(self,
                 logger: ILoggerService,
                 config_repository: IConfigRepository,
                 platform_detection_service: IPlatformDetectionService,
                 thread_service: IBackgroundTaskService):
        """Initialize the lockout service."""
        self.logger = logger
        self.config_repository = config_repository
        self.platform_detection_service = platform_detection_service
        self.thread_service = thread_service
        self.lockout_task_id = "lockout_sequence"

    def perform_lockout(self,
                        platform: str,
                        flatten_positions: List[Dict[str, Any]],
                        lockout_duration: int,
                        on_status_update: Optional[Callable[[str, str], None]] = None) -> Result[bool]:
        """Perform the lockout sequence for a trading platform."""
        try:
            self.logger.info(f"Starting lockout sequence for {platform}")

            # Validate inputs
            if not platform:
                error = ValidationError(
                    message="Platform name cannot be empty",
                    details={"required": "platform"}
                )
                return Result.fail(error)

            if not flatten_positions:
                error = ValidationError(
                    message="Flatten positions cannot be empty",
                    details={"required": "flatten_positions"}
                )
                return Result.fail(error)

            # Get blocker path
            blocker_path = self.config_repository.get_cold_turkey_path()
            if not blocker_path or not os.path.exists(blocker_path):
                error = ConfigurationError(
                    message="Cold Turkey Blocker path not configured or invalid",
                    details={"path": blocker_path, "exists": os.path.exists(blocker_path) if blocker_path else False}
                )
                return Result.fail(error)

            # Create worker
            worker = LockoutWorker(
                platform=platform,
                flatten_positions=flatten_positions,
                lockout_duration=lockout_duration,
                blocker_path=blocker_path,
                platform_detection_service=self.platform_detection_service,
                logger=self.logger,
                on_status_update=on_status_update
            )

            # Execute in background thread
            return self.thread_service.execute_task_with_auto_cleanup(self.lockout_task_id, worker)

        except Exception as e:
            error = PlatformError(
                message=f"Lockout error: {e}",
                details={"platform": platform},
                inner_error=e
            )
            self.logger.error(str(error))
            return Result.fail(error)

    def verify_blocker_configuration(self, platform: str, block_name: str) -> Result[bool]:
        """Verify that Cold Turkey Blocker is properly configured for the platform."""
        # This requires UI automation which would be complex to implement here
        # We'll provide a minimal implementation that just checks the executable exists
        blocker_path = self.config_repository.get_cold_turkey_path()
        if not blocker_path or not os.path.exists(blocker_path):
            return Result.fail("Cold Turkey Blocker executable not found")

        # We could add more verification here, such as:
        # - Check if the block exists
        # - Check if the block is properly configured
        # - Test a quick block/unblock

        return Result.ok(True)

    def get_blocker_path(self) -> Result[str]:
        """Get the path to the Cold Turkey Blocker executable."""
        path = self.config_repository.get_cold_turkey_path()
        if not path:
            return Result.fail("Cold Turkey Blocker path not configured")
        return Result.ok(path)

    def set_blocker_path(self, path: str) -> Result[bool]:
        """Set the path to the Cold Turkey Blocker executable."""
        if not path or not os.path.exists(path):
            return Result.fail("Invalid path to Cold Turkey Blocker executable")

        result = self.config_repository.set_cold_turkey_path(path)
        if result.is_failure:
            return result

        return Result.ok(True)