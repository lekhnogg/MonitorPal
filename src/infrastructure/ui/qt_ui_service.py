# src/infrastructure/ui/qt_ui_service.py

import sys
from typing import Tuple, Optional, Any

# --- PySide6 Imports ---
from PySide6.QtWidgets import (QMessageBox, QFileDialog, QApplication, QMainWindow, QWidget)
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtCore import (Qt, QObject, Signal, Slot, QEventLoop, QTimer, QThread)

# --- Domain Imports ---
from src.domain.services.i_ui_service import IUIService, IFlashOverlay
from src.domain.services.i_logger_service import ILoggerService
from src.domain.common.result import Result
from src.domain.common.errors import UIError, ConfigurationError

# --- Concrete Implementation of the Overlay Widget ---
class QtFlashOverlay(QWidget):
    """
    A simple QWidget implementation for the flashing overlay.
    It adheres to the IFlashOverlay interface via duck typing/registration.
    """
    def __init__(self, coords: Tuple[int, int, int, int], parent=None):
        """Initialize the overlay widget."""
        super().__init__(parent)
        x, y, w, h = coords
        self.setGeometry(x, y, w, h)

        # Configure appearance and behavior
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |    # No window border or title bar
            Qt.WindowType.WindowStaysOnTopHint |   # Ensure it's visible above other windows
            Qt.WindowType.Tool                     # Prevent appearing in the taskbar/alt-tab
        )
        # Make the widget background transparent so only the border shows
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        # Prevent the overlay from receiving mouse/keyboard events
        self.setAttribute(Qt.WA_Disabled, True)
        # Prevent the overlay from stealing focus when shown
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        # Visual style for the flashing border
        self.fill_color = QColor(57, 255, 20, 128) # Neon Green (~50% transparent)

        self.setVisible(False) # Start hidden; visibility controlled by FlashWorker

    def paintEvent(self, event):
        """Overrides the paint event to draw the flashing border."""
        painter = QPainter(self)
        painter.setPen(Qt.PenStyle.NoPen)  # No outline
        painter.fillRect(self.rect(), self.fill_color)  # Fill with the defined color

    def show(self):
        """Show the overlay."""
        super().show() # Call the parent QWidget's show method

    def hide(self):
        """Hide the overlay."""
        super().hide() # Call the parent QWidget's hide method

    def destroy_overlay(self):
        """Safely closes and schedules the deletion of the overlay widget."""
        self.hide()
        self.deleteLater()

# --- Register the concrete class as implementing the interface (optional but good practice) ---
IFlashOverlay.register(QtFlashOverlay)

# --- Private Bridge for Thread-Safe UI Calls ---
class _QtUIBridge(QObject):
    """Private bridge class to handle UI operations safely on the main Qt thread."""
    # Define signals for each type of UI operation
    message_signal = Signal(object)         # For show_message
    confirmation_signal = Signal(object)    # For show_confirmation
    file_selection_signal = Signal(object)  # For select_file
    region_selection_signal = Signal(object)# For select_screen_region
    activation_signal = Signal(object)      # For activate_application_window
    create_overlay_signal = Signal(object)  # For create_flash_overlay

    # Arguments for signals are packed into dictionaries

    def __init__(self, logger: ILoggerService):
        """Initialize the UI bridge and connect signals."""
        super().__init__()
        self.logger = logger

        # Connect signals to their corresponding implementation slots
        # Qt.QueuedConnection ensures the slot runs in the receiver's thread (main thread)
        self.message_signal.connect(self._show_message_impl, Qt.QueuedConnection)
        self.confirmation_signal.connect(self._show_confirmation_impl, Qt.QueuedConnection)
        self.file_selection_signal.connect(self._select_file_impl, Qt.QueuedConnection)
        self.region_selection_signal.connect(self._select_region_impl, Qt.QueuedConnection)
        self.activation_signal.connect(self._activate_window_impl, Qt.QueuedConnection)
        self.create_overlay_signal.connect(self._create_flash_overlay_impl, Qt.QueuedConnection)

    # --- Slot Implementations (These run on the main thread) ---

    @Slot(object)
    def _show_message_impl(self, args_dict):
        """Main thread implementation for showing message boxes."""
        title = args_dict["title"]
        message = args_dict["message"]
        message_type = args_dict["message_type"]
        callback = args_dict["callback"]
        try:
            # Select appropriate QMessageBox static method
            if message_type == "info":
                QMessageBox.information(None, title, message)
            elif message_type == "warning":
                QMessageBox.warning(None, title, message)
            elif message_type == "error":
                QMessageBox.critical(None, title, message)
            elif message_type == "question":
                 # Note: question usually returns a value, but show_message doesn't expect one
                 QMessageBox.question(None, title, message)
            else: # Default to info
                QMessageBox.information(None, title, message)
            callback(True, None) # Signal success back to calling thread
        except Exception as e:
            self.logger.error(f"Error showing message dialog: {e}", exc_info=True)
            callback(None, e) # Signal failure back

    @Slot(object)
    def _show_confirmation_impl(self, args_dict):
        """Main thread implementation for showing confirmation boxes."""
        title = args_dict["title"]
        message = args_dict["message"]
        callback = args_dict["callback"]
        try:
            reply = QMessageBox.question(
                None, title, message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, # Use enum values
                QMessageBox.StandardButton.No # Default button
            )
            callback(reply == QMessageBox.StandardButton.Yes, None) # Return boolean result
        except Exception as e:
            self.logger.error(f"Error showing confirmation dialog: {e}", exc_info=True)
            callback(None, e)

    @Slot(object)
    def _select_file_impl(self, args_dict):
        """Main thread implementation for file selection dialog."""
        title = args_dict["title"]
        filter_pattern = args_dict["filter_pattern"]
        callback = args_dict["callback"]
        try:
            options = QFileDialog.Options()
            # options |= QFileDialog.DontUseNativeDialog # Uncomment for non-native dialog if needed
            file_path, _ = QFileDialog.getOpenFileName(
                None, title, "", filter_pattern, options=options
            )
            callback(file_path if file_path else None, None) # Return path or None if cancelled
        except Exception as e:
            self.logger.error(f"Error showing file selection dialog: {e}", exc_info=True)
            callback(None, e)

    @Slot(object)
    def _select_region_impl(self, args_dict):
        """Main thread implementation for screen region selection."""
        message = args_dict["message"]
        callback = args_dict["callback"]
        try:
            # Import dynamically to avoid potential startup circular dependencies
            from src.presentation.components.qt_region_selector import select_region_qt
            region = select_region_qt(message)
            callback(region, None) # Return region tuple or None if cancelled
        except Exception as e:
            self.logger.error(f"Error in region selection: {e}", exc_info=True)
            callback(None, e)

    @Slot(object)
    def _activate_window_impl(self, args_dict):
        """Main thread implementation for activating the application window."""
        callback = args_dict["callback"]
        try:
            main_window = None
            # Find the QMainWindow instance among top-level widgets
            for widget in QApplication.instance().topLevelWidgets():
                if isinstance(widget, QMainWindow):
                    main_window = widget
                    break

            if not main_window:
                 self.logger.warning("Could not find QMainWindow instance to activate.")
                 callback(False, None) # Indicate failure to find window
                 return

            # Bring window to front using standard Qt methods
            main_window.setWindowState(main_window.windowState() & ~Qt.WindowState.WindowMinimized)
            main_window.show()
            main_window.activateWindow()
            main_window.raise_()

            # Optional: Windows-specific activation for stubborn cases
            if sys.platform == 'win32':
                try:
                    window_id = int(main_window.winId())
                    import win32gui
                    import win32con
                    # Attempt to force window to foreground
                    win32gui.ShowWindow(window_id, win32con.SW_RESTORE) # Ensure not minimized
                    win32gui.SetForegroundWindow(window_id)
                except ImportError:
                     self.logger.debug("pywin32 not installed, skipping Windows-specific activation.")
                except Exception as e:
                    self.logger.warning(f"Windows-specific activation failed: {e}")

            callback(True, None) # Signal success
        except Exception as e:
            self.logger.error(f"Error activating application window: {e}", exc_info=True)
            callback(None, e) # Signal failure

    @Slot(object)
    def _create_flash_overlay_impl(self, args_dict):
        """Main thread implementation for creating the flash overlay widget."""
        coords = args_dict["coords"]
        callback = args_dict["callback"]
        try:
            # Ensure QApplication exists (should always unless major setup issue)
            if not QApplication.instance():
                 raise RuntimeError("QApplication not initialized when creating overlay")
            # Instantiate the concrete QtFlashOverlay widget
            overlay = QtFlashOverlay(coords)
            self.logger.debug(f"Flash overlay widget created on main thread: {overlay}")
            callback(overlay, None) # Pass the created widget instance back
        except Exception as e:
            self.logger.error(f"Error creating flash overlay on main thread: {e}", exc_info=True)
            callback(None, e) # Signal failure


# --- Main Service Implementation ---
class QtUIService(IUIService):
    """
    Qt implementation of the UI service, providing thread-safe UI interactions.
    """

    def __init__(self, logger: ILoggerService):
        """Initialize the UI service."""
        self.logger = logger
        # Create the bridge object to handle cross-thread communication
        self._bridge = _QtUIBridge(logger)
        # Store a reference to the main Qt application thread
        self._main_thread = QApplication.instance().thread()


    def show_message(self, title: str, message: str, message_type: str = "info") -> Result[bool]:
        """Show a message dialog to the user (thread-safe)."""
        self.logger.debug(f"Showing message: '{title}' ({message_type})")
        # Check if the current thread is the main GUI thread
        if QThread.currentThread() == self._main_thread:
            self.logger.debug("Executing show_message directly (main thread)")
            try:
                # Execute directly as it's safe
                if message_type == "info": QMessageBox.information(None, title, message)
                elif message_type == "warning": QMessageBox.warning(None, title, message)
                elif message_type == "error": QMessageBox.critical(None, title, message)
                elif message_type == "question": QMessageBox.question(None, title, message)
                else: QMessageBox.information(None, title, message)
                return Result.ok(True)
            except Exception as e:
                error = UIError(message=f"Error showing message dialog: {e}", inner_error=e)
                self.logger.error(str(error), exc_info=True)
                return Result.fail(error)
        else:
            # Execute via the bridge for thread safety
            self.logger.debug("Executing show_message via bridge (background thread)")
            return self._execute_on_main_thread(
                self._bridge.message_signal,
                {"title": title, "message": message, "message_type": message_type}
            )

    def show_confirmation(self, title: str, message: str) -> Result[bool]:
        """Show a confirmation dialog (Yes/No) to the user (thread-safe)."""
        self.logger.debug(f"Showing confirmation: '{title}'")
        if QThread.currentThread() == self._main_thread:
            self.logger.debug("Executing show_confirmation directly (main thread)")
            try:
                reply = QMessageBox.question(None, title, message,
                                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                             QMessageBox.StandardButton.No)
                return Result.ok(reply == QMessageBox.StandardButton.Yes)
            except Exception as e:
                error = UIError(message=f"Error showing confirmation dialog: {e}", inner_error=e)
                self.logger.error(str(error), exc_info=True)
                return Result.fail(error)
        else:
            self.logger.debug("Executing show_confirmation via bridge (background thread)")
            return self._execute_on_main_thread(
                self._bridge.confirmation_signal,
                {"title": title, "message": message}
            )

    def select_file(self, title: str, filter_pattern: str) -> Result[Optional[str]]:
        """Show a file selection dialog (thread-safe). Returns None if cancelled."""
        self.logger.debug(f"Showing file selection: '{title}'")
        if QThread.currentThread() == self._main_thread:
            self.logger.debug("Executing select_file directly (main thread)")
            try:
                options = QFileDialog.Options()
                file_path, _ = QFileDialog.getOpenFileName(None, title, "", filter_pattern, options=options)
                return Result.ok(file_path if file_path else None)
            except Exception as e:
                error = UIError(message=f"Error showing file selection dialog: {e}", inner_error=e)
                self.logger.error(str(error), exc_info=True)
                return Result.fail(error)
        else:
            self.logger.debug("Executing select_file via bridge (background thread)")
            # The bridge's callback handles returning file_path or None
            return self._execute_on_main_thread(
                self._bridge.file_selection_signal,
                {"title": title, "filter_pattern": filter_pattern}
            )

    def select_screen_region(self, message: str) -> Result[Optional[Tuple[int, int, int, int]]]:
        """Allow the user to select a screen region (thread-safe). Returns None if cancelled."""
        self.logger.debug(f"Selecting screen region: '{message}'")
        try:
            # Import needed for direct execution check
            from src.presentation.components.qt_region_selector import select_region_qt

            if QThread.currentThread() == self._main_thread:
                self.logger.debug("Executing select_screen_region directly (main thread)")
                try:
                    region = select_region_qt(message)
                    # select_region_qt returns None if cancelled
                    if region is None:
                         self.logger.info("Region selection cancelled by user.")
                         # Return success with None value for cancellation
                         return Result.ok(None)
                    return Result.ok(region)
                except Exception as e:
                    error = UIError(message=f"Error during region selection: {e}", inner_error=e)
                    self.logger.error(str(error), exc_info=True)
                    return Result.fail(error)
            else:
                # Use the bridge; the bridge callback handles None return
                self.logger.debug("Executing select_screen_region via bridge (background thread)")
                result = self._execute_on_main_thread(
                    self._bridge.region_selection_signal,
                    {"message": message}
                )
                # Check if bridge operation succeeded but returned None (cancellation)
                if result.is_success and result.value is None:
                    self.logger.info("Region selection cancelled by user (via bridge).")
                    return Result.ok(None) # Return success with None value
                elif result.is_failure:
                    return Result.fail(result.error) # Propagate bridge error
                else:
                    return result # Return success with region tuple

        except ImportError as e:
             error = UIError(message="Region selector component not found.", inner_error=e)
             self.logger.error(str(error), exc_info=True)
             return Result.fail(error)
        except Exception as e: # Catch any other unexpected error during setup
            error = UIError(message=f"Unexpected error setting up region selection: {e}", inner_error=e)
            self.logger.error(str(error), exc_info=True)
            return Result.fail(error)

    def activate_application_window(self) -> Result[bool]:
        """Bring the main application window to the foreground (thread-safe)."""
        self.logger.debug("Activating application window")
        # Always use the bridge for this operation for consistency and potential platform specifics
        self.logger.debug("Executing activate_application_window via bridge")
        return self._execute_on_main_thread(
            self._bridge.activation_signal,
            {}
        )

    def create_flash_overlay(self, coords: Tuple[int, int, int, int]) -> Result[IFlashOverlay]:
        """Creates a non-interactive overlay widget for flashing (thread-safe)."""
        self.logger.debug(f"Request to create flash overlay at {coords}")

        # Basic validation of coordinates
        if not (isinstance(coords, tuple) and len(coords) == 4 and
                all(isinstance(c, int) for c in coords) and
                coords[2] > 0 and coords[3] > 0):
            error = ConfigurationError(message=f"Invalid coordinates provided for flash overlay: {coords}")
            self.logger.error(str(error))
            return Result.fail(error)

        # Check if running on the main GUI thread
        if QThread.currentThread() == self._main_thread:
            self.logger.debug("Creating overlay directly (main thread)")
            try:
                # Instantiate the concrete QtFlashOverlay widget
                overlay = QtFlashOverlay(coords)
                return Result.ok(overlay) # Return the instance adhering to IFlashOverlay
            except Exception as e:
                error = UIError(message=f"Error creating flash overlay directly: {e}", inner_error=e)
                self.logger.error(str(error), exc_info=True)
                return Result.fail(error)
        else:
            # Execute overlay creation on the main thread via the bridge
            self.logger.debug("Creating overlay via bridge (background thread)")
            return self._execute_on_main_thread(
                self._bridge.create_overlay_signal, # Use the dedicated signal
                {"coords": coords}
            )

    def _execute_on_main_thread(self, signal: Signal, args_dict: dict) -> Result[Any]:
        """
        Helper method to execute a task on the main thread via signals and wait for the result.
        """
        try:
            # Dictionary to store the result received from the main thread callback
            result_container = {"success": False, "value": None, "error": None}
            # Event loop to pause the current (background) thread until the main thread replies
            loop = QEventLoop()

            # Callback function that will be executed by the main thread slot
            def callback(value: Optional[Any], error: Optional[Exception]):
                result_container["value"] = value
                result_container["error"] = error
                result_container["success"] = error is None
                loop.quit() # Exit the event loop once the result is received

            # Add the callback function to the arguments dictionary passed via the signal
            args_dict["callback"] = callback

            # Emit the signal, sending the arguments to the connected slot on the main thread
            signal.emit(args_dict)

            # Set up a timeout timer in case the main thread never responds
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(loop.quit) # Exit loop on timeout
            timer.start(10000) # 10-second timeout (adjust if needed)

            # Start the event loop - this blocks the current thread until loop.quit() is called
            loop.exec()
            timer.stop() # Stop the timer if the loop exited normally

            # Process the result received in the container
            if result_container["success"]:
                return Result.ok(result_container["value"])
            else:
                # Determine error message (use received error or timeout message)
                if result_container["error"]:
                     error_text = f"UI operation failed: {result_container['error']}"
                     inner_error = result_container['error']
                elif not timer.isActive(): # Timer timed out
                     error_text = "UI operation timed out"
                     inner_error = TimeoutError(error_text)
                else: # Should not happen if loop exited normally without success/error
                    error_text = "UI operation failed for an unknown reason"
                    inner_error = RuntimeError(error_text)

                # Create and log a UIError
                error = UIError(message=error_text, inner_error=inner_error)
                self.logger.error(str(error), exc_info=(isinstance(inner_error, Exception)))
                return Result.fail(error)

        except Exception as e: # Catch unexpected errors during the setup/execution
            error = UIError(message=f"Error executing UI operation via bridge: {e}", inner_error=e)
            self.logger.error(str(error), exc_info=True)
            return Result.fail(error)