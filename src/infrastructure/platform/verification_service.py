# NewLayout/src/infrastructure/platform/verification_service.py
"""
Windows implementation of the verification service.

This service verifies that Cold Turkey Blocker is properly configured
to block trading platforms, using UI automation to check block status.
"""
import os
import subprocess
import time
from typing import Dict, Any, List, Optional, Tuple

import win32gui

try:
    import pywinauto
except ImportError:
    pywinauto = None

from src.domain.services.i_verification_service import IVerificationService
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_background_task_service import IBackgroundTaskService, Worker
from src.domain.services.i_config_repository_service import IConfigRepository
from src.domain.common.result import Result


class VerificationWorker(Worker[bool]):
    """Worker for verifying Cold Turkey Blocker configuration."""

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
                 platform: str,
                 block_name: str,
                 blocker_path: str,
                 logger: ILoggerService):
        """Initialize the verification worker."""
        super().__init__()
        self.platform = platform
        self.block_name = block_name
        self.blocker_path = blocker_path
        self.logger = logger

    def execute(self) -> bool:
        """Execute the verification process."""
        try:
            self.logger.info(f"Verifying block '{self.block_name}' for platform '{self.platform}'")

            if not self.blocker_path or not os.path.exists(self.blocker_path):
                self.report_error("Cold Turkey Blocker executable not found")
                return False

            # Ensure Cold Turkey is running
            try:
                subprocess.Popen([self.blocker_path], shell=False)
                time.sleep(self.DEFAULT_SLEEP_DURATION)  # Allow time for Cold Turkey to open
            except Exception as e:
                self.logger.error(f"Error starting Cold Turkey: {e}")
                # Continue anyway, as it might already be running

            # Attempt to trigger the block
            try:
                self.logger.debug(f"Triggering block '{self.block_name}'")
                subprocess.run(
                    [self.blocker_path, "-start", self.block_name, "-lock", "1"],
                    check=True,
                    timeout=self.BLOCK_TRIGGER_TIMEOUT
                )
            except subprocess.CalledProcessError as e:
                self.report_error(f"Failed to trigger block: {e}")
                return False
            except subprocess.TimeoutExpired:
                self.logger.debug("Block trigger command timed out, which may be normal.")

            time.sleep(self.POST_TRIGGER_SLEEP)  # Allow time for the command to be processed

            # Check if pywinauto is available
            if pywinauto is None:
                self.report_error("pywinauto is not installed, required for verification")
                return False

            # Find and verify the Cold Turkey window
            verification_success = False
            found_window = False
            found_block_row = False
            error_message = ""
            row_text = ""

            # Find the Cold Turkey window
            cold_turkey_hwnd = self._find_cold_turkey_window()

            if cold_turkey_hwnd:
                found_window = True
                self.logger.info(f"Found Cold Turkey window: {cold_turkey_hwnd}")

                try:
                    # Bring the window to the foreground
                    win32gui.ShowWindow(cold_turkey_hwnd, win32gui.SW_RESTORE)
                    win32gui.SetForegroundWindow(cold_turkey_hwnd)
                    time.sleep(0.5)

                    # Connect to the Cold Turkey window using pywinauto
                    app = pywinauto.Application(backend="uia").connect(handle=cold_turkey_hwnd)
                    main_window = app.window(handle=cold_turkey_hwnd)

                    # Try to click on the "Blocks" tab
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
                            self.logger.info("Successfully clicked on the Blocks tab")
                            break

                    if not clicked:
                        self.logger.warning("Could not find clickable Blocks tab")

                    time.sleep(1.0)

                    # Look for block name and checking indicators
                    verification_success, row_text = self._check_for_block_in_window(main_window, self.block_name)

                    if verification_success:
                        self.logger.info(f"Successfully verified block '{self.block_name}'")
                        found_block_row = True
                    else:
                        self.logger.warning(f"Could not verify block '{self.block_name}'")

                except Exception as e:
                    self.logger.error(f"Error during verification process: {e}")
                    error_message = str(e)

            # Handle verification result
            if verification_success:
                return True
            else:
                if not found_window:
                    self.report_error("Could not find Cold Turkey Blocker window")
                elif not found_block_row:
                    self.report_error(
                        f"Found Cold Turkey window but couldn't find block named '{self.block_name}' with active blocking. "
                        f"Please check that the block name exactly matches your Cold Turkey configuration."
                    )
                else:
                    self.report_error(f"Verification failed: {error_message}")
                return False

        except Exception as e:
            self.logger.error(f"Unexpected error in verification: {e}")
            self.report_error(f"Unexpected error: {e}")
            return False

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

    def _check_for_block_in_window(self, main_window, block_name: str) -> Tuple[bool, str]:
        """
        Check if the specified block is active in the Cold Turkey window.

        Args:
            main_window: pywinauto window object
            block_name: Name of the block to check

        Returns:
            Tuple of (verification_success, row_text)
        """
        verification_success = False
        row_text = ""

        try:
            # Get all UI elements
            ui_elements = main_window.descendants()

            # First approach: look for elements containing the block name
            matching_rows = []
            for element in ui_elements:
                try:
                    if hasattr(element, 'window_text'):
                        element_text = element.window_text()
                        if element_text and block_name in element_text:
                            matching_rows.append(element)
                            self.logger.debug(f"Found potential block row: '{element_text}'")
                except Exception as el_err:
                    self.logger.debug(f"Error reading element: {el_err}")

            # Check each matching row for blocking indicators
            if matching_rows:
                for row in matching_rows:
                    try:
                        row_text = row.window_text().lower()
                        self.logger.debug(f"Checking row text: '{row_text}'")
                        for indicator in self.BLOCKING_INDICATORS:
                            if indicator.lower() in row_text:
                                self.logger.info(f"Found block indicator '{indicator}' in row")
                                verification_success = True
                                break
                        if verification_success:
                            break
                    except Exception as row_err:
                        self.logger.debug(f"Error checking row: {row_err}")

            # Alternative approach: check siblings/children
            if not verification_success:
                self.logger.debug("Trying alternative approach - checking siblings/children...")
                block_elements = [
                    element for element in ui_elements
                    if hasattr(element, 'window_text') and block_name in element.window_text()
                ]

                for block_element in block_elements:
                    try:
                        parent = block_element.parent()
                        siblings = parent.children()

                        for sibling in siblings:
                            try:
                                if hasattr(sibling, 'window_text'):
                                    sibling_text = sibling.window_text().lower()
                                    for indicator in self.BLOCKING_INDICATORS:
                                        if indicator.lower() in sibling_text:
                                            self.logger.info(f"Found block indicator '{indicator}' in sibling")
                                            verification_success = True
                                            break
                                    if verification_success:
                                        break
                            except Exception:
                                pass

                        if verification_success:
                            break
                    except Exception as parent_err:
                        self.logger.debug(f"Error checking parent/siblings: {parent_err}")

        except Exception as e:
            self.logger.error(f"Error analyzing Cold Turkey window: {e}")

        return verification_success, row_text

class WindowsVerificationService(IVerificationService):
    """
    Windows implementation of the verification service.

    Uses win32gui, subprocess, and pywinauto to verify Cold Turkey Blocker
    configuration.
    """

    def __init__(self, logger: ILoggerService, config_repository: IConfigRepository,
                 thread_service: IBackgroundTaskService):
        """
        Initialize the verification service.

        Args:
            logger: Logger service for logging
            config_repository: Repository for configuration settings
            thread_service: Thread service for background tasks
        """
        self.logger = logger
        self.config_repository = config_repository
        self.thread_service = thread_service
        self.verification_task_id = "verify_block"

    def verify_block(self, platform: str, block_name: str, cancellable: bool = True) -> Result[bool]:
        """
        Verify that a Cold Turkey block exists and is properly configured.

        Args:
            platform: Platform name
            block_name: Cold Turkey block name
            cancellable: Whether the verification can be cancelled by the user

        Returns:
            Result indicating success or failure
        """
        if not self.is_blocker_path_configured():
            return Result.fail("Cold Turkey Blocker path not configured")

        if not block_name:
            return Result.fail("Block name is empty")

        try:
            blocker_path = self.config_repository.get_cold_turkey_path()

            if not blocker_path or not os.path.exists(blocker_path):
                return Result.fail("Cold Turkey Blocker executable not found")

            # Create a worker for verification
            worker = VerificationWorker(
                platform=platform,
                block_name=block_name,
                blocker_path=blocker_path,
                logger=self.logger
            )

            # Set up completion callback to capture the worker's result
            verification_result = None

            def on_verification_completed(result):
                nonlocal verification_result
                verification_result = result

            worker.set_on_completed(on_verification_completed)

            # Execute task with auto cleanup
            task_result = self.thread_service.execute_task(
                self.verification_task_id, worker
            )

            if task_result.is_failure:
                return task_result

            # Wait for the verification to complete or be cancelled
            wait_result = self.thread_service.wait_for_task_completion(
                self.verification_task_id,
                timeout_ms=30000
            )
            if wait_result.is_failure:
                return Result.fail(wait_result.error)

            # If verification completed successfully
            if verification_result is not None:
                return Result.ok(verification_result)
            else:
                return Result.fail("Verification failed or was cancelled")

        except Exception as e:
            self.logger.error(f"Unexpected error in verification: {e}")
            return Result.fail(f"Unexpected error: {e}")

    def cancel_verification(self) -> Result[bool]:
        """Cancel any running verification task."""
        if not self.thread_service.is_task_running(self.verification_task_id):
            return Result.ok(False)  # Nothing to cancel

        return self.thread_service.cancel_task(self.verification_task_id)

    def get_verified_blocks(self) -> Result[List[Dict[str, Any]]]:
        """
        Get list of verified platform blocks.
        """
        try:
            verified_blocks = self.config_repository.get_global_setting("verified_blocks", [])
            return Result.ok(verified_blocks)
        except Exception as e:
            self.logger.error(f"Error getting verified blocks: {e}")
            return Result.fail(f"Error getting verified blocks: {e}")

    def add_verified_block(self, platform: str, block_name: str) -> Result[bool]:
        """
        Add a verified platform block to the saved configuration.
        """
        try:
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

        except Exception as e:
            self.logger.error(f"Error adding verified block: {e}")
            return Result.fail(f"Error adding verified block: {e}")

    def remove_verified_block(self, platform: str) -> Result[bool]:
        """
        Remove a verified platform block from the saved configuration.
        """
        try:
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

        except Exception as e:
            self.logger.error(f"Error removing verified block: {e}")
            return Result.fail(f"Error removing verified block: {e}")

    def clear_verified_blocks(self) -> Result[bool]:
        """
        Clear all verified platform blocks.
        """
        try:
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

        except Exception as e:
            self.logger.error(f"Error clearing verified blocks: {e}")
            return Result.fail(f"Error clearing verified blocks: {e}")

    def is_blocker_path_configured(self) -> bool:
        """
        Check if Cold Turkey Blocker path is configured.
        """
        blocker_path = self.config_repository.get_cold_turkey_path()
        return bool(blocker_path and os.path.exists(blocker_path))

    def is_verification_complete(self) -> bool:
        """
        Check if at least one platform block has been verified.
        """
        verified_blocks = self.config_repository.get_global_setting("verified_blocks", [])
        return len(verified_blocks) > 0