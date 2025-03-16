# src/domain/common/result.py

"""
Result pattern implementation for error handling.

The Result pattern allows methods to return either a success value or a failure with an error message,
avoiding the need for exceptions for expected error conditions.
"""
from typing import TypeVar, Generic, Optional, Union, Any, Callable, Dict

# Import the new domain error types
from src.domain.common.errors import DomainError

T = TypeVar('T')
U = TypeVar('U')


class Result(Generic[T]):
    """
    Result type for representing success or failure of an operation.

    Attributes:
        value: The result value (if successful)
        error: Error object (if failed)
        is_success: Whether the operation was successful
        is_failure: Whether the operation failed
    """

    def __init__(self, value: Optional[T], error: Optional[Union[str, DomainError]]):
        """
        Initialize a Result object.

        Args:
            value: The result value (or None if failed)
            error: Error object or message (or None if successful)
        """
        self._value = value

        # Convert string errors to DomainError
        if isinstance(error, str):
            from src.domain.common.errors import DomainError, ErrorCategory
            self._error = DomainError(message=error, category=ErrorCategory.UNKNOWN)
        else:
            self._error = error

    @classmethod
    def ok(cls, value: T) -> 'Result[T]':
        """
        Create a successful result with a value.

        Args:
            value: The result value

        Returns:
            A successful Result containing the value
        """
        return cls(value, None)

    @classmethod
    def fail(cls, error: Union[str, DomainError]) -> 'Result[T]':
        """
        Create a failed result with an error.

        Args:
            error: The error message or DomainError object

        Returns:
            A failed Result with the error
        """
        return cls(None, error)

    @property
    def is_success(self) -> bool:
        """Whether the result represents a successful operation."""
        return self._error is None

    @property
    def is_failure(self) -> bool:
        """Whether the result represents a failed operation."""
        return not self.is_success

    @property
    def value(self) -> T:
        """
        Get the success value.

        Returns:
            The result value

        Raises:
            ValueError: If the result is a failure
        """
        if self.is_failure:
            error_msg = str(self._error) if self._error else "Unknown error"
            raise ValueError(f"Cannot access value of a failed result: {error_msg}")
        return self._value

    @property
    def error(self) -> DomainError:
        """
        Get the error.

        Returns:
            The error object

        Raises:
            ValueError: If the result is a success
        """
        if self.is_success:
            raise ValueError("Cannot access error of a successful result")
        return self._error

    def map(self, func: Callable[[T], U]) -> 'Result[U]':
        """
        Transform the result value if successful.

        Args:
            func: The mapping function

        Returns:
            A new Result with the transformed value or the same error
        """
        if self.is_success:
            try:
                return Result.ok(func(self._value))
            except Exception as e:
                from src.domain.common.errors import DomainError
                return Result.fail(DomainError.from_exception(e))
        else:
            return Result.fail(self._error)

    def match(self, success_func: Callable[[T], U], failure_func: Callable[[DomainError], U]) -> U:
        """
        Pattern match on the result to handle both success and failure cases.

        Args:
            success_func: Function to call with the value if successful
            failure_func: Function to call with the error if failed

        Returns:
            The result of calling either success_func or failure_func
        """
        if self.is_success:
            return success_func(self._value)
        else:
            return failure_func(self._error)

    def on_success(self, action: Callable[[T], None]) -> 'Result[T]':
        """
        Execute an action if the result is successful.

        Args:
            action: Action to execute with the value

        Returns:
            The same Result for chaining
        """
        if self.is_success:
            action(self._value)
        return self

    def on_failure(self, action: Callable[[DomainError], None]) -> 'Result[T]':
        """
        Execute an action if the result is a failure.

        Args:
            action: Action to execute with the error

        Returns:
            The same Result for chaining
        """
        if self.is_failure:
            action(self._error)
        return self

    def and_then(self, func: Callable[[T], 'Result[U]']) -> 'Result[U]':
        """
        Chain another operation that returns a Result.

        Args:
            func: Function that takes the value and returns a new Result

        Returns:
            The new Result or the original error
        """
        if self.is_success:
            return func(self._value)
        else:
            return Result.fail(self._error)

    @classmethod
    def from_operation(cls, operation_func, logger, error_type, error_message, **kwargs):
        """
        Create a Result from an operation that might fail.

        This utility method standardizes the try/except pattern used throughout services.

        Args:
            operation_func: The function to execute
            logger: Logger to use for errors
            error_type: The domain error type to create on failure
            error_message: Error message prefix
            **kwargs: Context information for error details

        Returns:
            A Result object containing the operation result or error
        """
        try:
            result = operation_func()
            # If the operation already returns a Result, use it directly
            if isinstance(result, Result):
                return result
            # Otherwise wrap the result in a successful Result
            return cls.ok(result)
        except Exception as e:
            # Create appropriate error object
            error = error_type(
                message=f"{error_message}: {e}",
                details=kwargs,
                inner_error=e
            )
            # Log the error
            logger.error(str(error))
            # Return failure result
            return cls.fail(error)

    def to_thread_safe_dict(self) -> Dict[str, Any]:
        """
        Convert result to a thread-safe dictionary representation.

        This method ensures the result can be safely passed across thread
        boundaries without causing issues with Qt's signal/slot mechanism.

        Returns:
            A thread-safe dictionary representation of the result
        """
        if self.is_success:
            return {
                "success": True,
                "value": self._serialize_value(self._value)
            }
        else:
            return {
                "success": False,
                "error": str(self._error)
            }

    def _serialize_value(self, value: Any) -> Any:
        """
        Convert a result value to a serializable format.

        Args:
            value: The value to serialize

        Returns:
            A serializable representation of the value
        """
        # Handle None, primitives, and strings
        if value is None or isinstance(value, (bool, int, float, str)):
            return value

        # Handle lists and tuples
        if isinstance(value, (list, tuple)):
            return [self._serialize_value(item) for item in value]

        # Handle dictionaries
        if isinstance(value, dict):
            return {
                str(k): self._serialize_value(v)
                for k, v in value.items()
            }

        # Handle objects with to_dict method
        if hasattr(value, 'to_dict') and callable(value.to_dict):
            return value.to_dict()

        # Handle objects with __dict__ attribute
        if hasattr(value, '__dict__'):
            return {
                k: self._serialize_value(v)
                for k, v in value.__dict__.items()
                if not k.startswith('_') and not callable(v)
            }

        # Return string representation as fallback
        return str(value)

    @classmethod
    def from_thread_safe_dict(cls, data: Dict[str, Any]) -> 'Result[Any]':
        """
        Create a Result object from a thread-safe dictionary.

        Args:
            data: Dictionary created by to_thread_safe_dict

        Returns:
            A Result object
        """
        if data.get("success", False):
            return cls.ok(data.get("value"))
        else:
            return cls.fail(data.get("error", "Unknown error"))