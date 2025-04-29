# src/presentation/components/ui_components.py
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

# Import the StyleManager for component-specific styles
from src.presentation.styles.style_manager import StyleManager

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

        # Apply styling using StyleManager
        self.setStyleSheet(StyleManager.get_button_style("styled_button"))

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

        # Apply styling using StyleManager
        self.setStyleSheet(StyleManager.get_button_style("action_button"))


class WarningButton(QPushButton):
    """Orange button for actions that need caution."""
    def __init__(self, text, parent=None, icon=None, max_width=None):
        super().__init__(text, parent)

        if icon:
            self.setIcon(QIcon(icon))

        if max_width:
            self.setMaximumWidth(max_width)

        # Apply styling using StyleManager
        self.setStyleSheet(StyleManager.get_button_style("warning_button"))


class DangerButton(QPushButton):
    """Red button for destructive actions like delete."""
    def __init__(self, text, parent=None, icon=None, max_width=None):
        super().__init__(text, parent)

        if icon:
            self.setIcon(QIcon(icon))

        if max_width:
            self.setMaximumWidth(max_width)

        # Apply styling using StyleManager
        self.setStyleSheet(StyleManager.get_button_style("danger_button"))


class SecondaryButton(QPushButton):
    """Light gray button for secondary or cancel actions."""
    def __init__(self, text, parent=None, icon=None, max_width=None):
        super().__init__(text, parent)

        if icon:
            self.setIcon(QIcon(icon))

        if max_width:
            self.setMaximumWidth(max_width)

        # Apply styling using StyleManager
        self.setStyleSheet(StyleManager.get_button_style("secondary_button"))


class GroupHeader(QGroupBox):
    """Standard group box with consistent styling."""
    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        # Use default QSS styling from application.qss


class LogDisplay(QTextEdit):
    """Custom text display for logging messages with colors."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMinimumHeight(200)

        # Apply styling using StyleManager
        self.setStyleSheet(StyleManager.get_component_style("log_display"))

        self.color_map = {
            "INFO": "#2980b9",      # Blue
            "SUCCESS": "#27ae60",   # Green
            "WARNING": "#f39c12",   # Orange
            "ERROR": "#e74c3c",     # Red
            "DEBUG": "#7f8c8d"      # Gray
        }

    def append_message(self, message: str, level: str = "INFO"):
        """Append a message with the appropriate color based on level."""
        color = self.color_map.get(level.upper(), "#2d3436")  # Default to dark gray

        # Format with timestamp for better readability
        timestamp = time.strftime("%H:%M:%S")

        # HTML formatting for better visual structure
        formatted_html = f"""
        <div style="margin: 2px 0;">
            <span style="color: #7f8c8d; font-size: 8pt;">[{timestamp}]</span>
            <span style="color: {color}; font-weight: bold;">[{level}]</span>
            <span style="color: #2d3436;"> {message}</span>
        </div>
        """
        self.append(formatted_html)

        # Ensure the latest message is visible
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.setTextCursor(cursor)