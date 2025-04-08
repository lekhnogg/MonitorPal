# src/infrastructure/threading/qt_background_task_service.py
"""
Qt implementation of the thread service.

This module provides a thread service implementation using Qt's QThread for
safely executing background tasks without blocking the UI.
"""
import traceback
from typing import Dict, Any, Optional, Callable, List, TypeVar

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, QThread, Signal, Slot, Qt, QMutex, QMutexLocker, QTimer, QEventLoop

from src.domain.services.i_background_task_service import IBackgroundTaskService, Worker
from src.domain.services.i_logger_service import ILoggerService
from src.domain.common.result import Result

T = TypeVar('T')


class WorkerSignals(QObject):
    """
    Defines the signals available from a running worker thread.

    Signals:
        started: Signal emitted when the worker starts execution
        progress: Signal emitted to report progress (percent, message)
        completed: Signal emitted with the result when the worker completes successfully
        error: Signal emitted with error information when the worker encounters an error
    """
    started = Signal()
    progress = Signal(int, str)
    completed = Signal(object)
    error = Signal(str)


class WorkerWrapper(QObject):
    """
    Qt wrapper for Worker objects to run in a QThread.

    This class bridges between the domain Worker interface and Qt's threading model,
    ensuring thread-safe communication via signals and slots.
    """

    def __init__(self, worker: Worker[T], logger: ILoggerService, task_id: str):
        """
        Initialize the worker wrapper.

        Args:
            worker: The domain worker to execute
            logger: Logger service for error reporting
            task_id: Identifier for this task
        """
        super().__init__()
        self.worker = worker
        self.logger = logger
        self.task_id = task_id
        self.signals = WorkerSignals()

        # Store original callbacks
        self.original_started_callback = worker.on_started_callback
        self.original_progress_callback = worker.on_progress_callback
        self.original_completed_callback = worker.on_completed_callback
        self.original_error_callback = worker.on_error_callback

        # Connect worker callbacks to our signals
        self.worker.set_on_started(self.signals.started.emit)
        self.worker.set_on_progress(self.signals.progress.emit)
        self.worker.set_on_error(self.signals.error.emit)

        # We don't set completed callback directly to avoid circular references
        # Instead, we'll emit our completed signal in _process_and_emit_result

    @Slot()
    def run(self):
        """
        Execute the worker's task in the background thread.
        This method is called automatically when the thread starts.
        """
        try:
            self.logger.debug(f"Worker for task '{self.task_id}' starting execution")
            self.worker.report_started()
            result = self.worker.execute()
            self._process_and_emit_result(result)
        except Exception as e:
            # Handle any unhandled exceptions in the worker
            error_message = f"Unhandled error in worker: {e}"
            self.logger.error(error_message)
            self.logger.debug(traceback.format_exc())
            self.worker.report_error(error_message)

    def _process_and_emit_result(self, result):
        """
        Process the result and emit the completed signal with a thread-safe representation.

        Args:
            result: The result from the worker's execute method
        """
        try:
            # Handle Result objects using their built-in thread safety methods
            if isinstance(result, Result):
                self.logger.debug(f"Converting Result object to thread-safe dictionary")
                thread_safe_dict = result.to_thread_safe_dict()
                self.signals.completed.emit(thread_safe_dict)
                return

            # Check if result is a complex object that might not safely cross thread boundaries
            if result is None:
                # None is always safe to pass
                self.signals.completed.emit(None)
            elif isinstance(result, (str, int, float, bool, list, tuple, dict, set)):
                # Basic types and standard containers should be safe to pass directly
                self.signals.completed.emit(result)
            elif hasattr(result, 'to_dict') and callable(result.to_dict):
                # Use to_dict method if available (preferred)
                self.logger.debug(f"Converting complex result object to dictionary using to_dict method")
                safe_result = result.to_dict()
                self.signals.completed.emit(safe_result)
            elif hasattr(result, '__dict__'):
                # Create a dictionary from public attributes
                self.logger.debug(f"Converting complex result object to dictionary from attributes")
                safe_result = {k: v for k, v in result.__dict__.items()
                               if not k.startswith('_') and not callable(v)}
                self.signals.completed.emit(safe_result)
            else:
                # Unknown type - try to pass it directly but log a warning
                self.logger.warning(f"Emitting result of unknown type {type(result).__name__} - may not be thread-safe")
                self.signals.completed.emit(result)
        except Exception as e:
            error_message = f"Error handling thread result: {e}"
            self.logger.error(error_message)
            self.logger.debug(traceback.format_exc())
            self.worker.report_error(error_message)


class TaskInfo:
    """
    Stores information about a running task.

    Maintains references to threads, wrappers, and workers for a specific task,
    along with metadata and state information.
    """

    def __init__(self, task_id: str, thread: QThread, wrapper: WorkerWrapper, worker: Worker):
        """
        Initialize task information.

        Args:
            task_id: Unique identifier for the task
            thread: QThread instance running the task
            wrapper: WorkerWrapper bridging the worker to the thread
            worker: The worker being executed
        """
        self.task_id = task_id
        self.thread = thread
        self.wrapper = wrapper
        self.worker = worker


class QtBackgroundTaskService(IBackgroundTaskService):
    """
    Qt implementation of thread service for managing background tasks.

    Uses Qt's QThread and signal/slot mechanism to safely execute
    tasks in background threads without blocking the UI.
    """

    def __init__(self, logger: ILoggerService):
        """
        Initialize the Qt thread service.

        Args:
            logger: Logger service for error reporting
        """
        self.logger = logger
        self.tasks: Dict[str, TaskInfo] = {}
        self.mutex = QMutex()  # Simple mutex for thread safety

    def execute_task(self, task_id: str, worker: Worker[T]) -> Result[bool]:
        """
        Execute a worker in a background thread.

        Args:
            task_id: Unique identifier for the task
            worker: Worker to execute

        Returns:
            Result indicating success or failure of task initialization
        """
        locker = QMutexLocker(self.mutex)

        try:
            if task_id in self.tasks:
                locker.unlock()  # Unlock before returning
                self.logger.warning(f"Task '{task_id}' is already running")
                return Result.fail(f"Task '{task_id}' is already running")

            self.logger.debug(f"Starting task '{task_id}'")

            # Create QThread
            thread = QThread()

            # Create worker wrapper
            wrapper = WorkerWrapper(worker, self.logger, task_id)
            wrapper.moveToThread(thread)

            # Connect thread lifecycle signals
            thread.started.connect(wrapper.run)

            # Use deleteLater for wrapper and thread cleanup when thread finishes
            # THIS IS CRUCIAL for safe object deletion and signal disconnection
            thread.finished.connect(wrapper.deleteLater)
            thread.finished.connect(thread.deleteLater)

            # Connect a slot to remove the task from our tracking dictionary *after* finished
            thread.finished.connect(lambda: self._handle_task_finished(task_id))  # MODIFIED/ADDED

            # Connect worker signals (keep existing connections)
            if worker.on_started_callback:
                wrapper.signals.started.connect(worker.on_started_callback, Qt.QueuedConnection)
            if worker.on_progress_callback:
                wrapper.signals.progress.connect(worker.on_progress_callback, Qt.QueuedConnection)
            if worker.on_completed_callback:
                wrapper.signals.completed.connect(worker.on_completed_callback, Qt.QueuedConnection)
            if worker.on_error_callback:
                wrapper.signals.error.connect(worker.on_error_callback, Qt.QueuedConnection)

            # Store task info
            self.tasks[task_id] = TaskInfo(task_id, thread, wrapper, worker)
            locker.unlock()  # Unlock after modifying tasks dict

            # Start thread
            thread.start()

            self.logger.debug(f"Task '{task_id}' started successfully")
            return Result.ok(True)
        except Exception as e:
            # Ensure locker is unlocked in case of exception before return
            if locker.isLocked():
                locker.unlock()
            error_message = f"Error starting task '{task_id}': {e}"
            self.logger.error(error_message)
            self.logger.debug(traceback.format_exc())
            return Result.fail(error_message)

    # --- Add this new private method ---
    @Slot(str)  # Make it a slot if needed, otherwise just a private method
    def _handle_task_finished(self, task_id: str):
        """Slot called when a task's thread emits finished()."""
        locker = QMutexLocker(self.mutex)
        try:
            if task_id in self.tasks:
                self.logger.debug(f"Cleaning up finished task '{task_id}' from tracking dictionary.")
                del self.tasks[task_id]
            else:
                self.logger.debug(f"Task '{task_id}' already cleaned up or not found upon finishing.")
        except Exception as e:
            self.logger.error(f"Error during task finish handling for '{task_id}': {e}")
        finally:
            # Locker unlocks automatically
            pass  # QMutexLocker handles unlock

    def execute_task_with_auto_cleanup(self, task_id: str, worker: Worker[T]) -> Result[bool]:
        """
        Execute a task that will be automatically cleaned up when completed.
        (Cleanup now primarily means calling the original callback,
         dictionary removal is handled by _handle_task_finished)
        """
        original_completed_callback = worker.on_completed_callback
        original_error_callback = worker.on_error_callback

        # We still need to wrap the callbacks to ensure the *original* user callback runs
        # before the task is considered fully "done".

        def on_task_completed_wrapper(result):
            """Call original callback."""
            if original_completed_callback:
                try:
                    # If result is a serialized Result, convert it back
                    if isinstance(result, dict) and "success" in result and ("value" in result or "error" in result):
                        restored_result = Result.from_thread_safe_dict(result)
                        original_completed_callback(restored_result)
                    else:
                        original_completed_callback(result)
                except Exception as e:
                    self.logger.error(f"Error in user's on_completed callback for task '{task_id}': {e}")
            # No need to call _cleanup_task here anymore

        def on_task_error_wrapper(error):
            """Call original callback."""
            if original_error_callback:
                try:
                     original_error_callback(error)
                except Exception as e:
                     self.logger.error(f"Error in user's on_error callback for task '{task_id}': {e}")
            # No need to call _cleanup_task here anymore

        # Set wrapped callbacks
        worker.set_on_completed(on_task_completed_wrapper)
        worker.set_on_error(on_task_error_wrapper)

        # Execute the task (which connects _handle_task_finished)
        return self.execute_task(task_id, worker)

    def execute_ui_task(self, task_id: str, worker: Worker[T],
                        ui_callback: Callable[[T], None]) -> Result[bool]:
        """
        Execute a task with a UI callback for the result.

        Args:
            task_id: Unique identifier for the task
            worker: Worker to execute
            ui_callback: Callback to execute on the UI thread with the result

        Returns:
            Result indicating success or failure of task initialization
        """
        try:
            # Create a wrapped callback that handles Result objects
            def wrapped_callback(result):
                # If result is a dictionary that might be a thread-safe Result
                if isinstance(result, dict) and "success" in result and ("value" in result or "error" in result):
                    # Convert back to Result object
                    result_obj = Result.from_thread_safe_dict(result)
                    ui_callback(result_obj)
                else:
                    # Pass through directly
                    ui_callback(result)

            # Set the wrapped callback
            worker.set_on_completed(wrapped_callback)

            # Execute the task with auto cleanup
            return self.execute_task_with_auto_cleanup(task_id, worker)
        except Exception as e:
            error_message = f"Error executing UI task '{task_id}': {e}"
            self.logger.error(error_message)
            self.logger.debug(traceback.format_exc())
            return Result.fail(error_message)

    def cancel_task(self, task_id: str) -> Result[bool]:
        """
        Request cancellation of a running task.
        """
        task_info = None # Variable to hold task_info outside the lock

        # --- Step 1: Find the task info under lock ---
        locker = QMutexLocker(self.mutex)
        if task_id not in self.tasks:
            self.logger.warning(f"Cannot cancel task '{task_id}' - not found or already finished.")
            return Result.fail(f"Task '{task_id}' not found")
        task_info = self.tasks[task_id]
        locker.unlock() # Release lock before interacting with thread

        # --- Step 2: Request cancellation without lock ---
        try:
            self.logger.debug(f"Requesting cancellation for task '{task_id}'")
            task_info.worker.cancel() # Signal the worker logic to stop

            # Ask the thread's event loop to quit. This helps if the worker
            # is waiting on something event-loop related. Might not be strictly
            # necessary if the worker loop checks cancel_requested frequently.
            # Use invokeMethod for thread-safety if calling from different thread,
            # but here cancel_task is likely called from main thread where QThread was created.
            # Direct call should be fine, but MetaObject call is safer across threads.
            # QMetaObject.invokeMethod(task_info.thread, "quit", Qt.QueuedConnection)
            task_info.thread.quit() # Try direct quit first

            # --- Step 3: Wait GRACEFULLY (Optional but recommended) ---
            # Decide if you want cancel_task to block until the thread confirms exit.
            # If you don't wait here, the task might still be in the dictionary for a short while.
            wait_success = task_info.thread.wait(2000) # Wait up to 2 seconds

            if wait_success:
                 self.logger.debug(f"Task '{task_id}' thread finished gracefully after cancellation request.")
                 # No need to remove from dict here, _handle_task_finished will do it.
                 return Result.ok(True)
            else:
                 self.logger.warning(f"Task '{task_id}' thread did not finish within timeout after cancellation request. It might finish later.")
                 # DO NOT TERMINATE.
                 # The task will be removed from the dictionary later when the 'finished' signal is emitted.
                 # We report success because the cancellation *request* was sent.
                 return Result.ok(True) # Or Result.fail("Cancellation timed out") if you prefer

        except Exception as e:
            error_message = f"Error requesting cancellation for task '{task_id}': {e}"
            self.logger.error(error_message)
            self.logger.debug(traceback.format_exc())
            # Attempt to remove the task from the dictionary in case of error during cancellation itself
            locker_cleanup = QMutexLocker(self.mutex)
            if task_id in self.tasks:
                 del self.tasks[task_id]
            return Result.fail(error_message)

    def is_task_running(self, task_id: str) -> bool:
        """
        Check if a task is currently running.

        Args:
            task_id: Identifier of the task to check

        Returns:
            True if task is running, False otherwise
        """
        locker = QMutexLocker(self.mutex)
        try:
            return task_id in self.tasks
        finally:
            # QMutexLocker will automatically unlock when it goes out of scope
            pass

    def get_running_tasks(self) -> List[str]:
        """
        Get a list of all running task IDs.

        Returns:
            List of task identifiers that are currently running
        """
        locker = QMutexLocker(self.mutex)
        try:
            return list(self.tasks.keys())
        finally:
            # QMutexLocker will automatically unlock when it goes out of scope
            pass

    def cancel_all_tasks(self) -> None:
        """Cancel all running background tasks."""
        task_ids = []

        # Get all task IDs with the lock
        locker = QMutexLocker(self.mutex)
        try:
            task_ids = list(self.tasks.keys())
        finally:
            locker.unlock()  # Unlock before calling cancel_task to avoid deadlock

        # Cancel each task (cancel_task will acquire its own lock)
        for task_id in task_ids:
            self.cancel_task(task_id)

    def wait_for_task(self, task_id: str, timeout_ms: int = 30000) -> Result[bool]:
        """
        Wait for a specific task to complete.

        This method blocks the current thread until the task completes,
        is cancelled, or the timeout is reached.

        Args:
            task_id: Identifier of the task to wait for
            timeout_ms: Maximum time to wait in milliseconds (default: 30 seconds)

        Returns:
            Result indicating whether the task completed successfully
        """
        if not self.is_task_running(task_id):
            return Result.ok(False)  # Task is not running

        try:
            # Create an event loop for waiting
            wait_loop = QEventLoop()

            # Setup timer to check if task is still running
            check_timer = QTimer()
            check_timer.setInterval(100)  # Check every 100ms

            # Setup timeout timer
            timeout_timer = QTimer()
            timeout_timer.setSingleShot(True)
            timeout_timer.setInterval(timeout_ms)

            # Flag to track result
            completion_status = {"completed": False, "timed_out": False}

            def check_task_status():
                if not self.is_task_running(task_id):
                    check_timer.stop()
                    wait_loop.quit()
                    completion_status["completed"] = True

            def on_timeout():
                completion_status["timed_out"] = True
                check_timer.stop()
                wait_loop.quit()

            # Connect signals
            check_timer.timeout.connect(check_task_status)
            timeout_timer.timeout.connect(on_timeout)

            # Start timers
            check_timer.start()
            timeout_timer.start()

            # Wait for completion or timeout
            wait_loop.exec()

            if completion_status["timed_out"]:
                return Result.fail(f"Timeout waiting for task '{task_id}' to complete")

            return Result.ok(completion_status["completed"])

        except Exception as e:
            error_message = f"Error waiting for task '{task_id}': {e}"
            self.logger.error(error_message)
            self.logger.debug(traceback.format_exc())
            return Result.fail(error_message)
