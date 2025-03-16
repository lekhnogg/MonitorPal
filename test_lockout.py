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

# Add the project root to the Python path so we can import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
    QTextEdit, QMessageBox, QTabWidget, QFileDialog, QLineEdit, QGroupBox, QComboBox,
    QListWidget, QListWidgetItem, QSplitter, QFormLayout, QSpinBox, QDoubleSpinBox
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
        self.monitoring_regions = {}  # name -> (x, y, w, h)
        self.flatten_regions = {}  # name -> (x, y, w, h)
        self.current_platform = "Quantower"  # Default platform
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

        # Create tabs
        self._create_region_tab()
        self._create_verification_tab()
        self._create_lockout_tab()
        self._create_settings_tab()

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

        platform_layout = QFormLayout()
        self.platform_combo = QComboBox()
        platform_layout.addRow("Platform:", self.platform_combo)

        # Platform detection button
        detect_btn = QPushButton("Detect Platform")
        detect_btn.clicked.connect(self._on_detect_platform)
        platform_layout.addRow("", detect_btn)

        top_layout.addLayout(platform_layout)
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

        # Platform selection
        self.verify_platform_combo = QComboBox()
        block_layout.addRow("Platform:", self.verify_platform_combo)

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

        # Platform selection
        platform_group = QGroupBox("Platform")
        platform_layout = QFormLayout(platform_group)

        self.lockout_platform_combo = QComboBox()
        platform_layout.addRow("Platform:", self.lockout_platform_combo)

        layout.addWidget(platform_group)

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

    def _populate_platform_list(self):
        """Populate the platform dropdown with supported platforms."""
        try:
            # Get supported platforms from platform detection service
            result = self.platform_detection.get_supported_platforms()

            if result.is_success:
                platforms = list(result.value.keys())

                # Update all platform dropdowns
                for combo in [self.platform_combo, self.verify_platform_combo, self.lockout_platform_combo]:
                    combo.clear()
                    combo.addItems(platforms)
                    combo.setCurrentText(self.current_platform)

                    # Connect signal for platform change
                    combo.currentTextChanged.connect(self._on_platform_changed)
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
                self.current_platform = current
                for combo in [self.platform_combo, self.verify_platform_combo, self.lockout_platform_combo]:
                    combo.setCurrentText(current)

            # Refresh verified blocks
            self._refresh_verified_blocks()

            # Load platform-specific regions
            self._load_platform_regions()

            self.log_message("Settings loaded successfully", "INFO")
        except Exception as e:
            self.log_message(f"Error loading settings: {str(e)}", "ERROR")
            self.logger.error(f"Error loading settings: {e}", exc_info=True)

    def _load_platform_regions(self):
        """Load platform-specific regions from config."""
        try:
            platform_settings = self.config_repository.get_platform_settings(self.current_platform)

            # Load monitoring regions
            self.monitoring_regions = {}
            self.monitoring_list.clear()

            if "monitoring_regions" in platform_settings:
                for name, region in platform_settings["monitoring_regions"].items():
                    self.monitoring_regions[name] = tuple(region)
                    self._add_region_to_list(name, region, "monitor")

            # Load flatten regions
            self.flatten_regions = {}
            self.flatten_list.clear()

            if "flatten_regions" in platform_settings:
                for name, region in platform_settings["flatten_regions"].items():
                    self.flatten_regions[name] = tuple(region)
                    self._add_region_to_list(name, region, "flatten")

            self.log_message(
                f"Loaded {len(self.monitoring_regions)} monitoring regions and {len(self.flatten_regions)} flatten regions",
                "INFO")
        except Exception as e:
            self.log_message(f"Error loading platform regions: {str(e)}", "WARNING")
            self.logger.warning(f"Error loading platform regions: {e}", exc_info=True)

    def _save_platform_regions(self):
        """Save platform-specific regions to config."""
        try:
            # Get current platform settings
            platform_settings = self.config_repository.get_platform_settings(self.current_platform)

            # Update with current regions
            platform_settings["monitoring_regions"] = {name: list(region) for name, region in
                                                       self.monitoring_regions.items()}
            platform_settings["flatten_regions"] = {name: list(region) for name, region in self.flatten_regions.items()}

            # Save back to config
            result = self.config_repository.save_platform_settings(self.current_platform, platform_settings)

            if result.is_success:
                self.log_message(f"Saved regions for {self.current_platform}", "SUCCESS")
            else:
                self.log_message(f"Failed to save regions: {result.error}", "ERROR")
        except Exception as e:
            self.log_message(f"Error saving platform regions: {str(e)}", "ERROR")
            self.logger.error(f"Error saving platform regions: {e}", exc_info=True)

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

    def _on_platform_changed(self, platform):
        """Handle platform change in any dropdown."""
        if platform and platform != self.current_platform:
            # Save current platform's regions before switching
            self._save_platform_regions()

            self.current_platform = platform

            # Update all other dropdowns
            for combo in [self.platform_combo, self.verify_platform_combo, self.lockout_platform_combo]:
                if combo.currentText() != platform:
                    combo.blockSignals(True)
                    combo.setCurrentText(platform)
                    combo.blockSignals(False)

            # Load new platform's regions
            self._load_platform_regions()

            # Save current platform to config
            self.config_repository.set_global_setting("current_platform", platform)

            self.log_message(f"Selected platform: {platform}", "INFO")

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
        platform = self.platform_combo.currentText()
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
        if region_type == "monitor":
            name = f"monitor_{len(self.monitoring_regions) + 1}"
            title = "Select P&L Monitoring Region"
            collection = self.monitoring_regions
        else:  # flatten
            name = f"flatten_{len(self.flatten_regions) + 1}"
            title = "Select Position Flatten Button Region"
            collection = self.flatten_regions

        # Use region selector
        self.log_message(f"Starting region selection for {region_type}...", "INFO")

        # Use UI service for region selection to maintain consistency
        region_result = self.ui_service.select_screen_region(f"Please select the {region_type} region")

        if region_result.is_success:
            region = region_result.value

            # Add to collection
            collection[name] = region

            # Add to UI list
            self._add_region_to_list(name, region, region_type)

            self.log_message(f"Added {region_type} region {name}: {region}", "SUCCESS")

            # If it's a monitoring region, capture a screenshot and do OCR
            if region_type == "monitor":
                self._capture_and_process_region(region)

            # Save updated regions to config
            self._save_platform_regions()
        else:
            self.log_message(f"Region selection cancelled or failed: {region_result.error}", "INFO")

    def _on_edit_region(self, region_id, current_region, region_type):
        """Edit an existing region."""
        # Use region selector with previous region as starting point
        self.log_message(f"Editing region {region_id}...", "INFO")

        region_result = self.ui_service.select_screen_region(f"Edit the {region_type} region")

        if region_result.is_success:
            region = region_result.value

            # Update collection
            if region_type == "monitor":
                self.monitoring_regions[region_id] = region
                list_widget = self.monitoring_list
            else:  # flatten
                self.flatten_regions[region_id] = region
                list_widget = self.flatten_list

            # Update UI list
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                widget = list_widget.itemWidget(item)
                if hasattr(widget, 'region_id') and widget.region_id == region_id:
                    new_widget = RegionEntry(
                        region_id, region,
                        on_edit=lambda id, r: self._on_edit_region(id, r, region_type),
                        on_delete=lambda id: self._on_delete_region(id, region_type),
                        on_view=lambda id, r: self._on_view_region(id, r, region_type)
                    )
                    item.setSizeHint(new_widget.sizeHint())
                    list_widget.setItemWidget(item, new_widget)
                    break

            self.log_message(f"Updated {region_type} region {region_id}: {region}", "SUCCESS")

            # If it's a monitoring region, capture a screenshot and do OCR
            if region_type == "monitor":
                self._capture_and_process_region(region)

            # Save updated regions to config
            self._save_platform_regions()
        else:
            self.log_message(f"Region edit cancelled or failed: {region_result.error}", "INFO")

    def _on_delete_region(self, region_id, region_type):
        """Delete an existing region."""
        if region_type == "monitor":
            del self.monitoring_regions[region_id]
            list_widget = self.monitoring_list
        else:  # flatten
            del self.flatten_regions[region_id]
            list_widget = self.flatten_list

        # Remove from UI list
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            widget = list_widget.itemWidget(item)
            if hasattr(widget, 'region_id') and widget.region_id == region_id:
                list_widget.takeItem(i)
                break

        self.log_message(f"Deleted {region_type} region {region_id}", "INFO")

        # Save updated regions to config
        self._save_platform_regions()

    def _on_view_region(self, region_id, region, region_type):
        """Capture and display a region."""
        self.log_message(f"Viewing region {region_id}...", "INFO")

        # Capture the region
        self._capture_and_process_region(region)

    def _capture_and_process_region(self, region):
        """Capture and process a region."""
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

        # Extract text using OCR
        result = self.ocr_service.extract_text(self.captured_screenshot)

        if result.is_success:
            text = result.value
            self.log_message("Text extracted successfully", "SUCCESS")
            self.ocr_text.setText(text)

            # Extract numeric values
            numbers_result = self.ocr_service.extract_numeric_values(text)
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
        platform = self.verify_platform_combo.currentText()
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
        platform = self.lockout_platform_combo.currentText()
        threshold = self.threshold_spin.value()

        # Ensure threshold is negative
        if threshold > 0:
            threshold = -threshold

        # Check if we have monitoring regions
        if not self.monitoring_regions:
            self.log_message("No monitoring regions defined", "ERROR")
            return

        # Get the first monitoring region
        region_id = next(iter(self.monitoring_regions))
        region = self.monitoring_regions[region_id]

        self.log_message(f"Starting monitoring for {platform} with region {region_id}...", "INFO")
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
                region=region,
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
        platform = self.lockout_platform_combo.currentText()
        duration = self.duration_spin.value()

        # Check if we have flatten regions
        if not self.flatten_regions:
            self.log_message("No flatten regions defined", "ERROR")
            return

        # Convert flatten regions to the format expected by lockout service
        flatten_positions = []
        for region_id, region in self.flatten_regions.items():
            x, y, w, h = region
            flatten_positions.append({"coords": (x, y, x + w, y + h)})

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
        """Handle application close event."""
        try:
            # Stop monitoring if active
            if self.is_monitoring:
                try:
                    self.monitoring_service.stop_monitoring()
                    self.log_message("Monitoring stopped on application exit", "INFO")
                except Exception as e:
                    self.logger.error(f"Error stopping monitoring on exit: {e}", exc_info=True)

            # Save regions
            self._save_platform_regions()

            # Cancel all background tasks
            self.thread_service.cancel_all_tasks()

            # Accept the close event
            event.accept()
        except Exception as e:
            self.logger.error(f"Error during application shutdown: {e}", exc_info=True)
            event.accept()  # Still close even if there's an error


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