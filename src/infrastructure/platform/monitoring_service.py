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
            platform_window_result = self.platform_detection_service.detect_platform_window(
                self.platform, timeout=10)
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
        self.path_service = path_service
        self.logger = logger
        self.profile_service = profile_service
        self.region_service = region_service
        self._history_service = history_service

        self.monitoring_active = False
        self.monitoring_task_id = "platform_monitoring"
        self.latest_result: Optional[MonitoringResult] = None
        self.platform: Optional[str] = None
        self.threshold: Optional[float] = None
        self.on_threshold_exceeded_callback: Optional[Callable[[MonitoringResult], None]] = None
        self._on_individual_check_complete_callback: Optional[Callable[[MonitoringResult], None]] = None

    def start_monitoring(self,
                         platform: str,
                         threshold: float,
                         session_id: str,
                         interval_seconds: float = 5.0,
                         on_status_update: Optional[Callable[[str, str], None]] = None,
                         on_threshold_exceeded: Optional[Callable[[MonitoringResult], None]] = None,
                         on_error: Optional[Callable[[str], None]] = None,
                         on_individual_check_complete: Optional[Callable[[MonitoringResult], None]] = None) -> Result[bool]:
        """
        Starts the monitoring process for a given platform and threshold.
        This involves:
        1. Validating inputs and current state.
        2. Fetching necessary configuration (like monitor region coordinates).
        3. Storing session parameters and callbacks.
        4. Creating a MonitoringWorker instance.
        5. Defining callbacks for the worker's completion or errors.
        6. Submitting the worker to the background task service.
        """
        # The main try block should start here, encompassing all setup logic
        try: # <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< FIXED: ADDED TRY HERE

            # --- 1. PRE-FLIGHT CHECKS ---
            if self.monitoring_active:
                self.logger.warning(f"Start monitoring requested for {platform}, but monitoring is already active for {self.platform}.")
                return Result.fail(ValidationError(message="Monitoring already active", details={"current_platform": self.platform}))

            self.logger.info(f"Attempting to start monitoring for platform '{platform}' (Session ID: {session_id})")

            if not platform:
                self.logger.error("Start monitoring failed: Platform name cannot be empty.")
                return Result.fail(ValidationError("Platform name cannot be empty"))

            if threshold > 0:
                self.logger.debug(f"Positive threshold {threshold} provided, converting to {-threshold} for loss monitoring.")
                threshold = -threshold

            # --- 2. FETCH CONFIGURATION (Monitor Region) ---
            self.logger.debug(f"Fetching monitor region for platform '{platform}'.")
            region_result = self.region_service.get_monitor_region(platform)
            if region_result.is_failure or region_result.value is None:
                msg = f"P&L Monitoring region is not defined for platform '{platform}'. Cannot start monitoring."
                self.logger.error(msg)
                return Result.fail(ConfigurationError(msg))

            monitor_region = region_result.value
            coordinates = monitor_region.coordinates
            region_name = monitor_region.name

            self.logger.info(f"Successfully fetched monitor region '{region_name}' at {coordinates} for '{platform}'.")

            # --- 3. STORE SESSION PARAMETERS AND CALLBACKS ---
            self.platform = platform
            self.threshold = threshold
            self.on_threshold_exceeded_callback = on_threshold_exceeded
            self._on_individual_check_complete_callback = on_individual_check_complete

            try:
                platform_monitoring_path = self.path_service.get_platform_monitoring_path(platform)
                self.logger.info(f"Monitoring screenshots will be saved in: {platform_monitoring_path}")
            except Exception as e_path: # This specific try-except for path_service is fine
                self.logger.error(f"Failed to get monitoring path for {platform}: {e_path}", exc_info=True)
                return Result.fail(ConfigurationError(f"Failed to determine monitoring save path: {e_path}"))

            # --- 4. CREATE MONITORING WORKER ---
            self.logger.debug(f"Creating MonitoringWorker for session '{session_id}'.")
            try:
                worker = MonitoringWorker( # This specific try-except for worker init is fine
                    session_id=session_id,
                    history_service=self._history_service,
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
            except Exception as e_worker_init:
                self.logger.error(f"Failed to initialize MonitoringWorker: {e_worker_init}", exc_info=True)
                self._on_individual_check_complete_callback = None
                return Result.fail(PlatformError(f"Failed to create monitoring worker: {e_worker_init}"))

            # --- 5. DEFINE WORKER COMPLETION/ERROR HANDLERS ---
            def on_worker_task_completed(execute_result: bool):
                self.logger.info(f"MonitoringWorker task for session '{session_id}' completed. Result: {execute_result}.")
                self.monitoring_active = False
                self.platform = None
                self.threshold = None
                self._on_individual_check_complete_callback = None

                if worker.cancel_requested:
                    self.logger.info(f"Monitoring task for session {session_id} was cancelled by request.")
                    if on_status_update: on_status_update("Monitoring cancelled.", "INFO")
                    return

                if execute_result is True:
                    if self.latest_result and self.latest_result.threshold_exceeded:
                        self.logger.info(f"Threshold exceeded for session '{session_id}'. Notifying external listener.")
                        if self.on_threshold_exceeded_callback:
                            try:
                                self.on_threshold_exceeded_callback(self.latest_result)
                            except Exception as e_cb:
                                self.logger.error(f"Error in external on_threshold_exceeded_callback: {e_cb}", exc_info=True)
                    else:
                        self.logger.warning(
                            f"Worker for session {session_id} completed with 'True' but latest_result does not indicate threshold exceeded. Review logic.")
                        if on_status_update: on_status_update("Monitoring finished (unexpected state).", "WARNING")
                else:
                    self.logger.error(
                        f"Monitoring worker for session {session_id} returned 'False', indicating an error or abnormal early exit.")

            def on_worker_task_error(error_message_from_worker: str):
                self.logger.error(f"MonitoringWorker task for session '{session_id}' reported an error: {error_message_from_worker}")
                self.monitoring_active = False
                self.platform = None
                self.threshold = None
                self._on_individual_check_complete_callback = None

                if on_error:
                    try:
                        on_error(error_message_from_worker)
                    except Exception as e_cb:
                        self.logger.error(f"Error in external on_error_callback: {e_cb}", exc_info=True)

            worker.set_on_completed(on_worker_task_completed)
            worker.set_on_error(on_worker_task_error)

            # --- 6. SUBMIT WORKER TO BACKGROUND TASK SERVICE ---
            self.logger.info(f"Submitting MonitoringWorker for session '{session_id}' to background task service.")
            task_submission_result = self.thread_service.execute_task(self.monitoring_task_id, worker)

            if task_submission_result.is_success:
                self.monitoring_active = True
                self.logger.info(f"Monitoring task for session '{session_id}' submitted successfully.")
                return Result.ok(True)
            else:
                self.logger.error(f"Failed to submit monitoring task to thread service: {task_submission_result.error}")
                self._on_individual_check_complete_callback = None
                self.on_threshold_exceeded_callback = None
                return task_submission_result

        # --- EXCEPTION HANDLING for start_monitoring itself ---
        except Exception as e: # <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< THIS EXCEPT NOW CORRECTLY PAIRS WITH THE OUTER TRY
            self.logger.error(f"Unexpected critical error in MonitoringService.start_monitoring for platform '{platform}': {e}", exc_info=True)
            self._on_individual_check_complete_callback = None
            self.on_threshold_exceeded_callback = None
            return Result.fail(ConfigurationError(message=f"Unexpected error starting monitoring: {e}", inner_error=e))

    def _handle_worker_check_complete(self, result: MonitoringResult):
        self.latest_result = result
        self.logger.debug(f"Internal: _handle_worker_check_complete received result for session '{result.session_id if hasattr(result, 'session_id') else 'N/A'}'. P&L: {result.minimum_value if result.has_values else 'N/A'}.")

        if self._on_individual_check_complete_callback:
            try:
                self.logger.debug(f"Propagating MonitoringResult (P&L: {result.minimum_value if result.has_values else 'N/A'}) to external on_individual_check_complete callback.")
                self._on_individual_check_complete_callback(result)
            except Exception as e:
                self.logger.error(f"Error invoking external _on_individual_check_complete_callback: {e}", exc_info=True)
        else:
            self.logger.debug("No external on_individual_check_complete_callback registered to propagate result to.")

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


