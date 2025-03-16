#!/usr/bin/env python3
"""
Block Verification Test Application

A standalone test application for verifying the Cold Turkey Blocker integration.
This script can be run directly to test the block verification sequence.
"""
import sys
import os
import logging
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QPushButton, QLabel, \
    QLineEdit, QFileDialog, QMessageBox, QComboBox, QGroupBox
from PySide6.QtCore import Qt, QTimer

# Add the project root to the Python path if needed
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import necessary services
from src.domain.common.di_container import DIContainer
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_background_task_service import IBackgroundTaskService
from src.domain.services.i_config_repository_service import IConfigRepository
from src.domain.services.i_verification_service import IVerificationService
from src.infrastructure.logging.logger_service import ConsoleLoggerService, FileLoggerService
from src.infrastructure.threading.qt_background_task_service import QtBackgroundTaskService
from src.infrastructure.config.json_config_repository import JsonConfigRepository
from src.infrastructure.platform.verification_service import WindowsVerificationService


class BlockVerificationTestWindow(QMainWindow):
    """
    Test window for the block verification functionality.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Block Verification Test")
        self.setMinimumSize(600, 400)

        # Initialize services
        self.initialize_services()

        # Set up UI
        self.setup_ui()

        # Load initial values from config
        self.load_config_values()

    def initialize_services(self):
        """Initialize required services."""
        # Create container
        self.container = DIContainer()

        # Set up logger
        self.logger = FileLoggerService(level=logging.DEBUG)
        self.container.register_instance(ILoggerService, self.logger)

        # Set up config repository
        config_path = os.path.join(os.getcwd(), "config.json")
        self.config_repo = JsonConfigRepository(config_path, self.logger)
        self.container.register_instance(IConfigRepository, self.config_repo)

        # Set up thread service
        self.thread_service = QtBackgroundTaskService(self.logger)
        self.container.register_instance(IBackgroundTaskService, self.thread_service)

        # Set up verification service
        self.verification_service = WindowsVerificationService(
            logger=self.logger,
            config_repository=self.config_repo,
            thread_service=self.thread_service
        )
        self.container.register_instance(IVerificationService, self.verification_service)

    def setup_ui(self):
        """Set up the user interface."""
        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Cold Turkey Blocker path selection
        blocker_group = QGroupBox("Cold Turkey Blocker Configuration")
        blocker_layout = QVBoxLayout(blocker_group)

        path_layout = QHBoxLayout()
        path_label = QLabel("Cold Turkey Path:")
        self.path_field = QLineEdit()
        self.path_field.setReadOnly(True)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_for_blocker)

        path_layout.addWidget(path_label)
        path_layout.addWidget(self.path_field, 1)
        path_layout.addWidget(browse_btn)
        blocker_layout.addLayout(path_layout)

        main_layout.addWidget(blocker_group)

        # Platform selection
        platform_group = QGroupBox("Platform Configuration")
        platform_layout = QVBoxLayout(platform_group)

        platform_selection_layout = QHBoxLayout()
        platform_label = QLabel("Platform:")
        self.platform_combo = QComboBox()
        self.platform_combo.addItems(["Quantower", "NinjaTrader", "TradingView", "Tradovate"])
        platform_selection_layout.addWidget(platform_label)
        platform_selection_layout.addWidget(self.platform_combo, 1)
        platform_layout.addLayout(platform_selection_layout)

        # Block name
        block_layout = QHBoxLayout()
        block_label = QLabel("Block Name:")
        self.block_name_field = QLineEdit()
        block_layout.addWidget(block_label)
        block_layout.addWidget(self.block_name_field, 1)
        platform_layout.addLayout(block_layout)

        main_layout.addWidget(platform_group)

        # Verification controls
        controls_group = QGroupBox("Verification Controls")
        controls_layout = QVBoxLayout(controls_group)

        # Status display
        self.status_label = QLabel("Status: Ready")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-weight: bold; padding: 10px;")
        controls_layout.addWidget(self.status_label)

        # Buttons
        button_layout = QHBoxLayout()
        self.verify_btn = QPushButton("Verify Block")
        self.verify_btn.clicked.connect(self.verify_block)
        self.verify_btn.setMinimumHeight(40)
        self.verify_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")

        self.cancel_btn = QPushButton("Cancel Verification")
        self.cancel_btn.clicked.connect(self.cancel_verification)
        self.cancel_btn.setEnabled(False)

        button_layout.addWidget(self.verify_btn)
        button_layout.addWidget(self.cancel_btn)
        controls_layout.addLayout(button_layout)

        main_layout.addWidget(controls_group)

        # Verified blocks display
        verified_group = QGroupBox("Verified Blocks")
        verified_layout = QVBoxLayout(verified_group)

        self.verified_blocks_label = QLabel("No verified blocks")
        verified_layout.addWidget(self.verified_blocks_label)

        # Add a button to clear verified blocks
        clear_btn = QPushButton("Clear Verified Blocks")
        clear_btn.clicked.connect(self.clear_verified_blocks)
        verified_layout.addWidget(clear_btn)

        main_layout.addWidget(verified_group)

        # Help section
        help_group = QGroupBox("Instructions")
        help_layout = QVBoxLayout(help_group)

        help_text = """
        <p><b>How to use this test application:</b></p>
        <ol>
            <li>Select the Cold Turkey Blocker executable using the Browse button</li>
            <li>Choose a platform from the dropdown</li>
            <li>Enter the <b>exact</b> name of the block you created in Cold Turkey</li>
            <li>Click "Verify Block" to test the verification</li>
        </ol>
        <p>The verification will check if Cold Turkey can successfully block the platform.</p>
        """
        help_label = QLabel(help_text)
        help_label.setWordWrap(True)
        help_layout.addWidget(help_label)

        main_layout.addWidget(help_group)

    def load_config_values(self):
        """Load values from configuration."""
        # Load Cold Turkey path
        ct_path = self.config_repo.get_cold_turkey_path()
        if ct_path:
            self.path_field.setText(ct_path)
            self.update_status(f"Cold Turkey Blocker found at: {ct_path}", "info")
        else:
            self.update_status("Cold Turkey Blocker path not configured", "warning")

        # Load platform
        current_platform = self.config_repo.get_current_platform()
        if current_platform:
            index = self.platform_combo.findText(current_platform)
            if index >= 0:
                self.platform_combo.setCurrentIndex(index)

        # Load block name from verified blocks
        verified_blocks = self.verification_service.get_verified_blocks()
        if verified_blocks.is_success and verified_blocks.value:
            self.refresh_verified_blocks_display(verified_blocks.value)

            # Find block for current platform
            current_platform = self.platform_combo.currentText()
            for block in verified_blocks.value:
                if block.get("platform") == current_platform:
                    self.block_name_field.setText(block.get("block_name", ""))
                    break

    def browse_for_blocker(self):
        """Open file dialog to browse for Cold Turkey Blocker executable."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Cold Turkey Blocker Executable",
            "",
            "Executables (*.exe);;All Files (*)"
        )

        if file_path:
            # Save path to config
            result = self.config_repo.set_cold_turkey_path(file_path)
            if result.is_success:
                self.path_field.setText(file_path)
                self.update_status(f"Cold Turkey Blocker path set to: {file_path}", "success")
            else:
                QMessageBox.warning(
                    self,
                    "Configuration Error",
                    f"Failed to save Cold Turkey path: {result.error}"
                )

    def verify_block(self):
        """Start the block verification process."""
        # Get values
        platform = self.platform_combo.currentText()
        block_name = self.block_name_field.text().strip()

        # Validate
        if not block_name:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Please enter a block name."
            )
            return

        if not self.verification_service.is_blocker_path_configured():
            QMessageBox.warning(
                self,
                "Configuration Error",
                "Cold Turkey Blocker path is not configured. Please select the executable."
            )
            return

        # Update UI
        self.verify_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.update_status(f"Verifying block '{block_name}' for platform '{platform}'...", "info")

        # Create a callback function for verification completion
        def on_verification_completed(result):
            # Handle result
            self.verify_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)

            if isinstance(result, bool):
                if result:
                    # Add to verified blocks
                    add_result = self.verification_service.add_verified_block(platform, block_name)
                    if add_result.is_success:
                        self.update_status(
                            f"Block '{block_name}' for '{platform}' verified successfully!",
                            "success"
                        )
                        # Refresh verified blocks display
                        verified_blocks = self.verification_service.get_verified_blocks()
                        if verified_blocks.is_success:
                            self.refresh_verified_blocks_display(verified_blocks.value)
                    else:
                        self.update_status(
                            f"Block verified but failed to save: {add_result.error}",
                            "error"
                        )
                else:
                    self.update_status(
                        f"Block verification failed. Please check that the block name matches exactly.",
                        "error"
                    )
            else:
                self.update_status(
                    f"Verification failed with unexpected result: {result}",
                    "error"
                )

        def on_verification_error(error):
            self.verify_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
            self.update_status(f"Verification error: {error}", "error")

        # Create the worker and set callbacks
        from src.infrastructure.platform.verification_service import VerificationWorker
        worker = VerificationWorker(
            platform=platform,
            block_name=block_name,
            blocker_path=self.config_repo.get_cold_turkey_path(),
            logger=self.logger
        )

        worker.set_on_completed(on_verification_completed)
        worker.set_on_error(on_verification_error)

        # Start verification
        result = self.thread_service.execute_task("verify_block", worker)

        if not result.is_success:
            self.verify_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
            self.update_status(f"Failed to start verification: {result.error}", "error")

    def cancel_verification(self):
        """Cancel the ongoing verification process."""
        result = self.verification_service.cancel_verification()
        if result.is_success:
            self.update_status("Verification cancelled", "warning")
        else:
            self.update_status(f"Failed to cancel verification: {result.error}", "error")

        self.verify_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    def clear_verified_blocks(self):
        """Clear all verified blocks."""
        reply = QMessageBox.question(
            self,
            "Confirm Clear",
            "Are you sure you want to clear all verified blocks?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            result = self.verification_service.clear_verified_blocks()
            if result.is_success:
                self.update_status("All verified blocks cleared", "info")
                self.verified_blocks_label.setText("No verified blocks")
            else:
                self.update_status(f"Failed to clear verified blocks: {result.error}", "error")

    def update_status(self, message, level="info"):
        """Update the status label with a message."""
        # Log the message
        if level == "error":
            style = "color: #D32F2F; background-color: #FFEBEE;"
            self.logger.error(message)
        elif level == "warning":
            style = "color: #FF8F00; background-color: #FFF8E1;"
            self.logger.warning(message)
        elif level == "success":
            style = "color: #388E3C; background-color: #E8F5E9;"
            self.logger.info(message)
        elif level == "info":
            style = "color: #1976D2; background-color: #E3F2FD;"
            self.logger.info(message)

        # Update the status label
        self.status_label.setText(f"Status: {message}")
        self.status_label.setStyleSheet(f"font-weight: bold; padding: 10px; border-radius: 5px; {style}")

    def refresh_verified_blocks_display(self, blocks):
        """Update the verified blocks display."""
        if not blocks:
            self.verified_blocks_label.setText("No verified blocks")
            return

        html = "<ul>"
        for block in blocks:
            platform = block.get("platform", "Unknown")
            block_name = block.get("block_name", "Unknown")
            html += f"<li><b>{platform}:</b> {block_name}</li>"
        html += "</ul>"

        self.verified_blocks_label.setText(html)

    def closeEvent(self, event):
        """Handle application close event."""
        # Clean up
        self.thread_service.cancel_all_tasks()
        event.accept()


if __name__ == "__main__":
    print("Starting Block Verification Test Application...")

    # Create application
    app = QApplication(sys.argv)

    # Set application style
    app.setStyle("Fusion")

    # Create and show the main window
    window = BlockVerificationTestWindow()
    window.show()

    # Start the application
    sys.exit(app.exec())