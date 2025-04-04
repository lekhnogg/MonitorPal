#src/infrastructure/platform/windows_cold_turkey_service.py

import os
import subprocess
import time
from typing import List, Dict, Any, Optional, Tuple

import win32gui
import win32con

from src.domain.services.i_cold_turkey_service import IColdTurkeyService
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_config_repository_service import IConfigRepository
from src.domain.services.i_window_manager_service import IWindowManager
from src.domain.common.result import Result
from src.domain.common.errors import ConfigurationError, PlatformError, ValidationError


class WindowsColdTurkeyService(IColdTurkeyService):
    """Windows implementation of Cold Turkey Blocker integration."""

    # Constants for timing and verification
    DEFAULT_SLEEP_DURATION = 2.0  # seconds to wait after starting Cold Turkey
    POST_TRIGGER_SLEEP = 1.5  # seconds to wait after triggering the block
    BLOCK_TRIGGER_TIMEOUT = 5  # timeout in seconds for subprocess.run

    # Indicators that a block is active
    BLOCKING_INDICATORS = [
        "for a few seconds", "for a minute", "locked", "blocked",
        "seconds left", "minutes left"
    ]

    def __init__(self,
                 logger: ILoggerService,
                 config_repository: IConfigRepository,
                 window_manager: IWindowManager):
        """Initialize the service."""
        self.logger = logger
        self.config_repository = config_repository
        self.window_manager = window_manager

        # Check if pywinauto is available
        try:
            import pywinauto
            self.pywinauto_available = True
        except ImportError:
            self.pywinauto_available = False
            self.logger.warning("pywinauto is not installed, some verification features will be limited")

    def _run_with_error_handling(self, operation_name: str, func, *args, **kwargs) -> Result:
        """
        Run a function with standardized error handling.

        Args:
            operation_name: Name of the operation for logging
            func: Function to execute
            *args, **kwargs: Arguments to pass to the function

        Returns:
            Result from the function or error Result
        """
        try:
            self.logger.debug(f"Executing {operation_name}")
            return func(*args, **kwargs)
        except Exception as e:
            error_msg = f"Error in {operation_name}: {e}"
            self.logger.error(error_msg)
            return Result.fail(error_msg)

    def execute_block_command(self, block_name: str, duration_minutes: int) -> Result[bool]:
        """Execute a block command to lock a specific block."""

        def _execute():
            blocker_path = self.config_repository.get_cold_turkey_path()
            if not blocker_path or not os.path.exists(blocker_path):
                error = ConfigurationError(
                    message="Cold Turkey Blocker executable not found",
                    details={"path": blocker_path}
                )
                return Result.fail(error)

            normalized_path = os.path.normpath(blocker_path)

            self.logger.info(f"Executing block command for '{block_name}' with duration {duration_minutes} minutes")
            result = subprocess.run(
                [normalized_path, "-start", block_name, "-lock", str(duration_minutes)],
                check=True,
                capture_output=True,
                text=True
            )

            if result.stderr:
                self.logger.warning(f"Cold Turkey command stderr: {result.stderr}")

            return Result.ok(True)

        return self._run_with_error_handling(
            f"execute_block_command({block_name}, {duration_minutes})",
            _execute
        )

    def verify_block(self, block_name: str, platform: Optional[str] = None,
                     register_if_valid: bool = False) -> Result[bool]:
        """
        Verify that a block exists and is properly configured.

        Args:
            block_name: Name of the block to verify
            platform: Optional platform name to associate with the block
            register_if_valid: Whether to register the block if verification succeeds

        Returns:
            Result containing True if verification succeeded, False otherwise
        """
        # Check if registration is requested but platform is missing
        if register_if_valid and not platform:
            error = ValidationError(
                message="Platform is required when registering a verified block",
                details={"block_name": block_name}
            )
            return Result.fail(error)

        # Check if Cold Turkey is configured
        blocker_path_result = self.get_blocker_path()
        if blocker_path_result.is_failure:
            return Result.fail(blocker_path_result.error)

        blocker_path = blocker_path_result.value

        # Ensure Cold Turkey is running
        try:
            subprocess.Popen([blocker_path], shell=False)
            time.sleep(self.DEFAULT_SLEEP_DURATION)  # Allow time for Cold Turkey to open
        except Exception as e:
            self.logger.warning(f"Error starting Cold Turkey: {e}")
            # Continue anyway, as it might already be running

        # Attempt to trigger the block
        try:
            self.logger.debug(f"Triggering block '{block_name}'")
            subprocess.run(
                [blocker_path, "-start", block_name, "-lock", "1"],
                check=True,
                timeout=self.BLOCK_TRIGGER_TIMEOUT
            )
        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to trigger block: {e}"
            self.logger.error(error_msg)
            return Result.fail(error_msg)
        except subprocess.TimeoutExpired:
            self.logger.debug("Block trigger command timed out, which may be normal.")

        time.sleep(self.POST_TRIGGER_SLEEP)  # Allow time for the command to be processed

        # Check if pywinauto is available
        if not self.pywinauto_available:
            error_msg = "pywinauto is not installed, required for verification"
            self.logger.error(error_msg)
            return Result.fail(error_msg)

        # Find the Cold Turkey window
        cold_turkey_hwnd = self._find_cold_turkey_window()

        if not cold_turkey_hwnd:
            error_msg = "Could not find Cold Turkey Blocker window"
            self.logger.error(error_msg)
            return Result.fail(error_msg)

        # Verify using UI automation
        verification_success, row_text = self._verify_cold_turkey_ui(cold_turkey_hwnd, block_name)

        if verification_success:
            self.logger.info(f"Successfully verified block '{block_name}'")

            # Register the block if requested
            if register_if_valid and platform:
                add_result = self.add_verified_block(platform, block_name)
                if add_result.is_failure:
                    self.logger.warning(f"Verification successful but failed to save: {add_result.error}")

            return Result.ok(True)
        else:
            error = PlatformError(
                message=f"Found Cold Turkey window but couldn't find block named '{block_name}'...",
                details={"block_name": block_name}
            )
            return Result.fail(error)

    def _safely_activate_window(self, hwnd: int) -> bool:
        """
        Safely activate a window with proper validation and error handling.

        Args:
            hwnd: Window handle to activate

        Returns:
            Boolean indicating success or failure
        """
        try:
            # First verify the window still exists and is valid
            if not win32gui.IsWindow(hwnd):
                self.logger.warning(f"Window handle {hwnd} is no longer valid")
                return False

            # Check if window is visible
            if not win32gui.IsWindowVisible(hwnd):
                self.logger.warning(f"Window {hwnd} is not visible")
                return False

            # Check if window is minimized and restore it
            if win32gui.IsIconic(hwnd):
                self.logger.debug(f"Restoring minimized window {hwnd}")
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.1)  # Short delay

            # Use a safer approach to activation
            try:
                # First just bring window to top (less intrusive)
                self.logger.debug(f"Bringing window {hwnd} to top")
                win32gui.BringWindowToTop(hwnd)
                time.sleep(0.1)  # Short delay

                # If that wasn't enough, try to set as foreground
                if win32gui.GetForegroundWindow() != hwnd:
                    self.logger.debug(f"Setting window {hwnd} as foreground")
                    win32gui.SetForegroundWindow(hwnd)

                return True
            except Exception as e:
                self.logger.warning(f"Standard window activation failed: {e}")

                # If standard approach fails, try alternative
                try:
                    # Make window topmost temporarily
                    win32gui.SetWindowPos(
                        hwnd,
                        win32con.HWND_TOPMOST,
                        0, 0, 0, 0,
                        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                    )
                    time.sleep(0.1)

                    # Then make it non-topmost again
                    win32gui.SetWindowPos(
                        hwnd,
                        win32con.HWND_NOTOPMOST,
                        0, 0, 0, 0,
                        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                    )

                    return True
                except Exception as alt_e:
                    self.logger.error(f"Alternative window activation also failed: {alt_e}")
                    return False

        except Exception as e:
            self.logger.error(f"Unexpected error in window activation: {e}")
            return False

    def _verify_cold_turkey_ui(self, cold_turkey_hwnd: int, block_name: str) -> Tuple[bool, str]:
        """
        Unified method to verify a block in Cold Turkey by navigating to Blocks tab and checking status.

        Args:
            cold_turkey_hwnd: Window handle for Cold Turkey
            block_name: Name of the block to verify

        Returns:
            Tuple of (verification_success, row_text)
        """
        if not self.pywinauto_available:
            return False, "pywinauto not available"

        import pywinauto
        verification_success = False
        row_text = ""
        app = None

        try:
            # Safely activate the window
            if not self._safely_activate_window(cold_turkey_hwnd):
                return False, "Failed to activate Cold Turkey window"

            time.sleep(0.5)  # Allow UI to update

            # Connect to the Cold Turkey window using pywinauto
            app = pywinauto.Application(backend="uia").connect(handle=cold_turkey_hwnd)
            main_window = app.window(handle=cold_turkey_hwnd)

            # Click on the "Blocks" tab
            blocks_elements = [
                elem for elem in main_window.descendants()
                if hasattr(elem, 'window_text') and "Blocks" in elem.window_text()
            ]

            clicked = False
            for blocks_element in blocks_elements:
                for i in range(3):  # Try up to 3 times
                    try:
                        self.logger.debug(f"Attempting click {i + 1} on Blocks tab")
                        blocks_element.click_input()
                        time.sleep(0.5)
                        clicked = True
                        break
                    except Exception as click_err:
                        self.logger.debug(f"Click {i + 1} failed: {click_err}")
                        time.sleep(0.3)
                if clicked:
                    break

            if not clicked:
                self.logger.warning("Could not find clickable Blocks tab")

            time.sleep(1.0)  # Allow UI to update after tab click

            # Search for the block in the UI
            ui_elements = main_window.descendants()

            # First approach: look for elements containing the block name
            matching_elements = []
            for element in ui_elements:
                try:
                    if hasattr(element, 'window_text'):
                        element_text = element.window_text()
                        if element_text and block_name in element_text:
                            matching_elements.append(element)
                except Exception:
                    pass

            # Check each matching element for blocking indicators
            for element in matching_elements:
                try:
                    element_text = element.window_text().lower()
                    for indicator in self.BLOCKING_INDICATORS:
                        if indicator.lower() in element_text:
                            verification_success = True
                            row_text = element_text
                            break
                    if verification_success:
                        break
                except Exception:
                    pass

            # Alternative: check parent/sibling elements for indicators
            if not verification_success:
                for element in matching_elements:
                    try:
                        parent = element.parent()
                        for sibling in parent.children():
                            if hasattr(sibling, 'window_text'):
                                sibling_text = sibling.window_text().lower()
                                for indicator in self.BLOCKING_INDICATORS:
                                    if indicator.lower() in sibling_text:
                                        verification_success = True
                                        row_text = element.window_text() + " - " + sibling_text
                                        break
                            if verification_success:
                                break
                    except Exception:
                        pass
                    if verification_success:
                        break

        except Exception as e:
            self.logger.error(f"Error in UI verification: {e}")
        finally:
            # Clean up pywinauto resources
            if app:
                try:
                    # Just let the app go out of scope instead of explicitly disconnecting
                    app = None
                except Exception as disconnect_err:
                    self.logger.debug(f"Error cleaning up application: {disconnect_err}")

        return verification_success, row_text

    def _find_cold_turkey_window(self) -> Optional[int]:
        """
        Find the Cold Turkey Blocker window.

        Returns:
            Window handle (HWND) or None if not found
        """
        cold_turkey_hwnd = None

        def enum_windows_callback(hwnd, _):
            nonlocal cold_turkey_hwnd
            if win32gui.IsWindowVisible(hwnd):
                window_text = win32gui.GetWindowText(hwnd)
                if "Cold Turkey Blocker" in window_text or "Cold Turkey Pro" in window_text:
                    cold_turkey_hwnd = hwnd
                    return False  # Stop enumeration
            return True

        win32gui.EnumWindows(enum_windows_callback, None)

        # Try broader search if not found
        if not cold_turkey_hwnd:
            def enum_windows_callback_broader(hwnd, _):
                nonlocal cold_turkey_hwnd
                if win32gui.IsWindowVisible(hwnd):
                    window_text = win32gui.GetWindowText(hwnd)
                    if "Cold Turkey" in window_text:
                        cold_turkey_hwnd = hwnd
                        return False  # Stop enumeration
                return True

            win32gui.EnumWindows(enum_windows_callback_broader, None)

        return cold_turkey_hwnd

    def get_blocker_path(self) -> Result[str]:
        """Get the path to the Cold Turkey executable."""
        path = self.config_repository.get_cold_turkey_path()
        if not path:
            error = ConfigurationError(
                message="Cold Turkey Blocker path not configured",
                details={"path": None}
            )
            return Result.fail(error)
        return Result.ok(path)

    def set_blocker_path(self, path: str) -> Result[bool]:
        """Set the path to the Cold Turkey executable."""
        if not path or not os.path.exists(path):
            error = ValidationError(
                message="Invalid path to Cold Turkey Blocker executable",
                details={"path": path, "exists": os.path.exists(path) if path else False}
            )
            return Result.fail(error)

        return self.config_repository.set_cold_turkey_path(path)

    def get_verified_blocks(self) -> Result[List[Dict[str, Any]]]:
        """Get list of verified platform blocks."""
        return self._run_with_error_handling(
            "get_verified_blocks",
            lambda: Result.ok(self.config_repository.get_global_setting("verified_blocks", []))
        )

    def add_verified_block(self, platform: str, block_name: str) -> Result[bool]:
        """Add a verified platform block to the saved configuration."""

        def _add_block():
            # Get existing verified blocks
            verified_blocks = self.config_repository.get_global_setting("verified_blocks", [])

            # Check if this platform/block is already verified
            for block in verified_blocks:
                if block.get("platform") == platform and block.get("block_name") == block_name:
                    return Result.ok(False)  # Already exists, not an error

            # Add to verified blocks
            verified_blocks.append({
                "platform": platform,
                "block_name": block_name
            })

            # Save verified blocks
            result = self.config_repository.set_global_setting("verified_blocks", verified_blocks)
            if result.is_failure:
                return result

            # Also save block_settings for backward compatibility
            block_settings = self.config_repository.get_global_setting("block_settings", {})
            block_settings[platform] = block_name
            result = self.config_repository.set_global_setting("block_settings", block_settings)
            if result.is_failure:
                return result

            self.logger.info(f"Added verified block for platform {platform}: {block_name}")
            return Result.ok(True)

        return self._run_with_error_handling(
            f"add_verified_block({platform}, {block_name})",
            _add_block
        )

    def remove_verified_block(self, platform: str) -> Result[bool]:
        """Remove a verified platform block from the saved configuration."""

        def _remove_block():
            # Get existing verified blocks
            verified_blocks = self.config_repository.get_global_setting("verified_blocks", [])

            # Find and remove the block for the platform
            original_length = len(verified_blocks)
            verified_blocks = [block for block in verified_blocks if block.get("platform") != platform]

            if len(verified_blocks) == original_length:
                return Result.ok(False)  # Nothing was removed

            # Save verified blocks
            result = self.config_repository.set_global_setting("verified_blocks", verified_blocks)
            if result.is_failure:
                return result

            # Also update block_settings for backward compatibility
            block_settings = self.config_repository.get_global_setting("block_settings", {})
            if platform in block_settings:
                del block_settings[platform]
                result = self.config_repository.set_global_setting("block_settings", block_settings)
                if result.is_failure:
                    return result

            self.logger.info(f"Removed verified block for platform {platform}")
            return Result.ok(True)

        return self._run_with_error_handling(
            f"remove_verified_block({platform})",
            _remove_block
        )

    def clear_verified_blocks(self) -> Result[bool]:
        """Clear all verified platform blocks."""

        def _clear_blocks():
            # Save empty verified blocks
            result = self.config_repository.set_global_setting("verified_blocks", [])
            if result.is_failure:
                return result

            # Also clear block_settings for backward compatibility
            result = self.config_repository.set_global_setting("block_settings", {})
            if result.is_failure:
                return result

            self.logger.info("Cleared all verified blocks")
            return Result.ok(True)

        return self._run_with_error_handling(
            "clear_verified_blocks",
            _clear_blocks
        )

    def is_blocker_path_configured(self) -> bool:
        """Check if Cold Turkey Blocker path is configured."""
        blocker_path = self.config_repository.get_cold_turkey_path()
        return bool(blocker_path and os.path.exists(blocker_path))