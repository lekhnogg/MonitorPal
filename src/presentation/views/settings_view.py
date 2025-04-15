# src/presentation/views/settings_view.py

import os
from typing import Optional, List # Added List import

# --- Qt Imports ---
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox, QDoubleSpinBox,
    QGroupBox, QSizePolicy, QCheckBox, QComboBox, QScrollArea, QFrame, QListWidget # Added QListWidget
)
from PySide6.QtCore import Slot, Qt
from PySide6.QtGui import QIntValidator, QDoubleValidator, QColor # Added QColor

# --- Application Imports ---
from src.presentation.view_models.settings_view_model import SettingsViewModel
# Import custom UI components
from src.presentation.components.ui_components import (
    StyledButton, ActionButton, SecondaryButton, WarningButton, DangerButton, GroupHeader
)

# Helper function for collapsible groupbox
def create_collapsible_section(title: str, parent: QWidget = None) -> tuple[QGroupBox, QVBoxLayout]:
    """Creates a groupbox that can be toggled."""
    group_box = GroupHeader(title, parent)
    group_box.setCheckable(True)
    group_box.setChecked(False) # Start collapsed

    content_widget = QWidget() # Widget to hold the actual content
    content_layout = QVBoxLayout(content_widget)
    content_layout.setContentsMargins(9, 9, 9, 9) # Padding inside content
    content_layout.setSpacing(8)

    # Add the content widget to the main layout of the group box
    group_box_layout = QVBoxLayout(group_box)
    # Adjust top margin based on title presence
    group_box_layout.setContentsMargins(0, 20 if title else 5, 0, 0)
    group_box_layout.setSpacing(0)
    group_box_layout.addWidget(content_widget)

    # Toggle content visibility when checkbox state changes
    group_box.toggled.connect(content_widget.setVisible)
    content_widget.setVisible(False) # Start hidden

    return group_box, content_layout # Return group and the *inner* layout for adding widgets


class SettingsView(QWidget):
    """
    View for the Settings tab.

    Displays controls for configuring application paths, monitoring parameters,
    Cold Turkey integration, and other options.
    """

    def __init__(self, view_model: SettingsViewModel, parent: QWidget = None):
        """
        Initialize the SettingsView.

        Args:
            view_model: The corresponding SettingsViewModel instance.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.view_model = view_model
        self._setup_ui()
        self._connect_signals()
        self._apply_initial_vm_state()
        # No explicit _apply_initial_state needed if ViewModel emits on init

    def _setup_ui(self):
        """Creates and arranges the UI elements for the settings tab."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(15)

        # --- Scroll Area for Content ---
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame) # Use Shape enum
        main_layout.addWidget(scroll_area, 1)

        scroll_content_widget = QWidget()
        scroll_area.setWidget(scroll_content_widget)
        content_layout = QVBoxLayout(scroll_content_widget)
        content_layout.setSpacing(15)

        # --- Platform Integration Section ---
        plat_group, plat_layout = create_collapsible_section("PLATFORM INTEGRATION", scroll_content_widget)
        plat_group.setChecked(True) # Start expanded

        # Platform label (read-only display)
        plat_display_layout = QHBoxLayout()
        plat_display_layout.addWidget(QLabel("Platform (Selected Globally):"))
        self.platform_display_label = QLabel("N/A")
        self.platform_display_label.setStyleSheet("font-weight: bold;")
        plat_display_layout.addWidget(self.platform_display_label)
        plat_display_layout.addStretch()
        plat_layout.addLayout(plat_display_layout)

        plat_layout.addSpacing(10)

        # Cold Turkey Path
        plat_layout.addWidget(QLabel("Cold Turkey Blocker Path:"))
        ct_path_layout = QHBoxLayout()
        self.ct_path_input = QLineEdit()
        self.ct_path_input.setPlaceholderText("Path to ColdTurkey.exe")
        ct_path_layout.addWidget(self.ct_path_input, 1)
        self.ct_browse_button = SecondaryButton("Browse...")
        ct_path_layout.addWidget(self.ct_browse_button)
        plat_layout.addLayout(ct_path_layout)

        plat_layout.addSpacing(10)

        # Cold Turkey Block Name and Verification
        ct_block_layout = QHBoxLayout()
        ct_block_layout.addWidget(QLabel("Block Name:"))
        self.ct_block_name_input = QLineEdit()
        self.ct_block_name_input.setPlaceholderText("e.g., Trading")
        ct_block_layout.addWidget(self.ct_block_name_input, 1) # Let it stretch

        self.verify_status_label = QLabel("N/A")
        self.verify_status_label.setMinimumWidth(90) # Slightly wider
        self.verify_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.verify_status_label.setStyleSheet("border: 1px solid grey; border-radius: 3px; padding: 2px;")
        ct_block_layout.addWidget(self.verify_status_label)

        self.verify_block_button = WarningButton("Verify") # Shorten text
        self.verify_block_button.setMinimumWidth(70)
        ct_block_layout.addWidget(self.verify_block_button)
        plat_layout.addLayout(ct_block_layout)

        # --- Verified Blocks List (FIX 1) ---
        plat_layout.addSpacing(15)
        verified_group = QGroupBox("Verified Blocks")
        verified_layout = QVBoxLayout(verified_group)
        verified_layout.setSpacing(5)

        self.verified_list_widget = QListWidget()
        self.verified_list_widget.setMaximumHeight(100) # Limit height
        self.verified_list_widget.setStyleSheet("QListWidget { border: 1px solid #ccc; }")
        verified_layout.addWidget(self.verified_list_widget)

        self.clear_verified_button = DangerButton("Clear All Verified")
        self.clear_verified_button.setEnabled(False) # Start disabled
        # Add button inside the layout, aligned right
        verified_btn_layout = QHBoxLayout()
        verified_btn_layout.addStretch()
        verified_btn_layout.addWidget(self.clear_verified_button)
        verified_layout.addLayout(verified_btn_layout)

        plat_layout.addWidget(verified_group)
        # --- END Verified Blocks List ---

        content_layout.addWidget(plat_group)


        # --- Monitoring Settings Section ---
        monitor_group, monitor_layout = create_collapsible_section("MONITORING SETTINGS", scroll_content_widget)
        monitor_group.setChecked(True) # Start expanded

        # Stop Loss Threshold
        thresh_layout = QHBoxLayout()
        thresh_layout.addWidget(QLabel("Stop Loss Threshold: $"))
        self.threshold_spinbox = QDoubleSpinBox()
        self.threshold_spinbox.setDecimals(2)
        self.threshold_spinbox.setRange(-999999.99, 0.00)
        self.threshold_spinbox.setSingleStep(10.00)
        self.threshold_spinbox.setButtonSymbols(QSpinBox.ButtonSymbols.PlusMinus)
        self.threshold_spinbox.setMinimumWidth(120) # Ensure space
        thresh_layout.addWidget(self.threshold_spinbox)
        thresh_layout.addStretch()
        monitor_layout.addLayout(thresh_layout)

        # Check Interval
        interval_layout = QHBoxLayout()
        interval_layout.addWidget(QLabel("Check Interval (seconds):"))
        self.interval_spinbox = QDoubleSpinBox()
        self.interval_spinbox.setDecimals(1)
        self.interval_spinbox.setRange(0.5, 60.0)
        self.interval_spinbox.setSingleStep(0.5)
        self.interval_spinbox.setSuffix(" s")
        self.interval_spinbox.setMinimumWidth(80)
        interval_layout.addWidget(self.interval_spinbox)
        interval_layout.addStretch()
        monitor_layout.addLayout(interval_layout)

        # Lockout Duration
        duration_layout = QHBoxLayout()
        duration_layout.addWidget(QLabel("Lockout Duration (minutes):"))
        self.duration_spinbox = QSpinBox()
        self.duration_spinbox.setRange(1, 1440)
        self.duration_spinbox.setSingleStep(5)
        self.duration_spinbox.setSuffix(" min")
        self.duration_spinbox.setMinimumWidth(80)
        duration_layout.addWidget(self.duration_spinbox)
        duration_layout.addStretch()
        monitor_layout.addLayout(duration_layout)

        content_layout.addWidget(monitor_group)

        # --- Advanced Settings Section ---
        advanced_group, advanced_layout = create_collapsible_section("ADVANCED SETTINGS", scroll_content_widget)
        # Start collapsed by default

        # Data Directory
        advanced_layout.addWidget(QLabel("Application Data Directory:"))
        self.data_dir_label = QLabel("N/A")
        self.data_dir_label.setStyleSheet("font-style: italic; color: grey;")
        self.data_dir_label.setWordWrap(True) # Allow wrapping if path is long
        advanced_layout.addWidget(self.data_dir_label)

        # Add other advanced settings here if needed
        # fs_layout = QHBoxLayout()
        # self.fullscreen_checkbox = QCheckBox("Use Fullscreen Lockout Overlay")
        # fs_layout.addWidget(self.fullscreen_checkbox)
        # fs_layout.addStretch()
        # advanced_layout.addLayout(fs_layout)

        content_layout.addWidget(advanced_group)

        # --- Push content to top ---
        content_layout.addStretch(1)

        # --- Save/Reset Buttons ---
        bottom_button_layout = QHBoxLayout()
        bottom_button_layout.addStretch(1)
        self.reset_button = SecondaryButton("Reset Settings") # Changed text slightly
        self.save_button = ActionButton("Save Settings")
        bottom_button_layout.addWidget(self.reset_button)
        bottom_button_layout.addWidget(self.save_button)
        # Add button layout outside scroll area for permanent visibility
        main_layout.addLayout(bottom_button_layout)

    def _connect_signals(self):
        """Connect signals from widgets to ViewModel slots and vice versa."""

        # --- View -> ViewModel ---
        self.ct_browse_button.clicked.connect(self.view_model.browse_cold_turkey_path)
        self.ct_path_input.editingFinished.connect(
            lambda: self.view_model.set_cold_turkey_path_text(self.ct_path_input.text())
        )
        self.ct_block_name_input.editingFinished.connect(
            lambda: self.view_model.set_cold_turkey_block_name(self.ct_block_name_input.text())
        )
        self.verify_block_button.clicked.connect(self.view_model.verify_block_configuration)

        self.threshold_spinbox.valueChanged.connect(self.view_model.set_stop_loss_threshold)
        self.interval_spinbox.valueChanged.connect(self.view_model.set_check_interval)
        self.duration_spinbox.valueChanged.connect(self.view_model.set_lockout_duration)

        self.save_button.clicked.connect(self.view_model.save_settings)
        self.reset_button.clicked.connect(self.view_model.reset_to_defaults)

        # Connect clear verified blocks button (FIX 1)
        self.clear_verified_button.clicked.connect(self.view_model.clear_verified_blocks)

        # --- ViewModel -> View ---
        self.view_model.cold_turkey_path_changed.connect(self.ct_path_input.setText)
        self.view_model.cold_turkey_block_name_changed.connect(self.ct_block_name_input.setText)
        self.view_model.verification_status_changed.connect(self._update_verification_status)
        self.view_model.can_verify_block_changed.connect(self.verify_block_button.setEnabled)

        self.view_model.stop_loss_threshold_changed.connect(self.threshold_spinbox.setValue)
        self.view_model.check_interval_changed.connect(self.interval_spinbox.setValue)
        self.view_model.lockout_duration_changed.connect(self.duration_spinbox.setValue)

        self.view_model.data_directory_changed.connect(self.data_dir_label.setText)

        # Connect verified blocks list update (FIX 1)
        self.view_model.verified_blocks_changed.connect(self._update_verified_blocks_list)
        self.view_model.can_clear_verified_blocks_changed.connect(self.clear_verified_button.setEnabled)

        # Connect platform name change to update the display label
        # ViewModel holds reference to the service, View listens to service via VM
        self.view_model._platform_selection_service.register_platform_change_listener(
             self._update_platform_display_label # Connect to local slot
        )
        # Set initial platform name
        self._update_platform_display_label(
            self.view_model._platform_selection_service.get_current_platform()
        )

    def _apply_initial_vm_state(self):
        """Applies the current state from the ViewModel to the widgets."""
        # Trigger update slots/methods using the VM's current internal state attributes
        self.ct_path_input.setText(self.view_model._ct_path)
        self.ct_block_name_input.setText(self.view_model._ct_block_name)

        self.threshold_spinbox.setValue(self.view_model._threshold)
        self.interval_spinbox.setValue(self.view_model._interval)
        self.duration_spinbox.setValue(self.view_model._duration)

        self.data_dir_label.setText(self.view_model._data_dir)

        # Update read-only platform label using the service ref from VM
        self._update_platform_display_label(
            self.view_model._platform_selection_service.get_current_platform()
        )

        # Update verified blocks list and button state
        self._update_verified_blocks_list(self.view_model._verified_blocks_list)
        self.clear_verified_button.setEnabled(self.view_model._can_clear_verified)

        # Update verification status label and button state
        # We need the VM to calculate this based on its state
        self.view_model._update_verification_status()  # Ask VM to re-evaluate and emit signals
        # The slots connected to verification_status_changed and can_verify_block_changed
        # will handle the UI update.

    # --- Slots for ViewModel Signals ---

    @Slot(str, str)
    def _update_verification_status(self, status_text: str, color_name: str):
        """Updates the verification status label text and style color."""
        self.verify_status_label.setText(status_text)
        # Map color names to actual color values if needed, or use standard names
        color = QColor(color_name) if QColor.isValidColorName(color_name) else QColor("gray")
        border_style = f"border: 1px solid {color.name()};"
        text_color_style = f"color: {color.name()};"

        # Special case for 'Not Verified' maybe make text stand out more
        if status_text == "Not Verified":
             text_color_style = f"color: white; background-color: {color.name()};" # White text on red background

        self.verify_status_label.setStyleSheet(
            f"{text_color_style} {border_style} border-radius: 3px; padding: 2px;"
        )

    @Slot(list)
    def _update_verified_blocks_list(self, blocks: List[str]): # Changed type hint
        """Updates the QListWidget displaying verified blocks."""
        self.verified_list_widget.clear()
        if blocks:
            self.verified_list_widget.addItems(blocks)
        else:
            # Optional placeholder
            self.verified_list_widget.addItem("No blocks verified yet.")
            # You might want to disable selection for the placeholder item:
            # item = self.verified_list_widget.item(0)
            # if item: item.setFlags(item.flags() & ~Qt.ItemIsSelectable)

    @Slot(str)
    def _update_platform_display_label(self, platform_name: str):
        """Updates the read-only platform display label."""
        self.platform_display_label.setText(platform_name if platform_name else "None Selected")