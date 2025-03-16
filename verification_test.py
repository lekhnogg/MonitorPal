#!/usr/bin/env python
"""
Test application for Cold Turkey Blocker verification.

This standalone app tests the verification functionality of Cold Turkey blocks
using the application's existing architecture and services.
"""
import sys
import os
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QComboBox, QStatusBar
)
from PySide6.QtCore import Qt, Slot, QTimer

# Prevent double logging by disabling Python's built-in logger
import logging

logging.getLogger().handlers = []  # Remove all handlers from the root logger
logging.getLogger().addHandler(logging.NullHandler())  # Add null handler to avoid warnings

# Add parent directory to path to allow imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import app initialization and container
from src.application.app import initialize_app, get_container

# Import interfaces
from src.domain.services.i_verification_service import IVerificationService
from src.domain.services.i_cold_turkey_service import IColdTurkeyService
from src.domain.services.i_config_repository_service import IConfigRepository
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_ui_service import IUIService


class VerificationTestWindow(QMainWindow):
    """Main window for the Cold Turkey verification test app."""

    def __init__(self, container):
        """Initialize the main window with services from the container."""
        super().__init__()

        # Resolve services from the container
        self.verification_service = container.resolve(IVerificationService)
        self.cold_turkey_service = container.resolve(IColdTurkeyService)
        self.config_repository = container.resolve(IConfigRepository)
        self.logger = container.resolve(ILoggerService)
        self.ui_service = container.resolve(IUIService)

        self.setWindowTitle("Cold Turkey Block Verification Test")
        self.setMinimumSize(600, 500)

        # Create and set the central widget
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # Create layout
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setSpacing(10)
        self.main_layout.setContentsMargins(10, 10, 10, 10)

        # Add header
        header_label = QLabel("Cold Turkey Block Verification Test")
        header_label.setStyleSheet("font-size: 16pt; font-weight: bold;")
        self.main_layout.addWidget(header_label)

        # Add description
        description = QLabel(
            "This utility tests the verification of Cold Turkey Blocker blocks "
            "for trading platforms. Enter the platform name and block name to verify."
        )
        description.setWordWrap(True)
        self.main_layout.addWidget(description)

        # Path configuration
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Cold Turkey Path:"))

        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Path to Cold Turkey Blocker executable")
        path_layout.addWidget(self.path_input, 1)

        self.browse_button = QPushButton("Browse...")
        path_layout.addWidget(self.browse_button)

        self.save_path_button = QPushButton("Save Path")
        path_layout.addWidget(self.save_path_button)

        self.main_layout.addLayout(path_layout)

        # Platform selection
        platform_layout = QHBoxLayout()
        platform_layout.addWidget(QLabel("Platform:"))

        self.platform_combo = QComboBox()
        self.platform_combo.addItems(["Quantower", "NinjaTrader", "TradingView", "Tradovate"])
        self.platform_combo.setCurrentText("NinjaTrader")  # Set a default
        platform_layout.addWidget(self.platform_combo, 1)

        self.main_layout.addLayout(platform_layout)

        # Block name
        block_layout = QHBoxLayout()
        block_layout.addWidget(QLabel("Block Name:"))

        self.block_input = QLineEdit("Ninja")  # Default value for testing
        self.block_input.setPlaceholderText("Enter the name of the Cold Turkey block")
        block_layout.addWidget(self.block_input, 1)

        self.main_layout.addLayout(block_layout)

        # Verification button
        self.verify_button = QPushButton("Verify Block")
        self.verify_button.setMinimumHeight(40)
        self.main_layout.addWidget(self.verify_button)

        # Cancel button
        self.cancel_button = QPushButton("Cancel Verification")
        self.cancel_button.setEnabled(False)
        self.main_layout.addWidget(self.cancel_button)

        # Log output
        self.main_layout.addWidget(QLabel("Log Output:"))

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMinimumHeight(200)
        self.main_layout.addWidget(self.log_output)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Connect signals
        self.verify_button.clicked.connect(self.verify_block)
        self.cancel_button.clicked.connect(self.cancel_verification)
        self.browse_button.clicked.connect(self.browse_for_path)
        self.save_path_button.clicked.connect(self.save_path)

        # Load current path from config
        self.load_path()

        # Update verification status
        self.update_verification_status()

        # Log initialization
        self.log_message("Verification Test App initialized", "info")

        # Make window active when started
        self.activateWindow()
        self.raise_()

    def load_path(self):
        """Load Cold Turkey path from configuration."""
        # Get path using the service's method rather than direct configuration access
        path_result = self.cold_turkey_service.get_blocker_path()

        if path_result.is_success:
            path = path_result.value
            self.path_input.setText(path)

            # Update status based on path
            if path and os.path.exists(path):
                self.status_bar.showMessage("Cold Turkey Blocker path is configured.")
            else:
                self.status_bar.showMessage("Cold Turkey Blocker path is not configured or invalid!", 5000)
        else:
            self.log_message(f"Failed to load Cold Turkey path: {path_result.error}", "error")
            self.status_bar.showMessage("Failed to load Cold Turkey path configuration!", 5000)

    def save_path(self):
        """Save Cold Turkey path to configuration."""
        path = self.path_input.text().strip()

        if not path:
            self.log_message("Error: Path cannot be empty", "error")
            return

        if not os.path.exists(path):
            self.log_message(f"Error: Path does not exist: {path}", "error")
            return

        result = self.cold_turkey_service.set_blocker_path(path)

        if result.is_success:
            self.log_message(f"Successfully saved Cold Turkey path: {path}", "info")
            self.status_bar.showMessage("Path saved successfully!")
            self.update_verification_status()
        else:
            self.log_message(f"Failed to save path: {result.error}", "error")
            self.status_bar.showMessage("Failed to save path!")

    def browse_for_path(self):
        """Open file dialog to browse for Cold Turkey executable using UI service."""
        result = self.ui_service.select_file(
            "Locate Cold Turkey Blocker Executable",
            "Executables (*.exe)"
        )

        if result.is_success and result.value:
            self.path_input.setText(result.value)

    @Slot()
    def verify_block(self):
        """Initiate the block verification process."""
        platform = self.platform_combo.currentText()
        block_name = self.block_input.text().strip()

        if not block_name:
            self.log_message("Error: Block name cannot be empty", "error")
            return

        self.log_message(f"Starting verification for platform '{platform}' with block '{block_name}'...", "info")

        # Verify the blocker path first
        if not self.cold_turkey_service.is_blocker_path_configured():
            self.log_message("Error: Cold Turkey Blocker path is not configured", "error")
            return

        # Update UI state
        self.verify_button.setEnabled(False)
        self.cancel_button.setEnabled(True)

        # Start verification process
        result = self.verification_service.verify_platform_block(platform, block_name)

        if result.is_failure:
            self.log_message(f"Failed to start verification: {result.error}", "error")
            self.verify_button.setEnabled(True)
            self.cancel_button.setEnabled(False)
            return

        self.log_message("Verification process started. This may take a moment...", "info")
        self.status_bar.showMessage("Verification in progress...")

        # Start a timer to check verification status
        self.check_timer = QTimer(self)
        self.check_timer.timeout.connect(self.check_verification_status)
        self.check_timer.start(500)  # Check every 500ms

    @Slot()
    def check_verification_status(self):
        """Check the status of the verification process."""
        if not self.verification_service.is_verification_in_progress():
            self.check_timer.stop()

            # Wait a brief moment to ensure all async operations complete
            QTimer.singleShot(200, self._update_after_verification)

    def _update_after_verification(self):
        """Update UI after verification completes."""
        # Check if verification succeeded by looking at verified blocks
        verified_blocks_result = self.verification_service.get_verified_blocks()

        if verified_blocks_result.is_success:
            platform = self.platform_combo.currentText()
            block_found = False

            for block in verified_blocks_result.value:
                if block.get("platform") == platform:
                    block_found = True
                    self.log_message(
                        f"Verification successful! Block '{block.get('block_name')}' "
                        f"is now verified for platform '{platform}'",
                        "success"
                    )
                    break

            if not block_found:
                self.log_message(
                    f"Verification failed or was cancelled. No verified block found for '{platform}'",
                    "error"
                )
        else:
            self.log_message(f"Error checking verified blocks: {verified_blocks_result.error}", "error")

        # Reset UI state
        self.verify_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.status_bar.showMessage("Verification completed.")

        # Refresh verification status
        self.update_verification_status()

        # Re-activate this window
        self.activateWindow()
        self.raise_()

    @Slot()
    def cancel_verification(self):
        """Cancel the ongoing verification process."""
        if self.verification_service.is_verification_in_progress():
            self.log_message("Cancelling verification...", "info")

            result = self.verification_service.cancel_verification()

            if result.is_success:
                self.log_message("Verification cancelled successfully", "info")
            else:
                self.log_message(f"Failed to cancel verification: {result.error}", "error")

        # Reset UI state
        self.verify_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

        # Stop the check timer if it's running
        if hasattr(self, "check_timer") and self.check_timer.isActive():
            self.check_timer.stop()

    def update_verification_status(self):
        """Update the UI with current verification status."""
        result = self.verification_service.get_verified_blocks()

        if result.is_failure:
            self.log_message(f"Error getting verified blocks: {result.error}", "error")
            return

        verified_blocks = result.value

        if not verified_blocks:
            self.log_message("No verified blocks found.", "info")
            return

        self.log_message("Current verified blocks:", "info")

        for block in verified_blocks:
            platform = block.get("platform", "Unknown")
            block_name = block.get("block_name", "Unknown")
            self.log_message(f"  • Platform: {platform}, Block: {block_name}", "info")

    def log_message(self, message: str, level: str = "info"):
        """Add a message to the log output with appropriate styling."""
        # Define colors for different log levels
        colors = {
            "info": "black",
            "success": "green",
            "warning": "orange",
            "error": "red",
            "critical": "darkred"
        }

        # Normalize level to lowercase for consistency
        level = level.lower()
        color = colors.get(level, "black")

        # Add message to log output with timestamp
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Log through the logger service
        log_method = getattr(self.logger, level, self.logger.info)
        log_method(message)

        # Add to UI with HTML formatting
        self.log_output.append(
            f'<span style="color:{color}">[{timestamp}] [{level.upper()}] {message}</span>'
        )

        # Auto-scroll to bottom
        self.log_output.verticalScrollBar().setValue(
            self.log_output.verticalScrollBar().maximum()
        )

    def closeEvent(self, event):
        """Handle window close event to ensure thread cleanup."""
        # Cancel any running verification
        if self.verification_service.is_verification_in_progress():
            self.verification_service.cancel_verification()

        # Accept the close event
        event.accept()


def modify_ui_service():
    """Patch UI service to correctly handle window activation."""
    # Get the container
    container = get_container()

    # Get UI service
    ui_service = container.resolve(IUIService)

    # Add the activation method if it doesn't exist
    if not hasattr(ui_service, 'activate_application_window'):
        from src.domain.common.result import Result
        from src.domain.common.errors import UIError

        def activate_application_window(self):
            """Bring the main application window to the foreground."""

            def operation():
                # Import QMainWindow and QApplication
                from PySide6.QtWidgets import QMainWindow, QApplication
                from PySide6.QtCore import Qt

                # Find the main window
                main_window = None
                for widget in QApplication.topLevelWidgets():
                    if isinstance(widget, QMainWindow):
                        main_window = widget
                        break

                if not main_window:
                    return False

                # Use Qt's built-in mechanisms first
                main_window.setWindowState(
                    main_window.windowState() & ~Qt.WindowMinimized
                )
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

        # Add the method to the UI service
        import types
        ui_service.activate_application_window = types.MethodType(
            activate_application_window, ui_service
        )


def main():
    """Main entry point for the test application."""
    try:
        # Initialize QApplication
        app = QApplication(sys.argv)

        # Use the application's own initialization
        container = initialize_app()

        # Patch the UI service to add activation method
        modify_ui_service()

        # Create main window with the container
        window = VerificationTestWindow(container)
        window.show()

        # Run the application
        sys.exit(app.exec())

    except Exception as e:
        print(f"Error starting application: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()