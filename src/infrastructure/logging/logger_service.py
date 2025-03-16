#NewLayout/src/infrastructure/logging/logger_service.py
"""
Implementation of the logger service using Python's built-in logging module.
"""
import logging
import sys
import os
from datetime import datetime
from typing import Any, Dict

from src.domain.services.i_logger_service import ILoggerService


class ConsoleLoggerService(ILoggerService):
    """
    Implementation of the logger service that logs to console.

    Uses Python's built-in logging module to handle log messages.
    """

    def __init__(self, level: int = logging.INFO, name: str = "MonitorPal"):
        """
        Initialize the logger service.

        Args:
            level: Initial log level (default: INFO)
            name: Logger name
        """
        self.logger = logging.getLogger(name)
        self.set_level(level)

        # Don't add handlers if they already exist
        if not self.logger.handlers:
            # Create console handler
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(level)

            # Create formatter
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            console_handler.setFormatter(formatter)

            # Add handler to logger
            self.logger.addHandler(console_handler)

    def debug(self, message: str, **kwargs) -> None:
        """
        Log a debug message.

        Args:
            message: The message to log
            **kwargs: Additional context information to log
        """
        extra = self._format_extra(kwargs)
        if extra:
            message = f"{message} {extra}"
        self.logger.debug(message)

    def info(self, message: str, **kwargs) -> None:
        """
        Log an info message.

        Args:
            message: The message to log
            **kwargs: Additional context information to log
        """
        extra = self._format_extra(kwargs)
        if extra:
            message = f"{message} {extra}"
        self.logger.info(message)

    def warning(self, message: str, **kwargs) -> None:
        """
        Log a warning message.

        Args:
            message: The message to log
            **kwargs: Additional context information to log
        """
        extra = self._format_extra(kwargs)
        if extra:
            message = f"{message} {extra}"
        self.logger.warning(message)

    def error(self, message: str, **kwargs) -> None:
        """
        Log an error message.

        Args:
            message: The message to log
            **kwargs: Additional context information to log
        """
        extra = self._format_extra(kwargs)
        if extra:
            message = f"{message} {extra}"
        self.logger.error(message)

    def critical(self, message: str, **kwargs) -> None:
        """
        Log a critical message.

        Args:
            message: The message to log
            **kwargs: Additional context information to log
        """
        extra = self._format_extra(kwargs)
        if extra:
            message = f"{message} {extra}"
        self.logger.critical(message)

    def set_level(self, level: int) -> None:
        """
        Set the minimum log level to display.

        Args:
            level: Minimum log level (e.g., logging.INFO, logging.DEBUG)
        """
        self.logger.setLevel(level)

    def _format_extra(self, extra: Dict[str, Any]) -> str:
        """
        Format extra context information for logging.

        Args:
            extra: Dictionary of extra context information

        Returns:
            Formatted string of context information
        """
        if not extra:
            return ""

        # Format each key-value pair
        formatted = []
        for key, value in extra.items():
            formatted.append(f"{key}={value}")

        return f"[{' '.join(formatted)}]"


class FileLoggerService(ConsoleLoggerService):
    """
    Extension of ConsoleLoggerService that also logs to a file.
    """

    def __init__(self, level: int = logging.INFO, name: str = "MonitorPal",
                 log_dir: str = "logs"):
        """
        Initialize the file logger service.

        Args:
            level: Initial log level (default: INFO)
            name: Logger name
            log_dir: Directory to store log files
        """
        super().__init__(level, name)

        # Create logs directory if it doesn't exist
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # Create unique filename based on current date
        current_date = datetime.now().strftime("%Y-%m-%d")
        log_file = os.path.join(log_dir, f"{name}_{current_date}.log")

        # Create file handler
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)

        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)

        # Add handler to logger
        self.logger.addHandler(file_handler)