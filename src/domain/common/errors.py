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

class PlatformNotRunningError(PlatformError): # Inherits from PlatformError
    """Error indicating the specified platform's process is not running."""
    def __init__(self, platform_name: str, message: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        self.platform_name = platform_name
        custom_message = message or f"Platform '{platform_name}' process is not running."
        super().__init__(message=custom_message, details=details)
        # Severity can be WARNING if we want the status bar to treat it as such by default
        self.severity = ErrorSeverity.WARNING # Or keep as ERROR from PlatformError if preferred

class UnknownPlatformError(PlatformError): # Inherits from PlatformError
    """Error indicating the platform name is not recognized by the detection service."""
    def __init__(self, platform_name: str, message: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        self.platform_name = platform_name
        custom_message = message or f"Platform name '{platform_name}' is unknown or not supported by the detection service."
        super().__init__(message=custom_message, details=details)
        self.severity = ErrorSeverity.ERROR # This is likely a config error

class PlatformOperationError(PlatformError): # Inherits from PlatformError
    """Generic error for failures during a platform operation (e.g., psutil failure)."""
    def __init__(self, platform_name: Optional[str], operation: str, message: Optional[str] = None, details: Optional[Dict[str, Any]] = None, inner_error: Optional[Exception] = None):
        self.platform_name = platform_name
        self.operation = operation
        custom_message = message or f"An error occurred during operation '{operation}' for platform '{platform_name or 'N/A'}'. See inner error."
        super().__init__(message=custom_message, details=details, inner_error=inner_error)
        self.severity = ErrorSeverity.ERROR