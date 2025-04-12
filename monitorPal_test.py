#!/usr/bin/env python3
"""
Comprehensive testing application for the Trading Monitor functionality.
...
"""

# ANALYSIS: Standard imports - these will be distributed between ViewModels and Views.
# Some imports are used only for UI (PySide6 related) and others for business logic.

import os
import re
import sys
import time
from typing import List, Dict, Any, Optional, Tuple
import traceback
import dataclasses
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
    QTextEdit, QMessageBox, QTabWidget, QLineEdit, QGroupBox, QComboBox,
    QListWidget, QListWidgetItem, QSplitter, QFormLayout, QSpinBox, QDoubleSpinBox, QCheckBox, QProgressBar,
    QInputDialog
)
from PySide6.QtGui import QPixmap, QTextCursor
from PySide6.QtCore import Qt, QEvent

from src.domain.common.result import Result
from src.domain.common.errors import DomainError, ErrorCategory, ErrorSeverity
from src.domain.models.monitoring_result import MonitoringResult
from src.domain.models.region_model import Region
from src.domain.services.i_flash_service import IFlashService

# Add the project root to the Python path so we can import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_background_task_service import IBackgroundTaskService, Worker
from src.domain.services.i_window_manager_service import IWindowManager
from src.domain.services.i_platform_detection_service import IPlatformDetectionService
from src.domain.services.i_screenshot_service import IScreenshotService
from src.domain.services.i_ocr_service import IOcrService
from src.domain.services.i_monitoring_service import IMonitoringService
from src.domain.services.i_cold_turkey_service import IColdTurkeyService
from src.domain.services.i_verification_service import IVerificationService
from src.domain.services.i_lockout_service import ILockoutService
from src.domain.services.i_ui_service import IUIService
from src.domain.services.i_config_repository_service import IConfigRepository
from src.domain.services.i_profile_service import IProfileService
from src.domain.services.i_ocr_analysis_service import IOcrAnalysisService
from src.domain.services.i_region_service import IRegionService
from src.domain.services.i_platform_selection_service import IPlatformSelectionService

from src.presentation.components.ui_components import LogDisplay, StyledButton, GroupHeader, ActionButton, \
    SecondaryButton, WarningButton, DangerButton
from src.presentation.components.platform_selector_toolbar import PlatformSelectorToolbar

from src.domain.models.platform_profile import PlatformProfile, OcrProfile


class RegionEntry(QWidget):
    """Widget for displaying a selected region with options to edit/delete."""

    def __init__(self, region_id: str, region: Tuple[int, int, int, int],
                 on_edit, on_delete, on_flash, parent=None):
        super().__init__(parent)
        self.region_id = region_id
        self.region = region
        self.on_edit = on_edit
        self.on_delete = on_delete
        self.on_flash = on_flash

        # Use a vertical layout for the whole entry
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # Top row with region info and buttons
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)

        # Region info
        x, y, w, h = region
        label = QLabel(f"{region_id}: ({x}, {y}, {w}, {h})")
        top_layout.addWidget(label, 1)

        # Add Flash Button
        flash_btn = StyledButton("Flash", max_width=60)  # Standard blue button
        # Connect to the new on_flash callback, passing the region_id (name)
        flash_btn.clicked.connect(lambda: self.on_flash(self.region_id))
        top_layout.addWidget(flash_btn)


        # Edit button
        edit_btn = StyledButton("Edit", max_width=60)  # Standard action with max_width
        edit_btn.clicked.connect(lambda: self.on_edit(self.region_id, self.region))
        top_layout.addWidget(edit_btn)

        # Delete button
        delete_btn = DangerButton("Delete", max_width=60)  # Danger button for deletion
        delete_btn.clicked.connect(lambda: self.on_delete(self.region_id))
        top_layout.addWidget(delete_btn)

        # Add top row to main layout
        main_layout.addLayout(top_layout)

        # Add screenshot preview label
        self.screenshot_label = QLabel("No preview available")
        self.screenshot_label.setAlignment(Qt.AlignCenter)
        self.screenshot_label.setStyleSheet("border: 1px solid #ddd;")
        self.screenshot_label.setMinimumHeight(80)
        self.screenshot_label.setMaximumHeight(120)

        main_layout.addWidget(self.screenshot_label)


# ANALYSIS: UI-related code - this handles thread-safe UI updates.
# MIGRATION: This belongs in the MonitoringView or should be replaced with proper
# ViewModel callbacks and Qt signals.
class _ThresholdExceededEvent(QEvent):
    """Custom event for threshold exceeded notification."""
    EVENT_TYPE = QEvent.Type(QEvent.registerEventType())

    def __init__(self, result):
        super().__init__(_ThresholdExceededEvent.EVENT_TYPE)
        self.result = result



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

        # For progress reporting - will be calculated
        self.total_attempts = 0
        self.current_attempt = 0

    def execute(self) -> Optional[Dict[str, Any]]:
        """Try different OCR parameters and patterns until expected value is found."""
        self.report_started()
        self.report_progress(0, "Starting calibration...")

        # =================== START: CORRECTED BLOCK ===================
        # Clean the expected value using the OCR Service's helper method
        expected_value_str = self.expected_value.strip()
        try:
            # Call the OCR service's cleaning method directly
            # Pass the raw string as both value_str and full_match for context
            # Note the call to self.ocr_service._clean_and_convert_value
            cleaned_value_float = self.ocr_service._clean_and_convert_value(
                value_str=expected_value_str,
                full_match=expected_value_str
            )

            if cleaned_value_float is None:
                 self.report_error(f"Invalid expected value entered: '{self.expected_value}' could not be cleaned to a number.")
                 return None

            target_value = cleaned_value_float # Use the float directly
            self.logger.info(f"Cleaned expected value: '{self.expected_value}' -> Target float: {target_value}")

        except Exception as e: # Catch potential errors during cleaning call
            self.report_error(f"Unexpected error processing expected value '{self.expected_value}': {e}")
            self.logger.error("Exception during expected value cleaning", exc_info=True)
            return None
        # =================== END: CORRECTED BLOCK ===================

        # Load the image
        try:
            import PIL.Image
            image = PIL.Image.open(self.image_path)
        except Exception as e:
            self.report_error(f"Failed to load image: {e}")
            return None

        # Phase 1: Get baseline OCR parameters
        self.report_progress(5, "Detecting baseline OCR parameters...")
        ocr_result = self.ocr_analysis_service.detect_optimal_ocr_parameters(self.image_path)
        if ocr_result.is_failure:
            self.report_error(f"Failed to detect baseline OCR parameters: {ocr_result.error}")
            return None
        base_profile = ocr_result.value
        self.logger.info(f"Baseline OCR profile detected: {base_profile}")

        # Phase 2: Generate OCR Profile Variations to Test
        profiles_to_try = self._generate_ocr_profile_variations(base_profile)
        self.logger.info(f"Generated {len(profiles_to_try)} OCR profile variations to test.")

        # Phase 3: Generate Robust Pattern Sets
        patterns_to_try = self._generate_pattern_variations()
        self.logger.info(f"Generated {len(patterns_to_try)} pattern set variations to test.")

        # Calculate total attempts for progress bar
        self.total_attempts = len(profiles_to_try) * len(patterns_to_try)
        if self.total_attempts == 0:
            self.report_error("No OCR profiles or pattern sets generated to test.")
            return None

        # Phase 4: Nested Loop Testing
        best_match_info = None
        min_difference = float('inf')
        self.current_attempt = 0

        for i, current_profile in enumerate(profiles_to_try):
            self.logger.debug(f"Testing OCR Profile {i+1}/{len(profiles_to_try)}: {current_profile}")
            image_copy = image.copy()
            extract_result = self.ocr_service.extract_text_with_profile(image_copy, current_profile)

            if extract_result.is_failure:
                self.logger.warning(f"OCR failed for profile {i+1}: {extract_result.error}")
                self.current_attempt += len(patterns_to_try)
                continue

            extracted_text = extract_result.value
            self.logger.debug(f"  Profile {i+1} Extracted text: '{extracted_text}'")

            if not extracted_text or not extracted_text.strip():
                 self.logger.debug("  Skipping pattern matching for empty/whitespace text.")
                 self.current_attempt += len(patterns_to_try)
                 continue

            for j, pattern_set in enumerate(patterns_to_try):
                self.current_attempt += 1
                progress_pct = int((self.current_attempt / self.total_attempts) * 90) + 5 if self.total_attempts > 0 else 5
                self.report_progress(progress_pct, f"Testing profile {i+1}, pattern set {j+1}...")

                if self.cancel_requested: self.report_error("Calibration cancelled"); return None

                # This call uses the OCR service, which internally uses the CORRECT cleaner now
                numeric_result = self.ocr_service.extract_numeric_values_with_patterns(extracted_text, pattern_set)

                if numeric_result.is_success and numeric_result.value:
                    extracted_values = numeric_result.value
                    self.logger.debug(f"    Pattern set {j+1} extracted: {extracted_values}")

                    for value in extracted_values:
                        difference = abs(value - target_value)
                        if difference < 0.001:
                            self.report_progress(100, f"Found exact match: {value}")
                            self.logger.info(f"Exact match found with profile {i+1} and pattern set {j+1}")
                            return { "ocr_profile": current_profile, "patterns": pattern_set, "extracted_text": extracted_text, "matched_value": value }
                        if difference < min_difference:
                             self.logger.debug(f"      New best match: {value} (Diff: {difference}, Prev Diff: {min_difference})")
                             min_difference = difference
                             best_match_info = { "ocr_profile": current_profile, "patterns": pattern_set, "extracted_text": extracted_text, "matched_value": value, "difference": difference }
                elif numeric_result.is_failure: self.logger.debug(f"    Pattern set {j+1} extraction failed: {numeric_result.error}")
                else: self.logger.debug(f"    Pattern set {j+1} extracted no values.")

        # Phase 5: No Exact Match Found - Return Best Attempt?
        if best_match_info and min_difference < 1.0:
            self.report_progress(95, f"Found close match: {best_match_info['matched_value']} (diff: {min_difference:.2f})")
            self.logger.info(f"Using closest match (difference {min_difference:.2f}) found with profile variation and pattern set.")
            return best_match_info
        elif best_match_info:
             self.logger.warning(f"Closest match found had difference {min_difference:.2f} (Tolerance: 1.0). Failing calibration.")

        self.report_error("Could not find matching OCR profile and pattern combination.")
        self.logger.error("Calibration failed: No suitable combination found after trying variations.")
        return None


    def _generate_pattern_variations(self) -> List[Dict[str, str]]:
        """Generate different pattern variations to try (NOW MORE ROBUST)."""
        variations = []
        # Define base patterns with flexibility
        base = {
            # Optional $ or §, digits/commas, optional . or ,, digits
            "dollar": r'[$§]?([\d,]+(?:[.,]\d+)?)', # Simplified: require decimal only if digits follow
            # Negative via parens, allow optional $ or § inside
            "negative": r'\((?:[$§]?)([\d,]+(?:[.,]\d+)?)\)',
            # Negative via dash/tilde/etc., allow optional $ or §
            "negative_dash": r'[-~–—]\s*[$§]?([\d,]+(?:[.,]\d+)?)', # Added optional space after sign
            # Regular number, allow leading sign, ensure not preceded by $ or §
            "regular": r'(?<![$§])([-~–—]?[\d,]+(?:[.,]\d+)?)'
        }

        # Add variations (e.g., individual patterns, combined patterns)
        # Individual attempts might be faster if only one format exists
        variations.append({"dollar": base["dollar"]})
        variations.append({"negative": base["negative"]})
        variations.append({"negative_dash": base["negative_dash"]})
        variations.append({"regular": base["regular"]})
        variations.append(base.copy()) # Add the combined set

        # Add platform-specific patterns if needed (can be refined)
        # Example: Detect platform based on expected value format? Or pass platform context?
        # if '@' in self.expected_value: # Simple heuristic
        #      base_ninja = base.copy()
        #      base_ninja["ninja_at"] = r'@\s*([-~–—]?[\d,]+(?:[.,]\d+)?)'
        #      variations.append(base_ninja)
        # if 'PNL' in self.expected_value:
        #     base_tv = base.copy()
        #     base_tv["pnl_label"] = r'PNL[:\s]+([-~–—]?[\d,]+(?:[.,]\d+)?)'
        #     variations.append(base_tv)

        return variations


    def _generate_ocr_profile_variations(self, base_profile: OcrProfile) -> List[OcrProfile]:
        """Generate a list of OCR profiles to try, based on the baseline."""
        # Use dataclasses.replace for easy modification
        variations = [base_profile] # Start with the baseline

        # --- Define ranges/options to try ---
        # Use sets to avoid duplicates easily
        scale_factors = {base_profile.scale_factor,
                         max(1.0, base_profile.scale_factor - 0.5),
                         base_profile.scale_factor + 0.5,
                         base_profile.scale_factor + 1.0}
        denoise_hs = {base_profile.denoise_h,
                      max(1, base_profile.denoise_h - 5), # Wider range
                      base_profile.denoise_h + 5}
        invert_options = {base_profile.invert_colors, not base_profile.invert_colors}

        # Thresholds: Try baseline and one/two alternatives +/- 4 or 2
        threshold_sets = {(base_profile.threshold_block_size, base_profile.threshold_c)}
        alt_block1 = base_profile.threshold_block_size + 4
        alt_block2 = base_profile.threshold_block_size - 4
        alt_c1 = base_profile.threshold_c + 2
        alt_c2 = base_profile.threshold_c - 2
        if alt_block1 % 2 != 0 and alt_block1 > 1: threshold_sets.add((alt_block1, base_profile.threshold_c))
        if alt_block2 % 2 != 0 and alt_block2 > 1: threshold_sets.add((alt_block2, base_profile.threshold_c))
        if alt_c1 >= 0: threshold_sets.add((base_profile.threshold_block_size, alt_c1))
        if alt_c2 >= 0: threshold_sets.add((base_profile.threshold_block_size, alt_c2))


        psm_options = {base_profile.tesseract_config} # Start with base config
        base_psm_match = re.search(r'--psm\s+(\d+)', base_profile.tesseract_config)
        base_psm = int(base_psm_match.group(1)) if base_psm_match else 6 # Default to 6 if not found

        # Add common alternatives if different from base
        for psm_val in [6, 7, 11, 13]:
            if psm_val != base_psm:
                psm_options.add(f"--oem 3 --psm {psm_val}")


        # --- Create combinations ---
        # Keep it relatively simple first: vary one parameter at a time from baseline
        generated_profiles = {base_profile} # Use set to avoid duplicates

        # Vary scale factor
        for sf in scale_factors:
            if sf != base_profile.scale_factor:
                generated_profiles.add(dataclasses.replace(base_profile, scale_factor=sf))

        # Vary denoise_h
        for dh in denoise_hs:
             if dh != base_profile.denoise_h:
                 generated_profiles.add(dataclasses.replace(base_profile, denoise_h=dh))

        # Vary invert_colors
        for inv in invert_options:
             if inv != base_profile.invert_colors:
                 generated_profiles.add(dataclasses.replace(base_profile, invert_colors=inv))

        # Vary threshold sets
        for block, c_val in threshold_sets:
             if block != base_profile.threshold_block_size or c_val != base_profile.threshold_c:
                  generated_profiles.add(dataclasses.replace(base_profile, threshold_block_size=block, threshold_c=c_val))

        # Vary PSM
        for psm_config in psm_options:
             if psm_config != base_profile.tesseract_config:
                 generated_profiles.add(dataclasses.replace(base_profile, tesseract_config=psm_config))

        # Optional: Combine Invert + one other change (can increase combinations significantly)
        # temp_profiles = set(generated_profiles) # Copy current
        # for prof in temp_profiles:
        #     if prof.invert_colors != (not base_profile.invert_colors): # If not already the inverted version
        #         generated_profiles.add(dataclasses.replace(prof, invert_colors=not base_profile.invert_colors))


        self.logger.info(f"Generated {len(generated_profiles)} unique OCR profile variations.")
        # Limit the number if it gets too large?
        # return list(generated_profiles)[:30] # Example limit
        return list(generated_profiles)

class TradingMonitorTestApp(QMainWindow):
    """Test application for the Trading Monitor functionality."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Trading Monitor Test App")
        self.resize(1000, 800)

        # Initialize dependency injection container and services
        self._initialize_services()

        # Setup UI
        self._setup_ui()

        # Initialize data
        self.is_monitoring = False

        # Populate platform list
        self._populate_platform_list()

        # Load settings
        self._load_settings()

        # Log startup message
        self.log_message("Application initialized. Select a tab to begin testing.", "INFO")
        self._ui_initialized = True  # Signal that UI setup is complete

    def _initialize_services(self):
        """Initialize all required services."""
        # Use the container from app.py
        self.container = get_container()

        # Resolve services we need
        self.logger = self.container.resolve(ILoggerService)
        self.config_repository = self.container.resolve(IConfigRepository)
        self.thread_service = self.container.resolve(IBackgroundTaskService)
        self.window_manager = self.container.resolve(IWindowManager)
        self.ui_service = self.container.resolve(IUIService)
        self.screenshot_service = self.container.resolve(IScreenshotService)
        self.ocr_service = self.container.resolve(IOcrService)
        self.platform_detection = self.container.resolve(IPlatformDetectionService)
        self.cold_turkey_service = self.container.resolve(IColdTurkeyService)
        self.verification_service = self.container.resolve(IVerificationService)
        self.lockout_service = self.container.resolve(ILockoutService)
        self.monitoring_service = self.container.resolve(IMonitoringService)
        self.profile_service = self.container.resolve(IProfileService)
        self.platform_selection_service = self.container.resolve(IPlatformSelectionService)
        self.region_service = self.container.resolve(IRegionService)
        self.ocr_analysis_service = self.container.resolve(IOcrAnalysisService)
        self.flash_service = self.container.resolve(IFlashService)

    def _setup_ui(self):
        """Set up the user interface."""
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        main_layout = QVBoxLayout(central_widget)

        # Create tab widget
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)


        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        # Create and add platform selector toolbar
        self.platform_toolbar = PlatformSelectorToolbar(self.platform_selection_service, self)
        self.addToolBar(self.platform_toolbar)
        self.platform_toolbar.platform_changed.connect(self._on_global_platform_changed)

        # Create tabs
        self._create_region_tab()
        self._create_verification_tab()
        self._create_lockout_tab()
        self._create_profile_tab()

        # Log area
        log_group = GroupHeader("Log")
        log_layout = QVBoxLayout(log_group)
        self.log_display = LogDisplay()
        log_layout.addWidget(self.log_display)

        main_layout.addWidget(log_group)
        # --- START: Connect signals for summary updates AFTER widgets are created ---
        if hasattr(self, 'monitor_region_combo'):
            self.monitor_region_combo.currentTextChanged.connect(self._update_summary_display)
        if hasattr(self, 'threshold_spin'):
            self.threshold_spin.valueChanged.connect(self._update_summary_display)
        if hasattr(self, 'duration_spin'):
            self.duration_spin.valueChanged.connect(self._update_summary_display)

    def _create_region_tab(self):
        """Create the region selection tab."""
        region_tab = QWidget()
        layout = QVBoxLayout(region_tab)

        # Top area (keep as is or modify if needed)
        top_layout = QHBoxLayout()
        detect_btn = StyledButton("Detect Platform")
        detect_btn.clicked.connect(self._on_detect_platform)
        top_layout.addWidget(detect_btn)
        top_layout.addStretch()
        layout.addLayout(top_layout)

        # Split the rest of the tab
        splitter = QSplitter(Qt.Horizontal)

        # --- START: Monitor Region Display Area ---
        monitor_widget = QWidget() # Renamed for clarity
        monitor_layout = QVBoxLayout(monitor_widget)
        # monitor_layout.setContentsMargins(0,0,0,0) # Keep if desired

        monitor_group = QGroupBox("P&L Monitoring Region") # Updated title
        m_layout = QVBoxLayout(monitor_group)

        # Labels to display info (replace the QListWidget)
        self.monitor_status_label = QLabel("Status: Not Defined")
        self.monitor_status_label.setStyleSheet("font-style: italic; color: grey;")
        m_layout.addWidget(self.monitor_status_label)

        self.monitor_coords_label = QLabel("Coordinates: N/A")
        m_layout.addWidget(self.monitor_coords_label)

        self.monitor_preview_label = QLabel("No Preview")
        self.monitor_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.monitor_preview_label.setStyleSheet("border: 1px solid #ddd; background-color: #f0f0f0;")
        self.monitor_preview_label.setMinimumSize(150, 80) # Give it some size
        self.monitor_preview_label.setMaximumHeight(120)
        m_layout.addWidget(self.monitor_preview_label)

        # Buttons Layout
        m_btn_layout = QHBoxLayout()
        self.define_monitor_btn = StyledButton("Define / Edit Region") # Changed text & name
        self.define_monitor_btn.clicked.connect(self._on_define_edit_monitor_region) # New handler
        m_btn_layout.addWidget(self.define_monitor_btn)

        self.delete_monitor_btn = DangerButton("Delete Region") # Changed text & name
        self.delete_monitor_btn.clicked.connect(self._on_delete_monitor_region) # New handler
        self.delete_monitor_btn.setEnabled(False) # Initially disabled
        m_btn_layout.addWidget(self.delete_monitor_btn)

        m_layout.addLayout(m_btn_layout)
        m_layout.addStretch() # Push content up

        monitor_layout.addWidget(monitor_group)
        # --- END: Monitor Region Display Area ---


        # Flatten regions (This part remains the same as before)
        flatten_widget = QWidget()
        flatten_layout = QVBoxLayout(flatten_widget)
        # flatten_layout.setContentsMargins(0,0,0,0) # Keep if desired

        flatten_group = QGroupBox("Flatten Position Regions")
        f_layout = QVBoxLayout(flatten_group)

        self.flatten_list = QListWidget() # Flatten list stays
        f_layout.addWidget(self.flatten_list)

        add_flatten_btn = StyledButton("Add Region") # Flatten button stays
        # Ensure this lambda uses 'flatten' explicitly
        add_flatten_btn.clicked.connect(lambda: self._on_add_flatten_region()) # Changed handler name for clarity
        f_layout.addWidget(add_flatten_btn)

        flatten_layout.addWidget(flatten_group)

        # Add both widgets to splitter
        splitter.addWidget(monitor_widget) # Use new widget name
        splitter.addWidget(flatten_widget)
        splitter.setSizes([500, 500]) # Adjust initial sizes if needed

        layout.addWidget(splitter, 1)
        self.tab_widget.addTab(region_tab, "Region Selection")

    def _create_verification_tab(self):
        """Create the Cold Turkey verification tab."""
        verify_tab = QWidget()
        layout = QVBoxLayout(verify_tab)

        # Path selection
        path_group = QGroupBox("Cold Turkey Blocker Path")
        path_layout = QHBoxLayout(path_group)

        self.ct_path_input = QLineEdit()
        self.ct_path_input.setReadOnly(True)
        self.ct_path_input.setPlaceholderText("Select Cold Turkey Blocker path...")
        path_layout.addWidget(self.ct_path_input, 1)

        browse_btn = SecondaryButton("Browse...")  # Secondary action for browsing
        browse_btn.clicked.connect(self._on_browse_ct_path)
        path_layout.addWidget(browse_btn)

        save_path_btn = ActionButton("Save Path")  # Action button for saving
        save_path_btn.clicked.connect(self._on_save_ct_path)
        path_layout.addWidget(save_path_btn)

        layout.addWidget(path_group)

        # Block configuration
        block_group = QGroupBox("Block Configuration")
        block_layout = QFormLayout(block_group)

        # Block name
        self.block_name_input = QLineEdit()
        self.block_name_input.setPlaceholderText("e.g., Trading")
        block_layout.addRow("Block Name:", self.block_name_input)

        # Verify button
        verify_btn = WarningButton("Verify Block Configuration")  # Warning for verification action
        verify_btn.clicked.connect(self._on_verify_block)
        block_layout.addRow("", verify_btn)

        layout.addWidget(block_group)

        # Verified blocks
        verified_group = QGroupBox("Verified Blocks")
        verified_layout = QVBoxLayout(verified_group)

        self.verified_list = QListWidget()
        verified_layout.addWidget(self.verified_list)

        # Refresh and clear buttons
        v_btn_layout = QHBoxLayout()

        refresh_btn = StyledButton("Refresh List")  # Standard action
        refresh_btn.clicked.connect(self._refresh_verified_blocks)
        v_btn_layout.addWidget(refresh_btn)

        clear_btn = DangerButton("Clear All")  # Danger button for destructive action
        clear_btn.clicked.connect(self._on_clear_verified_blocks)
        v_btn_layout.addWidget(clear_btn)

        verified_layout.addLayout(v_btn_layout)

        layout.addWidget(verified_group, 1)

        # Add to tabs
        self.tab_widget.addTab(verify_tab, "Cold Turkey Verification")

    def _create_lockout_tab(self):
        """Create the lockout testing tab."""
        lockout_tab = QWidget()
        layout = QVBoxLayout(lockout_tab)

        # Lockout settings
        settings_group = QGroupBox("Lockout Settings")
        settings_layout = QFormLayout(settings_group)

        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(-100000, 0) # Increased range maybe
        self.threshold_spin.setValue(-100)
        self.threshold_spin.setPrefix("$ ")
        self.threshold_spin.setDecimals(2)
        settings_layout.addRow("Stop Loss Threshold:", self.threshold_spin)

        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(1, 1440)  # Allow up to 24 hours
        self.duration_spin.setValue(15)
        self.duration_spin.setSuffix(" minutes")
        settings_layout.addRow("Lockout Duration:", self.duration_spin)

        layout.addWidget(settings_group)

        # Monitoring controls
        monitor_group = QGroupBox("Monitoring")
        monitor_layout = QVBoxLayout(monitor_group)

        # Start monitoring button
        self.start_monitor_btn = ActionButton("Start Monitoring")  # Action button for primary function
        self.start_monitor_btn.clicked.connect(self._on_start_monitoring)
        monitor_layout.addWidget(self.start_monitor_btn)

        # Stop monitoring button
        self.stop_monitor_btn = SecondaryButton("Stop Monitoring")
        self.stop_monitor_btn.clicked.connect(self._on_stop_monitoring)
        self.stop_monitor_btn.setEnabled(False)
        monitor_layout.addWidget(self.stop_monitor_btn)

        # Manually trigger lockout
        self.trigger_lockout_btn = WarningButton("Manually Trigger Lockout")
        self.trigger_lockout_btn.clicked.connect(self._on_trigger_lockout)
        monitor_layout.addWidget(self.trigger_lockout_btn)

        layout.addWidget(monitor_group)

        # Status display
        status_group = QGroupBox("Status")
        status_layout = QVBoxLayout(status_group)

        self.lockout_status = QTextEdit()
        self.lockout_status.setReadOnly(True)
        self.lockout_status.setPlaceholderText("Monitoring status will appear here")
        status_layout.addWidget(self.lockout_status)

        layout.addWidget(status_group, 1)

        # Add to tabs
        self.tab_widget.addTab(lockout_tab, "Lockout Testing")

    def _create_profile_tab(self):
        """Create the profile management tab with integrated auto-calibration."""
        profile_tab = QWidget()
        layout = QVBoxLayout(profile_tab)

        # 1. Calibration Source Section (Renamed & Added Preview Label)
        # --- RENAME GROUP & ADD PREVIEW ---
        source_group = QGroupBox("Calibration Preview (Monitor Region Screenshot)")  # Renamed Group
        source_layout = QVBoxLayout(source_group)

        # --- ADD THIS LABEL (Make sure this part is present) ---
        self.profile_preview_label = QLabel("Define Monitor Region with screenshot first.")
        self.profile_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.profile_preview_label.setStyleSheet("border: 1px solid #ccc; background-color: #f0f0f0; color: #555;")
        self.profile_preview_label.setMinimumSize(200, 100)  # Give it some initial size
        self.profile_preview_label.setMaximumHeight(150)  # Limit height
        source_layout.addWidget(self.profile_preview_label, alignment=Qt.AlignmentFlag.AlignCenter)  # Add the label

        # Info text below preview
        source_info_label = QLabel(
            "Calibration uses the screenshot saved for the defined "
            "'P&L Monitoring Region' (on the Region Selection tab)."
        )
        source_info_label.setWordWrap(True)
        source_layout.addWidget(source_info_label)

        layout.addWidget(source_group)


        # 2. Value Calibration Section
        value_group = QGroupBox("Value Calibration Input")  # Clearer title
        value_layout = QVBoxLayout(value_group)

        # Instructions
        instructions = QLabel(
            "Enter the exact P&L value (including signs like $, -, or parentheses) exactly as shown in the selected region's screenshot above:")
        instructions.setWordWrap(True)
        value_layout.addWidget(instructions)

        # Horizontal layout for input and button
        input_layout = QHBoxLayout()

        # Input field for expected value
        self.expected_value_input = QLineEdit()
        self.expected_value_input.setPlaceholderText(
            "e.g., -$123.45 or ($123.45) or 123.45 or @ -100.00")  # Added examples
        input_layout.addWidget(self.expected_value_input)

        # Calibrate button
        self.calibrate_btn = WarningButton("Calibrate OCR")  # Warning for calibration process
        self.calibrate_btn.clicked.connect(self._start_calibration)
        self.calibrate_btn.setEnabled(False)
        input_layout.addWidget(self.calibrate_btn)

        value_layout.addLayout(input_layout)

        # Progress and status area
        self.calibration_status = QLabel(
            "Select a region screenshot above and enter the value you see.")  # Updated text
        self.calibration_status.setStyleSheet("font-style: italic; color: #555;")  # Adjusted style
        value_layout.addWidget(self.calibration_status)

        self.calibration_progress = QProgressBar()
        self.calibration_progress.setVisible(False)  # Start hidden
        self.calibration_progress.setTextVisible(False)  # Hide percentage text
        value_layout.addWidget(self.calibration_progress)

        layout.addWidget(value_group)

        # 3. Advanced Settings Section (collapsible)
        advanced_layout = QHBoxLayout()
        advanced_layout.addStretch()

        self.advanced_settings_check = QCheckBox("Show Advanced OCR Settings")  # Updated text
        self.advanced_settings_check.toggled.connect(self._toggle_advanced_settings)
        advanced_layout.addWidget(self.advanced_settings_check)

        layout.addLayout(advanced_layout)

        self.profile_group = QGroupBox("Advanced OCR Profile Settings (Calibrated)")  # Updated title
        profile_layout = QFormLayout(self.profile_group)

        # OCR parameters
        self.scale_factor_spin = QDoubleSpinBox()
        self.scale_factor_spin.setRange(1.0, 5.0)
        self.scale_factor_spin.setSingleStep(0.1)
        self.scale_factor_spin.setDecimals(1)  # One decimal place often sufficient
        profile_layout.addRow("Scale Factor:", self.scale_factor_spin)

        self.block_size_spin = QSpinBox()
        self.block_size_spin.setRange(3, 31)  # Wider range maybe
        self.block_size_spin.setSingleStep(2)  # Must be odd
        profile_layout.addRow("Threshold Block Size:", self.block_size_spin)

        self.c_value_spin = QSpinBox()
        self.c_value_spin.setRange(0, 15)  # Wider range maybe
        profile_layout.addRow("Threshold C Value:", self.c_value_spin)

        self.denoise_h_spin = QSpinBox()
        self.denoise_h_spin.setRange(1, 30)
        profile_layout.addRow("Denoise Strength (h):", self.denoise_h_spin)  # Clarified label

        self.config_text = QLineEdit()
        # self.config_text.setText("--oem 3 --psm 6") # Remove default text, let calibration set it
        self.config_text.setPlaceholderText("e.g., --oem 3 --psm 7 (Auto-set by calibration)")
        profile_layout.addRow("Tesseract Config:", self.config_text)

        # Color inversion option
        self.invert_colors_check = QCheckBox(
            "Invert Colors (Needed for light text on dark background)")  # Clarified label
        profile_layout.addRow("", self.invert_colors_check)

        # Initially hide advanced settings
        self.profile_group.setVisible(False)
        layout.addWidget(self.profile_group)

        # 4. Detected Formats Section (Replaces old pattern display)
        self.pattern_group = QGroupBox("Detected Number Formats (Read-Only)")  # Updated title
        pattern_layout = QVBoxLayout(self.pattern_group)

        # Create and store checkboxes in a dictionary for easy access
        self.pattern_checkboxes = {}

        # Define the patterns and their user-friendly descriptions/examples
        # The keys MUST match the keys used in CalibrationWorker._generate_pattern_variations
        patterns_info = {
            "dollar": "Positive Currency ($123.45, $1,234.56)",
            "negative": "Negative in Parens ((123.45), ($1,234.56))",
            "negative_dash": "Negative with Dash (-123.45, -$1,234.56, ~123.45)",
            "regular": "Plain Numbers (123.45, -123.45, 1234)"
            # --- Add other platform-specific patterns here if needed ---
            # "ninja_at": "NinjaTrader '@' Prefix (@ -100.00)"
        }

        # Create checkboxes based on the defined patterns
        for key, description in patterns_info.items():
            checkbox = QCheckBox(description)
            checkbox.setEnabled(False)  # Make them read-only displays
            # Style to hide indicator unless checked (will be set in on_completed)
            checkbox.setStyleSheet("QCheckBox::indicator { width: 0px; }")
            self.pattern_checkboxes[key] = checkbox
            pattern_layout.addWidget(checkbox)

        # Initially hide the pattern group
        self.pattern_group.setVisible(False)
        layout.addWidget(self.pattern_group)

        # 5. Buttons for saving/resetting
        button_layout = QHBoxLayout()
        self.save_profile_button = ActionButton("Save Calibrated Profile")  # Action for saving
        self.save_profile_button.clicked.connect(self._save_calibrated_profile)
        self.save_profile_button.setEnabled(False)
        button_layout.addWidget(self.save_profile_button)

        self.reset_profile_button = WarningButton("Reset Profile to Default")  # Warning for reset action
        self.reset_profile_button.clicked.connect(self._reset_platform_profile)
        button_layout.addWidget(self.reset_profile_button)

        layout.addLayout(button_layout)

        # Add the finished tab to the main tab widget
        self.tab_widget.addTab(profile_tab, "Profile Management")

    def _populate_platform_list(self):
        """Populate the global platform dropdown."""
        current_platform = self.platform_selection_service.get_current_platform()
        try:
            # Get supported platforms from platform detection service
            result = self.platform_detection.get_supported_platforms() # result is a Result[Dict[str, Any]]

            platforms = Result.handle_ui_result(
                result=result,                     # The Result object itself
                logger=self.logger,                # The logger instance
                ui_feedback_func=self.log_message, # The UI logging function
                success_message=None,              # No message needed on success here
                error_message="Failed to get platform list", # Custom error message
                context="Platform Populate",       # Optional context for logs
            )
            if platforms:
                self.platform_toolbar.update_platforms(list(platforms.keys()), current_platform)

        except Exception as e:
            # Catch any unexpected exceptions during the process
            self.log_message(f"Unexpected error populating platform list: {str(e)}", "ERROR")
            self.logger.error(f"Unexpected error populating platform list: {e}", exc_info=True)

    def _load_settings(self):
        """Load settings from config repository."""
        try:
            # Load Cold Turkey path
            ct_path = self.config_repository.get_cold_turkey_path()
            self.ct_path_input.setText(ct_path if ct_path else "")

            # Load global settings
            threshold = self.config_repository.get_stop_loss_threshold()
            duration = self.config_repository.get_lockout_duration()

            # Copy to lockout tab
            self.threshold_spin.setValue(threshold if threshold < 0 else -threshold)
            self.duration_spin.setValue(duration)

            # Load current platform
            current = self.config_repository.get_current_platform()
            if current:
                # Update toolbar with current platform
                platforms_result = self.platform_detection.get_supported_platforms()
                if platforms_result.is_success:
                    self.platform_toolbar.update_platforms(
                        list(platforms_result.value.keys()),
                        current
                    )
                else:
                    self.log_message(f"Failed to get platforms: {platforms_result.error}", "WARNING")

            # Refresh verified blocks
            self._refresh_verified_blocks()

            # --- START: Update region loading ---
            # Load platform-specific regions
            self._update_monitor_region_display()  # Update monitor display
            self._load_flatten_region_list()  # Load flatten list
            # --- END: Update region loading ---

            # Update summary display AFTER loading all settings and regions
            self._update_summary_display()

            self.log_message("Settings loaded successfully", "INFO")
        except Exception as e:
            self.log_message(f"Error loading settings: {str(e)}", "ERROR")
            self.logger.error(f"Error loading settings: {e}", exc_info=True)
            self._update_monitor_region_display()
            self._load_flatten_region_list()
            self._update_summary_display()

    def _load_platform_profile(self, platform=None):
        """Load and display profile for the selected platform."""
        if not platform:
            platform = self.platform_selection_service.get_current_platform()

        if not platform:
            return

        try:
            self.log_message(f"Loading profile for {platform}...", "INFO")

            # Use static handler for cleaner code
            Result.handle_ui_result(
                result=self.profile_service.get_profile(platform),
                logger=self.logger,
                ui_feedback_func=self.log_message,
                success_message=f"Profile loaded for {platform}",
                error_message=f"Failed to load profile for {platform}",
                context="Profile loading",
                on_success=self._update_profile_ui
            )
        except Exception as e:
            self.log_message(f"Error loading profile: {str(e)}", "ERROR")
            self.logger.error(f"Error loading profile: {e}", exc_info=True)

    def _update_profile_ui(self, profile):
        """Update UI with profile values."""
        # OCR profile
        ocr = profile.ocr_profile
        self.scale_factor_spin.setValue(ocr.scale_factor)
        self.block_size_spin.setValue(ocr.threshold_block_size)
        self.c_value_spin.setValue(ocr.threshold_c)
        self.denoise_h_spin.setValue(ocr.denoise_h)
        self.config_text.setText(ocr.tesseract_config)
        self.invert_colors_check.setChecked(ocr.invert_colors)

        # enable/disable state of the 'Load Screenshot' button.
        self._update_profile_tab_calibration_source()

    def _save_platform_profile(self):
        """Save the current profile settings."""
        platform = self.platform_selection_service.get_current_platform()
        if not platform:
            self.log_message("No platform selected", "WARNING")
            return

        try:
            # Import models
            from src.domain.models.platform_profile import OcrProfile, PlatformProfile

            # Create OCR profile
            ocr = OcrProfile(
                scale_factor=self.scale_factor_spin.value(),
                threshold_block_size=self.block_size_spin.value(),
                threshold_c=self.c_value_spin.value(),
                denoise_h=self.denoise_h_spin.value(),
                tesseract_config=self.config_text.text(),
                invert_colors=self.invert_colors_check.isChecked()
            )

            # Get existing profile to preserve existing patterns
            profile_result = self.profile_service.get_profile(platform)
            if profile_result.is_success:
                existing_profile = profile_result.value
                patterns = existing_profile.numeric_patterns
            else:
                # Default patterns as fallback
                patterns = {
                    "dollar": r'\$([\d,]+\.?\d*)',
                    "negative": r'\((?:\$)?([\d,]+\.?\d*)\)',
                    "regular": r'(?<!\$)(-?[\d,]+\.?\d*)'
                }

            # Create profile object
            profile = PlatformProfile(
                platform_name=platform,
                ocr_profile=ocr,
                numeric_patterns=patterns
            )

            # Save profile
            result = self.profile_service.save_profile(profile)

            if result.is_success:
                self.log_message(f"Profile saved for {platform}", "SUCCESS")
            else:
                self.log_message(f"Failed to save profile: {result.error}", "ERROR")
        except Exception as e:
            self.log_message(f"Error saving profile: {str(e)}", "ERROR")
            self.logger.error(f"Error saving profile: {e}", exc_info=True)

    def _reset_platform_profile(self):
        """Reset profile to default values."""
        platform = self.platform_selection_service.get_current_platform()
        if not platform:
            self.log_message("No platform selected", "WARNING")
            return

        try:
            # Create a default profile
            result = self.profile_service.create_default_profile(platform)

            if result.is_success:
                self.log_message(f"Profile reset to defaults for {platform}", "SUCCESS")
                # Reload the profile
                self._load_platform_profile(platform)
            else:
                self.log_message(f"Failed to reset profile: {result.error}", "ERROR")
        except Exception as e:
            self.log_message(f"Error resetting profile: {str(e)}", "ERROR")
            self.logger.error(f"Error resetting profile: {e}", exc_info=True)

    def _refresh_verified_blocks(self):
        """Refresh the list of verified blocks."""
        try:
            self.verified_list.clear()

            # Use direct result handling
            Result.handle_ui_result(
                result=self.verification_service.get_verified_blocks(),
                logger=self.logger,
                ui_feedback_func=self.log_message,
                error_message="Failed to get verified blocks",
                context="Blocks refresh",
                on_success=self._update_verified_blocks_list
            )
        except Exception as e:
            self.log_message(f"Error refreshing verified blocks: {str(e)}", "ERROR")
            self.logger.error(f"Error refreshing verified blocks: {e}", exc_info=True)

    def _update_verified_blocks_list(self, blocks):
        """Update the verified blocks list with data."""
        if blocks:
            for block in blocks:
                platform = block.get("platform", "Unknown")
                block_name = block.get("block_name", "Unknown")
                item = QListWidgetItem(f"{platform}: {block_name}")
                self.verified_list.addItem(item)

            if not blocks:
                self.verified_list.addItem("No verified blocks found")

            self.log_message(f"Found {len(blocks)} verified blocks", "INFO")
        else:
            self.verified_list.addItem("No blocks found")

    def _on_global_platform_changed(self, platform: str) -> None:
        """Handle global platform change."""
        # Load regions for this platform
        self._update_monitor_region_display()
        self._load_flatten_region_list()

        # Load profile for new platform
        self._load_platform_profile(platform)

        # Update summary display after platform change
        self._update_summary_display()

        if hasattr(self, 'calibration_status'):
            self.calibration_status.setText("Select a region and enter the value you see")

        self.log_message(f"Selected platform: {platform}", "INFO")

    def _on_browse_ct_path(self):
        """Browse for Cold Turkey Blocker executable."""
        self.ui_service.select_file(
            "Select Cold Turkey Blocker Executable",
            "Executables (*.exe);;All Files (*)"
        ).on_success(
            lambda file_path: self._update_ct_path(file_path) if file_path else None
        )

    def _update_ct_path(self, file_path):
        """Update the CT path input field."""
        self.ct_path_input.setText(file_path)
        self.log_message(f"Selected Cold Turkey path: {file_path}", "INFO")

    def _on_save_ct_path(self):
        """Save the Cold Turkey Blocker path."""
        path = self.ct_path_input.text()

        # Validate the path using our new method
        validation = self._validate_input(path, "Cold Turkey path")
        if validation.is_failure:
            self.log_message(f"Validation error: {validation.error}", "WARNING")
            return

        self.cold_turkey_service.set_blocker_path(path).with_ui_feedback(
            ui_feedback_func=self.log_message,
            success_message="Cold Turkey path saved successfully",
            error_message="Failed to save path"
        )

    def _on_detect_platform(self):
        """Detect platform in background thread but keep activation on UI thread."""
        platform = self.platform_selection_service.get_current_platform()
        if not platform:
            self.log_message("No platform selected", "WARNING")
            return

        # Quick check first (this is fast, so UI thread is fine)
        running_result = self.platform_detection.is_platform_running(platform)
        if running_result.is_failure or not running_result.value:
            self.log_message(f"{platform} is not running", "WARNING")
            QMessageBox.information(self, "Platform Not Running", f"Please start {platform} first.")
            return

        # Create detection worker for background processing
        class DetectionWorker(Worker[Dict[str, Any]]):
            def __init__(self, platform_detection, platform, logger):
                super().__init__()
                self.platform_detection = platform_detection
                self.platform = platform
                self.logger = logger

            def execute(self):
                try:
                    self.report_started()
                    result = self.platform_detection.detect_platform_window(self.platform, timeout=5)
                    if result.is_success:
                        return result.value
                    else:
                        self.report_error(str(result.error))
                        return None
                except Exception as e:
                    self.report_error(f"Error in detection: {e}")
                    return None

        # Set up worker callback that brings information back but DOESN'T ACTIVATE
        def on_detection_complete(window_info):
            if window_info:
                self.log_message(f"Successfully detected {platform} window", "SUCCESS")
                self.log_message(f"    Title: {window_info.get('title')}", "INFO")

                # Store detection result, show dialog, then use a direct method call
                # to handle activation on the UI thread
                response = QMessageBox.question(self, "Activate?",
                                                f"Do you want to bring {platform} to the foreground?",
                                                QMessageBox.Yes | QMessageBox.No)

                if response == QMessageBox.Yes:
                    # This is a direct method call on the UI thread - not a callback!
                    self._do_platform_activation(platform)

        # Run detection in background
        worker = DetectionWorker(self.platform_detection, platform, self.logger)
        worker.set_on_completed(on_detection_complete)

        result = self.thread_service.execute_task_and_restore_result(f"detect_{platform}", worker)
        if result.is_failure:
            self.log_message(f"Error starting detection: {result.error}", "ERROR")

    def _do_platform_activation(self, platform):
        """Method that runs on UI thread to activate windows safely."""
        self.log_message(f"Activating {platform} windows...", "INFO")
        result = self.platform_detection.activate_platform_windows(platform)

        if result.is_success:
            self.log_message(f"Successfully activated {platform} windows", "SUCCESS")
        else:
            self.log_message(f"Activation issue: {result.error}", "WARNING")

    def _on_define_edit_monitor_region(self):
        """Handles defining or editing the single monitor region."""
        region_type = "monitor"
        region_name = "monitor" # Use a fixed, standard name

        current_platform = self.platform_selection_service.get_current_platform()
        if not current_platform:
            self.log_message("No platform selected.", "ERROR")
            QMessageBox.warning(self, "Platform Needed", "Please select a platform first.")
            return

        # Check if editing or defining anew
        existing_region_result = self.region_service.get_monitor_region(current_platform)
        is_editing = existing_region_result.is_success and existing_region_result.value is not None

        action_text = "editing" if is_editing else "defining"
        self.log_message(f"Starting region selection for {action_text} the {region_type} region...", "INFO")

        # Use region selector UI
        region_result = self.ui_service.select_screen_region(f"Please select the P&L Monitoring region")
        if region_result.is_failure or region_result.value is None:
            self.log_message(f"Region selection cancelled or failed: {region_result.error}", "INFO")
            return
        coordinates = region_result.value

        # Create the Region object
        region_id = f"{current_platform}_{region_type}_{region_name}"
        region = Region(
            id=region_id,
            name=region_name,
            coordinates=coordinates,
            type=region_type,
            platform=current_platform,
            # Screenshot path will be handled by capture/save logic
        )

        # --- Capture Screenshot Data ---
        # This returns Result[Tuple[ImageData, IntendedPath]]
        capture_result = self.region_service.capture_region_screenshot(
            coordinates, region.id, region.platform, region.type
        )

        if capture_result.is_success:
            image_data, _ = capture_result.value # Don't need intended path here
            # Attach image data to temporary attribute for save_region
            setattr(region, '_temp_screenshot_data', image_data)
            self.log_message(f"Captured screenshot data for region '{region.name}'.", "INFO")
        elif capture_result.is_failure:
            self.log_message(f"Failed to capture screenshot for region '{region.name}': {capture_result.error}", "WARNING")
            QMessageBox.warning(self, "Screenshot Failed", "Could not capture screenshot. Region will be saved without an image preview.")
            # Keep existing path if editing and capture fails? Or clear it? Let's clear it for simplicity.
            if hasattr(region, '_temp_screenshot_data'): delattr(region, '_temp_screenshot_data')


        # --- Save the Region (Repository handles overwriting monitor region) ---
        save_result = self.region_service.save_region(region)

        if save_result.is_failure:
            self.log_message(f"Failed to save monitor region: {save_result.error}", "ERROR")
            QMessageBox.critical(self, "Error Saving Region", f"Failed to save monitor region.\nError: {save_result.error}")
            return

        self.log_message(f"Successfully defined/updated monitor region: {coordinates}", "SUCCESS")

        # --- Refresh the display ---
        self._update_monitor_region_display() # New method to update labels/preview
        self._refresh_ui_after_region_change() # Update other dependent UI parts

    def _on_add_flatten_region(self):
        """Handles adding a new flatten region."""
        region_type = "flatten"
        current_platform = self.platform_selection_service.get_current_platform()
        if not current_platform:
            self.log_message("No platform selected.", "ERROR")
            QMessageBox.warning(self, "Platform Needed", "Please select a platform first.")
            return

        # Get existing flatten regions to suggest default name
        flatten_regions_result = self.region_service.get_regions_by_platform(current_platform, region_type)
        count = len(flatten_regions_result.value) if flatten_regions_result.is_success else 0
        default_name = f"Flatten_{count + 1}"

        self.log_message(f"Starting region selection for adding a {region_type} region...", "INFO")

        # Select Area
        region_result = self.ui_service.select_screen_region(f"Please select the Flatten Position button region")
        if region_result.is_failure or region_result.value is None:
            self.log_message(f"Region selection cancelled or failed: {region_result.error}", "INFO")
            return
        coordinates = region_result.value

        # Get Name (Loop until valid name or cancel)
        while True:
            name, ok = QInputDialog.getText(self, f"Name this {region_type} region",
                                            "Enter a descriptive name:", QLineEdit.Normal, default_name)
            if not ok: self.log_message("Region naming cancelled", "INFO"); return
            name = name.strip()
            if not name: QMessageBox.warning(self, "Invalid Name", "Name cannot be empty."); continue

            # Check if flatten region with this name already exists
            existing_check = self.region_service.get_region(current_platform, region_type, name)
            if existing_check.is_success:
                 choice = QMessageBox.question(self, "Name Exists", f"Flatten region '{name}' already exists. Replace?",
                                               QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                 if choice != QMessageBox.Yes: continue # Ask again
                 # User chose Yes - proceed (save will overwrite)
                 break
            elif existing_check.error.category == ErrorCategory.VALIDATION: # Assuming "Not Found" is a validation error
                 # Name is unique
                 break
            else:
                 # Some other error fetching region
                 self.log_message(f"Error checking region name '{name}': {existing_check.error}", "ERROR")
                 QMessageBox.critical(self, "Error", f"Could not verify region name '{name}'.")
                 return # Abort

        # Create Region Object
        region_id = f"{current_platform}_{region_type}_{name}"
        region = Region(id=region_id, name=name, coordinates=coordinates, type=region_type, platform=current_platform)

        # Capture Screenshot
        capture_result = self.region_service.capture_region_screenshot(coordinates, region.id, region.platform, region.type)
        if capture_result.is_success:
            setattr(region, '_temp_screenshot_data', capture_result.value[0])
        else:
            self.log_message(f"Failed to capture screenshot for flatten region '{name}': {capture_result.error}", "WARNING")
            # Proceed without screenshot

        # Save Region (repository adds/updates flatten region in dict)
        save_result = self.region_service.save_region(region)
        if save_result.is_failure:
            self.log_message(f"Failed to save flatten region '{name}': {save_result.error}", "ERROR")
            QMessageBox.critical(self, "Error Saving Region", f"Failed to save flatten region '{name}'.\nError: {save_result.error}")
            return

        # --- Refresh the flatten list (Need to add this specific logic back) ---
        self._load_flatten_region_list() # We need a method to specifically reload/update the flatten QListWidget
        # --- End Refresh ---

        self.log_message(f"Added flatten region '{name}': {coordinates}", "SUCCESS")
        self._refresh_ui_after_region_change() # Update other parts if needed

    def _on_edit_flatten_region(self, region_name: str, current_coords: tuple):
        """Edit an existing flatten region."""
        region_type = "flatten"
        current_platform = self.platform_selection_service.get_current_platform()
        if not current_platform:
            self.log_message("Cannot edit region, no platform selected.", "ERROR")
            return

        self.log_message(f"Editing {region_type} region '{region_name}'...", "INFO")

        # --- Get existing region details (only needed if keeping old screenshot on failure) ---
        # get_result = self.region_service.get_region(current_platform, region_type, region_name)
        # if get_result.is_failure: # ... handle error ...
        # region_to_edit = get_result.value

        # --- Select new area ---
        region_result = self.ui_service.select_screen_region(
            f"Select the NEW area for the '{region_name}' flatten region")
        if region_result.is_failure or region_result.value is None:
            self.log_message(f"Region edit cancelled or failed: {region_result.error}", "INFO")
            return
        new_coordinates = region_result.value

        # --- Ask to recapture screenshot ---
        recapture = QMessageBox.question(self, "Recapture Screenshot?",
                                         "Capture a new screenshot for the updated region?",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)

        # --- Create/Update Region Object ---
        # Create a new object with updated coords, let save_region handle overwrite
        region_id = f"{current_platform}_{region_type}_{region_name}"
        region = Region(id=region_id, name=region_name, coordinates=new_coordinates,
                        type=region_type, platform=current_platform)

        if recapture == QMessageBox.Yes:
            capture_result = self.region_service.capture_region_screenshot(
                new_coordinates, region.id, region.platform, region.type
            )
            if capture_result.is_success:
                setattr(region, '_temp_screenshot_data', capture_result.value[0])
                self.log_message(f"Captured new screenshot data for edited region '{region_name}'.", "INFO")
            else:
                self.log_message(f"Failed capture new screenshot for edited '{region_name}': {capture_result.error}", "WARNING")
                QMessageBox.warning(self, "Screenshot Failed", "Could not capture new screenshot. Region metadata will be updated.")
                # Keep existing screenshot path? save_region logic needs to handle this if desired.
                # For simplicity, let's assume save_region clears path if no new data.

        # --- Save updated region ---
        save_result = self.region_service.save_region(region) # Repository overwrites based on name
        if save_result.is_failure:
            self.log_message(f"Failed to save edited flatten region '{region_name}': {save_result.error}", "ERROR")
            QMessageBox.critical(self, "Error Saving Region", f"Failed to save edited region '{region_name}'.\nError: {save_result.error}")
            return

        # --- Refresh the flatten list ---
        self._load_flatten_region_list() # Reload list to show updated coords/preview

        self.log_message(f"Updated flatten region '{region_name}': {new_coordinates}", "SUCCESS")
        self._refresh_ui_after_region_change()

    def _on_delete_monitor_region(self):
        """Deletes the single monitor region."""
        region_type = "monitor"
        region_name = "monitor" # Fixed name
        current_platform = self.platform_selection_service.get_current_platform()
        if not current_platform:
            self.log_message("Cannot delete region: No platform selected.", "ERROR"); return

        confirm = QMessageBox.question(self, "Confirm Delete",
                                       f"Delete the P&L Monitoring region for {current_platform}?",
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm != QMessageBox.Yes: return

        self.log_message(f"Deleting monitor region for {current_platform}...", "INFO")

        # Call service (Repository handles setting monitor_region to None)
        result = self.region_service.delete_region(current_platform, region_type, region_name)

        if result.is_failure and result.error.category != ErrorCategory.VALIDATION: # Ignore "Not Found" error
            self.log_message(f"Failed to delete monitor region: {result.error}", "ERROR")
            return
        elif result.is_success and not result.value: # Check if repo reported 'not found'
             self.log_message(f"Monitor region already not defined for {current_platform}.", "INFO")
             # Proceed to update display anyway to ensure consistency

        self.log_message(f"Deleted monitor region for {current_platform}", "SUCCESS")

        # Refresh the display area
        self._update_monitor_region_display()
        self._refresh_ui_after_region_change()

    def _on_delete_flatten_region(self, region_name: str):
        """Deletes a specific flatten region."""
        region_type = "flatten"
        current_platform = self.platform_selection_service.get_current_platform()
        if not current_platform:
             self.log_message("Cannot delete region: No platform selected.", "ERROR"); return

        confirm = QMessageBox.question(self, "Confirm Delete",
                                       f"Delete the flatten region '{region_name}' for {current_platform}?",
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm != QMessageBox.Yes: return

        self.log_message(f"Deleting flatten region '{region_name}'...", "INFO")

        # Call service (Repository removes from flatten_regions dict)
        result = self.region_service.delete_region(current_platform, region_type, region_name)

        if result.is_failure and result.error.category != ErrorCategory.VALIDATION: # Ignore "Not Found"
            self.log_message(f"Failed to delete flatten region '{region_name}': {result.error}", "ERROR")
            return

        # --- Refresh the flatten list ---
        self._load_flatten_region_list()

        self.log_message(f"Deleted flatten region {region_name}", "SUCCESS")
        self._refresh_ui_after_region_change()

    def _on_flash_region(self, region_name: str, region_type: str):
        """Handles the request to flash a specific region."""
        current_platform = self.platform_selection_service.get_current_platform()
        if not current_platform:
            self.log_message("Cannot flash region: No platform selected.", "ERROR")
            QMessageBox.warning(self, "Platform Needed", "No platform selected.")
            return

        self.log_message(f"Flashing '{region_name}' ({region_type}) for {current_platform}...", "INFO")

        # Call the flash service
        result = self.flash_service.flash_region(current_platform, region_type, region_name)

        # Log the outcome (flash_service logs details internally)
        if result.is_failure:
            self.log_message(f"Failed to initiate flash for '{region_name}': {result.error}", "ERROR")
            # Optionally show a QMessageBox error here too
            # QMessageBox.critical(self, "Flash Error", f"Could not flash region '{region_name}':\n{result.error}")
        else:
            # Success means the *task started*, not necessarily finished flashing
            self.log_message(f"Flash sequence initiated for '{region_name}'.", "SUCCESS")

    def _on_verify_block(self):
        """Verify the Cold Turkey block configuration."""
        platform = self.platform_selection_service.get_current_platform()
        block_name = self.block_name_input.text()

        if not platform:
            self.log_message("No platform selected", "WARNING")
            return

        if not block_name:
            self.log_message("No block name specified", "WARNING")
            return

        self.log_message(f"Starting verification of block '{block_name}' for platform '{platform}'...", "INFO")

        # Check if Cold Turkey path is configured
        if not self.verification_service.is_blocker_path_configured():
            self.log_message("Cold Turkey Blocker path not configured", "ERROR")
            return

        # Run verification with proper boolean result handling
        self.verification_service.verify_platform_block(
            platform=platform,
            block_name=block_name,
            cancellable=False
        ).on_success(
            # This function receives the boolean value indicating if verification worked
            lambda verification_succeeded:
            # If verification truly succeeded (the boolean is True)
            self._handle_successful_verification(block_name)
            if verification_succeeded else
            # If Result is success but verification didn't work (boolean is False)
            self.log_message("Verification completed but did not succeed.", "WARNING")
        ).on_failure(
            # Handle case where Result itself failed (error occurred)
            lambda error: self.log_message(f"Verification failed: {error}", "ERROR")
        )

    def _handle_successful_verification(self, block_name):
        """Handle a successful verification."""
        self.log_message(f"Verification successful! Block '{block_name}' is correctly configured.", "SUCCESS")
        self._refresh_verified_blocks()

    def _on_clear_verified_blocks(self):
        """Clear all verified blocks."""
        confirm = QMessageBox.question(
            self,
            "Confirm Clear",
            "Are you sure you want to clear all verified blocks?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if confirm == QMessageBox.Yes:
            self.verification_service.clear_verified_blocks().with_ui_feedback(
                ui_feedback_func=self.log_message,
                success_message="All verified blocks cleared",
                error_message="Failed to clear verified blocks"
            ).on_success(
                lambda _: self._refresh_verified_blocks()
            )

    def _on_start_monitoring(self):
        """Handles the click of the 'Start Monitoring' button."""
        current_platform = self.platform_selection_service.get_current_platform()
        if not current_platform:
            self.log_message("No platform selected.", "ERROR")
            QMessageBox.warning(self, "Platform Needed", "Please select a platform first.")
            return

        threshold = self.threshold_spin.value()
        # Ensure threshold is negative (can be done here or let service handle it)
        if threshold > 0:
            threshold = -threshold

        # --- START: Check platform is running ---
        platform_running_result = self.platform_detection.is_platform_running(current_platform)
        if platform_running_result.is_failure or not platform_running_result.value:
            msg = f"{current_platform} is not running. Please start it first."
            self.log_message(msg, "ERROR")
            QMessageBox.warning(self, "Platform Not Running", msg)
            return

        self.log_message(f"Checking for defined monitor region for {current_platform}...", "DEBUG")
        region_result = self.region_service.get_monitor_region(current_platform) # Use the correct service method

        if region_result.is_failure:
            # Error fetching region info (config issue, etc.)
            self.log_message(f"Failed to check for monitor region: {region_result.error}", "ERROR")
            QMessageBox.critical(self, "Region Error", f"Could not retrieve monitor region information:\n{region_result.error}")
            return

        monitor_region = region_result.value # This is the Region object or None

        if monitor_region is None:
            # Monitor region is simply not defined yet
            msg = f"Monitor region not defined for {current_platform}. Please define it on the 'Region Selection' tab."
            self.log_message(msg, "ERROR")
            QMessageBox.warning(self, "Region Not Defined", msg)
            return

        self.log_message(f"Requesting start monitoring for {current_platform} with threshold {threshold}", "INFO")

        # Define callbacks needed by the service
        def on_status_update(message, level):
            # Ensure UI updates happen safely if needed (log_message should be safe)
            self.log_message(message, level)
            # Append to status display if it exists
            if hasattr(self, 'lockout_status'):
                self.lockout_status.append(f"[{level}] {message}")

        def on_threshold_exceeded(result: MonitoringResult):
            # This callback might be called from a background thread by MonitoringService
            self.log_message("Threshold exceeded (reported by service)!", "ERROR")
            self.log_message(f"Detected value: ${result.minimum_value:.2f}", "ERROR") # Use result object
            # Stop monitoring service (this method should be thread-safe)
            stop_res = self.monitoring_service.stop_monitoring()
            if stop_res.is_failure:
                 self.log_message(f"Error stopping monitoring after threshold: {stop_res.error}", "ERROR")
            # Post event to UI thread for UI updates and lockout trigger
            QApplication.instance().postEvent(self, _ThresholdExceededEvent(result))

        def on_error(msg):
            # This callback might be called from a background thread
            self.log_message(f"Monitoring Service Error: {msg}", "ERROR")
            # Safely update UI state if needed (e.g., via signal or QTimer.singleShot)
            # For now, just log. Button state will update via _ThresholdExceededEvent or manual stop.


        # Call the updated service method (only platform & threshold needed now)
        start_result = self.monitoring_service.start_monitoring(
            platform=current_platform,
            threshold=threshold,
            # interval_seconds=2.0, # Pass interval if needed by service
            on_status_update=on_status_update,
            on_threshold_exceeded=on_threshold_exceeded,
            on_error=on_error
        )

        # Update UI button states based on whether starting the service task succeeded
        if start_result.is_success:
             self._update_monitoring_ui_state(True) # Update button states using existing helper
             self.log_message("Monitoring service start requested successfully.", "SUCCESS")
        else:
             self.log_message(f"Failed to start monitoring service: {start_result.error}", "ERROR")
             self._update_monitoring_ui_state(False) # Ensure button states are correct

    def _update_monitoring_ui_state(self, is_active):
        """Update UI state based on monitoring activity."""
        self.is_monitoring = is_active
        self.start_monitor_btn.setEnabled(not is_active)
        self.stop_monitor_btn.setEnabled(is_active)

    def _on_stop_monitoring(self):
        """Stop monitoring for P&L losses."""
        if not self.is_monitoring:
            self.log_message("No active monitoring to stop", "WARNING")
            return

        try:
            self.monitoring_service.stop_monitoring().with_ui_feedback(
                ui_feedback_func=self.log_message,
                success_message="Monitoring stopped",
                error_message="Failed to stop monitoring"
            ).handle_ui_state(
                success_state_updater=lambda: self._update_monitoring_ui_state(False),
                failure_state_updater=lambda: self._update_monitoring_ui_state(False)
                # Always update UI state even on failure
            )
        except Exception as e:
            self.log_message(f"Error stopping monitoring: {str(e)}", "ERROR")
            self.logger.error(f"Error stopping monitoring: {e}", exc_info=True)
            self._update_monitoring_ui_state(False)  # Ensure UI consistency

    def _on_trigger_lockout(self, automatic=False):
        """Manually trigger the lockout sequence."""
        platform = self.platform_selection_service.get_current_platform()
        duration = self.duration_spin.value()

        # Pass the automatic flag through
        self.region_service.get_regions_by_platform(platform, "flatten").with_ui_feedback(
            ui_feedback_func=self.log_message,
            error_message="Failed to get flatten regions",
            context="Lockout preparation"
        ).on_success(lambda regions: self._prepare_lockout(platform, regions, duration, automatic))

    def _prepare_lockout(self, platform, flatten_regions, duration, automatic=False):
        """Prepare lockout with retrieved flatten regions."""
        if not flatten_regions:
            self.log_message("No flatten regions defined", "ERROR")
            return

        # Convert flatten regions to the format expected by lockout service
        flatten_positions = []
        for region in flatten_regions:
            x, y, width, height = region.coordinates
            flatten_positions.append({"coords": (x, y, x + width, y + height)})

        self.log_message(f"Triggering lockout for {platform}...", "INFO")
        self.log_message(f"Duration: {duration} minutes", "INFO")
        self.log_message(f"Flatten positions: {len(flatten_positions)}", "INFO")

        # Skip confirmation for automatic lockouts
        if not automatic:
            confirm = QMessageBox.question(
                self,
                "Confirm Lockout",
                f"Are you sure you want to trigger a {duration}-minute lockout for {platform}?\n\n"
                "This will create an overlay with clickable regions for flattening positions "
                "and then activate Cold Turkey Blocker.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if confirm != QMessageBox.Yes:
                self.log_message("Lockout cancelled by user", "INFO")
                return

        # Prepare callback
        def on_status_update(message, level):
            self.log_message(message, level)
            self.lockout_status.append(f"[{level}] {message}")

        # Execute lockout
        self.lockout_service.perform_lockout(
            platform=platform,
            flatten_positions=flatten_positions,
            lockout_duration=duration,
            on_status_update=on_status_update,
            fullscreen = True  # New parameter
        ).with_ui_feedback(
            ui_feedback_func=self.log_message,
            success_message="Lockout sequence initiated",
            error_message="Failed to initiate lockout"
        )

    def log_message(self, message, level="INFO"):
        """Log a message to both the UI and the logger."""
        # Map level to logger method
        level_map = {
            "INFO": self.logger.info,
            "SUCCESS": self.logger.info,  # Success is not a standard logging level
            "WARNING": self.logger.warning,
            "ERROR": self.logger.error,
            "DEBUG": self.logger.debug
        }

        try:
            # Log to logger
            log_func = level_map.get(level.upper(), self.logger.info)
            log_func(message)

            # Log to UI (only if the UI has been initialized)
            if hasattr(self, 'log_display') and self.log_display:
                # Ensure UI updates happen in the main thread
                self.log_display.append_message(message, level)
        except Exception as e:
            print(f"Error logging message: {e}")
            traceback.print_exc()

    def closeEvent(self, event):
        try:
            # Stop monitoring if active
            if self.is_monitoring:
                try:
                    self.monitoring_service.stop_monitoring()
                    self.log_message("Monitoring stopped on application exit", "INFO")
                except Exception as e:
                    self.logger.error(f"Error stopping monitoring on exit: {e}", exc_info=True)

            # No need to save regions - they're saved as they change

            # Cancel all background tasks
            self.thread_service.cancel_all_tasks()

            # Accept the close event
            event.accept()
        except Exception as e:
            self.logger.error(f"Error during application shutdown: {e}", exc_info=True)
            event.accept()  # Still close even if there's an error

    def _toggle_advanced_settings(self, checked):
        """Toggle visibility of advanced settings."""
        self.profile_group.setVisible(checked)

    def _refresh_ui_after_region_change(self):
        """Refresh all UI components that depend on region data."""
        try:
            # Update monitor display (if defined) and flatten list
            self._update_monitor_region_display()
            self._load_flatten_region_list()
            self._update_profile_tab_calibration_source()  # New placeholder method needed
            # Update the main summary toolbar
            self._update_summary_display()
            # Allow UI to update
            QApplication.processEvents()
        except Exception as e:
            self.log_message(f"Error refreshing UI: {str(e)}", "ERROR")
            self.logger.error(f"Error in UI refresh: {e}", exc_info=True)

    def _on_tab_changed(self, index):
        """Handle tab changes by refreshing data as needed."""
        tab_name = self.tab_widget.tabText(index)
        # Refresh region tab displays if potentially stale
        if tab_name == "Region Selection":
             self._update_monitor_region_display()
             self._load_flatten_region_list()

        elif tab_name == "Profile Management":
             # Refresh calibration source info
             self._update_profile_tab_calibration_source()

    def _update_profile_tab_calibration_source(self):
        """
        Checks for the monitor region screenshot, updates the preview automatically,
        and enables/disables the Calibrate button. Stores path if found.
        """
        if not self._ui_initialized:
            self.log_message("UI not fully initialized, skipping profile tab source update.", "DEBUG")
            return

        # Reset state
        can_calibrate = False
        self.calibration_image_path = None
        preview_message = "Define Monitor Region\nwith Screenshot first."
        calibration_status_text = "Define Monitor Region with screenshot to enable calibration."
        preview_pixmap = QPixmap() # Empty pixmap

        current_platform = self.platform_selection_service.get_current_platform()
        if current_platform:
            region_result = self.region_service.get_monitor_region(current_platform)
            if region_result.is_success and region_result.value:
                monitor_region = region_result.value
                screenshot_path = monitor_region.screenshot_path

                if screenshot_path and os.path.exists(screenshot_path) and os.path.isfile(screenshot_path):
                    # Screenshot exists - attempt to load preview
                    self.log_message(f"Attempting to load calibration preview: {screenshot_path}", "DEBUG")
                    try:
                        temp_pixmap = QPixmap(screenshot_path)
                        if not temp_pixmap.isNull():
                             # Scale pixmap to fit the label
                             scaled_pixmap = temp_pixmap.scaled(
                                 self.profile_preview_label.width() - 10,
                                 self.profile_preview_label.height() - 10,
                                 Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation
                             )
                             preview_pixmap = scaled_pixmap # Use loaded pixmap
                             preview_message = "" # Clear text message if pixmap loaded
                             can_calibrate = True
                             self.calibration_image_path = screenshot_path # Store path for calibration worker
                             calibration_status_text = "Enter value shown above and click Calibrate."
                             self.log_message("Calibration preview loaded successfully.", "DEBUG")
                        else:
                             preview_message = "Error: Could not load\nscreenshot image."
                             self.log_message(f"Failed to load QPixmap (isNull): {screenshot_path}", "ERROR")
                    except Exception as e:
                         preview_message = "Error loading preview."
                         self.log_message(f"Exception loading calibration preview: {e}", "ERROR", exc_info=True)
                else:
                    # Region defined, but no screenshot
                    preview_message = "Monitor Region Defined\n(No Screenshot Found)"
                    self.log_message("Monitor region found, but screenshot path missing or invalid.", "WARNING")
            elif region_result.is_failure:
                 # Error fetching region
                 preview_message = "Error loading region data."
                 self.log_message(f"Failed to get monitor region for profile tab: {region_result.error}", "WARNING")
            # else: region_result was success but value was None (not defined) - keep default messages

        # --- Update UI Elements ---
        # Ensure widgets exist before updating
        if hasattr(self, 'profile_preview_label'):
             self.profile_preview_label.setText(preview_message)
             self.profile_preview_label.setPixmap(preview_pixmap)
        if hasattr(self, 'calibrate_btn'):
             self.calibrate_btn.setEnabled(can_calibrate)
        if hasattr(self, 'calibration_status'):
             self.calibration_status.setText(calibration_status_text)

    def _update_monitor_region_display(self):
        """Fetches the single monitor region and updates the UI display."""
        current_platform = self.platform_selection_service.get_current_platform()
        if not current_platform:
            # Reset display if no platform selected
            self.monitor_status_label.setText("Status: Select Platform")
            self.monitor_coords_label.setText("Coordinates: N/A")
            self.monitor_preview_label.setText("No Preview")
            self.monitor_preview_label.setPixmap(QPixmap())  # Clear image
            self.delete_monitor_btn.setEnabled(False)
            return

        result = self.region_service.get_monitor_region(current_platform)

        if result.is_success and result.value is not None:
            # Region is defined
            region = result.value
            x, y, w, h = region.coordinates
            self.monitor_status_label.setText("Status: Defined")
            self.monitor_status_label.setStyleSheet("font-style: normal; color: green;")
            self.monitor_coords_label.setText(f"Coordinates: ({x}, {y}, {w}, {h})")
            self.delete_monitor_btn.setEnabled(True)

            # Load and display preview
            if region.screenshot_path:
                load_result = self.region_service.load_region_screenshot(region)
                if load_result.is_success:
                    img_data = load_result.value
                    pixmap_result = self.screenshot_service.to_pyside_pixmap(img_data)
                    if pixmap_result.is_success:
                        pixmap = pixmap_result.value
                        # Scale pixmap to fit the label
                        scaled_pixmap = pixmap.scaled(
                            self.monitor_preview_label.width() - 6,
                            self.monitor_preview_label.height() - 6,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
                        self.monitor_preview_label.setPixmap(scaled_pixmap)
                    else:
                        self.monitor_preview_label.setText("Preview Load Failed"); self.monitor_preview_label.setPixmap(
                            QPixmap())
                else:
                    self.monitor_preview_label.setText("Preview Load Failed"); self.monitor_preview_label.setPixmap(
                        QPixmap())
            else:
                self.monitor_preview_label.setText("No Screenshot");
                self.monitor_preview_label.setPixmap(QPixmap())

        else:
            # Region is not defined or failed to load
            self.monitor_status_label.setText("Status: Not Defined")
            self.monitor_status_label.setStyleSheet("font-style: italic; color: grey;")
            self.monitor_coords_label.setText("Coordinates: N/A")
            self.monitor_preview_label.setText("No Preview")
            self.monitor_preview_label.setPixmap(QPixmap())
            self.delete_monitor_btn.setEnabled(False)
            if result.is_failure:
                self.log_message(f"Could not load monitor region: {result.error}", "WARNING")

    def _load_flatten_region_list(self):
        """Clears and reloads the QListWidget for flatten regions."""
        self.flatten_list.clear()
        current_platform = self.platform_selection_service.get_current_platform()
        if not current_platform: return  # Nothing to load

        result = self.region_service.get_regions_by_platform(current_platform, "flatten")
        if result.is_success and result.value:
            flatten_regions = result.value
            for region in flatten_regions:
                # Create the RegionEntry widget for each flatten region
                item = QListWidgetItem()
                widget = RegionEntry(
                    region_id=region.name,  # Use name as ID here
                    region=region.coordinates,
                    on_edit=lambda name, coords: self._on_edit_flatten_region(name, coords),
                    # Connect to flatten edit handler
                    on_delete=lambda name: self._on_delete_flatten_region(name),  # Connect to flatten delete handler
                    on_flash=lambda name: self._on_flash_region(name, "flatten")  # Connect to flash handler
                )
                item.setSizeHint(widget.sizeHint())
                self.flatten_list.addItem(item)
                self.flatten_list.setItemWidget(item, widget)

                # Load screenshot preview for the flatten region entry
                if region.screenshot_path:
                    load_result = self.region_service.load_region_screenshot(region)
                    if load_result.is_success:
                        pixmap_result = self.screenshot_service.to_pyside_pixmap(load_result.value)
                        if pixmap_result.is_success:
                            scaled_pixmap = pixmap_result.value.scaled(
                                widget.screenshot_label.width() - 6,
                                widget.screenshot_label.height() - 6,
                                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                            widget.screenshot_label.setPixmap(scaled_pixmap)
                        else:
                            widget.screenshot_label.setText("Preview Failed")
                    else:
                        widget.screenshot_label.setText("Preview Failed")
                else:
                    widget.screenshot_label.setText("No Screenshot")

        elif result.is_failure:
            self.log_message(f"Failed to load flatten regions: {result.error}", "WARNING")

    def _validate_input(self, input_value: str, field_name: str) -> Result:
        """Validate user input and return a Result object."""
        if not input_value or not input_value.strip():
            error = DomainError(
                message=f"{field_name} cannot be empty",
                category=ErrorCategory.VALIDATION,
                severity=ErrorSeverity.WARNING
            )
            return Result.fail(error)
        return Result.ok(input_value)

    def _start_calibration(self):
        """Start the auto-calibration process with a unique task ID."""
        # --- Verify it uses self.calibration_image_path ---
        if not hasattr(self, 'calibration_image_path') or not self.calibration_image_path:
            self.log_message("Calibration source image path not set.", "ERROR")
            QMessageBox.warning(self, "Screenshot Needed", "Monitor region screenshot not available for calibration.")
            return
        screenshot_path = self.calibration_image_path
        if not os.path.exists(screenshot_path):
             self.log_message(f"Calibration source file missing: {screenshot_path}", "ERROR")
             QMessageBox.critical(self, "File Missing", f"The screenshot file needed for calibration is missing.")
             return

        # Get expected value
        expected_value = self.expected_value_input.text().strip()
        if not expected_value:
            self.log_message("Please enter the expected value shown in the image.", "ERROR")
            QMessageBox.warning(self, "Missing Value",
                                "Please enter the exact value shown in the image into the input field.")
            return

        # --- UI Updates Before Starting ---
        self.calibrate_btn.setEnabled(False)  # Disable button during calibration
        self.save_profile_button.setEnabled(False)  # Disable save button
        self.pattern_group.setVisible(False)  # Hide old results
        # Reset checkboxes styling
        for checkbox in self.pattern_checkboxes.values():
            if checkbox:
                checkbox.setChecked(False)
                font = checkbox.font()
                font.setBold(False)
                checkbox.setFont(font)
                checkbox.setStyleSheet("QCheckBox::indicator { width: 0px; }")

        self.calibration_progress.setVisible(True)
        self.calibration_progress.setValue(0)
        self.calibration_status.setText(f"Starting calibration for '{expected_value}'...")
        # --- End UI Updates ---

        # Create worker
        worker = CalibrationWorker(
            image_path=screenshot_path,  # Use the verified path
            expected_value=expected_value,
            ocr_service=self.ocr_service,
            ocr_analysis_service=self.ocr_analysis_service,
            logger=self.logger
        )

        # --- Define Callbacks ---
        def on_progress(percent, message):
            self.calibration_progress.setValue(percent)
            self.calibration_status.setText(message)

        def on_completed(result):
            self.calibration_progress.setVisible(False)
            self.calibrate_btn.setEnabled(True)  # Re-enable calibrate button

            if result:
                # Calibration succeeded
                self.log_message("Calibration successful!", "SUCCESS")

                # Update OCR parameter UI elements
                ocr_profile = result["ocr_profile"]
                self.scale_factor_spin.setValue(ocr_profile.scale_factor)
                self.block_size_spin.setValue(ocr_profile.threshold_block_size)
                self.c_value_spin.setValue(ocr_profile.threshold_c)
                self.denoise_h_spin.setValue(ocr_profile.denoise_h)
                self.config_text.setText(ocr_profile.tesseract_config)
                self.invert_colors_check.setChecked(ocr_profile.invert_colors)

                # Store the detected patterns dictionary
                self.detected_patterns = result.get("patterns", {})  # Use .get for safety

                # Update Checkbox UI based on detected patterns
                self.logger.debug(
                    f"Updating pattern checkboxes based on detected keys: {list(self.detected_patterns.keys())}")
                any_format_detected = False
                for key, checkbox in self.pattern_checkboxes.items():
                    if checkbox:  # Ensure the checkbox widget exists
                        is_detected = key in self.detected_patterns
                        checkbox.setChecked(is_detected)
                        # Visually distinguish detected formats
                        font = checkbox.font()
                        font.setBold(is_detected)
                        checkbox.setFont(font)
                        # Show the check indicator only if detected
                        checkbox.setStyleSheet("QCheckBox::indicator { width: %spx; }" % ("13" if is_detected else "0"))

                        if is_detected:
                            any_format_detected = True
                            self.logger.debug(f"  Checkbox '{key}' set to checked.")

                if any_format_detected:
                    self.pattern_group.setVisible(True)  # Show the formats section
                    self.pattern_group.setTitle("Detected Number Formats (Read-Only)")
                else:
                    self.logger.warning("Calibration succeeded but no known pattern keys found in result.")
                    self.pattern_group.setVisible(False)

                # Update status label
                status_msg = f"Calibration successful! Detected value: {result.get('matched_value', 'N/A')}"
                if result.get('difference', 0) > 0.001:  # Check if it was a close match
                    status_msg += f" (Note: Matched within ${result.get('difference', 0):.2f} tolerance)"
                self.calibration_status.setText(status_msg)
                self.calibration_status.setStyleSheet("color: green;")  # Success color

                # Enable saving
                self.save_profile_button.setEnabled(True)

                # Auto-show advanced settings
                self.advanced_settings_check.setChecked(True)

                # Optional: Ask to save immediately
                # response = QMessageBox.question(...) # Keep your existing save prompt logic if desired

            else:
                # Calibration failed
                self.log_message("Calibration failed.", "ERROR")
                self.pattern_group.setVisible(False)  # Ensure pattern group is hidden
                self.calibration_status.setText(
                    "Calibration failed. Suggestions: Try a different region screenshot, check the entered value, or adjust advanced settings manually.")
                self.calibration_status.setStyleSheet("color: red;")  # Failure color
                self.save_profile_button.setEnabled(False)  # Ensure save is disabled

        def on_error(error_msg):
            self.calibration_progress.setVisible(False)
            self.calibrate_btn.setEnabled(True)  # Re-enable calibrate button
            self.save_profile_button.setEnabled(False)  # Ensure save is disabled
            self.pattern_group.setVisible(False)  # Hide pattern group
            self.calibration_status.setText(f"Calibration Error: {error_msg}")
            self.calibration_status.setStyleSheet("color: red;")
            self.log_message(f"Calibration error reported: {error_msg}", "ERROR")

        # --- End Callbacks ---

        # Set callbacks on worker
        worker.set_on_progress(on_progress)
        worker.set_on_completed(on_completed)
        worker.set_on_error(on_error)

        # --- Generate UNIQUE Task ID ---
        import uuid
        task_id = f"calibration_{uuid.uuid4()}"  # Create a unique ID each time
        self.log_message(f"Starting calibration task with ID: {task_id}", "INFO")
        # -----------------------------

        # Start the worker thread using the UNIQUE ID
        self.log_message(
            f"Executing calibration task for image '{os.path.basename(screenshot_path)}' and value '{expected_value}'...",
            "INFO")
        # --- Use the new unique task_id ---
        task_result = self.thread_service.execute_task_and_restore_result(task_id, worker)
        # ----------------------------------

        if task_result.is_failure:
            self.log_message(f"Failed to start calibration task (ID: {task_id}): {task_result.error}", "ERROR")
            # Reset UI elements if task fails to start
            on_error(f"Failed to start task: {task_result.error}")  # Pass original error

    def _save_calibrated_profile(self):
        """Save the profile with calibrated parameters and patterns."""
        platform = self.platform_selection_service.get_current_platform()
        if not platform:
            self.log_message("No platform selected", "WARNING")
            return

        if not hasattr(self, 'detected_patterns') or not self.detected_patterns:
            self.log_message("No patterns detected to save", "ERROR")
            return

        try:
            # Create OCR profile from UI values (should be updated by calibration)
            ocr = OcrProfile(
                scale_factor=self.scale_factor_spin.value(),
                threshold_block_size=self.block_size_spin.value(),
                threshold_c=self.c_value_spin.value(),
                denoise_h=self.denoise_h_spin.value(),
                tesseract_config=self.config_text.text(),
                invert_colors=self.invert_colors_check.isChecked()
            )

            # Create profile object with detected patterns
            profile = PlatformProfile(
                platform_name=platform,
                ocr_profile=ocr,
                numeric_patterns=self.detected_patterns
            )

            # Save profile
            result = self.profile_service.save_profile(profile)

            if result.is_success:
                self.log_message(f"Calibrated profile saved for {platform}", "SUCCESS")
            else:
                self.log_message(f"Failed to save profile: {result.error}", "ERROR")
        except Exception as e:
            self.log_message(f"Error saving profile: {str(e)}", "ERROR")
            self.logger.error(f"Error saving profile: {e}", exc_info=True)

    def event(self, event):
        """Handle custom events."""
        if event.type() == _ThresholdExceededEvent.EVENT_TYPE:
            self.log_message("!!! _ThresholdExceededEvent Received !!!", "ERROR")  # Keep this

            # --- RESTORE THESE LINES ---
            self.lockout_status.append(f"Threshold exceeded! Detected value: ${event.result.minimum_value}")
            self._update_monitoring_ui_state(False)
            self.log_message("--- Calling _on_trigger_lockout ---", "DEBUG")  # Add log before call
            self._on_trigger_lockout(automatic=True)  # <--- UNCOMMENT THIS
            self.log_message("--- Returned from _on_trigger_lockout call ---", "DEBUG")  # Add log after call
            # --- END OF RESTORED LINES ---

            # Remove the test QMessageBox and logging related to it
            # QMessageBox.information(...)
            # self.log_message("!!! Lockout Trigger Postponed for Test !!!", "ERROR")

            return True  # Indicate event was handled
        return super().event(event)


    def _update_summary_display(self):
        """Fetches current settings and updates the summary labels in the toolbar."""
        if not hasattr(self, 'platform_toolbar'): return # Safety check

        # --- Get data from UI widgets ---
        threshold = self.threshold_spin.value() if hasattr(self, 'threshold_spin') else None
        duration = self.duration_spin.value() if hasattr(self, 'duration_spin') else None

        # --- Determine Monitor Region Status ---
        monitor_region_status = "N/A" # Default if no platform
        current_platform = self.platform_selection_service.get_current_platform()
        if current_platform:
            region_result = self.region_service.get_monitor_region(current_platform)
            if region_result.is_success:
                 # Show coordinates if defined, otherwise "Not Defined"
                 monitor_region = region_result.value
                 if monitor_region:
                      x, y, w, h = monitor_region.coordinates
                      monitor_region_status = f"({x},{y},{w},{h})" # Display coordinates
                 else:
                      monitor_region_status = "Not Defined"
            else:
                 # Error fetching status
                 monitor_region_status = "Error"
                 self.log_message(f"Toolbar: Failed to get monitor region status: {region_result.error}", "WARNING")

        # --- Determine Pattern Summary (Using Suggestion 2 from before) ---
        patterns_desc = "N/A" # Default if no platform
        if current_platform:
            profile_result = self.profile_service.get_profile(current_platform)
            if profile_result.is_success:
                patterns = profile_result.value.numeric_patterns
                # Check if profile uses default patterns (compare with a default instance)
                is_default_patterns = (patterns == PlatformProfile("dummy").numeric_patterns)

                if not patterns or is_default_patterns:
                    patterns_desc = "Default"
                else:
                     # Determine description based on keys present
                     if "negative" in patterns: patterns_desc = "ParensNeg ()"
                     elif "negative_dash" in patterns: patterns_desc = "DashNeg -"
                     elif "dollar" in patterns: patterns_desc = "Currency $"
                     elif "regular" in patterns: patterns_desc = "Number +/-"
                     else: patterns_desc = "Custom" # Calibrated but no known primary key?
            else:
                patterns_desc = "Error"
                self.log_message(f"Toolbar: Failed to get profile for patterns: {profile_result.error}", "WARNING")

        # --- Update the Toolbar ---
        # Assumes platform_toolbar has update_summary & update_pattern_summary methods
        # (We need to add update_pattern_summary to the toolbar class next)
        self.platform_toolbar.update_summary(
            region_status=monitor_region_status, # Pass status/coords string
            threshold=threshold,
            duration=duration
        )
        # Check if the method exists before calling
        if hasattr(self.platform_toolbar, 'update_pattern_summary'):
             self.platform_toolbar.update_pattern_summary(patterns_desc)
        else:
             self.log_message("Toolbar needs update_pattern_summary method", "DEBUG")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    from src.application.app import get_container
    if get_container() is None:
        from src.application.app import initialize_app
        initialize_app()
    window = TradingMonitorTestApp()
    window.show()
    sys.exit(app.exec())