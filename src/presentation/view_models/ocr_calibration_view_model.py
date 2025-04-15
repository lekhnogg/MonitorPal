# src/presentation/view_models/ocr_calibration_view_model.py

import os
import uuid # For unique task IDs
from typing import Optional, Dict, Any, List # Added List

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
from src.domain.common.errors import ConfigurationError, ResourceError # Import errors used

# --- CalibrationWorker Definition (Copied from previous step) ---
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
                self.current_attempt += len(patterns_to_try); continue
            extracted_text = extract_result.value
            self.logger.debug(f"  Profile {i+1} Extracted text: '{extracted_text}'")
            if not extracted_text or not extracted_text.strip():
                 self.logger.debug("  Skipping pattern matching for empty/whitespace text.")
                 self.current_attempt += len(patterns_to_try); continue

            for j, pattern_set in enumerate(patterns_to_try):
                self.current_attempt += 1
                progress_pct = int((self.current_attempt / self.total_attempts) * 90) + 5 if self.total_attempts > 0 else 5
                self.report_progress(progress_pct, f"Testing profile {i+1}, pattern set {j+1}...")
                if self.cancel_requested: self.report_error("Calibration cancelled"); return None

                numeric_result = self.ocr_service.extract_numeric_values_with_patterns(extracted_text, pattern_set)
                if numeric_result.is_success and numeric_result.value:
                    extracted_values = numeric_result.value
                    self.logger.debug(f"    Pattern set {j+1} extracted: {extracted_values}")
                    for value in extracted_values:
                        difference = abs(value - target_value)
                        if difference < 0.001:
                            self.report_progress(100, f"Found exact match: {value}")
                            return { "ocr_profile": current_profile, "patterns": pattern_set, "extracted_text": extracted_text, "matched_value": value }
                        if difference < min_difference:
                             min_difference = difference
                             best_match_info = { "ocr_profile": current_profile, "patterns": pattern_set, "extracted_text": extracted_text, "matched_value": value, "difference": difference }
                elif numeric_result.is_failure: self.logger.debug(f"    Pattern set {j+1} extraction failed: {numeric_result.error}")
                else: self.logger.debug(f"    Pattern set {j+1} extracted no values.")

        if best_match_info and min_difference < 1.0:
            self.report_progress(95, f"Found close match: {best_match_info['matched_value']} (diff: {min_difference:.2f})")
            return best_match_info

        self.report_error("Could not find matching OCR profile and pattern combination.")
        return None

    def _generate_pattern_variations(self) -> List[Dict[str, str]]:
        variations = []
        base = {
            "dollar": r'[$§]?([\d,]+(?:[.,]\d+)?)',
            "negative": r'\((?:[$§]?)([\d,]+(?:[.,]\d+)?)\)',
            "negative_dash": r'[-~–—]\s*[$§]?([\d,]+(?:[.,]\d+)?)',
            "regular": r'(?<![$§])([-~–—]?[\d,]+(?:[.,]\d+)?)'
        }
        variations.append({"dollar": base["dollar"]})
        variations.append({"negative": base["negative"]})
        variations.append({"negative_dash": base["negative_dash"]})
        variations.append({"regular": base["regular"]})
        variations.append(base.copy())
        return variations

    def _generate_ocr_profile_variations(self, base_profile: OcrProfile) -> List[OcrProfile]:
        variations = [base_profile]
        scale_factors = {base_profile.scale_factor, max(1.0, base_profile.scale_factor - 0.5), base_profile.scale_factor + 0.5, base_profile.scale_factor + 1.0}
        denoise_hs = {base_profile.denoise_h, max(1, base_profile.denoise_h - 5), base_profile.denoise_h + 5}
        invert_options = {base_profile.invert_colors, not base_profile.invert_colors}
        threshold_sets = {(base_profile.threshold_block_size, base_profile.threshold_c)}
        alt_block1 = base_profile.threshold_block_size + 4; alt_block2 = base_profile.threshold_block_size - 4
        alt_c1 = base_profile.threshold_c + 2; alt_c2 = base_profile.threshold_c - 2
        if alt_block1 % 2 != 0 and alt_block1 > 1: threshold_sets.add((alt_block1, base_profile.threshold_c))
        if alt_block2 % 2 != 0 and alt_block2 > 1: threshold_sets.add((alt_block2, base_profile.threshold_c))
        if alt_c1 >= 0: threshold_sets.add((base_profile.threshold_block_size, alt_c1))
        if alt_c2 >= 0: threshold_sets.add((base_profile.threshold_block_size, alt_c2))
        psm_options = {base_profile.tesseract_config}
        base_psm_match = re.search(r'--psm\s+(\d+)', base_profile.tesseract_config)
        base_psm = int(base_psm_match.group(1)) if base_psm_match else 6
        for psm_val in [6, 7, 11, 13]:
            if psm_val != base_psm: psm_options.add(f"--oem 3 --psm {psm_val}")
        generated_profiles = {base_profile}
        for sf in scale_factors:
            if sf != base_profile.scale_factor: generated_profiles.add(dataclasses.replace(base_profile, scale_factor=sf))
        for dh in denoise_hs:
             if dh != base_profile.denoise_h: generated_profiles.add(dataclasses.replace(base_profile, denoise_h=dh))
        for inv in invert_options:
             if inv != base_profile.invert_colors: generated_profiles.add(dataclasses.replace(base_profile, invert_colors=inv))
        for block, c_val in threshold_sets:
             if block != base_profile.threshold_block_size or c_val != base_profile.threshold_c: generated_profiles.add(dataclasses.replace(base_profile, threshold_block_size=block, threshold_c=c_val))
        for psm_config in psm_options:
             if psm_config != base_profile.tesseract_config: generated_profiles.add(dataclasses.replace(base_profile, tesseract_config=psm_config))
        self.logger.info(f"Generated {len(generated_profiles)} unique OCR profile variations.")
        return list(generated_profiles)
# --- End of CalibrationWorker Definition ---


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

    status_message_changed = Signal(str, str)


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
        self._logger = logger
        self._profile_service = profile_service
        self._ocr_service = ocr_service
        self._ocr_analysis_service = ocr_analysis_service
        self._region_service = region_service
        self._platform_selection_service = platform_selection_service
        self._thread_service = thread_service
        self._screenshot_service = screenshot_service
        self._ui_service = ui_service

        # --- Internal State ---
        self._selected_platform: Optional[str] = None
        self._calibration_source_image_path: Optional[str] = None
        self._expected_value: str = ""
        self._is_calibrating: bool = False
        self._last_calibration_result: Optional[Dict[str, Any]] = None
        # State for OCR parameters reflecting UI/loaded/calibrated state
        self._current_ocr_profile: OcrProfile = OcrProfile() # Start with default
        self._source_preview_pixmap: QPixmap = QPixmap()
        self._source_status_text: str = "N/A"
        self._logger.debug("Initializing OcrCalibrationViewModel...")
        self._platform_selection_service.register_platform_change_listener(
            self._handle_platform_selection_change
        )
        initial_platform = self._platform_selection_service.get_current_platform()
        self._update_for_platform(initial_platform)
        self._logger.debug("OcrCalibrationViewModel initialized.")


    # --- Command Slots (Called by the View) ---

    @Slot(str)
    def set_expected_value(self, value: str):
        """Stores the value entered by the user."""
        self._expected_value = value.strip()


    @Slot()
    def start_calibration(self):
        """Starts the background calibration process."""
        if self._is_calibrating:
            self._logger.warning("Calibration already in progress.")
            return
        if not self._calibration_source_image_path:
            self.status_message_changed.emit("Calibration source image not available.", "ERROR")
            self._ui_service.show_message("Error", "Monitor region screenshot is needed for calibration.", "error")
            return
        if not self._expected_value:
            self.status_message_changed.emit("Please enter the expected P&L value shown in the image.", "ERROR")
            self._ui_service.show_message("Input Needed", "Enter the exact P&L value you see in the screenshot preview.", "warning")
            return

        self._logger.info(f"Starting OCR calibration for image: {os.path.basename(self._calibration_source_image_path)}, expected value: '{self._expected_value}'")
        self._is_calibrating = True
        self._last_calibration_result = None
        self.calibration_in_progress_changed.emit(True)
        self.can_save_calibrated_profile_changed.emit(False)
        self.can_save_manual_edits_changed.emit(False) # Also disable manual save
        self.show_detected_patterns_changed.emit(False)
        self.calibration_status_text_changed.emit(f"Starting calibration for '{self._expected_value}'...", "black")
        self.calibration_progress_changed.emit(0, "Starting...")

        worker = CalibrationWorker(
            image_path=self._calibration_source_image_path,
            expected_value=self._expected_value,
            ocr_service=self._ocr_service,
            ocr_analysis_service=self._ocr_analysis_service,
            logger=self._logger
        )

        worker.set_on_progress(self._handle_calibration_progress)
        worker.set_on_completed(self._handle_calibration_completed)
        worker.set_on_error(self._handle_calibration_error)

        task_id = f"calibration_{uuid.uuid4()}"
        task_result = self._thread_service.execute_task_and_restore_result(task_id, worker)

        if task_result.is_failure:
            self._logger.error(f"Failed to start calibration task (ID: {task_id}): {task_result.error}")
            self._handle_calibration_error(f"Failed to start task: {task_result.error}")


    @Slot()
    def save_calibrated_profile(self):
        """Saves the profile using the result of the last successful calibration."""
        if not self._selected_platform:
             self.status_message_changed.emit("No platform selected to save profile for.", "ERROR")
             return
        if self._is_calibrating:
             self.status_message_changed.emit("Cannot save while calibration is in progress.", "WARNING")
             return
        if not self._last_calibration_result or "patterns" not in self._last_calibration_result or "ocr_profile" not in self._last_calibration_result:
             self.status_message_changed.emit("No valid calibration result available to save.", "ERROR")
             self._logger.error("Save calibrated profile called but _last_calibration_result incomplete.")
             return

        self._logger.info(f"Saving calibrated profile for {self._selected_platform}...")
        self.status_message_changed.emit("Saving calibrated profile...", "INFO")

        try:
            # Use the profile and patterns directly from the stored result
            calibrated_ocr_profile = self._last_calibration_result["ocr_profile"]
            detected_patterns = self._last_calibration_result["patterns"]

            # Ensure the profile object is the correct type
            if not isinstance(calibrated_ocr_profile, OcrProfile):
                 self._logger.error(f"Invalid OCR profile type in calibration result: {type(calibrated_ocr_profile)}")
                 self.status_message_changed.emit("Internal error: Invalid calibration result format.", "ERROR")
                 return

            profile_to_save = PlatformProfile(
                platform_name=self._selected_platform,
                ocr_profile=calibrated_ocr_profile,
                numeric_patterns=detected_patterns
            )

            result = self._profile_service.save_profile(profile_to_save)

            if result.is_success:
                self.status_message_changed.emit(f"Calibrated profile saved for {self._selected_platform}", "SUCCESS")
                self._logger.info(f"Calibrated profile saved successfully for {self._selected_platform}")
                # Disable save button after successful save, require new calibration
                self.can_save_calibrated_profile_changed.emit(False)
            else:
                self.status_message_changed.emit(f"Failed to save profile: {result.error}", "ERROR")
                self._logger.error(f"Failed to save calibrated profile: {result.error}")

        except Exception as e:
            self.status_message_changed.emit(f"Error saving profile: {str(e)}", "ERROR")
            self._logger.error(f"Error saving calibrated profile: {e}", exc_info=True)


    @Slot()
    def save_manual_ocr_edits(self): # Fix 3 Implementation
        """Saves only the manually edited OCR parameters, preserving existing patterns."""
        if not self._selected_platform:
            self.status_message_changed.emit("No platform selected.", "ERROR")
            return
        if self._is_calibrating:
            self.status_message_changed.emit("Cannot save while calibrating.", "WARNING")
            return

        self._logger.info(f"Saving manual OCR parameter edits for {self._selected_platform}...")
        self.status_message_changed.emit("Saving OCR parameters...", "INFO")

        try:
            # 1. Get the CURRENTLY saved profile to retrieve existing patterns
            current_profile_res = self._profile_service.get_profile(self._selected_platform)
            if current_profile_res.is_failure:
                 # Handle case where default profile couldn't even be created (should be rare)
                 self.status_message_changed.emit(f"Failed to load current profile to get patterns: {current_profile_res.error}", "ERROR")
                 self._logger.error(f"Failed to load current profile before saving manual edits: {current_profile_res.error}")
                 # Use fallback default patterns if profile load fails
                 existing_patterns = PlatformProfile("dummy").numeric_patterns
            else:
                 existing_patterns = current_profile_res.value.numeric_patterns

            # 2. Use the ViewModel's _current_ocr_profile which reflects UI edits
            edited_ocr_profile = self._current_ocr_profile

            # 3. Create the PlatformProfile to save
            profile_to_save = PlatformProfile(
                platform_name=self._selected_platform,
                ocr_profile=edited_ocr_profile,
                numeric_patterns=existing_patterns # Use EXISTING patterns
            )

            # 4. Save via the service
            save_result = self._profile_service.save_profile(profile_to_save)

            if save_result.is_success:
                self.status_message_changed.emit("Manual OCR parameter edits saved.", "SUCCESS")
                self._logger.info("Manual OCR edits saved successfully.")
            else:
                self.status_message_changed.emit(f"Failed to save OCR edits: {save_result.error}", "ERROR")
                self._logger.error(f"Failed to save manual OCR edits: {save_result.error}")

        except Exception as e:
            self.status_message_changed.emit(f"Error saving manual OCR edits: {str(e)}", "ERROR")
            self._logger.error(f"Error saving manual OCR edits: {e}", exc_info=True)


    @Slot()
    def reset_profile_to_default(self):
        """Resets the OCR profile parameters to the application defaults."""
        if not self._selected_platform:
             self.status_message_changed.emit("No platform selected to reset profile for.", "ERROR")
             return

        self._logger.warning(f"Resetting OCR profile to defaults for {self._selected_platform}")
        self.status_message_changed.emit(f"Resetting profile for {self._selected_platform}...", "INFO")

        # Call service to get/create the default profile object
        # We don't pass an image path, so it uses platform defaults
        result = self._profile_service.create_default_profile(self._selected_platform)

        if result.is_success:
            self.status_message_changed.emit("Profile reset to defaults. Use 'Save Parameter Edits' to persist.", "INFO")
            # Update the internal state and UI with the default profile data
            self._update_ocr_profile_state(result.value.ocr_profile)
            # Clear calibration results
            self._last_calibration_result = None
            self.show_detected_patterns_changed.emit(False)
            self.detected_patterns_changed.emit({})
            self.can_save_calibrated_profile_changed.emit(False)
            self.can_save_manual_edits_changed.emit(True) # Allow saving the defaults if desired
        else:
            self.status_message_changed.emit(f"Failed to reset profile: {result.error}", "ERROR")
            self._logger.error(f"Failed to create/get default profile for reset: {result.error}")


    # --- Internal Slots / Callbacks ---

    @Slot(str)
    def _handle_platform_selection_change(self, platform: str):
        """Reloads calibration source and profile when platform changes."""
        self._logger.debug(f"OcrCalibrationViewModel received platform change: {platform}")
        self._update_for_platform(platform)


    @Slot(int, str)
    def _handle_calibration_progress(self, percent: int, message: str):
        """Updates progress signal."""
        self.calibration_progress_changed.emit(percent, message)


    @Slot(object)
    def _handle_calibration_completed(self, result_data: Optional[Dict[str, Any]]):
        """Handles the result from the CalibrationWorker."""
        self._logger.info(f"Calibration completed. Result data received: {'Yes' if result_data else 'No'}")
        self._is_calibrating = False
        self.calibration_in_progress_changed.emit(False)
        self._last_calibration_result = result_data # Store raw result

        if result_data:
            calibrated_ocr_profile = result_data.get("ocr_profile")
            detected_patterns = result_data.get("patterns", {})
            matched_value = result_data.get("matched_value", "N/A")
            difference = result_data.get("difference", 0)

            if not calibrated_ocr_profile or not isinstance(calibrated_ocr_profile, OcrProfile):
                 self._handle_calibration_error("Calibration result missing or invalid OCR profile data.")
                 return

            self._update_ocr_profile_state(calibrated_ocr_profile) # Updates internal state and emits signals

            pattern_keys = list(detected_patterns.keys())
            pattern_display_state = {key: (key in pattern_keys) for key in ["dollar", "negative", "negative_dash", "regular"]}
            self.detected_patterns_changed.emit(pattern_display_state)
            self.show_detected_patterns_changed.emit(bool(pattern_keys))

            status_msg = f"Calibration successful! Detected value: {matched_value}"
            if difference > 0.001: status_msg += f" (Note: Matched within ${difference:.2f} tolerance)"
            self.calibration_status_text_changed.emit(status_msg, "green")
            self.status_message_changed.emit("Calibration successful. Review and save.", "SUCCESS")

            self.can_save_calibrated_profile_changed.emit(True) # Enable calibrated save
            self.can_save_manual_edits_changed.emit(True) # Also enable manual save

        else:
            # Calibration Failed (Worker returned None)
            self._handle_calibration_error("Calibration failed to find a suitable profile and pattern combination.")
            # Keep existing profile params displayed, don't enable save calibrated
            self.can_save_calibrated_profile_changed.emit(False)
            self.can_save_manual_edits_changed.emit(True) # Still allow saving if user tweaks params


    @Slot(str)
    def _handle_calibration_error(self, error_msg: str):
        """Handles errors reported by the CalibrationWorker or task execution."""
        self._logger.error(f"Calibration Error: {error_msg}")
        self._is_calibrating = False
        self._last_calibration_result = None
        self.calibration_in_progress_changed.emit(False)
        self.calibration_status_text_changed.emit(f"Calibration Error: {error_msg}", "red")
        self.status_message_changed.emit(f"Calibration failed: {error_msg}", "ERROR")
        self.show_detected_patterns_changed.emit(False)
        self.detected_patterns_changed.emit({})
        self.can_save_calibrated_profile_changed.emit(False)
        self.can_save_manual_edits_changed.emit(True) # Allow manual save even if calibration failed


    # --- Slots to update internal _current_ocr_profile from UI edits ---
    # These are needed for save_manual_ocr_edits to work correctly
    @Slot(float)
    def set_scale_factor(self, value: float):
        if self._current_ocr_profile.scale_factor != value:
             self._current_ocr_profile.scale_factor = value
             self.can_save_manual_edits_changed.emit(True) # Enable manual save on edit

    @Slot(int)
    def set_block_size(self, value: int):
        # Ensure block size is odd
        adjusted_value = value + 1 if value % 2 == 0 else value
        if self._current_ocr_profile.threshold_block_size != adjusted_value:
            self._current_ocr_profile.threshold_block_size = adjusted_value
            self.can_save_manual_edits_changed.emit(True)
            # If value was adjusted, emit change back to UI
            if adjusted_value != value:
                 self.threshold_block_size_changed.emit(adjusted_value)

    @Slot(int)
    def set_c_value(self, value: int):
         if self._current_ocr_profile.threshold_c != value:
              self._current_ocr_profile.threshold_c = value
              self.can_save_manual_edits_changed.emit(True)

    @Slot(int)
    def set_denoise_h(self, value: int):
         if self._current_ocr_profile.denoise_h != value:
              self._current_ocr_profile.denoise_h = value
              self.can_save_manual_edits_changed.emit(True)

    @Slot(str)
    def set_tesseract_config(self, value: str):
         if self._current_ocr_profile.tesseract_config != value:
              self._current_ocr_profile.tesseract_config = value
              self.can_save_manual_edits_changed.emit(True)

    @Slot(bool)
    def set_invert_colors(self, value: bool):
         if self._current_ocr_profile.invert_colors != value:
              self._current_ocr_profile.invert_colors = value
              self.can_save_manual_edits_changed.emit(True)
    # --- End Slots for UI edits ---


    # --- Private Helper Methods ---

    def _update_for_platform(self, platform: str):
        """Loads calibration source image and current profile for the platform."""
        self._selected_platform = platform
        self._logger.info(f"Updating calibration view for platform: {platform}")
        self._expected_value = ""
        self._is_calibrating = False
        self._last_calibration_result = None
        self.calibration_in_progress_changed.emit(False)
        self.can_save_calibrated_profile_changed.emit(False)
        self.show_detected_patterns_changed.emit(False)
        self.detected_patterns_changed.emit({})

        if not platform:
             self._clear_calibration_source()
             self._update_ocr_profile_state(OcrProfile())
             self.can_save_manual_edits_changed.emit(False) # Cannot save manual edits without platform
             return

        profile_res = self._profile_service.get_profile(platform)
        if profile_res.is_success:
             self._update_ocr_profile_state(profile_res.value.ocr_profile)
        else:
             self._logger.error(f"Failed to load profile for {platform} on view update: {profile_res.error}")
             self.status_message_changed.emit(f"Error loading profile: {profile_res.error}", "ERROR")
             self._update_ocr_profile_state(OcrProfile())

        self.can_save_manual_edits_changed.emit(True) # Allow manual save once platform loaded
        self._load_calibration_source(platform)

    def _clear_calibration_source(self):
        self._calibration_source_image_path = None
        self._source_preview_pixmap = QPixmap()  # Store empty
        self._source_status_text = "Select platform and define Monitor Region."  # Store text
        # --- Emit signals using stored state ---
        self.calibration_source_preview_changed.emit(self._source_preview_pixmap)
        self.calibration_source_status_text_changed.emit(self._source_status_text)
        self.can_calibrate_changed.emit(False)
        self.calibration_status_text_changed.emit(self._source_status_text, "gray")

    def _load_calibration_source(self, platform: str):
        """Loads the monitor region screenshot for the specified platform."""
        if not platform:
            self._clear_calibration_source() # This helper also updates internal state now
            return

        # --- Reset state before loading ---
        preview_pixmap = QPixmap()
        status_text = ""
        can_calibrate = False
        self._calibration_source_image_path = None # Clear path initially
        # --- End Reset ---

        region_result = self._region_service.get_monitor_region(platform)

        if region_result.is_success and region_result.value:
            monitor_region = region_result.value
            screenshot_path = monitor_region.screenshot_path

            if screenshot_path and os.path.exists(screenshot_path):
                self._logger.debug(f"Found screenshot path: {screenshot_path}")
                load_res = self._region_service.load_region_screenshot(monitor_region)
                if load_res.is_success:
                    pixmap_res = self._screenshot_service.to_pyside_pixmap(load_res.value)
                    if pixmap_res.is_success:
                        preview_pixmap = pixmap_res.value
                        status_text = f"Using screenshot from Monitor region: {os.path.basename(screenshot_path)}"
                        can_calibrate = True
                        self._calibration_source_image_path = screenshot_path # Store path
                        self._logger.debug(f"Successfully loaded and converted preview for {platform}.")
                    else:
                        status_text = "Error: Failed to convert screenshot preview."
                        self._logger.warning(f"Failed to convert screenshot to QPixmap for {platform}: {pixmap_res.error}")
                else:
                    status_text = f"Error: Failed to load screenshot file: {os.path.basename(screenshot_path)}"
                    self._logger.warning(f"Failed to load screenshot file {screenshot_path}: {load_res.error}")
            elif screenshot_path:
                 status_text = f"Monitor Region defined, but screenshot file not found: {os.path.basename(screenshot_path)}"
                 self._logger.warning(f"Screenshot file path exists in config but not on disk: {screenshot_path}")
            else:
                 status_text = "Monitor Region defined, but no screenshot path recorded."
                 self._logger.debug(f"Monitor region loaded for {platform}, but no screenshot path associated.")
        elif region_result.is_failure:
            status_text = f"Error loading region data: {region_result.error}"
            self._logger.warning(f"Failed to load monitor region for {platform}: {region_result.error}")
        else: # Not defined
            status_text = "P&L Monitor Region not defined for this platform."
            self._logger.debug(f"Monitor region not defined for {platform}.")

        # --- Store state internally ---
        self._source_preview_pixmap = preview_pixmap
        self._source_status_text = status_text
        # self._calibration_source_image_path is set above if successful
        # --- End Store state ---

        # --- Emit signals using stored state ---
        self.calibration_source_preview_changed.emit(self._source_preview_pixmap)
        self.calibration_source_status_text_changed.emit(self._source_status_text)
        self.can_calibrate_changed.emit(can_calibrate)
        # Update calibration status text based on whether calibration is possible
        initial_calib_status = "Enter value shown above and click Calibrate." if can_calibrate else status_text
        initial_calib_color = "gray" # Always start gray until calibration runs
        self.calibration_status_text_changed.emit(initial_calib_status, initial_calib_color)

    def _update_ocr_profile_state(self, ocr_profile: OcrProfile):
        """Updates internal state and emits signals for OCR parameters."""
        if not isinstance(ocr_profile, OcrProfile):
             self._logger.error(f"Invalid OCR profile type received: {type(ocr_profile)}. Resetting to default.")
             ocr_profile = OcrProfile()

        self._current_ocr_profile = dataclasses.replace(ocr_profile) # Store a copy

        self.scale_factor_changed.emit(self._current_ocr_profile.scale_factor)
        self.threshold_block_size_changed.emit(self._current_ocr_profile.threshold_block_size)
        self.threshold_c_changed.emit(self._current_ocr_profile.threshold_c)
        self.denoise_h_changed.emit(self._current_ocr_profile.denoise_h)
        self.tesseract_config_changed.emit(self._current_ocr_profile.tesseract_config)
        self.invert_colors_changed.emit(self._current_ocr_profile.invert_colors)
        # Enable manual saving whenever profile state is updated (load, reset, calibration)
        self.can_save_manual_edits_changed.emit(self._selected_platform is not None)