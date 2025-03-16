#!/usr/bin/env python3
"""
Test script for screenshot capture and region selection functionality.

This script tests:
1. Region selection UI
2. Screenshot capture of a selected region
3. OCR text extraction from the captured region
4. Saving and loading of screenshots
"""
import os
import sys
import logging
from PIL import Image

# Add the project root to the Python path so we can import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QLabel, QPushButton, QWidget, QTextEdit, \
    QMessageBox
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt

# Import required services
from src.domain.services.i_logger_service import ILoggerService
from src.infrastructure.logging.logger_service import ConsoleLoggerService
from src.infrastructure.platform.screenshot_service import QtScreenshotService
from src.infrastructure.ocr.tesseract_ocr_service import TesseractOcrService
from src.domain.common.di_container import DIContainer
from src.infrastructure.threading.qt_background_task_service import QtBackgroundTaskService
from src.presentation.components.qt_region_selector import select_region_qt


class ScreenshotTestWindow(QMainWindow):
    """Test window for screenshot functionality."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Screenshot Testing")
        self.resize(800, 600)

        # Setup services
        self.setup_services()

        # Setup UI
        self.setup_ui()

        # Selected region
        self.selected_region = None
        self.captured_screenshot = None

    def setup_services(self):
        """Initialize the required services."""
        # Create a container for dependency injection
        self.container = DIContainer()

        # Setup logger
        self.logger = ConsoleLoggerService(level=logging.DEBUG)
        self.container.register_instance(ILoggerService, self.logger)

        # Setup screenshot service
        self.screenshot_service = QtScreenshotService(self.logger)

        # Setup OCR service
        self.ocr_service = TesseractOcrService(self.logger)

        # Setup thread service
        self.thread_service = QtBackgroundTaskService(self.logger)

    def setup_ui(self):
        """Set up the user interface."""
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Layout
        layout = QVBoxLayout(central_widget)

        # Region selection button
        self.select_region_btn = QPushButton("Select Region")
        self.select_region_btn.clicked.connect(self.on_select_region)
        layout.addWidget(self.select_region_btn)


        # OCR button
        self.ocr_btn = QPushButton("Extract Text from Screenshot")
        self.ocr_btn.clicked.connect(self.on_extract_text)
        self.ocr_btn.setEnabled(False)  # Disabled until screenshot is captured
        layout.addWidget(self.ocr_btn)

        # Save screenshot button
        self.save_btn = QPushButton("Save Screenshot")
        self.save_btn.clicked.connect(self.on_save_screenshot)
        self.save_btn.setEnabled(False)  # Disabled until screenshot is captured
        layout.addWidget(self.save_btn)

        # Region info label
        self.region_label = QLabel("No region selected")
        layout.addWidget(self.region_label)

        # Screenshot display label
        self.screenshot_label = QLabel("No screenshot captured")
        self.screenshot_label.setAlignment(Qt.AlignCenter)
        self.screenshot_label.setMinimumHeight(200)
        self.screenshot_label.setStyleSheet("border: 1px solid #ccc")
        layout.addWidget(self.screenshot_label)

        # Text output
        self.text_output = QTextEdit()
        self.text_output.setReadOnly(True)
        self.text_output.setMinimumHeight(200)
        layout.addWidget(self.text_output)

        # Status button
        self.status_btn = QPushButton("Check Status")
        self.status_btn.clicked.connect(self.on_check_status)
        layout.addWidget(self.status_btn)

    def on_select_region(self):
        """Handle region selection and immediately capture screenshot."""
        self.log_message("Starting region selection...")

        # Use the QtRegionSelector to select a region
        region = select_region_qt("Select a region to monitor")

        if region:
            self.selected_region = region
            self.log_message(f"Region selected: {region}")
            self.region_label.setText(f"Selected region: {region}")

            # Automatically capture screenshot immediately after selection
            self.log_message("Automatically capturing screenshot of selected region...")

            # Capture the screenshot
            result = self.screenshot_service.capture_region(self.selected_region)

            if result.is_success:
                self.captured_screenshot = result.value
                self.log_message("Screenshot captured successfully")

                # Convert to QPixmap and display
                pixmap_result = self.screenshot_service.to_pyside_pixmap(self.captured_screenshot)
                if pixmap_result.is_success:
                    pixmap = pixmap_result.value
                    self.screenshot_label.setPixmap(pixmap.scaled(
                        self.screenshot_label.width(),
                        self.screenshot_label.height(),
                        Qt.KeepAspectRatio
                    ))
                    self.ocr_btn.setEnabled(True)
                    self.save_btn.setEnabled(True)
                else:
                    self.log_message(f"Error converting to pixmap: {pixmap_result.error}")
            else:
                self.log_message(f"Error capturing screenshot: {result.error}")
        else:
            self.log_message("Region selection cancelled")

    def on_extract_text(self):
        """Extract text from the captured screenshot."""
        if not self.captured_screenshot:
            self.log_message("Error: No screenshot captured")
            return

        self.log_message("Extracting text...")

        # Extract text using OCR
        result = self.ocr_service.extract_text(self.captured_screenshot)

        if result.is_success:
            text = result.value
            self.log_message("Text extracted successfully")
            self.text_output.setText(text)

            # Extract numeric values
            numbers_result = self.ocr_service.extract_numeric_values(text)
            if numbers_result.is_success:
                numbers = numbers_result.value
                if numbers:
                    self.log_message(f"Numeric values found: {numbers}")
                else:
                    self.log_message("No numeric values found in the text")
            else:
                self.log_message(f"Error extracting numeric values: {numbers_result.error}")
        else:
            self.log_message(f"Error extracting text: {result.error}")

    def on_save_screenshot(self):
        """Save the screenshot to a file."""
        if not self.captured_screenshot:
            self.log_message("Error: No screenshot captured")
            return

        self.log_message("Saving screenshot...")

        # Create a directory for test screenshots if it doesn't exist
        os.makedirs("test_screenshots", exist_ok=True)

        # Save the screenshot
        filename = f"test_screenshots/screenshot_{os.getpid()}_{int(os.urandom(4).hex(), 16)}.png"
        result = self.screenshot_service.save_screenshot(self.captured_screenshot, filename)

        if result.is_success:
            self.log_message(f"Screenshot saved to: {result.value}")

            # Try to open the file to verify it was saved correctly
            try:
                Image.open(result.value)
                self.log_message("Verified: Image file is valid")
            except Exception as e:
                self.log_message(f"Warning: Could not verify image file: {e}")
        else:
            self.log_message(f"Error saving screenshot: {result.error}")

    def on_check_status(self):
        """Check the status of the OCR and screenshot services."""
        status_messages = []

        # Check screenshot service
        try:
            status_messages.append("Screenshot Service: Available")
        except Exception as e:
            status_messages.append(f"Screenshot Service: Error - {e}")

        # Check OCR service
        try:
            # Check if Tesseract is configured
            ocr_path = getattr(self.ocr_service, '_tesseract_path',
                               getattr(self.ocr_service, 'tesseract_cmd', None))
            if ocr_path:
                status_messages.append(f"OCR Service: Available (Tesseract path: {ocr_path})")
            else:
                status_messages.append("OCR Service: Available (using system Tesseract)")
        except Exception as e:
            status_messages.append(f"OCR Service: Error - {e}")

        # Display status
        QMessageBox.information(self, "Service Status", "\n".join(status_messages))

    def log_message(self, message):
        """Log a message to both the UI and the logger."""
        self.logger.info(message)
        self.text_output.append(message)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ScreenshotTestWindow()
    window.show()
    sys.exit(app.exec())