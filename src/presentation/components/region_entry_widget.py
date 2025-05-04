# src/presentation/components/region_entry_widget.py

from typing import Tuple, Callable

# --- Qt Imports ---
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt, Slot, Signal
from PySide6.QtGui import QPixmap

# --- Application Imports ---
# Import your custom button styles
from src.presentation.components.ui_components import StyledButton, DangerButton, SecondaryButton




class RegionEntryWidget(QWidget):
    """
    Widget for displaying a single flatten region entry with details and actions.
    Emits signals when action buttons are clicked.
    """
    # --- Define explicit signals ---
    delete_requested = Signal(str) # Emits region_id string
    edit_requested = Signal(str)   # Emits region_id string
    flash_requested = Signal(str)  # Emits region_id string
    # --- End signal definition ---

    def __init__(self,
                 region_id: str, # This is the region 'name'
                 coords_text: str, # Pass formatted coords text directly
                 preview_pixmap: 'QPixmap', # Pass the QPixmap for preview
                 # REMOVED CALLBACK ARGUMENTS: on_edit, on_delete, on_flash
                 parent: QWidget = None):
        """
        Initialize the RegionEntryWidget.

        Args:
            region_id: The unique name/ID of the region.
            coords_text: Formatted string of coordinates "(x, y, w, h)".
            preview_pixmap: QPixmap object for the preview image (can be empty).
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._region_id = region_id # Store the region ID

        # --- UI Setup ---
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
        flash_btn = SecondaryButton("Flash", max_width=55) # Changed to SecondaryButton for consistency? Or keep StyledButton
        # Connect directly to the internal slot that emits the new signal
        flash_btn.clicked.connect(self._emit_flash_requested)
        top_layout.addWidget(flash_btn)

        # Edit button
        edit_btn = StyledButton("Edit", max_width=55)
        edit_btn.clicked.connect(self._emit_edit_requested)
        top_layout.addWidget(edit_btn)

        # Delete button
        delete_btn = DangerButton("Delete", max_width=55)
        delete_btn.clicked.connect(self._emit_delete_requested)
        top_layout.addWidget(delete_btn)

        # Add top row to main layout
        main_layout.addLayout(top_layout)

        # Add screenshot preview label
        self.screenshot_label = QLabel() # No default text needed if pixmap handles it
        self.screenshot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.screenshot_label.setMaximumHeight(60) # Give it a max height for preview scaling
        self.screenshot_label.setMinimumHeight(40)
        self.set_preview(preview_pixmap) # Set initial preview
        main_layout.addWidget(self.screenshot_label)

    def set_preview(self, pixmap: 'QPixmap'):
        """Sets or updates the preview image."""
        if pixmap and not pixmap.isNull():
             # Scale pixmap to fit the label while preserving aspect ratio
             scaled_pixmap = pixmap.scaled(
                 150, # Max width for preview
                 self.screenshot_label.maximumHeight() - 4, # Use max height for scaling
                 Qt.AspectRatioMode.KeepAspectRatio,
                 Qt.TransformationMode.SmoothTransformation
             )
             self.screenshot_label.setPixmap(scaled_pixmap)
             self.screenshot_label.setText("") # Clear placeholder text
        else:
             self.screenshot_label.setPixmap(QPixmap()) # Clear image
             self.screenshot_label.setText("No Preview")

    # --- Internal slots to emit the new signals ---
    @Slot()
    def _emit_edit_requested(self):
        """Emits the edit_requested signal with the stored region ID."""
        self.edit_requested.emit(self._region_id)

    @Slot()
    def _emit_delete_requested(self):
        """Emits the delete_requested signal with the stored region ID."""
        self.delete_requested.emit(self._region_id)

    @Slot()
    def _emit_flash_requested(self):
        """Emits the flash_requested signal with the stored region ID."""
        self.flash_requested.emit(self._region_id)