#!/usr/bin/env python3
"""
MonitorPal Threading Test Application

This test application validates the threading implementation of various
components in the MonitorPal application, ensuring they function correctly
and efficiently in a multi-threaded environment.
"""
import os
import sys
import time
from datetime import datetime
from typing import Dict, Any

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTabWidget, QLabel, QTextEdit, QProgressBar,
    QFileDialog, QComboBox, QSpinBox, QGroupBox
)
from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QPixmap

# Import your MonitorPal components
# Ensure the NewLayout package is in the Python path
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_background_task_service import IBackgroundTaskService, Worker
from src.domain.services.i_config_repository_service import IConfigRepository
from src.domain.services.i_platform_detection_service import IPlatformDetectionService
from src.domain.services.i_screenshot_service import IScreenshotService
from src.domain.services.i_ocr_service import IOcrService
from src.domain.services.i_monitoring_service import IMonitoringService
from src.domain.services.i_lockout_service import ILockoutService
from src.domain.services.i_verification_service import IVerificationService
from src.domain.services.i_window_manager_service import IWindowManager
from src.application.app import initialize_app


class TestSignals(QObject):
    """Signals for the test application."""
    log_message = Signal(str, str)  # message, level


class SleepWorker(Worker[Dict[str, Any]]):
    """Worker that sleeps for a specified duration and reports progress."""

    def __init__(self, duration_seconds: int, name: str):
        """Initialize the sleep worker."""
        super().__init__()
        self.duration = duration_seconds
        self.name = name

    def execute(self) -> Dict[str, Any]:
        """Execute the worker task."""
        try:
            start_time = time.time()

            # Report starting
            self.report_started()

            # Calculate step size for progress reporting
            step_time = self.duration / 10 if self.duration > 0 else 0.1

            # Sleep with progress reporting
            elapsed = 0
            while elapsed < self.duration and not self.cancel_requested:
                # Calculate progress
                elapsed = time.time() - start_time
                progress = min(int((elapsed / self.duration) * 100), 100)

                # Report progress
                self.report_progress(progress, f"{self.name} progress: {progress}%")

                # Sleep for a small interval
                time.sleep(min(step_time, 0.1))

            # Final elapsed time
            elapsed = time.time() - start_time

            # Check if cancelled
            if self.cancel_requested:
                return {"completed": False, "elapsed": elapsed, "name": self.name}

            return {"completed": True, "elapsed": elapsed, "name": self.name}

        except Exception as e:
            self.report_error(f"Error in sleep worker: {e}")
            return {"completed": False, "error": str(e), "name": self.name}


class ThreadingTestApp(QMainWindow):
    """Main window for the Threading Test Application."""

    def __init__(self):
        super().__init__()

        # Initialize application
        self.container = initialize_app()
        self.logger = self.container.resolve(ILoggerService)
        self.thread_service = self.container.resolve(IBackgroundTaskService)
        self.config_repository = self.container.resolve(IConfigRepository)
        self.platform_detection_service = self.container.resolve(IPlatformDetectionService)
        self.screenshot_service = self.container.resolve(IScreenshotService)
        self.ocr_service = self.container.resolve(IOcrService)
        self.monitoring_service = self.container.resolve(IMonitoringService)
        self.lockout_service = self.container.resolve(ILockoutService)
        self.verification_service = self.container.resolve(IVerificationService)
        self.window_manager = self.container.resolve(IWindowManager)

        # Set up UI
        self.setWindowTitle("MonitorPal Threading Test")
        self.resize(1000, 800)
        self.signals = TestSignals()
        self.signals.log_message.connect(self.log_message)

        # Central widget and main layout
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)

        # Create tab widget
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # Create tabs for different tests
        self.create_thread_service_tab()
        self.create_config_repository_tab()
        self.create_screenshot_tab()
        self.create_ocr_tab()
        self.create_monitoring_tab()
        self.create_lockout_tab()
        self.create_verification_tab()
        self.create_stress_test_tab()

        # Global log and status bar
        log_group = QGroupBox("Global Log")
        log_layout = QVBoxLayout(log_group)
        self.global_log = QTextEdit()
        self.global_log.setReadOnly(True)
        log_layout.addWidget(self.global_log)
        main_layout.addWidget(log_group)

        # Set the central widget
        self.setCentralWidget(central_widget)

        # Initialize UI state
        self.log_message("Threading Test Application initialized", "INFO")
        self.log_message(f"Current running threads: {self.thread_service.get_running_tasks()}", "INFO")

    def closeEvent(self, event):
        """Handle window close event."""
        # Stop any running operations
        self.thread_service.cancel_all_tasks()

        # Accept the event to close the window
        event.accept()

    def log_message(self, message, level="INFO"):
        """Log a message to the global log."""
        timestamp = datetime.now().strftime("%H:%M:%S")

        if level == "INFO":
            self.global_log.append(f"[{timestamp}] {message}")
        elif level == "WARNING":
            self.global_log.append(f"[{timestamp}] <span style='color:orange'>{message}</span>")
        elif level == "ERROR":
            self.global_log.append(f"[{timestamp}] <span style='color:red'>{message}</span>")
        elif level == "SUCCESS":
            self.global_log.append(f"[{timestamp}] <span style='color:green'>{message}</span>")

    # ----------------------------------------------------------------------------
    # Thread Service Tab Methods
    # ----------------------------------------------------------------------------

    def create_thread_service_tab(self):
        """Create tab for testing thread service."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Controls
        controls_group = QGroupBox("Thread Service Controls")
        controls_layout = QVBoxLayout(controls_group)

        # Number of tasks
        task_layout = QHBoxLayout()
        task_layout.addWidget(QLabel("Number of Tasks:"))
        self.task_count_spinner = QSpinBox()
        self.task_count_spinner.setRange(1, 100)
        self.task_count_spinner.setValue(5)
        task_layout.addWidget(self.task_count_spinner)
        controls_layout.addLayout(task_layout)

        # Task duration
        duration_layout = QHBoxLayout()
        duration_layout.addWidget(QLabel("Task Duration (seconds):"))
        self.task_duration_spinner = QSpinBox()
        self.task_duration_spinner.setRange(1, 30)
        self.task_duration_spinner.setValue(3)
        duration_layout.addWidget(self.task_duration_spinner)
        controls_layout.addLayout(duration_layout)

        # Buttons
        button_layout = QHBoxLayout()
        self.start_tasks_button = QPushButton("Start Tasks")
        self.start_tasks_button.clicked.connect(self.start_thread_tasks)
        button_layout.addWidget(self.start_tasks_button)

        self.cancel_tasks_button = QPushButton("Cancel Tasks")
        self.cancel_tasks_button.clicked.connect(self.cancel_thread_tasks)
        button_layout.addWidget(self.cancel_tasks_button)

        controls_layout.addLayout(button_layout)
        layout.addWidget(controls_group)

        # Log
        log_group = QGroupBox("Thread Service Log")
        log_layout = QVBoxLayout(log_group)
        self.thread_log = QTextEdit()
        self.thread_log.setReadOnly(True)
        log_layout.addWidget(self.thread_log)
        layout.addWidget(log_group)

        # Add tab
        self.tab_widget.addTab(tab, "Thread Service")

    def start_thread_tasks(self):
        """Start multiple thread tasks to test the thread service."""
        count = self.task_count_spinner.value()
        duration = self.task_duration_spinner.value()

        self.thread_log.append(f"Starting {count} tasks with {duration} second duration...")

        for i in range(count):
            task_id = f"test_task_{i}"
            worker = SleepWorker(duration, f"Task {i}")

            # Set callbacks
            worker.set_on_started(lambda idx=i: self.on_task_started(idx))
            worker.set_on_progress(lambda percent, msg, idx=i: self.on_task_progress(idx, percent, msg))
            worker.set_on_completed(lambda result, idx=i: self.on_task_completed(idx, result))
            worker.set_on_error(lambda error, idx=i: self.on_task_error(idx, error))

            # Execute task
            result = self.thread_service.execute_task(task_id, worker)

            if result.is_failure:
                self.thread_log.append(f"<span style='color:red'>Failed to start task {i}: {result.error}</span>")
            else:
                self.thread_log.append(f"Task {i} started successfully")

        # Update running tasks
        self.update_running_tasks()

    def cancel_thread_tasks(self):
        """Cancel all running thread tasks."""
        tasks = self.thread_service.get_running_tasks()

        if not tasks:
            self.thread_log.append("No tasks running to cancel")
            return

        self.thread_log.append(f"Cancelling {len(tasks)} tasks...")

        for task_id in tasks:
            # Cancel all tasks, not just test_task_ ones
            result = self.thread_service.cancel_task(task_id)

            if result.is_failure:
                self.thread_log.append(
                    f"<span style='color:red'>Failed to cancel task {task_id}: {result.error}</span>")
            else:
                self.thread_log.append(f"Task {task_id} cancelled successfully")

        # Update running tasks
        self.update_running_tasks()

    def update_running_tasks(self):
        """Update the display of running tasks."""
        tasks = self.thread_service.get_running_tasks()
        self.thread_log.append(f"Current running tasks: {tasks}")
        self.log_message(f"Running tasks: {tasks}", "INFO")

    def on_task_started(self, task_index):
        """Handle task started event."""
        self.thread_log.append(f"<span style='color:blue'>Task {task_index} started</span>")

    def on_task_progress(self, task_index, percent, message):
        """Handle task progress event."""
        self.thread_log.append(f"Task {task_index} progress: {percent}% - {message}")

    def on_task_completed(self, task_index, result):
        """Handle task completed event."""
        self.thread_log.append(f"<span style='color:green'>Task {task_index} completed with result: {result}</span>")
        self.update_running_tasks()

    def on_task_error(self, task_index, error):
        """Handle task error event."""
        self.thread_log.append(f"<span style='color:red'>Task {task_index} error: {error}</span>")
        self.update_running_tasks()

    # ----------------------------------------------------------------------------
    # Config Repository Tab Methods
    # ----------------------------------------------------------------------------

    def create_config_repository_tab(self):
        """Create tab for testing config repository."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Controls
        controls_group = QGroupBox("Config Repository Controls")
        controls_layout = QVBoxLayout(controls_group)

        # Buttons
        button_layout = QHBoxLayout()
        self.load_config_button = QPushButton("Load Configuration")
        self.load_config_button.clicked.connect(self.test_load_config)
        button_layout.addWidget(self.load_config_button)

        self.save_config_button = QPushButton("Save Configuration")
        self.save_config_button.clicked.connect(self.test_save_config)
        button_layout.addWidget(self.save_config_button)

        self.stress_config_button = QPushButton("Stress Test Config")
        self.stress_config_button.clicked.connect(self.stress_test_config)
        button_layout.addWidget(self.stress_config_button)

        controls_layout.addLayout(button_layout)
        layout.addWidget(controls_group)

        # Log
        log_group = QGroupBox("Config Repository Log")
        log_layout = QVBoxLayout(log_group)
        self.config_log = QTextEdit()
        self.config_log.setReadOnly(True)
        log_layout.addWidget(self.config_log)
        layout.addWidget(log_group)

        # Add tab
        self.tab_widget.addTab(tab, "Config Repository")

    def test_load_config(self):
        """Test loading the configuration."""
        self.config_log.append("Loading configuration...")

        # Create a worker for the load operation
        class LoadConfigWorker(Worker):
            def execute(self):
                config_result = self.config_repo.load_config(force_reload=True)
                if config_result.is_failure:
                    return {"success": False, "error": str(config_result.error)}
                return {"success": True, "config": config_result.value}

        worker = LoadConfigWorker()
        worker.config_repo = self.config_repository

        # Set callbacks
        worker.set_on_completed(self.on_config_loaded)
        worker.set_on_error(
            lambda error: self.config_log.append(f"<span style='color:red'>Error loading config: {error}</span>"))

        # Execute in background
        result = self.thread_service.execute_task("load_config", worker)

        if result.is_failure:
            self.config_log.append(f"<span style='color:red'>Failed to start load operation: {result.error}</span>")

    def on_config_loaded(self, result):
        """Handle config loaded event."""
        if result["success"]:
            self.config_log.append("<span style='color:green'>Configuration loaded successfully</span>")

            # Display some config values
            config = result["config"]
            config_str = "Configuration values:\n"
            config_str += f"Default platforms: {config.get('default_platforms', [])}\n"
            config_str += f"Stop loss threshold: {config.get('stop_loss_threshold', 0.0)}\n"
            config_str += f"Lockout duration: {config.get('lockout_duration', 15)}\n"
            config_str += f"Cold Turkey path: {config.get('cold_turkey_blocker', '')}\n"
            config_str += f"Verified blocks: {config.get('verified_blocks', [])}\n"

            self.config_log.append(config_str)
        else:
            self.config_log.append(f"<span style='color:red'>Failed to load config: {result['error']}</span>")

    def test_save_config(self):
        """Test saving the configuration."""
        self.config_log.append("Saving configuration...")

        # Create a worker for the save operation
        class SaveConfigWorker(Worker):
            def execute(self):
                # Get current config
                config_result = self.config_repo.load_config()
                if config_result.is_failure:
                    return {"success": False, "error": str(config_result.error)}

                # Update a value to ensure a change
                config = config_result.value
                config["test_timestamp"] = datetime.now().isoformat()

                # Save config
                save_result = self.config_repo.save_config(config)
                if save_result.is_failure:
                    return {"success": False, "error": str(save_result.error)}

                return {"success": True}

        worker = SaveConfigWorker()
        worker.config_repo = self.config_repository

        # Set callbacks
        worker.set_on_completed(self.on_config_saved)
        worker.set_on_error(
            lambda error: self.config_log.append(f"<span style='color:red'>Error saving config: {error}</span>"))

        # Execute in background
        result = self.thread_service.execute_task("save_config", worker)

        if result.is_failure:
            self.config_log.append(f"<span style='color:red'>Failed to start save operation: {result.error}</span>")

    def on_config_saved(self, result):
        """Handle config saved event."""
        if result["success"]:
            self.config_log.append("<span style='color:green'>Configuration saved successfully</span>")
        else:
            self.config_log.append(f"<span style='color:red'>Failed to save config: {result['error']}</span>")

    def stress_test_config(self):
        """Stress test the config repository with multiple concurrent operations."""
        self.config_log.append("Starting config repository stress test...")

        # Number of operations to perform
        num_operations = 50

        # Track completed operations
        self.config_operations_completed = 0
        self.config_operations_failed = 0

        for i in range(num_operations):
            # Alternate between load and save
            if i % 2 == 0:
                self._stress_load_config(i)
            else:
                self._stress_save_config(i)

        self.config_log.append(f"Launched {num_operations} concurrent config operations")

    def _stress_load_config(self, index):
        """Execute a load config operation for stress testing."""

        class StressLoadConfigWorker(Worker):
            def execute(self):
                # Add a small delay to create more concurrency
                time.sleep(0.05 * (index % 10))
                config_result = self.config_repo.load_config(force_reload=True)
                if config_result.is_failure:
                    return {"success": False, "error": str(config_result.error), "index": index}
                return {"success": True, "index": index}

        worker = StressLoadConfigWorker()
        worker.config_repo = self.config_repository

        # Set callbacks
        worker.set_on_completed(self.on_stress_config_completed)
        worker.set_on_error(lambda error: self.on_stress_config_error(error, index))

        # Execute in background
        task_id = f"stress_load_{index}"
        result = self.thread_service.execute_task(task_id, worker)

        if result.is_failure:
            self.config_log.append(
                f"<span style='color:red'>Failed to start stress load {index}: {result.error}</span>")
            self.config_operations_failed += 1

    def _stress_save_config(self, index):
        """Execute a save config operation for stress testing."""

        class StressSaveConfigWorker(Worker):
            def execute(self):
                # Add a small delay to create more concurrency
                time.sleep(0.05 * (index % 10))

                # Get current config
                config_result = self.config_repo.load_config()
                if config_result.is_failure:
                    return {"success": False, "error": str(config_result.error), "index": index}

                # Update a value
                config = config_result.value
                config[f"stress_test_{index}"] = datetime.now().isoformat()

                # Save config
                save_result = self.config_repo.save_config(config)
                if save_result.is_failure:
                    return {"success": False, "error": str(save_result.error), "index": index}

                return {"success": True, "index": index}

        worker = StressSaveConfigWorker()
        worker.config_repo = self.config_repository

        # Set callbacks
        worker.set_on_completed(self.on_stress_config_completed)
        worker.set_on_error(lambda error: self.on_stress_config_error(error, index))

        # Execute in background
        task_id = f"stress_save_{index}"
        result = self.thread_service.execute_task(task_id, worker)

        if result.is_failure:
            self.config_log.append(
                f"<span style='color:red'>Failed to start stress save {index}: {result.error}</span>")
            self.config_operations_failed += 1

    def on_stress_config_completed(self, result):
        """Handle completion of a config stress test operation."""
        self.config_operations_completed += 1

        if not result["success"]:
            self.config_operations_failed += 1
            self.config_log.append(
                f"<span style='color:red'>Stress operation {result['index']} failed: {result.get('error')}</span>")

        # Check if all operations are complete
        if self.config_operations_completed >= 50:
            self.config_log.append(f"<span style='color:green'>Config stress test complete. "
                                   f"Failed: {self.config_operations_failed} / {self.config_operations_completed}</span>")

    def on_stress_config_error(self, error, index):
        """Handle error in a config stress test operation."""
        self.config_operations_completed += 1
        self.config_operations_failed += 1
        self.config_log.append(f"<span style='color:red'>Stress operation {index} error: {error}</span>")

        # Check if all operations are complete
        if self.config_operations_completed >= 50:
            self.config_log.append(f"<span style='color:green'>Config stress test complete. "
                                   f"Failed: {self.config_operations_failed} / {self.config_operations_completed}</span>")

    # ----------------------------------------------------------------------------
    # Screenshot Service Tab Methods
    # ----------------------------------------------------------------------------

    def create_screenshot_tab(self):
        """Create tab for testing screenshot service."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Controls
        controls_group = QGroupBox("Screenshot Controls")
        controls_layout = QVBoxLayout(controls_group)

        # Region selection
        region_layout = QHBoxLayout()
        region_layout.addWidget(QLabel("Region:"))
        self.region_button = QPushButton("Select Region")
        self.region_button.clicked.connect(self.select_screenshot_region)
        region_layout.addWidget(self.region_button)
        self.region_label = QLabel("No region selected")
        region_layout.addWidget(self.region_label)
        controls_layout.addLayout(region_layout)

        # Buttons
        button_layout = QHBoxLayout()
        self.capture_button = QPushButton("Capture Screenshot")
        self.capture_button.clicked.connect(self.test_screenshot_capture)
        button_layout.addWidget(self.capture_button)

        self.multi_capture_button = QPushButton("Multiple Captures")
        self.multi_capture_button.clicked.connect(self.test_multi_screenshot)
        button_layout.addWidget(self.multi_capture_button)

        controls_layout.addLayout(button_layout)
        layout.addWidget(controls_group)

        # Display
        display_group = QGroupBox("Screenshot Display")
        display_layout = QVBoxLayout(display_group)
        self.screenshot_label = QLabel("No screenshot captured")
        self.screenshot_label.setAlignment(Qt.AlignCenter)
        self.screenshot_label.setMinimumHeight(200)
        display_layout.addWidget(self.screenshot_label)
        layout.addWidget(display_group)

        # Log
        log_group = QGroupBox("Screenshot Log")
        log_layout = QVBoxLayout(log_group)
        self.screenshot_log = QTextEdit()
        self.screenshot_log.setReadOnly(True)
        log_layout.addWidget(self.screenshot_log)
        layout.addWidget(log_group)

        # Add tab
        self.tab_widget.addTab(tab, "Screenshot Service")

        # Initialize state
        self.selected_region = None

    def select_screenshot_region(self):
        """Select a region for screenshot capture."""
        self.screenshot_log.append("Opening region selection...")

        try:
            # Import region selector directly
            from src.presentation.components.qt_region_selector import select_region_qt

            # Use synchronous region selection directly
            region = select_region_qt(
                "Please select the region to capture a screenshot."
            )

            if region:
                self.selected_region = region
                self.region_label.setText(f"Region: {self.selected_region}")
                self.screenshot_log.append(f"<span style='color:green'>Region selected: {self.selected_region}</span>")
            else:
                self.screenshot_log.append("Region selection cancelled")
        except Exception as e:
            self.screenshot_log.append(f"<span style='color:red'>Error in region selection: {str(e)}</span>")
            import traceback
            self.screenshot_log.append(traceback.format_exc())

    def test_screenshot_capture(self):
        """Test capturing a screenshot."""
        if not self.selected_region:
            self.screenshot_log.append("<span style='color:red'>No region selected</span>")
            return

        self.screenshot_log.append(f"Capturing screenshot of region {self.selected_region}...")

        # Create a worker for the screenshot capture
        class ScreenshotWorker(Worker):
            def execute(self):
                capture_result = self.screenshot_service.capture_region(self.region)
                if capture_result.is_failure:
                    return {"success": False, "error": str(capture_result.error)}

                # Convert to bytes for transport across thread boundary
                image = capture_result.value
                bytes_result = self.screenshot_service.to_bytes(image)
                if bytes_result.is_failure:
                    return {"success": False, "error": str(bytes_result.error)}

                return {
                    "success": True,
                    "image_bytes": bytes_result.value,
                    "size": (image.width, image.height)
                }

        worker = ScreenshotWorker()
        worker.screenshot_service = self.screenshot_service
        worker.region = self.selected_region

        # Set callbacks
        worker.set_on_completed(self.on_screenshot_captured)
        worker.set_on_error(lambda error: self.screenshot_log.append(
            f"<span style='color:red'>Error capturing screenshot: {error}</span>"))

        # Execute in background
        result = self.thread_service.execute_task("capture_screenshot", worker)

        if result.is_failure:
            self.screenshot_log.append(f"<span style='color:red'>Failed to start capture: {result.error}</span>")

    def on_screenshot_captured(self, result):
        """Handle screenshot captured event."""
        if result["success"]:
            self.screenshot_log.append("<span style='color:green'>Screenshot captured successfully</span>")

            # Create QPixmap from bytes
            pixmap = QPixmap()
            pixmap.loadFromData(result["image_bytes"])

            # Display the screenshot
            self.screenshot_label.setPixmap(pixmap)
            self.screenshot_label.setFixedSize(pixmap.size())

            # Show size info
            size = result["size"]
            self.screenshot_log.append(f"Screenshot size: {size[0]}x{size[1]}")
        else:
            self.screenshot_log.append(
                f"<span style='color:red'>Failed to capture screenshot: {result['error']}</span>")

    def test_multi_screenshot(self):
        """Test capturing multiple screenshots concurrently."""
        if not self.selected_region:
            self.screenshot_log.append("<span style='color:red'>No region selected</span>")
            return

        # Number of screenshots to capture
        num_captures = 10

        self.screenshot_log.append(f"Capturing {num_captures} screenshots concurrently...")

        # Track completed captures
        self.screenshot_captures_completed = 0
        self.screenshot_captures_failed = 0

        for i in range(num_captures):
            self._execute_screenshot_capture(i)

        self.screenshot_log.append(f"Launched {num_captures} concurrent screenshot captures")

    def _execute_screenshot_capture(self, index):
        """Execute a screenshot capture for the multi-capture test."""
        class MultiScreenshotWorker(Worker):
            def execute(self):
                # Add a small delay to create more concurrency
                time.sleep(0.05 * (index % 5))

                capture_result = self.screenshot_service.capture_region(self.region)
                if capture_result.is_failure:
                    return {"success": False, "error": str(capture_result.error), "index": index}

                # Get image dimensions
                image = capture_result.value

                return {"success": True, "size": (image.width, image.height), "index": index}

        worker = MultiScreenshotWorker()
        worker.screenshot_service = self.screenshot_service
        worker.region = self.selected_region

        # Set callbacks
        worker.set_on_completed(self.on_multi_screenshot_completed)
        worker.set_on_error(lambda error: self.on_multi_screenshot_error(error, index))

        # Execute in background
        task_id = f"multi_capture_{index}"
        result = self.thread_service.execute_task(task_id, worker)

        if result.is_failure:
            self.screenshot_log.append(f"<span style='color:red'>Failed to start capture {index}: {result.error}</span>")
            self.screenshot_captures_failed += 1

    def on_multi_screenshot_completed(self, result):
        """Handle completion of a multi-capture screenshot."""
        self.screenshot_captures_completed += 1

        if result["success"]:
            size = result["size"]
            self.screenshot_log.append(f"Capture {result['index']} complete: {size[0]}x{size[1]}")
        else:
            self.screenshot_captures_failed += 1
            self.screenshot_log.append(f"<span style='color:red'>Capture {result['index']} failed: {result.get('error')}</span>")

        # Check if all captures are complete
        if self.screenshot_captures_completed >= 10:
            self.screenshot_log.append(f"<span style='color:green'>All captures complete. "
                                       f"Failed: {self.screenshot_captures_failed} / {self.screenshot_captures_completed}</span>")

    def on_multi_screenshot_error(self, error, index):
        """Handle error in a multi-capture screenshot."""
        self.screenshot_captures_completed += 1
        self.screenshot_captures_failed += 1
        self.screenshot_log.append(f"<span style='color:red'>Capture {index} error: {error}</span>")

        # Check if all captures are complete
        if self.screenshot_captures_completed >= 10:
            self.screenshot_log.append(f"<span style='color:green'>All captures complete. "
                                       f"Failed: {self.screenshot_captures_failed} / {self.screenshot_captures_completed}</span>")

    #----------------------------------------------------------------------------
    # OCR Service Tab Methods
    #----------------------------------------------------------------------------

    def create_ocr_tab(self):
        """Create tab for testing OCR service."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Controls
        controls_group = QGroupBox("OCR Controls")
        controls_layout = QVBoxLayout(controls_group)

        # Region selection
        region_layout = QHBoxLayout()
        region_layout.addWidget(QLabel("Region:"))
        self.ocr_region_button = QPushButton("Select Region")
        self.ocr_region_button.clicked.connect(self.select_ocr_region)
        region_layout.addWidget(self.ocr_region_button)
        self.ocr_region_label = QLabel("No region selected")
        region_layout.addWidget(self.ocr_region_label)
        controls_layout.addLayout(region_layout)

        # Buttons
        button_layout = QHBoxLayout()
        self.ocr_button = QPushButton("Perform OCR")
        self.ocr_button.clicked.connect(self.test_ocr)
        button_layout.addWidget(self.ocr_button)

        self.multi_ocr_button = QPushButton("Multiple OCR Tasks")
        self.multi_ocr_button.clicked.connect(self.test_multi_ocr)
        button_layout.addWidget(self.multi_ocr_button)

        controls_layout.addLayout(button_layout)
        layout.addWidget(controls_group)

        # Results
        results_group = QGroupBox("OCR Results")
        results_layout = QVBoxLayout(results_group)
        self.ocr_results = QTextEdit()
        self.ocr_results.setReadOnly(True)
        results_layout.addWidget(self.ocr_results)
        layout.addWidget(results_group)

        # Log
        log_group = QGroupBox("OCR Log")
        log_layout = QVBoxLayout(log_group)
        self.ocr_log = QTextEdit()
        self.ocr_log.setReadOnly(True)
        log_layout.addWidget(self.ocr_log)
        layout.addWidget(log_group)

        # Add tab
        self.tab_widget.addTab(tab, "OCR Service")

        # Initialize state
        self.ocr_region = None

    def select_ocr_region(self):
        """Select a region for OCR processing."""
        self.ocr_log.append("Opening region selection...")

        try:
            # Import region selector directly - same approach as in select_screenshot_region
            from src.presentation.components.qt_region_selector import select_region_qt

            # Use synchronous region selection directly
            region = select_region_qt(
                "Please select the region for OCR processing."
            )

            if region:
                self.ocr_region = region
                self.ocr_region_label.setText(f"Region: {self.ocr_region}")
                self.ocr_log.append(f"<span style='color:green'>Region selected: {self.ocr_region}</span>")
            else:
                self.ocr_log.append("Region selection cancelled")
        except Exception as e:
            self.ocr_log.append(f"<span style='color:red'>Error in region selection: {str(e)}</span>")
            import traceback
            self.ocr_log.append(traceback.format_exc())

    def test_ocr(self):
        """Test OCR processing."""
        if not self.ocr_region:
            self.ocr_log.append("<span style='color:red'>No region selected</span>")
            return

        self.ocr_log.append(f"Performing OCR on region {self.ocr_region}...")

        # Create a worker for the OCR processing
        class OcrWorker(Worker):
            def execute(self):
                # Capture screenshot
                capture_result = self.screenshot_service.capture_region(self.region)
                if capture_result.is_failure:
                    return {"success": False, "error": str(capture_result.error), "stage": "screenshot"}

                image = capture_result.value

                # Extract text
                ocr_result = self.ocr_service.extract_text(image)
                if ocr_result.is_failure:
                    return {"success": False, "error": str(ocr_result.error), "stage": "ocr"}

                text = ocr_result.value

                # Extract numeric values
                numeric_result = self.ocr_service.extract_numeric_values(text)
                if numeric_result.is_failure:
                    return {"success": False, "error": str(numeric_result.error), "stage": "numeric"}

                values = numeric_result.value

                # Return all results
                return {
                    "success": True,
                    "text": text,
                    "values": values
                }

        worker = OcrWorker()
        worker.screenshot_service = self.screenshot_service
        worker.ocr_service = self.ocr_service
        worker.region = self.ocr_region

        # Set callbacks
        worker.set_on_completed(self.on_ocr_completed)
        worker.set_on_error(lambda error: self.ocr_log.append(f"<span style='color:red'>Error in OCR processing: {error}</span>"))

        # Execute in background
        result = self.thread_service.execute_task("ocr_processing", worker)

        if result.is_failure:
            self.ocr_log.append(f"<span style='color:red'>Failed to start OCR: {result.error}</span>")

    def on_ocr_completed(self, result):
        """Handle OCR completed event."""
        if result["success"]:
            self.ocr_log.append("<span style='color:green'>OCR processing completed successfully</span>")

            # Display OCR results
            text = result["text"]
            values = result["values"]

            self.ocr_results.clear()
            self.ocr_results.append("<b>Extracted Text:</b>")
            self.ocr_results.append(text)
            self.ocr_results.append("\n<b>Numeric Values:</b>")
            if values:
                for i, value in enumerate(values):
                    self.ocr_results.append(f"Value {i+1}: {value}")
            else:
                self.ocr_results.append("No numeric values detected")
        else:
            stage = result.get("stage", "unknown")
            self.ocr_log.append(f"<span style='color:red'>OCR failed at {stage} stage: {result['error']}</span>")

    def test_multi_ocr(self):
        """Test multiple concurrent OCR operations."""
        if not self.ocr_region:
            self.ocr_log.append("<span style='color:red'>No region selected</span>")
            return

        # Number of OCR operations
        num_operations = 5

        self.ocr_log.append(f"Starting {num_operations} concurrent OCR operations...")

        # Track completed operations
        self.ocr_operations_completed = 0
        self.ocr_operations_failed = 0

        for i in range(num_operations):
            self._execute_ocr_operation(i)

        self.ocr_log.append(f"Launched {num_operations} concurrent OCR operations")

    def _execute_ocr_operation(self, index):
        """Execute an OCR operation for the multi-OCR test."""
        class MultiOcrWorker(Worker):
            def execute(self):
                # Capture screenshot
                capture_result = self.screenshot_service.capture_region(self.region)
                if capture_result.is_failure:
                    return {"success": False, "error": str(capture_result.error), "index": index}

                image = capture_result.value

                # Extract text
                ocr_result = self.ocr_service.extract_text(image)
                if ocr_result.is_failure:
                    return {"success": False, "error": str(ocr_result.error), "index": index}

                text = ocr_result.value

                # Extract numeric values
                numeric_result = self.ocr_service.extract_numeric_values(text)
                if numeric_result.is_failure:
                    return {"success": False, "error": str(numeric_result.error), "index": index}

                values = numeric_result.value

                # Return results
                return {
                    "success": True,
                    "text_length": len(text),
                    "values_count": len(values),
                    "index": index
                }

        worker = MultiOcrWorker()
        worker.screenshot_service = self.screenshot_service
        worker.ocr_service = self.ocr_service
        worker.region = self.ocr_region

        # Set callbacks
        worker.set_on_completed(self.on_multi_ocr_completed)
        worker.set_on_error(lambda error: self.on_multi_ocr_error(error, index))

        # Execute in background
        task_id = f"multi_ocr_{index}"
        result = self.thread_service.execute_task(task_id, worker)

        if result.is_failure:
            self.ocr_log.append(f"<span style='color:red'>Failed to start OCR {index}: {result.error}</span>")
            self.ocr_operations_failed += 1

    def on_multi_ocr_completed(self, result):
        """Handle completion of a multi-OCR operation."""
        self.ocr_operations_completed += 1

        if result["success"]:
            self.ocr_log.append(f"OCR {result['index']} complete: {result['text_length']} chars, {result['values_count']} values")
        else:
            self.ocr_operations_failed += 1
            self.ocr_log.append(f"<span style='color:red'>OCR {result['index']} failed: {result.get('error')}</span>")

        # Check if all operations are complete
        if self.ocr_operations_completed >= 5:
            self.ocr_log.append(f"<span style='color:green'>All OCR operations complete. "
                                f"Failed: {self.ocr_operations_failed} / {self.ocr_operations_completed}</span>")

    def on_multi_ocr_error(self, error, index):
        """Handle error in a multi-OCR operation."""
        self.ocr_operations_completed += 1
        self.ocr_operations_failed += 1
        self.ocr_log.append(f"<span style='color:red'>OCR {index} error: {error}</span>")

        # Check if all operations are complete
        if self.ocr_operations_completed >= 5:
            self.ocr_log.append(f"<span style='color:green'>All OCR operations complete. "
                                f"Failed: {self.ocr_operations_failed} / {self.ocr_operations_completed}</span>")

    #----------------------------------------------------------------------------
    # Monitoring Service Tab Methods
    #----------------------------------------------------------------------------

    def create_monitoring_tab(self):
        """Create tab for testing monitoring service."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Controls
        controls_group = QGroupBox("Monitoring Controls")
        controls_layout = QVBoxLayout(controls_group)

        # Platform selection
        platform_layout = QHBoxLayout()
        platform_layout.addWidget(QLabel("Platform:"))
        self.platform_combo = QComboBox()

        # Get supported platforms
        platforms_result = self.platform_detection_service.get_supported_platforms()
        if platforms_result.is_success:
            for platform in platforms_result.value.keys():
                self.platform_combo.addItem(platform)

        platform_layout.addWidget(self.platform_combo)
        controls_layout.addLayout(platform_layout)

        # Region selection
        region_layout = QHBoxLayout()
        region_layout.addWidget(QLabel("Region:"))
        self.monitoring_region_button = QPushButton("Select Region")
        self.monitoring_region_button.clicked.connect(self.select_monitoring_region)
        region_layout.addWidget(self.monitoring_region_button)
        self.monitoring_region_label = QLabel("No region selected")
        region_layout.addWidget(self.monitoring_region_label)
        controls_layout.addLayout(region_layout)

        # Threshold
        threshold_layout = QHBoxLayout()
        threshold_layout.addWidget(QLabel("Threshold:"))
        self.threshold_spinner = QSpinBox()
        self.threshold_spinner.setRange(-10000, 0)
        self.threshold_spinner.setValue(-100)
        threshold_layout.addWidget(self.threshold_spinner)
        controls_layout.addLayout(threshold_layout)

        # Interval
        interval_layout = QHBoxLayout()
        interval_layout.addWidget(QLabel("Interval (seconds):"))
        self.interval_spinner = QSpinBox()
        self.interval_spinner.setRange(1, 60)
        self.interval_spinner.setValue(5)
        interval_layout.addWidget(self.interval_spinner)
        controls_layout.addLayout(interval_layout)

        # Buttons
        button_layout = QHBoxLayout()
        self.start_monitoring_button = QPushButton("Start Monitoring")
        self.start_monitoring_button.clicked.connect(self.test_start_monitoring)
        button_layout.addWidget(self.start_monitoring_button)

        self.stop_monitoring_button = QPushButton("Stop Monitoring")
        self.stop_monitoring_button.clicked.connect(self.test_stop_monitoring)
        self.stop_monitoring_button.setEnabled(False)
        button_layout.addWidget(self.stop_monitoring_button)

        controls_layout.addLayout(button_layout)
        layout.addWidget(controls_group)

        # Status
        status_group = QGroupBox("Monitoring Status")
        status_layout = QVBoxLayout(status_group)
        self.monitoring_status = QLabel("Not monitoring")
        status_layout.addWidget(self.monitoring_status)
        self.monitoring_values = QLabel("No values detected")
        status_layout.addWidget(self.monitoring_values)
        layout.addWidget(status_group)

        # Log
        log_group = QGroupBox("Monitoring Log")
        log_layout = QVBoxLayout(log_group)
        self.monitoring_log = QTextEdit()
        self.monitoring_log.setReadOnly(True)
        log_layout.addWidget(self.monitoring_log)
        layout.addWidget(log_group)

        # Add tab
        self.tab_widget.addTab(tab, "Monitoring Service")

        # Initialize state
        self.monitoring_region = None

    def select_monitoring_region(self):
        """Select a region for monitoring."""
        self.monitoring_log.append("Opening region selection...")

        try:
            # Import region selector directly
            from src.presentation.components.qt_region_selector import select_region_qt

            # Use synchronous region selection directly
            region = select_region_qt(
                "Please select the region to monitor."
            )

            if region:
                self.monitoring_region = region
                self.monitoring_region_label.setText(f"Region: {self.monitoring_region}")
                self.monitoring_log.append(
                    f"<span style='color:green'>Region selected: {self.monitoring_region}</span>")
            else:
                self.monitoring_log.append("Region selection cancelled")
        except Exception as e:
            self.monitoring_log.append(f"<span style='color:red'>Error in region selection: {str(e)}</span>")
            import traceback
            self.monitoring_log.append(traceback.format_exc())

    def test_start_monitoring(self):
        """Test starting the monitoring service."""
        if not self.monitoring_region:
            self.monitoring_log.append("<span style='color:red'>No region selected</span>")
            return

        # Get parameters
        platform = self.platform_combo.currentText()
        threshold = float(self.threshold_spinner.value())
        interval = float(self.interval_spinner.value())

        self.monitoring_log.append(f"Starting monitoring for {platform} with threshold {threshold}...")

        # Start monitoring
        result = self.monitoring_service.start_monitoring(
            platform=platform,
            region=self.monitoring_region,
            threshold=threshold,
            interval_seconds=interval,
            on_status_update=self.on_monitoring_status_update,
            on_threshold_exceeded=self.on_monitoring_threshold_exceeded,
            on_error=self.on_monitoring_error
        )

        if result.is_success:
            self.monitoring_log.append("<span style='color:green'>Monitoring started successfully</span>")
            self.monitoring_status.setText("Monitoring active")

            # Update button states
            self.start_monitoring_button.setEnabled(False)
            self.stop_monitoring_button.setEnabled(True)
        else:
            self.monitoring_log.append(f"<span style='color:red'>Failed to start monitoring: {result.error}</span>")

    def test_stop_monitoring(self):
        """Test stopping the monitoring service."""
        self.monitoring_log.append("Stopping monitoring...")

        # Stop monitoring
        result = self.monitoring_service.stop_monitoring()

        if result.is_success:
            self.monitoring_log.append("<span style='color:green'>Monitoring stopped successfully</span>")
            self.monitoring_status.setText("Monitoring stopped")

            # Update button states
            self.start_monitoring_button.setEnabled(True)
            self.stop_monitoring_button.setEnabled(False)
        else:
            self.monitoring_log.append(f"<span style='color:red'>Failed to stop monitoring: {result.error}</span>")

    def on_monitoring_status_update(self, message, level):
        """Handle monitoring status update."""
        if level == "INFO":
            self.monitoring_log.append(message)
        elif level == "WARNING":
            self.monitoring_log.append(f"<span style='color:orange'>{message}</span>")
        elif level == "ERROR":
            self.monitoring_log.append(f"<span style='color:red'>{message}</span>")
        elif level == "SUCCESS":
            self.monitoring_log.append(f"<span style='color:green'>{message}</span>")

        # Update latest result
        latest_result = self.monitoring_service.get_latest_result()
        if latest_result:
            values_str = ", ".join([f"{v:.2f}" for v in latest_result.values])
            min_value = latest_result.minimum_value
            threshold = latest_result.threshold

            self.monitoring_values.setText(f"Values: {values_str}\nMin: {min_value:.2f}\nThreshold: {threshold:.2f}")

    def on_monitoring_threshold_exceeded(self, result):
        """Handle monitoring threshold exceeded event."""
        self.monitoring_log.append(f"<span style='color:red'>THRESHOLD EXCEEDED: {result.minimum_value:.2f} < {result.threshold:.2f}</span>")
        self.monitoring_status.setText("Threshold exceeded - monitoring stopped")

        # Update button states
        self.start_monitoring_button.setEnabled(True)
        self.stop_monitoring_button.setEnabled(False)

    def on_monitoring_error(self, error):
        """Handle monitoring error event."""
        self.monitoring_log.append(f"<span style='color:red'>Monitoring error: {error}</span>")

    # ----------------------------------------------------------------------------
    # Lockout Service Tab Methods
    # ----------------------------------------------------------------------------

    def create_lockout_tab(self):
        """Create tab for testing lockout service."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Controls
        controls_group = QGroupBox("Lockout Controls")
        controls_layout = QVBoxLayout(controls_group)

        # Platform selection
        platform_layout = QHBoxLayout()
        platform_layout.addWidget(QLabel("Platform:"))
        self.lockout_platform_combo = QComboBox()

        # Get supported platforms
        platforms_result = self.platform_detection_service.get_supported_platforms()
        if platforms_result.is_success:
            for platform in platforms_result.value.keys():
                self.lockout_platform_combo.addItem(platform)

        platform_layout.addWidget(self.lockout_platform_combo)
        controls_layout.addLayout(platform_layout)

        # Flatten positions
        positions_layout = QHBoxLayout()
        positions_layout.addWidget(QLabel("Flatten Positions:"))
        self.add_position_button = QPushButton("Add Position")
        self.add_position_button.clicked.connect(self.add_flatten_position)
        positions_layout.addWidget(self.add_position_button)
        self.positions_label = QLabel("0 positions configured")
        positions_layout.addWidget(self.positions_label)
        controls_layout.addLayout(positions_layout)

        # Duration
        duration_layout = QHBoxLayout()
        duration_layout.addWidget(QLabel("Lockout Duration (minutes):"))
        self.lockout_duration_spinner = QSpinBox()
        self.lockout_duration_spinner.setRange(1, 60)
        self.lockout_duration_spinner.setValue(15)
        duration_layout.addWidget(self.lockout_duration_spinner)
        controls_layout.addLayout(duration_layout)

        # Cold Turkey path
        ct_path_layout = QHBoxLayout()
        ct_path_layout.addWidget(QLabel("Cold Turkey Path:"))
        self.ct_path_button = QPushButton("Set Path")
        self.ct_path_button.clicked.connect(self.set_cold_turkey_path)
        ct_path_layout.addWidget(self.ct_path_button)
        self.ct_path_label = QLabel("No path set")
        ct_path_layout.addWidget(self.ct_path_label)
        controls_layout.addLayout(ct_path_layout)

        # Buttons
        button_layout = QHBoxLayout()
        self.perform_lockout_button = QPushButton("Perform Lockout")
        self.perform_lockout_button.clicked.connect(self.test_perform_lockout)
        button_layout.addWidget(self.perform_lockout_button)
        controls_layout.addLayout(button_layout)

        layout.addWidget(controls_group)

        # Log
        log_group = QGroupBox("Lockout Log")
        log_layout = QVBoxLayout(log_group)
        self.lockout_log = QTextEdit()
        self.lockout_log.setReadOnly(True)
        log_layout.addWidget(self.lockout_log)
        layout.addWidget(log_group)

        # Add tab
        self.tab_widget.addTab(tab, "Lockout Service")

        # Initialize state
        self.flatten_positions = []

        # Initialize CT path display
        ct_path = self.config_repository.get_cold_turkey_path()
        if ct_path:
            self.ct_path_label.setText(ct_path)

    def add_flatten_position(self):
        """Add a flatten position for the lockout test."""
        self.lockout_log.append("Opening region selection for flatten position...")

        try:
            # Import region selector directly
            from src.presentation.components.qt_region_selector import select_region_qt

            # Use synchronous region selection directly
            region = select_region_qt(
                "Please select a region for the flatten position."
            )

            if region:
                # Convert to coords format used by lockout service
                x, y, width, height = region
                coords = [x, y, x + width, y + height]

                # Add to positions list
                self.flatten_positions.append({"coords": coords})
                self.positions_label.setText(f"{len(self.flatten_positions)} positions configured")

                self.lockout_log.append(f"<span style='color:green'>Position added: {coords}</span>")
            else:
                self.lockout_log.append("Region selection cancelled")
        except Exception as e:
            self.lockout_log.append(f"<span style='color:red'>Error in region selection: {str(e)}</span>")
            import traceback
            self.lockout_log.append(traceback.format_exc())

    def set_cold_turkey_path(self):
        """Set the Cold Turkey Blocker path."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Cold Turkey Blocker Executable",
            "", "Executables (*.exe)"
        )

        if path:
            # Set the path
            result = self.config_repository.set_cold_turkey_path(path)

            if result.is_success:
                self.ct_path_label.setText(path)
                self.lockout_log.append(f"<span style='color:green'>Cold Turkey path set to: {path}</span>")
            else:
                self.lockout_log.append(
                    f"<span style='color:red'>Failed to set Cold Turkey path: {result.error}</span>")

    def test_perform_lockout(self):
        """Test performing a lockout."""
        if not self.flatten_positions:
            self.lockout_log.append("<span style='color:red'>No flatten positions configured</span>")
            return

        # Get parameters
        platform = self.lockout_platform_combo.currentText()
        duration = self.lockout_duration_spinner.value()

        self.lockout_log.append(
            f"Performing lockout for {platform} with {len(self.flatten_positions)} flatten positions...")

        # Create a worker for the lockout
        class LockoutWorker(Worker):
            def execute(self):
                result = self.lockout_service.perform_lockout(
                    platform=self.platform,
                    flatten_positions=self.flatten_positions,
                    lockout_duration=self.duration,
                    on_status_update=self.on_status_update
                )

                if result.is_failure:
                    return {"success": False, "error": str(result.error)}

                return {"success": True}

            def on_status_update(self, message, level):
                # We need to use a signal to safely update UI from worker thread
                self.report_progress(50, f"{level}:{message}")

        worker = LockoutWorker()
        worker.lockout_service = self.lockout_service
        worker.platform = platform
        worker.flatten_positions = self.flatten_positions
        worker.duration = duration

        # Set callbacks
        worker.set_on_progress(self.on_lockout_progress)
        worker.set_on_completed(self.on_lockout_completed)
        worker.set_on_error(
            lambda error: self.lockout_log.append(f"<span style='color:red'>Lockout error: {error}</span>"))

        # Execute in background
        result = self.thread_service.execute_task("perform_lockout", worker)

        if result.is_failure:
            self.lockout_log.append(f"<span style='color:red'>Failed to start lockout: {result.error}</span>")

    def on_lockout_progress(self, percent, message):
         """Handle lockout progress update."""
         if ":" in message:
            level, msg = message.split(":", 1)

            if level == "INFO":
                self.lockout_log.append(msg)
            elif level == "WARNING":
                self.lockout_log.append(f"<span style='color:orange'>{msg}</span>")
            elif level == "ERROR":
                self.lockout_log.append(f"<span style='color:red'>{msg}</span>")
            elif level == "SUCCESS":
                self.lockout_log.append(f"<span style='color:green'>{msg}</span>")
         else:
            self.lockout_log.append(message)

    def on_lockout_completed(self, result):
        """Handle lockout completed event."""
        if result["success"]:
            self.lockout_log.append("<span style='color:green'>Lockout completed successfully</span>")
        else:
            self.lockout_log.append(f"<span style='color:red'>Lockout failed: {result['error']}</span>")

    #----------------------------------------------------------------------------
    # Verification Service Tab Methods
    #----------------------------------------------------------------------------

    def create_verification_tab(self):
        """Create tab for testing verification service."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Controls
        controls_group = QGroupBox("Verification Controls")
        controls_layout = QVBoxLayout(controls_group)

        # Platform selection
        platform_layout = QHBoxLayout()
        platform_layout.addWidget(QLabel("Platform:"))
        self.verify_platform_combo = QComboBox()

        # Get supported platforms
        platforms_result = self.platform_detection_service.get_supported_platforms()
        if platforms_result.is_success:
            for platform in platforms_result.value.keys():
                self.verify_platform_combo.addItem(platform)

        platform_layout.addWidget(self.verify_platform_combo)
        controls_layout.addLayout(platform_layout)

        # Block name
        block_layout = QHBoxLayout()
        block_layout.addWidget(QLabel("Block Name:"))
        self.block_name_combo = QComboBox()
        self.block_name_combo.setEditable(True)
        self.block_name_combo.addItems(["Quantower", "NinjaTrader", "TradingView", "Trading", "Ninja"])
        block_layout.addWidget(self.block_name_combo)
        controls_layout.addLayout(block_layout)

        # Buttons
        button_layout = QHBoxLayout()
        self.verify_button = QPushButton("Verify Block")
        self.verify_button.clicked.connect(self.test_verify_block)
        button_layout.addWidget(self.verify_button)

        self.cancel_verify_button = QPushButton("Cancel Verification")
        self.cancel_verify_button.clicked.connect(self.test_cancel_verification)
        self.cancel_verify_button.setEnabled(False)
        button_layout.addWidget(self.cancel_verify_button)

        controls_layout.addLayout(button_layout)
        layout.addWidget(controls_group)

        # Verified blocks
        blocks_group = QGroupBox("Verified Blocks")
        blocks_layout = QVBoxLayout(blocks_group)

        blocks_buttons = QHBoxLayout()
        self.refresh_blocks_button = QPushButton("Refresh Blocks")
        self.refresh_blocks_button.clicked.connect(self.refresh_verified_blocks)
        blocks_buttons.addWidget(self.refresh_blocks_button)

        self.clear_blocks_button = QPushButton("Clear All Blocks")
        self.clear_blocks_button.clicked.connect(self.clear_verified_blocks)
        blocks_buttons.addWidget(self.clear_blocks_button)

        blocks_layout.addLayout(blocks_buttons)

        self.verified_blocks_text = QTextEdit()
        self.verified_blocks_text.setReadOnly(True)
        blocks_layout.addWidget(self.verified_blocks_text)
        layout.addWidget(blocks_group)

        # Log
        log_group = QGroupBox("Verification Log")
        log_layout = QVBoxLayout(log_group)
        self.verification_log = QTextEdit()
        self.verification_log.setReadOnly(True)
        log_layout.addWidget(self.verification_log)
        layout.addWidget(log_group)

        # Add tab
        self.tab_widget.addTab(tab, "Verification Service")

        # Initialize verified blocks
        self.refresh_verified_blocks()

    def test_verify_block(self):
        """Test verifying a Cold Turkey block."""
        # Get parameters
        platform = self.verify_platform_combo.currentText()
        block_name = self.block_name_combo.currentText()

        self.verification_log.append(f"Verifying block '{block_name}' for platform '{platform}'...")

        # Create a worker for the verification
        class VerifyBlockWorker(Worker):
            def execute(self):
                # Create an event for cancellation
                import threading
                self.stop_event = threading.Event()

                result = self.verification_service.verify_block(
                    platform=self.platform,
                    block_name=self.block_name,
                    cancellable=True
                )

                if result.is_failure:
                    return {"success": False, "error": str(result.error)}

                # If successful, add to verified blocks
                if result.value:
                    add_result = self.verification_service.add_verified_block(
                        platform=self.platform,
                        block_name=self.block_name
                    )

                    if add_result.is_failure:
                        return {
                            "success": True,
                            "verified": True,
                            "added": False,
                            "error": str(add_result.error)
                        }

                    return {"success": True, "verified": True, "added": True}
                else:
                    return {"success": True, "verified": False}

            def cancel(self):
                """Cancel the verification process."""
                if hasattr(self, 'stop_event'):
                    self.stop_event.set()
                super().cancel()

        worker = VerifyBlockWorker()
        worker.verification_service = self.verification_service
        worker.platform = platform
        worker.block_name = block_name

        # Set callbacks
        worker.set_on_completed(self.on_verification_completed)
        worker.set_on_error(lambda error: self.verification_log.append(f"<span style='color:red'>Verification error: {error}</span>"))

        # Execute in background
        result = self.thread_service.execute_task("verify_block", worker)

        if result.is_success:
            self.verification_log.append("<span style='color:blue'>Verification started...</span>")

            # Update button states
            self.verify_button.setEnabled(False)
            self.cancel_verify_button.setEnabled(True)
        else:
            self.verification_log.append(f"<span style='color:red'>Failed to start verification: {result.error}</span>")

    def test_cancel_verification(self):
        """Test cancelling a verification operation."""
        self.verification_log.append("Cancelling verification...")

        # Cancel the task
        result = self.thread_service.cancel_task("verify_block")

        if result.is_success:
            self.verification_log.append("<span style='color:orange'>Verification cancelled</span>")

            # Update button states
            self.verify_button.setEnabled(True)
            self.cancel_verify_button.setEnabled(False)
        else:
            self.verification_log.append(f"<span style='color:red'>Failed to cancel verification: {result.error}</span>")

    def on_verification_completed(self, result):
        """Handle verification completed event."""
        if result["success"]:
            if result.get("verified", False):
                self.verification_log.append("<span style='color:green'>Block verified successfully</span>")

                if result.get("added", False):
                    self.verification_log.append("<span style='color:green'>Block added to verified blocks</span>")
                else:
                    error = result.get("error", "Unknown error")
                    self.verification_log.append(f"<span style='color:orange'>Block verified but not added: {error}</span>")

                # Refresh verified blocks
                self.refresh_verified_blocks()
            else:
                self.verification_log.append("<span style='color:orange'>Block verification failed</span>")
        else:
            self.verification_log.append(f"<span style='color:red'>Verification failed: {result['error']}</span>")

        # Update button states
        self.verify_button.setEnabled(True)
        self.cancel_verify_button.setEnabled(False)

    def refresh_verified_blocks(self):
        """Refresh the list of verified blocks."""
        self.verification_log.append("Refreshing verified blocks...")

        # Get verified blocks
        result = self.verification_service.get_verified_blocks()

        if result.is_success:
            blocks = result.value

            # Display blocks
            self.verified_blocks_text.clear()

            if blocks:
                for block in blocks:
                    platform = block.get("platform", "Unknown")
                    block_name = block.get("block_name", "Unknown")
                    self.verified_blocks_text.append(f"Platform: {platform}, Block: {block_name}")
            else:
                self.verified_blocks_text.append("No verified blocks found")

            self.verification_log.append(f"<span style='color:green'>Found {len(blocks)} verified blocks</span>")
        else:
            self.verification_log.append(f"<span style='color:red'>Failed to get verified blocks: {result.error}</span>")

    def clear_verified_blocks(self):
        """Clear all verified blocks."""
        self.verification_log.append("Clearing all verified blocks...")

        # Clear blocks
        result = self.verification_service.clear_verified_blocks()

        if result.is_success:
            self.verification_log.append("<span style='color:green'>All verified blocks cleared</span>")

            # Refresh display
            self.refresh_verified_blocks()
        else:
            self.verification_log.append(f"<span style='color:red'>Failed to clear verified blocks: {result.error}</span>")

    #----------------------------------------------------------------------------
    # Stress Test Tab Methods
    #----------------------------------------------------------------------------

    def create_stress_test_tab(self):
        """Create tab for stress testing the application."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Controls
        controls_group = QGroupBox("Stress Test Controls")
        controls_layout = QVBoxLayout(controls_group)

        # Number of threads
        threads_layout = QHBoxLayout()
        threads_layout.addWidget(QLabel("Number of Threads:"))
        self.stress_threads_spinner = QSpinBox()
        self.stress_threads_spinner.setRange(1, 50)
        self.stress_threads_spinner.setValue(10)
        threads_layout.addWidget(self.stress_threads_spinner)
        controls_layout.addLayout(threads_layout)

        # Duration
        duration_layout = QHBoxLayout()
        duration_layout.addWidget(QLabel("Test Duration (seconds):"))
        self.stress_duration_spinner = QSpinBox()
        self.stress_duration_spinner.setRange(5, 300)
        self.stress_duration_spinner.setValue(30)
        duration_layout.addWidget(self.stress_duration_spinner)
        controls_layout.addLayout(duration_layout)

        # Component selection
        component_layout = QHBoxLayout()
        component_layout.addWidget(QLabel("Component to Test:"))
        self.stress_component_combo = QComboBox()
        self.stress_component_combo.addItems([
            "Thread Service", "Config Repository", "Screenshot Service",
            "OCR Service", "All Services"
        ])
        component_layout.addWidget(self.stress_component_combo)
        controls_layout.addLayout(component_layout)

        # Buttons
        button_layout = QHBoxLayout()
        self.start_stress_button = QPushButton("Start Stress Test")
        self.start_stress_button.clicked.connect(self.start_stress_test)
        button_layout.addWidget(self.start_stress_button)

        self.stop_stress_button = QPushButton("Stop Stress Test")
        self.stop_stress_button.clicked.connect(self.stop_stress_test)
        self.stop_stress_button.setEnabled(False)
        button_layout.addWidget(self.stop_stress_button)

        controls_layout.addLayout(button_layout)
        layout.addWidget(controls_group)

        # Progress
        progress_group = QGroupBox("Stress Test Progress")
        progress_layout = QVBoxLayout(progress_group)

        self.stress_progress_bar = QProgressBar()
        self.stress_progress_bar.setRange(0, 100)
        self.stress_progress_bar.setValue(0)
        progress_layout.addWidget(self.stress_progress_bar)

        self.stress_status_label = QLabel("No stress test running")
        progress_layout.addWidget(self.stress_status_label)

        layout.addWidget(progress_group)

        # Statistics
        stats_group = QGroupBox("Stress Test Statistics")
        stats_layout = QVBoxLayout(stats_group)
        self.stress_stats_text = QTextEdit()
        self.stress_stats_text.setReadOnly(True)
        stats_layout.addWidget(self.stress_stats_text)
        layout.addWidget(stats_group)

        # Add tab
        self.tab_widget.addTab(tab, "Stress Test")

        # Initialize state
        self.stress_test_running = False
        self.stress_test_timer = QTimer()
        self.stress_test_timer.timeout.connect(self.update_stress_progress)
        self.stress_start_time = 0
        self.stress_tasks = []

    def start_stress_test(self):
        """Start a stress test of the selected component."""
        # Get parameters
        num_threads = self.stress_threads_spinner.value()
        duration = self.stress_duration_spinner.value()
        component = self.stress_component_combo.currentText()

        self.stress_stats_text.clear()
        self.stress_stats_text.append(f"Starting stress test of {component} with {num_threads} threads for {duration} seconds...")

        # Set up stress test state
        self.stress_test_running = True
        self.stress_start_time = time.time()
        self.stress_tasks = []
        self.stress_completed_tasks = 0
        self.stress_successful_tasks = 0
        self.stress_failed_tasks = 0

        # Start progress timer
        self.stress_test_timer.start(1000)  # Update every second

        # Update UI
        self.start_stress_button.setEnabled(False)
        self.stop_stress_button.setEnabled(True)
        self.stress_status_label.setText("Stress test running...")

        # Launch tasks based on component
        if component == "Thread Service":
            self._start_thread_service_stress(num_threads)
        elif component == "Config Repository":
            self._start_config_repo_stress(num_threads)
        elif component == "Screenshot Service":
            self._start_screenshot_service_stress(num_threads)
        elif component == "OCR Service":
            self._start_ocr_service_stress(num_threads)
        elif component == "All Services":
            self._start_all_services_stress(num_threads)
        else:
            self.stress_stats_text.append(f"<span style='color:red'>Unknown component: {component}</span>")
            self.stop_stress_test()

    def stop_stress_test(self):
        """Stop the current stress test."""
        if not self.stress_test_running:
            return

        self.stress_stats_text.append("Stopping stress test...")

        # Stop timer
        self.stress_test_timer.stop()

        # Cancel all tasks
        for task_id in self.stress_tasks:
            self.thread_service.cancel_task(task_id)

        # Update state
        self.stress_test_running = False

        # Update UI
        self.start_stress_button.setEnabled(True)
        self.stop_stress_button.setEnabled(False)
        self.stress_status_label.setText("Stress test stopped")

        # Final report
        elapsed = time.time() - self.stress_start_time
        self.stress_stats_text.append(f"Stress test completed after {elapsed:.1f} seconds")
        self.stress_stats_text.append(f"Completed tasks: {self.stress_completed_tasks}")
        self.stress_stats_text.append(f"Successful tasks: {self.stress_successful_tasks}")
        self.stress_stats_text.append(f"Failed tasks: {self.stress_failed_tasks}")

    def update_stress_progress(self):
        """Update the stress test progress."""
        if not self.stress_test_running:
            return

        # Calculate progress
        elapsed = time.time() - self.stress_start_time
        duration = self.stress_duration_spinner.value()

        if elapsed >= duration:
            # Test complete
            self.stop_stress_test()
            return

        # Update progress bar
        progress = int((elapsed / duration) * 100)
        self.stress_progress_bar.setValue(progress)

        # Update status
        self.stress_status_label.setText(f"Running... {elapsed:.1f}/{duration} seconds")

        # Update stats
        self.stress_stats_text.append(f"Progress update: {self.stress_completed_tasks} completed, "
                                     f"{self.stress_successful_tasks} successful, "
                                     f"{self.stress_failed_tasks} failed")

    def _start_thread_service_stress(self, num_threads):
        """Start thread service stress test."""
        self.stress_stats_text.append("Thread Service stress test: Running many short-lived tasks...")

        # Launch tasks
        for i in range(num_threads):
            self._launch_thread_service_task(i)

    def _launch_thread_service_task(self, index):
        """Launch a thread service stress test task."""
        # Create worker that does multiple iterations
        class ThreadStressWorker(Worker):
            def execute(self):
                results = []

                # Run until cancelled or the stress test completes
                while not self.cancel_requested:
                    try:
                        # Random sleep duration
                        import random
                        duration = random.uniform(0.1, 1.0)

                        # Sleep
                        time.sleep(duration)

                        # Report progress
                        self.report_progress(50, f"Iteration completed with duration {duration:.2f}")

                        # Add to results
                        results.append(duration)

                        # Occasionally report error to test error handling
                        if random.random() < 0.05:  # 5% chance
                            self.report_error(f"Random error in iteration {len(results)}")
                    except Exception as e:
                        self.report_error(f"Exception in thread stress task: {e}")

                return {
                    "iterations": len(results),
                    "total_duration": sum(results),
                    "avg_duration": sum(results) / len(results) if results else 0
                }

        worker = ThreadStressWorker()

        # Set callbacks
        worker.set_on_progress(lambda percent, msg: None)  # Ignore progress updates
        worker.set_on_completed(self.on_stress_task_completed)
        worker.set_on_error(self.on_stress_task_error)

        # Execute in background
        task_id = f"thread_stress_{index}"
        result = self.thread_service.execute_task(task_id, worker)

        if result.is_success:
            self.stress_tasks.append(task_id)
        else:
            self.stress_stats_text.append(f"<span style='color:red'>Failed to start task {index}: {result.error}</span>")

    def _start_config_repo_stress(self, num_threads):
        """Start config repository stress test."""
        self.stress_stats_text.append("Config Repository stress test: Concurrent load/save operations...")

        # Launch tasks
        for i in range(num_threads):
            self._launch_config_repo_task(i)

    def _launch_config_repo_task(self, index):
        """Launch a config repository stress test task."""
        # Create worker that alternates between load and save
        class ConfigStressWorker(Worker):
            def execute(self):
                results = {"loads": 0, "saves": 0, "load_errors": 0, "save_errors": 0}

                # Run until cancelled or the stress test completes
                while not self.cancel_requested:
                    try:
                        # Alternate between load and save
                        if results["loads"] <= results["saves"]:
                            # Load config
                            config_result = self.config_repo.load_config(force_reload=True)
                            if config_result.is_failure:
                                results["load_errors"] += 1
                                self.report_error(f"Load error: {config_result.error}")
                            else:
                                results["loads"] += 1
                        else:
                            # Save config with a unique test value
                            config_result = self.config_repo.load_config()
                            if config_result.is_failure:
                                results["load_errors"] += 1
                                self.report_error(f"Load error before save: {config_result.error}")
                            else:
                                config = config_result.value
                                config[f"stress_test_{index}_{results['saves']}"] = time.time()

                                save_result = self.config_repo.save_config(config)
                                if save_result.is_failure:
                                    results["save_errors"] += 1
                                    self.report_error(f"Save error: {save_result.error}")
                                else:
                                    results["saves"] += 1

                        # Small delay to prevent too rapid operations
                        time.sleep(0.1)

                    except Exception as e:
                        self.report_error(f"Exception in config stress task: {e}")

                return results

        worker = ConfigStressWorker()
        worker.config_repo = self.config_repository

        # Set callbacks
        worker.set_on_completed(self.on_stress_task_completed)
        worker.set_on_error(self.on_stress_task_error)

        # Execute in background
        task_id = f"config_stress_{index}"
        result = self.thread_service.execute_task(task_id, worker)

        if result.is_success:
            self.stress_tasks.append(task_id)
        else:
            self.stress_stats_text.append(f"<span style='color:red'>Failed to start task {index}: {result.error}</span>")

    def _start_screenshot_service_stress(self, num_threads):
        """Start screenshot service stress test."""
        self.stress_stats_text.append("Screenshot Service stress test: Concurrent screenshot captures...")

        # Select entire screen as region if none selected
        if not hasattr(self, 'selected_region') or not self.selected_region:
            # Use entire screen
            screen = QApplication.primaryScreen()
            rect = screen.geometry()
            self.stress_region = (0, 0, rect.width(), rect.height())
        else:
            self.stress_region = self.selected_region

        # Launch tasks
        for i in range(num_threads):
            self._launch_screenshot_task(i)

    def _launch_screenshot_task(self, index):
        """Launch a screenshot service stress test task."""
        class ScreenshotStressWorker(Worker):
            def execute(self):
                results = {"captures": 0, "errors": 0, "total_time": 0}

                # Run until cancelled or the stress test completes
                while not self.cancel_requested:
                    try:
                        # Time the capture
                        start_time = time.time()

                        # Capture screenshot
                        capture_result = self.screenshot_service.capture_region(self.region)

                        # Calculate time
                        capture_time = time.time() - start_time
                        results["total_time"] += capture_time

                        if capture_result.is_failure:
                            results["errors"] += 1
                            self.report_error(f"Capture error: {capture_result.error}")
                        else:
                            results["captures"] += 1

                            # Report occasional progress
                            if results["captures"] % 10 == 0:
                                self.report_progress(
                                    50,
                                    f"Completed {results['captures']} captures, avg time: {results['total_time']/results['captures']:.3f}s"
                                )

                        # Small delay to prevent too rapid operations
                        time.sleep(0.1)

                    except Exception as e:
                        self.report_error(f"Exception in screenshot stress task: {e}")

                # Calculate average time
                avg_time = results["total_time"] / results["captures"] if results["captures"] > 0 else 0
                results["avg_time"] = avg_time

                return results

        worker = ScreenshotStressWorker()
        worker.screenshot_service = self.screenshot_service
        worker.region = self.stress_region

        # Set callbacks
        worker.set_on_completed(self.on_stress_task_completed)
        worker.set_on_error(self.on_stress_task_error)

        # Execute in background
        task_id = f"screenshot_stress_{index}"
        result = self.thread_service.execute_task(task_id, worker)

        if result.is_success:
            self.stress_tasks.append(task_id)
        else:
            self.stress_stats_text.append(f"<span style='color:red'>Failed to start task {index}: {result.error}</span>")

    def _start_ocr_service_stress(self, num_threads):
        """Start OCR service stress test."""
        self.stress_stats_text.append("OCR Service stress test: Concurrent OCR operations...")

        # Select entire screen as region if none selected
        if not hasattr(self, 'ocr_region') or not self.ocr_region:
            # Use entire screen
            screen = QApplication.primaryScreen()
            rect = screen.geometry()
            self.stress_ocr_region = (0, 0, rect.width(), rect.height())
        else:
            self.stress_ocr_region = self.ocr_region

        # Launch tasks
        for i in range(num_threads):
            self._launch_ocr_task(i)

    def _launch_ocr_task(self, index):
        """Launch an OCR service stress test task."""
        class OcrStressWorker(Worker):
            def execute(self):
                results = {"ocr_operations": 0, "errors": 0, "total_time": 0}

                # Run until cancelled or the stress test completes
                while not self.cancel_requested:
                    try:
                        # Capture screenshot
                        capture_result = self.screenshot_service.capture_region(self.region)

                        if capture_result.is_failure:
                            results["errors"] += 1
                            self.report_error(f"Capture error: {capture_result.error}")
                            continue

                        image = capture_result.value

                        # Time the OCR operation
                        start_time = time.time()

                        # Perform OCR
                        ocr_result = self.ocr_service.extract_text(image)

                        # Calculate time
                        ocr_time = time.time() - start_time
                        results["total_time"] += ocr_time

                        if ocr_result.is_failure:
                            results["errors"] += 1
                            self.report_error(f"OCR error: {ocr_result.error}")
                        else:
                            results["ocr_operations"] += 1

                            # Report occasional progress
                            if results["ocr_operations"] % 5 == 0:
                                self.report_progress(
                                    50,
                                    f"Completed {results['ocr_operations']} OCR ops, avg time: {results['total_time']/results['ocr_operations']:.3f}s"
                                )

                        # Larger delay for OCR to prevent overwhelming the CPU
                        time.sleep(0.5)

                    except Exception as e:
                        self.report_error(f"Exception in OCR stress task: {e}")

                # Calculate average time
                avg_time = results["total_time"] / results["ocr_operations"] if results["ocr_operations"] > 0 else 0
                results["avg_time"] = avg_time

                return results

        worker = OcrStressWorker()
        worker.screenshot_service = self.screenshot_service
        worker.ocr_service = self.ocr_service
        worker.region = self.stress_ocr_region

        # Set callbacks
        worker.set_on_completed(self.on_stress_task_completed)
        worker.set_on_error(self.on_stress_task_error)

        # Execute in background
        task_id = f"ocr_stress_{index}"
        result = self.thread_service.execute_task(task_id, worker)

        if result.is_success:
            self.stress_tasks.append(task_id)
        else:
            self.stress_stats_text.append(f"<span style='color:red'>Failed to start task {index}: {result.error}</span>")

    def _start_all_services_stress(self, num_threads):
        """Start a comprehensive stress test of all services."""
        self.stress_stats_text.append("All Services stress test: Testing all components simultaneously...")

        # Allocate threads among services
        thread_counts = {
            "thread": max(1, int(num_threads * 0.3)),
            "config": max(1, int(num_threads * 0.2)),
            "screenshot": max(1, int(num_threads * 0.3)),
            "ocr": max(1, int(num_threads * 0.2))
        }

        # Launch tasks for each service
        for i in range(thread_counts["thread"]):
            self._launch_thread_service_task(i)

        for i in range(thread_counts["config"]):
            self._launch_config_repo_task(i)

        for i in range(thread_counts["screenshot"]):
            self._launch_screenshot_task(i)

        for i in range(thread_counts["ocr"]):
            self._launch_ocr_task(i)

        self.stress_stats_text.append(f"Launched {sum(thread_counts.values())} tasks across all services")

    def on_stress_task_completed(self, result):
        """Handle completion of a stress test task."""
        self.stress_completed_tasks += 1
        self.stress_successful_tasks += 1

        # Log detailed results
        self.stress_stats_text.append(f"Task completed with result: {result}")

    def on_stress_task_error(self, error):
        """Handle error in a stress test task."""
        self.stress_completed_tasks += 1
        self.stress_failed_tasks += 1

        # Log error
        self.stress_stats_text.append(f"<span style='color:red'>Task error: {error}</span>")


def main():
    """Main entry point for the test application."""
    try:
        app = QApplication(sys.argv)
        window = ThreadingTestApp()
        window.show()
        return app.exec()
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()

        # Try to show error in dialog
        try:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(None, "Fatal Error",
                                 f"An unrecoverable error occurred:\n\n{e}\n\n{traceback.format_exc()}")
        except:
            pass

        return 1


if __name__ == "__main__":
    sys.exit(main())