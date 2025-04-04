#!/usr/bin/env python3
"""
Comprehensive testing application for the Trading Monitor functionality.

This application tests:
1. Region selection for P&L monitoring
2. Region selection for flatten positions during lockout
3. Cold Turkey Blocker path verification
4. Block configuration verification
5. Complete lockout sequence testing

Usage:
    python test_lockout.py
"""
import os
import re
import sys
import time
import logging
from typing import List, Dict, Any, Optional, Tuple
import traceback

from src.domain.services.i_ocr_analysis_service import IOcrAnalysisService
from src.domain.services.i_region_service import IRegionService
from src.domain.models.platform_profile import PlatformProfile, OcrProfile

from src.domain.common.result import Result
from src.domain.common.errors import DomainError, ErrorCategory, ErrorSeverity


# Add the project root to the Python path so we can import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
    QTextEdit, QMessageBox, QTabWidget, QFileDialog, QLineEdit, QGroupBox, QComboBox,
    QListWidget, QListWidgetItem, QSplitter, QFormLayout, QSpinBox, QDoubleSpinBox, QCheckBox, QScrollArea, QFrame,
    QButtonGroup, QRadioButton
)
from PySide6.QtGui import QPixmap, QColor, QTextCursor
from PySide6.QtCore import Qt, QSize, QObject, Signal, QThread

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

from src.domain.services.i_platform_selection_service import IPlatformSelectionService
from src.presentation.components.platform_selector_toolbar import PlatformSelectorToolbar
SCREENSHOTS_DIR = os.path.join(os.getcwd(), "region_screenshots")


class LogDisplay(QTextEdit):
    """Custom text display for logging messages with colors."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMinimumHeight(200)

    def append_message(self, message: str, level: str = "INFO"):
        """Append a message with the appropriate color based on level."""
        color_map = {
            "INFO": "black",
            "SUCCESS": "green",
            "WARNING": "orange",
            "ERROR": "red",
            "DEBUG": "gray"
        }
        color = color_map.get(level.upper(), "black")

        timestamp = time.strftime("%H:%M:%S")
        formatted_message = f"<span style='color:{color};'>[{timestamp} {level}] {message}</span>"
        self.append(formatted_message)

        # Ensure the latest message is visible
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.setTextCursor(cursor)

class RegionEntry(QWidget):
    """Widget for displaying a selected region with options to edit/delete."""

    def __init__(self, region_id: str, region: Tuple[int, int, int, int],
                 on_edit, on_delete, parent=None):
        super().__init__(parent)
        self.region_id = region_id
        self.region = region
        self.on_edit = on_edit
        self.on_delete = on_delete

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

        # Edit button
        edit_btn = QPushButton("Edit")
        edit_btn.setMaximumWidth(60)
        edit_btn.clicked.connect(lambda: self.on_edit(self.region_id, self.region))
        top_layout.addWidget(edit_btn)

        # Delete button
        delete_btn = QPushButton("Delete")
        delete_btn.setMaximumWidth(60)
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

class RegionComboBox(QComboBox):
    """Custom combo box that displays region information."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.regions = []
        self.setMinimumWidth(250)

    def add_region(self, region, screenshot=None):
        """Add a region with optional screenshot."""
        self.regions.append({
            "region": region,
            "screenshot": screenshot
        })

        # Add to combo box
        x, y, w, h = region.coordinates
        self.addItem(f"{region.name}: ({x}, {y}, {w}, {h})")

    def get_selected_region(self):
        """Get the currently selected region object."""
        idx = self.currentIndex()
        if idx >= 0 and idx < len(self.regions):
            return self.regions[idx]["region"]
        return None

    def get_selected_screenshot_path(self):
        """Get the screenshot path for the selected region."""
        region = self.get_selected_region()
        if region:
            return region.screenshot_path
        return None

    def get_selected_screenshot(self):
        """Get the screenshot for the selected region."""
        idx = self.currentIndex()
        if idx >= 0 and idx < len(self.regions):
            return self.regions[idx]["screenshot"]
        return None

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
        self.current_image_path = None
        self.ocr_profile = None
        self.extracted_text = ""
        self.patterns = {}
        self.retry_count = 0

        # Populate platform list
        self._populate_platform_list()

        # Load settings
        self._load_settings()

        # Log startup message
        self.log_message("Application initialized. Select a tab to begin testing.", "INFO")

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
        self.cold_turkey = self.container.resolve(IColdTurkeyService)
        self.verification_service = self.container.resolve(IVerificationService)
        self.lockout_service = self.container.resolve(ILockoutService)
        self.monitoring_service = self.container.resolve(IMonitoringService)
        self.profile_service = self.container.resolve(IProfileService)
        self.platform_selection_service = self.container.resolve(IPlatformSelectionService)
        self.region_service = self.container.resolve(IRegionService)
        self.ocr_analysis_service = self.container.resolve(IOcrAnalysisService)

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
        log_group = QGroupBox("Log")
        log_layout = QVBoxLayout(log_group)

        self.log_display = LogDisplay()
        log_layout.addWidget(self.log_display)

        main_layout.addWidget(log_group)

    def _create_region_tab(self):
        """Create the region selection tab."""
        region_tab = QWidget()
        layout = QVBoxLayout(region_tab)

        # Top area with platform selection
        top_layout = QHBoxLayout()

        # Platform detection button
        detect_btn = QPushButton("Detect Platform")
        detect_btn.clicked.connect(self._on_detect_platform)
        top_layout.addWidget(detect_btn)

        top_layout.addStretch()

        layout.addLayout(top_layout)

        # Split the rest of the tab between monitoring regions and flatten regions
        splitter = QSplitter(Qt.Horizontal)

        # Monitoring regions
        monitoring_widget = QWidget()
        monitoring_layout = QVBoxLayout(monitoring_widget)
        monitoring_layout.setContentsMargins(0, 0, 0, 0)

        monitoring_group = QGroupBox("P&L Monitoring Regions")
        m_layout = QVBoxLayout(monitoring_group)

        self.monitoring_list = QListWidget()
        m_layout.addWidget(self.monitoring_list)

        m_btn_layout = QHBoxLayout()
        add_monitoring_btn = QPushButton("Add Region")
        add_monitoring_btn.clicked.connect(lambda: self._on_add_region("monitor"))
        m_btn_layout.addWidget(add_monitoring_btn)

        m_layout.addLayout(m_btn_layout)

        monitoring_layout.addWidget(monitoring_group)

        # Flatten regions
        flatten_widget = QWidget()
        flatten_layout = QVBoxLayout(flatten_widget)
        flatten_layout.setContentsMargins(0, 0, 0, 0)

        flatten_group = QGroupBox("Flatten Position Regions")
        f_layout = QVBoxLayout(flatten_group)

        self.flatten_list = QListWidget()
        f_layout.addWidget(self.flatten_list)

        add_flatten_btn = QPushButton("Add Region")
        add_flatten_btn.clicked.connect(lambda: self._on_add_region("flatten"))
        f_layout.addWidget(add_flatten_btn)

        flatten_layout.addWidget(flatten_group)

        # Add both to splitter
        splitter.addWidget(monitoring_widget)
        splitter.addWidget(flatten_widget)
        splitter.setSizes([500, 500])  # Equal split

        layout.addWidget(splitter, 1)

        # Add to tabs
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

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._on_browse_ct_path)
        path_layout.addWidget(browse_btn)

        save_path_btn = QPushButton("Save Path")
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
        verify_btn = QPushButton("Verify Block Configuration")
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

        refresh_btn = QPushButton("Refresh List")
        refresh_btn.clicked.connect(self._refresh_verified_blocks)
        v_btn_layout.addWidget(refresh_btn)

        clear_btn = QPushButton("Clear All")
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
        self.threshold_spin.setRange(-10000, 0)
        self.threshold_spin.setValue(-100)
        self.threshold_spin.setPrefix("$ ")
        self.threshold_spin.setDecimals(2)
        settings_layout.addRow("Stop Loss Threshold:", self.threshold_spin)

        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(1, 720)
        self.duration_spin.setValue(15)
        self.duration_spin.setSuffix(" minutes")
        settings_layout.addRow("Lockout Duration:", self.duration_spin)

        layout.addWidget(settings_group)

        # Monitoring controls
        monitor_group = QGroupBox("Monitoring")
        monitor_layout = QVBoxLayout(monitor_group)

        # Add region selection dropdown
        self.monitor_region_combo = QComboBox()
        self.monitor_region_combo.setPlaceholderText("Select monitoring region...")
        monitor_layout.addWidget(QLabel("Monitoring Region:"))
        monitor_layout.addWidget(self.monitor_region_combo)

        # Start monitoring button
        self.start_monitor_btn = QPushButton("Start Monitoring")
        self.start_monitor_btn.clicked.connect(self._on_start_monitoring)
        monitor_layout.addWidget(self.start_monitor_btn)

        # Stop monitoring button
        self.stop_monitor_btn = QPushButton("Stop Monitoring")
        self.stop_monitor_btn.clicked.connect(self._on_stop_monitoring)
        self.stop_monitor_btn.setEnabled(False)
        monitor_layout.addWidget(self.stop_monitor_btn)

        # Manually trigger lockout
        self.trigger_lockout_btn = QPushButton("Manually Trigger Lockout")
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
        """Create the profile management tab with integrated auto-detection."""
        profile_tab = QWidget()
        layout = QVBoxLayout(profile_tab)

        # 1. Region Selection Section
        region_group = QGroupBox("Region Selection")
        region_layout = QVBoxLayout(region_group)

        region_help = QLabel(
            "Select a region with P&L values to analyze and detect optimal OCR settings."
        )
        region_help.setWordWrap(True)
        region_layout.addWidget(region_help)

        # Region dropdown row
        region_row = QHBoxLayout()
        region_row.addWidget(QLabel("Select region:"))

        # Create the custom region combo box
        self.profile_region_combo = RegionComboBox()
        self.profile_region_combo.currentIndexChanged.connect(self._on_profile_region_selected)
        region_row.addWidget(self.profile_region_combo)

        region_layout.addLayout(region_row)

        # Screenshot preview
        self.profile_preview_label = QLabel("No preview available")
        self.profile_preview_label.setAlignment(Qt.AlignCenter)
        self.profile_preview_label.setStyleSheet("border: 1px solid #ddd;")
        self.profile_preview_label.setMinimumHeight(100)
        self.profile_preview_label.setMaximumHeight(150)
        region_layout.addWidget(self.profile_preview_label)

        # Add Start Detection button
        self.start_detection_btn = QPushButton("Start Detection")
        self.start_detection_btn.setStyleSheet(
            "background-color: #3a7ca5; color: white; padding: 8px 16px; border-radius: 4px;"
        )
        self.start_detection_btn.clicked.connect(self._start_profile_detection)
        region_layout.addWidget(self.start_detection_btn, alignment=Qt.AlignCenter)

        layout.addWidget(region_group)

        # 2. Status Section
        self.profile_status_label = QLabel("Select a region and click 'Start Detection'")
        self.profile_status_label.setStyleSheet("font-style: italic;")
        layout.addWidget(self.profile_status_label)

        # 3. Verification Section
        self.profile_verification_widget = QWidget()
        self.profile_verification_widget.setVisible(False)
        verification_layout = QHBoxLayout(self.profile_verification_widget)
        verification_layout.setContentsMargins(0, 10, 0, 10)

        verification_label = QLabel("Extracted: ")
        verification_layout.addWidget(verification_label)

        self.profile_extracted_text_label = QLabel("")
        self.profile_extracted_text_label.setStyleSheet("font-weight: bold;")
        self.profile_extracted_text_label.setWordWrap(True)
        verification_layout.addWidget(self.profile_extracted_text_label, 1)

        self.profile_yes_button = QPushButton("Correct")
        self.profile_yes_button.setToolTip("The extracted text shows the correct P&L values")
        self.profile_yes_button.clicked.connect(self._on_profile_text_verified)
        verification_layout.addWidget(self.profile_yes_button)

        self.profile_no_button = QPushButton("Try Again")
        self.profile_no_button.setToolTip("The text doesn't accurately show the P&L values")
        self.profile_no_button.clicked.connect(self._on_profile_text_rejected)
        verification_layout.addWidget(self.profile_no_button)

        layout.addWidget(self.profile_verification_widget)

        # 4. Pattern Configuration Section
        self.profile_pattern_group = QGroupBox("P&L Format Configuration")
        self.profile_pattern_group.setVisible(False)
        pattern_layout = QVBoxLayout(self.profile_pattern_group)

        # Two-column layout for format options
        format_layout = QHBoxLayout()

        # Left column
        left_layout = QVBoxLayout()

        # Dollar sign option
        self.profile_dollar_check = QCheckBox("Dollar signs ($123.45)")
        self.profile_dollar_check.setChecked(True)
        left_layout.addWidget(self.profile_dollar_check)

        # Plain number option
        self.profile_plain_number_check = QCheckBox("Plain numbers (123.45)")
        self.profile_plain_number_check.setChecked(True)
        left_layout.addWidget(self.profile_plain_number_check)

        format_layout.addLayout(left_layout)

        # Right column - other currencies
        right_layout = QVBoxLayout()

        self.profile_euro_check = QCheckBox("Euro symbol (€123.45)")
        right_layout.addWidget(self.profile_euro_check)

        self.profile_pound_check = QCheckBox("Pound symbol (£123.45)")
        right_layout.addWidget(self.profile_pound_check)

        format_layout.addLayout(right_layout)
        pattern_layout.addLayout(format_layout)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        pattern_layout.addWidget(separator)

        # Negative format options in horizontal layout
        neg_layout = QHBoxLayout()
        neg_label = QLabel("Negative values appear as:")
        neg_layout.addWidget(neg_label)

        self.profile_negative_group = QButtonGroup(profile_tab)

        self.profile_negative_minus_radio = QRadioButton("Minus (-$123.45)")
        self.profile_negative_group.addButton(self.profile_negative_minus_radio)
        neg_layout.addWidget(self.profile_negative_minus_radio)

        self.profile_negative_parentheses_radio = QRadioButton("Parentheses ($123.45)")
        self.profile_negative_group.addButton(self.profile_negative_parentheses_radio)
        neg_layout.addWidget(self.profile_negative_parentheses_radio)

        self.profile_negative_both_radio = QRadioButton("Both formats")
        self.profile_negative_group.addButton(self.profile_negative_both_radio)
        self.profile_negative_both_radio.setChecked(True)
        neg_layout.addWidget(self.profile_negative_both_radio)

        pattern_layout.addLayout(neg_layout)

        # Results and test button in horizontal layout
        results_layout = QHBoxLayout()

        results_label = QLabel("Detected values:")
        results_layout.addWidget(results_label)

        self.profile_pattern_results = QLabel("")
        self.profile_pattern_results.setStyleSheet("font-weight: bold;")
        results_layout.addWidget(self.profile_pattern_results, 1)

        test_button = QPushButton("Test")
        test_button.setMaximumWidth(60)
        test_button.clicked.connect(self._test_profile_patterns)
        results_layout.addWidget(test_button)

        pattern_layout.addLayout(results_layout)

        layout.addWidget(self.profile_pattern_group)

        # 5. OCR Parameters Section (collapsible)
        advanced_layout = QHBoxLayout()
        advanced_layout.addStretch()

        self.advanced_settings_check = QCheckBox("Show Advanced Settings")
        self.advanced_settings_check.toggled.connect(self._toggle_advanced_settings)
        advanced_layout.addWidget(self.advanced_settings_check)

        layout.addLayout(advanced_layout)

        self.profile_group = QGroupBox("OCR Profile Settings")
        profile_layout = QFormLayout(self.profile_group)

        # OCR parameters
        self.scale_factor_spin = QDoubleSpinBox()
        self.scale_factor_spin.setRange(1.0, 5.0)
        self.scale_factor_spin.setSingleStep(0.1)
        self.scale_factor_spin.setValue(2.0)
        profile_layout.addRow("Scale Factor:", self.scale_factor_spin)

        self.block_size_spin = QSpinBox()
        self.block_size_spin.setRange(3, 21)
        self.block_size_spin.setSingleStep(2)  # Must be odd
        self.block_size_spin.setValue(11)
        profile_layout.addRow("Threshold Block Size:", self.block_size_spin)

        self.c_value_spin = QSpinBox()
        self.c_value_spin.setRange(0, 10)
        self.c_value_spin.setValue(2)
        profile_layout.addRow("Threshold C Value:", self.c_value_spin)

        self.denoise_h_spin = QSpinBox()
        self.denoise_h_spin.setRange(1, 30)
        self.denoise_h_spin.setValue(10)
        profile_layout.addRow("Denoise H:", self.denoise_h_spin)

        self.config_text = QLineEdit()
        self.config_text.setText("--oem 3 --psm 6")
        profile_layout.addRow("Tesseract Config:", self.config_text)

        # Color inversion option
        self.invert_colors_check = QCheckBox("Invert Colors (for light text on dark background)")
        profile_layout.addRow("", self.invert_colors_check)

        # Initially hide advanced settings
        self.profile_group.setVisible(False)
        layout.addWidget(self.profile_group)

        # Buttons for saving/resetting profile
        button_layout = QHBoxLayout()

        save_btn = QPushButton("Save Profile")
        save_btn.clicked.connect(self._save_platform_profile)
        button_layout.addWidget(save_btn)

        reset_btn = QPushButton("Reset to Default")
        reset_btn.clicked.connect(self._reset_platform_profile)
        button_layout.addWidget(reset_btn)

        layout.addLayout(button_layout)

        # Add to tabs
        self.tab_widget.addTab(profile_tab, "Profile Management")

    def _populate_platform_list(self):
        """Populate the global platform dropdown."""
        current_platform = self.platform_selection_service.get_current_platform()
        try:
            # Get supported platforms from platform detection service
            result = self.platform_detection.get_supported_platforms()

            platforms = self._handle_result(
                result,
                error_message="Failed to get platform list"
            )

            if platforms:
                # We only need to update the global platform toolbar
                self.platform_toolbar.update_platforms(list(platforms.keys()), current_platform)
        except Exception as e:
            self.log_message(f"Error populating platform list: {str(e)}", "ERROR")
            self.logger.error(f"Error populating platform list: {e}", exc_info=True)

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

            # Load platform-specific regions
            self._load_regions_for_platform()  # USING THE NEW METHOD

            self.log_message("Settings loaded successfully", "INFO")
        except Exception as e:
            self.log_message(f"Error loading settings: {str(e)}", "ERROR")
            self.logger.error(f"Error loading settings: {e}", exc_info=True)

    def _load_platform_profile(self, platform=None):
        """Load and display profile for the selected platform."""
        if not platform:
            platform = self.platform_selection_service.get_current_platform()

        if not platform:
            return

        try:
            self.log_message(f"Loading profile for {platform}...", "INFO")

            # Get profile from service
            result = self.profile_service.get_profile(platform)

            if result.is_success:
                profile = result.value

                # Update UI with profile values
                # OCR profile
                ocr = profile.ocr_profile
                self.scale_factor_spin.setValue(ocr.scale_factor)
                self.block_size_spin.setValue(ocr.threshold_block_size)
                self.c_value_spin.setValue(ocr.threshold_c)
                self.denoise_h_spin.setValue(ocr.denoise_h)
                self.config_text.setText(ocr.tesseract_config)
                self.invert_colors_check.setChecked(ocr.invert_colors)

                # Also load regions for the profile tab
                self._load_profile_regions()

                self.log_message(f"Profile loaded for {platform}", "SUCCESS")
            else:
                self.log_message(f"Failed to load profile: {result.error}", "ERROR")
        except Exception as e:
            self.log_message(f"Error loading profile: {str(e)}", "ERROR")
            self.logger.error(f"Error loading profile: {e}", exc_info=True)

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

            # Update patterns if we have generated new ones
            if hasattr(self, 'patterns') and self.patterns:
                patterns = self.patterns

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

            blocks = self._handle_result(
                self.verification_service.get_verified_blocks(),
                error_message="Failed to get verified blocks"
            )

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
                self.verified_list.addItem("Error loading verified blocks")
        except Exception as e:
            self.log_message(f"Error refreshing verified blocks: {str(e)}", "ERROR")
            self.logger.error(f"Error refreshing verified blocks: {e}", exc_info=True)

    def _on_global_platform_changed(self, platform: str) -> None:
        """Handle global platform change."""
        # Load regions for this platform
        self._load_regions_for_platform()

        # Load profile for new platform
        self._load_platform_profile(platform)

        # Reset profile tab state
        self.profile_verification_widget.setVisible(False)
        self.profile_pattern_group.setVisible(False)
        self.profile_status_label.setText("Select a region and click 'Start Detection'")

        self.log_message(f"Selected platform: {platform}", "INFO")

    def _load_regions_for_platform(self):
        """Load regions for the current platform."""
        # Clear existing lists
        self.monitoring_list.clear()
        self.flatten_list.clear()

        # Get current platform from service
        current_platform = self.platform_selection_service.get_current_platform()

        # Load monitoring regions
        monitor_regions = self._handle_result(
            self.region_service.get_regions_by_platform(current_platform, "monitor"),
            error_message="Failed to load monitoring regions",
            error_level="WARNING"
        )

        if monitor_regions:
            for region in monitor_regions:
                self._add_region_to_list(region.name, region.coordinates, "monitor")

        # Load flatten regions
        flatten_regions = self._handle_result(
            self.region_service.get_regions_by_platform(current_platform, "flatten"),
            error_message="Failed to load flatten regions",
            error_level="WARNING"
        )

        if flatten_regions:
            for region in flatten_regions:
                self._add_region_to_list(region.name, region.coordinates, "flatten")

        # Update monitoring dropdown
        self._update_monitoring_dropdown()

    def _on_browse_ct_path(self):
        """Browse for Cold Turkey Blocker executable."""
        result = self.ui_service.select_file(
            "Select Cold Turkey Blocker Executable",
            "Executables (*.exe);;All Files (*)"
        )

        if result.is_success and result.value:
            file_path = result.value
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

        result = self.cold_turkey_service.set_blocker_path(path)
        if result.is_success:
            self.log_message("Cold Turkey path saved successfully", "SUCCESS")
        else:
            self.log_message(f"Failed to save path: {result.error}", "ERROR")

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

        result = self.thread_service.execute_task_with_auto_cleanup(f"detect_{platform}", worker)
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

    def _add_region_to_list(self, name: str, region: tuple, region_type: str):
        """Add a region to the appropriate list widget."""
        if region_type == "monitor":
            list_widget = self.monitoring_list
        else:  # flatten
            list_widget = self.flatten_list

        item = QListWidgetItem()
        widget = RegionEntry(
            name, region,
            on_edit=lambda id, r: self._on_edit_region(id, r, region_type),
            on_delete=lambda id: self._on_delete_region(id, region_type)
        )
        item.setSizeHint(widget.sizeHint())
        list_widget.addItem(item)
        list_widget.setItemWidget(item, widget)

        # Immediately load and display the screenshot
        current_platform = self.platform_selection_service.get_current_platform()
        result = self.region_service.get_region(current_platform, region_type, name)
        if result.is_success:
            region_obj = result.value
            if region_obj.screenshot_path:
                load_result = self.region_service.load_region_screenshot(region_obj)
                if load_result.is_success:
                    screenshot = load_result.value
                    pixmap_result = self.screenshot_service.to_pyside_pixmap(screenshot)
                    if pixmap_result.is_success:
                        widget.screenshot_label.setPixmap(pixmap_result.value)

    def _on_add_region(self, region_type):
        """Add a new region for monitoring or flatten positions."""
        from PySide6.QtWidgets import QInputDialog, QLineEdit, QMessageBox
        from src.domain.models.region_model import Region  # Import the model

        current_platform = self.platform_selection_service.get_current_platform()
        # Determine title and default name based on region type
        if region_type == "monitor":
            title = "Select P&L Monitoring Region"
            # Get count of existing regions for default name
            result = self.region_service.get_regions_by_platform(current_platform, "monitor")
            count = len(result.value) if result.is_success else 0
            default_name = f"P&L_{count + 1}"
        else:  # flatten
            title = "Select Position Flatten Button Region"
            # Get count of existing regions for default name
            result = self.region_service.get_regions_by_platform(current_platform, "flatten")
            count = len(result.value) if result.is_success else 0
            default_name = f"Flatten_{count + 1}"

        # Use region selector
        self.log_message(f"Starting region selection for {region_type}...", "INFO")
        region_result = self.ui_service.select_screen_region(f"Please select the {region_type} region")

        if not region_result.is_success:
            self.log_message(f"Region selection cancelled or failed: {region_result.error}", "INFO")
            return

        coordinates = region_result.value

        # Prompt for a name using Qt dialog
        while True:
            name, ok = QInputDialog.getText(
                self,
                f"Name this {region_type} region",
                "Enter a descriptive name for this region:",
                QLineEdit.Normal,
                default_name
            )

            if not ok:  # User pressed Cancel
                self.log_message(f"Region naming cancelled", "INFO")
                return

            # Validate name
            if not name.strip():
                QMessageBox.warning(self, "Invalid Name", "Name cannot be empty.")
                continue

            # Check if region with this name already exists
            region_check = self.region_service.get_region(current_platform, region_type, name)

            # If a region with this name already exists
            if region_check.is_success:
                choice = QMessageBox.question(
                    self,
                    "Name Already Exists",
                    f"A {region_type} region with this name already exists. Replace it?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )

                if choice != QMessageBox.Yes:
                    continue  # Try again with a different name

                # If user wants to replace existing region, delete the old one first
                # both from the service and from the UI list
                delete_result = self.region_service.delete_region(current_platform, region_type, name)
                if delete_result.is_failure:
                    self.log_message(f"Failed to delete existing region: {delete_result.error}", "ERROR")
                    return

                # Also remove from UI list
                list_widget = self.monitoring_list if region_type == "monitor" else self.flatten_list
                for i in range(list_widget.count()):
                    item = list_widget.item(i)
                    widget = list_widget.itemWidget(item)
                    if hasattr(widget, 'region_id') and widget.region_id == name:
                        list_widget.takeItem(i)
                        break

            # Valid name obtained, break the loop
            break

        # Create a Region object
        region_id = f"{current_platform}_{region_type}_{name}"
        region = Region(
            id=region_id,
            name=name,
            coordinates=coordinates,
            type=region_type,
            platform=current_platform
        )

        # Capture screenshot for the region
        screenshot_result = self.region_service.capture_region_screenshot(
            coordinates, region_id, current_platform, region_type
        )

        if screenshot_result.is_success:
            region.screenshot_path = screenshot_result.value
            self.log_message(f"Captured screenshot for region '{name}'", "SUCCESS")
        else:
            self.log_message(f"Failed to capture screenshot: {screenshot_result.error}", "WARNING")

        # Save the region
        save_result = self.region_service.save_region(region)
        if save_result.is_failure:
            self.log_message(f"Failed to save region: {save_result.error}", "ERROR")
            return

        # Add to UI list
        self._add_region_to_list(name, coordinates, region_type)

        # WITH THIS:
        self.log_message(f"Added {region_type} region '{name}': {coordinates}", "SUCCESS")

        # Refresh all UI components that depend on region data
        self._refresh_ui_after_region_change()

    def _on_edit_region(self, region_id, current_coords, region_type):
        """Edit an existing region."""
        self.log_message(f"Editing region {region_id}...", "INFO")

        current_platform = self.platform_selection_service.get_current_platform()

        # Start region selection
        region_result = self.ui_service.select_screen_region(f"Edit the {region_type} region")

        if region_result.is_failure:
            self.log_message(f"Region edit cancelled or failed: {region_result.error}", "INFO")
            return

        new_coordinates = region_result.value

        # Get the existing region
        get_result = self.region_service.get_region(current_platform, region_type, region_id)
        if get_result.is_failure:
            self.log_message(f"Failed to get region: {get_result.error}", "ERROR")
            return

        region = get_result.value

        # Update coordinates
        region.coordinates = new_coordinates

        # Capture new screenshot
        screenshot_result = self.region_service.capture_region_screenshot(
            new_coordinates, region.id, current_platform, region_type
        )

        if screenshot_result.is_success:
            region.screenshot_path = screenshot_result.value
            self.log_message(f"Updated screenshot for region '{region_id}'", "SUCCESS")
        else:
            self.log_message(f"Failed to update screenshot: {screenshot_result.error}", "WARNING")

        # Save updated region
        save_result = self.region_service.save_region(region)
        if save_result.is_failure:
            self.log_message(f"Failed to save region: {save_result.error}", "ERROR")
            return

        # Update UI list
        list_widget = self.monitoring_list if region_type == "monitor" else self.flatten_list
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            widget = list_widget.itemWidget(item)
            if hasattr(widget, 'region_id') and widget.region_id == region_id:
                # Update the widget with new coordinates
                new_widget = RegionEntry(
                    region_id, new_coordinates,
                    on_edit=lambda id, r: self._on_edit_region(id, r, region_type),
                    on_delete=lambda id: self._on_delete_region(id, region_type)
                )
                item.setSizeHint(new_widget.sizeHint())
                list_widget.setItemWidget(item, new_widget)

                # Immediately display the updated screenshot
                if region.screenshot_path:
                    load_result = self.region_service.load_region_screenshot(region)
                    if load_result.is_success:
                        screenshot = load_result.value
                        pixmap_result = self.screenshot_service.to_pyside_pixmap(screenshot)
                        if pixmap_result.is_success:
                            new_widget.screenshot_label.setPixmap(pixmap_result.value)
                break

        self.log_message(f"Updated {region_type} region {region_id}: {new_coordinates}", "SUCCESS")

        # Refresh all UI components that depend on region data
        self._refresh_ui_after_region_change()

    def _on_delete_region(self, region_id, region_type):
        """Delete an existing region."""
        self.log_message(f"Deleting region {region_id}...", "INFO")

        current_platform = self.platform_selection_service.get_current_platform()
        # Delete the region using service
        result = self.region_service.delete_region(current_platform, region_type, region_id)

        if result.is_failure:
            self.log_message(f"Failed to delete region: {result.error}", "ERROR")
            return

        # Remove from UI list
        list_widget = self.monitoring_list if region_type == "monitor" else self.flatten_list
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            widget = list_widget.itemWidget(item)
            if hasattr(widget, 'region_id') and widget.region_id == region_id:
                list_widget.takeItem(i)
                break

        self.log_message(f"Deleted {region_type} region {region_id}", "SUCCESS")

        # Refresh all UI components that depend on region data
        self._refresh_ui_after_region_change()

    def _capture_region(self, region):
        """Capture a region screenshot without OCR processing."""
        # Capture the screenshot
        result = self.screenshot_service.capture_region(region)

        if result.is_success:
            self.captured_screenshot = result.value
            self.log_message("Screenshot captured successfully", "INFO")

            # Convert to QPixmap and display
            pixmap_result = self.screenshot_service.to_pyside_pixmap(self.captured_screenshot)
            if pixmap_result.is_success:
                pixmap = pixmap_result.value

                # Get the size of the parent container
                container_width = self.screenshot_label.parentWidget().width() - 20
                container_height = self.screenshot_label.parentWidget().height() - 20

                # Scale image to fit the container while maintaining aspect ratio
                scaled_pixmap = pixmap.scaled(
                    container_width,
                    container_height,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )

                # Set the pixmap
                self.screenshot_label.setPixmap(scaled_pixmap)
            else:
                self.log_message(f"Error converting to pixmap: {pixmap_result.error}", "ERROR")
        else:
            self.log_message(f"Error capturing screenshot: {result.error}", "ERROR")

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

        # Run verification with cancellable=False to wait for completion
        # This is for testing purposes - in a production app, you might want to keep it cancellable
        result = self.verification_service.verify_platform_block(
            platform=platform,
            block_name=block_name,
            cancellable=False  # Changed to False to wait for completion
        )

        if result.is_success:
            if result.value:
                self.log_message(f"Verification successful! Block '{block_name}' is correctly configured.", "SUCCESS")
                # Refresh the verified blocks list
                self._refresh_verified_blocks()
            else:
                self.log_message("Verification completed but did not succeed.", "WARNING")
        else:
            self.log_message(f"Verification failed: {result.error}", "ERROR")

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
            result = self.verification_service.clear_verified_blocks()

            if result.is_success:
                self.log_message("All verified blocks cleared", "SUCCESS")
                self._refresh_verified_blocks()
            else:
                self.log_message(f"Failed to clear verified blocks: {result.error}", "ERROR")

    def _on_start_monitoring(self):
        """Start monitoring for P&L losses."""
        platform = self.platform_selection_service.get_current_platform()

        threshold = self.threshold_spin.value()

        # Ensure threshold is negative
        if threshold > 0:
            threshold = -threshold

        # Get selected region name
        region_name = self.monitor_region_combo.currentText()
        if not region_name:
            self.log_message("No monitoring region selected", "ERROR")
            return

        # Get region details
        region_result = self.region_service.get_region(platform, "monitor", region_name)
        if region_result.is_failure:
            self.log_message(f"Failed to get region: {region_result.error}", "ERROR")
            return

        region = region_result.value
        coordinates = region.coordinates

        self.log_message(f"Starting monitoring for {platform} with region '{region_name}'...", "INFO")
        self.log_message(f"Threshold: ${threshold}", "INFO")

        # Clear status display
        self.lockout_status.clear()

        # Prepare callbacks
        def on_status_update(message, level):
            self.log_message(message, level)
            self.lockout_status.append(f"[{level}] {message}")

        def on_threshold_exceeded(result):
            self.log_message("Threshold exceeded!", "ERROR")
            self.log_message(f"Detected value: ${result.minimum_value}", "ERROR")
            self.lockout_status.append(f"Threshold exceeded! Detected value: ${result.minimum_value}")

            # Update UI state
            self.start_monitor_btn.setEnabled(True)
            self.stop_monitor_btn.setEnabled(False)
            self.is_monitoring = False

            # Automatically trigger lockout
            self._on_trigger_lockout()

        # Start monitoring
        try:
            result = self.monitoring_service.start_monitoring(
                platform=platform,
                region=coordinates,
                region_name=region_name,
                threshold=threshold,
                interval_seconds=2.0,  # Check every 2 seconds
                on_status_update=on_status_update,
                on_threshold_exceeded=on_threshold_exceeded,
                on_error=lambda msg: self.log_message(f"Error: {msg}", "ERROR")
            )

            if result.is_success:
                self.is_monitoring = True
                self.start_monitor_btn.setEnabled(False)
                self.stop_monitor_btn.setEnabled(True)
                self.log_message("Monitoring started successfully", "SUCCESS")
            else:
                self.log_message(f"Failed to start monitoring: {result.error}", "ERROR")
        except Exception as e:
            self.log_message(f"Error starting monitoring: {str(e)}", "ERROR")
            self.logger.error(f"Error starting monitoring: {e}", exc_info=True)

    def _on_stop_monitoring(self):
        """Stop monitoring for P&L losses."""
        if not self.is_monitoring:
            self.log_message("No active monitoring to stop", "WARNING")
            return

        try:
            result = self.monitoring_service.stop_monitoring()

            if result.is_success:
                self.log_message("Monitoring stopped", "INFO")
                self.is_monitoring = False
                self.start_monitor_btn.setEnabled(True)
                self.stop_monitor_btn.setEnabled(False)
            else:
                self.log_message(f"Failed to stop monitoring: {result.error}", "ERROR")
        except Exception as e:
            self.log_message(f"Error stopping monitoring: {str(e)}", "ERROR")
            self.logger.error(f"Error stopping monitoring: {e}", exc_info=True)

            # Ensure UI is in a consistent state even if error occurs
            self.is_monitoring = False
            self.start_monitor_btn.setEnabled(True)
            self.stop_monitor_btn.setEnabled(False)

    def _on_trigger_lockout(self):
        """Manually trigger the lockout sequence."""
        platform = self.platform_selection_service.get_current_platform()
        duration = self.duration_spin.value()

        # Get flatten regions
        regions_result = self.region_service.get_regions_by_platform(platform, "flatten")
        if regions_result.is_failure:
            self.log_message(f"Failed to get flatten regions: {regions_result.error}", "ERROR")
            return

        flatten_regions = regions_result.value
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

        # Confirm with user
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
        result = self.lockout_service.perform_lockout(
            platform=platform,
            flatten_positions=flatten_positions,
            lockout_duration=duration,
            on_status_update=on_status_update
        )

        if result.is_success:
            self.log_message("Lockout sequence initiated", "SUCCESS")
        else:
            self.log_message(f"Failed to initiate lockout: {result.error}", "ERROR")

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

    def _update_monitoring_dropdown(self):
        """Update the monitoring region dropdown with current regions."""
        self.monitor_region_combo.clear()

        current_platform = self.platform_selection_service.get_current_platform()

        # Get monitoring regions
        result = self.region_service.get_regions_by_platform(current_platform, "monitor")
        if result.is_success:
            regions = result.value
            region_names = [region.name for region in regions]
            if region_names:
                self.monitor_region_combo.addItems(region_names)
                self.monitor_region_combo.setCurrentIndex(0)
        else:
            self.log_message(f"Failed to get monitoring regions: {result.error}", "WARNING")

    def _toggle_advanced_settings(self, checked):
        """Toggle visibility of advanced settings."""
        self.profile_group.setVisible(checked)

    def _load_profile_regions(self):
        """Load regions for the profile tab region selector."""
        # Clear existing combo box
        self.profile_region_combo.clear()

        # Reset the internal regions list
        self.profile_region_combo.regions = []

        # Get current platform
        current_platform = self.platform_selection_service.get_current_platform()

        # Get monitor regions
        monitor_result = self.region_service.get_regions_by_platform(current_platform, "monitor")

        if monitor_result.is_success and monitor_result.value:
            regions = monitor_result.value

            # CRITICAL FIX: Ensure the combo box is enabled
            self.profile_region_combo.setEnabled(True)

            # Add each region to the combo box
            for region in regions:
                # Load the screenshot
                screenshot = None
                if region.screenshot_path:
                    load_result = self.region_service.load_region_screenshot(region)
                    if load_result.is_success:
                        screenshot = load_result.value

                # Add to combo box
                self.profile_region_combo.add_region(region, screenshot)

            # CRITICAL FIX: Always select the first item by default
            if len(regions) > 0:
                self.profile_region_combo.setCurrentIndex(0)
                self.start_detection_btn.setEnabled(True)
                self._on_profile_region_selected(0)
            else:
                self.profile_region_combo.setCurrentIndex(-1)
                self.start_detection_btn.setEnabled(False)

            self.log_message(f"Loaded {len(regions)} regions for profile management", "INFO")
        else:
            # No regions found - add a message
            self.profile_region_combo.addItem("No monitoring regions found")
            self.profile_region_combo.setEnabled(False)
            self.start_detection_btn.setEnabled(False)
            self.log_message("No monitoring regions found for profile management", "WARNING")

    def _on_profile_region_selected(self, index):
        """Handle region selection in profile tab."""
        if index < 0:
            self.start_detection_btn.setEnabled(False)
            self.profile_preview_label.setText("No region selected")
            return

        # Get selected region and update preview
        selected_region = self.profile_region_combo.get_selected_region()

        if selected_region:
            # Update preview with screenshot
            if selected_region.screenshot_path:
                load_result = self.region_service.load_region_screenshot(selected_region)
                if load_result.is_success:
                    screenshot = load_result.value
                    pixmap_result = self.screenshot_service.to_pyside_pixmap(screenshot)
                    if pixmap_result.is_success:
                        pixmap = pixmap_result.value
                        # Scale to fit while maintaining aspect ratio
                        scaled_pixmap = pixmap.scaled(
                            self.profile_preview_label.width(),
                            self.profile_preview_label.height(),
                            Qt.KeepAspectRatio,
                            Qt.SmoothTransformation
                        )
                        self.profile_preview_label.setPixmap(scaled_pixmap)
                    else:
                        self.profile_preview_label.setText("Error loading preview")
                else:
                    self.profile_preview_label.setText("Screenshot not available")

            # Enable start button if we have a valid screenshot path
            self.start_detection_btn.setEnabled(bool(selected_region.screenshot_path))
        else:
            self.profile_preview_label.setText("No region selected")
            self.start_detection_btn.setEnabled(False)

    def _start_profile_detection(self):
        """Start the OCR parameter detection process."""
        # Get selected region
        selected_region = self.profile_region_combo.get_selected_region()
        if not selected_region or not selected_region.screenshot_path:
            self.log_message("No valid region selected", "WARNING")
            return

        # Reset UI state
        self.profile_verification_widget.setVisible(False)
        self.profile_pattern_group.setVisible(False)

        # Update status
        self.profile_status_label.setText("Analyzing image and detecting OCR parameters...")
        QApplication.processEvents()

        # Store path for later use
        self.current_image_path = selected_region.screenshot_path

        # Detect OCR parameters using OCR Analysis Service
        ocr_profile_result = self.ocr_analysis_service.detect_optimal_ocr_parameters(selected_region.screenshot_path)

        if ocr_profile_result.is_failure:
            self.profile_status_label.setText(f"Detection failed: {ocr_profile_result.error}")
            return

        self.ocr_profile = ocr_profile_result.value

        # Update status
        self.profile_status_label.setText("Testing OCR with detected parameters...")
        QApplication.processEvents()

        # Test OCR with detected parameters
        self._test_profile_ocr_parameters()

        # Show verification widget
        self.profile_verification_widget.setVisible(True)

        # Update OCR parameter controls
        self.scale_factor_spin.setValue(self.ocr_profile.scale_factor)
        self.block_size_spin.setValue(self.ocr_profile.threshold_block_size)
        self.c_value_spin.setValue(self.ocr_profile.threshold_c)
        self.denoise_h_spin.setValue(self.ocr_profile.denoise_h)
        self.config_text.setText(self.ocr_profile.tesseract_config)
        self.invert_colors_check.setChecked(self.ocr_profile.invert_colors)

        # Show advanced settings
        self.advanced_settings_check.setChecked(True)

        # Update status
        self.profile_status_label.setText("Please verify if the extracted text is correct")

    def _test_profile_ocr_parameters(self):
        """Test OCR with the detected parameters."""
        try:
            import PIL.Image

            # Load the image
            image = PIL.Image.open(self.current_image_path)

            # Extract text using the detected parameters
            extract_result = self.ocr_service.extract_text_with_profile(image, self.ocr_profile)

            if extract_result.is_success:
                self.extracted_text = extract_result.value

                # Trim and clean up the text for display
                display_text = self.extracted_text.strip()
                # Truncate if too long
                if len(display_text) > 50:
                    display_text = display_text[:47] + "..."

                self.profile_extracted_text_label.setText(display_text)

                # Auto-detect likely formats based on the extracted text
                self._auto_detect_formats()
            else:
                self.extracted_text = "Failed to extract text"
                error_msg = str(extract_result.error)
                if len(error_msg) > 50:
                    error_msg = error_msg[:47] + "..."
                self.profile_extracted_text_label.setText(f"Error: {error_msg}")

        except Exception as e:
            self.extracted_text = f"Error testing OCR: {e}"
            error_msg = str(e)
            if len(error_msg) > 50:
                error_msg = error_msg[:47] + "..."
            self.profile_extracted_text_label.setText(f"Error: {error_msg}")

    def _on_profile_text_verified(self):
        """User confirmed the extracted text is accurate."""
        # Update UI
        self.profile_pattern_group.setVisible(True)
        self.profile_status_label.setText("Analyzing text formats...")

        # Auto-detect formats and run initial pattern test
        self._auto_detect_formats()
        self._test_profile_patterns()

    def _on_profile_text_rejected(self):
        """User rejected the extracted text."""
        # Adjust parameters slightly
        if hasattr(self, 'ocr_profile'):
            # Increase scale factor
            self.ocr_profile.scale_factor += 0.5
            if self.ocr_profile.scale_factor > 4.0:
                self.ocr_profile.scale_factor = 1.5

            # Try inverting colors if retries > 2
            if hasattr(self, 'retry_count') and self.retry_count > 2:
                self.ocr_profile.invert_colors = not self.ocr_profile.invert_colors

            # Keep track of retry attempts
            if not hasattr(self, 'retry_count'):
                self.retry_count = 1
            else:
                self.retry_count += 1

            # Update status
            self.profile_status_label.setText(f"Retrying with adjusted settings (attempt {self.retry_count})...")
            QApplication.processEvents()

            # Test again with modified parameters
            self._test_profile_ocr_parameters()

            # Update OCR parameter controls
            self.scale_factor_spin.setValue(self.ocr_profile.scale_factor)
            self.block_size_spin.setValue(self.ocr_profile.threshold_block_size)
            self.c_value_spin.setValue(self.ocr_profile.threshold_c)
            self.denoise_h_spin.setValue(self.ocr_profile.denoise_h)
            self.config_text.setText(self.ocr_profile.tesseract_config)
            self.invert_colors_check.setChecked(self.ocr_profile.invert_colors)

    def _auto_detect_formats(self):
        """Auto-detect likely formats from the extracted text and configure the UI accordingly."""
        if not hasattr(self, 'extracted_text'):
            return

        text = self.extracted_text
        formats_detected = []

        # Check for dollar signs
        has_dollar = '$' in text
        self.profile_dollar_check.setChecked(has_dollar)
        if has_dollar:
            formats_detected.append("dollar sign ($)")

        # Check for Euro signs
        has_euro = '€' in text
        self.profile_euro_check.setChecked(has_euro)
        if has_euro:
            formats_detected.append("euro symbol (€)")

        # Check for Pound signs
        has_pound = '£' in text
        self.profile_pound_check.setChecked(has_pound)
        if has_pound:
            formats_detected.append("pound symbol (£)")

        # Check for negative formats
        has_parentheses = bool(re.search(r'\(\$?[\d,]+\.?\d*\)', text))
        has_minus = bool(re.search(r'-\$?[\d,]+\.?\d*', text))

        if has_parentheses and has_minus:
            self.profile_negative_both_radio.setChecked(True)
            formats_detected.append("both negative formats")
        elif has_parentheses:
            self.profile_negative_parentheses_radio.setChecked(True)
            formats_detected.append("parentheses for negative values")
        elif has_minus:
            self.profile_negative_minus_radio.setChecked(True)
            formats_detected.append("minus signs for negative values")
        else:
            # Default if no negatives detected
            self.profile_negative_both_radio.setChecked(True)

        # Check for plain numbers
        has_plain = bool(re.search(r'(?<!\$|€|£)(-?[\d,]+\.?\d*)', text))
        self.profile_plain_number_check.setChecked(has_plain)
        if has_plain:
            formats_detected.append("plain numbers")

        # Update status with detected formats
        if formats_detected:
            self.profile_status_label.setText(f"Auto-detected formats: {', '.join(formats_detected)}")

    def _test_profile_patterns(self):
        """Generate and test pattern based on user selections."""
        # Get pattern dictionary
        patterns = self._build_profile_custom_pattern()
        self.patterns = patterns

        # Test pattern extraction
        test_result = self.ocr_analysis_service.test_pattern_extraction(self.extracted_text, patterns)

        if test_result.is_success:
            values = test_result.value

            if values:
                # Remove duplicates and sort values
                unique_values = []
                for value in values:
                    # Round to 2 decimal places for comparison
                    rounded = round(value, 2)
                    if rounded not in [round(v, 2) for v in unique_values]:
                        unique_values.append(value)

                # Sort values (usually we want the lowest/negative value first for P&L)
                unique_values.sort()

                # Format results
                results_text = ""
                for value in unique_values:
                    results_text += f"{value:.2f}, "

                # Remove trailing comma and space
                if results_text:
                    results_text = results_text[:-2]

                self.profile_pattern_results.setText(results_text)

                # If we found a single value, highlight it as the likely P&L
                if len(unique_values) == 1:
                    self.profile_status_label.setText(f"Detected P&L value: {unique_values[0]:.2f}")
                elif len(unique_values) > 0:
                    min_value = min(unique_values)
                    self.profile_status_label.setText(f"Multiple values found. Minimum (likely P&L): {min_value:.2f}")
            else:
                self.profile_pattern_results.setText("No values detected")
                self.profile_status_label.setText("No numeric values detected with current pattern settings")
        else:
            error_msg = str(test_result.error)
            if len(error_msg) > 30:
                error_msg = error_msg[:27] + "..."
            self.profile_pattern_results.setText(f"Error: {error_msg}")

    def _build_profile_custom_pattern(self):
        """Build pattern dictionary based on user selections."""
        # Start with a pattern type based on selected currency
        pattern_type = "regular"
        pattern = None

        # Determine pattern type and base pattern
        if self.profile_dollar_check.isChecked():
            pattern_type = "dollar"
            pattern = r'\$([\d,]+\.?\d*)'
        elif self.profile_euro_check.isChecked():
            pattern_type = "euro"
            pattern = r'€([\d,]+\.?\d*)'
        elif self.profile_pound_check.isChecked():
            pattern_type = "pound"
            pattern = r'£([\d,]+\.?\d*)'
        elif self.profile_plain_number_check.isChecked():
            pattern = r'(?<!\$|€|£)(-?[\d,]+\.?\d*)'
        else:
            # Fallback pattern
            pattern = r'(-?[\d,]+\.?\d*)'

        # Return a dictionary with single entry
        return {pattern_type: pattern}

    def _refresh_ui_after_region_change(self):
        """Refresh all UI components that depend on region data."""
        try:
            # Update monitoring dropdown in lockout tab
            self._update_monitoring_dropdown()

            # Update profile tab's region combo
            self._load_profile_regions()

            # Allow UI to update
            QApplication.processEvents()
        except Exception as e:
            self.log_message(f"Error refreshing UI: {str(e)}", "ERROR")
            self.logger.error(f"Error in UI refresh: {e}", exc_info=True)

    def _on_tab_changed(self, index):
        """Handle tab changes by refreshing data as needed."""
        tab_name = self.tab_widget.tabText(index)
        if tab_name == "Lockout Testing":
            self._update_monitoring_dropdown()
        elif tab_name == "Profile Management":
            self._load_profile_regions()

    def _handle_result(self, result: Result, success_message=None, error_message="Operation failed",
                       error_level="ERROR"):
        """Standard handler for Result objects."""
        if result.is_success:
            if success_message:
                self.log_message(success_message, "SUCCESS")
            return result.value
        else:
            self.log_message(f"{error_message}: {result.error}", error_level)
            return None

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

# At the top of the main section
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Don't call initialize_app() again if it's already been called
    from src.application.app import get_container

    if get_container() is None:
        from src.application.app import initialize_app

        initialize_app()

    window = TradingMonitorTestApp()
    window.show()
    sys.exit(app.exec())