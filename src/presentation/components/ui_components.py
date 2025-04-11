"""
Standardized UI components for consistent look and feel.

Button usage guide:
- StyledButton: Standard blue button for regular actions
- ActionButton: Green button for positive/confirmation actions
- WarningButton: Orange button for cautious actions
- DangerButton: Red button for destructive/irreversible actions
- SecondaryButton: Light gray button for secondary/cancel actions
"""

from PySide6.QtWidgets import QPushButton, QLabel, QGroupBox, QTextEdit
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QIcon
import time

class StyledButton(QPushButton):
    """Standard blue button for regular actions."""
    def __init__(self, text, parent=None, icon=None, max_width=None):
        super().__init__(text, parent)

        # Set icon if provided
        if icon:
            self.setIcon(QIcon(icon))

        # Set maximum width if provided
        if max_width:
            self.setMaximumWidth(max_width)

        # Use minimal styling to preserve original size
        self.setStyleSheet("""
            QPushButton {
                background-color: #3a7ca5;
                color: white;
            }
            QPushButton:hover {
                background-color: #2a6b94;
            }
            QPushButton:pressed {
                background-color: #1a5a83;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #888888;
            }
        """)

    def set_loading(self, is_loading=True):
        """Set button to loading state (disabled + loading text)."""
        self.setDisabled(is_loading)
        if is_loading:
            self._original_text = self.text()
            self.setText("Loading...")
        else:
            if hasattr(self, '_original_text'):
                self.setText(self._original_text)


class ActionButton(QPushButton):
    """Green button for positive actions like saving or confirming."""
    def __init__(self, text, parent=None, icon=None, max_width=None):
        super().__init__(text, parent)

        if icon:
            self.setIcon(QIcon(icon))

        if max_width:
            self.setMaximumWidth(max_width)

        self.setStyleSheet("""
            QPushButton {
                background-color: #5cb85c;
                color: white;
            }
            QPushButton:hover {
                background-color: #4cae4c;
            }
            QPushButton:pressed {
                background-color: #3c903c;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #888888;
            }
        """)


class WarningButton(QPushButton):
    """Orange button for actions that need caution."""
    def __init__(self, text, parent=None, icon=None, max_width=None):
        super().__init__(text, parent)

        if icon:
            self.setIcon(QIcon(icon))

        if max_width:
            self.setMaximumWidth(max_width)

        self.setStyleSheet("""
            QPushButton {
                background-color: #f0ad4e;
                color: white;
            }
            QPushButton:hover {
                background-color: #eea236;
            }
            QPushButton:pressed {
                background-color: #de9226;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #888888;
            }
        """)


class DangerButton(QPushButton):
    """Red button for destructive actions like delete."""
    def __init__(self, text, parent=None, icon=None, max_width=None):
        super().__init__(text, parent)

        if icon:
            self.setIcon(QIcon(icon))

        if max_width:
            self.setMaximumWidth(max_width)

        self.setStyleSheet("""
            QPushButton {
                background-color: #d9534f;
                color: white;
            }
            QPushButton:hover {
                background-color: #c9302c;
            }
            QPushButton:pressed {
                background-color: #b92c28;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #888888;
            }
        """)


class SecondaryButton(QPushButton):
    """Light gray button for secondary or cancel actions."""
    def __init__(self, text, parent=None, icon=None, max_width=None):
        super().__init__(text, parent)

        if icon:
            self.setIcon(QIcon(icon))

        if max_width:
            self.setMaximumWidth(max_width)

        self.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                color: #333333;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
            QPushButton:pressed {
                background-color: #d0d0d0;
            }
            QPushButton:disabled {
                background-color: #f5f5f5;
                color: #aaaaaa;
            }
        """)


class GroupHeader(QGroupBox):
    """Standard group box with consistent styling."""
    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        self.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #cccccc;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 5px;
            }
        """)


class LogDisplay(QTextEdit):
    """Custom text display for logging messages with colors."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMinimumHeight(200)
        self.color_map = {
            "INFO": "white",         # Changed from "black"
            "SUCCESS": "green",
            "WARNING": "red",
            "ERROR": "#8B008B",     # Changed from "red" to dark magenta hex
            "DEBUG": "gray"
        }

    def append_message(self, message: str, level: str = "INFO"):
        """Append a message with the appropriate color based on level."""
        color = self.color_map.get(level.upper(), "black")

        timestamp = time.strftime("%H:%M:%S")
        formatted_message = f"<span style='color:{color};'>[{timestamp} {level}] {message}</span>"
        self.append(formatted_message)

        # Ensure the latest message is visible
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.setTextCursor(cursor)