# src/presentation/views/settings_view.py

import os
# import re # No longer needed here
from typing import Optional, List

# --- Qt Imports ---
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox, QDoubleSpinBox,
    QGroupBox, QSizePolicy, QCheckBox, QComboBox, QScrollArea, QFrame,
    QPushButton, # Add QPushButton
    QListWidget, QListWidgetItem, QAbstractItemView # Keep imports if used elsewhere
)
from PySide6.QtCore import Slot, Qt
from PySide6.QtGui import QIntValidator, QDoubleValidator, QColor

# --- Application Imports ---
from src.presentation.view_models.settings_view_model import SettingsViewModel
from src.presentation.components.ui_components import (
    StyledButton, ActionButton, SecondaryButton, WarningButton, DangerButton, GroupHeader
)
from src.presentation.styles.style_manager import StyleManager

# Helper function (Unchanged)
def create_section(title: str, parent: QWidget = None, checkable: bool = True, start_checked: bool = False) -> tuple[GroupHeader, QVBoxLayout]:
    group_box = GroupHeader(title, parent)
    group_box.setCheckable(checkable)
    group_box.setChecked(start_checked)
    group_header_main_layout = QVBoxLayout()
    group_header_main_layout.setContentsMargins(0, 20, 0, 0)
    group_header_main_layout.setSpacing(0)
    content_widget = QWidget()
    content_layout = QVBoxLayout()
    content_layout.setContentsMargins(9, 9, 9, 9)
    content_layout.setSpacing(8)
    content_widget.setLayout(content_layout)
    group_header_main_layout.addWidget(content_widget)
    group_box.setLayout(group_header_main_layout)
    if checkable:
        group_box.toggled.connect(content_widget.setVisible)
        content_widget.setVisible(start_checked)
    else:
        content_widget.setVisible(True)
    return group_box, content_layout


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
        self._apply_initial_vm_state()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(15)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        main_layout.addWidget(scroll_area, 1)
        scroll_content_widget = QWidget()
        scroll_area.setWidget(scroll_content_widget)
        content_layout = QVBoxLayout(scroll_content_widget)
        content_layout.setSpacing(15)

        # --- Platform Integration Section ---
        plat_group, plat_layout = create_section(
            "PLATFORM INTEGRATION", scroll_content_widget, checkable=False
        )
        plat_group.setObjectName("platformGroup")

        # -- Selected Platform Display --
        plat_display_layout = QHBoxLayout()
        plat_display_layout.addWidget(QLabel("Platform (Selected Globally):"))
        self.platform_display_label = QLabel("N/A")
        self.platform_display_label.setObjectName("platformDisplayLabel")
        plat_display_layout.addWidget(self.platform_display_label)
        plat_display_layout.addStretch()
        plat_layout.addLayout(plat_display_layout)
        plat_layout.addSpacing(10) # Space before next input group

        # -- Cold Turkey Path --
        plat_layout.addWidget(QLabel("Cold Turkey Blocker Path:"))
        ct_path_layout = QHBoxLayout()
        self.ct_path_input = QLineEdit()
        self.ct_path_input.setPlaceholderText("Path to ColdTurkey.exe")
        ct_path_layout.addWidget(self.ct_path_input, 1)
        self.ct_browse_button = SecondaryButton("Browse...")
        ct_path_layout.addWidget(self.ct_browse_button)
        plat_layout.addLayout(ct_path_layout)
        plat_layout.addSpacing(5) # Smaller space between input rows

        # --- NEW: Trading Platform Executable Path ---
        plat_layout.addWidget(QLabel("Trading Platform Executable Path:"))
        platform_exe_layout = QHBoxLayout()
        self.platform_exe_input = QLineEdit()
        self.platform_exe_input.setObjectName("platformExeInput") # For QSS if needed
        self.platform_exe_input.setPlaceholderText("Path to Trading Platform .exe (e.g., NinjaTrader.exe)")
        platform_exe_layout.addWidget(self.platform_exe_input, 1)
        self.platform_exe_browse_button = SecondaryButton("Browse...") # Or "Test..." if testing launch
        self.platform_exe_browse_button.setObjectName("platformExeBrowseButton")
        platform_exe_layout.addWidget(self.platform_exe_browse_button)
        plat_layout.addLayout(platform_exe_layout)
        plat_layout.addSpacing(10) # Space before block name row
        # --- END NEW ---

        # -- Cold Turkey Block Name and Verification Row --
        ct_block_layout = QHBoxLayout()
        ct_block_layout.addWidget(QLabel("Cold Turkey Block Name:"))
        self.ct_block_name_input = QLineEdit()
        self.ct_block_name_input.setPlaceholderText("e.g., Trading (Case-Sensitive)")
        ct_block_layout.addWidget(self.ct_block_name_input, 1)
        ct_block_layout.addSpacing(10)
        self.verify_status_label = QLabel("N/A")
        self.verify_status_label.setObjectName("verifyStatusLabel")
        self.verify_status_label.setProperty("state", "pending")
        ct_block_layout.addWidget(self.verify_status_label)
        self.verify_block_button = WarningButton("Verify")
        self.verify_block_button.setObjectName("verifyBlockButton")
        ct_block_layout.addWidget(self.verify_block_button)
        self.remove_verification_button = DangerButton("Remove Verification")
        self.remove_verification_button.setObjectName("removeVerificationButton")
        self.remove_verification_button.setEnabled(False)
        self.remove_verification_button.setToolTip("Remove the verified status for the currently selected platform.")
        ct_block_layout.addWidget(self.remove_verification_button)
        plat_layout.addLayout(ct_block_layout)
        plat_layout.addSpacing(15) # End of platform section spacing

        content_layout.addWidget(plat_group)

        # --- Monitoring Settings Section (Unchanged) ---
        monitor_group, monitor_layout = create_section(
            "MONITORING SETTINGS", scroll_content_widget, checkable=False
        )
        monitor_group.setObjectName("monitorGroup")
        thresh_layout = QHBoxLayout(); thresh_layout.addWidget(QLabel("Stop Loss Threshold: $"))
        self.threshold_spinbox = QDoubleSpinBox(); self.threshold_spinbox.setObjectName("thresholdSpinBox")
        self.threshold_spinbox.setDecimals(2); self.threshold_spinbox.setRange(-999999.99, 0.00); self.threshold_spinbox.setSingleStep(10.00)
        self.threshold_spinbox.setButtonSymbols(QSpinBox.ButtonSymbols.PlusMinus)
        thresh_layout.addWidget(self.threshold_spinbox); thresh_layout.addStretch()
        monitor_layout.addLayout(thresh_layout)
        interval_layout = QHBoxLayout(); interval_layout.addWidget(QLabel("Check Interval (seconds):"))
        self.interval_spinbox = QDoubleSpinBox(); self.interval_spinbox.setObjectName("intervalSpinBox")
        self.interval_spinbox.setDecimals(1); self.interval_spinbox.setRange(0.5, 60.0); self.interval_spinbox.setSingleStep(0.5)
        self.interval_spinbox.setSuffix(" s")
        interval_layout.addWidget(self.interval_spinbox); interval_layout.addStretch()
        monitor_layout.addLayout(interval_layout)
        duration_layout = QHBoxLayout(); duration_layout.addWidget(QLabel("Lockout Duration (minutes):"))
        self.duration_spinbox = QSpinBox(); self.duration_spinbox.setObjectName("durationSpinBox")
        self.duration_spinbox.setRange(1, 1440); self.duration_spinbox.setSingleStep(5)
        self.duration_spinbox.setSuffix(" min")
        duration_layout.addWidget(self.duration_spinbox); duration_layout.addStretch()
        monitor_layout.addLayout(duration_layout)
        content_layout.addWidget(monitor_group)

        # --- Advanced Settings Section (Unchanged) ---
        advanced_group, advanced_layout = create_section(
            "ADVANCED SETTINGS", scroll_content_widget, checkable=True, start_checked=False
        )
        advanced_group.setObjectName("advancedGroup")
        advanced_layout.addWidget(QLabel("Application Data Directory:"))
        self.data_dir_label = QLabel("N/A"); self.data_dir_label.setObjectName("dataDirLabel")
        self.data_dir_label.setWordWrap(True); advanced_layout.addWidget(self.data_dir_label)
        content_layout.addWidget(advanced_group)
        content_layout.addStretch(1)

        # --- Save/Reset Buttons (Unchanged) ---
        bottom_button_layout = QHBoxLayout()
        bottom_button_layout.addStretch(1)
        self.reset_button = SecondaryButton("Reset Settings"); self.reset_button.setObjectName("resetButton")
        self.save_button = ActionButton("Save Settings"); self.save_button.setObjectName("saveButton")
        bottom_button_layout.addWidget(self.reset_button); bottom_button_layout.addWidget(self.save_button)
        main_layout.addLayout(bottom_button_layout)


    def _connect_signals(self):
        """Connect signals from widgets to ViewModel slots and vice versa."""

        # --- View -> ViewModel ---
        self.ct_browse_button.clicked.connect(self.view_model.browse_cold_turkey_path)
        self.ct_path_input.editingFinished.connect(lambda: self.view_model.set_cold_turkey_path_text(self.ct_path_input.text()))
        self.ct_block_name_input.editingFinished.connect(lambda: self.view_model.set_cold_turkey_block_name(self.ct_block_name_input.text()))

        # --- Connect NEW Platform Exe Path Signals ---
        self.platform_exe_browse_button.clicked.connect(self.view_model.browse_platform_executable_path)
        self.platform_exe_input.editingFinished.connect(lambda: self.view_model.set_platform_executable_path_text(self.platform_exe_input.text()))
        # --- END NEW ---

        self.verify_block_button.clicked.connect(self.view_model.verify_block_configuration)
        self.remove_verification_button.clicked.connect(self.view_model.remove_verification_for_current_platform)

        self.threshold_spinbox.valueChanged.connect(self.view_model.set_stop_loss_threshold)
        self.interval_spinbox.valueChanged.connect(self.view_model.set_check_interval)
        self.duration_spinbox.valueChanged.connect(self.view_model.set_lockout_duration)

        self.save_button.clicked.connect(self.view_model.save_settings)
        self.reset_button.clicked.connect(self.view_model.reset_to_defaults)


        # --- ViewModel -> View ---
        self.view_model.cold_turkey_path_changed.connect(self.ct_path_input.setText)
        self.view_model.cold_turkey_block_name_changed.connect(self.ct_block_name_input.setText)

        # --- Connect NEW Platform Exe Path Signal ---
        self.view_model.platform_executable_path_changed.connect(self.platform_exe_input.setText)
        # --- END NEW ---

        self.view_model.verification_status_changed.connect(self._update_verification_status)
        self.view_model.can_verify_block_changed.connect(self.verify_block_button.setEnabled)
        self.view_model.can_remove_verification_changed.connect(self.remove_verification_button.setEnabled)
        self.view_model.block_name_input_read_only_changed.connect(self._set_block_name_input_read_only)
        self.view_model.stop_loss_threshold_changed.connect(self.threshold_spinbox.setValue)
        self.view_model.check_interval_changed.connect(self.interval_spinbox.setValue)
        self.view_model.lockout_duration_changed.connect(self.duration_spinbox.setValue)
        self.view_model.data_directory_changed.connect(self.data_dir_label.setText)

        # Connect platform name change
        if hasattr(self.view_model, '_platform_selection_service') and self.view_model._platform_selection_service:
             self.view_model._platform_selection_service.register_platform_change_listener(
                 self._update_platform_display_label
             )
             self._update_platform_display_label(
                 self.view_model._platform_selection_service.get_current_platform()
             )
        else:
             # Use logger if available, otherwise print
             logger = getattr(self.view_model, '_logger', None)
             if logger: logger.warning("PlatformSelectionService not available when connecting signals in SettingsView.")
             else: print("WARN: PlatformSelectionService not available in SettingsView.")
             self._update_platform_display_label(None)

    def _apply_initial_vm_state(self):
        """Applies the current state from the ViewModel to the widgets."""
        self.ct_path_input.setText(self.view_model._ct_path)
        self.ct_block_name_input.setText(self.view_model._ct_block_name)

        # --- Set Initial Platform Exe Path ---
        self.platform_exe_input.setText(self.view_model._platform_exe_path) # Add this line
        # --- END ---

        self.threshold_spinbox.setValue(self.view_model._threshold)
        self.interval_spinbox.setValue(self.view_model._interval)
        self.duration_spinbox.setValue(self.view_model._duration)
        self.data_dir_label.setText(self.view_model._data_dir)

        # Update platform display
        if hasattr(self.view_model, '_platform_selection_service') and self.view_model._platform_selection_service:
             self._update_platform_display_label(
                 self.view_model._platform_selection_service.get_current_platform()
             )
        else:
             self._update_platform_display_label(None)

        self.remove_verification_button.setEnabled(False) # Starts disabled

        # Update verification status/buttons (triggers internal logic in VM)
        self.view_model._update_verification_status()
        # _update_verification_status calculates the state, now apply it
        initial_read_only_state = self.view_model._config_repo.get_verified_block(
            self.view_model._selected_platform
        ).value is not None
        self._set_block_name_input_read_only(initial_read_only_state)

    # --- Slots for ViewModel Signals ---

    @Slot(str, str)
    def _update_verification_status(self, status_text: str, state_name: str):
        """Updates the verification status label and its style state."""
        self.verify_status_label.setText(status_text)
        self.verify_status_label.setProperty("state", state_name)
        # Force style update
        self.verify_status_label.style().unpolish(self.verify_status_label)
        self.verify_status_label.style().polish(self.verify_status_label)

    @Slot(bool)
    def _set_block_name_input_read_only(self, is_read_only: bool):
        """Sets the read-only state of the Cold Turkey block name input."""
        if self.ct_block_name_input:  # Check widget exists
            self.ct_block_name_input.setReadOnly(is_read_only)
            # Optionally change background color slightly via stylesheet or property
            self.ct_block_name_input.setProperty("readOnly", "true" if is_read_only else "false")
            self.ct_block_name_input.style().unpolish(self.ct_block_name_input)
            self.ct_block_name_input.style().polish(self.ct_block_name_input)

    @Slot(str)
    def _update_platform_display_label(self, platform_name: Optional[str]):
        """Updates the label showing the currently selected platform."""
        display_text = platform_name if platform_name else "None Selected"
        self.platform_display_label.setText(display_text)