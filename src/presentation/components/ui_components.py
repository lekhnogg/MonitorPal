# src/presentation/components/ui_components.py
"""
Standardized UI components for consistent look and feel.
Components set a 'class' property for QSS styling.
Icons are automatically colored based on button type.
"""

import re
from PySide6.QtWidgets import QPushButton, QLabel, QGroupBox, QTextEdit, QSizePolicy, QComboBox, QFrame
from PySide6.QtCore import Qt, QSize, QByteArray, QFile, QIODevice, QTimer, QEvent, QPoint
from PySide6.QtGui import QTextCursor, QIcon, QColor, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer # Import QSvgRenderer
import time
import html

# --- Icon Coloring Helper Function ---
# Moved here for encapsulation within the components module

def create_colored_svg_icon(svg_resource_path: str, color: QColor, size: QSize = QSize(14, 14)) -> QIcon:
    """Creates a colored SVG icon with comprehensive color replacement."""
    icon = QIcon()
    color_hex = color.name()

    # First check if file exists
    if not QFile.exists(svg_resource_path):
        print(f"Error: SVG file not found: {svg_resource_path}")
        return icon

    # Read SVG data
    file = QFile(svg_resource_path)
    if not file.open(QIODevice.OpenModeFlag.ReadOnly | QIODevice.OpenModeFlag.Text):
        print(f"Error: Could not open resource file: {svg_resource_path}")
        return icon

    svg_data_bytes = file.readAll()
    file.close()

    try:
        svg_content = svg_data_bytes.data().decode('utf-8')

        # Store original for comparison
        original_content = svg_content

        # Handle multiple color formats
        replacements = [
            # Handle currentColor
            (r'(stroke|fill)=["\']currentColor["\']', fr'\1="{color_hex}"'),
            # Handle fill="#000" format
            (r'(fill|stroke)=["\'](#000000|#000|black)["\']', fr'\1="{color_hex}"'),
            # Handle style="fill:#000" format
            (r'style=["\']([^"\']*)(fill|stroke):(#000000|#000|black)([^"\']*)["\']', fr'style="\1\2:{color_hex}\4"'),
            # Handle rgb format
            (r'(fill|stroke)=["\'](rgb\(\s*0\s*,\s*0\s*,\s*0\s*\))["\']', fr'\1="{color_hex}"'),
            # Handle rgba format
            (r'(fill|stroke)=["\'](rgba\(\s*0\s*,\s*0\s*,\s*0\s*,\s*[0-9.]+\s*\))["\']', fr'\1="{color_hex}"')
        ]

        # Apply all replacements
        for pattern, replacement in replacements:
            svg_content = re.sub(pattern, replacement, svg_content)

        # Debug: Check if any substitutions were made
        if svg_content == original_content:
            print(f"Warning: No color substitutions made in SVG: {svg_resource_path}")
            # If critical (like logo), you could add more detailed logging here
            # Add sample of SVG content: print(f"SVG content sample: {svg_content[:100]}...")

        # Render SVG
        renderer = QSvgRenderer(QByteArray(svg_content.encode('utf-8')))
        if not renderer.isValid():
            print(f"Error: Modified SVG data is invalid for {svg_resource_path}")
            return icon

        # Create pixmap with transparent background
        pixmap = QPixmap(size)
        pixmap.fill(Qt.GlobalColor.transparent)

        # Paint SVG onto pixmap
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()

        return QIcon(pixmap)

    except Exception as e:
        print(f"Error processing SVG {svg_resource_path}: {e}")
        return icon
# --- Base Class for Consistent Icon Handling (Optional but good practice) ---

class BaseStyledButton(QPushButton):
    """Base class for buttons with consistent styling and theme-aware icon handling."""
    # These will now be default/fallback or light theme colors
    # LIGHT_THEME_ICON_COLOR = QColor("#2d3436") # Example default
    # DARK_THEME_ICON_COLOR = QColor("#f0f0f0")   # Example default
    ICON_SIZE = QSize(14, 14)

    def __init__(self, text: str, css_class: str,
                 light_theme_icon_color: QColor,
                 dark_theme_icon_color: QColor,
                 icon_path: str | None = None, parent=None):
        super().__init__(text, parent)
        self.setProperty("class", css_class)
        self._icon_resource_path = icon_path
        self._light_theme_icon_color = light_theme_icon_color
        self._dark_theme_icon_color = dark_theme_icon_color

        if self._icon_resource_path:
            # Initial icon setup. The 'darkTheme' property might not be set on `self` yet,
            # so we might need a slight delay or rely on the first StyleChange event.
            # For simplicity, let's try an initial call; StyleChange will correct it.
            self._refresh_icon_for_current_theme()

    def _refresh_icon_for_current_theme(self):
        """Re-creates and sets the icon based on the current theme property."""
        if not self._icon_resource_path:
            return

        # Determine if the widget (or its hierarchy) is in dark mode
        is_dark = False
        widget_to_check = self
        while widget_to_check:
            prop_val = widget_to_check.property("darkTheme")
            if isinstance(prop_val, bool):  # Ensure it's a boolean
                is_dark = prop_val
                break
            widget_to_check = widget_to_check.parent()

        # Fallback if no darkTheme property found up the chain (less likely with current setup)
        # if widget_to_check is None:
        #     print(f"Warning: Could not determine theme for button {self.text()}. Defaulting icon color.")

        actual_icon_color = self._dark_theme_icon_color if is_dark else self._light_theme_icon_color

        # Debugging print
        # print(f"Button '{self.text()}': Theme is_dark={is_dark}, IconColor={actual_icon_color.name()}, Path={self._icon_resource_path}")

        colored_icon = create_colored_svg_icon(self._icon_resource_path, actual_icon_color, self.ICON_SIZE)
        self.setIcon(colored_icon)
        # It's good practice to setIconSize, though often the QIcon carries this.
        # If your icons in buttons have varying actual sizes, set it explicitly.
        # Otherwise, if all button icons from create_colored_svg_icon are self.ICON_SIZE,
        # QPushButton might handle it. Let's keep it for safety.
        self.setIconSize(self.ICON_SIZE)


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

    def changeEvent(self, event: QEvent):
        """Handle style changes to refresh the icon."""
        super().changeEvent(event)
        if event.type() == QEvent.Type.StyleChange:
            # print(f"Button '{self.text()}' received StyleChange event. Refreshing icon.")
            if hasattr(self, '_icon_resource_path') and self._icon_resource_path:  # Ensure initialized
                self._refresh_icon_for_current_theme()
        elif event.type() == QEvent.Type.ParentChange:  # Also refresh if parent changes, as theme prop might come from parent
            if hasattr(self, '_icon_resource_path') and self._icon_resource_path:
                self._refresh_icon_for_current_theme()


# --- Specific Button Types (Removing max_width) ---
class StyledButton(BaseStyledButton):
    # Define theme-specific colors for the icon
    DEFAULT_LIGHT_ICON_COLOR = QColor("#3498db") # Blue for light theme
    DEFAULT_DARK_ICON_COLOR  = QColor("#5dade2") # Lighter blue for dark theme
    def __init__(self, text, parent=None, icon=None):
        super().__init__(text, "styled",
                         light_theme_icon_color=StyledButton.DEFAULT_LIGHT_ICON_COLOR,
                         dark_theme_icon_color=StyledButton.DEFAULT_DARK_ICON_COLOR,
                         icon_path=icon, parent=parent)

class ActionButton(BaseStyledButton):
    DEFAULT_LIGHT_ICON_COLOR = QColor("#27ae60") # Green for light theme
    DEFAULT_DARK_ICON_COLOR  = QColor("#2ecc71") # Brighter green for dark theme
    def __init__(self, text, parent=None, icon=None):
        super().__init__(text, "action",
                         light_theme_icon_color=ActionButton.DEFAULT_LIGHT_ICON_COLOR,
                         dark_theme_icon_color=ActionButton.DEFAULT_DARK_ICON_COLOR,
                         icon_path=icon, parent=parent)

class WarningButton(BaseStyledButton):
    DEFAULT_LIGHT_ICON_COLOR = QColor("#f39c12") # Orange for light theme
    DEFAULT_DARK_ICON_COLOR  = QColor("#f5b041") # Lighter orange for dark theme
    def __init__(self, text, parent=None, icon=None):
        super().__init__(text, "warning",
                         light_theme_icon_color=WarningButton.DEFAULT_LIGHT_ICON_COLOR,
                         dark_theme_icon_color=WarningButton.DEFAULT_DARK_ICON_COLOR,
                         icon_path=icon, parent=parent)

class DangerButton(BaseStyledButton):
    DEFAULT_LIGHT_ICON_COLOR = QColor("#e74c3c") # Red for light theme
    DEFAULT_DARK_ICON_COLOR  = QColor("#ec7063") # Lighter red for dark theme
    def __init__(self, text, parent=None, icon=None):
        super().__init__(text, "danger",
                         light_theme_icon_color=DangerButton.DEFAULT_LIGHT_ICON_COLOR,
                         dark_theme_icon_color=DangerButton.DEFAULT_DARK_ICON_COLOR,
                         icon_path=icon, parent=parent)

class SecondaryButton(BaseStyledButton):
    DEFAULT_LIGHT_ICON_COLOR = QColor("#34495e") # Dark gray/blue for light theme
    DEFAULT_DARK_ICON_COLOR  = QColor("#7f8c8d") # Lighter gray for dark theme
    def __init__(self, text, parent=None, icon=None):
        super().__init__(text, "secondary",
                         light_theme_icon_color=SecondaryButton.DEFAULT_LIGHT_ICON_COLOR,
                         dark_theme_icon_color=SecondaryButton.DEFAULT_DARK_ICON_COLOR,
                         icon_path=icon, parent=parent)

# --- Icon Button ---
class IconButton(BaseStyledButton):
    """A button primarily intended to display just an icon, text is empty."""
    ICON_SIZE = QSize(16, 16)  # Default icon size for these specific buttons, can be overridden

    # Define default icon colors - these will often be neutral as the button background is transparent/subtle
    DEFAULT_LIGHT_ICON_COLOR = QColor("#495057")  # A fairly dark gray for light theme
    DEFAULT_DARK_ICON_COLOR = QColor("#adb5bd")  # A light gray for dark theme

    def __init__(self, icon_path: str, tooltip: str = "",
                 icon_size: QSize = QSize(16, 16),
                 parent=None):
        # Remove icon_size from super() call since parent doesn't accept it
        super().__init__(
            text="",
            css_class="iconButtonBare",
            light_theme_icon_color=IconButton.DEFAULT_LIGHT_ICON_COLOR,
            dark_theme_icon_color=IconButton.DEFAULT_DARK_ICON_COLOR,
            icon_path=icon_path,
            parent=parent
        )
        # Set ICON_SIZE class variable instead
        self.ICON_SIZE = icon_size
        if tooltip:
            self.setToolTip(tooltip)

        # IconButtons often have a fixed square-ish size based on their icon + padding
        # This can be set here, or controlled by QSS min-width/min-height/padding on class "iconButtonBare"
        effective_size = icon_size.width() + 8  # Example: 4px padding around 16px icon = 24px button
        self.setFixedSize(QSize(effective_size, effective_size))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)


# --- GroupHeader ---
class GroupHeader(QGroupBox):
    def __init__(self, title, parent=None):
        super().__init__(title, parent)


# --- LogDisplay ---
class LogDisplay(QTextEdit):
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
        """Append a message with explicit newline control and auto-scroll."""
        # print(f"DEBUG: LogDisplay.append_message received: Level='{level}', Msg='{message[:50]}...'") # Keep for debugging if needed

        # --- Get Color and Timestamp ---
        color = self.color_map.get(level.upper(), "#cfd8dc")
        timestamp = time.strftime("%H:%M:%S")
        escaped_message = html.escape(message)

        # --- Format HTML with zero margins ---
        formatted_html = f"""
        <p style="margin: 0; padding: 0;">
            <span style="color:#7f8c8d;">[{timestamp}]</span>
            <span style="color:{color}; font-weight:bold;"> [{level.upper()}]</span>
            <span style="color:#cfd8dc;"> {escaped_message}</span>
        </p>
        """

        # --- Check scroll position BEFORE modifying content ---
        scrollbar = self.verticalScrollBar()
        scroll_at_bottom = scrollbar.value() >= (scrollbar.maximum() - 5)

        # --- Determine if this is the very first message ---
        is_first_message = not self.toPlainText()

        # --- Append the text using insertHtml and manual block insert ---
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        # --- Refined Block Insertion ---
        if not is_first_message:
            cursor.insertBlock() # Create a new paragraph/line if not the first message
        # --- End Refinement ---

        cursor.insertHtml(formatted_html) # Insert the actual formatted message content
        # --- End Appending ---

        # --- Force scroll if user was at the bottom OR if it's the first message ---
        if scroll_at_bottom or is_first_message:
            QTimer.singleShot(0, lambda: scrollbar.setValue(scrollbar.maximum()))
        # --- End Force Scroll ---

