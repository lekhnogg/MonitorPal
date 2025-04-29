# src/presentation/view_models/ocr_calibration_view_model.py

import os
import uuid # For unique task IDs
from typing import Optional, Dict, Any, List

# --- Qt Imports ---
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QPixmap

# --- Application Imports ---
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_profile_service import IProfileService
from src.domain.services.i_ocr_service import IOcrService
from src.domain.services.i_ocr_analysis_service import IOcrAnalysisService
from src.domain.services.i_region_service import IRegionService
from src.domain.services.i_platform_selection_service import IPlatformSelectionService
from src.domain.services.i_background_task_service import IBackgroundTaskService, Worker
from src.domain.services.i_screenshot_service import IScreenshotService
from src.domain.services.i_ui_service import IUIService
from src.domain.models.platform_profile import PlatformProfile, OcrProfile
from src.domain.models.region_model import Region
from src.domain.common.result import Result
from src.domain.common.errors import ConfigurationError, ResourceError

# --- CalibrationWorker Definition ---
# (Ensure this worker class definition is present, either here or imported correctly)
# Note: If CalibrationWorker is defined in another file, import it instead.
import re
import dataclasses
import PIL.Image
class CalibrationWorker(Worker[Dict[str, Any]]):
    """Worker that attempts to find OCR parameters that match an expected value."""
    def __init__(self,
                 image_path: str,
                 expected_value: str,
                 ocr_service: IOcrService,
                 ocr_analysis_service: IOcrAnalysisService,
                 logger: ILoggerService):
        super().__init__()
        self.image_path = image_path
        self.expected_value = expected_value
        self.ocr_service = ocr_service
        self.ocr_analysis_service = ocr_analysis_service
        self.logger = logger
        self.total_attempts = 0
        self.current_attempt = 0

    def execute(self) -> Optional[Dict[str, Any]]:
        """Try different OCR parameters and patterns until expected value is found."""
        self.report_started()
        self.report_progress(0, "Starting calibration...")

        expected_value_str = self.expected_value.strip()
        try:
            # Using protected member here - consider adding public helper to IOcrService if preferred
            # noinspection PyProtectedMember
            cleaned_value_float = self.ocr_service._clean_and_convert_value( # type: ignore
                value_str=expected_value_str,
                full_match=expected_value_str
            )
            if cleaned_value_float is None:
                 self.report_error(f"Invalid expected value entered: '{self.expected_value}' could not be cleaned.")
                 return None
            target_value = cleaned_value_float
            self.logger.info(f"Cleaned expected value: '{self.expected_value}' -> Target float: {target_value}")
        except Exception as e:
            self.report_error(f"Error processing expected value '{self.expected_value}': {e}")
            self.logger.error("Exception during expected value cleaning", exc_info=True)
            return None

        try:
            image = PIL.Image.open(self.image_path)
        except Exception as e:
            self.report_error(f"Failed to load image: {e}")
            return None

        self.report_progress(5, "Detecting baseline OCR parameters...")
        ocr_result = self.ocr_analysis_service.detect_optimal_ocr_parameters(self.image_path)
        if ocr_result.is_failure:
            self.report_error(f"Failed to detect baseline OCR parameters: {ocr_result.error}")
            return None
        base_profile = ocr_result.value
        self.logger.info(f"Baseline OCR profile detected: {base_profile}")

        profiles_to_try = self._generate_ocr_profile_variations(base_profile)
        self.logger.info(f"Generated {len(profiles_to_try)} OCR profile variations to test.")
        patterns_to_try = self._generate_pattern_variations()
        self.logger.info(f"Generated {len(patterns_to_try)} pattern set variations to test.")

        self.total_attempts = len(profiles_to_try) * len(patterns_to_try)
        if self.total_attempts == 0:
            self.report_error("No OCR profiles or pattern sets generated to test.")
            return None

        best_match_info = None
        min_difference = float('inf')
        self.current_attempt = 0

        for i, current_profile in enumerate(profiles_to_try):
            if self.cancel_requested: self.report_error("Calibration cancelled"); return None # Check early
            self.logger.debug(f"Testing OCR Profile {i+1}/{len(profiles_to_try)}: {current_profile}")
            image_copy = image.copy()
            extract_result = self.ocr_service.extract_text_with_profile(image_copy, current_profile)
            if extract_result.is_failure:
                self.logger.warning(f"OCR failed for profile {i+1}: {extract_result.error}")
                self.current_attempt += len(patterns_to_try); continue # Skip patterns if OCR fails
            extracted_text = extract_result.value
            self.logger.debug(f"  Profile {i+1} Extracted text: '{extracted_text}'")
            if not extracted_text or not extracted_text.strip():
                 self.logger.debug("  Skipping pattern matching for empty/whitespace text.")
                 self.current_attempt += len(patterns_to_try); continue # Skip patterns for empty text

            for j, pattern_set in enumerate(patterns_to_try):
                self.current_attempt += 1
                # Ensure division by zero doesn't happen if total_attempts is somehow 0 here
                progress_pct = int((self.current_attempt / self.total_attempts) * 90) + 5 if self.total_attempts > 0 else 5
                self.report_progress(progress_pct, f"Testing profile {i+1}, pattern set {j+1}...")
                if self.cancel_requested: self.report_error("Calibration cancelled"); return None

                numeric_result = self.ocr_service.extract_numeric_values_with_patterns(extracted_text, pattern_set)
                if numeric_result.is_success and numeric_result.value:
                    extracted_values = numeric_result.value
                    self.logger.debug(f"    Pattern set {j+1} extracted: {extracted_values}")
                    for value in extracted_values:
                        difference = abs(value - target_value)
                        # Use a small tolerance for floating point comparison
                        if difference < 0.001:
                            self.report_progress(100, f"Found exact match: {value}")
                            self.logger.info(f"Exact match found with profile {i+1}, patterns {j+1}")
                            return { "ocr_profile": current_profile, "patterns": pattern_set, "extracted_text": extracted_text, "matched_value": value }
                        if difference < min_difference:
                             min_difference = difference
                             best_match_info = { "ocr_profile": current_profile, "patterns": pattern_set, "extracted_text": extracted_text, "matched_value": value, "difference": difference }
                             self.logger.debug(f"  New best match: {value} (Diff: {difference:.4f})")
                elif numeric_result.is_failure:
                    # Log pattern extraction failure but continue trying other patterns/profiles
                    self.logger.debug(f"    Pattern set {j+1} extraction failed: {numeric_result.error}")
                else: # No values extracted by this pattern set
                    self.logger.debug(f"    Pattern set {j+1} extracted no values.")

        # After trying all combinations, check the best match found
        # Adjust tolerance as needed (e.g., < 0.1 or < 1.0 depending on expected precision)
        if best_match_info and min_difference < 1.0:
            self.report_progress(95, f"Found close match: {best_match_info['matched_value']} (diff: {min_difference:.2f})")
            self.logger.info(f"Close match found (Diff: {min_difference:.4f}): {best_match_info}")
            return best_match_info

        # If no satisfactory match found after all attempts
        self.report_error("Could not find matching OCR profile and pattern combination.")
        self.logger.warning("Calibration finished without finding a satisfactory match.")
        return None

    def _generate_pattern_variations(self) -> List[Dict[str, str]]:
        """Generates sets of regex patterns to try."""
        variations = []
        # Use the default patterns from OcrAnalysisService as the base
        base = self.ocr_analysis_service.get_default_patterns()

        # Individual patterns (useful if only one format is present)
        variations.append({"dollar": base.get("dollar", "")})
        variations.append({"negative": base.get("negative", "")})
        variations.append({"negative_dash": base.get("negative_dash", "")})
        variations.append({"regular": base.get("regular", "")})

        # Common combinations
        variations.append({k: v for k, v in base.items() if k in ["dollar", "negative", "negative_dash"]}) # Currency formats
        variations.append({k: v for k, v in base.items() if k in ["negative", "negative_dash", "regular"]}) # Non-currency signed numbers

        # All patterns (most common case)
        variations.append(base.copy())

        # Remove empty dictionaries if a base pattern was missing
        variations = [v for v in variations if v]
        return variations

    def _generate_ocr_profile_variations(self, base_profile: OcrProfile) -> List[OcrProfile]:
        """Generates variations of OCR parameters around a baseline."""
        # Define ranges or sets of values to try for each parameter
        # Use sets to automatically handle duplicates
        scale_factors = {base_profile.scale_factor, max(1.0, base_profile.scale_factor - 0.5), base_profile.scale_factor + 0.5, base_profile.scale_factor + 1.0, 2.0, 3.0}
        # Ensure reasonable bounds for denoising
        denoise_hs = {base_profile.denoise_h, max(1, base_profile.denoise_h - 5), base_profile.denoise_h + 5, 7, 10, 13}
        invert_options = {base_profile.invert_colors, not base_profile.invert_colors}
        # Try different block sizes and C values, ensuring block size is odd and >= 3
        threshold_sets = set()
        base_block, base_c = base_profile.threshold_block_size, base_profile.threshold_c
        for block_delta in [0, -4, 4, -2, 2]:
             for c_delta in [0, -2, 2, -1, 1]:
                  new_block = base_block + block_delta
                  new_c = base_c + c_delta
                  # Validate parameters
                  if new_block < 3: new_block = 3
                  if new_block % 2 == 0: new_block += 1
                  if new_c < 0: new_c = 0
                  threshold_sets.add((new_block, new_c))
        # Include some common defaults
        threshold_sets.add((11, 2)); threshold_sets.add((15, 3)); threshold_sets.add((9, 2))

        # Generate Tesseract config variations (PSM modes)
        psm_options = {base_profile.tesseract_config}
        base_psm_match = re.search(r'--psm\s+(\d+)', base_profile.tesseract_config)
        base_psm = int(base_psm_match.group(1)) if base_psm_match else 6
        # Common PSM modes for numbers/lines/blocks
        for psm_val in [6, 7, 8, 11, 13]:
             psm_options.add(f"--oem 3 --psm {psm_val}") # Always use OEM 3 (LSTM)

        # Use a set to store unique generated profiles
        generated_profiles = {base_profile}

        # Systematically create variations (avoid deep nesting for clarity)
        current_profiles = list(generated_profiles)
        for profile in current_profiles:
             for sf in scale_factors: generated_profiles.add(dataclasses.replace(profile, scale_factor=sf))
        current_profiles = list(generated_profiles)
        for profile in current_profiles:
             for dh in denoise_hs: generated_profiles.add(dataclasses.replace(profile, denoise_h=dh))
        current_profiles = list(generated_profiles)
        for profile in current_profiles:
             for inv in invert_options: generated_profiles.add(dataclasses.replace(profile, invert_colors=inv))
        current_profiles = list(generated_profiles)
        for profile in current_profiles:
             for block, c_val in threshold_sets: generated_profiles.add(dataclasses.replace(profile, threshold_block_size=block, threshold_c=c_val))
        current_profiles = list(generated_profiles)
        for profile in current_profiles:
             for psm_config in psm_options: generated_profiles.add(dataclasses.replace(profile, tesseract_config=psm_config))

        self.logger.info(f"Generated {len(generated_profiles)} unique OCR profile variations.")
        # Return as a list
        return list(generated_profiles)
# --- End Worker ---


class OcrCalibrationViewModel(QObject):
    """
    ViewModel for the OCR Calibration tab.

    Manages loading source image, running calibration, displaying results,
    and saving calibrated profiles.
    """

    # --- Signals for View updates ---
    calibration_source_preview_changed = Signal(QPixmap)
    calibration_source_status_text_changed = Signal(str)
    can_calibrate_changed = Signal(bool)
    expected_value_changed = Signal(str)
    calibration_in_progress_changed = Signal(bool)
    calibration_progress_changed = Signal(int, str)
    calibration_status_text_changed = Signal(str, str) # message, color

    detected_patterns_changed = Signal(dict)
    show_detected_patterns_changed = Signal(bool)

    scale_factor_changed = Signal(float)
    threshold_block_size_changed = Signal(int)
    threshold_c_changed = Signal(int)
    denoise_h_changed = Signal(int)
    tesseract_config_changed = Signal(str)
    invert_colors_changed = Signal(bool)

    can_save_calibrated_profile_changed = Signal(bool)
    can_save_manual_edits_changed = Signal(bool) # Enable state for manual save button

    status_message_changed = Signal(str, str) # For main window status bar


    def __init__(self,
                 logger: ILoggerService,
                 profile_service: IProfileService,
                 ocr_service: IOcrService,
                 ocr_analysis_service: IOcrAnalysisService,
                 region_service: IRegionService,
                 platform_selection_service: IPlatformSelectionService,
                 thread_service: IBackgroundTaskService,
                 screenshot_service: IScreenshotService,
                 ui_service: IUIService,
                 parent: Optional[QObject] = None):
        """Initialize the OcrCalibrationViewModel."""
        super().__init__(parent)
        # Store services
        self._logger = logger
        self._profile_service = profile_service
        self._ocr_service = ocr_service
        self._ocr_analysis_service = ocr_analysis_service
        self._region_service = region_service
        self._platform_selection_service = platform_selection_service
        self._thread_service = thread_service
        self._screenshot_service = screenshot_service
        self._ui_service = ui_service

        # --- Internal State (Removed _last_... variables) ---
        self._selected_platform: Optional[str] = None
        self._calibration_source_image_path: Optional[str] = None
        self._expected_value: str = ""
        self._is_calibrating: bool = False
        self._last_calibration_result: Optional[Dict[str, Any]] = None
        # Holds the currently loaded/edited/calibrated profile parameters
        self._current_ocr_profile: OcrProfile = OcrProfile()
        # Holds the state for the UI preview and its status
        self._source_preview_pixmap: QPixmap = QPixmap()
        self._source_status_text: str = "N/A"
        # Holds the state for the pattern checkboxes
        self._current_patterns_state: Dict[str, bool] = {}
        self._current_patterns_visible: bool = False
        # Holds the state for the main status label below the input
        self._current_calibration_status_text: str = "Ready."
        self._current_calibration_status_color: str = "gray" # Use 'gray' or 'info' state

        self._logger.debug("Initializing OcrCalibrationViewModel...")
        self._platform_selection_service.register_platform_change_listener(
            self._handle_platform_selection_change
        )
        initial_platform = self._platform_selection_service.get_current_platform()
        # Perform initial load, which updates internal state and emits signals
        self._update_for_platform(initial_platform)
        self._logger.debug("OcrCalibrationViewModel initialized.")

    # --- Public Method for Initial View Sync ---
    @Slot() # Make it a slot so QTimer can call it easily
    def refresh_ui_signals(self):
        """Re-emits all current state signals for initial View synchronization."""
        self._logger.debug("ViewModel received request to refresh UI signals.")
        # Emit signals based on current internal state held in attributes
        self.calibration_source_preview_changed.emit(self._source_preview_pixmap)
        self.calibration_source_status_text_changed.emit(self._source_status_text)
        self.can_calibrate_changed.emit(self._calibration_source_image_path is not None)
        self.expected_value_changed.emit(self._expected_value) # Emit initial empty value
        self.calibration_in_progress_changed.emit(self._is_calibrating) # Emit initial false state
        # Don't emit progress, it's transient
        self.calibration_status_text_changed.emit(self._current_calibration_status_text, self._current_calibration_status_color)
        self.detected_patterns_changed.emit(self._current_patterns_state)
        self.show_detected_patterns_changed.emit(self._current_patterns_visible)
        # Emit all OCR parameter signals
        self.scale_factor_changed.emit(self._current_ocr_profile.scale_factor)
        self.threshold_block_size_changed.emit(self._current_ocr_profile.threshold_block_size)
        self.threshold_c_changed.emit(self._current_ocr_profile.threshold_c)
        self.denoise_h_changed.emit(self._current_ocr_profile.denoise_h)
        self.tesseract_config_changed.emit(self._current_ocr_profile.tesseract_config)
        self.invert_colors_changed.emit(self._current_ocr_profile.invert_colors)
        # Emit button states
        self.can_save_calibrated_profile_changed.emit(self._last_calibration_result is not None and not self._is_calibrating)
        self.can_save_manual_edits_changed.emit(self._selected_platform is not None and not self._is_calibrating)


    # --- Command Slots (Called by the View) ---

    @Slot(str)
    def set_expected_value(self, value: str):
        """Stores the value entered by the user."""
        self._expected_value = value.strip()
        # Optional: emit expected_value_changed if View needs to react dynamically

    @Slot()
    def start_calibration(self):
        """Starts the background calibration process."""
        if self._is_calibrating: self._logger.warning("Calibration already in progress."); return
        if not self._calibration_source_image_path:
            self.status_message_changed.emit("Calibration source image not available.", "ERROR")
            self._ui_service.show_message("Error", "Monitor region screenshot is needed for calibration.", "error"); return
        if not self._expected_value:
            self.status_message_changed.emit("Please enter the expected P&L value shown in the image.", "ERROR")
            self._ui_service.show_message("Input Needed", "Enter the exact P&L value you see in the screenshot preview.", "warning"); return

        self._logger.info(f"Starting OCR calibration for image: {os.path.basename(self._calibration_source_image_path)}, expected value: '{self._expected_value}'")
        self._is_calibrating = True
        self._last_calibration_result = None
        self._current_calibration_status_text = f"Starting calibration for '{self._expected_value}'..."
        self._current_calibration_status_color = "black" # Or another neutral/busy color
        self._current_patterns_visible = False # Hide patterns during calibration

        # Emit signals to update UI for starting state
        self.calibration_in_progress_changed.emit(True)
        self.can_save_calibrated_profile_changed.emit(False)
        self.can_save_manual_edits_changed.emit(False)
        self.show_detected_patterns_changed.emit(self._current_patterns_visible)
        self.calibration_status_text_changed.emit(self._current_calibration_status_text, self._current_calibration_status_color)
        self.calibration_progress_changed.emit(0, "Starting...") # Reset progress

        # Create and start the worker
        worker = CalibrationWorker(
            image_path=self._calibration_source_image_path,
            expected_value=self._expected_value,
            ocr_service=self._ocr_service,
            ocr_analysis_service=self._ocr_analysis_service,
            logger=self._logger
        )
        worker.set_on_progress(self.calibration_progress_changed.emit) # Directly connect progress signal
        worker.set_on_completed(self._handle_calibration_completed)
        worker.set_on_error(self._handle_calibration_error)

        task_id = f"calibration_{uuid.uuid4()}"
        task_result = self._thread_service.execute_task_and_restore_result(task_id, worker)

        if task_result.is_failure:
            self._logger.error(f"Failed to start calibration task (ID: {task_id}): {task_result.error}")
            # Reset state via error handler if task failed to start
            self._handle_calibration_error(f"Failed to start task: {task_result.error}")

    @Slot()
    def save_calibrated_profile(self):
        """Saves the profile using the result of the last successful calibration."""
        if not self._selected_platform: self.status_message_changed.emit("No platform selected.", "ERROR"); return
        if self._is_calibrating: self.status_message_changed.emit("Cannot save while calibrating.", "WARNING"); return
        if not self._last_calibration_result or "patterns" not in self._last_calibration_result or "ocr_profile" not in self._last_calibration_result:
             self.status_message_changed.emit("No valid calibration result available to save.", "ERROR"); return

        self._logger.info(f"Saving calibrated profile for {self._selected_platform}...")
        self.status_message_changed.emit("Saving calibrated profile...", "INFO")
        try:
            calibrated_ocr_profile = self._last_calibration_result["ocr_profile"]
            detected_patterns = self._last_calibration_result["patterns"]
            if not isinstance(calibrated_ocr_profile, OcrProfile):
                 self._logger.error(f"Invalid OCR profile type: {type(calibrated_ocr_profile)}")
                 self.status_message_changed.emit("Internal error: Invalid result format.", "ERROR"); return

            profile_to_save = PlatformProfile(
                platform_name=self._selected_platform,
                ocr_profile=calibrated_ocr_profile,
                numeric_patterns=detected_patterns
            )
            result = self._profile_service.save_profile(profile_to_save)

            if result.is_success:
                self.status_message_changed.emit(f"Calibrated profile saved for {self._selected_platform}", "SUCCESS")
                self._logger.info(f"Calibrated profile saved successfully for {self._selected_platform}")
                # Update internal state to match saved profile
                self._current_ocr_profile = calibrated_ocr_profile # Update internal current profile
                self._current_patterns_state = {key: (key in detected_patterns) for key in ["dollar", "negative", "negative_dash", "regular"]}
                # Update UI state after successful save
                self.can_save_calibrated_profile_changed.emit(False) # Disable calibrated save until next run
                self.can_save_manual_edits_changed.emit(True) # Manual edits now reflect calibrated profile
            else:
                self.status_message_changed.emit(f"Failed to save profile: {result.error}", "ERROR")
        except Exception as e:
            self.status_message_changed.emit(f"Error saving profile: {str(e)}", "ERROR")
            self._logger.error(f"Error saving calibrated profile: {e}", exc_info=True)

    @Slot()
    def save_manual_ocr_edits(self):
        """Saves only the manually edited OCR parameters, preserving existing patterns."""
        if not self._selected_platform: self.status_message_changed.emit("No platform selected.", "ERROR"); return
        if self._is_calibrating: self.status_message_changed.emit("Cannot save while calibrating.", "WARNING"); return

        self._logger.info(f"Saving manual OCR parameter edits for {self._selected_platform}...")
        self.status_message_changed.emit("Saving OCR parameters...", "INFO")
        try:
            # Get currently saved patterns to preserve them
            current_profile_res = self._profile_service.get_profile(self._selected_platform)
            if current_profile_res.is_failure:
                 self.status_message_changed.emit(f"Failed to load current profile patterns: {current_profile_res.error}", "ERROR")
                 # Use default patterns as a fallback if loading fails
                 existing_patterns = self._profile_service._get_default_patterns_for_platform(self._selected_platform)
            else:
                 # Use loaded patterns, or an empty dict if none were saved
                 existing_patterns = current_profile_res.value.numeric_patterns or {}

            # Use the ViewModel's _current_ocr_profile which reflects UI edits
            edited_ocr_profile = self._current_ocr_profile
            profile_to_save = PlatformProfile(
                platform_name=self._selected_platform,
                ocr_profile=edited_ocr_profile,
                numeric_patterns=existing_patterns # Preserve existing patterns
            )
            save_result = self._profile_service.save_profile(profile_to_save)

            if save_result.is_success:
                self.status_message_changed.emit("Manual OCR parameter edits saved.", "SUCCESS")
                self._logger.info("Manual OCR edits saved successfully.")
            else:
                self.status_message_changed.emit(f"Failed to save OCR edits: {save_result.error}", "ERROR")
        except Exception as e:
            self.status_message_changed.emit(f"Error saving manual OCR edits: {str(e)}", "ERROR")
            self._logger.error(f"Error saving manual OCR edits: {e}", exc_info=True)

    @Slot()
    def reset_profile_to_default(self):
        """Resets the OCR profile parameters UI to the application defaults for the platform."""
        if not self._selected_platform: self.status_message_changed.emit("No platform selected.", "ERROR"); return

        self._logger.warning(f"Resetting OCR profile UI to defaults for {self._selected_platform}")
        self.status_message_changed.emit(f"Resetting parameters display for {self._selected_platform}...", "INFO")

        # Get default profile *object* but DON'T save it yet
        default_ocr = self._profile_service._get_platform_default_ocr_profile(self._selected_platform)
        default_patterns = self._profile_service._get_default_patterns_for_platform(self._selected_platform)

        # Update internal state AND UI to show defaults
        self._update_ocr_profile_state(default_ocr) # Emits signals for OCR params UI
        self._current_patterns_state = {key: (key in default_patterns) for key in ["dollar", "negative", "negative_dash", "regular"]}
        self._current_patterns_visible = True # Defaults should be visible
        self.detected_patterns_changed.emit(self._current_patterns_state)
        self.show_detected_patterns_changed.emit(self._current_patterns_visible)

        # Update status label
        self._current_calibration_status_text = "Parameters reset to default. Save edits to persist."
        self._current_calibration_status_color = "info"
        self.calibration_status_text_changed.emit(self._current_calibration_status_text, self._current_calibration_status_color)

        # Clear calibration results and update buttons
        self._last_calibration_result = None
        self.can_save_calibrated_profile_changed.emit(False)
        self.can_save_manual_edits_changed.emit(True) # Allow saving the defaults
        self.status_message_changed.emit("Parameters reset to defaults. Use 'Save Parameter Edits' to apply.", "INFO")


    # --- Internal Slots / Callbacks ---

    @Slot(str)
    def _handle_platform_selection_change(self, platform: str):
        """Reloads calibration source and profile when platform changes."""
        self._logger.debug(f"OcrCalibrationViewModel received platform change: {platform}")
        self._update_for_platform(platform)

    # _handle_calibration_progress is simple emission, no internal state change needed here
    @Slot(int, str)
    def _handle_calibration_progress(self, percent: int, message: str):
        """Updates progress signal."""
        self.calibration_progress_changed.emit(percent, message)

    @Slot(object)
    def _handle_calibration_completed(self, result_data: Optional[Dict[str, Any]]):
        """Handles the result from the CalibrationWorker, updates state and emits signals."""
        self._logger.info(f"Calibration completed. Result data received: {'Yes' if result_data else 'No'}")
        self._is_calibrating = False
        self._last_calibration_result = result_data # Store result

        if result_data:
            calibrated_ocr_profile = result_data.get("ocr_profile")
            detected_patterns = result_data.get("patterns", {})
            matched_value = result_data.get("matched_value", "N/A")
            difference = result_data.get("difference", 0)
            if not calibrated_ocr_profile or not isinstance(calibrated_ocr_profile, OcrProfile):
                self._logger.error(f"Invalid OCR profile data type: {type(calibrated_ocr_profile)}")
                self._handle_calibration_error("Internal Error: Invalid calibration result data.")
                return

            # Update internal state variables first
            self._current_ocr_profile = calibrated_ocr_profile
            self._current_patterns_state = {key: (key in detected_patterns) for key in ["dollar", "negative", "negative_dash", "regular"]}
            self._current_patterns_visible = True
            status_msg = f"Calibration successful! Detected value: {matched_value}"
            if difference > 0.001: status_msg += f" (Note: Matched within ${difference:.2f} tolerance)"
            self._current_calibration_status_text = status_msg
            self._current_calibration_status_color = "green"

            # Emit signals to update the UI based on the new state
            self._update_ocr_profile_state(self._current_ocr_profile) # Emits OCR param signals
            self.detected_patterns_changed.emit(self._current_patterns_state)
            self.show_detected_patterns_changed.emit(self._current_patterns_visible)
            self.calibration_status_text_changed.emit(self._current_calibration_status_text, self._current_calibration_status_color)
            self.status_message_changed.emit("Calibration successful. Review parameters and save.", "SUCCESS")
            self.can_save_calibrated_profile_changed.emit(True)
            self.can_save_manual_edits_changed.emit(True) # Can save manually after calibration too
            self.calibration_in_progress_changed.emit(False)

        else:
            # Handle calibration failure (worker returned None or error)
            # Check if error handler already ran; if not, call it.
            if self._is_calibrating: # Flag wasn't reset by error handler yet
                 self._handle_calibration_error("Calibration failed to find a suitable profile/pattern.")
            # Ensure buttons are in correct state after failure
            self.can_save_calibrated_profile_changed.emit(False)
            self.can_save_manual_edits_changed.emit(self._selected_platform is not None)

    @Slot(str)
    def _handle_calibration_error(self, error_msg: str):
        """Handles errors, updates state, and emits signals."""
        self._logger.error(f"Calibration Error: {error_msg}")
        # Update internal state first
        self._is_calibrating = False
        self._last_calibration_result = None
        self._current_calibration_status_text = f"Calibration Error: {error_msg}"
        self._current_calibration_status_color = "red"
        self._current_patterns_visible = False # Hide patterns on error
        self._current_patterns_state = {}
        # Emit signals to update UI
        self.calibration_in_progress_changed.emit(False)
        self.calibration_status_text_changed.emit(self._current_calibration_status_text, self._current_calibration_status_color)
        self.status_message_changed.emit(f"Calibration failed: {error_msg}", "ERROR")
        self.show_detected_patterns_changed.emit(self._current_patterns_visible)
        self.detected_patterns_changed.emit(self._current_patterns_state)
        self.can_save_calibrated_profile_changed.emit(False)
        self.can_save_manual_edits_changed.emit(self._selected_platform is not None)

    @Slot(str)
    def handle_monitor_region_saved(self, platform_name: str):
        """Slot triggered when the monitor region is saved elsewhere."""
        if self._selected_platform and platform_name == self._selected_platform:
             self._logger.debug(f"Monitor region saved, reloading calibration source.")
             self._load_calibration_source(self._selected_platform)
        else:
             self._logger.debug(f"Ignoring monitor_region_saved signal for {platform_name}.")

    # --- Slots to update internal _current_ocr_profile from UI edits ---
    # These update the internal _current_ocr_profile state based on user input
    # in the advanced settings section and enable the "Save Parameter Edits" button.
    @Slot(float)
    def set_scale_factor(self, value: float):
        if self._current_ocr_profile.scale_factor != value:
             self._current_ocr_profile.scale_factor = value
             self.can_save_manual_edits_changed.emit(True)
    @Slot(int)
    def set_block_size(self, value: int):
        adjusted_value = value + 1 if value % 2 == 0 else value
        adjusted_value = max(3, adjusted_value) # Ensure minimum of 3
        if self._current_ocr_profile.threshold_block_size != adjusted_value:
            self._current_ocr_profile.threshold_block_size = adjusted_value
            self.can_save_manual_edits_changed.emit(True)
            if adjusted_value != value: self.threshold_block_size_changed.emit(adjusted_value) # Update UI if adjusted
    @Slot(int)
    def set_c_value(self, value: int):
         value = max(0, value) # Ensure non-negative
         if self._current_ocr_profile.threshold_c != value:
              self._current_ocr_profile.threshold_c = value
              self.can_save_manual_edits_changed.emit(True)
    @Slot(int)
    def set_denoise_h(self, value: int):
         value = max(1, value) # Ensure positive
         if self._current_ocr_profile.denoise_h != value:
              self._current_ocr_profile.denoise_h = value
              self.can_save_manual_edits_changed.emit(True)
    @Slot(str)
    def set_tesseract_config(self, value: str):
         # Basic validation: ensure it contains --psm or --oem? Optional.
         value = value.strip()
         if self._current_ocr_profile.tesseract_config != value:
              self._current_ocr_profile.tesseract_config = value
              self.can_save_manual_edits_changed.emit(True)
    @Slot(bool)
    def set_invert_colors(self, value: bool):
         if self._current_ocr_profile.invert_colors != value:
              self._current_ocr_profile.invert_colors = value
              self.can_save_manual_edits_changed.emit(True)

    # --- Private Helper Methods ---

    def _update_for_platform(self, platform: str):
        """Loads calibration source and profile, updates internal state, emits signals."""
        self._selected_platform = platform
        self._logger.info(f"Updating calibration view for platform: {platform or 'None'}")
        # Reset state before loading new platform data
        self._expected_value = ""
        self.expected_value_changed.emit("")
        self._is_calibrating = False
        self.calibration_in_progress_changed.emit(False)
        self._last_calibration_result = None
        self.can_save_calibrated_profile_changed.emit(False)
        # --- Default values for local calculation ---
        loaded_patterns = {}
        status_message = "N/A"
        status_color = "gray"
        show_patterns = False
        allow_manual_save = False
        loaded_ocr_profile = OcrProfile() # Use default OcrProfile as base

        if not platform:
            self._clear_calibration_source() # This handles source UI and resets internal status vars
            loaded_ocr_profile = self._profile_service._get_platform_default_ocr_profile("")
            loaded_patterns = self._profile_service._get_default_patterns_for_platform(None)
            allow_manual_save = False
            # Status/patterns state already set by _clear_calibration_source
            status_message = self._current_calibration_status_text
            status_color = self._current_calibration_status_color
            show_patterns = self._current_patterns_visible
        else:
            # Load profile for the selected platform
            profile_res = self._profile_service.get_profile(platform)
            if profile_res.is_success:
                loaded_platform_profile = profile_res.value
                loaded_ocr_profile = loaded_platform_profile.ocr_profile # Get the loaded OCR profile
                loaded_patterns = loaded_platform_profile.numeric_patterns or {}
                allow_manual_save = True
                status_message = f"Loaded saved profile for {platform}."
                status_color = "gray"
                show_patterns = True
            else: # Error loading profile
                self._logger.error(f"Failed to load profile for {platform}: {profile_res.error}")
                # Use default profile if load fails
                loaded_ocr_profile = self._profile_service._get_platform_default_ocr_profile(platform)
                loaded_patterns = self._profile_service._get_default_patterns_for_platform(platform)
                allow_manual_save = True # Still allow saving defaults
                status_message = f"Error loading profile. Using defaults."
                status_color = "orange"
                show_patterns = True # Show patterns even if default

        # Update internal OCR profile state and emit signals for advanced params UI
        self._update_ocr_profile_state(loaded_ocr_profile)

        # Calculate pattern state based on loaded patterns
        pattern_display_state = {key: (key in loaded_patterns) for key in ["dollar", "negative", "negative_dash", "regular"]}

        # Update manual save button state
        self.can_save_manual_edits_changed.emit(allow_manual_save)

        # Load preview (this updates internal _source_status_text)
        self._load_calibration_source(platform)

        # Determine final status message/color for the main calibration status label
        final_status_msg = status_message
        final_status_color = status_color
        if not self._calibration_source_image_path and platform:
             final_status_msg = self._source_status_text # Use source status if image missing
             final_status_color = "orange"

        # --- Update Internal State Variables ---
        # Store the final calculated state for status and patterns
        self._current_calibration_status_text = final_status_msg
        self._current_calibration_status_color = final_status_color
        self._current_patterns_state = pattern_display_state
        self._current_patterns_visible = show_patterns
        # --- END Update ---

        # --- EMIT SIGNALS based on final calculated state ---
        # Emit signals needed for UI update that aren't handled by helpers
        self.detected_patterns_changed.emit(self._current_patterns_state)
        self.show_detected_patterns_changed.emit(self._current_patterns_visible)
        self.calibration_status_text_changed.emit(self._current_calibration_status_text, self._current_calibration_status_color)
        # Note: OCR param signals are emitted by _update_ocr_profile_state
        # Note: Source preview signals are emitted by _load_calibration_source

    def _clear_calibration_source(self):
        """Clears calibration source info, updates state, and emits signals."""
        # Update internal state
        self._calibration_source_image_path = None
        self._source_preview_pixmap = QPixmap()
        self._source_status_text = "Select platform and define Monitor Region."
        self._current_calibration_status_text = self._source_status_text # Reset main status
        self._current_calibration_status_color = "gray"
        self._current_patterns_visible = False # Hide patterns
        self._current_patterns_state = {}

        # Emit signals
        self.calibration_source_preview_changed.emit(self._source_preview_pixmap)
        self.calibration_source_status_text_changed.emit(self._source_status_text)
        self.can_calibrate_changed.emit(False)
        self.calibration_status_text_changed.emit(self._current_calibration_status_text, self._current_calibration_status_color)
        self.show_detected_patterns_changed.emit(self._current_patterns_visible)
        self.detected_patterns_changed.emit(self._current_patterns_state)

    def _load_calibration_source(self, platform: str):
        """Loads the monitor region screenshot, updates source state, emits source signals."""
        if not platform: self._clear_calibration_source(); return

        preview_pixmap = QPixmap()
        status_text = ""
        can_calibrate = False
        image_path = None

        region_result = self._region_service.get_monitor_region(platform)
        if region_result.is_success and region_result.value:
            monitor_region = region_result.value
            screenshot_path = monitor_region.screenshot_path
            if screenshot_path and os.path.exists(screenshot_path):
                load_res = self._region_service.load_region_screenshot(monitor_region)
                if load_res.is_success:
                    pixmap_res = self._screenshot_service.to_pyside_pixmap(load_res.value)
                    if pixmap_res.is_success:
                        preview_pixmap = pixmap_res.value
                        status_text = f"Source: {os.path.basename(screenshot_path)}"
                        can_calibrate = True
                        image_path = screenshot_path
                    else: status_text = "Error: Failed converting preview."
                else: status_text = f"Error: Failed loading '{os.path.basename(screenshot_path)}'" # Added quotes
            elif screenshot_path: status_text = f"Error: Screenshot file missing ('{os.path.basename(screenshot_path)}')." # Added quotes
            else: status_text = "Monitor Region defined, but no screenshot saved yet." # Clearer message
        elif region_result.is_failure: status_text = f"Error loading region data: {region_result.error}" # Show error
        else: status_text = "P&L Monitor Region not defined."

        # Update internal state variables for the source section
        self._calibration_source_image_path = image_path
        self._source_preview_pixmap = preview_pixmap
        self._source_status_text = status_text
        # Emit signals only for the source section
        self.calibration_source_preview_changed.emit(self._source_preview_pixmap)
        self.calibration_source_status_text_changed.emit(self._source_status_text)
        self.can_calibrate_changed.emit(can_calibrate)

    def _update_ocr_profile_state(self, ocr_profile: OcrProfile):
        """Updates internal state AND emits signals for OCR parameters UI."""
        if not isinstance(ocr_profile, OcrProfile):
             self._logger.error(f"Invalid OCR profile type: {type(ocr_profile)}. Using default.")
             ocr_profile = OcrProfile()

        # Ensure block size is valid before storing/emitting
        block_size = int(ocr_profile.threshold_block_size)
        if block_size < 3: block_size = 3
        if block_size % 2 == 0: block_size += 1
        # Create a potentially adjusted profile to compare/store
        new_profile = dataclasses.replace(ocr_profile, threshold_block_size=block_size)

        # Optimization: Only update and emit if the profile actually changed
        if self._current_ocr_profile == new_profile:
            # self._logger.debug("OCR profile state unchanged, skipping signal emissions.")
            return

        self._current_ocr_profile = new_profile # Update internal state
        self._logger.debug(f"Internal OCR profile state updated. Emitting OCR parameter signals...")

        # Emit signals for ALL OCR parameters based on the new state
        self.scale_factor_changed.emit(self._current_ocr_profile.scale_factor)
        self.threshold_block_size_changed.emit(self._current_ocr_profile.threshold_block_size)
        self.threshold_c_changed.emit(self._current_ocr_profile.threshold_c)
        self.denoise_h_changed.emit(self._current_ocr_profile.denoise_h)
        self.tesseract_config_changed.emit(self._current_ocr_profile.tesseract_config)
        self.invert_colors_changed.emit(self._current_ocr_profile.invert_colors)

        # Enable manual saving whenever profile state is updated (if a platform is selected)
        # This signal is emitted regardless of whether the profile changed,
        # because loading a new profile might enable the button.
        self.can_save_manual_edits_changed.emit(self._selected_platform is not None)