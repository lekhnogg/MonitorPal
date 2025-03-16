#!/usr/bin/env python3
"""
ThreadServiceTester: A test application for QtBackgroundTaskService

This application provides a comprehensive test suite for validating the
QtBackgroundTaskService implementation. It includes tests for:
- Basic task execution and lifecycle
- Progress reporting
- Error handling and recovery
- Task cancellation
- Parallel execution
- Resource cleanup
- Stress testing
"""
import sys
import os
import time
import random
import logging
import json
from typing import Dict, Any, List, Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QProgressBar, QGroupBox,
    QListWidget, QListWidgetItem, QSplitter, QTabWidget,
    QCheckBox, QSpinBox, QComboBox, QGridLayout, QMessageBox
)
from PySide6.QtCore import Qt, QTimer, Slot, QSize

# Ensure proper path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

# Import required components
from src.domain.services.i_background_task_service import IBackgroundTaskService, Worker, TaskCancelledException
from src.domain.services.i_logger_service import ILoggerService
from src.infrastructure.logging.logger_service import ConsoleLoggerService
from src.infrastructure.threading.qt_background_task_service import QtBackgroundTaskService
from src.domain.common.result import Result


# =============== LOG HANDLER ===============

class UILogHandler(logging.Handler):
    """Custom log handler to redirect logs to the UI."""

    def __init__(self, text_edit):
        super().__init__()
        self.text_edit = text_edit
        self.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

    def emit(self, record):
        msg = self.format(record)
        # Thread-safe update using Qt's signal/slot
        from PySide6.QtCore import QMetaObject, Qt, Q_ARG
        QMetaObject.invokeMethod(
            self.text_edit,
            "append_log",
            Qt.QueuedConnection,
            Q_ARG(str, msg),
            Q_ARG(int, record.levelno)
        )


# =============== TEST WORKERS ===============

class SimpleWorker(Worker[str]):
    """Worker that performs a simple task with progress updates."""

    def __init__(self,
                 duration: int = 3,
                 should_fail: bool = False,
                 ignore_cancel: bool = False,
                 logger: Optional[ILoggerService] = None):
        super().__init__()
        self.duration = duration
        self.should_fail = should_fail
        self.ignore_cancel = ignore_cancel
        self.logger = logger

    def initialize(self) -> None:
        if self.logger:
            self.logger.info(f"Initializing SimpleWorker: duration={self.duration}s, fail={self.should_fail}")

    def execute(self) -> str:
        if self.logger:
            self.logger.info("SimpleWorker execution started")

        start_time = time.time()
        total_steps = self.duration * 10  # 10 steps per second

        for step in range(total_steps):
            # Check for cancellation
            if not self.ignore_cancel and self.cancel_requested:
                if self.logger:
                    self.logger.info("SimpleWorker cancelled")
                raise TaskCancelledException("Task was cancelled")

            # Calculate progress
            progress = int((step / total_steps) * 100)
            self.report_progress(
                progress,
                f"Processing step {step + 1}/{total_steps} ({progress}%)"
            )

            # Simulate work
            time.sleep(0.1)

            # Introduce failure if configured
            if self.should_fail and progress > 60:
                if self.logger:
                    self.logger.warning("SimpleWorker simulating failure")
                raise RuntimeError("Simulated failure in SimpleWorker")

        elapsed = time.time() - start_time
        result = f"SimpleWorker completed in {elapsed:.2f}s"

        if self.logger:
            self.logger.info(result)

        return result

    def cleanup(self) -> None:
        if self.logger:
            self.logger.info("SimpleWorker cleanup called")


class CPUIntensiveWorker(Worker[Dict[str, Any]]):
    """Worker that performs CPU-intensive calculations."""

    def __init__(self,
                 iterations: int = 3,
                 logger: Optional[ILoggerService] = None):
        super().__init__()
        self.iterations = iterations
        self.logger = logger

    def initialize(self) -> None:
        if self.logger:
            self.logger.info(f"Initializing CPUIntensiveWorker: iterations={self.iterations}")

    def execute(self) -> Dict[str, Any]:
        if self.logger:
            self.logger.info("CPUIntensiveWorker execution started")

        start_time = time.time()
        results = {}

        for i in range(self.iterations):
            # Check for cancellation
            if self.cancel_requested:
                if self.logger:
                    self.logger.info("CPUIntensiveWorker cancelled")
                raise TaskCancelledException("Task was cancelled")

            # Report progress
            progress = int((i / self.iterations) * 100)
            self.report_progress(
                progress,
                f"Calculating primes batch {i + 1}/{self.iterations}"
            )

            # Perform CPU-intensive calculation - find prime numbers
            iteration_start = time.time()
            batch_size = 10000 * (i + 1)
            primes = []

            for n in range(2, batch_size):
                # Periodically check for cancellation during long calculations
                if n % 1000 == 0 and self.cancel_requested:
                    if self.logger:
                        self.logger.info("CPUIntensiveWorker cancelled during calculation")
                    raise TaskCancelledException("Task was cancelled")

                # Simple primality test
                if all(n % j != 0 for j in range(2, int(n ** 0.5) + 1)):
                    primes.append(n)

            # Record results for this iteration
            iteration_time = time.time() - iteration_start
            results[f"batch_{i + 1}"] = {
                "range": f"2 to {batch_size}",
                "primes_found": len(primes),
                "largest_prime": primes[-1] if primes else None,
                "calculation_time": iteration_time
            }

            if self.logger:
                self.logger.info(f"Completed batch {i + 1} in {iteration_time:.2f}s, found {len(primes)} primes")

        total_time = time.time() - start_time

        # Prepare final result
        final_result = {
            "total_time": total_time,
            "iterations": self.iterations,
            "batches": results
        }

        if self.logger:
            self.logger.info(f"CPUIntensiveWorker completed in {total_time:.2f}s")

        return final_result

    def cleanup(self) -> None:
        if self.logger:
            self.logger.info("CPUIntensiveWorker cleanup called")


class IOBoundWorker(Worker[Dict[str, Any]]):
    """Worker that simulates I/O-bound operations."""

    def __init__(self,
                 operations: int = 5,
                 delay: float = 0.5,
                 logger: Optional[ILoggerService] = None):
        super().__init__()
        self.operations = operations
        self.delay = delay
        self.logger = logger

    def initialize(self) -> None:
        if self.logger:
            self.logger.info(f"Initializing IOBoundWorker: operations={self.operations}, delay={self.delay}s")

    def execute(self) -> Dict[str, Any]:
        if self.logger:
            self.logger.info("IOBoundWorker execution started")

        start_time = time.time()
        results = []

        for i in range(self.operations):
            # Check for cancellation
            if self.cancel_requested:
                if self.logger:
                    self.logger.info("IOBoundWorker cancelled")
                raise TaskCancelledException("Task was cancelled")

            # Report progress
            progress = int((i / self.operations) * 100)
            self.report_progress(
                progress,
                f"I/O operation {i + 1}/{self.operations}"
            )

            # Simulate I/O operation with random success/failure
            operation_start = time.time()
            time.sleep(self.delay)  # Simulate I/O wait
            operation_time = time.time() - operation_start

            # Record operation details
            results.append({
                "operation": i + 1,
                "duration": operation_time,
                "timestamp": time.time()
            })

            if self.logger:
                self.logger.info(f"Completed I/O operation {i + 1} in {operation_time:.2f}s")

        total_time = time.time() - start_time

        # Prepare final result
        final_result = {
            "total_time": total_time,
            "operations_completed": self.operations,
            "average_operation_time": sum(r["duration"] for r in results) / len(results),
            "operations": results
        }

        if self.logger:
            self.logger.info(f"IOBoundWorker completed in {total_time:.2f}s")

        return final_result

    def cleanup(self) -> None:
        if self.logger:
            self.logger.info("IOBoundWorker cleanup called")


class MemoryLeakTestWorker(Worker[Dict[str, Any]]):
    """Worker that tests memory management by allocating and releasing memory."""

    def __init__(self,
                 allocations: int = 5,
                 size_mb: int = 10,
                 logger: Optional[ILoggerService] = None):
        super().__init__()
        self.allocations = allocations
        self.size_mb = size_mb
        self.logger = logger
        self._data = None  # Will hold allocated memory

    def initialize(self) -> None:
        if self.logger:
            self.logger.info(
                f"Initializing MemoryLeakTestWorker: allocations={self.allocations}, size={self.size_mb}MB")

    def execute(self) -> Dict[str, Any]:
        if self.logger:
            self.logger.info("MemoryLeakTestWorker execution started")

        start_time = time.time()
        results = []

        for i in range(self.allocations):
            # Check for cancellation
            if self.cancel_requested:
                if self.logger:
                    self.logger.info("MemoryLeakTestWorker cancelled")
                # Clear data before raising exception
                self._data = None
                raise TaskCancelledException("Task was cancelled")

            # Report progress
            progress = int((i / self.allocations) * 100)
            self.report_progress(
                progress,
                f"Allocation {i + 1}/{self.allocations} ({self.size_mb}MB)"
            )

            # Allocate memory
            allocation_start = time.time()

            # Create a byte array of specified size
            bytes_to_allocate = self.size_mb * 1024 * 1024
            self._data = bytearray(bytes_to_allocate)

            # Simulate some work with the allocated memory
            for j in range(0, bytes_to_allocate, 1024 * 1024):
                # Write some data
                if j + 100 < bytes_to_allocate:
                    self._data[j:j + 100] = b'x' * 100

            # Hold memory for a moment
            time.sleep(0.5)

            # Record allocation details
            allocation_time = time.time() - allocation_start
            results.append({
                "allocation": i + 1,
                "size_mb": self.size_mb,
                "allocation_time": allocation_time
            })

            # Release memory for next iteration
            self._data = None

            if self.logger:
                self.logger.info(f"Completed allocation {i + 1} in {allocation_time:.2f}s")

        total_time = time.time() - start_time

        # Prepare final result
        final_result = {
            "total_time": total_time,
            "allocations_completed": self.allocations,
            "total_memory_allocated_mb": self.allocations * self.size_mb,
            "allocations": results
        }

        if self.logger:
            self.logger.info(f"MemoryLeakTestWorker completed in {total_time:.2f}s")

        return final_result

    def cleanup(self) -> None:
        # Ensure memory is released
        self._data = None
        if self.logger:
            self.logger.info("MemoryLeakTestWorker cleanup called")


# =============== UI COMPONENTS ===============

class LogTextEdit(QTextEdit):
    """TextEdit widget that can display colored log messages."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)

    @Slot(str, int)
    def append_log(self, text, level):
        # Set color based on log level
        if level >= logging.ERROR:
            self.setTextColor(Qt.red)
        elif level >= logging.WARNING:
            self.setTextColor(Qt.darkYellow)
        elif level >= logging.INFO:
            self.setTextColor(Qt.black)
        else:  # DEBUG
            self.setTextColor(Qt.darkGray)

        # Append text
        self.append(text)

        # Reset color
        self.setTextColor(Qt.black)

        # Scroll to bottom
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())


class TaskListItem(QListWidgetItem):
    """List item representing a task in the UI."""

    def __init__(self, task_id, task_type, description=""):
        super().__init__()
        self.task_id = task_id
        self.task_type = task_type
        self.description = description

        # Set initial data
        self.setData(Qt.UserRole, {
            "id": task_id,
            "type": task_type,
            "status": "Pending",
            "progress": 0,
            "start_time": time.time()
        })

        # Update display
        self.update_display()

    def update_status(self, status, progress=None):
        data = self.data(Qt.UserRole)
        data["status"] = status
        if progress is not None:
            data["progress"] = progress
        self.setData(Qt.UserRole, data)
        self.update_display()

    def update_display(self):
        data = self.data(Qt.UserRole)
        elapsed = time.time() - data["start_time"]

        # Format task display text
        display_text = f"{data['id']} ({data['type']}): {data['status']} - {data['progress']}% [{elapsed:.1f}s]"
        self.setText(display_text)

        # Set color based on status
        if data["status"].startswith("Failed"):
            self.setForeground(Qt.red)
        elif data["status"] == "Completed":
            self.setForeground(Qt.darkGreen)
        elif data["status"] == "Cancelling":
            self.setForeground(Qt.darkYellow)
        else:
            self.setForeground(Qt.black)


# =============== MAIN WINDOW ===============

class ThreadServiceTester(QMainWindow):
    """Main window for testing the QtBackgroundTaskService."""

    def __init__(self):
        super().__init__()

        # Set up window
        self.setWindowTitle("Qt Thread Service Tester")
        self.setMinimumSize(1000, 800)

        # Set up logger
        self.logger = ConsoleLoggerService(level=logging.DEBUG)

        # Create thread service
        self.thread_service = QtBackgroundTaskService(self.logger)

        # Initialize task tracking
        self.tasks = {}

        # Create UI
        self._create_ui()

        # Set up logger for UI
        log_handler = UILogHandler(self.log_text)
        logging.getLogger().addHandler(log_handler)
        logging.getLogger().setLevel(logging.DEBUG)

        # Start refresh timer
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_tasks)
        self.refresh_timer.start(500)  # Update every 500ms

        # Log startup
        self.logger.info("Thread Service Tester initialized")
        self.logger.info("QtBackgroundTaskService testing application ready")

    def _create_ui(self):
        """Create the user interface."""
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        main_layout = QVBoxLayout(central_widget)

        # Create splitter for top/bottom sections
        splitter = QSplitter(Qt.Vertical)
        main_layout.addWidget(splitter, 1)

        # ===== Top section - Controls and active tasks =====
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)

        # Task configuration
        config_group = QGroupBox("Task Configuration")
        config_layout = QGridLayout()
        config_group.setLayout(config_layout)

        # Worker type selection
        config_layout.addWidget(QLabel("Worker Type:"), 0, 0)
        self.worker_type_combo = QComboBox()
        self.worker_type_combo.addItems([
            "SimpleWorker",
            "CPUIntensiveWorker",
            "IOBoundWorker",
            "MemoryLeakTestWorker"
        ])
        config_layout.addWidget(self.worker_type_combo, 0, 1)

        # Duration/Iterations
        config_layout.addWidget(QLabel("Duration/Iterations:"), 0, 2)
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(1, 20)
        self.duration_spin.setValue(3)
        config_layout.addWidget(self.duration_spin, 0, 3)

        # Should fail checkbox
        self.should_fail_check = QCheckBox("Simulate Failure")
        config_layout.addWidget(self.should_fail_check, 1, 0)

        # Ignore cancellation checkbox
        self.ignore_cancel_check = QCheckBox("Ignore Cancellation")
        config_layout.addWidget(self.ignore_cancel_check, 1, 1)

        top_layout.addWidget(config_group)

        # Control buttons
        buttons_layout = QHBoxLayout()

        self.start_button = QPushButton("Start Single Task")
        self.start_button.clicked.connect(self._start_task)
        buttons_layout.addWidget(self.start_button)

        self.start_multi_button = QPushButton("Start 5 Tasks")
        self.start_multi_button.clicked.connect(self._start_multiple_tasks)
        buttons_layout.addWidget(self.start_multi_button)

        self.stress_test_button = QPushButton("Stress Test (20 Tasks)")
        self.stress_test_button.clicked.connect(self._start_stress_test)
        buttons_layout.addWidget(self.stress_test_button)

        top_layout.addLayout(buttons_layout)

        # Cancellation buttons
        cancel_layout = QHBoxLayout()

        self.cancel_button = QPushButton("Cancel Selected Task")
        self.cancel_button.clicked.connect(self._cancel_selected_task)
        cancel_layout.addWidget(self.cancel_button)

        self.cancel_all_button = QPushButton("Cancel All Tasks")
        self.cancel_all_button.clicked.connect(self._cancel_all_tasks)
        cancel_layout.addWidget(self.cancel_all_button)

        self.cleanup_button = QPushButton("Clean Up Completed Tasks")
        self.cleanup_button.clicked.connect(self._cleanup_completed_tasks)
        cancel_layout.addWidget(self.cleanup_button)

        top_layout.addLayout(cancel_layout)

        # Active tasks section
        tasks_group = QGroupBox("Active Tasks")
        tasks_layout = QVBoxLayout()

        self.task_list = QListWidget()
        self.task_list.setSelectionMode(QListWidget.SingleSelection)
        self.task_list.currentItemChanged.connect(self._on_selected_task_changed)
        tasks_layout.addWidget(self.task_list)

        # Task statistics
        stats_layout = QHBoxLayout()

        self.running_label = QLabel("Running: 0")
        stats_layout.addWidget(self.running_label)

        self.completed_label = QLabel("Completed: 0")
        stats_layout.addWidget(self.completed_label)

        self.failed_label = QLabel("Failed: 0")
        stats_layout.addWidget(self.failed_label)

        tasks_layout.addLayout(stats_layout)

        tasks_group.setLayout(tasks_layout)
        top_layout.addWidget(tasks_group, 1)

        # Progress section
        progress_group = QGroupBox("Selected Task Progress")
        progress_layout = QVBoxLayout()

        self.progress_bar = QProgressBar()
        progress_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("No task selected")
        progress_layout.addWidget(self.status_label)

        progress_group.setLayout(progress_layout)
        top_layout.addWidget(progress_group)

        # Add top section to splitter
        splitter.addWidget(top_widget)

        # ===== Bottom section - Results and logs =====
        bottom_widget = QTabWidget()

        # Results tab
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        bottom_widget.addTab(self.results_text, "Results")

        # Log tab
        self.log_text = LogTextEdit()
        bottom_widget.addTab(self.log_text, "Logs")

        # Add bottom section to splitter
        splitter.addWidget(bottom_widget)

        # Set initial splitter sizes
        splitter.setSizes([600, 200])

    def _start_task(self):
        """Start a single task based on current configuration."""
        worker_type = self.worker_type_combo.currentText()
        duration = self.duration_spin.value()
        should_fail = self.should_fail_check.isChecked()
        ignore_cancel = self.ignore_cancel_check.isChecked()

        # Generate task ID
        task_id = f"{worker_type.lower()}_{int(time.time())}"

        # Create appropriate worker
        worker = None
        if worker_type == "SimpleWorker":
            worker = SimpleWorker(
                duration=duration,
                should_fail=should_fail,
                ignore_cancel=ignore_cancel,
                logger=self.logger
            )
        elif worker_type == "CPUIntensiveWorker":
            worker = CPUIntensiveWorker(
                iterations=duration,
                logger=self.logger
            )
        elif worker_type == "IOBoundWorker":
            worker = IOBoundWorker(
                operations=duration,
                delay=0.5,
                logger=self.logger
            )
        elif worker_type == "MemoryLeakTestWorker":
            worker = MemoryLeakTestWorker(
                allocations=duration,
                size_mb=10,
                logger=self.logger
            )

        if not worker:
            self.logger.error(f"Unknown worker type: {worker_type}")
            return

        # Set up callbacks
        worker.set_on_started(lambda: self._on_task_started(task_id))
        worker.set_on_progress(lambda p, m: self._on_task_progress(task_id, p, m))
        worker.set_on_completed(lambda r: self._on_task_completed(task_id, r))
        worker.set_on_error(lambda e: self._on_task_error(task_id, e))

        # Execute task
        self.logger.info(
            f"Starting task {task_id} - {worker_type} (duration={duration}, fail={should_fail}, ignore_cancel={ignore_cancel})")
        result = self.thread_service.execute_task(task_id, worker)

        if result.is_success:
            # Add to task list
            item = TaskListItem(task_id, worker_type, f"Duration: {duration}")
            self.task_list.addItem(item)
            self.tasks[task_id] = {
                "item": item,
                "type": worker_type
            }

            # Select the new task
            self.task_list.setCurrentItem(item)
        else:
            self.logger.error(f"Failed to start task: {result.error}")

    def _start_multiple_tasks(self):
        """Start multiple tasks with varying configurations."""
        self.logger.info("Starting 5 tasks with varied configurations")

        for i in range(5):
            # Vary configurations
            worker_type = random.choice([
                "SimpleWorker",
                "CPUIntensiveWorker",
                "IOBoundWorker",
                "MemoryLeakTestWorker"
            ])
            duration = random.randint(2, 8)
            should_fail = random.random() < 0.2  # 20% chance of failure
            ignore_cancel = random.random() < 0.1  # 10% chance of ignoring cancellation

            # Generate task ID
            task_id = f"multi_{worker_type.lower()}_{int(time.time())}_{i}"

            # Create appropriate worker
            worker = None
            if worker_type == "SimpleWorker":
                worker = SimpleWorker(
                    duration=duration,
                    should_fail=should_fail,
                    ignore_cancel=ignore_cancel,
                    logger=self.logger
                )
            elif worker_type == "CPUIntensiveWorker":
                worker = CPUIntensiveWorker(
                    iterations=duration,
                    logger=self.logger
                )
            elif worker_type == "IOBoundWorker":
                worker = IOBoundWorker(
                    operations=duration,
                    delay=0.3,
                    logger=self.logger
                )
            elif worker_type == "MemoryLeakTestWorker":
                worker = MemoryLeakTestWorker(
                    allocations=duration,
                    size_mb=5,
                    logger=self.logger
                )

            if not worker:
                self.logger.error(f"Unknown worker type: {worker_type}")
                continue

            # Set up callbacks
            worker.set_on_started(lambda tid=task_id: self._on_task_started(tid))
            worker.set_on_progress(lambda p, m, tid=task_id: self._on_task_progress(tid, p, m))
            worker.set_on_completed(lambda r, tid=task_id: self._on_task_completed(tid, r))
            worker.set_on_error(lambda e, tid=task_id: self._on_task_error(tid, e))

            # Execute task
            self.logger.info(
                f"Starting task {task_id} - {worker_type} (duration={duration}, fail={should_fail}, ignore_cancel={ignore_cancel})")
            result = self.thread_service.execute_task(task_id, worker)

            if result.is_success:
                # Add to task list
                item = TaskListItem(task_id, worker_type, f"Duration: {duration}")
                self.task_list.addItem(item)
                self.tasks[task_id] = {
                    "item": item,
                    "type": worker_type
                }
            else:
                self.logger.error(f"Failed to start task: {result.error}")

    def _start_stress_test(self):
        """Start many tasks simultaneously to stress test the thread service."""
        self.logger.info("Starting stress test with 20 tasks")

        for i in range(20):
            # Generate varied configurations
            worker_type = random.choice([
                "SimpleWorker",
                "CPUIntensiveWorker",
                "IOBoundWorker"
            ])
            duration = random.randint(2, 6)
            should_fail = random.random() < 0.1  # 10% chance of failure

            # Generate task ID
            task_id = f"stress_{worker_type.lower()}_{int(time.time())}_{i}"

            # Create appropriate worker
            worker = None
            if worker_type == "SimpleWorker":
                worker = SimpleWorker(
                    duration=duration,
                    should_fail=should_fail,
                    logger=self.logger
                )
            elif worker_type == "CPUIntensiveWorker":
                worker = CPUIntensiveWorker(
                    iterations=max(1, duration // 2),  # Reduce iterations for stress test
                    logger=self.logger
                )
            elif worker_type == "IOBoundWorker":
                worker = IOBoundWorker(
                    operations=duration,
                    delay=0.2,
                    logger=self.logger
                )

            if not worker:
                self.logger.error(f"Unknown worker type: {worker_type}")
                continue

            # Set up callbacks
            worker.set_on_started(lambda tid=task_id: self._on_task_started(tid))
            worker.set_on_progress(lambda p, m, tid=task_id: self._on_task_progress(tid, p, m))
            worker.set_on_completed(lambda r, tid=task_id: self._on_task_completed(tid, r))
            worker.set_on_error(lambda e, tid=task_id: self._on_task_error(tid, e))

            # Execute task
            result = self.thread_service.execute_task(task_id, worker)

            if result.is_success:
                # Add to task list
                item = TaskListItem(task_id, worker_type)
                self.task_list.addItem(item)
                self.tasks[task_id] = {
                    "item": item,
                    "type": worker_type
                }
            else:
                self.logger.error(f"Failed to start task: {result.error}")

    def _cancel_selected_task(self):
        """Cancel the currently selected task."""
        # Get selected item
        current_item = self.task_list.currentItem()
        if not current_item or not isinstance(current_item, TaskListItem):
            self.logger.warning("No task selected")
            return

        task_id = current_item.task_id
        self.logger.info(f"Cancelling task {task_id}")

        # Request cancellation
        result = self.thread_service.cancel_task(task_id)

        if result.is_success:
            current_item.update_status("Cancelling")
            self.logger.info(f"Cancellation requested for task {task_id}")
        else:
            self.logger.error(f"Failed to cancel task: {result.error}")

    def _cancel_all_tasks(self):
        """Cancel all running tasks."""
        running_tasks = self.thread_service.get_running_tasks()
        if not running_tasks:
            self.logger.warning("No tasks running")
            return

        self.logger.info(f"Cancelling all tasks ({len(running_tasks)} running)")

        # Cancel all tasks
        self.thread_service.cancel_all_tasks()

        # Update UI
        for task_id in running_tasks:
            if task_id in self.tasks:
                self.tasks[task_id]["item"].update_status("Cancelling")

        self.logger.info("Cancellation requested for all tasks")

    def _cleanup_completed_tasks(self):
        """Remove completed tasks from the list."""
        for i in range(self.task_list.count() - 1, -1, -1):
            item = self.task_list.item(i)
            if isinstance(item, TaskListItem):
                data = item.data(Qt.UserRole)
                if data["status"] in ["Completed", "Failed"]:
                    # Remove from list
                    self.task_list.takeItem(i)

                    # Remove from tasks dictionary
                    if item.task_id in self.tasks:
                        del self.tasks[item.task_id]

        self.logger.info("Cleaned up completed tasks")

    def _refresh_tasks(self):
        """Update task statuses and statistics."""
        running_tasks = self.thread_service.get_running_tasks()

        # Update task statuses
        for task_id, task_info in list(self.tasks.items()):
            item = task_info["item"]
            data = item.data(Qt.UserRole)

            # If task was running but is no longer in running_tasks
            if (data["status"] == "Running" or data["status"] == "Cancelling") and task_id not in running_tasks:
                item.update_status("Unknown (Stopped)")

            # Update item display (to update elapsed time)
            item.update_display()

        # Update statistics
        running_count = 0
        completed_count = 0
        failed_count = 0

        for i in range(self.task_list.count()):
            item = self.task_list.item(i)
            if isinstance(item, TaskListItem):
                data = item.data(Qt.UserRole)
                if data["status"] == "Running":
                    running_count += 1
                elif data["status"] == "Completed":
                    completed_count += 1
                elif data["status"].startswith("Failed") or data["status"] == "Unknown (Stopped)":
                    failed_count += 1

        self.running_label.setText(f"Running: {running_count}")
        self.completed_label.setText(f"Completed: {completed_count}")
        self.failed_label.setText(f"Failed: {failed_count}")

    def _on_selected_task_changed(self, current, previous):
        """Handle change in selected task."""
        if current and isinstance(current, TaskListItem):
            data = current.data(Qt.UserRole)
            self.progress_bar.setValue(data["progress"])
            self.status_label.setText(f"Task: {current.task_id} - Status: {data['status']}")
        else:
            self.progress_bar.setValue(0)
            self.status_label.setText("No task selected")

    def _on_task_started(self, task_id):
        """Handle task started event."""
        self.logger.info(f"Task {task_id} started")

        if task_id in self.tasks:
            self.tasks[task_id]["item"].update_status("Running", 0)

    def _on_task_progress(self, task_id, percent, message):
        """Handle task progress event."""
        # Update item status
        if task_id in self.tasks:
            self.tasks[task_id]["item"].update_status("Running", percent)

            # Update progress display if this is the selected task
            current_item = self.task_list.currentItem()
            if current_item and isinstance(current_item, TaskListItem) and current_item.task_id == task_id:
                self.progress_bar.setValue(percent)
                self.status_label.setText(message)

    def _on_task_completed(self, task_id, result):
        """Handle task completed event."""
        self.logger.info(f"Task {task_id} completed successfully")

        if task_id in self.tasks:
            self.tasks[task_id]["item"].update_status("Completed", 100)

            # Update progress display if this is the selected task
            current_item = self.task_list.currentItem()
            if current_item and isinstance(current_item, TaskListItem) and current_item.task_id == task_id:
                self.progress_bar.setValue(100)
                self.status_label.setText(f"Completed: {task_id}")

            # Add result to results display
            result_text = f"=== Result from task {task_id} ===\n"

            if isinstance(result, dict):
                try:
                    result_text += json.dumps(result, indent=2)
                except:
                    result_text += str(result)
            else:
                result_text += str(result)

            result_text += "\n\n"
            self.results_text.append(result_text)

            # Scroll to end of results
            self.results_text.verticalScrollBar().setValue(
                self.results_text.verticalScrollBar().maximum()
            )

    def _on_task_error(self, task_id, error):
        """Handle task error event."""
        self.logger.error(f"Task {task_id} failed: {error}")

        if task_id in self.tasks:
            self.tasks[task_id]["item"].update_status(f"Failed: {error}", 0)

            # Update progress display if this is the selected task
            current_item = self.task_list.currentItem()
            if current_item and isinstance(current_item, TaskListItem) and current_item.task_id == task_id:
                self.progress_bar.setValue(0)
                self.status_label.setText(f"Failed: {error}")

            # Add error to results display
            error_text = f"=== Error from task {task_id} ===\n"
            error_text += f"Error: {error}\n\n"

            self.results_text.append(error_text)

            # Scroll to end of results
            self.results_text.verticalScrollBar().setValue(
                self.results_text.verticalScrollBar().maximum()
            )

    def closeEvent(self, event):
        """Handle window close event."""
        # Check if tasks are running
        running_tasks = self.thread_service.get_running_tasks()
        if running_tasks:
            reply = QMessageBox.question(
                self,
                "Confirm Exit",
                f"There are {len(running_tasks)} running tasks. Do you want to cancel them and exit?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.No:
                event.ignore()
                return

            # Cancel all tasks before exit
            self.logger.info(f"Cancelling {len(running_tasks)} tasks before exit")
            self.thread_service.cancel_all_tasks()

        # Stop refresh timer
        self.refresh_timer.stop()

        # Accept close event
        event.accept()


# =============== MAIN ENTRY POINT ===============

if __name__ == "__main__":
    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("Qt Thread Service Tester")

    # Create and show main window
    window = ThreadServiceTester()
    window.show()

    # Start event loop
    sys.exit(app.exec())