#!/usr/bin/env python3
"""
Main script for the QtBackgroundTaskService test application.

This script sets up and runs the thread testing application.
"""
import sys
from PySide6.QtWidgets import QApplication

# Import the test window
from test_appOLD import ThreadTestWindow

if __name__ == "__main__":
    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("QtBackgroundTaskService Test")

    # Create and show main window
    window = ThreadTestWindow()
    window.show()

    # Start the event loop
    sys.exit(app.exec())