# src/presentation/components/region_entry_widget.py

from typing import Tuple, Callable

# --- Qt Imports ---
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt, Slot

# --- Application Imports ---
# Import your custom button styles
from src.presentation.components.ui_components import StyledButton, DangerButton




class RegionEntryWidget(QWidget): # Renamed from RegionEntry
    """
    Widget for displaying a single flatten region entry with details and actions.
    """
    def __init__(self,
                 region_id: str, # This is the region 'name' (e.g., "Flatten_1")
                 coords_text: str, # Pass formatted coords text directly
                 preview_pixmap: 'QPixmap', # Pass the QPixmap for preview
                 on_edit: Callable[[], None], # Callback expects no args now
                 on_delete: Callable[[], None], # Callback expects no args now
                 on_flash: Callable[[], None], # Callback expects no args now
                 parent: QWidget = None):
        """
        Initialize the RegionEntryWidget.

        Args:
            region_id: The unique name/ID of the region.
            coords_text: Formatted string of coordinates "(x, y, w, h)".
            preview_pixmap: QPixmap object for the preview image (can be empty).
            on_edit: Callback function to trigger when Edit is clicked.
            on_delete: Callback function to trigger when Delete is clicked.
            on_flash: Callback function to trigger when Flash is clicked.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        # Store callbacks for button connections
        self._on_edit = on_edit
        self._on_delete = on_delete
        self._on_flash = on_flash

        # Use a vertical layout for the whole entry
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5) # Padding around the entry
        main_layout.setSpacing(4) # Spacing between elements

        # Top row with region info and buttons
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(6) # Spacing between label and buttons

        # Region info Label (Name + Coords)
        info_label = QLabel(f"{region_id}: {coords_text}")
        top_layout.addWidget(info_label, 1) # Allow label to stretch

        # Flash Button
        flash_btn = StyledButton("Flash", max_width=55)
        flash_btn.clicked.connect(self._on_flash) # Connect to internal slot
        top_layout.addWidget(flash_btn)

        # Edit button
        edit_btn = StyledButton("Edit", max_width=55)
        edit_btn.clicked.connect(self._on_edit) # Connect to internal slot
        top_layout.addWidget(edit_btn)

        # Delete button
        delete_btn = DangerButton("Delete", max_width=55)
        delete_btn.clicked.connect(self._on_delete) # Connect to internal slot
        top_layout.addWidget(delete_btn)

        # Add top row to main layout
        main_layout.addLayout(top_layout)

        # Add screenshot preview label
        self.screenshot_label = QLabel() # No default text needed if pixmap handles it
        self.screenshot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.screenshot_label.setStyleSheet(
            "border: 1px solid #ddd; background-color: #f0f0f0;"
            "min-height: 60px; max-height: 80px;" # Adjust size as needed
            "min-width: 100px;"
        )
        self.set_preview(preview_pixmap) # Set initial preview
        main_layout.addWidget(self.screenshot_label)


    def set_preview(self, pixmap: 'QPixmap'):
        """Sets or updates the preview image."""
        if pixmap and not pixmap.isNull():
             # Scale pixmap to fit the label while preserving aspect ratio
             # Use a reasonable fixed width for scaling consistency if needed
             # Or scale based on label size, which might vary slightly.
             scaled_pixmap = pixmap.scaled(
                 # self.screenshot_label.width() - 4, # Scale to current width
                 150, # Or scale to fixed width
                 self.screenshot_label.maximumHeight() - 4, # Scale to max height
                 Qt.AspectRatioMode.KeepAspectRatio,
                 Qt.TransformationMode.SmoothTransformation
             )
             self.screenshot_label.setPixmap(scaled_pixmap)
             self.screenshot_label.setText("") # Clear placeholder text
        else:
             self.screenshot_label.setPixmap(QPixmap()) # Clear image
             self.screenshot_label.setText("No Preview")


    # Internal slots to call the callbacks passed during initialization
    @Slot()
    def _on_edit(self):
        if self._on_edit: self._on_edit()

    @Slot()
    def _on_delete(self):
        if self._on_delete: self._on_delete()

    @Slot()
    def _on_flash(self):
        if self._on_flash: self._on_flash()