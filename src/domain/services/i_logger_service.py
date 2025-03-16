#NewLayout/src/domain/services/i_logger_service.py
"""
Logger service interface for application-wide logging.

Defines the contract for logging services in the application.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class ILoggerService(ABC):
    """
    Interface for logging services.

    Defines methods for different log levels and configuration.
    """

    @abstractmethod
    def debug(self, message: str, **kwargs) -> None:
        """
        Log a debug message.

        Args:
            message: The message to log
            **kwargs: Additional context information to log
        """
        pass

    @abstractmethod
    def info(self, message: str, **kwargs) -> None:
        """
        Log an info message.

        Args:
            message: The message to log
            **kwargs: Additional context information to log
        """
        pass

    @abstractmethod
    def warning(self, message: str, **kwargs) -> None:
        """
        Log a warning message.

        Args:
            message: The message to log
            **kwargs: Additional context information to log
        """
        pass

    @abstractmethod
    def error(self, message: str, **kwargs) -> None:
        """
        Log an error message.

        Args:
            message: The message to log
            **kwargs: Additional context information to log
        """
        pass

    @abstractmethod
    def critical(self, message: str, **kwargs) -> None:
        """
        Log a critical message.

        Args:
            message: The message to log
            **kwargs: Additional context information to log
        """
        pass

    @abstractmethod
    def set_level(self, level: int) -> None:
        """
        Set the minimum log level to display.

        Args:
            level: Minimum log level (e.g., logging.INFO, logging.DEBUG)
        """
        pass