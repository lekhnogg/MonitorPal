# src/utils/logging_config.py
"""
Centralized logging configuration for the entire application.
This should be imported and called only once at application startup.
"""

import logging
import os
import sys
from datetime import datetime
from typing import Optional

from PySide6.QtCore import QObject, Signal

# Global flag to track if logging has been configured
_logging_configured = False


def setup_logging(log_level: int = logging.INFO,
                  log_dir: Optional[str] = None) -> logging.Logger:
    """
    Configure logging for the entire application.

    Args:
        log_level: Logging level (default: logging.INFO)
        log_dir: Directory for log files (optional)

    Returns:
        Configured root logger
    """
    global _logging_configured

    # Only configure logging once
    if _logging_configured:
        return logging.getLogger()

    # Determine log directory
    if log_dir is None:
        # Default to a 'logs' directory in the project root
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        log_dir = os.path.join(base_dir, 'logs')

    # Ensure log directory exists
    os.makedirs(log_dir, exist_ok=True)

    # Get current date for log filename
    current_date = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(log_dir, f"app_{current_date}.log")

    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # Configure formatter with timestamp, level, and module info
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Console handler (INFO level)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # File handler (DEBUG level)
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Clear existing handlers to prevent duplicate logging
    logger.handlers.clear()

    # Add handlers to the root logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    # Rotating file handler for long-term log management
    try:
        from logging.handlers import RotatingFileHandler
        rotating_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5  # Keep 5 backup files
        )
        rotating_handler.setLevel(logging.DEBUG)
        rotating_handler.setFormatter(formatter)
        logger.addHandler(rotating_handler)
    except ImportError:
        logger.warning("RotatingFileHandler could not be imported")

    # Log startup message
    logger.info("Logging system initialized")

    # Mark as configured
    _logging_configured = True

    return logger


# PySide6-specific logging signal emitter
class LogSignalEmitter(QObject):
    """
    A Qt-based log signal emitter to support reactive logging.

    Allows logging messages to be broadcast as Qt signals,
    which can be connected to UI components or other observers.
    """

    # Signals for different log levels
    debug_logged = Signal(str)
    info_logged = Signal(str)
    warning_logged = Signal(str)
    error_logged = Signal(str)
    critical_logged = Signal(str)

    def __init__(self, parent=None):
        """
        Initialize the log signal emitter.

        Args:
            parent: Optional parent QObject
        """
        super().__init__(parent)

    def emit_debug(self, message: str):
        """Emit debug log signal"""
        self.debug_logged.emit(message)
        logging.debug(message)

    def emit_info(self, message: str):
        """Emit info log signal"""
        self.info_logged.emit(message)
        logging.info(message)

    def emit_warning(self, message: str):
        """Emit warning log signal"""
        self.warning_logged.emit(message)
        logging.warning(message)

    def emit_error(self, message: str):
        """Emit error log signal"""
        self.error_logged.emit(message)
        logging.error(message)

    def emit_critical(self, message: str):
        """Emit critical log signal"""
        self.critical_logged.emit(message)
        logging.critical(message)


# Global log signal emitter for easy access
log_signal_emitter = LogSignalEmitter()