# src/domain/services/i_background_task_service.py

"""
Interface for Background Task Service and Worker definition.
"""
from abc import ABC, abstractmethod
from typing import TypeVar, Generic, Optional, Callable, List, Dict, Any # Added Dict, Any

# Import Result for type hinting
from src.domain.common.result import Result


T = TypeVar('T')

class Worker(Generic[T]):
    """
    Abstract base class for workers that perform tasks in background threads.
    Includes support for cancellation and progress reporting.
    """

    def __init__(self):
        """Initialize the worker."""
        self._cancel_requested = False
        # Initialize callbacks to None
        self.on_started_callback: Optional[Callable[[], None]] = None
        self.on_progress_callback: Optional[Callable[[int, str], None]] = None
        self.on_completed_callback: Optional[Callable[[Any], None]] = None # Use Any for flexibility
        self.on_error_callback: Optional[Callable[[str], None]] = None

    @abstractmethod
    def execute(self) -> T:
        """
        The main task execution logic. This method is called by the background thread.
        Implementations should periodically check `self.cancel_requested`.

        Returns:
            The result of the task execution.
        """
        pass

    @property
    def cancel_requested(self) -> bool:
        """Check if cancellation has been requested."""
        return self._cancel_requested

    def cancel(self) -> None:
        """Request cancellation of the task."""
        self._cancel_requested = True

    # --- Callback Setters ---
    def set_on_started(self, callback: Optional[Callable[[], None]]):
        """Set the callback function for when the task starts."""
        self.on_started_callback = callback

    def set_on_progress(self, callback: Optional[Callable[[int, str], None]]):
        """Set the callback function for progress updates."""
        self.on_progress_callback = callback

    def set_on_completed(self, callback: Optional[Callable[[Any], None]]):
        """Set the callback function for successful completion."""
        self.on_completed_callback = callback

    def set_on_error(self, callback: Optional[Callable[[str], None]]):
        """Set the callback function for errors."""
        self.on_error_callback = callback

    # --- Callback Triggers (for worker implementation use) ---
    def report_started(self):
        """Utility method for worker implementations to report start."""
        if self.on_started_callback:
            try:
                self.on_started_callback()
            except Exception as e:
                # Log this error? Worker needs logger access or service needs to handle
                print(f"ERROR in worker's on_started callback: {e}")

    def report_progress(self, percent: int, message: str):
        """Utility method for worker implementations to report progress."""
        if self.on_progress_callback:
            try:
                self.on_progress_callback(percent, message)
            except Exception as e:
                print(f"ERROR in worker's on_progress callback: {e}")


    def report_completed(self, result: T):  # Type hint T for the result
        """Utility method for worker implementations OR wrappers to report successful completion."""
        if self.on_completed_callback:
            try:
                self.on_completed_callback(result)
            except Exception as e:
                # Log this error? Worker needs logger access or service needs to handle
                print(f"ERROR in worker's on_completed callback: {e}")


    def report_error(self, error_message: str):
        """Utility method for worker implementations to report errors."""
        if self.on_error_callback:
            try:
                self.on_error_callback(error_message)
            except Exception as e:
                print(f"ERROR in worker's on_error callback: {e}")


class IBackgroundTaskService(ABC):
    """
    Interface for executing tasks in background threads.
    """

    @abstractmethod
    def execute_task(self, task_id: str, worker: Worker[T]) -> Result[bool]:
        """
        Execute a worker in a background thread.

        Does not automatically handle worker cleanup or result restoration.
        The caller is responsible for managing the task lifecycle if needed.

        Args:
            task_id: A unique identifier for the task.
            worker: The Worker instance containing the execution logic.

        Returns:
            Result.ok(True) if task started successfully.
            Result.fail(error) if task ID is duplicate or start failed.
        """
        pass

    @abstractmethod
    def execute_task_and_restore_result(self, task_id: str, worker: Worker[T]) -> Result[bool]:
        """
        Execute a task and ensure its results (including Result objects) are handled
        correctly, potentially restoring them from a thread-safe format.
        Manages cleanup of task resources upon completion or error.

        Args:
            task_id: A unique identifier for the task.
            worker: The Worker instance containing the execution logic.

        Returns:
            Result.ok(True) if task started successfully.
            Result.fail(error) if task ID is duplicate or start failed.
        """
        pass

    @abstractmethod
    def execute_ui_task(self, task_id: str, worker: Worker[T],
                        ui_callback: Callable[[Any], None]) -> Result[bool]: # Use Any result type
        """
        Execute a task with a callback that is guaranteed to run on the UI thread.

        Args:
            task_id: A unique identifier for the task.
            worker: The Worker instance containing the execution logic.
            ui_callback: The function to call on the UI thread with the worker's result.

        Returns:
            Result.ok(True) if task started successfully.
            Result.fail(error) if task ID is duplicate or start failed.
        """
        pass

    @abstractmethod
    def cancel_task(self, task_id: str) -> Result[bool]:
        """
        Request cancellation of a specific background task.

        Args:
            task_id: The identifier of the task to cancel.

        Returns:
            Result indicating if the cancellation request was successfully sent.
            Does not guarantee immediate task termination. Returns fail if task not found.
        """
        pass

    @abstractmethod
    def is_task_running(self, task_id: str) -> bool:
        """
        Check if a task with the given ID is currently running.

        Args:
            task_id: The identifier of the task.

        Returns:
            True if the task is considered active, False otherwise.
        """
        pass

    @abstractmethod
    def get_running_tasks(self) -> List[str]:
        """
        Get a list of IDs for all currently running tasks.

        Returns:
            A list of task identifiers.
        """
        pass

    @abstractmethod
    def cancel_all_tasks(self) -> None:
        """
        Request cancellation of all currently running background tasks.
        """
        pass

    @abstractmethod
    def wait_for_task(self, task_id: str, timeout_ms: int = 30000) -> Result[bool]:
        """
        Block the calling thread until the specified task completes or times out.
        USE WITH CAUTION, especially on the main UI thread.

        Args:
            task_id: The identifier of the task to wait for.
            timeout_ms: Maximum time to wait in milliseconds.

        Returns:
            Result.ok(True) if the task completed within the timeout.
            Result.ok(False) if the task was not running initially.
            Result.fail(error) if the timeout occurred or another error happened.
        """
        pass