# src/infrastructure/ui/qt_ui_service.py

import sys
from typing import Tuple, Optional

from PySide6.QtWidgets import QMessageBox, QFileDialog, QApplication, QMainWindow
from PySide6.QtCore import Qt

from src.domain.services.i_ui_service import IUIService
from src.domain.services.i_logger_service import ILoggerService
from src.domain.common.result import Result
from src.domain.common.errors import UIError


class QtUIService(IUIService):
    """Qt implementation of UI service."""

    def __init__(self, logger: ILoggerService):
        """Initialize the UI service."""
        self.logger = logger

    def show_message(self, title: str, message: str, message_type: str = "info") -> Result[bool]:
        """Show a message dialog to the user."""

        def operation():
            if message_type == "info":
                QMessageBox.information(None, title, message)
            elif message_type == "warning":
                QMessageBox.warning(None, title, message)
            elif message_type == "error":
                QMessageBox.critical(None, title, message)
            elif message_type == "question":
                QMessageBox.question(None, title, message)
            else:
                QMessageBox.information(None, title, message)
            return True

        return Result.from_operation(
            operation,
            self.logger,
            UIError,
            "Error showing message dialog",
            title=title,
            message_type=message_type
        )

    def show_confirmation(self, title: str, message: str) -> Result[bool]:
        """Show a confirmation dialog and return the user's choice."""

        def operation():
            reply = QMessageBox.question(
                None, title, message,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            return (reply == QMessageBox.Yes)

        return Result.from_operation(
            operation,
            self.logger,
            UIError,
            "Error showing confirmation dialog",
            title=title
        )

    def select_file(self, title: str, filter_pattern: str) -> Result[str]:
        """Show a file selection dialog."""

        def operation():
            options = QFileDialog.Options()
            file_path, _ = QFileDialog.getOpenFileName(
                None, title, "", filter_pattern, options=options
            )
            return file_path

        return Result.from_operation(
            operation,
            self.logger,
            UIError,
            "Error showing file selection dialog",
            title=title,
            filter_pattern=filter_pattern
        )

    def select_screen_region(self, message: str) -> Result[Tuple[int, int, int, int]]:
        """Allow the user to select a region on the screen."""
        # This method has custom error handling, so we'll keep it as is
        try:
            # Import here to avoid circular imports
            from src.presentation.components.qt_region_selector import select_region_qt

            region = select_region_qt(message)

            if region is None:
                error = UIError(
                    message="Region selection cancelled",
                    details={"message": message}
                )
                return Result.fail(error)

            return Result.ok(region)
        except Exception as e:
            error = UIError(
                message=f"Error in region selection",
                details={"message": message},
                inner_error=e
            )
            self.logger.error(str(error))
            return Result.fail(error)

    def activate_application_window(self) -> Result[bool]:
        """Bring the main application window to the foreground."""

        def operation():
            # Find the main window
            main_window = None
            for widget in QApplication.topLevelWidgets():
                if isinstance(widget, QMainWindow):
                    main_window = widget
                    break

            if not main_window:
                return False

            # Use Qt's built-in mechanisms first
            main_window.setWindowState(main_window.windowState() & ~Qt.WindowMinimized)
            main_window.show()
            main_window.activateWindow()
            main_window.raise_()

            # For Windows, additional API calls for more reliable activation
            if sys.platform == 'win32':
                try:
                    # Convert Qt window ID to a Windows handle
                    window_id = int(main_window.winId())

                    # Try to force foreground using Win32 API
                    import win32gui
                    import win32con

                    # Ensure window is not minimized
                    if win32gui.IsIconic(window_id):
                        win32gui.ShowWindow(window_id, win32con.SW_RESTORE)

                    # Set as foreground window
                    win32gui.SetForegroundWindow(window_id)
                except Exception as e:
                    self.logger.warning(f"Windows-specific activation failed: {e}")
                    # Continue with Qt's activation methods

            return True

        return Result.from_operation(
            operation,
            self.logger,
            UIError,
            "Error activating application window"
        )