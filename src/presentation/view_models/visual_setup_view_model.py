# src/presentation/view_models/visual_setup_view_model.py

import os
import re
import uuid
from typing import List, Optional, Dict, Any, Tuple, Iterable  # Added Iterable

# --- Qt Imports ---
from PySide6.QtCore import QObject, Signal, Slot, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QWidget  # For theme updates

# --- Application Imports ---
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_region_service import IRegionService
from src.domain.services.i_platform_selection_service import IPlatformSelectionService
from src.domain.services.i_flash_service import IFlashService
from src.domain.services.i_ui_service import IUIService
from src.domain.services.i_screenshot_service import IScreenshotService
from src.domain.services.i_profile_service import IProfileService
from src.domain.services.i_ocr_service import IOcrService
from src.domain.services.i_ocr_analysis_service import IOcrAnalysisService
from src.domain.services.i_background_task_service import IBackgroundTaskService, \
    Worker  # Keep Worker if CalibrationWorker is inner
from src.domain.models.region_model import Region
from src.domain.models.platform_profile import PlatformProfile, OcrProfile
from src.domain.common.result import Result
from src.domain.common.errors import ErrorCategory, ConfigurationError, ResourceError

# --- CalibrationWorker Definition (can be moved to a separate file if large) ---
# For now, let's assume it's copied here from ocr_calibration_view_model.py
# Ensure DEFAULT_TESSERACT_WHITELIST is defined or imported
try:
    from src.domain.models.platform_profile import DEFAULT_TESSERACT_WHITELIST
except ImportError:
    DEFAULT_TESSERACT_WHITELIST = "-c tessedit_char_whitelist=0123456789.,-()$"

import dataclasses  # For CalibrationWorker if it uses dataclasses.replace
import PIL.Image  # For CalibrationWorker


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
        # --- Keep existing implementation ---
        self.report_started()
        self.report_progress(0, "Starting calibration...")

        # --- Keep expected value processing ---
        expected_value_str = self.expected_value.strip()
        try:
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

        # --- Keep image loading ---
        try:
            image = PIL.Image.open(self.image_path)
        except Exception as e:
            self.report_error(f"Failed to load image: {e}")
            return None

        # --- Keep baseline detection ---
        self.report_progress(5, "Detecting baseline OCR parameters...")
        ocr_result = self.ocr_analysis_service.detect_optimal_ocr_parameters(self.image_path)
        if ocr_result.is_failure:
            self.report_error(f"Failed to detect baseline OCR parameters: {ocr_result.error}")
            return None
        base_profile = ocr_result.value
        # --- Base profile now includes whitelist from OcrAnalysisService ---
        self.logger.info(f"Baseline OCR profile detected: {base_profile}")

        # --- Keep variation generation ---
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

        # --- Keep main iteration loop ---
        for i, current_profile in enumerate(profiles_to_try):
            if self.cancel_requested: self.report_error("Calibration cancelled"); return None
            self.logger.debug(f"Testing OCR Profile {i+1}/{len(profiles_to_try)}: {current_profile}") # Profile now includes whitelist
            image_copy = image.copy()
            # --- Keep OCR text extraction ---
            extract_result = self.ocr_service.extract_text_with_profile(image_copy, current_profile)
            if extract_result.is_failure:
                self.logger.warning(f"OCR failed for profile {i+1}: {extract_result.error}")
                self.current_attempt += len(patterns_to_try); continue
            extracted_text = extract_result.value
            self.logger.debug(f"  Profile {i+1} Extracted text: '{extracted_text}'")
            if not extracted_text or not extracted_text.strip():
                 self.logger.debug("  Skipping pattern matching for empty/whitespace text.")
                 self.current_attempt += len(patterns_to_try); continue

            # --- Keep pattern iteration ---
            for j, pattern_set in enumerate(patterns_to_try):
                self.current_attempt += 1
                progress_pct = int((self.current_attempt / self.total_attempts) * 90) + 5 if self.total_attempts > 0 else 5
                self.report_progress(progress_pct, f"Testing profile {i+1}, pattern set {j+1}...")
                if self.cancel_requested: self.report_error("Calibration cancelled"); return None

                # --- Keep numeric extraction and matching logic ---
                numeric_result = self.ocr_service.extract_numeric_values_with_patterns(extracted_text, pattern_set)
                if numeric_result.is_success and numeric_result.value:
                    extracted_values = numeric_result.value
                    self.logger.debug(f"    Pattern set {j+1} extracted: {extracted_values}")
                    for value in extracted_values:
                        difference = abs(value - target_value)
                        if difference < 0.001:
                            self.report_progress(100, f"Found exact match: {value}")
                            self.logger.info(f"Exact match found with profile {i+1}, patterns {j+1}")
                            # Return the successful profile (incl. whitelist) and pattern set
                            return { "ocr_profile": current_profile, "patterns": pattern_set, "extracted_text": extracted_text, "matched_value": value }
                        if difference < min_difference:
                             min_difference = difference
                             best_match_info = { "ocr_profile": current_profile, "patterns": pattern_set, "extracted_text": extracted_text, "matched_value": value, "difference": difference }
                             self.logger.debug(f"  New best match: {value} (Diff: {difference:.4f})")
                elif numeric_result.is_failure:
                    self.logger.debug(f"    Pattern set {j+1} extraction failed: {numeric_result.error}")
                else:
                    self.logger.debug(f"    Pattern set {j+1} extracted no values.")

        # --- Keep best match checking ---
        if best_match_info and min_difference < 1.0:
            self.report_progress(95, f"Found close match: {best_match_info['matched_value']} (diff: {min_difference:.2f})")
            self.logger.info(f"Close match found (Diff: {min_difference:.4f}): {best_match_info}")
            return best_match_info

        # --- Keep final error reporting ---
        self.report_error("Could not find matching OCR profile and pattern combination.")
        self.logger.warning("Calibration finished without finding a satisfactory match.")
        return None

    def _generate_pattern_variations(self) -> List[Dict[str, str]]:
        """Generates sets of regex patterns to try."""
        # --- Keep existing implementation ---
        variations = []
        base = self.ocr_analysis_service.get_default_patterns()
        variations.append({"dollar": base.get("dollar", "")})
        variations.append({"negative": base.get("negative", "")})
        variations.append({"negative_dash": base.get("negative_dash", "")})
        variations.append({"regular": base.get("regular", "")})
        variations.append({k: v for k, v in base.items() if k in ["dollar", "negative", "negative_dash"]})
        variations.append({k: v for k, v in base.items() if k in ["negative", "negative_dash", "regular"]})
        variations.append(base.copy())
        variations = [v for v in variations if v]
        return variations

    def _generate_ocr_profile_variations(self, base_profile: OcrProfile) -> List[OcrProfile]:
        """
        Generates variations of OCR parameters around a baseline,
        ensuring the whitelist is included in Tesseract configs.
        Uses a list and checks for uniqueness to avoid hashing mutable fields.
        """
        self.logger.debug("Generating OCR profile variations...")

        # --- Define Parameter Variations ---
        scale_factors = {base_profile.scale_factor, max(1.0, base_profile.scale_factor - 0.5),
                         base_profile.scale_factor + 0.5, base_profile.scale_factor + 1.0, 2.0, 2.5, 3.0}
        denoise_hs = {base_profile.denoise_h, max(0, base_profile.denoise_h - 5), base_profile.denoise_h + 5, 0, 7,
                      10, 13}  # Include 0 explicitly
        invert_options = {base_profile.invert_colors, not base_profile.invert_colors}

        threshold_sets = set()
        base_block = max(3, base_profile.threshold_block_size)
        if base_block % 2 == 0: base_block += 1
        base_c = base_profile.threshold_c
        for block_delta in [0, -4, 4, -2, 2]:
            for c_delta in [0, -2, 2, -1, 1]:
                new_block = base_block + block_delta
                new_c = base_c + c_delta
                if new_block < 3: new_block = 3
                if new_block % 2 == 0: new_block += 1
                if new_c < 0: new_c = 0
                threshold_sets.add((new_block, new_c))
        threshold_sets.add((11, 2));
        threshold_sets.add((15, 3));
        threshold_sets.add((9, 2))

        psm_options_configs = set()
        whitelist_part = f" {DEFAULT_TESSERACT_WHITELIST}"
        base_tess_config = base_profile.tesseract_config
        if not base_tess_config:  # Handle empty base config
            base_tess_config = f"--oem 3 --psm 7{whitelist_part}"  # Sensible default
        elif DEFAULT_TESSERACT_WHITELIST not in base_tess_config:
            base_tess_config += whitelist_part
        psm_options_configs.add(base_tess_config.strip())

        for psm_val in [6, 7, 8, 11, 13]:
            config_base = f"--oem 3 --psm {psm_val}"
            # Add only if the base PSM is different from the current one, to avoid redundant configs
            current_base_psm_str = f"--oem 3 --psm {re.search(r'--psm\s+(\d+)', base_tess_config).group(1) if re.search(r'--psm\s+(\d+)', base_tess_config) else '7'}"
            if config_base != current_base_psm_str:
                psm_options_configs.add(f"{config_base}{whitelist_part}")
        # --- End Parameter Variations Definition ---

        # --- Use a LIST and check uniqueness manually ---
        generated_profiles_list: List[OcrProfile] = [base_profile]  # Start with the baseline

        # Helper function to add only if unique
        def add_unique_profile(profile_to_add):
            # Dataclasses implement __eq__ based on fields, so 'in' works for uniqueness check
            if profile_to_add not in generated_profiles_list:
                generated_profiles_list.append(profile_to_add)

        # --- Systematically create variations, adding uniquely layer by layer ---
        last_count = 0
        self.logger.debug(f" Starting variations with {len(generated_profiles_list)} profile(s)")

        # Apply Scale Factor variations
        current_snapshot = list(generated_profiles_list)
        for profile in current_snapshot:
            for sf in scale_factors:
                add_unique_profile(dataclasses.replace(profile, scale_factor=sf))
        self.logger.debug(
            f" After Scale Factor: {len(generated_profiles_list)} profiles (+{len(generated_profiles_list) - last_count})")
        last_count = len(generated_profiles_list)

        # Apply Denoise H variations
        current_snapshot = list(generated_profiles_list)
        for profile in current_snapshot:
            for dh in denoise_hs:
                add_unique_profile(dataclasses.replace(profile, denoise_h=dh))
        self.logger.debug(
            f" After Denoise H: {len(generated_profiles_list)} profiles (+{len(generated_profiles_list) - last_count})")
        last_count = len(generated_profiles_list)

        # Apply Invert Colors variations
        current_snapshot = list(generated_profiles_list)
        for profile in current_snapshot:
            for inv in invert_options:
                add_unique_profile(dataclasses.replace(profile, invert_colors=inv))
        self.logger.debug(
            f" After Invert Colors: {len(generated_profiles_list)} profiles (+{len(generated_profiles_list) - last_count})")
        last_count = len(generated_profiles_list)

        # Apply Threshold variations
        current_snapshot = list(generated_profiles_list)
        for profile in current_snapshot:
            for block, c_val in threshold_sets:
                add_unique_profile(dataclasses.replace(profile, threshold_block_size=block, threshold_c=c_val))
        self.logger.debug(
            f" After Threshold: {len(generated_profiles_list)} profiles (+{len(generated_profiles_list) - last_count})")
        last_count = len(generated_profiles_list)

        # Apply Tesseract Config variations
        current_snapshot = list(generated_profiles_list)
        for profile in current_snapshot:
            for tess_config in psm_options_configs:
                add_unique_profile(dataclasses.replace(profile, tesseract_config=tess_config))
        self.logger.debug(
            f" After Tesseract Config: {len(generated_profiles_list)} profiles (+{len(generated_profiles_list) - last_count})")
        # --- End Variation Generation ---

        self.logger.info(f"Generated {len(generated_profiles_list)} final unique OCR profile variations.")
        return generated_profiles_list  # Return the list


class VisualSetupViewModel(QObject):
    """
    ViewModel for the consolidated "Visual Setup" tab.
    Manages P&L Monitor Region, Flatten Regions, and OCR Calibration.
    """

    # --- Signals from RegionSetupViewModel ---
    monitor_region_status_changed = Signal(str)
    monitor_region_coords_text_changed = Signal(str)
    monitor_region_preview_changed = Signal(QPixmap)  # This will be the primary preview
    can_delete_monitor_region_changed = Signal(bool)
    can_flash_monitor_region_changed = Signal(bool)
    monitor_region_saved = Signal(str)

    flatten_regions_list_updated = Signal(list)
    can_add_flatten_region_changed = Signal(bool)
    # No need for flatten_region_count_changed, view can derive from list length

    # --- Signals from OcrCalibrationViewModel ---
    # calibration_source_preview_changed # Not needed, uses monitor_region_preview_changed
    calibration_source_status_text_changed = Signal(str)  # For status specific to OCR source readiness
    can_calibrate_changed = Signal(bool)
    expected_value_changed = Signal(str)
    calibration_in_progress_changed = Signal(bool)
    calibration_progress_changed = Signal(int, str)
    calibration_status_text_changed = Signal(str, str)  # message, color for OCR status line

    scale_factor_changed = Signal(float)
    threshold_block_size_changed = Signal(int)
    threshold_c_changed = Signal(int)
    denoise_h_changed = Signal(int)
    tesseract_config_changed = Signal(str)
    invert_colors_changed = Signal(bool)

    can_save_calibrated_profile_changed = Signal(bool)
    can_save_manual_edits_changed = Signal(bool)
    # profile_potentially_changed # Renamed/repurposed from OcrCalibrationViewModel
    visual_setup_profile_changed = Signal(
        str)  # Emits platform name when OCR profile or monitor region (which might affect profile) is saved/reset

    # --- Common Signals ---
    status_message_changed = Signal(str, str)  # For main window status bar

    def __init__(self,
                 logger: ILoggerService,
                 region_service: IRegionService,
                 platform_selection_service: IPlatformSelectionService,
                 flash_service: IFlashService,
                 ui_service: IUIService,
                 screenshot_service: IScreenshotService,
                 profile_service: IProfileService,  # From OCR VM
                 ocr_service: IOcrService,  # From OCR VM
                 ocr_analysis_service: IOcrAnalysisService,  # From OCR VM
                 thread_service: IBackgroundTaskService,  # From OCR VM
                 parent: Optional[QObject] = None):
        super().__init__(parent)
        self._logger = logger
        self._region_service = region_service
        self._platform_selection_service = platform_selection_service
        self._flash_service = flash_service
        self._ui_service = ui_service
        self._screenshot_service = screenshot_service
        self._profile_service = profile_service
        self._ocr_service = ocr_service
        self._ocr_analysis_service = ocr_analysis_service
        self._thread_service = thread_service

        self._logger.info("Initializing VisualSetupViewModel...")

        # --- Combined Internal State ---
        self._selected_platform: Optional[str] = None

        # Monitor Region State
        self._monitor_region_status_text: str = "N/A"
        self._monitor_region_coords_text: str = "N/A"
        self._monitor_region_preview_pixmap: QPixmap = QPixmap()  # Primary preview
        self._monitor_region_screenshot_path: Optional[str] = None  # Path to the image used for OCR
        self._can_delete_monitor: bool = False
        self._can_flash_monitor: bool = False

        # Flatten Regions State
        self._flatten_list_data: List[Dict[str, Any]] = []
        self._can_add_flatten: bool = True  # Usually true if platform selected

        # OCR Calibration State
        self._expected_value: str = ""
        self._is_calibrating: bool = False
        self._last_calibration_result: Optional[Dict[str, Any]] = None
        self._current_ocr_profile: OcrProfile = OcrProfile()  # Default empty profile
        self._ocr_source_status_text: str = "Define Monitor Region first."  # Status for OCR readiness
        self._calibration_status_text: str = "Ready."
        self._calibration_status_color: str = "gray"

        # Connect to platform changes
        self._platform_selection_service.register_platform_change_listener(
            self._handle_platform_selection_change
        )
        initial_platform = self._platform_selection_service.get_current_platform()
        self._load_data_for_platform(initial_platform)

        self._logger.info("VisualSetupViewModel initialized.")

    # --- Slots & Methods to be merged and implemented ---

    @Slot()
    def refresh_ui_signals(self):
        """Re-emits all current state signals for initial View synchronization."""
        self._logger.debug(f"VisualSetupVM: Refreshing UI signals for {self._selected_platform or 'None'}")

        # Monitor Region
        self.monitor_region_status_changed.emit(self._monitor_region_status_text)
        self.monitor_region_coords_text_changed.emit(self._monitor_region_coords_text)
        self.monitor_region_preview_changed.emit(self._monitor_region_preview_pixmap)
        self.can_delete_monitor_region_changed.emit(self._can_delete_monitor)
        self.can_flash_monitor_region_changed.emit(self._can_flash_monitor)

        # Flatten Regions
        self.flatten_regions_list_updated.emit(self._flatten_list_data)
        self.can_add_flatten_region_changed.emit(self._can_add_flatten)

        # OCR Calibration
        self.calibration_source_status_text_changed.emit(self._ocr_source_status_text)
        self.can_calibrate_changed.emit(self._monitor_region_screenshot_path is not None and not self._is_calibrating)
        self.expected_value_changed.emit(self._expected_value)
        self.calibration_in_progress_changed.emit(self._is_calibrating)
        self.calibration_status_text_changed.emit(self._calibration_status_text, self._calibration_status_color)

        self.scale_factor_changed.emit(self._current_ocr_profile.scale_factor)
        self.threshold_block_size_changed.emit(self._current_ocr_profile.threshold_block_size)
        self.threshold_c_changed.emit(self._current_ocr_profile.threshold_c)
        self.denoise_h_changed.emit(self._current_ocr_profile.denoise_h)
        self.tesseract_config_changed.emit(self._current_ocr_profile.tesseract_config)
        self.invert_colors_changed.emit(self._current_ocr_profile.invert_colors)

        self.can_save_calibrated_profile_changed.emit(
            self._last_calibration_result is not None and not self._is_calibrating)
        self.can_save_manual_edits_changed.emit(self._selected_platform is not None and not self._is_calibrating)

    @Slot(str)
    def _handle_platform_selection_change(self, platform: str):
        self._logger.debug(f"VisualSetupVM: Platform changed to '{platform}'")
        self._load_data_for_platform(platform)

    def _load_data_for_platform(self, platform: Optional[str]):
        """Loads all data (monitor region, flatten regions, OCR profile) for the given platform."""
        self._selected_platform = platform
        self._logger.info(f"VisualSetupVM: Loading all data for platform: '{platform or 'None'}'")

        if not platform:
            # Reset all states and emit signals
            self._monitor_region_status_text = "Select Platform"
            self._monitor_region_coords_text = "N/A"
            self._monitor_region_preview_pixmap = QPixmap()
            self._monitor_region_screenshot_path = None
            self._can_delete_monitor = False
            self._can_flash_monitor = False
            self._flatten_list_data = []
            self._can_add_flatten = False  # Can't add if no platform

            self._expected_value = ""
            self._is_calibrating = False  # Should not be calibrating if platform changes
            self._last_calibration_result = None
            self._current_ocr_profile = OcrProfile()  # Reset to default
            self._ocr_source_status_text = "Select Platform and define Monitor Region."
            self._calibration_status_text = "Ready."
            self._calibration_status_color = "gray"

            self.refresh_ui_signals()  # Emit all cleared states
            return

        # Platform is selected, proceed to load data
        self._can_add_flatten = True  # Can add flatten if platform is selected

        # 1. Load Monitor Region Info (and updates OCR source path)
        self._load_monitor_region_data(platform)  # This will update preview and screenshot path

        # 2. Load Flatten Regions Info
        self._load_flatten_regions(platform)

        # 3. Load OCR Profile (and related OCR states)
        self._load_ocr_profile_data(
            platform)  # This depends on monitor region screenshot path being set by _load_monitor_region_data

        # 4. Emit all updated states
        self.refresh_ui_signals()  # Call at the end to ensure all derived states are correct

    def _load_monitor_region_data(self, platform: str):
        # (Logic from RegionSetupViewModel._load_monitor_region)
        # IMPORTANT: This method should now also set self._monitor_region_screenshot_path
        # And it should update self._ocr_source_status_text and self.can_calibrate_changed
        self._logger.debug(f"VisualSetupVM: Loading monitor region for {platform}")
        result = self._region_service.get_monitor_region(platform)
        preview_pixmap = QPixmap()
        screenshot_path_for_ocr: Optional[str] = None
        ocr_source_status = "P&L Monitor Region not defined."  # Default for OCR
        can_calibrate_ocr = False

        if result.is_success and result.value is not None:
            region = result.value
            x, y, w, h = region.coordinates
            self._monitor_region_status_text = "Defined"
            self._monitor_region_coords_text = f"({x}, {y}, {w}, {h})"
            self._can_delete_monitor = True
            self._can_flash_monitor = True
            preview_pixmap = self._load_region_preview(region)  # Reusable helper

            if region.screenshot_path and os.path.exists(region.screenshot_path):
                screenshot_path_for_ocr = region.screenshot_path
                ocr_source_status = f"Using: {os.path.basename(region.screenshot_path)}"
                can_calibrate_ocr = True
            elif region.screenshot_path:
                ocr_source_status = f"Error: Screenshot file missing ('{os.path.basename(region.screenshot_path)}'). Recapture needed."
            else:
                ocr_source_status = "Monitor Region defined, but no screenshot saved. Recapture needed."
        else:
            self._monitor_region_status_text = "Not Defined"
            self._monitor_coords_text = "N/A"
            self._can_delete_monitor = False
            self._can_flash_monitor = False
            if result.is_failure:
                self.status_message_changed.emit(f"Error loading monitor region: {result.error}", "WARNING")

        self._monitor_region_preview_pixmap = preview_pixmap
        self._monitor_region_screenshot_path = screenshot_path_for_ocr  # CRITICAL for OCR
        self._ocr_source_status_text = ocr_source_status  # Update OCR source status

    def _load_flatten_regions(self, platform: str):
        if not platform: return
        result = self._region_service.get_regions_by_platform(platform, "flatten")
        flatten_region_list_data = []

        if result.is_success and result.value:
            flatten_regions = result.value
            for region in flatten_regions:
                coords = region.coordinates
                preview_pixmap = self._load_region_preview(region)
                region_item_data = {
                    "name": region.name,
                    "coords_text": f"({coords[0]}, {coords[1]}, {coords[2]}, {coords[3]})",
                    "preview_pixmap": preview_pixmap
                }
                flatten_region_list_data.append(region_item_data)
        elif result.is_failure:
            self.status_message_changed.emit(f"Error loading flatten regions: {result.error}", "WARNING")

        # --- Update Internal State & Emit Signal ---
        self._flatten_list_data = flatten_region_list_data
        self.flatten_regions_list_updated.emit(self._flatten_list_data)

    def _load_ocr_profile_data(self, platform: str):
        # (Logic from OcrCalibrationViewModel._update_for_platform, focusing on profile part)
        self._logger.debug(f"VisualSetupVM: Loading OCR profile for {platform}")
        profile_res = self._profile_service.get_profile(platform)
        loaded_ocr_profile = OcrProfile()  # Default
        status_message = "Ready."
        status_color = "gray"
        allow_manual_save = False

        if profile_res.is_success and profile_res.value:
            loaded_ocr_profile = profile_res.value.ocr_profile
            status_message = f"Loaded saved OCR profile for {platform}."
            allow_manual_save = True
        else:
            loaded_ocr_profile = self._profile_service._get_platform_default_ocr_profile(platform)
            if profile_res.is_failure:
                status_message = f"Error loading OCR profile. Using defaults. ({profile_res.error})"
                status_color = "orange"
            else:  # No profile saved yet
                status_message = "No OCR profile saved. Using defaults."
            allow_manual_save = True  # Can always save the defaults as a starting point

        self._current_ocr_profile = loaded_ocr_profile  # Update internal state
        # self._update_ocr_profile_ui_elements(loaded_ocr_profile) # Emits individual OCR param signals (called by refresh_ui_signals)

        # If source image isn't ready, that takes precedence for status
        if not self._monitor_region_screenshot_path:
            self._calibration_status_text = self._ocr_source_status_text
            self._calibration_status_color = "orange"  # Or appropriate color
        else:
            self._calibration_status_text = status_message
            self._calibration_status_color = status_color

        # self.can_save_manual_edits_changed.emit(allow_manual_save and not self._is_calibrating) # Emitted by refresh
        # self.calibration_status_text_changed.emit(self._calibration_status_text, self._calibration_status_color) # Emitted by refresh

    def _load_region_preview(self, region: Region) -> QPixmap:
        """Helper to load and convert a region's screenshot to QPixmap."""
        empty_pixmap = QPixmap()
        if not region or not region.screenshot_path:
            return empty_pixmap

        load_result = self._region_service.load_region_screenshot(region)
        if load_result.is_failure:
            self._logger.warning(f"Failed to load screenshot file for {region.name}: {load_result.error}")
            return empty_pixmap

        # Convert PIL Image data to QPixmap
        pixmap_result = self._screenshot_service.to_pyside_pixmap(load_result.value)
        if pixmap_result.is_failure:
            self._logger.warning(f"Failed to convert screenshot to QPixmap for {region.name}: {pixmap_result.error}")
            return empty_pixmap

        return pixmap_result.value

    @Slot()
    def define_edit_monitor_region(self):
        # (Copy logic from RegionSetupViewModel.define_edit_monitor_region)
        # IMPORTANT: After successful save, call:
        #   self._load_monitor_region_data(self._selected_platform)
        #   self.visual_setup_profile_changed.emit(self._selected_platform) # If monitor region change implies profile change
        #   Also, update OCR source status based on new screenshot
        if not self._selected_platform: self.status_message_changed.emit("No platform selected.", "ERROR"); return
        action_text = "editing" if self._monitor_region_screenshot_path else "defining"  # Basic check
        self.status_message_changed.emit(f"Starting selection for {action_text} P&L region...", "INFO")
        region_result = self._ui_service.select_screen_region("Select P&L Monitoring region")
        if region_result.is_failure or region_result.value is None:
            self.status_message_changed.emit(
                f"P&L region selection {'failed' if region_result.is_failure else 'cancelled'}.",
                "ERROR" if region_result.is_failure else "INFO")
            return
        coordinates = region_result.value
        region = Region(id=f"{self._selected_platform}_monitor_monitor", name="monitor", coordinates=coordinates,
                        type="monitor", platform=self._selected_platform)
        capture_result = self._region_service.capture_region_screenshot(coordinates, region.id, region.platform,
                                                                        region.type)
        if capture_result.is_success:
            setattr(region, '_temp_screenshot_data', capture_result.value[0])
        else:
            self.status_message_changed.emit(f"Failed to capture P&L screenshot: {capture_result.error}", "WARNING")
        save_result = self._region_service.save_region(region)
        if save_result.is_success:
            self.status_message_changed.emit(f"P&L region saved: {coordinates}", "SUCCESS")
            self.monitor_region_saved.emit(self._selected_platform)  # Old signal
            self.visual_setup_profile_changed.emit(self._selected_platform)  # New consolidated signal
            self._load_monitor_region_data(self._selected_platform)  # This reloads preview & OCR source status
            self.refresh_ui_signals()  # To update can_calibrate etc.
        else:
            self.status_message_changed.emit(f"Failed to save P&L region: {save_result.error}", "ERROR")

    @Slot()
    def delete_monitor_region(self):
        # (Copy logic from RegionSetupViewModel.delete_monitor_region)
        # After successful delete, call:
        #   self._load_monitor_region_data(self._selected_platform)
        #   self.visual_setup_profile_changed.emit(self._selected_platform)
        if not self._selected_platform: self.status_message_changed.emit("No platform selected.", "ERROR"); return
        confirm = self._ui_service.show_confirmation("Confirm Delete",
                                                     f"Delete P&L region for {self._selected_platform}?")
        if not (confirm.is_success and confirm.value): self.status_message_changed.emit(
            "P&L region deletion cancelled.", "INFO"); return
        delete_result = self._region_service.delete_region(self._selected_platform, "monitor", "monitor")
        if delete_result.is_success or (
                delete_result.is_failure and delete_result.error.category == ErrorCategory.VALIDATION):
            self.status_message_changed.emit("P&L region deleted.", "SUCCESS")
            self.monitor_region_saved.emit(self._selected_platform)  # Signal that monitor region config changed
            self.visual_setup_profile_changed.emit(self._selected_platform)
            self._load_monitor_region_data(self._selected_platform)
            self.refresh_ui_signals()
        else:
            self.status_message_changed.emit(f"Failed to delete P&L region: {delete_result.error}", "ERROR")

    @Slot()
    def flash_monitor_region(self):
        # (Copy logic from RegionSetupViewModel.flash_monitor_region)
        if not self._selected_platform: self.status_message_changed.emit("No platform selected.", "ERROR"); return
        region_result = self._region_service.get_monitor_region(self._selected_platform)
        if not (region_result.is_success and region_result.value and region_result.value.coordinates):
            self.status_message_changed.emit(f"P&L region not defined for {self._selected_platform}.", "ERROR");
            return
        self._flash_service.flash_regions([region_result.value.coordinates])

    @Slot()
    def add_flatten_region(self):
        """Starts the process to add a new flatten region."""
        if not self._selected_platform:
            self.status_message_changed.emit("No platform selected.", "ERROR")
            return

        region_type = "flatten"

        # --- Get default name ---
        flatten_regions_result = self._region_service.get_regions_by_platform(self._selected_platform, region_type)
        count = len(flatten_regions_result.value) if flatten_regions_result.is_success else 0
        default_name = f"Flatten_{count + 1}"

        self.status_message_changed.emit(f"Starting region selection for adding a flatten region...", "INFO")

        # --- Select Area ---
        region_result = self._ui_service.select_screen_region("Please select the Flatten Position button region")
        if region_result.is_failure:
            self.status_message_changed.emit(f"Region selection failed: {region_result.error}", "ERROR")
            return
        if region_result.value is None:
            self.status_message_changed.emit("Region selection cancelled.", "INFO")
            return
        coordinates = region_result.value

        # --- Get Name (Using QInputDialog via UIService - Needs adding) ---
        # Assuming UIService needs a method like get_text_input(title, label, default) -> Result[Optional[str]]
        # For now, we'll use a placeholder and log.
        # name_result = self._ui_service.get_text_input("Name Flatten Region", "Enter a unique name:", default_name)
        # if name_result.is_failure or name_result.value is None:
        #      self.status_message_changed.emit("Region naming cancelled.", "INFO")
        #      return
        # name = name_result.value.strip()
        # --- Placeholder until UIService.get_text_input exists ---
        name = default_name  # Use default name for now
        self._logger.warning("UIService needs get_text_input; using default name for flatten region.")
        # --- End Placeholder ---

        # TODO: Add validation loop here once get_text_input exists
        # - Check if name is empty
        # - Check if name already exists using self._region_service.get_region
        # - Ask for overwrite confirmation if exists

        # Create Region Object
        region_id = f"{self._selected_platform}_{region_type}_{name}"
        region = Region(id=region_id, name=name, coordinates=coordinates, type=region_type,
                        platform=self._selected_platform)

        # Capture Screenshot
        capture_result = self._region_service.capture_region_screenshot(coordinates, region.id, region.platform,
                                                                        region.type)
        if capture_result.is_success:
            setattr(region, '_temp_screenshot_data', capture_result.value[0])
        else:
            self.status_message_changed.emit(f"Failed capture screenshot for '{name}': {capture_result.error}",
                                             "WARNING")

        # Save Region
        save_result = self._region_service.save_region(region)
        if save_result.is_failure:
            self.status_message_changed.emit(f"Failed to save flatten region '{name}': {save_result.error}", "ERROR")
            return

        self.status_message_changed.emit(f"Added flatten region '{name}': {coordinates}", "SUCCESS")
        # Refresh the flatten list display
        self._load_flatten_regions(self._selected_platform)

    @Slot(str)  # Expects the region name (ID for the entry widget)
    def edit_flatten_region(self, region_name: str):
        """Starts the process to edit an existing flatten region."""
        self._logger.critical(f"VM SLOT EDIT: Received Name='{region_name}' (Type: {type(region_name)})")
        if not self._selected_platform:
            self.status_message_changed.emit("No platform selected.", "ERROR")
            return

        self.status_message_changed.emit(f"Editing flatten region '{region_name}'...", "INFO")

        # Get current region data (optional, needed for coords only if UI doesn't provide)
        # get_result = self._region_service.get_region(self._selected_platform, "flatten", region_name)
        # if get_result.is_failure: # ... handle error ...

        # Select New Area
        region_result = self._ui_service.select_screen_region(
            f"Select the NEW area for the '{region_name}' flatten region"
        )
        if region_result.is_failure:
            self.status_message_changed.emit(f"Region edit failed: {region_result.error}", "ERROR")
            return
        if region_result.value is None:
            self.status_message_changed.emit("Region edit cancelled.", "INFO")
            return
        new_coordinates = region_result.value

        # Ask to recapture screenshot (Optional - could always recapture)
        recapture_result = self._ui_service.show_confirmation("Recapture Screenshot?",
                                                              "Capture a new screenshot for the updated region?")
        recapture = recapture_result.is_success and recapture_result.value

        # Create/Update Region Object
        region_id = f"{self._selected_platform}_flatten_{region_name}"
        region = Region(id=region_id, name=region_name, coordinates=new_coordinates,
                        type="flatten", platform=self._selected_platform)

        if recapture:
            capture_result = self._region_service.capture_region_screenshot(
                new_coordinates, region.id, region.platform, region.type
            )
            if capture_result.is_success:
                setattr(region, '_temp_screenshot_data', capture_result.value[0])
            else:
                self.status_message_changed.emit(
                    f"Failed capture new screenshot for '{region_name}': {capture_result.error}", "WARNING")

        # Save updated region
        save_result = self._region_service.save_region(region)
        if save_result.is_failure:
            self.status_message_changed.emit(f"Failed save edited region '{region_name}': {save_result.error}", "ERROR")
            return

        self.status_message_changed.emit(f"Updated flatten region '{region_name}': {new_coordinates}", "SUCCESS")
        # Refresh the flatten list display
        self._load_flatten_regions(self._selected_platform)

    @Slot(str)  # Expects the region name
    def delete_flatten_region(self, region_name: str):
        """Deletes a specific flatten region."""
        self._logger.critical(f"VM SLOT DELETE: Received Name='{region_name}' (Type: {type(region_name)})")
        # <<< If the above log shows Name='False', the problem is BEFORE this method runs >>>

        if not self._selected_platform:
            self.status_message_changed.emit("No platform selected.", "ERROR");
            return

        confirm_result = self._ui_service.show_confirmation("Confirm Delete",
                                                            f"Delete the flatten region '{region_name}' for {self._selected_platform}?"
                                                            )
        self._logger.debug(
            f"Confirmation result: Value={confirm_result.unwrap_or(None)}, Success={confirm_result.is_success}")

        if confirm_result.is_failure or not confirm_result.value:  # Checks for error OR False value (cancel)
            self.status_message_changed.emit(f"Deletion of flatten region '{region_name}' cancelled.", "INFO")
            return

        # If confirmed
        self.status_message_changed.emit(f"Deleting flatten region '{region_name}'...", "INFO")

        # Capture arguments just before the single call
        arg_platform = self._selected_platform
        arg_type = "flatten"
        arg_name = region_name
        self._logger.critical(
            f"!!!! VERIFY ARGS !!!! Platform='{arg_platform}', Type='{arg_type}', Name='{arg_name}' (Type: {type(arg_name)})")

        # --- SINGLE CORRECT CALL ---
        delete_result = self._region_service.delete_region(arg_platform, arg_type, arg_name)
        # --- END SINGLE CORRECT CALL ---

        self._logger.debug(
            f"Service delete_region result: Success={delete_result.is_success}, Value={delete_result.unwrap_or(None)}, Error={delete_result.error if delete_result.is_failure else 'N/A'}")

        # Handle result (ignoring Validation errors like "Not Found")
        if delete_result.is_failure and delete_result.error.category != ErrorCategory.VALIDATION:
            self.status_message_changed.emit(f"Failed to delete flatten region '{region_name}': {delete_result.error}",
                                             "ERROR")
            # Decide if UI should refresh on failure - probably yes to show error state?
            # return # Optionally stop before refresh on failure
        elif delete_result.is_success and not delete_result.value:
            self.status_message_changed.emit(f"Flatten region '{region_name}' not found in configuration.", "WARNING")
        elif delete_result.is_success and delete_result.value:
            self.status_message_changed.emit(f"Deleted flatten region {region_name}", "SUCCESS")

        # Refresh the flatten list display
        self._load_flatten_regions(self._selected_platform)

    @Slot(str)  # Expects the region name
    def flash_flatten_region(self, region_name: str):
        """Flashes a specific flatten region."""
        if not self._selected_platform:
            self.status_message_changed.emit("No platform selected.", "ERROR")
            return

        # 1. Get Region Object
        region_result = self._region_service.get_region(self._selected_platform, "flatten", region_name)
        if region_result.is_failure or not region_result.value or not region_result.value.coordinates:
            self.status_message_changed.emit(f"Flatten region '{region_name}' not found or invalid.", "ERROR")
            return

        # 2. Extract Coordinates
        coords = region_result.value.coordinates

        # 3. Call flash_regions with a list containing the single tuple
        self.status_message_changed.emit(f"Flashing flatten region '{region_name}' for {self._selected_platform}...",
                                         "INFO")
        flash_result = self._flash_service.flash_regions([coords])  # Pass as a list
        if flash_result.is_failure:
            self.status_message_changed.emit(f"Failed to initiate flash for '{region_name}': {flash_result.error}",
                                             "ERROR")

    @Slot(str)
    def set_expected_value(self, value: str):
        self._expected_value = value.strip()

    @Slot()
    def start_calibration(self):
        # (Copy from OcrCalibrationViewModel)
        # Ensure it uses self._monitor_region_screenshot_path
        if self._is_calibrating: self._logger.warning("Calibration already in progress."); return
        if not self._monitor_region_screenshot_path:  # Check the unified path
            self.status_message_changed.emit("Monitor region screenshot not available for OCR calibration.", "ERROR")
            self._ui_service.show_message("Error", "P&L Monitor region screenshot is needed for calibration.", "error");
            return
        if not self._expected_value:
            self.status_message_changed.emit("Please enter the P&L value shown in the preview.", "ERROR")
            self._ui_service.show_message("Input Needed", "Enter the exact P&L value from the preview.", "warning");
            return
        self._is_calibrating = True;
        self._last_calibration_result = None
        self.calibration_in_progress_changed.emit(True);
        self.can_save_calibrated_profile_changed.emit(False);
        self.can_save_manual_edits_changed.emit(False)
        self.calibration_status_text_changed.emit(f"Calibrating for '{self._expected_value}'...", "busy");
        self.calibration_progress_changed.emit(0, "Starting...")
        worker = CalibrationWorker(self._monitor_region_screenshot_path, self._expected_value, self._ocr_service,
                                   self._ocr_analysis_service, self._logger)
        worker.set_on_completed(self._handle_calibration_completed);
        worker.set_on_error(self._handle_calibration_error)
        worker.set_on_progress(self.calibration_progress_changed.emit)
        task_id = f"ocr_calib_{uuid.uuid4()}";
        task_res = self._thread_service.execute_task_and_restore_result(task_id, worker)
        if task_res.is_failure: self._handle_calibration_error(f"Failed to start task: {task_res.error}")

    @Slot()
    def save_calibrated_profile(self):
        # (Copy from OcrCalibrationViewModel)
        # On success: self.visual_setup_profile_changed.emit(self._selected_platform)
        if not self._selected_platform or self._is_calibrating or not self._last_calibration_result or "ocr_profile" not in self._last_calibration_result:
            self.status_message_changed.emit("Cannot save: No platform, calibrating, or no valid result.", "ERROR");
            return
        calibrated_ocr_profile = self._last_calibration_result["ocr_profile"]
        if not isinstance(calibrated_ocr_profile, OcrProfile):
            self.status_message_changed.emit("Internal error: Invalid calibration result.", "ERROR");
            return
        default_patterns = self._ocr_analysis_service.get_default_patterns(self._selected_platform)
        profile_to_save = PlatformProfile(self._selected_platform, calibrated_ocr_profile, default_patterns)
        result = self._profile_service.save_profile(profile_to_save)
        if result.is_success:
            self.status_message_changed.emit(f"Calibrated OCR profile saved for {self._selected_platform}.", "SUCCESS")
            self._current_ocr_profile = calibrated_ocr_profile  # Update internal current
            self.visual_setup_profile_changed.emit(self._selected_platform)
            self.can_save_calibrated_profile_changed.emit(False)  # Saved, so disable this until next calibration
            self.can_save_manual_edits_changed.emit(True)  # Can still save manual edits to this
            self._load_ocr_profile_data(
                self._selected_platform)  # To refresh displayed patterns if they changed due to using defaults
        else:
            self.status_message_changed.emit(f"Failed to save profile: {result.error}", "ERROR")

    @Slot()
    def save_manual_ocr_edits(self):
        # (Copy from OcrCalibrationViewModel)
        # On success: self.visual_setup_profile_changed.emit(self._selected_platform)
        if not self._selected_platform or self._is_calibrating:
            self.status_message_changed.emit("Cannot save: No platform or calibrating.", "ERROR");
            return
        current_profile_res = self._profile_service.get_profile(self._selected_platform)
        existing_patterns = current_profile_res.value.numeric_patterns or {} if current_profile_res.is_success and current_profile_res.value else self._ocr_analysis_service.get_default_patterns(
            self._selected_platform)
        profile_to_save = PlatformProfile(self._selected_platform, self._current_ocr_profile, existing_patterns)
        save_result = self._profile_service.save_profile(profile_to_save)
        if save_result.is_success:
            self.status_message_changed.emit("OCR parameter edits saved.", "SUCCESS")
            self.visual_setup_profile_changed.emit(self._selected_platform)
        else:
            self.status_message_changed.emit(f"Failed to save OCR edits: {save_result.error}", "ERROR")

    @Slot()
    def reset_profile_to_default(self):
        # (Copy from OcrCalibrationViewModel)
        # On completion: self.visual_setup_profile_changed.emit(self._selected_platform)
        if not self._selected_platform: self.status_message_changed.emit("No platform selected.", "ERROR"); return
        default_ocr = self._profile_service._get_platform_default_ocr_profile(self._selected_platform)
        self._current_ocr_profile = default_ocr  # Set internal state to defaults
        # self._update_ocr_profile_ui_elements(default_ocr) # Update UI elements reflecting OCR params (called by refresh_ui_signals)
        self._last_calibration_result = None  # Clear any previous calibration result
        self.status_message_changed.emit("OCR parameters reset to default. Save to persist.", "INFO")
        self.visual_setup_profile_changed.emit(self._selected_platform)  # Indicate potential change
        self.refresh_ui_signals()  # Re-emit all signals to update UI

    @Slot(float)
    def set_scale_factor(self, value: float):
        if self._current_ocr_profile.scale_factor != value: self._current_ocr_profile.scale_factor = value; self.can_save_manual_edits_changed.emit(
            True)

    @Slot(int)
    def set_block_size(self, value: int):
        adj_val = max(3, value + 1 if value % 2 == 0 else value)
        if self._current_ocr_profile.threshold_block_size != adj_val: self._current_ocr_profile.threshold_block_size = adj_val; self.can_save_manual_edits_changed.emit(
            True); self.threshold_block_size_changed.emit(adj_val)  # Update UI if changed

    @Slot(int)
    def set_c_value(self, value: int):
        adj_val = max(0, value)
        if self._current_ocr_profile.threshold_c != adj_val: self._current_ocr_profile.threshold_c = adj_val; self.can_save_manual_edits_changed.emit(
            True)

    @Slot(int)
    def set_denoise_h(self, value: int):
        adj_val = max(0, value)  # Denoise can be 0
        if self._current_ocr_profile.denoise_h != adj_val: self._current_ocr_profile.denoise_h = adj_val; self.can_save_manual_edits_changed.emit(
            True)

    @Slot(str)
    def set_tesseract_config(self, value: str):
        val = value.strip()
        if self._current_ocr_profile.tesseract_config != val: self._current_ocr_profile.tesseract_config = val; self.can_save_manual_edits_changed.emit(
            True)

    @Slot(bool)
    def set_invert_colors(self, value: bool):
        if self._current_ocr_profile.invert_colors != value: self._current_ocr_profile.invert_colors = value; self.can_save_manual_edits_changed.emit(
            True)

    @Slot(object)  # result_data: Optional[Dict[str, Any]]
    def _handle_calibration_completed(self, result_data: Optional[Dict[str, Any]]):
        self._is_calibrating = False;
        self._last_calibration_result = result_data
        self.calibration_in_progress_changed.emit(False)
        if result_data and isinstance(result_data.get("ocr_profile"), OcrProfile):
            self._current_ocr_profile = result_data["ocr_profile"]
            # self._update_ocr_profile_ui_elements(self._current_ocr_profile) # Done by refresh_ui_signals
            match_val = result_data.get("matched_value", "N/A");
            diff = result_data.get("difference", 0)
            msg = f"Calibration successful! Detected: {match_val}" + (f" (Diff: ${diff:.2f})" if diff > 0.001 else "")
            self._calibration_status_text = msg;
            self._calibration_status_color = "green"
            self.status_message_changed.emit("Calibration successful. Review and save.", "SUCCESS")
            self.can_save_calibrated_profile_changed.emit(True)
        else:
            self._calibration_status_text = "Calibration failed or result invalid.";
            self._calibration_status_color = "red"
            self.status_message_changed.emit("Calibration failed.", "ERROR")
            self.can_save_calibrated_profile_changed.emit(False)
        self.calibration_status_text_changed.emit(self._calibration_status_text, self._calibration_status_color)
        self.refresh_ui_signals()  # Refresh all UI elements, including OCR params

    @Slot(str)
    def _handle_calibration_error(self, error_msg: str):
        self._is_calibrating = False;
        self._last_calibration_result = None
        self.calibration_in_progress_changed.emit(False)
        self._calibration_status_text = f"Calibration Error: {error_msg}";
        self._calibration_status_color = "red"
        self.calibration_status_text_changed.emit(self._calibration_status_text, self._calibration_status_color)
        self.status_message_changed.emit(f"Calibration failed: {error_msg}", "ERROR")
        self.can_save_calibrated_profile_changed.emit(False)
        # self.can_save_manual_edits_changed.emit(self._selected_platform is not None) # Keep this enabled

    # Slot for theme refresh (if needed by elements not auto-updating via QSS/changeEvent)
    @Slot()
    def on_theme_refresh_requested(self):
        self._logger.info(f"{self.__class__.__name__}: Theme refresh requested. Re-emitting UI signals.")
        self.refresh_ui_signals()