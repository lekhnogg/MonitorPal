#src/domain/services/i_background_task_service.py
"""
Thread service interface for application-wide threading.

Defines the contract for thread management services in the application.
Includes messaging system for safe cross-thread communication.
"""
from abc import ABC, abstractmethod
from typing import Any, Optional, Callable, List, TypeVar, Generic, Protocol
import threading

from src.domain.common.result import Result

T = TypeVar('T')
U = TypeVar('U')


class CancellationToken:
    """
    Token for coordinating cancellation across threads.
    Provides thread-safe cancellation state checking and waiting.
    """

    def __init__(self):
        """Initialize a new cancellation token."""
        self._cancelled = False
        self._event = threading.Event()
        self._lock = threading.RLock()

    def cancel(self) -> None:
        """Mark the token as cancelled and signal any waiting threads."""
        with self._lock:
            self._cancelled = True
            self._event.set()

    @property
    def is_cancelled(self) -> bool:
        """Check if cancellation has been requested."""
        with self._lock:
            return self._cancelled

    def wait(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for cancellation or timeout.

        Args:
            timeout: Maximum time to wait in seconds, or None to wait indefinitely

        Returns:
            True if the token was cancelled, False if timeout occurred
        """
        return self._event.wait(timeout)

    def throw_if_cancelled(self) -> None:
        """
        Throw a TaskCancelledException if cancellation has been requested.

        Raises:
            TaskCancelledException: If cancellation has been requested
        """
        if self.is_cancelled:
            raise TaskCancelledException("Task was cancelled")


class TaskCancelledException(Exception):
    """Exception raised when a task is cancelled."""
    pass


class WorkerObserver(Protocol):
    """Protocol defining the interface for worker observation."""

    def on_started(self) -> None: ...

    def on_progress(self, percent: int, message: str) -> None: ...

    def on_completed(self, result: Any) -> None: ...

    def on_error(self, error: str) -> None: ...


class Worker(Generic[T]):
    """
    Base class for background workers that can be executed by the thread service.

    Worker tasks are executed in a background thread and can report progress,
    completion with a result, or errors.
    """

    def __init__(self):
        """Initialize the worker."""
        # Cancellation support
        self._cancellation_token = CancellationToken()

        # Callbacks for progress reporting
        self.on_started_callback: Optional[Callable[[], None]] = None
        self.on_progress_callback: Optional[Callable[[int, str], None]] = None
        self.on_completed_callback: Optional[Callable[[T], None]] = None
        self.on_error_callback: Optional[Callable[[str], None]] = None

        # Observer list
        self._observers: List[WorkerObserver] = []

    @property
    def cancel_requested(self) -> bool:
        """Check if cancellation has been requested."""
        return self._cancellation_token.is_cancelled

    def set_on_started(self, callback: Callable[[], None]) -> None:
        """Set callback for when worker starts."""
        self.on_started_callback = callback

    def set_on_progress(self, callback: Callable[[int, str], None]) -> None:
        """Set callback for progress updates."""
        self.on_progress_callback = callback

    def set_on_completed(self, callback: Callable[[T], None]) -> None:
        """Set callback for when worker completes successfully."""
        self.on_completed_callback = callback

    def set_on_error(self, callback: Callable[[str], None]) -> None:
        """Set callback for when worker encounters an error."""
        self.on_error_callback = callback

    def add_observer(self, observer: WorkerObserver) -> None:
        """Add an observer to receive all worker events."""
        if observer not in self._observers:
            self._observers.append(observer)

    def remove_observer(self, observer: WorkerObserver) -> None:
        """Remove an observer from the worker."""
        if observer in self._observers:
            self._observers.remove(observer)

    def report_started(self) -> None:
        """Report that the worker has started."""
        if self.on_started_callback:
            self.on_started_callback()

        for observer in self._observers:
            observer.on_started()

    def report_progress(self, percent: int, message: str = "") -> None:
        """Report progress update."""
        if self.on_progress_callback:
            self.on_progress_callback(percent, message)

        for observer in self._observers:
            observer.on_progress(percent, message)

    def report_completed(self, result: T) -> None:
        """Report that the worker has completed successfully."""
        if self.on_completed_callback:
            self.on_completed_callback(result)

        for observer in self._observers:
            observer.on_completed(result)

    def report_error(self, error: str) -> None:
        """Report that the worker has encountered an error."""
        if self.on_error_callback:
            self.on_error_callback(error)

        for observer in self._observers:
            observer.on_error(error)

    def initialize(self) -> None:
        """
        Initialize the worker before execution.

        Override this method to perform setup operations before execute().
        """
        pass

    def cleanup(self) -> None:
        """
        Clean up worker resources.

        Override this method to perform cleanup operations after execute().
        Called regardless of whether execute() completes successfully or not.
        """
        pass

    def check_cancellation(self) -> None:
        """
        Check if cancellation has been requested and raise exception if so.

        Raises:
            TaskCancelledException: If cancellation has been requested
        """
        self._cancellation_token.throw_if_cancelled()

    @abstractmethod
    def execute(self) -> T:
        """
        Execute the worker's task.

        This method is called in a background thread and should return a result.

        Returns:
            The result of the worker's execution

        Raises:
            TaskCancelledException: If the task is cancelled
            Exception: For any other execution errors
        """
        pass

    def cancel(self) -> None:
        """Request cancellation of the worker's task."""
        self._cancellation_token.cancel()


class IBackgroundTaskService(ABC):
    """
    Interface for thread management services.

    Defines methods for executing tasks in background threads
    and managing thread lifecycle.
    """

    @abstractmethod
    def execute_task(self, task_id: str, worker: Worker[T]) -> Result[bool]:
        """
        Execute a worker in a background thread.

        Args:
            task_id: Unique identifier for the task
            worker: Worker to execute

        Returns:
            Result indicating success or failure
        """
        pass

    @abstractmethod
    def execute_task_with_auto_cleanup(self, task_id: str, worker: Worker[T]) -> Result[bool]:
        """
        Execute a task that will be automatically cleaned up when completed.

        Args:
            task_id: Unique identifier for the task
            worker: Worker to execute

        Returns:
            Result indicating success or failure
        """
        pass

    @abstractmethod
    def execute_ui_task(self, task_id: str, worker: Worker[T],
                        ui_callback: Callable[[T], None]) -> Result[bool]:
        """
        Execute a task with a UI callback for the result.

        Args:
            task_id: Unique identifier for the task
            worker: Worker to execute
            ui_callback: Callback to be executed on the UI thread with the result

        Returns:
            Result indicating success or failure
        """
        pass

    @abstractmethod
    def cancel_task(self, task_id: str) -> Result[bool]:
        """
        Cancel a background task.

        Args:
            task_id: Identifier of the task to cancel

        Returns:
            Result indicating success or failure
        """
        pass

    @abstractmethod
    def is_task_running(self, task_id: str) -> bool:
        """
        Check if a task is currently running.

        Args:
            task_id: Identifier of the task to check

        Returns:
            True if the task is running, False otherwise
        """
        pass

    @abstractmethod
    def get_running_tasks(self) -> List[str]:
        """
        Get a list of all running task IDs.

        Returns:
            List of task identifiers for running tasks
        """
        pass

    @abstractmethod
    def cancel_all_tasks(self) -> None:
        """Cancel all running background tasks."""
        pass