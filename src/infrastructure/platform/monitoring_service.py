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

from src.domain.services.i_history_service import IHistoryService
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
                 session_id: str,  # <-- ADD
                 history_service: IHistoryService,  # <-- ADD
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
        self.session_id = session_id  # <-- STORE
        self._history_service = history_service  # <-- STORE (use _ prefix if preferred)
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
        self.report_started()  # <<< ADD THIS AT THE START
        self.logger.info(f"Starting monitoring for {self.platform} (Session ID: {self.session_id})") # Added session_id to log
        try:
            self.logger.critical("!!!! Worker execute: Main TRY block entered !!!!")

            platform_window_result = self.platform_detection_service.detect_platform_window(
                self.platform, timeout=10)
            self.logger.critical(f"!!!! Worker execute: detect_platform_window Result: {platform_window_result.is_success} !!!!")

            if platform_window_result.is_failure:
                error_msg = f"Failed to detect {self.platform} window: {platform_window_result.error}"
                self.logger.error(error_msg)
                self.report_error(error_msg) # report_error is a method of Worker
                return False

            self.platform_window_info = platform_window_result.value

            while not self.cancel_requested:
                try:
                    self.check_count += 1
                    self.report_progress(0, f"Performing check #{self.check_count}")

                    is_active_result = self.platform_detection_service.is_platform_window_active(
                        self.platform_window_info)

                    if is_active_result.is_failure:
                        # Log and report, but continue trying unless critical
                        self.logger.warning(f"Error checking platform activity: {is_active_result.error}")
                        if self.on_status_update: self.on_status_update(
                            f"Error checking platform activity: {is_active_result.error}", "WARNING")
                        time.sleep(self.interval_seconds)
                        continue

                    is_active = is_active_result.value
                    if is_active != self.last_active:
                        activity_state = "active" if is_active else "inactive"
                        if self.on_status_update: self.on_status_update(f"Platform window became {activity_state}",
                                                                        "INFO" if is_active else "WARNING")
                        self.last_active = is_active

                    if is_active:
                        check_result = self._process_check()
                        if check_result.is_success:
                            final_result = check_result.value
                            if self.on_check_complete:  # Call if provided
                                self.on_check_complete(final_result)

                            # --- Record P&L to History Service ---
                            if final_result.has_values:
                                try:
                                    self._history_service.record_pnl(
                                        session_id=self.session_id,
                                        timestamp=final_result.timestamp,
                                        pnl_value=final_result.minimum_value
                                    )
                                except Exception as e_hist:
                                    self.logger.error(
                                        f"HistoryService Error: Failed to record P&L for session {self.session_id}: {e_hist}",
                                        exc_info=True)
                            # --- End History Recording ---

                            if final_result.threshold_exceeded:
                                if self.on_status_update: self.on_status_update(
                                    f"ALERT: Threshold exceeded! Detected: ${final_result.minimum_value:.2f}, "
                                    f"Threshold: ${self.threshold:.2f}", "ERROR"
                                )
                                # The external on_threshold_exceeded callback (passed to MonitoringService)
                                # will be triggered because this worker returns True and the MonitoringService
                                # calls its stored on_threshold_exceeded_callback.
                                return True  # Indicate successful completion (threshold met)
                        else:
                            error_message = str(check_result.error)
                            self.logger.error(f"Failed to process monitoring check: {error_message}", exc_info=True)
                            if self.on_status_update: self.on_status_update(
                                f"Failed to process monitoring check: {error_message}", "ERROR")
                            time.sleep(2)  # Short delay before retrying
                            continue
                    else:
                        if self.on_status_update: self.on_status_update("Platform window is inactive, waiting...",
                                                                        "INFO")

                    # Wait for the next interval
                    wait_step = 0.5
                    num_steps = int(self.interval_seconds / wait_step)
                    for _ in range(num_steps):
                        if self.cancel_requested: break
                        time.sleep(wait_step)
                    if self.cancel_requested: break

                except Exception as cycle_err:
                    self.logger.error(f"Error in monitoring cycle: {cycle_err}", exc_info=True)
                    if self.on_status_update: self.on_status_update(f"Error in monitoring cycle: {cycle_err}", "ERROR")
                    time.sleep(2)  # Short delay before retrying next iteration

            if self.cancel_requested:
                if self.on_status_update: self.on_status_update("Monitoring cancelled by request", "INFO")
                self.logger.info("Monitoring worker execution cancelled by request.")
                # If not cancelled, and loop exited, it means threshold was exceeded (handled by return True above)
            return True  # Loop finished (either by threshold or cancellation)

        except Exception as outer_err:
            self.logger.error(f"Critical monitoring worker error: {outer_err}", exc_info=True)
            self.report_error(f"Critical monitoring error: {outer_err}")  # Use worker's error reporting
            return False
        finally:
            self.logger.debug(f"MonitoringWorker for session {self.session_id} execute method finished.")

    def _process_check(self) -> Result[MonitoringResult]:
        """
        Process a single monitoring check, including OCR and threshold comparison.
        Handles cases where no numeric values are extracted.
        """
        extracted_text = "" # Initialize for robust error reporting
        screenshot_path = "" # Initialize for robust error reporting
        profile = None # Initialize

        try:
            # --- 1. Setup Paths ---
            safe_region_name = re.sub(r'[^\w\-]+', '_', self.region_name)
            screenshot_filename = f"{self.platform}_{safe_region_name}_current.png"
            screenshot_path = os.path.join(self.monitoring_directory, screenshot_filename)

            self.report_status(f"Capturing screenshot to {screenshot_path} (check #{self.check_count})", "INFO")

            # --- 2. Capture Screenshot ---
            capture_result = self.screenshot_service.capture_and_save(self.region, screenshot_path)
            if capture_result.is_failure:
                self.report_status(f"Failed to capture screenshot: {capture_result.error}", "ERROR")
                # Return failure Result directly
                return capture_result

            # --- 3. Load Profile ---
            profile_result = self.profile_service.get_profile(self.platform)
            if profile_result.is_failure:
                self.report_status(f"Failed to get profile: {profile_result.error}", "ERROR")
                # Return failure Result directly
                return profile_result
            profile = profile_result.value

            # --- 4. Extract Text ---
            try:
                image = Image.open(screenshot_path)
            except Exception as img_err:
                self.report_status(f"Failed to open captured screenshot '{screenshot_path}': {img_err}", "ERROR")
                return Result.fail(
                    ResourceError(message=f"Failed to open image: {img_err}", details={"path": screenshot_path}))

            extract_result = self.ocr_service.extract_text_with_profile(image, profile.ocr_profile)
            if extract_result.is_failure:
                self.report_status(f"Failed to extract text: {extract_result.error}", "ERROR")
                # Return failure Result directly
                return extract_result
            extracted_text = extract_result.value # Store the extracted text

            # --- 5. Extract Numeric Values ---
            extract_values_result = self.ocr_service.extract_numeric_values_with_patterns(
                extracted_text, profile.numeric_patterns)

            if extract_values_result.is_failure:
                self.report_status(f"Failed to extract values: {extract_values_result.error}", "ERROR")
                # Return failure Result directly
                return extract_values_result
            values = extract_values_result.value

            # --- 6. Heuristic Check (Optional - Keep or Remove as desired) ---
            # This block tries to guess negative values if extraction failed initially
            if not values:
                # Check if it looks like a dollar value that might be missing a sign
                if '$' in extracted_text:
                    dollar_match = re.search(r'\$\s*([0-9,]+\.?[0-9]*)', extracted_text)
                    if dollar_match:
                        dollar_value = dollar_match.group(1)
                        self.logger.debug(f"Heuristic: Dollar value found without minus sign: ${dollar_value}")
                        try:
                            # Use the existing cleaner method (assuming _clean_and_convert_value exists on ocr_service)
                             # noinspection PyProtectedMember
                            cleaned_value = self.ocr_service._clean_and_convert_value(dollar_value, f"${dollar_value}") # type: ignore

                            if cleaned_value is not None and cleaned_value >= 0: # Check conversion succeeded and it's not already negative
                                self.report_status(
                                    f"Heuristic: OCR may have missed sign. Treating ${dollar_value} as negative.", "WARNING")
                                values = [-cleaned_value]  # Force to negative
                                self.logger.debug(f"Heuristic: Forced value to negative: {values}")
                        except Exception as ex:
                            self.logger.error(f"Heuristic: Error processing potential dollar value: {ex}")
                # Add other heuristics here if needed

            # --- 7. *** THE CRITICAL CHECK FOR EMPTY LIST *** ---
            if not values:
                # If values list is *still* empty after heuristics (or if heuristic wasn't applied)
                self.report_status(f"No numeric P&L values identified in text: '{extracted_text}'", "WARNING")

                # Create a MonitoringResult indicating no value was found
                no_value_result = MonitoringResult(
                    values=[],
                    minimum_value=0.0, # Placeholder
                    threshold=self.threshold,
                    threshold_exceeded=False, # Cannot exceed threshold
                    raw_text=extracted_text,
                    timestamp=time.time(),
                    region_name=self.region_name,
                    screenshot_path=screenshot_path
                )
                # Inform listeners about the check completion, even with no value
                self.on_check_complete(no_value_result)
                # Return success for this check, indicating no unexpected error occurred
                return Result.ok(no_value_result)
            # --- END CRITICAL CHECK ---

            # --- 8. Process Found Values (If 'values' was not empty) ---
            min_value = min(values) # Now safe to call min()
            threshold_exceeded = min_value < self.threshold
            result_screenshot_path = screenshot_path # Default path

            # --- 9. Handle Threshold Breach (Save history screenshot) ---
            if threshold_exceeded:
                timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
                timestamp_filename = f"{self.platform}_{safe_region_name}_{timestamp_str}_exceeded.png"
                timestamped_path = os.path.join(self.monitoring_directory, timestamp_filename)
                try:
                    import shutil
                    shutil.copy2(screenshot_path, timestamped_path)
                    self.report_status(f"Threshold exceeded! Saved history to {timestamped_path}", "WARNING")
                    result_screenshot_path = timestamped_path # Update path for result object
                except Exception as copy_err:
                    self.report_status(f"Failed to copy screenshot on threshold breach: {copy_err}", "ERROR")
                    self.logger.error(f"Failed to copy '{screenshot_path}' to '{timestamped_path}': {copy_err}", exc_info=True)
                    # Keep result_screenshot_path as the _current.png path

            # --- 10. Create Final Result Object ---
            final_result = MonitoringResult(
                values=values,
                minimum_value=min_value,
                threshold=self.threshold,
                threshold_exceeded=threshold_exceeded,
                raw_text=extracted_text,
                timestamp=time.time(),
                region_name=self.region_name,
                screenshot_path=result_screenshot_path
            )

            # --- 11. Report Status & Return Success ---
            self.report_status(f"Detected values in '{self.region_name}': {values}", "INFO")
            self.report_status(f"Current minimum value: ${min_value:.2f}", "INFO")
            # Send result back via callback BEFORE returning success
            self.on_check_complete(final_result)
            return Result.ok(final_result)

        except Exception as check_err:
             # --- 12. Catch-All Error Handling ---
             self.logger.error(f"Unexpected error during _process_check: {check_err}", exc_info=True)
             # Report the error via callback if possible
             self.report_error(f"Internal error during monitoring check: {check_err}")
             # Return a failure Result containing a domain error
             return Result.fail(PlatformError(message=f"Internal check error: {check_err}", inner_error=check_err))

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
                 region_service: IRegionService,
                 history_service: IHistoryService):
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
        self._history_service = history_service  # <-- STORE IT HERE
        # Internal state
        self.monitoring_active = False
        self.monitoring_task_id = "platform_monitoring"
        #self.monitoring_results = []
        self.latest_result = None
        self.platform = None
        self.threshold = None
        self.on_threshold_exceeded_callback = None

    def start_monitoring(self,
                         platform: str,
                         threshold: float,
                         session_id: str, # <<< CORRECT: Accepts session_id from caller
                         interval_seconds: float = 5.0,
                         on_status_update: Optional[Callable[[str, str], None]] = None,
                         on_threshold_exceeded: Optional[Callable[[MonitoringResult], None]] = None,
                         on_error: Optional[Callable[[str], None]] = None) -> Result[bool]:
        if self.monitoring_active:
            return Result.fail(ValidationError(message="Monitoring already active", details={"current_platform": self.platform}))

        try:
            self.logger.info(f"Attempting to start monitoring for {platform} (Session: {session_id})")
            if not platform: return Result.fail(ValidationError("Platform name cannot be empty"))
            if threshold > 0: threshold = -threshold

            region_result = self.region_service.get_monitor_region(platform)
            if region_result.is_failure or region_result.value is None:
                msg = f"P&L Monitoring region is not defined for platform '{platform}'."
                self.logger.error(msg)
                return Result.fail(ConfigurationError(msg))
            monitor_region = region_result.value
            coordinates = monitor_region.coordinates
            region_name = monitor_region.name

            self.logger.info(f"Starting monitoring for {platform}, region '{region_name}' at {coordinates}")

            self.platform = platform
            self.threshold = threshold
            self.on_threshold_exceeded_callback = on_threshold_exceeded # Store external callback

            platform_monitoring_path = self.path_service.get_platform_monitoring_path(platform)
            self.logger.info(f"Monitoring screenshots will be saved in: {platform_monitoring_path}")

            # Create worker, passing session_id and the stored self._history_service
            worker = MonitoringWorker(
                session_id=session_id,
                history_service=self._history_service, # <<< Pass the stored service
                platform=platform,
                region=coordinates,
                region_name=region_name,
                threshold=threshold,
                interval_seconds=interval_seconds,
                screenshot_service=self.screenshot_service,
                ocr_service=self.ocr_service,
                platform_detection_service=self.platform_detection_service,
                logger=self.logger,
                profile_service=self.profile_service,
                save_directory=platform_monitoring_path,
                on_check_complete=self._handle_worker_check_complete,
                on_status_update=on_status_update,
                on_error=on_error
            )

            # Create a lambda to handle the worker's completion (True if threshold, False if error/cancelled)
            # This is where the external on_threshold_exceeded or on_error callbacks passed to
            # start_monitoring are invoked based on the worker's outcome.
            def on_worker_task_completed(execute_result: bool):  # Result of worker.execute()
                self.monitoring_active = False  # Mark as inactive
                self.platform = None
                self.threshold = None

                if worker.cancel_requested:
                    self.logger.info(f"Monitoring task for session {session_id} was cancelled.")
                    # The caller (DashboardViewModel) will end the history session via its stop_monitoring
                    if on_status_update: on_status_update("Monitoring cancelled.", "INFO")
                    return

                if execute_result is True:  # Worker's execute returned True (threshold exceeded)
                    if self.latest_result and self.latest_result.threshold_exceeded:
                        if self.on_threshold_exceeded_callback:  # This is the one from DashboardViewModel
                            self.on_threshold_exceeded_callback(self.latest_result)
                    else:
                        # This case (execute_result is True but no threshold_exceeded) shouldn't happen
                        # if worker logic is correct.
                        self.logger.warning(
                            f"Worker for session {session_id} completed successfully but threshold not marked. Check logic.")
                        if on_status_update: on_status_update("Monitoring finished unexpectedly.", "WARNING")
                else:  # Worker's execute returned False (likely due to an internal error it reported)
                    # The 'on_error' callback passed to start_monitoring would have been triggered
                    # by the worker's self.report_error() via the BackgroundTaskService.
                    # So, no need to call on_error again here unless the task itself failed to wrap.
                    self.logger.error(
                        f"Monitoring worker for session {session_id} returned False (error or early exit).")
                    # The on_error callback (from DashboardVM) should handle history session ending.

            def on_worker_task_error(error_message_from_worker: str):
                self.monitoring_active = False  # Mark as inactive
                self.platform = None
                self.threshold = None
                self.logger.error(
                    f"Monitoring task for session {session_id} reported error directly: {error_message_from_worker}")
                if on_error:  # Call the external on_error (from DashboardViewModel)
                    on_error(error_message_from_worker)

                # Set these callbacks on the worker object that QtBackgroundTaskService will use

            worker.set_on_completed(on_worker_task_completed)  # For result of execute()
            worker.set_on_error(on_worker_task_error)  # For explicit report_error() calls

            task_submission_result = self.thread_service.execute_task(self.monitoring_task_id, worker)

            if task_submission_result.is_success:
                self.monitoring_active = True
                return Result.ok(True)
            else:
                self.logger.error(f"Failed to submit monitoring task to thread service: {task_submission_result.error}")
                # If task submission fails, the session started by DashboardVM is orphaned.
                # DashboardVM should handle this (already does).
                return task_submission_result
        except Exception as e:
            self.logger.error(f"Unexpected error in MonitoringService.start_monitoring: {e}", exc_info=True)
            return Result.fail(ConfigurationError(message=f"Error starting monitoring: {e}", inner_error=e))
    # Add internal handler for worker check complete
    def _handle_worker_check_complete(self, result: MonitoringResult):
        # Store latest result if needed by other parts of MonitoringService
        self.latest_result = result
        # NOTE: We are NOT calling the external on_threshold_exceeded here.
        # That is handled by the DashboardViewModel when the worker task finishes.
        # If DashboardViewModel needs live PNL updates, add a separate callback for that.
        # For now, this just updates the internal state.
        pass

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