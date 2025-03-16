#src/infrastructure/platform/lockout_service.py

"""
Implementation of the lockout service for Windows.

This service creates an overlay window with click-through holes for flatten buttons
and executes Cold Turkey Blocker commands to lock out trading platforms.
"""
import time
from typing import List, Dict, Any, Optional, Callable, Tuple

from src.domain.services.i_lockout_service import ILockoutService
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_background_task_service import Worker, IBackgroundTaskService
from src.domain.services.i_platform_detection_service import IPlatformDetectionService
from src.domain.services.i_config_repository_service import IConfigRepository
from src.domain.services.i_window_manager_service import IWindowManager
from src.domain.services.i_ui_service import IUIService
from src.domain.services.i_cold_turkey_service import IColdTurkeyService
from src.domain.common.result import Result
from src.domain.common.errors import ValidationError, ConfigurationError, PlatformError

class LockoutWorker(Worker[bool]):
    """Worker for executing the lockout sequence in a background thread."""

    def __init__(self,
                 platform: str,
                 flatten_positions: List[Dict[str, Any]],
                 lockout_duration: int,
                 platform_detection_service: IPlatformDetectionService,
                 window_manager: IWindowManager,
                 ui_service: IUIService,
                 cold_turkey_service: IColdTurkeyService,
                 logger: ILoggerService,
                 on_status_update: Optional[Callable[[str, str], None]] = None):
        """Initialize the lockout worker."""
        super().__init__()
        self.platform = platform
        self.flatten_positions = flatten_positions
        self.lockout_duration = lockout_duration
        self.platform_detection_service = platform_detection_service
        self.window_manager = window_manager
        self.ui_service = ui_service
        self.cold_turkey_service = cold_turkey_service
        self.logger = logger
        self.on_status_update = on_status_update

        # Mapping from platform name to Cold Turkey block name (customizable)
        self.platform_mapping = {
            "NinjaTrader": "Ninja",
            # Other platforms use default (first word of platform name)
        }

        # State variables
        self.overlay_hwnd = 0

    def execute(self) -> bool:
        """Execute the lockout sequence."""
        try:
            self.report_status(f"Bringing {self.platform} windows forward...", "INFO")

            # Step 1: Bring platform windows to foreground
            activate_result = self.platform_detection_service.activate_platform_windows(self.platform)
            if activate_result.is_failure:
                self.logger.warning(f"Window activation warning: {activate_result.error}")
                # Continue anyway, as this is not critical

            # Step 2: Show info dialog
            self.ui_service.show_message(
                "Lockout Notice",
                f"Stop Loss triggered on {self.platform}.\n\n"
                "You have 30 seconds to flatten positions by clicking in the designated holes.\n"
                "All other areas are blocked!"
            )

            # Step 3: Create overlay
            self.report_status(f"Creating overlay with flatten positions...", "INFO")

            # Get screen dimensions
            import ctypes
            import win32con
            user32 = ctypes.windll.user32
            scr_w = user32.GetSystemMetrics(win32con.SM_CXSCREEN)
            scr_h = user32.GetSystemMetrics(win32con.SM_CYSCREEN)

            # Convert flatten positions format
            click_through_regions = []
            for pos in self.flatten_positions:
                coords = pos.get("coords")
                if coords:
                    x1, y1, x2, y2 = coords
                    w = x2 - x1
                    h = y2 - y1
                    click_through_regions.append((x1, y1, w, h))

            # Create the overlay window using the window manager
            overlay_result = self.window_manager.create_transparent_overlay(
                size=(scr_w, scr_h),
                position=(0, 0),
                click_through_regions=click_through_regions
            )

            if overlay_result.is_failure:
                self.report_error(f"Failed to create overlay: {overlay_result.error}")
                return False

            self.overlay_hwnd = overlay_result.value
            self.logger.info(f"Created overlay window with handle: {self.overlay_hwnd}")

            # Step 4: Wait for 30 seconds (with cancelation support)
            self.report_status(f"Lockout countdown (30s) started for {self.platform}...", "INFO")
            for i in range(30):
                if self.cancel_requested:
                    break
                self.report_progress(i * 3 + 10, f"Countdown: {30 - i} seconds remaining")
                time.sleep(1)

            # Destroy overlay window
            if self.overlay_hwnd:
                destroy_result = self.window_manager.destroy_window(self.overlay_hwnd)
                if destroy_result.is_failure:
                    self.logger.warning(f"Failed to destroy overlay window: {destroy_result.error}")
                self.overlay_hwnd = 0

            # Check if we were cancelled
            if self.cancel_requested:
                self.report_status("Lockout sequence cancelled", "WARNING")
                return False

            # Step 5: Execute Cold Turkey command
            self.report_status(f"Locking {self.platform} for {self.lockout_duration} minute(s)...", "INFO")

            # Get platform command
            platform_cmd = self._get_platform_cmd(self.platform)

            # Execute block command
            block_result = self.cold_turkey_service.execute_block_command(
                platform_cmd, self.lockout_duration
            )

            if block_result.is_failure:
                self.report_error(f"Failed to execute Cold Turkey block: {block_result.error}")
                return False

            self.report_status(
                f"Lockout executed successfully. {self.platform} locked for {self.lockout_duration} minute(s).",
                "SUCCESS"
            )
            return True

        except Exception as e:
            self.logger.error(f"Lockout error: {e}")
            self.report_error(f"Lockout error: {e}")
            return False
        finally:
            # Make sure overlay is destroyed even if an exception occurs
            if self.overlay_hwnd:
                try:
                    self.window_manager.destroy_window(self.overlay_hwnd)
                except Exception as e:
                    self.logger.error(f"Error destroying overlay in finally block: {e}")

    def _get_platform_cmd(self, platform: str) -> str:
        """Get the platform command for Cold Turkey Blocker."""
        # Check mapping first
        if platform in self.platform_mapping:
            return self.platform_mapping[platform]

        # Default to capitalizing the first part
        return platform.split()[0].capitalize()

    def report_status(self, message: str, level: str) -> None:
        """Report status update to callback if available."""
        self.logger.info(message)
        if self.on_status_update:
            self.on_status_update(message, level)


class WindowsLockoutService(ILockoutService):
    """Windows implementation of the lockout service."""

    def __init__(self,
                 logger: ILoggerService,
                 config_repository: IConfigRepository,
                 platform_detection_service: IPlatformDetectionService,
                 window_manager: IWindowManager,
                 ui_service: IUIService,
                 cold_turkey_service: IColdTurkeyService,
                 thread_service: IBackgroundTaskService):
        """Initialize the lockout service."""
        self.logger = logger
        self.config_repository = config_repository
        self.platform_detection_service = platform_detection_service
        self.window_manager = window_manager
        self.ui_service = ui_service
        self.cold_turkey_service = cold_turkey_service
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

            # Check if Cold Turkey is configured
            if not self.cold_turkey_service.is_blocker_path_configured():
                error = ConfigurationError(
                    message="Cold Turkey Blocker path not configured or invalid"
                )
                return Result.fail(error)

            # Create worker
            worker = LockoutWorker(
                platform=platform,
                flatten_positions=flatten_positions,
                lockout_duration=lockout_duration,
                platform_detection_service=self.platform_detection_service,
                window_manager=self.window_manager,
                ui_service=self.ui_service,
                cold_turkey_service=self.cold_turkey_service,
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
        return self.cold_turkey_service.verify_block_configuration(block_name)

    def get_blocker_path(self) -> Result[str]:
        """Get the path to the Cold Turkey Blocker executable."""
        return self.cold_turkey_service.get_blocker_path()

    def set_blocker_path(self, path: str) -> Result[bool]:
        """Set the path to the Cold Turkey Blocker executable."""
        return self.cold_turkey_service.set_blocker_path(path)