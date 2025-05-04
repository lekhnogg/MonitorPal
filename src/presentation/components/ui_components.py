# src/presentation/components/ui_components.py
"""
Standardized UI components for consistent look and feel.
Components set a 'class' property for QSS styling.
"""

from PySide6.QtWidgets import QPushButton, QLabel, QGroupBox, QTextEdit
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QIcon
import time

# StyleManager import might become unnecessary here if components
# no longer apply any styles directly. Keep if used elsewhere or remove.
# from src.presentation.styles.style_manager import StyleManager

class StyledButton(QPushButton):
    """Standard blue button for regular actions. Sets class='styled'."""

    def __init__(self, text, parent=None, icon=None, max_width=None):
        super().__init__(text, parent)

        # Use 'class' property for QSS styling based on button type
        self.setProperty("class", "styled")
        # Keep objectName if you need to target THIS specific instance later
        # self.setObjectName("styledButton") # Optional: usually not needed for type styling

        # Set icon if provided
        if icon:
            self.setIcon(QIcon(icon))

        # Set maximum width if provided
        if max_width:
            self.setMaximumWidth(max_width)


    def set_loading(self, is_loading=True):
        """Set button to loading state (disabled + loading text)."""
        self.setDisabled(is_loading)
        if is_loading:
            # Check if original text already stored to prevent overwrite on rapid calls
            if not hasattr(self, '_original_text') or self._original_text is None:
                 self._original_text = self.text()
            self.setText("Loading...")
        else:
            # Restore only if original text was stored
            if hasattr(self, '_original_text') and self._original_text is not None:
                self.setText(self._original_text)
                self._original_text = None # Clear stored text
        # Note: Disabled state style should be handled by QSS QPushButton:disabled {}


class ActionButton(QPushButton):
    """Green button for positive actions. Sets class='action'."""

    def __init__(self, text, parent=None, icon=None, max_width=None):
        super().__init__(text, parent)
        self.setProperty("class", "action")
        # self.setObjectName("actionButton") # Optional

        if icon:
            self.setIcon(QIcon(icon))
        if max_width:
            self.setMaximumWidth(max_width)


class WarningButton(QPushButton):
    """Orange button for actions that need caution. Sets class='warning'."""

    def __init__(self, text, parent=None, icon=None, max_width=None):
        super().__init__(text, parent)
        self.setProperty("class", "warning")
        # self.setObjectName("warningButton") # Optional

        if icon:
            self.setIcon(QIcon(icon))
        if max_width:
            self.setMaximumWidth(max_width)


class DangerButton(QPushButton):
    """Red button for destructive actions. Sets class='danger'."""

    def __init__(self, text, parent=None, icon=None, max_width=None):
        super().__init__(text, parent)
        self.setProperty("class", "danger")
        # self.setObjectName("dangerButton") # Optional

        if icon:
            self.setIcon(QIcon(icon))
        if max_width:
            self.setMaximumWidth(max_width)


class SecondaryButton(QPushButton):
    """Light gray button for secondary/cancel actions. Sets class='secondary'."""

    def __init__(self, text, parent=None, icon=None, max_width=None):
        super().__init__(text, parent)
        self.setProperty("class", "secondary")
        # self.setObjectName("secondaryButton") # Optional

        if icon:
            self.setIcon(QIcon(icon))
        if max_width:
            self.setMaximumWidth(max_width)


class GroupHeader(QGroupBox):
    """Standard group box with consistent styling."""

    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        # Styling comes entirely from application.qss targeting QGroupBox


class LogDisplay(QTextEdit):
    """Custom text display for logging messages with colors."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMinimumHeight(200) # Keep minimum height setting
        self.setObjectName("logDisplay") # Set object name for specific targeting if needed

        # HTML styling for colors is separate from QSS background/font/border
        self.color_map = {
            "INFO": "#2980b9",  # Blue
            "SUCCESS": "#27ae60",  # Green
            "WARNING": "#f39c12",  # Orange
            "ERROR": "#e74c3c",  # Red
            "DEBUG": "#7f8c8d"  # Gray
        }
        # Base font/background etc. will be set by QSS rule for #logDisplay or QTextEdit

    def append_message(self, message: str, level: str = "INFO"):
        """Append a message with explicit newline control."""
        color = self.color_map.get(level.upper(), "#cfd8dc")
        timestamp = time.strftime("%H:%M:%S")

        import html
        escaped_message = html.escape(message)

        formatted_html = f"""
        <p style="margin-bottom: 0px; margin-top: 0px;">
            <span style="color:#7f8c8d;">[{timestamp}]</span>
            <span style="color:{color}; font-weight:bold;"> [{level}]</span>
            <span style="color:#cfd8dc;"> {escaped_message}</span>
        </p>
        """

        # Move cursor to the end
        self.moveCursor(QTextCursor.MoveOperation.End)

        # --- Check if not the very first line ---
        # If the document isn't empty, insert a paragraph break *before* the new content.
        # textCursor().blockNumber() > 0 checks if there's more than one block (line).
        # Alternatively, check if last character is already newline? Less reliable.
        if self.document().blockCount() > 1 or self.toPlainText(): # Check if not empty
             self.textCursor().insertBlock() # Inserts a new paragraph break

        # Insert the actual formatted message
        self.insertHtml(formatted_html)

        # Ensure the view scrolls down
        self.ensureCursorVisible()