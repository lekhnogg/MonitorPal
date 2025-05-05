# src/presentation/components/ui_components.py
"""
Standardized UI components for consistent look and feel.
Components set a 'class' property for QSS styling.
Icons are automatically colored based on button type.
"""

import re
from PySide6.QtWidgets import QPushButton, QLabel, QGroupBox, QTextEdit
from PySide6.QtCore import Qt, QSize, QByteArray, QFile, QIODevice
from PySide6.QtGui import QTextCursor, QIcon, QColor, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer # Import QSvgRenderer
import time
import html

# --- Icon Coloring Helper Function ---
# Moved here for encapsulation within the components module

def create_colored_svg_icon(svg_resource_path: str, color: QColor, size: QSize = QSize(14, 14)) -> QIcon:
    """
    Loads an SVG from Qt resources, replaces 'currentColor' with the
    specified color, renders it to a QPixmap, and returns a QIcon.

    Args:
        svg_resource_path: Path to the SVG in Qt resources (e.g., ":/icons/icon.svg").
        color: The QColor to apply to the icon.
        size: The desired QSize for the icon pixmap.

    Returns:
        A QIcon containing the colored pixmap.
    """
    icon = QIcon() # Start with an empty icon

    # Read the SVG data from resources
    file = QFile(svg_resource_path)
    if not file.open(QIODevice.OpenModeFlag.ReadOnly | QIODevice.OpenModeFlag.Text):
        print(f"Error: Could not open resource file: {svg_resource_path}")
        return icon # Return empty icon

    svg_data_bytes = file.readAll()
    file.close()

    if not svg_data_bytes:
        print(f"Error: Resource file is empty: {svg_resource_path}")
        return icon

    try:
        # Decode to string (assuming UTF-8)
        svg_content = svg_data_bytes.data().decode('utf-8')

        # --- Replace "currentColor" with the target color hex string ---
        color_hex = color.name() # e.g., "#ffffff"
        pattern = re.compile(r'(stroke|fill)=["\']currentColor["\']', re.IGNORECASE)
        modified_svg_content = pattern.sub(fr'\1="{color_hex}"', svg_content)

        if modified_svg_content == svg_content:
             # Fallback: If currentColor isn't found, try replacing common default colors
             # like black (#000, #000000) if the target color isn't black itself.
             if color != Qt.GlobalColor.black:
                  pattern_black = re.compile(r'(stroke|fill)=["\'](#000000|#000|black)["\']', re.IGNORECASE)
                  modified_svg_content = pattern_black.sub(fr'\1="{color_hex}"', modified_svg_content)

             if modified_svg_content == svg_content: # Still no change? Log warning.
                 print(f"Warning: Could not find 'currentColor' or common defaults to replace in {svg_resource_path}. Icon might not be colored.")

        # --- Render the modified SVG ---
        renderer = QSvgRenderer(QByteArray(modified_svg_content.encode('utf-8')))
        if not renderer.isValid():
             print(f"Error: Modified SVG data is invalid for {svg_resource_path}")
             return icon # Return empty icon

        # Create pixmap to render onto
        pixmap = QPixmap(size) # Render at the target size
        pixmap.fill(Qt.GlobalColor.transparent) # Start transparent

        # Paint the rendered SVG onto the pixmap
        painter = QPainter(pixmap)
        # Ensure aspect ratio is maintained and rendering is smooth
        renderer.render(painter, pixmap.rect())
        painter.end()

        # Create QIcon from the colored pixmap
        icon = QIcon(pixmap)

    except Exception as e:
        print(f"Error processing SVG {svg_resource_path}: {e}") # Add logging

    return icon

# --- Base Class for Consistent Icon Handling (Optional but good practice) ---

class BaseStyledButton(QPushButton):
    """Base class for buttons with consistent styling and icon handling."""
    ICON_COLOR = QColor("#2d3436") # Default: Dark text color
    ICON_SIZE = QSize(14, 14)      # Default: Icon size

    def __init__(self, text, css_class: str, icon_path: str = None, parent=None, max_width=None):
        super().__init__(text, parent)
        self.setProperty("class", css_class)
        if icon_path:
            self.update_icon(icon_path) # Use helper method
        if max_width:
            self.setMaximumWidth(max_width)

    def update_icon(self, svg_resource_path: str):
        """Sets the button icon using the colored icon helper."""
        colored_icon = create_colored_svg_icon(svg_resource_path, self.ICON_COLOR, self.ICON_SIZE)
        self.setIcon(colored_icon)
        self.setIconSize(self.ICON_SIZE) # Ensure button respects the size

    def set_loading(self, is_loading=True):
        """Set button to loading state (disabled + loading text)."""
        # (Keep existing implementation from StyledButton)
        self.setDisabled(is_loading)
        if is_loading:
            if not hasattr(self, '_original_text') or self._original_text is None:
                 self._original_text = self.text()
            self.setText("Loading...")
        else:
            if hasattr(self, '_original_text') and self._original_text is not None:
                self.setText(self._original_text)
                self._original_text = None


# --- Specific Button Types ---

class StyledButton(BaseStyledButton):
    """Standard blue button for regular actions. Sets class='styled'."""
    ICON_COLOR = QColor("#3498db") # Blue Icon

    def __init__(self, text, parent=None, icon=None, max_width=None):
        super().__init__(text, "styled", icon_path=icon, parent=parent, max_width=max_width)


class ActionButton(BaseStyledButton):
    """Green button for positive actions. Sets class='action'."""
    ICON_COLOR = QColor("#27ae60") # Green Icon

    def __init__(self, text, parent=None, icon=None, max_width=None):
        super().__init__(text, "action", icon_path=icon, parent=parent, max_width=max_width)


class WarningButton(BaseStyledButton):
    """Orange button for actions that need caution. Sets class='warning'."""
    ICON_COLOR = QColor("#f39c12") # Orange Icon

    def __init__(self, text, parent=None, icon=None, max_width=None):
        super().__init__(text, "warning", icon_path=icon, parent=parent, max_width=max_width)


class DangerButton(BaseStyledButton):
    """Red button for destructive actions. Sets class='danger'."""
    ICON_COLOR = QColor("#e74c3c") # Red Icon

    def __init__(self, text, parent=None, icon=None, max_width=None):
        super().__init__(text, "danger", icon_path=icon, parent=parent, max_width=max_width)


class SecondaryButton(BaseStyledButton):
    """Light gray button for secondary/cancel actions. Sets class='secondary'."""
    ICON_COLOR = QColor("#34495e") # Dark Gray/Blue Icon (Keep as is or adjust)

    def __init__(self, text, parent=None, icon=None, max_width=None):
        super().__init__(text, "secondary", icon_path=icon, parent=parent, max_width=max_width)


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
        self.setMinimumHeight(200)
        self.setObjectName("logDisplay")

        self.color_map = {
            "INFO": "#2980b9", "SUCCESS": "#27ae60", "WARNING": "#f39c12",
            "ERROR": "#e74c3c", "DEBUG": "#7f8c8d"
        }

    def append_message(self, message: str, level: str = "INFO"):
        """Append a message with explicit newline control."""
        color = self.color_map.get(level.upper(), "#cfd8dc") # Default to light text color from QSS
        timestamp = time.strftime("%H:%M:%S")
        escaped_message = html.escape(message)

        # Use inline styles for colors within the HTML
        formatted_html = f"""
        <p style="margin-bottom: 0px; margin-top: 0px; color: #cfd8dc;"> <!-- Base color -->
            <span style="color:#7f8c8d;">[{timestamp}]</span>
            <span style="color:{color}; font-weight:bold;"> [{level.upper()}]</span> <!-- Level color -->
            <span> {escaped_message}</span> <!-- Message uses base color -->
        </p>
        """

        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        # Insert block separator if not the first block
        if cursor.blockNumber() > 0 or self.document().characterCount() > 0 :
             cursor.insertBlock()

        # Insert the actual formatted message
        cursor.insertHtml(formatted_html)

        # Ensure the view scrolls down
        self.ensureCursorVisible()