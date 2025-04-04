# src/infrastructure/platform/monitoring_service.py
"""
Implementation of the monitoring service.

This service coordinates screenshot capture, OCR, and detection of loss thresholds.
"""
import os
import time
from typing import Tuple, Optional, List, Callable
from datetime import datetime

from PySide6.QtWidgets import QApplication

from src.domain.services.i_monitoring_service import IMonitoringService
from src.domain.services.i_screenshot_service import IScreenshotService
from src.domain.services.i_ocr_service import IOcrService
from src.domain.services.i_background_task_service import IBackgroundTaskService, Worker
from src.domain.services.i_platform_detection_service import IPlatformDetectionService
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_config_repository_service import IConfigRepository
from src.domain.models.monitoring_result import MonitoringResult
from src.domain.common.result import Result
from src.domain.common.errors import ValidationError, ConfigurationError, ResourceError

class MonitoringWorker(Worker[bool]):
    """
    Worker for monitoring trading platform P&L in a background thread.
    """

    def __init__(self,
                 platform: str,
                 region: Tuple[int, int, int, int],
                 threshold: float,
                 interval_seconds: float,
                 screenshot_service: IScreenshotService,
                 ocr_service: IOcrService,
                 platform_detection_service: IPlatformDetectionService,
                 logger: ILoggerService,
                 save_directory: str,
                 on_check_complete: Callable[[MonitoringResult], None],
                 on_status_update: Optional[Callable[[str, str], None]] = None,
                 on_error: Optional[Callable[[str], None]] = None):
        """Initialize the monitoring worker."""
        super().__init__()
        self.platform = platform
        self.region = region
        self.threshold = threshold
        self.interval_seconds = interval_seconds
        self.screenshot_service = screenshot_service
        self.ocr_service = ocr_service
        self.platform_detection_service = platform_detection_service
        self.logger = logger
        self.save_directory = save_directory
        self.on_check_complete = on_check_complete
        self.on_status_update = on_status_update
        self.on_error = on_error

        # Internal state
        self.check_count = 0
        self.platform_window_info = None
        self.last_active = None

        # Ensure threshold is negative (we're looking for losses)
        if self.threshold > 0:
            self.threshold = -self.threshold

    def execute(self) -> bool:
        """Execute the monitoring process."""
        self.logger.info(f"Starting monitoring for {self.platform}")
        self.report_status(f"Starting monitoring for {self.platform}", "INFO")

        try:
            # Make sure save directory exists
            os.makedirs(self.save_directory, exist_ok=True)

            # Get platform window information
            platform_window_result = self.platform_detection_service.detect_platform_window(
                self.platform, timeout=10)

            if platform_window_result.is_failure:
                self.report_error(f"Failed to detect {self.platform} window: {platform_window_result.error}")
                return False

            self.platform_window_info = platform_window_result.value

            # Main monitoring loop
            while not self.cancel_requested:
                try:
                    # Increment check count
                    self.check_count += 1
                    self.report_progress(
                        percent=0,  # Cannot estimate progress for indefinite monitoring
                        message=f"Performing check #{self.check_count}"
                    )

                    # Check if platform window is active
                    is_active_result = self.platform_detection_service.is_platform_window_active(
                        self.platform_window_info)

                    if is_active_result.is_failure:
                        self.report_status(f"Error checking platform activity: {is_active_result.error}", "WARNING")
                        time.sleep(self.interval_seconds)
                        continue

                    is_active = is_active_result.value

                    # Report platform activity changes
                    if is_active != self.last_active:
                        if is_active:
                            self.report_status(f"Platform window became active", "INFO")
                        else:
                            self.report_status(f"Platform window became inactive", "WARNING")
                        self.last_active = is_active

                    # Only check when platform is active
                    if is_active:
                        # Process this check
                        result = self._process_check()

                        # Handle the result
                        if result is not None:
                            # Call the completion callback
                            self.on_check_complete(result)

                            # If threshold was exceeded, exit the monitoring loop
                            if result.threshold_exceeded:
                                self.report_status(
                                    f"ALERT: Threshold exceeded! Detected: ${result.minimum_value:.2f}, "
                                    f"Threshold: ${self.threshold:.2f}",
                                    "ERROR"
                                )
                                break
                        else:
                            # Handle the error case (when _process_check returns None)
                            self.report_status(
                                "Failed to process monitoring check. See logs for details.",
                                "ERROR"
                            )
                            # Optional: Add a short delay before the next attempt
                            time.sleep(2)
                    else:
                        self.report_status("Platform window is inactive, waiting...", "INFO")

                    # Wait for the next interval, checking for cancellation
                    for _ in range(int(self.interval_seconds)):
                        if self.cancel_requested:
                            break
                        time.sleep(1)

                except Exception as e:
                    self.logger.error(f"Error in monitoring cycle: {str(e)}")
                    self.report_status(f"Error in monitoring cycle: {str(e)}", "ERROR")
                    time.sleep(2)  # Short delay before retrying

            # Check if we were cancelled or completed
            if self.cancel_requested:
                self.report_status("Monitoring cancelled", "INFO")
            else:
                self.report_status("Monitoring completed", "INFO")

            return True

        except Exception as e:
            self.logger.error(f"Monitoring error: {str(e)}")
            self.report_error(f"Monitoring error: {str(e)}")
            return False

    def _process_check(self) -> Optional[MonitoringResult]:
        """
        Process a single monitoring check.

        Returns:
            A MonitoringResult if successful, None otherwise
        """
        screenshot_path = os.path.join(
            self.save_directory,
            f"check_{self.check_count}_{int(time.time())}.png"
        )

        self.report_status(f"Capturing screenshot (check #{self.check_count})", "INFO")

        # Capture screenshot
        capture_result = self.screenshot_service.capture_and_save(self.region, screenshot_path)
        if capture_result.is_failure:
            self.report_status(f"Failed to capture screenshot: {capture_result.error}", "ERROR")
            return None

        # Extract text from screenshot
        self.report_status(f"Extracting text from screenshot", "INFO")
        extract_result = self.ocr_service.extract_text_from_file(screenshot_path)
        if extract_result.is_failure:
            self.report_status(f"Failed to extract text: {extract_result.error}", "ERROR")
            return None

        extracted_text = extract_result.value

        # Extract numeric values from text
        extract_values_result = self.ocr_service.extract_numeric_values(extracted_text)
        if extract_values_result.is_failure:
            self.report_status(f"Failed to extract numeric values: {extract_values_result.error}", "ERROR")
            return None

        values = extract_values_result.value

        if len(values) == 0:
            self.report_status("No numeric values detected in the OCR text", "WARNING")
            return None

        # Find the minimum value (most negative)
        min_value = min(values)

        # Check if the loss exceeds the threshold
        threshold_exceeded = min_value < self.threshold

        # Create result object
        result = MonitoringResult(
            values=values,
            minimum_value=min_value,
            threshold=self.threshold,
            threshold_exceeded=threshold_exceeded,
            raw_text=extracted_text,
            timestamp=time.time(),
            screenshot_path=screenshot_path
        )

        self.report_status(f"Detected values: {values}", "INFO")
        self.report_status(f"Current value: ${min_value:.2f}", "INFO")

        return result

    def report_status(self, message: str, level: str) -> None:
        """Report a status update."""
        if self.on_status_update:
            self.on_status_update(message, level)

    def report_error(self, message: str) -> None:
        """Report an error."""
        self.logger.error(message)
        if self.on_error:
            self.on_error(message)
        super().report_error(message)


class MonitoringService(IMonitoringService):
    """Implementation of the monitoring service."""

    def __init__(self,
                 screenshot_service: IScreenshotService,
                 ocr_service: IOcrService,
                 thread_service: IBackgroundTaskService,
                 platform_detection_service: IPlatformDetectionService,
                 config_repository: IConfigRepository,
                 logger: ILoggerService):
        """Initialize the monitoring service."""
        self.screenshot_service = screenshot_service
        self.ocr_service = ocr_service
        self.thread_service = thread_service
        self.platform_detection_service = platform_detection_service
        self.config_repository = config_repository
        self.logger = logger

        # Internal state
        self.monitoring_active = False
        self.monitoring_task_id = "platform_monitoring"
        self.save_directory = os.path.join(os.getcwd(), "monitoring_history")
        self.monitoring_results = []
        self.latest_result = None
        self.platform = None
        self.region = None
        self.threshold = None
        self.on_threshold_exceeded_callback = None

        # Ensure monitoring history directory exists
        os.makedirs(self.save_directory, exist_ok=True)

    def start_monitoring(self,
                         platform: str,
                         region: Tuple[int, int, int, int],
                         threshold: float,
                         interval_seconds: float = 5.0,
                         on_status_update: Optional[Callable[[str, str], None]] = None,
                         on_threshold_exceeded: Optional[Callable[[MonitoringResult], None]] = None,
                         on_error: Optional[Callable[[str], None]] = None) -> Result[bool]:
        """Start monitoring the specified region for P&L values."""
        # Don't start if already monitoring
        if self.monitoring_active:
            error = ValidationError(
                message="Monitoring already active - stop first",
                details={"current_platform": self.platform}
            )
            return Result.fail(error)

        try:
            self.logger.info(f"Starting monitoring for {platform}")

            # Validate inputs
            if not platform:
                error = ValidationError(
                    message="Platform name cannot be empty",
                    details={"platform": platform}
                )
                return Result.fail(error)

            if not region or len(region) != 4:
                error = ValidationError(
                    message="Invalid region format",
                    details={"region": region}
                )
                return Result.fail(error)

            if threshold > 0:
                # Ensure threshold is negative (we're looking for losses)
                threshold = -threshold

            # Store monitoring parameters
            self.platform = platform
            self.region = region
            self.threshold = threshold
            self.on_threshold_exceeded_callback = on_threshold_exceeded

            # Create per-session directory
            session_dir = os.path.join(
                self.save_directory,
                f"{platform}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            try:
                os.makedirs(session_dir, exist_ok=True)
            except Exception as e:
                error = ResourceError(
                    message=f"Failed to create monitoring directory: {session_dir}",
                    details={"directory": session_dir},
                    inner_error=e
                )
                self.logger.error(str(error))
                return Result.fail(error)

            # Create worker
            worker = MonitoringWorker(
                platform=platform,
                region=region,
                threshold=threshold,
                interval_seconds=interval_seconds,
                screenshot_service=self.screenshot_service,
                ocr_service=self.ocr_service,
                platform_detection_service=self.platform_detection_service,
                logger=self.logger,
                save_directory=session_dir,
                on_check_complete=self._on_check_complete,
                on_status_update=on_status_update,
                on_error=on_error
            )

            # Execute in background thread
            result = self.thread_service.execute_task(self.monitoring_task_id, worker)

            if result.is_failure:
                self.logger.error(f"Failed to start monitoring: {result.error}")
                return result

            # Mark as active
            self.monitoring_active = True

            return Result.ok(True)

        except Exception as e:
            error = ConfigurationError(
                message=f"Error starting monitoring: {e}",
                details={"platform": platform, "region": region, "threshold": threshold},
                inner_error=e
            )
            self.logger.error(str(error))
            return Result.fail(error)

    def stop_monitoring(self) -> Result[bool]:
        """Stop the current monitoring process."""
        if not self.monitoring_active:
            return Result.ok(False)  # Nothing to stop

        try:
            self.logger.info("Stopping monitoring")

            # Cancel the monitoring task
            result = self.thread_service.cancel_task(self.monitoring_task_id)

            # Mark as inactive even if cancellation failed
            self.monitoring_active = False

            return result

        except Exception as e:
            self.logger.error(f"Error stopping monitoring: {e}")
            self.monitoring_active = False  # Ensure we reset the flag
            return Result.fail(f"Error stopping monitoring: {e}")

    def is_monitoring(self) -> bool:
        """Check if monitoring is currently active."""
        # Also check thread service to ensure task is still running
        if self.monitoring_active and not self.thread_service.is_task_running(self.monitoring_task_id):
            self.monitoring_active = False

        return self.monitoring_active

    def get_latest_result(self) -> Optional[MonitoringResult]:
        """Get the latest monitoring result."""
        return self.latest_result

    def select_monitoring_region(self) -> Result[Tuple[int, int, int, int]]:
        """Open a UI for the user to select a monitoring region."""
        try:
            # Create a worker for region selection
            from src.presentation.components.qt_region_selector import QtRegionSelectorWorker
            worker = QtRegionSelectorWorker(
                message="Please select the region containing P&L values to monitor.\nClick and drag to select an area.",
                logger=self.logger
            )

            # Use a different task ID to avoid conflicting with monitoring
            result = self.thread_service.execute_task("region_selection", worker)

            if result.is_failure:
                return result

            # Get the selected region synchronously
            from src.presentation.components.qt_region_selector import select_region_qt
            region = select_region_qt(
                "Please select the region containing P&L values to monitor.\nClick and drag to select an area."
            )

            if region is None:
                self.logger.info("Region selection cancelled")
                return Result.fail("Region selection cancelled")

            self.logger.info(f"Region selected: {region}")
            return Result.ok(region)

        except Exception as e:
            self.logger.error(f"Error in region selection: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return Result.fail(f"Error in region selection: {e}")

    def get_monitoring_history(self) -> Result[List[MonitoringResult]]:
        """Get the history of monitoring results."""
        return Result.ok(self.monitoring_results.copy())

    def _on_check_complete(self, result: MonitoringResult) -> None:
        """Handle a completed monitoring check."""
        # Store result
        self.latest_result = result
        self.monitoring_results.append(result)

        # Cap history length to avoid memory issues
        if len(self.monitoring_results) > 100:
            self.monitoring_results = self.monitoring_results[-100:]

        # Check for threshold exceeded
        if result.threshold_exceeded and self.on_threshold_exceeded_callback:
            self.on_threshold_exceeded_callback(result)

            # Monitoring will stop automatically when threshold is exceeded,
            # so update our active flag
            self.monitoring_active = False

    def check_values(self, platform: str, region: tuple, threshold: float) -> Result[MonitoringResult]:
        """
        Check a screen region for financial values and compare against the threshold.

        This synchronous function should only be used for immediate checking,
        not for continuous monitoring.
        """
        try:
            self.logger.info(f"Checking {platform} region {region} with threshold {threshold}")

            # Capture screenshot of the region
            screenshot_result = self.screenshot_service.capture_region(region)

            if screenshot_result.is_failure:
                return Result.fail(screenshot_result.error)

            screenshot = screenshot_result.value

            # Extract text with OCR
            ocr_result = self.ocr_service.extract_text(screenshot)

            if ocr_result.is_failure:
                return Result.fail(ocr_result.error)

            text = ocr_result.value

            # Extract numeric values from the text
            numeric_result = self.ocr_service.extract_numeric_values(text)

            if numeric_result.is_failure:
                return Result.fail(numeric_result.error)

            values = numeric_result.value

            # Check if any values were found
            if not values:
                return Result.fail("No numeric values detected in the specified region")

            # Find the minimum value (typically the P&L)
            min_value = min(values)

            # Check if the threshold is exceeded
            threshold_exceeded = min_value < threshold

            # Create monitoring result
            import time
            result = MonitoringResult(
                values=values,
                minimum_value=min_value,
                threshold=threshold,
                threshold_exceeded=threshold_exceeded,
                raw_text=text,
                timestamp=time.time()
            )

            self.logger.info(f"Check complete: values={values}, min={min_value}, exceeded={threshold_exceeded}")
            return Result.ok(result)

        except Exception as e:
            self.logger.error(f"Error checking values: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())
            return Result.fail(f"Error checking values: {e}")