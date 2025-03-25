# src/infrastructure/ui/qt_ui_service.py

import sys
from typing import Tuple, Optional

from PySide6.QtWidgets import QMessageBox, QFileDialog, QApplication, QMainWindow
from PySide6.QtCore import Qt, QObject, Signal, Slot, QEventLoop, QTimer, QThread

from src.domain.services.i_ui_service import IUIService
from src.domain.services.i_logger_service import ILoggerService
from src.domain.common.result import Result
from src.domain.common.errors import UIError


class _QtUIBridge(QObject):
    """Private bridge class to handle UI operations on the main thread."""
    # Define signals for thread-safe UI operations
    message_signal = Signal(object)  # Arguments packed as dictionary
    confirmation_signal = Signal(object)
    file_selection_signal = Signal(object)
    region_selection_signal = Signal(object)
    activation_signal = Signal(object)

    def __init__(self, logger: ILoggerService):
        """Initialize the UI bridge."""
        super().__init__()
        self.logger = logger

        # Connect signals to main thread handlers
        self.message_signal.connect(self._show_message_impl, Qt.QueuedConnection)
        self.confirmation_signal.connect(self._show_confirmation_impl, Qt.QueuedConnection)
        self.file_selection_signal.connect(self._select_file_impl, Qt.QueuedConnection)
        self.region_selection_signal.connect(self._select_region_impl, Qt.QueuedConnection)
        self.activation_signal.connect(self._activate_window_impl, Qt.QueuedConnection)

    @Slot(object)
    def _show_message_impl(self, args_dict):
        """Implementation of show_message on the main thread."""
        title = args_dict["title"]
        message = args_dict["message"]
        message_type = args_dict["message_type"]
        callback = args_dict["callback"]

        try:
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
            callback(True, None)
        except Exception as e:
            self.logger.error(f"Error showing message dialog: {e}")
            callback(None, e)

    @Slot(object)
    def _show_confirmation_impl(self, args_dict):
        """Implementation of show_confirmation on the main thread."""
        title = args_dict["title"]
        message = args_dict["message"]
        callback = args_dict["callback"]

        try:
            reply = QMessageBox.question(
                None, title, message,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            callback(reply == QMessageBox.Yes, None)
        except Exception as e:
            self.logger.error(f"Error showing confirmation dialog: {e}")
            callback(None, e)

    @Slot(object)
    def _select_file_impl(self, args_dict):
        """Implementation of select_file on the main thread."""
        title = args_dict["title"]
        filter_pattern = args_dict["filter_pattern"]
        callback = args_dict["callback"]

        try:
            options = QFileDialog.Options()
            file_path, _ = QFileDialog.getOpenFileName(
                None, title, "", filter_pattern, options=options
            )
            callback(file_path, None)
        except Exception as e:
            self.logger.error(f"Error showing file selection dialog: {e}")
            callback(None, e)

    @Slot(object)
    def _select_region_impl(self, args_dict):
        """Implementation of select_screen_region on the main thread."""
        message = args_dict["message"]
        callback = args_dict["callback"]

        try:
            # Import here to avoid circular imports
            from src.presentation.components.qt_region_selector import select_region_qt
            region = select_region_qt(message)
            callback(region, None)
        except Exception as e:
            self.logger.error(f"Error in region selection: {e}")
            callback(None, e)

    @Slot(object)
    def _activate_window_impl(self, args_dict):
        """Implementation of activate_application_window on the main thread."""
        callback = args_dict["callback"]

        try:
            # Find the main window
            main_window = None
            for widget in QApplication.topLevelWidgets():
                if isinstance(widget, QMainWindow):
                    main_window = widget
                    break

            if not main_window:
                callback(False, None)
                return

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

            callback(True, None)
        except Exception as e:
            self.logger.error(f"Error activating application window: {e}")
            callback(None, e)


class QtUIService(IUIService):
    """Qt implementation of UI service with thread safety."""

    def __init__(self, logger: ILoggerService):
        """Initialize the UI service."""
        self.logger = logger
        self._bridge = _QtUIBridge(logger)
        self._main_thread = QApplication.instance().thread()

    def show_message(self, title: str, message: str, message_type: str = "info") -> Result[bool]:
        """Show a message dialog to the user."""
        self.logger.debug(f"Showing message dialog: {title} ({message_type})")

        # Return early for direct execution if we're on the main thread
        if QThread.currentThread() == self._main_thread:
            try:
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
                return Result.ok(True)
            except Exception as e:
                error = UIError(message=f"Error showing message dialog: {e}", inner_error=e)
                self.logger.error(str(error))
                return Result.fail(error)

        # For background threads, use the bridge
        return self._execute_on_main_thread(
            self._bridge.message_signal,
            {"title": title, "message": message, "message_type": message_type}
        )

    def show_confirmation(self, title: str, message: str) -> Result[bool]:
        """Show a confirmation dialog and return the user's choice."""
        self.logger.debug(f"Showing confirmation dialog: {title}")

        # Return early for direct execution if we're on the main thread
        if QThread.currentThread() == self._main_thread:
            try:
                reply = QMessageBox.question(
                    None, title, message,
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                return Result.ok(reply == QMessageBox.Yes)
            except Exception as e:
                error = UIError(message=f"Error showing confirmation dialog: {e}", inner_error=e)
                self.logger.error(str(error))
                return Result.fail(error)

        # For background threads, use the bridge
        return self._execute_on_main_thread(
            self._bridge.confirmation_signal,
            {"title": title, "message": message}
        )

    def select_file(self, title: str, filter_pattern: str) -> Result[str]:
        """Show a file selection dialog."""
        self.logger.debug(f"Showing file selection dialog: {title}")

        # Return early for direct execution if we're on the main thread
        if QThread.currentThread() == self._main_thread:
            try:
                options = QFileDialog.Options()
                file_path, _ = QFileDialog.getOpenFileName(
                    None, title, "", filter_pattern, options=options
                )
                return Result.ok(file_path)
            except Exception as e:
                error = UIError(message=f"Error showing file selection dialog: {e}", inner_error=e)
                self.logger.error(str(error))
                return Result.fail(error)

        # For background threads, use the bridge
        return self._execute_on_main_thread(
            self._bridge.file_selection_signal,
            {"title": title, "filter_pattern": filter_pattern}
        )

    def select_screen_region(self, message: str) -> Result[Tuple[int, int, int, int]]:
        """Allow the user to select a region on the screen."""
        self.logger.debug(f"Selecting screen region: {message}")

        # Special case - import needed first
        try:
            from src.presentation.components.qt_region_selector import select_region_qt

            # Return early for direct execution if we're on the main thread
            if QThread.currentThread() == self._main_thread:
                try:
                    region = select_region_qt(message)
                    if region is None:
                        error = UIError(message="Region selection cancelled", details={"message": message})
                        return Result.fail(error)
                    return Result.ok(region)
                except Exception as e:
                    error = UIError(message=f"Error in region selection: {e}", inner_error=e)
                    self.logger.error(str(error))
                    return Result.fail(error)

            # For background threads, use the bridge
            result = self._execute_on_main_thread(
                self._bridge.region_selection_signal,
                {"message": message}
            )

            # Additional handling for None results
            if result.is_success and result.value is None:
                error = UIError(message="Region selection cancelled", details={"message": message})
                return Result.fail(error)

            return result

        except Exception as e:
            error = UIError(message=f"Error in region selection: {e}", inner_error=e)
            self.logger.error(str(error))
            return Result.fail(error)

    def activate_application_window(self) -> Result[bool]:
        """Bring the main application window to the foreground."""
        self.logger.debug("Activating application window")

        # Here we always use the bridge to avoid duplication
        return self._execute_on_main_thread(
            self._bridge.activation_signal,
            {}
        )

    def _execute_on_main_thread(self, signal, args_dict):
        """
        Execute a function on the main thread and wait for the result.

        Args:
            signal: The signal to emit
            args_dict: Dictionary of arguments for the signal

        Returns:
            Result object with the operation outcome
        """
        try:
            # Set up synchronization
            result_container = {"success": False, "value": None, "error": None}
            loop = QEventLoop()

            # Define callback and add it to args_dict
            def callback(value, error):
                result_container["value"] = value
                result_container["error"] = error
                result_container["success"] = error is None
                loop.quit()

            # Add callback to args (no type issues since using dictionary)
            args_dict["callback"] = callback

            # Emit signal with arguments dictionary
            signal.emit(args_dict)

            # Wait for result with timeout
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: loop.quit())
            timer.start(5000)  # 5 second timeout
            loop.exec()
            timer.stop()

            # Create appropriate result
            if result_container["success"]:
                return Result.ok(result_container["value"])
            else:
                error_text = str(result_container["error"]) if result_container[
                    "error"] else "Operation timed out or failed"
                error = UIError(message=error_text, inner_error=result_container["error"])
                self.logger.error(str(error))
                return Result.fail(error)

        except Exception as e:
            error = UIError(message=f"Error executing UI operation: {e}", inner_error=e)
            self.logger.error(str(error))
            return Result.fail(error)