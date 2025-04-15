# src/presentation/views/region_setup_view.py

from typing import List, Dict, Any

# --- Qt Imports ---
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QSplitter, QListWidget,
    QListWidgetItem, QPushButton, QSizePolicy # Added QPushButton
)
from PySide6.QtCore import Slot, Qt, QSize # Added QSize
from PySide6.QtGui import QPixmap

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
        self._apply_initial_vm_state()
        # No explicit _apply_initial_state needed if ViewModel emits on init

    def _setup_ui(self):
        """Creates and arranges the UI elements for the region setup tab."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # --- Splitter for Monitor and Flatten Regions ---
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter, 1) # Allow splitter to stretch

        # --- Left Side: P&L Monitoring Region ---
        monitor_widget = QWidget()
        monitor_layout = QVBoxLayout(monitor_widget)
        monitor_layout.setContentsMargins(0, 0, 0, 0) # Remove internal margins

        monitor_group = QGroupBox("P&L Monitoring Region")
        monitor_group_layout = QVBoxLayout(monitor_group)
        monitor_group_layout.setSpacing(8)

        # Preview Area
        self.monitor_preview_label = QLabel("No Preview Available")
        self.monitor_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.monitor_preview_label.setStyleSheet(
            "border: 1px solid #ccc; background-color: #f0f0f0; color: #555;"
            "min-height: 150px;" # Ensure decent initial height
        )
        self.monitor_preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding) # Allow stretch
        monitor_group_layout.addWidget(self.monitor_preview_label, 1) # Allow stretch

        # Status and Coords Labels
        self.monitor_status_label = QLabel("Status: N/A")
        monitor_group_layout.addWidget(self.monitor_status_label)

        self.monitor_coords_label = QLabel("Coordinates: N/A")
        monitor_group_layout.addWidget(self.monitor_coords_label)

        # Action Buttons
        monitor_button_layout = QHBoxLayout()
        self.define_edit_monitor_button = StyledButton("Define / Edit Region")
        self.flash_monitor_button = SecondaryButton("Flash")
        self.delete_monitor_button = DangerButton("Delete Region")

        monitor_button_layout.addWidget(self.define_edit_monitor_button)
        monitor_button_layout.addStretch() # Push flash/delete right
        monitor_button_layout.addWidget(self.flash_monitor_button)
        monitor_button_layout.addWidget(self.delete_monitor_button)
        monitor_group_layout.addLayout(monitor_button_layout)

        monitor_layout.addWidget(monitor_group)
        splitter.addWidget(monitor_widget)

        # --- Right Side: Flatten Position Regions ---
        flatten_widget = QWidget()
        flatten_layout = QVBoxLayout(flatten_widget)
        flatten_layout.setContentsMargins(0, 0, 0, 0)

        flatten_group = QGroupBox("Flatten Position Regions")
        flatten_group_layout = QVBoxLayout(flatten_group)
        flatten_group_layout.setSpacing(5)

        self.flatten_list_widget = QListWidget()
        self.flatten_list_widget.setStyleSheet("QListWidget { border: 1px solid #ccc; }") # Add border for clarity
        self.flatten_list_widget.setSpacing(3) # Space between items
        flatten_group_layout.addWidget(self.flatten_list_widget, 1) # Allow stretch

        self.add_flatten_button = ActionButton("+ Add Region")
        flatten_group_layout.addWidget(self.add_flatten_button, 0, Qt.AlignmentFlag.AlignRight) # Align right

        flatten_layout.addWidget(flatten_group)
        splitter.addWidget(flatten_widget)

        # --- Optional Help Section ---
        help_group = QGroupBox("Help")
        help_layout = QVBoxLayout(help_group)
        help_text = QLabel(
             "1. Define a P&L monitoring region where your platform displays your current profit/loss.\n"
             "2. Add Flatten Position regions for buttons that close all your positions.\n"
             "3. Use 'Flash' to highlight regions and confirm correct placement."
        )
        help_text.setWordWrap(True)
        help_layout.addWidget(help_text)
        main_layout.addWidget(help_group) # Add at the bottom


        # --- Set initial splitter sizes ---
        splitter.setSizes([self.width() // 2, self.width() // 2]) # Equal initial split

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

    def _apply_initial_vm_state(self):
        """Applies the current state from the ViewModel to the widgets."""
        # NOTE: This requires RegionSetupViewModel to store these states internally
        #       after its initial _load_regions_for_platform call.
        # Example internal VM attributes needed:
        # self.view_model._monitor_status_text
        # self.view_model._monitor_coords_text
        # self.view_model._monitor_preview_pixmap
        # self.view_model._can_delete_monitor
        # self.view_model._can_flash_monitor
        # self.view_model._flatten_list_data
        # self.view_model._can_add_flatten

        # Trigger update slots using the VM's current internal state
        self._update_monitor_status_label(getattr(self.view_model, '_monitor_status_text', "N/A"))
        self.monitor_coords_label.setText(getattr(self.view_model, '_monitor_coords_text', "N/A"))
        self._update_monitor_preview(getattr(self.view_model, '_monitor_preview_pixmap', QPixmap()))
        self.delete_monitor_button.setEnabled(getattr(self.view_model, '_can_delete_monitor', False))
        self.flash_monitor_button.setEnabled(getattr(self.view_model, '_can_flash_monitor', False))
        self._update_flatten_list(getattr(self.view_model, '_flatten_list_data', []))
        self.add_flatten_button.setEnabled(getattr(self.view_model, '_can_add_flatten', False))
    # --- Slots for ViewModel Signals ---

    @Slot(str)
    def _update_monitor_status_label(self, status: str):
        """Updates the monitor region status label."""
        self.monitor_status_label.setText(f"Status: {status}")
        # Optional: Change style based on status
        if status == "Defined":
             self.monitor_status_label.setStyleSheet("color: green; font-weight: bold;")
        elif status == "Not Defined":
             self.monitor_status_label.setStyleSheet("color: grey; font-style: italic;")
        else: # Error or Select Platform
             self.monitor_status_label.setStyleSheet("color: orange;")


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
        """Clears and repopulates the flatten regions list."""
        self.flatten_list_widget.clear()

        if not flatten_regions_data:
            # Optionally display a placeholder item
            placeholder_item = QListWidgetItem("No flatten regions defined.")
            placeholder_item.setForeground(Qt.GlobalColor.gray)
            placeholder_item.setFlags(placeholder_item.flags() & ~Qt.ItemFlag.ItemIsSelectable) # Make non-selectable
            self.flatten_list_widget.addItem(placeholder_item)
            return

        for region_data in flatten_regions_data:
            region_name = region_data.get("name", "Unknown")
            coords_text = region_data.get("coords_text", "N/A")
            preview_pixmap = region_data.get("preview_pixmap", QPixmap())

            # --- Create the custom RegionEntryWidget ---
            # Note: Pass ViewModel methods wrapped in lambdas to capture the correct region_name
            entry_widget = RegionEntryWidget(
                region_id=region_name,
                coords_text=coords_text,
                preview_pixmap=preview_pixmap,
                on_edit=lambda name=region_name: self.view_model.edit_flatten_region(name),
                on_delete=lambda name=region_name: self.view_model.delete_flatten_region(name),
                on_flash=lambda name=region_name: self.view_model.flash_flatten_region(name)
            )

            # --- Create QListWidgetItem and set the custom widget ---
            list_item = QListWidgetItem(self.flatten_list_widget)
            # Set size hint based on the widget's preferred size
            list_item.setSizeHint(entry_widget.sizeHint())
            # Add the item to the list *before* setting the widget
            self.flatten_list_widget.addItem(list_item)
            # Set the custom widget for this item
            self.flatten_list_widget.setItemWidget(list_item, entry_widget)