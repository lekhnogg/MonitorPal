# src/presentation/views/region_setup_view.py

from typing import List, Dict, Any

# --- Qt Imports ---
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QSplitter, QListWidget,
    QListWidgetItem, QPushButton, QSizePolicy # Added QPushButton
)
from PySide6.QtCore import Slot, Qt, QSize, QTimer  # Added QSize
from PySide6.QtGui import QPixmap, QColor

from src.presentation.styles.style_manager import StyleManager
# --- Application Imports ---
from src.presentation.view_models.region_setup_view_model import RegionSetupViewModel
# Import custom UI components
from src.presentation.components.ui_components import (
    StyledButton, ActionButton, SecondaryButton, WarningButton, DangerButton, GroupHeader
)
# Import the reusable widget for displaying flatten region entries
from src.presentation.components.region_entry_widget import RegionEntryWidget


class RegionSetupView(QWidget):
    """
    View for the Region Setup tab.

    Displays controls for defining P&L and Flatten regions.
    Connects user actions to the RegionSetupViewModel.
    Updates display based on signals from the ViewModel.
    """

    def __init__(self, view_model: RegionSetupViewModel, parent: QWidget = None):
        """
        Initialize the RegionSetupView.

        Args:
            view_model: The corresponding RegionSetupViewModel instance.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.view_model = view_model
        self._setup_ui()
        self._connect_signals()
        # Schedule the VM to emit its initial state signals shortly after setup
        self.view_model._logger.debug("View: Scheduling initial UI refresh via VM.refresh_ui_signals.")
        QTimer.singleShot(0, self.view_model.refresh_ui_signals)

    def _setup_ui(self):
        """Creates and arranges the UI elements for the region setup tab."""
        # Use a QVBoxLayout instead of a Splitter
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(15) # Increased spacing between groups

        # --- Top Section: P&L Monitoring Region ---
        monitor_group = QGroupBox("P&L Monitoring Region")
        monitor_group.setObjectName("monitorRegionGroup")
        monitor_group_layout = QVBoxLayout(monitor_group)
        monitor_group_layout.setSpacing(8)

        # Preview Area - Give it a maximum height
        self.monitor_preview_label = QLabel("No Preview Available")
        self.monitor_preview_label.setObjectName("monitorPreviewLabel") # For QSS targeting
        # REMOVED: Alignment handled by QSS
        # self.monitor_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.monitor_preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred) # Expand horizontally, preferred vertically
        self.monitor_preview_label.setMaximumHeight(75) # <<<--- SET MAX HEIGHT
        self.monitor_preview_label.setMinimumHeight(50) # <<<--- SET MIN HEIGHT (optional)
        monitor_group_layout.addWidget(self.monitor_preview_label) # Don't give it stretch factor

        # Status and Coords Labels
        self.monitor_status_label = QLabel("Status: N/A")
        self.monitor_status_label.setObjectName("monitorStatusLabel") # For QSS targeting
        self.monitor_status_label.setProperty("state", "notDefined") # Initial state
        monitor_group_layout.addWidget(self.monitor_status_label)

        self.monitor_coords_label = QLabel("Coordinates: N/A")
        self.monitor_coords_label.setObjectName("monitorCoordsLabel") # Add if specific style needed
        monitor_group_layout.addWidget(self.monitor_coords_label)

        # Action Buttons
        monitor_button_layout = QHBoxLayout()
        self.define_edit_monitor_button = StyledButton("Define / Edit Region")
        self.flash_monitor_button = SecondaryButton("Flash")
        self.delete_monitor_button = DangerButton("Delete Region")

        monitor_button_layout.addWidget(self.define_edit_monitor_button)
        monitor_button_layout.addStretch()  # Push flash/delete right
        monitor_button_layout.addWidget(self.flash_monitor_button)
        monitor_button_layout.addWidget(self.delete_monitor_button)
        monitor_group_layout.addLayout(monitor_button_layout)

        # Add Monitor Group Box to the main layout
        main_layout.addWidget(monitor_group) # Added directly to main layout

        # --- Middle Section: Flatten Position Regions ---
        flatten_group = QGroupBox("Flatten Position Regions")
        flatten_group.setObjectName("flattenRegionGroup")
        flatten_group_layout = QVBoxLayout(flatten_group)
        flatten_group_layout.setSpacing(5)

        self.flatten_list_widget = QListWidget()
        self.flatten_list_widget.setObjectName("flattenListWidget") # For QSS targeting
        # Styling handled by QSS
        # self.flatten_list_widget.setSpacing(3) # Handled by QSS
        # Allow the list widget to take available vertical space
        flatten_group_layout.addWidget(self.flatten_list_widget, 1) # <<<--- ADD STRETCH FACTOR

        self.add_flatten_button = ActionButton("+ Add Region")
        flatten_group_layout.addWidget(self.add_flatten_button, 0, Qt.AlignmentFlag.AlignRight)  # Align right

        # Add Flatten Group Box to the main layout, allow it to stretch vertically
        main_layout.addWidget(flatten_group, 1) # <<<--- ADD STRETCH FACTOR

        # --- Bottom Section: Help ---
        help_group = QGroupBox("Help")
        help_group.setObjectName("helpGroup")
        help_layout = QVBoxLayout(help_group)

        help_text = QLabel(
            "1. Define a P&L monitoring region where your platform displays your current profit/loss.\n"
            "2. Add Flatten Position regions for buttons that close all your positions.\n"
            "3. Use 'Flash' to highlight regions and confirm correct placement."
        )
        help_text.setObjectName("helpText") # For QSS targeting
        help_text.setWordWrap(True)
        help_layout.addWidget(help_text)
        main_layout.addWidget(help_group) # Add help at the bottom, no stretch

    def _connect_signals(self):
        """Connect signals from widgets to ViewModel slots and vice versa."""
        self._connect_monitor_region_signals()
        self._connect_flatten_region_signals()

        # Connect ViewModel status messages (if MainView doesn't handle them globally)
        # self.view_model.status_message_changed.connect(self.parent().show_status_message) # Example

    def _connect_monitor_region_signals(self):
        # --- View -> ViewModel (Monitor Region) ---
        self.define_edit_monitor_button.clicked.connect(self.view_model.define_edit_monitor_region)
        self.delete_monitor_button.clicked.connect(self.view_model.delete_monitor_region)
        self.flash_monitor_button.clicked.connect(self.view_model.flash_monitor_region)

        # --- ViewModel -> View (Monitor Region) ---
        self.view_model.monitor_region_status_changed.connect(self._update_monitor_status_label)
        self.view_model.monitor_region_coords_text_changed.connect(self.monitor_coords_label.setText)
        self.view_model.monitor_region_preview_changed.connect(self._update_monitor_preview)
        self.view_model.can_delete_monitor_region_changed.connect(self.delete_monitor_button.setEnabled)
        self.view_model.can_flash_monitor_region_changed.connect(self.flash_monitor_button.setEnabled)

    def _connect_flatten_region_signals(self):
         # --- View -> ViewModel (Flatten Regions) ---
        self.add_flatten_button.clicked.connect(self.view_model.add_flatten_region)
        # Connections for edit/delete/flash within list items are handled when the list is populated

        # --- ViewModel -> View (Flatten Regions) ---
        self.view_model.flatten_regions_list_updated.connect(self._update_flatten_list)
        self.view_model.can_add_flatten_region_changed.connect(self.add_flatten_button.setEnabled)


    @Slot(str)
    def _update_monitor_status_label(self, status: str):
        """Updates the monitor region status label."""
        self.monitor_status_label.setText(f"Status: {status}")

        # Update the state property for CSS styling
        if status == "Defined":
            self.monitor_status_label.setProperty("state", "defined")
        elif status == "Not Defined":
            self.monitor_status_label.setProperty("state", "notDefined")
        else:  # Error or Select Platform
            self.monitor_status_label.setProperty("state", "error")

        # Force style update
        self.monitor_status_label.style().unpolish(self.monitor_status_label)
        self.monitor_status_label.style().polish(self.monitor_status_label)


    @Slot(QPixmap)
    def _update_monitor_preview(self, pixmap: QPixmap):
        """Updates the monitor region preview image."""
        if pixmap and not pixmap.isNull():
            # Scale pixmap to fit the label while preserving aspect ratio
            scaled_pixmap = pixmap.scaled(
                self.monitor_preview_label.size(), # Use current label size as max
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.monitor_preview_label.setPixmap(scaled_pixmap)
            self.monitor_preview_label.setText("") # Clear placeholder text
        else:
            self.monitor_preview_label.setPixmap(QPixmap()) # Clear image
            self.monitor_preview_label.setText("No Preview Available")

    @Slot(list)
    def _update_flatten_list(self, flatten_regions_data: List[Dict[str, Any]]):
        """Clears and repopulates the flatten regions list using RegionEntryWidget."""
        self.view_model._logger.debug(f"VIEW: Updating flatten list with {len(flatten_regions_data)} items.")
        self.flatten_list_widget.clear()

        if not flatten_regions_data:
            # Optionally display a placeholder item
            placeholder_item = QListWidgetItem("No flatten regions defined.")
            placeholder_item.setData(Qt.ItemDataRole.UserRole, "placeholder")
            placeholder_item.setFlags(placeholder_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.flatten_list_widget.addItem(placeholder_item)
            # Set minimum size to prevent collapse when empty?
            # self.flatten_list_widget.setMinimumHeight(50)
            return

        # self.flatten_list_widget.setMinimumHeight(0) # Reset minimum height if needed

        for region_data in flatten_regions_data:
            region_name = region_data.get("name", "Unknown")
            coords_text = region_data.get("coords_text", "N/A")
            preview_pixmap = region_data.get("preview_pixmap", QPixmap())

            # --- Create the custom RegionEntryWidget (NO callbacks passed) ---
            entry_widget = RegionEntryWidget(
                region_id=region_name,
                coords_text=coords_text,
                preview_pixmap=preview_pixmap
                # No on_edit, on_delete, on_flash arguments here
            )

            # --- Connect the widget's explicit signals to the ViewModel slots ---
            # Make sure the ViewModel slots (@Slot(str)) exist and expect a string
            entry_widget.edit_requested.connect(self.view_model.edit_flatten_region)
            entry_widget.delete_requested.connect(self.view_model.delete_flatten_region)
            entry_widget.flash_requested.connect(self.view_model.flash_flatten_region)
            # --- End signal connections ---

            # --- Create QListWidgetItem and set the custom widget ---
            list_item = QListWidgetItem(self.flatten_list_widget)
            # Set size hint based on the widget's preferred size for proper layout
            list_item.setSizeHint(entry_widget.sizeHint())
            # Add the item to the list *before* setting the widget
            self.flatten_list_widget.addItem(list_item)
            # Set the custom widget for this item
            self.flatten_list_widget.setItemWidget(list_item, entry_widget)