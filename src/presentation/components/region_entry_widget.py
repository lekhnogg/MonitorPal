# src/presentation/components/region_entry_widget.py

from typing import Tuple, Callable

# --- Qt Imports ---
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt, Slot, Signal
from PySide6.QtGui import QPixmap

# --- Application Imports ---
# Import your custom button styles
from src.presentation.components.ui_components import StyledButton, DangerButton, SecondaryButton


class RegionEntryWidget(QWidget):
    """
    Enhanced widget for displaying a single flatten region entry with details and actions.
    Styled to match the modern dashboard design.
    """
    # Keep original signals
    delete_requested = Signal(str)
    edit_requested = Signal(str)
    flash_requested = Signal(str)

    def __init__(self,
                 region_id: str,
                 coords_text: str,
                 preview_pixmap: 'QPixmap',
                 parent: QWidget = None):
        """Initialize the RegionEntryWidget with modern styling."""
        super().__init__(parent)
        self._region_id = region_id

        # Create a card-like container
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Main widget container
        container = QFrame(self)
        container.setObjectName("regionEntryContainer")
        container.setProperty("class", "regionEntry")
        container.setFrameShape(QFrame.Shape.StyledPanel)
        container.setFrameShadow(QFrame.Shadow.Raised)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # 1. Header with name and expand/collapse button
        header = QWidget()
        header.setObjectName("regionEntryHeader")
        header.setProperty("class", "regionEntryHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 8, 10, 8)
        header_layout.setSpacing(6)

        # Region name
        name_label = QLabel(region_id)
        name_label.setObjectName("regionEntryName")
        name_label.setProperty("class", "regionEntryName")
        header_layout.addWidget(name_label, 1)

        # Coordinates
        coords_label = QLabel(coords_text)
        coords_label.setObjectName("regionEntryCoords")
        coords_label.setProperty("class", "regionEntryCoords")
        coords_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header_layout.addWidget(coords_label)

        container_layout.addWidget(header)

        # 2. Preview area
        preview_container = QWidget()
        preview_container.setObjectName("previewContainer")
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(10, 0, 10, 10)

        self.screenshot_label = QLabel()
        self.screenshot_label.setObjectName("regionEntryPreview")
        self.screenshot_label.setProperty("class", "regionEntryPreview")
        self.screenshot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.screenshot_label.setFixedHeight(40)
        preview_layout.addWidget(self.screenshot_label)

        # Set the preview
        self.set_preview(preview_pixmap)

        container_layout.addWidget(preview_container)

        # 3. Action buttons
        actions_container = QWidget()
        actions_container.setObjectName("actionsContainer")
        actions_layout = QHBoxLayout(actions_container)
        actions_layout.setContentsMargins(10, 0, 10, 10)
        actions_layout.setSpacing(6)

        # Use smaller buttons to save space
        flash_btn = SecondaryButton("Flash", icon=":/icons/zap.svg")
        flash_btn.setObjectName("flashRegionBtn")
        flash_btn.clicked.connect(self._emit_flash_requested)

        edit_btn = StyledButton("Edit", icon=":/icons/edit.svg")
        edit_btn.setObjectName("editRegionBtn")
        edit_btn.clicked.connect(self._emit_edit_requested)

        delete_btn = DangerButton("Delete", icon=":/icons/trash.svg")
        delete_btn.setObjectName("deleteRegionBtn")
        delete_btn.clicked.connect(self._emit_delete_requested)

        # Add spacers and buttons
        actions_layout.addStretch(1)
        actions_layout.addWidget(flash_btn)
        actions_layout.addWidget(edit_btn)
        actions_layout.addWidget(delete_btn)

        container_layout.addWidget(actions_container)

        # Add the container to the main layout
        main_layout.addWidget(container)

    def set_preview(self, pixmap: 'QPixmap'):
        """Sets or updates the preview image."""
        if pixmap and not pixmap.isNull():
            scaled_pixmap = pixmap.scaled(
                150,
                self.screenshot_label.height() - 4,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.screenshot_label.setPixmap(scaled_pixmap)
            self.screenshot_label.setText("")
        else:
            self.screenshot_label.setPixmap(QPixmap())
            self.screenshot_label.setText("No Preview")

    # Keep existing signal emitter methods
    @Slot()
    def _emit_edit_requested(self):
        self.edit_requested.emit(self._region_id)

    @Slot()
    def _emit_delete_requested(self):
        self.delete_requested.emit(self._region_id)

    @Slot()
    def _emit_flash_requested(self):
        self.flash_requested.emit(self._region_id)