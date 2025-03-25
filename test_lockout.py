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
import sys
import time
import logging
from typing import List, Dict, Any, Optional, Tuple
import traceback

from PySide6 import QtCore

from src.domain.models.platform_profile import PlatformProfile
from src.domain.services.i_region_service import IRegionService
from src.domain.models.region_model import Region

# Add the project root to the Python path so we can import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
    QTextEdit, QMessageBox, QTabWidget, QFileDialog, QLineEdit, QGroupBox, QComboBox,
    QListWidget, QListWidgetItem, QSplitter, QFormLayout, QSpinBox, QDoubleSpinBox, QCheckBox
)
from PySide6.QtGui import QPixmap, QColor, QTextCursor
from PySide6.QtCore import Qt, QSize, QObject, Signal, QThread

# Import application initialization
from src.application.app import initialize_app, get_container

# Import domain interfaces - only import what we actually use
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
                 on_edit, on_delete, on_view, parent=None):
        super().__init__(parent)
        self.region_id = region_id
        self.region = region
        self.on_edit = on_edit
        self.on_delete = on_delete
        self.on_view = on_view

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Region info
        x, y, w, h = region
        label = QLabel(f"{region_id}: ({x}, {y}, {w}, {h})")
        layout.addWidget(label, 1)

        # View button
        view_btn = QPushButton("View")
        view_btn.setMaximumWidth(60)
        view_btn.clicked.connect(lambda: self.on_view(self.region_id, self.region))
        layout.addWidget(view_btn)

        # Edit button
        edit_btn = QPushButton("Edit")
        edit_btn.setMaximumWidth(60)
        edit_btn.clicked.connect(lambda: self.on_edit(self.region_id, self.region))
        layout.addWidget(edit_btn)

        # Delete button
        delete_btn = QPushButton("Delete")
        delete_btn.setMaximumWidth(60)
        delete_btn.clicked.connect(lambda: self.on_delete(self.region_id))
        layout.addWidget(delete_btn)


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
        self.captured_screenshot = None
        self.is_monitoring = False

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

        # Create and add platform selector toolbar
        self.platform_toolbar = PlatformSelectorToolbar(self.platform_selection_service, self)
        self.addToolBar(self.platform_toolbar)
        self.platform_toolbar.platform_changed.connect(self._on_global_platform_changed)

        # Create tabs
        self._create_region_tab()
        self._create_verification_tab()
        self._create_lockout_tab()
        self._create_settings_tab()
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

        test_ocr_btn = QPushButton("Test OCR")
        test_ocr_btn.clicked.connect(self._on_test_ocr)
        m_btn_layout.addWidget(test_ocr_btn)

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

        # Screenshot display
        screenshot_group = QGroupBox("Screenshot Preview")
        s_layout = QVBoxLayout(screenshot_group)

        self.screenshot_label = QLabel("No screenshot captured")
        self.screenshot_label.setAlignment(Qt.AlignCenter)
        self.screenshot_label.setMinimumHeight(200)
        self.screenshot_label.setStyleSheet("border: 1px solid #ccc")
        s_layout.addWidget(self.screenshot_label)

        self.ocr_text = QTextEdit()
        self.ocr_text.setReadOnly(True)
        self.ocr_text.setMaximumHeight(100)
        self.ocr_text.setPlaceholderText("OCR Text will appear here")
        s_layout.addWidget(self.ocr_text)

        layout.addWidget(screenshot_group)

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

    def _create_settings_tab(self):
        """Create the settings tab."""
        settings_tab = QWidget()
        layout = QVBoxLayout(settings_tab)

        # Global settings
        global_group = QGroupBox("Global Settings")
        global_layout = QFormLayout(global_group)

        # Stop loss threshold
        self.global_threshold_spin = QDoubleSpinBox()
        self.global_threshold_spin.setRange(-10000, 0)
        self.global_threshold_spin.setValue(-100)
        self.global_threshold_spin.setPrefix("$ ")
        self.global_threshold_spin.setDecimals(2)
        global_layout.addRow("Stop Loss Threshold:", self.global_threshold_spin)

        # Lockout duration
        self.global_duration_spin = QSpinBox()
        self.global_duration_spin.setRange(1, 720)
        self.global_duration_spin.setValue(15)
        self.global_duration_spin.setSuffix(" minutes")
        global_layout.addRow("Lockout Duration:", self.global_duration_spin)

        # Save button
        save_settings_btn = QPushButton("Save Global Settings")
        save_settings_btn.clicked.connect(self._on_save_global_settings)
        global_layout.addRow("", save_settings_btn)

        layout.addWidget(global_group)

        # Test connection buttons
        conn_group = QGroupBox("Test Connections")
        conn_layout = QVBoxLayout(conn_group)

        # Buttons for various tests
        test_ocr_service_btn = QPushButton("Test OCR Service")
        test_ocr_service_btn.clicked.connect(lambda: self._test_service("ocr"))
        conn_layout.addWidget(test_ocr_service_btn)

        test_screenshot_btn = QPushButton("Test Screenshot Service")
        test_screenshot_btn.clicked.connect(lambda: self._test_service("screenshot"))
        conn_layout.addWidget(test_screenshot_btn)

        test_cold_turkey_btn = QPushButton("Test Cold Turkey Connection")
        test_cold_turkey_btn.clicked.connect(lambda: self._test_service("coldturkey"))
        conn_layout.addWidget(test_cold_turkey_btn)

        layout.addWidget(conn_group)

        # Add spacer
        layout.addStretch(1)

        # Add to tabs
        self.tab_widget.addTab(settings_tab, "Settings")

    def _create_profile_tab(self):
        """Create the profile management tab."""
        profile_tab = QWidget()
        layout = QVBoxLayout(profile_tab)

        # Profile details
        profile_group = QGroupBox("OCR Profile Settings")
        profile_layout = QFormLayout(profile_group)

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

        layout.addWidget(profile_group)

        # Color inversion option
        self.invert_colors_check = QCheckBox("Invert Colors (for light text on dark background)")
        profile_layout.addRow("", self.invert_colors_check)


        # Pattern settings
        patterns_group = QGroupBox("Regex Patterns")
        patterns_layout = QFormLayout(patterns_group)

        self.dollar_pattern_text = QLineEdit()
        self.dollar_pattern_text.setText(r'\$([\d,]+\.?\d*)')
        patterns_layout.addRow("Dollar Pattern:", self.dollar_pattern_text)

        self.negative_pattern_text = QLineEdit()
        self.negative_pattern_text.setText(r'\((?:\$)?([\d,]+\.?\d*)\)')
        patterns_layout.addRow("Negative Pattern:", self.negative_pattern_text)

        self.regular_pattern_text = QLineEdit()
        self.regular_pattern_text.setText(r'(?<!\$)(-?[\d,]+\.?\d*)')
        patterns_layout.addRow("Regular Pattern:", self.regular_pattern_text)

        layout.addWidget(patterns_group)

        # Buttons
        button_layout = QHBoxLayout()

        save_btn = QPushButton("Save Profile")
        save_btn.clicked.connect(self._save_platform_profile)
        button_layout.addWidget(save_btn)

        reset_btn = QPushButton("Reset to Default")
        reset_btn.clicked.connect(self._reset_platform_profile)
        button_layout.addWidget(reset_btn)

        test_btn = QPushButton("Test OCR with Profile")
        test_btn.clicked.connect(self._test_ocr_with_profile)
        button_layout.addWidget(test_btn)

        layout.addLayout(button_layout)

        # In _create_profile_tab method, add this with the other buttons
        test_pipeline_btn = QPushButton("Test Full OCR Pipeline")
        test_pipeline_btn.clicked.connect(self._test_profile_ocr_pipeline)
        button_layout.addWidget(test_pipeline_btn)

        # OCR result display
        result_group = QGroupBox("OCR Test Results")
        result_layout = QVBoxLayout(result_group)

        self.profile_ocr_text = QTextEdit()
        self.profile_ocr_text.setReadOnly(True)
        self.profile_ocr_text.setPlaceholderText("OCR results will appear here")
        result_layout.addWidget(self.profile_ocr_text)

        layout.addWidget(result_group, 1)

        # Add to tabs
        self.tab_widget.addTab(profile_tab, "Profile Management")

    def _populate_platform_list(self):
        """Populate the global platform dropdown."""
        current_platform = self.platform_selection_service.get_current_platform()
        try:
            # Get supported platforms from platform detection service
            result = self.platform_detection.get_supported_platforms()

            if result.is_success:
                platforms = list(result.value.keys())
                # We only need to update the global platform toolbar
                self.platform_toolbar.update_platforms(platforms, current_platform)
            else:
                self.log_message(f"Failed to get platform list: {result.error}", "ERROR")
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

            self.global_threshold_spin.setValue(threshold if threshold < 0 else -threshold)
            self.global_duration_spin.setValue(duration)

            # Copy to lockout tab
            self.threshold_spin.setValue(threshold if threshold < 0 else -threshold)
            self.duration_spin.setValue(duration)

            # Load current platform
            current = self.config_repository.get_current_platform()
            if current:
                # Update toolbar with current platform
                self.platform_toolbar.update_platforms(
                    self.platform_detection.get_supported_platforms().value.keys(),
                    current
                )

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

                # Regex patterns
                patterns = profile.numeric_patterns
                if "dollar" in patterns:
                    self.dollar_pattern_text.setText(patterns["dollar"])
                if "negative" in patterns:
                    self.negative_pattern_text.setText(patterns["negative"])
                if "regular" in patterns:
                    self.regular_pattern_text.setText(patterns["regular"])

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
                invert_colors = self.invert_colors_check.isChecked()
            )

            # Create patterns dictionary
            patterns = {
                "dollar": self.dollar_pattern_text.text(),
                "negative": self.negative_pattern_text.text(),
                "regular": self.regular_pattern_text.text()
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

    def _test_ocr_with_profile(self):
        """Test OCR using the current profile settings."""
        if not self.captured_screenshot:
            self.log_message("No screenshot captured. Please capture one first.", "WARNING")
            return

        platform = self.platform_selection_service.get_current_platform()
        if not platform:
            self.log_message("No platform selected", "WARNING")
            return

        try:
            # Get the current profile
            profile_result = self.profile_service.get_profile(platform)

            if profile_result.is_failure:
                self.log_message(f"Failed to get profile: {profile_result.error}", "ERROR")
                return

            profile = profile_result.value

            # Process the screenshot
            self.log_message(f"Testing OCR with profile for {platform}...", "INFO")

            # Extract text
            extract_result = self.ocr_service.extract_text_with_profile(
                self.captured_screenshot, profile.ocr_profile)

            if extract_result.is_failure:
                self.log_message(f"Text extraction failed: {extract_result.error}", "ERROR")
                return

            text = extract_result.value

            # Extract numeric values
            values_result = self.ocr_service.extract_numeric_values_with_patterns(
                text, profile.numeric_patterns)

            if values_result.is_failure:
                self.log_message(f"Value extraction failed: {values_result.error}", "ERROR")
                self.profile_ocr_text.setText(f"Extracted text:\n{text}\n\nValue extraction failed")
                return

            values = values_result.value

            # Display results
            result_text = f"Extracted text:\n{text}\n\n"
            result_text += f"Numeric values:\n{values}\n\n"

            if values:
                min_value = min(values)
                result_text += f"Minimum value (P&L): {min_value}\n"
                self.log_message(f"OCR test successful. Found values: {values}", "SUCCESS")
                self.log_message(f"Minimum value: {min_value}", "INFO")
            else:
                result_text += "No numeric values found"
                self.log_message("OCR test completed, but no numeric values found", "WARNING")

            self.profile_ocr_text.setText(result_text)

        except Exception as e:
            self.log_message(f"Error in OCR test: {str(e)}", "ERROR")
            self.logger.error(f"Error in OCR test: {e}", exc_info=True)

    def _refresh_verified_blocks(self):
        """Refresh the list of verified blocks."""
        try:
            self.verified_list.clear()

            result = self.verification_service.get_verified_blocks()
            if result.is_success:
                blocks = result.value
                for block in blocks:
                    platform = block.get("platform", "Unknown")
                    block_name = block.get("block_name", "Unknown")

                    item = QListWidgetItem(f"{platform}: {block_name}")
                    self.verified_list.addItem(item)

                if not blocks:
                    self.verified_list.addItem("No verified blocks found")

                self.log_message(f"Found {len(blocks)} verified blocks", "INFO")
            else:
                self.log_message(f"Failed to get verified blocks: {result.error}", "ERROR")
                self.verified_list.addItem("Error loading verified blocks")
        except Exception as e:
            self.log_message(f"Error refreshing verified blocks: {str(e)}", "ERROR")
            self.logger.error(f"Error refreshing verified blocks: {e}", exc_info=True)

    def _on_global_platform_changed(self, platform: str) -> None:
        """Handle global platform change."""
        # No need to check against stored value - service manages that

        # Load regions for this platform
        self._load_regions_for_platform()

        # Clear screenshot preview when switching platforms
        self.captured_screenshot = None
        self.screenshot_label.setText("No screenshot captured")
        self.screenshot_label.setPixmap(QPixmap())
        self.ocr_text.clear()
        self.profile_ocr_text.clear()

        # Load profile for new platform
        self._load_platform_profile(platform)

        self.log_message(f"Selected platform: {platform}", "INFO")

    def _load_regions_for_platform(self):
        """Load regions for the current platform."""
        # Clear existing lists
        self.monitoring_list.clear()
        self.flatten_list.clear()

        # Get current platform from service
        current_platform = self.platform_selection_service.get_current_platform()

        # Load monitoring regions
        monitor_result = self.region_service.get_regions_by_platform(current_platform, "monitor")

        if monitor_result.is_success:
            for region in monitor_result.value:
                self._add_region_to_list(region.name, region.coordinates, "monitor")
        else:
            self.log_message(f"Failed to load monitoring regions: {monitor_result.error}", "WARNING")

        # Load flatten regions
        flatten_result = self.region_service.get_regions_by_platform(current_platform, "flatten")
        if flatten_result.is_success:
            for region in flatten_result.value:
                self._add_region_to_list(region.name, region.coordinates, "flatten")
        else:
            self.log_message(f"Failed to load flatten regions: {flatten_result.error}", "WARNING")

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
        if not path:
            self.log_message("No path specified", "WARNING")
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
            on_delete=lambda id: self._on_delete_region(id, region_type),
            on_view=lambda id, r: self._on_view_region(id, r, region_type)
        )
        item.setSizeHint(widget.sizeHint())
        list_widget.addItem(item)
        list_widget.setItemWidget(item, widget)

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

        self.log_message(f"Added {region_type} region '{name}': {coordinates}", "SUCCESS")

        # If it's a monitoring region, display the screenshot and process OCR
        if region_type == "monitor":
            # Load and display the screenshot
            if region.screenshot_path:
                load_result = self.region_service.load_region_screenshot(region)
                if load_result.is_success:
                    self.captured_screenshot = load_result.value
                    # Display screenshot and process OCR
                    pixmap_result = self.screenshot_service.to_pyside_pixmap(self.captured_screenshot)
                    if pixmap_result.is_success:
                        pixmap = pixmap_result.value
                        self.screenshot_label.setPixmap(pixmap.scaled(
                            self.screenshot_label.width(),
                            self.screenshot_label.height(),
                            Qt.KeepAspectRatio
                        ))
                        # Run OCR on the screenshot
                        self._on_test_ocr()
                    else:
                        self.log_message(f"Error displaying screenshot: {pixmap_result.error}", "ERROR")
                else:
                    self.log_message(f"Error loading screenshot: {load_result.error}", "ERROR")

            # Update the monitoring dropdown
            self._update_monitoring_dropdown()

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
                new_widget = RegionEntry(
                    region_id, new_coordinates,
                    on_edit=lambda id, r: self._on_edit_region(id, r, region_type),
                    on_delete=lambda id: self._on_delete_region(id, region_type),
                    on_view=lambda id, r: self._on_view_region(id, r, region_type)
                )
                item.setSizeHint(new_widget.sizeHint())
                list_widget.setItemWidget(item, new_widget)
                break

        self.log_message(f"Updated {region_type} region {region_id}: {new_coordinates}", "SUCCESS")

        # If it's a monitoring region, display the screenshot and process OCR
        if region_type == "monitor":
            # Load and display the screenshot
            if region.screenshot_path:
                load_result = self.region_service.load_region_screenshot(region)
                if load_result.is_success:
                    self.captured_screenshot = load_result.value
                    # Display screenshot
                    pixmap_result = self.screenshot_service.to_pyside_pixmap(self.captured_screenshot)
                    if pixmap_result.is_success:
                        pixmap = pixmap_result.value
                        self.screenshot_label.setPixmap(pixmap.scaled(
                            self.screenshot_label.width(),
                            self.screenshot_label.height(),
                            Qt.KeepAspectRatio
                        ))
                        # Run OCR on the screenshot
                        self._on_test_ocr()
                    else:
                        self.log_message(f"Error displaying screenshot: {pixmap_result.error}", "ERROR")
                else:
                    self.log_message(f"Error loading screenshot: {load_result.error}", "ERROR")

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

        # Update monitoring dropdown if needed
        if region_type == "monitor":
            self._update_monitoring_dropdown()

    # In _on_view_region method
    def _on_view_region(self, region_id, coordinates, region_type):
        """Display a saved region screenshot."""
        self.log_message(f"Viewing region {region_id}...", "INFO")

        current_platform = self.platform_selection_service.get_current_platform()

        # Get the region from the service
        result = self.region_service.get_region(current_platform, region_type, region_id)

        if result.is_failure:
            self.log_message(f"Failed to get region: {result.error}", "ERROR")
            return

        region = result.value

        # Load screenshot
        if region.screenshot_path:
            load_result = self.region_service.load_region_screenshot(region)
            if load_result.is_success:
                # Store the loaded image
                self.captured_screenshot = load_result.value

                # Display screenshot
                pixmap_result = self.screenshot_service.to_pyside_pixmap(self.captured_screenshot)
                if pixmap_result.is_success:
                    pixmap = pixmap_result.value
                    self.screenshot_label.setPixmap(pixmap.scaled(
                        self.screenshot_label.width(),
                        self.screenshot_label.height(),
                        Qt.KeepAspectRatio
                    ))
                    self.log_message(f"Displayed saved screenshot for {region_id}", "SUCCESS")

                    # Run OCR test with profile if it's a monitoring region
                    if region_type == "monitor":
                        self._on_test_ocr()
                else:
                    self.log_message(f"Error displaying screenshot: {pixmap_result.error}", "ERROR")
            else:
                self.log_message(f"Error loading screenshot: {load_result.error}", "WARNING")
                # Fall back to capturing new screenshot
                self._capture_and_process_region(region.coordinates)
        else:
            self.log_message(f"No saved screenshot found for {region_id}, capturing new one", "WARNING")
            self._capture_and_process_region(region.coordinates)

    # In test_lockout.py -> _capture_and_process_region method
    def _capture_and_process_region(self, region):
        """Capture and process a region using the current platform profile."""
        # Get current platform
        platform = self.platform_selection_service.get_current_platform()

        # Capture the screenshot
        result = self.screenshot_service.capture_region(region)

        if result.is_success:
            self.captured_screenshot = result.value
            self.log_message("Screenshot captured successfully", "INFO")

            # Convert to QPixmap and display
            pixmap_result = self.screenshot_service.to_pyside_pixmap(self.captured_screenshot)
            if pixmap_result.is_success:
                pixmap = pixmap_result.value
                self.screenshot_label.setPixmap(pixmap.scaled(
                    self.screenshot_label.width(),
                    self.screenshot_label.height(),
                    Qt.KeepAspectRatio
                ))

                # Process OCR using platform profile
                if platform:
                    self._on_test_ocr()
                else:
                    self.log_message("No platform selected for OCR processing", "WARNING")
            else:
                self.log_message(f"Error converting to pixmap: {pixmap_result.error}", "ERROR")
        else:
            self.log_message(f"Error capturing screenshot: {result.error}", "ERROR")

    def _on_test_ocr(self):
        """Test OCR on the captured screenshot."""
        if not self.captured_screenshot:
            self.log_message("No screenshot captured", "WARNING")
            return

        self.log_message("Extracting text from screenshot...", "INFO")

        # Get current platform
        platform = self.platform_selection_service.get_current_platform()
        if not platform:
            self.log_message("No platform selected", "WARNING")
            return

        # Get profile for platform
        profile_result = self.profile_service.get_profile(platform)
        if profile_result.is_failure:
            self.log_message(f"Failed to get profile: {profile_result.error}", "WARNING")
            # Fall back to default profile if needed
            from src.domain.models.platform_profile import OcrProfile
            profile = PlatformProfile(platform_name="Default", ocr_profile=OcrProfile())
        else:
            profile = profile_result.value

        # Extract text using OCR with profile
        result = self.ocr_service.extract_text_with_profile(
            self.captured_screenshot, profile.ocr_profile)

        if result.is_success:
            text = result.value
            self.log_message("Text extracted successfully", "SUCCESS")
            self.ocr_text.setText(text)

            # Extract numeric values with patterns
            numbers_result = self.ocr_service.extract_numeric_values_with_patterns(
                text, profile.numeric_patterns)

            if numbers_result.is_success:
                numbers = numbers_result.value
                if numbers:
                    min_value = min(numbers)
                    self.log_message(f"Numeric values found: {numbers}", "INFO")
                    self.log_message(f"Minimum value (P&L): {min_value}", "INFO")
                else:
                    self.log_message("No numeric values found in the text", "WARNING")
            else:
                self.log_message(f"Error extracting numeric values: {numbers_result.error}", "ERROR")
        else:
            self.log_message(f"Error extracting text: {result.error}", "ERROR")

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

    def _on_save_global_settings(self):
        """Save global settings."""
        threshold = self.global_threshold_spin.value()
        duration = self.global_duration_spin.value()

        # Ensure threshold is negative
        if threshold > 0:
            threshold = -threshold

        # Save threshold
        result1 = self.config_repository.set_stop_loss_threshold(threshold)

        # Save duration
        result2 = self.config_repository.set_lockout_duration(duration)

        if result1.is_success and result2.is_success:
            self.log_message("Global settings saved successfully", "SUCCESS")

            # Update lockout tab values
            self.threshold_spin.setValue(threshold)
            self.duration_spin.setValue(duration)
        else:
            if result1.is_failure:
                self.log_message(f"Failed to save threshold: {result1.error}", "ERROR")
            if result2.is_failure:
                self.log_message(f"Failed to save duration: {result2.error}", "ERROR")

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

    def _test_service(self, service_type):
        """Test various services for functionality."""
        if service_type == "ocr":
            try:
                test_text = "Sample OCR test"
                result = self.ocr_service.extract_numeric_values(test_text)

                if result.is_success:
                    self.log_message("OCR Service is working correctly", "SUCCESS")
                else:
                    self.log_message(f"OCR Service test returned error: {result.error}", "WARNING")
            except Exception as e:
                self.log_message(f"OCR Service Error: {str(e)}", "ERROR")
                self.logger.error(f"OCR Service Error: {e}", exc_info=True)

        elif service_type == "screenshot":
            try:
                # Try to get screen information using screenshot service
                app = QApplication.instance()
                screens = app.screens()
                screen_info = []
                for i, screen in enumerate(screens):
                    geo = screen.geometry()
                    screen_info.append(f"Screen {i + 1}: {geo.width()}x{geo.height()} at ({geo.x()},{geo.y()})")

                # Try to capture a small region
                region = (0, 0, 10, 10)  # Small region at top-left
                capture_result = self.screenshot_service.capture_region(region)

                if capture_result.is_success:
                    self.log_message(f"Screenshot Service OK ({len(screens)} screens detected)", "SUCCESS")
                    for info in screen_info:
                        self.log_message(info, "INFO")
                else:
                    self.log_message(f"Screenshot Service Error: {capture_result.error}", "ERROR")
            except Exception as e:
                self.log_message(f"Screenshot Service Error: {str(e)}", "ERROR")
                self.logger.error(f"Screenshot Service Error: {e}", exc_info=True)

        elif service_type == "coldturkey":
            try:
                # Check if Cold Turkey path is configured
                if self.cold_turkey_service.is_blocker_path_configured():
                    path_result = self.cold_turkey_service.get_blocker_path()
                    if path_result.is_success:
                        self.log_message(f"Cold Turkey Service OK (Path: {path_result.value})", "SUCCESS")

                        # Check verified blocks
                        blocks_result = self.cold_turkey_service.get_verified_blocks()
                        if blocks_result.is_success:
                            blocks = blocks_result.value
                            self.log_message(f"Found {len(blocks)} verified blocks", "INFO")
                        else:
                            self.log_message(f"Error checking verified blocks: {blocks_result.error}", "WARNING")
                    else:
                        self.log_message(f"Cold Turkey Path Error: {path_result.error}", "ERROR")
                else:
                    self.log_message("Cold Turkey Blocker path not configured", "WARNING")
            except Exception as e:
                self.log_message(f"Cold Turkey Service Error: {str(e)}", "ERROR")
                self.logger.error(f"Cold Turkey Service Error: {e}", exc_info=True)

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

    # Add a new method to test_lockout.py to test the full profile-based OCR process
    def _test_profile_ocr_pipeline(self):
        """Test the full OCR pipeline using profiles."""
        platform = self.platform_selection_service.get_current_platform()
        if not platform:
            self.log_message("No platform selected", "WARNING")
            return

        if not self.captured_screenshot:
            self.log_message("No screenshot captured", "WARNING")
            return

        self.log_message(f"Testing full OCR pipeline for {platform}...", "INFO")

        # Get the profile
        profile_result = self.profile_service.get_profile(platform)
        if profile_result.is_failure:
            self.log_message(f"Failed to get profile: {profile_result.error}", "ERROR")
            return

        profile = profile_result.value

        # Show profile settings
        ocr = profile.ocr_profile
        self.log_message(f"Using profile with scale={ocr.scale_factor}, " +
                         f"block_size={ocr.threshold_block_size}, " +
                         f"c_value={ocr.threshold_c}, " +
                         f"invert={ocr.invert_colors}", "INFO")

        # Extract text
        extract_result = self.ocr_service.extract_text_with_profile(
            self.captured_screenshot, profile.ocr_profile)

        if extract_result.is_failure:
            self.log_message(f"Text extraction failed: {extract_result.error}", "ERROR")
            return

        text = extract_result.value
        self.log_message(f"Extracted text: {text}", "SUCCESS")

        # Extract values
        values_result = self.ocr_service.extract_numeric_values_with_patterns(
            text, profile.numeric_patterns)

        if values_result.is_failure:
            self.log_message(f"Value extraction failed: {values_result.error}", "ERROR")
            return

        values = values_result.value
        if values:
            min_value = min(values)
            self.log_message(f"Extracted values: {values}", "SUCCESS")
            self.log_message(f"Minimum value: {min_value}", "INFO")
        else:
            self.log_message("No numeric values extracted", "WARNING")
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