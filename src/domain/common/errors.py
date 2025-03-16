#src/domain/common/errors.py

"""
Domain-specific error types for standardized error handling.

This module defines error types and categories used throughout the application
to provide consistent error handling and reporting.
"""
from enum import Enum
from typing import Optional, Dict, Any


class ErrorCategory(Enum):
    """Categories of errors in the application."""
    VALIDATION = "Validation"
    CONFIGURATION = "Configuration"
    PLATFORM = "Platform"
    NETWORK = "Network"
    PERMISSION = "Permission"
    RESOURCE = "Resource"
    UI = "UI"
    UNKNOWN = "Unknown"


class ErrorSeverity(Enum):
    """Severity levels for errors."""
    INFO = "Info"
    WARNING = "Warning"
    ERROR = "Error"
    CRITICAL = "Critical"


class DomainError:
    """
    Base class for domain-specific errors.

    This provides structured error information that can be used
    for consistent error handling, logging, and user feedback.
    """

    def __init__(self,
                 message: str,
                 category: ErrorCategory = ErrorCategory.UNKNOWN,
                 severity: ErrorSeverity = ErrorSeverity.ERROR,
                 code: Optional[str] = None,
                 details: Optional[Dict[str, Any]] = None,
                 inner_error: Optional[Exception] = None):
        """
        Initialize a domain error.

        Args:
            message: Human-readable error message
            category: Error category
            severity: Error severity
            code: Optional error code for programmatic handling
            details: Optional additional error details
            inner_error: Optional original exception
        """
        self.message = message
        self.category = category
        self.severity = severity
        self.code = code
        self.details = details or {}
        self.inner_error = inner_error

    @staticmethod
    def from_exception(ex: Exception,
                       category: ErrorCategory = ErrorCategory.UNKNOWN,
                       severity: ErrorSeverity = ErrorSeverity.ERROR) -> 'DomainError':
        """
        Create a domain error from an exception.

        Args:
            ex: The exception
            category: Error category
            severity: Error severity

        Returns:
            A DomainError instance
        """
        return DomainError(
            message=str(ex),
            category=category,
            severity=severity,
            inner_error=ex
        )

    def __str__(self) -> str:
        """String representation of the error."""
        return f"{self.category.value} Error: {self.message}"


class ValidationError(DomainError):
    """Error for validation failures."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None, inner_error: Optional[Exception] = None):
        super().__init__(
            message=message,
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.WARNING,
            details=details,
            inner_error=inner_error
        )


class ConfigurationError(DomainError):
    """Error for configuration issues."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None, inner_error: Optional[Exception] = None):
        super().__init__(
            message=message,
            category=ErrorCategory.CONFIGURATION,
            severity=ErrorSeverity.ERROR,
            details=details,
            inner_error=inner_error
        )


class PlatformError(DomainError):
    """Error for platform detection or interaction issues."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None, inner_error: Optional[Exception] = None):
        super().__init__(
            message=message,
            category=ErrorCategory.PLATFORM,
            severity=ErrorSeverity.ERROR,
            details=details,
            inner_error=inner_error
        )


class ResourceError(DomainError):
    """Error for resource access or availability issues."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None, inner_error: Optional[Exception] = None):
        super().__init__(
            message=message,
            category=ErrorCategory.RESOURCE,
            severity=ErrorSeverity.ERROR,
            details=details,
            inner_error=inner_error
        )


class UIError(DomainError):
    """Error for UI-related issues."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None, inner_error: Optional[Exception] = None):
        super().__init__(
            message=message,
            category=ErrorCategory.UI,
            severity=ErrorSeverity.WARNING,
            details=details,
            inner_error=inner_error
        )