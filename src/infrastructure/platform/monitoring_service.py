#src/infrastructure/platform/monitoring_service.py
"""
Implementation of the monitoring service.

This service coordinates screenshot capture, OCR, and detection of loss thresholds.
"""
import os
import re
import time
from typing import Tuple, Optional, List, Callable
from datetime import datetime
from PIL import Image

from src.domain.services.i_monitoring_service import IMonitoringService
from src.domain.services.i_path_service import IPathService
from src.domain.services.i_screenshot_service import IScreenshotService
from src.domain.services.i_ocr_service import IOcrService
from src.domain.services.i_background_task_service import IBackgroundTaskService, Worker
from src.domain.services.i_platform_detection_service import IPlatformDetectionService
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_config_repository_service import IConfigRepository
from src.domain.services.i_region_service import IRegionService
from src.domain.models.monitoring_result import MonitoringResult
from src.domain.common.result import Result
from src.domain.common.errors import ValidationError, ConfigurationError, ResourceError, PlatformError
from src.domain.services.i_profile_service import IProfileService

class MonitoringWorker(Worker[bool]):
    """
    Worker for monitoring trading platform P&L in a background thread.
    """

    def __init__(self,
                 platform: str,
                 region: Tuple[int, int, int, int],
                 region_name: str,  # Add region_name parameter
                 threshold: float,
                 interval_seconds: float,
                 screenshot_service: IScreenshotService,
                 ocr_service: IOcrService,
                 platform_detection_service: IPlatformDetectionService,
                 logger: ILoggerService,
                 profile_service: IProfileService,
                 save_directory: str,
                 on_check_complete: Callable[[MonitoringResult], None],
                 on_status_update: Optional[Callable[[str, str], None]] = None,
                 on_error: Optional[Callable[[str], None]] = None):
        """Initialize the monitoring worker."""
        super().__init__()
        self.platform = platform
        self.region = region
        self.region_name = region_name  # Store the region name
        self.threshold = threshold
        self.interval_seconds = interval_seconds
        self.screenshot_service = screenshot_service
        self.ocr_service = ocr_service
        self.platform_detection_service = platform_detection_service
        self.logger = logger
        self.profile_service = profile_service
        self.monitoring_directory = save_directory
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
            # =================== REMOVED os.makedirs LINE ===================
            # The directory (self.monitoring_directory) is ensured by PathService/MonitoringService
            # ================================================================

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
                        # Process this check (uses self.monitoring_directory internally)
                        check_result = self._process_check()
                        if check_result.is_success:
                            result = check_result.value
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
                            # Handle the error case
                            error_message = str(check_result.error)
                            self.report_status(
                                f"Failed to process monitoring check: {error_message}",
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
            self.report_error(f"Monitoring error: {str(e)}")
            return False

        except Exception as e:
            self.logger.error(f"Monitoring error: {str(e)}")
            self.report_error(f"Monitoring error: {str(e)}")
            return False

    def _process_check(self) -> Result[MonitoringResult]:
        """Process a single monitoring check."""
        try:
            # Sanitize the region name to make it safe for filenames
            safe_region_name = re.sub(r'[^\w\-]+', '_', self.region_name)

            # Construct the filename for the constantly overwritten screenshot
            screenshot_filename = f"{self.platform}_{safe_region_name}_current.png"

            # Construct the full path within the directory passed to the worker's __init__
            # self.monitoring_directory was set from the path provided by PathService
            screenshot_path = os.path.join(self.monitoring_directory, screenshot_filename)

            self.report_status(f"Capturing screenshot to {screenshot_path} (check #{self.check_count})", "INFO")

            # Capture screenshot - overwrites the existing file at screenshot_path
            capture_result = self.screenshot_service.capture_and_save(self.region, screenshot_path)
            if capture_result.is_failure:
                self.report_status(f"Failed to capture screenshot: {capture_result.error}", "ERROR")
                return Result.fail(capture_result.error)

            # --- (OCR logic remains the same as previous correction) ---
            # Get the profile with all patterns
            profile_result = self.profile_service.get_profile(self.platform)
            if profile_result.is_failure:
                self.report_status(f"Failed to get profile: {profile_result.error}", "ERROR")
                return Result.fail(profile_result.error)
            profile = profile_result.value

            # Extract text with OCR using profile
            try:
                image = Image.open(screenshot_path)
            except Exception as img_err:
                self.report_status(f"Failed to open captured screenshot '{screenshot_path}': {img_err}", "ERROR")
                return Result.fail(
                    ResourceError(message=f"Failed to open image: {img_err}", details={"path": screenshot_path}))

            extract_result = self.ocr_service.extract_text_with_profile(image, profile.ocr_profile)
            if extract_result.is_failure:
                self.report_status(f"Failed to extract text: {extract_result.error}", "ERROR")
                return Result.fail(extract_result.error)
            extracted_text = extract_result.value

            # Use ALL patterns from the profile instead of just 'negative_dash'
            extract_values_result = self.ocr_service.extract_numeric_values_with_patterns(
                extracted_text, profile.numeric_patterns)  # Use all patterns from profile

            if extract_values_result.is_failure:
                self.report_status(f"Failed to extract values: {extract_values_result.error}", "ERROR")
                return Result.fail(extract_values_result.error)
            values = extract_values_result.value

            if not values:
                # OCR failed to detect values - check if it might be a value with a minus sign
                if '$' in extracted_text:  # If it looks like a dollar value
                    # Try to extract the numeric part after the $ sign
                    dollar_match = re.search(r'\$\s*([0-9,]+\.?[0-9]*)', extracted_text)
                    if dollar_match:
                        dollar_value = dollar_match.group(1)
                        self.logger.debug(f"Dollar value found without minus sign: ${dollar_value}")

                        # Clean and convert the value
                        try:
                            # Use the existing cleaner method
                            cleaned_value = self.ocr_service._clean_and_convert_value(dollar_value, f"${dollar_value}")

                            # Add a warning about the missing sign
                            self.report_status(
                                f"OCR may have missed a minus sign. Treating as negative: ${dollar_value}", "WARNING")

                            # Force negative (this is a heuristic - only do this if you're monitoring losses)
                            if cleaned_value and cleaned_value > 0:
                                values = [-cleaned_value]  # Force to negative
                                self.logger.debug(f"Forced value to negative: {values}")
                        except Exception as ex:
                            self.logger.error(f"Error processing potential dollar value: {ex}")

            min_value = min(values)
            threshold_exceeded = min_value < self.threshold
            result_screenshot_path = screenshot_path # Default path

            if threshold_exceeded:
                timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
                timestamp_filename = f"{self.platform}_{safe_region_name}_{timestamp_str}_exceeded.png"
                # Save within the same monitoring directory (self.monitoring_directory)
                timestamped_path = os.path.join(self.monitoring_directory, timestamp_filename)

                try:
                    import shutil
                    shutil.copy2(screenshot_path, timestamped_path)
                    self.report_status(f"Threshold exceeded! Saved history to {timestamped_path}", "WARNING")
                    result_screenshot_path = timestamped_path # Update path for result
                except Exception as copy_err:
                    self.report_status(f"Failed to copy screenshot on threshold breach: {copy_err}", "ERROR")
                    self.logger.error(f"Failed to copy '{screenshot_path}' to '{timestamped_path}': {copy_err}", exc_info=True)
                    # result_screenshot_path remains the _current.png path

            # Create result object
            result = MonitoringResult(
                values=values,
                minimum_value=min_value,
                threshold=self.threshold,
                threshold_exceeded=threshold_exceeded,
                raw_text=extracted_text,
                timestamp=time.time(),
                region_name=self.region_name,
                screenshot_path=result_screenshot_path # Use the correct path
            )

            self.report_status(f"Detected values in '{self.region_name}': {values}", "INFO")
            self.report_status(f"Current minimum value: ${min_value:.2f}", "INFO")

            return Result.ok(result)

        except Exception as check_err:
             self.logger.error(f"Unexpected error during _process_check: {check_err}", exc_info=True)
             self.report_error(f"Internal error during monitoring check: {check_err}")
             return Result.fail(PlatformError(message=f"Internal check error: {check_err}"))

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
                 path_service: IPathService,
                 logger: ILoggerService,
                 profile_service: IProfileService,
                 region_service: IRegionService):
        """Initialize the monitoring service."""
        self.screenshot_service = screenshot_service
        self.ocr_service = ocr_service
        self.thread_service = thread_service
        self.platform_detection_service = platform_detection_service
        self.config_repository = config_repository
        self.path_service = path_service  # Store path_service
        self.logger = logger
        self.profile_service = profile_service
        self.region_service = region_service

        # Internal state
        self.monitoring_active = False
        self.monitoring_task_id = "platform_monitoring"
        self.monitoring_results = []
        self.latest_result = None
        self.platform = None
        self.threshold = None
        self.on_threshold_exceeded_callback = None

    def start_monitoring(self,
                         platform: str,
                         threshold: float,
                         interval_seconds: float = 5.0,
                         on_status_update: Optional[Callable[[str, str], None]] = None,
                         on_threshold_exceeded: Optional[Callable[[MonitoringResult], None]] = None,
                         on_error: Optional[Callable[[str], None]] = None) -> Result[bool]:
        """Start monitoring the specified region for P&L values."""
        # Don't start if already monitoring
        if self.monitoring_active:
            error = ValidationError(message="Monitoring already active", details={"current_platform": self.platform})
            return Result.fail(error)

        try:
            self.logger.info(f"Attempting to start monitoring for {platform}")

            # Validate inputs
            if not platform: return Result.fail(ValidationError("Platform name cannot be empty"))
            if threshold > 0: threshold = -threshold  # Ensure negative

            # --- START: Fetch the monitor region ---
            region_result = self.region_service.get_monitor_region(platform)
            if region_result.is_failure:
                self.logger.error(f"Failed to get monitor region for {platform}: {region_result.error}")
                return Result.fail(region_result.error)  # Propagate error

            monitor_region = region_result.value  # Region object or None
            if monitor_region is None:
                msg = f"P&L Monitoring region is not defined for platform '{platform}'."
                self.logger.error(msg)
                return Result.fail(ConfigurationError(msg))
            # --- END: Fetch the monitor region ---

            # Extract details needed for the worker
            coordinates = monitor_region.coordinates
            region_name = monitor_region.name  # Should be 'monitor' or standard name

            self.logger.info(f"Starting monitoring for {platform}, region '{region_name}' at {coordinates}")

            # Store key parameters (platform, threshold, callback)
            self.platform = platform
            # No need to store self.region anymore if worker gets coords directly
            self.threshold = threshold
            self.on_threshold_exceeded_callback = on_threshold_exceeded

            # Get the monitoring path
            platform_monitoring_path = self.path_service.get_platform_monitoring_path(platform)
            self.logger.info(f"Monitoring screenshots will be saved in: {platform_monitoring_path}")

            # Create worker, passing fetched coordinates and name
            worker = MonitoringWorker(
                platform=platform,
                region=coordinates,  # Pass coordinates
                region_name=region_name,  # Pass fetched name
                threshold=threshold,
                interval_seconds=interval_seconds,
                screenshot_service=self.screenshot_service,
                ocr_service=self.ocr_service,
                platform_detection_service=self.platform_detection_service,
                logger=self.logger,
                profile_service=self.profile_service,
                save_directory=platform_monitoring_path,
                on_check_complete=self._on_check_complete,
                on_status_update=on_status_update,
                on_error=on_error
            )

            # Execute in background thread
            result = self.thread_service.execute_task(self.monitoring_task_id, worker)
            if result.is_failure:
                self.logger.error(f"Failed to start monitoring task: {result.error}")
                return result

            self.monitoring_active = True
            return Result.ok(True)

        except Exception as e:
            error = ConfigurationError(message=f"Error starting monitoring: {e}",
                                       details={"platform": platform, "threshold": threshold}, inner_error=e)
            self.logger.error(str(error), exc_info=True)
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