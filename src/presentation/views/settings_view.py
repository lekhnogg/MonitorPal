# src/presentation/views/settings_view.py

import os
from typing import Optional, List

# --- Qt Imports ---
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox, QDoubleSpinBox,
    QGroupBox, QSizePolicy, QCheckBox, QComboBox, QScrollArea, QFrame,
    QPushButton, # Keep import
    QListWidget, QListWidgetItem, QAbstractItemView # Keep imports
)
from PySide6.QtCore import Slot, Qt, QTimer
from PySide6.QtGui import QIntValidator, QDoubleValidator, QColor

# --- Application Imports ---
from src.presentation.view_models.settings_view_model import SettingsViewModel
from src.presentation.components.ui_components import (
    StyledButton, ActionButton, SecondaryButton, WarningButton, DangerButton, GroupHeader
)

class SettingsView(QWidget):
    """
    View for the Settings tab. Allows configuring paths, block names,
    monitoring parameters, and verification for the selected platform.
    """

    def __init__(self, view_model: SettingsViewModel, parent: QWidget = None):
        super().__init__(parent)
        self.view_model = view_model
        self._setup_ui()
        self._connect_signals()
        # Schedule the VM to emit its initial state signals shortly after setup
        self.view_model._logger.debug("View: Scheduling initial UI refresh via VM.refresh_ui_signals.")
        QTimer.singleShot(0, self.view_model.refresh_ui_signals)

    def _setup_ui(self):
        """Creates and arranges the UI elements for the settings tab using QFrame panels."""
        # Main layout set directly on the SettingsView widget
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15) # Overall padding for the tab
        main_layout.setSpacing(15) # Spacing between panels

        # --- Platform Integration Section ---
        plat_panel = QFrame() # Use QFrame
        plat_panel.setObjectName("platformPanel") # Specific ID if needed
        plat_panel.setProperty("class", "contentSectionPanel") # Use consistent class
        plat_layout = QVBoxLayout(plat_panel) # Layout for this panel's content
        plat_layout.setContentsMargins(15, 15, 15, 15) # Padding inside the panel
        plat_layout.setSpacing(8) # Spacing within the panel

        plat_title = QLabel("PLATFORM INTEGRATION") # Use QLabel for title
        plat_title.setProperty("class", "panelTitle") # Style title via class
        plat_layout.addWidget(plat_title)

        # Optional Divider
        plat_divider = QFrame(); plat_divider.setFrameShape(QFrame.Shape.HLine); plat_divider.setObjectName("panelDivider")
        plat_layout.addWidget(plat_divider)

        # -- Selected Platform Display --
        plat_display_layout = QHBoxLayout()
        plat_display_layout.addWidget(QLabel("Platform (Selected Globally):"))
        self.platform_display_label = QLabel("N/A"); self.platform_display_label.setObjectName("platformDisplayLabel")
        plat_display_layout.addWidget(self.platform_display_label); plat_display_layout.addStretch()
        plat_layout.addLayout(plat_display_layout)
        plat_layout.addSpacing(10)

        # -- Cold Turkey Path (Global) --
        plat_layout.addWidget(QLabel("Cold Turkey Blocker Path (Global):"))
        ct_path_layout = QHBoxLayout()
        self.ct_path_input = QLineEdit(); self.ct_path_input.setObjectName("ctPathInput"); self.ct_path_input.setPlaceholderText("Path to ColdTurkey.exe")
        ct_path_layout.addWidget(self.ct_path_input, 1)
        self.ct_browse_button = SecondaryButton("Browse...", icon=":/icons/folder.svg"); # Added icon
        self.ct_browse_button.setObjectName("ctBrowseButton")
        ct_path_layout.addWidget(self.ct_browse_button)
        plat_layout.addLayout(ct_path_layout)
        plat_layout.addSpacing(5)

        # -- Trading Platform Executable Path (Platform Specific) --
        plat_layout.addWidget(QLabel("Trading Platform Executable Path:"))
        platform_exe_layout = QHBoxLayout()
        self.platform_exe_input = QLineEdit(); self.platform_exe_input.setObjectName("platformExeInput"); self.platform_exe_input.setPlaceholderText("Path to Trading Platform .exe")
        platform_exe_layout.addWidget(self.platform_exe_input, 1)
        self.platform_exe_browse_button = SecondaryButton("Browse...", icon=":/icons/folder.svg"); # Added icon
        self.platform_exe_browse_button.setObjectName("platformExeBrowseButton")
        platform_exe_layout.addWidget(self.platform_exe_browse_button)
        plat_layout.addLayout(platform_exe_layout)
        plat_layout.addSpacing(10)

        # -- Cold Turkey Block Name and Verification Row --
        ct_block_layout = QHBoxLayout()
        ct_block_layout.addWidget(QLabel("Cold Turkey Block Name:"))
        self.ct_block_name_input = QLineEdit(); self.ct_block_name_input.setObjectName("ctBlockNameInput"); self.ct_block_name_input.setPlaceholderText("e.g., Trading (Case-Sensitive)")
        ct_block_layout.addWidget(self.ct_block_name_input, 1) # Give input stretch
        ct_block_layout.addSpacing(10) # Space before status

        self.verify_status_label = QLabel("N/A"); self.verify_status_label.setObjectName("verifyStatusLabel"); self.verify_status_label.setProperty("state", "pending")
        ct_block_layout.addWidget(self.verify_status_label) # Status label

        self.verify_block_button = WarningButton("Verify", icon=":/icons/zap.svg"); # Added icon
        self.verify_block_button.setObjectName("verifyBlockButton")
        ct_block_layout.addWidget(self.verify_block_button) # Verify button

        self.remove_verification_button = DangerButton("Remove", icon=":/icons/trash.svg"); # Added icon
        self.remove_verification_button.setObjectName("removeVerificationButton")
        self.remove_verification_button.setEnabled(False);
        self.remove_verification_button.setToolTip("Remove the verified status for this block name.")
        ct_block_layout.addWidget(self.remove_verification_button) # Remove button AFTER Verify

        plat_layout.addLayout(ct_block_layout) # Add the whole row to the panel layout

        plat_layout.addStretch(1)
        main_layout.addWidget(plat_panel) # Add panel to the view's main layout

        # --- Monitoring Settings Section ---
        monitor_panel = QFrame()
        monitor_panel.setObjectName("monitorPanel")
        monitor_panel.setProperty("class", "contentSectionPanel")
        monitor_layout = QVBoxLayout(monitor_panel)
        monitor_layout.setContentsMargins(15, 15, 15, 15); monitor_layout.setSpacing(8)

        monitor_title = QLabel("MONITORING SETTINGS"); monitor_title.setProperty("class", "panelTitle")
        monitor_layout.addWidget(monitor_title)
        monitor_divider = QFrame(); monitor_divider.setFrameShape(QFrame.Shape.HLine); monitor_divider.setObjectName("panelDivider")
        monitor_layout.addWidget(monitor_divider)

        # -- Stop Loss Threshold --
        thresh_layout = QHBoxLayout()
        thresh_layout.addWidget(QLabel("Stop Loss Threshold ($):"))
        self.threshold_spinbox = QDoubleSpinBox(); self.threshold_spinbox.setObjectName("thresholdSpinBox")
        self.threshold_spinbox.setPrefix("- "); self.threshold_spinbox.setDecimals(2); self.threshold_spinbox.setRange(0.01, 999999.99)
        self.threshold_spinbox.setSingleStep(10.00); self.threshold_spinbox.setButtonSymbols(QSpinBox.ButtonSymbols.PlusMinus)
        thresh_layout.addWidget(self.threshold_spinbox); thresh_layout.addStretch()
        monitor_layout.addLayout(thresh_layout)

        # -- Lockout Duration --
        duration_layout = QHBoxLayout(); duration_layout.addWidget(QLabel("Lockout Duration (minutes):"))
        self.duration_spinbox = QSpinBox(); self.duration_spinbox.setObjectName("durationSpinBox")
        self.duration_spinbox.setRange(1, 1440); self.duration_spinbox.setSingleStep(5); self.duration_spinbox.setSuffix(" min")
        duration_layout.addWidget(self.duration_spinbox); duration_layout.addStretch()
        monitor_layout.addLayout(duration_layout)

        # -- Check Interval --
        interval_layout = QHBoxLayout(); interval_layout.addWidget(QLabel("Check Interval (seconds, Global):"))
        self.interval_spinbox = QDoubleSpinBox(); self.interval_spinbox.setObjectName("intervalSpinBox")
        self.interval_spinbox.setDecimals(1); self.interval_spinbox.setRange(0.5, 60.0); self.interval_spinbox.setSingleStep(0.5); self.interval_spinbox.setSuffix(" s")
        interval_layout.addWidget(self.interval_spinbox); interval_layout.addStretch()
        monitor_layout.addLayout(interval_layout)

        monitor_layout.addStretch(1)
        main_layout.addWidget(monitor_panel) # Add panel to the view's main layout

        # --- Advanced Settings Section ---
        advanced_panel = QFrame()
        advanced_panel.setObjectName("advancedPanel")
        advanced_panel.setProperty("class", "contentSectionPanel")
        advanced_layout = QVBoxLayout(advanced_panel)
        advanced_layout.setContentsMargins(15, 15, 15, 15); advanced_layout.setSpacing(8)

        advanced_header_layout = QHBoxLayout()
        advanced_title = QLabel("ADVANCED SETTINGS"); advanced_title.setProperty("class", "panelTitle")
        advanced_header_layout.addWidget(advanced_title); advanced_header_layout.addStretch()
        advanced_layout.addLayout(advanced_header_layout)
        advanced_divider = QFrame(); advanced_divider.setFrameShape(QFrame.Shape.HLine); advanced_divider.setObjectName("panelDivider")
        advanced_layout.addWidget(advanced_divider)

        self.advanced_content = QWidget(); self.advanced_content.setObjectName("advancedSettingsContent")
        advanced_content_layout = QVBoxLayout(self.advanced_content)
        advanced_content_layout.setContentsMargins(0, 5, 0, 0); advanced_content_layout.setSpacing(8)
        advanced_content_layout.addWidget(QLabel("Application Data Directory:"))
        self.data_dir_label = QLabel("N/A"); self.data_dir_label.setObjectName("dataDirLabel")
        self.data_dir_label.setWordWrap(True); advanced_content_layout.addWidget(self.data_dir_label)
        advanced_layout.addWidget(self.advanced_content)
        self.advanced_content.setVisible(True) # Make visible by default if no toggle

        advanced_layout.addStretch(1)
        main_layout.addWidget(advanced_panel) # Add panel to the view's main layout

        # --- Spacer to push panels towards the top ---
        main_layout.addStretch(1) # Stretch in the main layout

        # --- Save/Reset Buttons ---
        bottom_button_layout = QHBoxLayout()
        bottom_button_layout.setContentsMargins(0, 5, 0, 0) # Add some top margin
        bottom_button_layout.addStretch(1) # Push buttons right

        self.reset_button = SecondaryButton("Reset Display", icon=":/icons/refresh-cw.svg");
        self.reset_button.setObjectName("resetButton"); self.reset_button.setToolTip("Reset fields to defaults (does not save)")

        self.save_button = ActionButton("Save Settings", icon=":/icons/save.svg");
        self.save_button.setObjectName("saveButton"); self.save_button.setToolTip("Save all global and current platform settings")

        bottom_button_layout.addWidget(self.reset_button)
        bottom_button_layout.addWidget(self.save_button) # Only Reset and Save here

        # Add buttons layout to the view's main layout
        main_layout.addLayout(bottom_button_layout)

    def _connect_signals(self):
        """Connect signals from widgets to ViewModel slots and vice versa."""

        # --- View -> ViewModel (User finished editing fields) ---
        # Connect editingFinished to update VM's internal *temporary* state
        self.ct_path_input.editingFinished.connect(
            lambda: self.view_model.update_ct_path_state(self.ct_path_input.text())
        )
        self.platform_exe_input.editingFinished.connect(
            lambda: self.view_model.update_platform_exe_path_state(self.platform_exe_input.text())
        )
        # Block name is platform specific, can update VM state more directly if needed for verification logic
        self.ct_block_name_input.editingFinished.connect(
             lambda: self.view_model.update_platform_block_name_state(self.ct_block_name_input.text())
        )
        self.threshold_spinbox.editingFinished.connect(
            # Pass absolute value, VM setter handles making it negative
            lambda: self.view_model.update_platform_threshold_state(abs(self.threshold_spinbox.value()))
        )
        self.interval_spinbox.editingFinished.connect(
            lambda: self.view_model.update_global_interval_state(self.interval_spinbox.value())
        )
        self.duration_spinbox.editingFinished.connect(
            lambda: self.view_model.update_platform_duration_state(self.duration_spinbox.value())
        )

        # --- View -> ViewModel (Button Actions) ---
        self.ct_browse_button.clicked.connect(self.view_model.browse_cold_turkey_path)
        self.platform_exe_browse_button.clicked.connect(self.view_model.browse_platform_executable_path)
        self.verify_block_button.clicked.connect(self.view_model.verify_block_configuration)
        self.remove_verification_button.clicked.connect(self.view_model.remove_verification_for_current_platform)
        self.save_button.clicked.connect(self.view_model.save_settings)
        self.reset_button.clicked.connect(self.view_model.reset_to_defaults)


        # --- ViewModel -> View (Update UI widgets when VM state changes) ---
        self.view_model.cold_turkey_path_changed.connect(self.ct_path_input.setText)
        self.view_model.cold_turkey_block_name_changed.connect(self.ct_block_name_input.setText)
        self.view_model.platform_executable_path_changed.connect(self.platform_exe_input.setText)

        # Connect platform-specific risk params
        self.view_model.stop_loss_threshold_changed.connect(lambda val: self.threshold_spinbox.setValue(abs(val))) # Display as positive
        self.view_model.lockout_duration_changed.connect(self.duration_spinbox.setValue)

        # Connect global interval
        self.view_model.check_interval_changed.connect(self.interval_spinbox.setValue)

        # Connect data directory display
        self.view_model.data_directory_changed.connect(self.data_dir_label.setText)

        # Verification status UI updates
        self.view_model.verification_status_changed.connect(self._update_verification_status)
        self.view_model.can_verify_block_changed.connect(self.verify_block_button.setEnabled)
        self.view_model.can_remove_verification_changed.connect(self.remove_verification_button.setEnabled)
        self.view_model.block_name_input_read_only_changed.connect(self._set_block_name_input_read_only)

        # Connect platform name display (ensure platform service listener exists in VM)
        if hasattr(self.view_model, '_platform_selection_service'):
             self.view_model._platform_selection_service.register_platform_change_listener(
                 self._update_platform_display_label
             )
             # Trigger initial display
             self._update_platform_display_label(
                 self.view_model._platform_selection_service.get_current_platform()
             )
        else:
             self._update_platform_display_label(None) # Handle missing service

    # --- Slots for ViewModel Signals ---

    @Slot(str, str)
    def _update_verification_status(self, status_text: str, state_name: str):
        """Updates the verification status label and its style state."""
        self.verify_status_label.setText(status_text)
        self.verify_status_label.setProperty("state", state_name)
        self.verify_status_label.style().unpolish(self.verify_status_label)
        self.verify_status_label.style().polish(self.verify_status_label)

    @Slot(bool)
    def _set_block_name_input_read_only(self, is_read_only: bool):
        """Sets the read-only state of the Cold Turkey block name input."""
        if hasattr(self, 'ct_block_name_input'): # Check widget exists
            self.ct_block_name_input.setReadOnly(is_read_only)
            self.ct_block_name_input.setProperty("readOnly", "true" if is_read_only else "false")
            self.ct_block_name_input.style().unpolish(self.ct_block_name_input)
            self.ct_block_name_input.style().polish(self.ct_block_name_input)

    @Slot(str)
    def _update_platform_display_label(self, platform_name: Optional[str]):
        """Updates the label showing the currently selected platform."""
        display_text = platform_name if platform_name else "None Selected"
        if hasattr(self, 'platform_display_label'): # Check widget exists
            self.platform_display_label.setText(display_text)