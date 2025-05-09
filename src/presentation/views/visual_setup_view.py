# src/presentation/views/visual_setup_view.py

from typing import List, Dict, Any, Optional  # Ensure Optional is imported

# --- Qt Imports ---
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QListWidget,
    QListWidgetItem, QPushButton, QSizePolicy, QLineEdit, QProgressBar,
    QFormLayout, QSpinBox, QDoubleSpinBox, QCheckBox, QSpacerItem, QGroupBox
)
from PySide6.QtCore import Slot, Qt, QSize, QTimer
from PySide6.QtGui import QPixmap, QColor

# --- Application Imports ---
# Assuming VisualSetupViewModel will be in the same directory or path is adjusted
from src.presentation.view_models.visual_setup_view_model import VisualSetupViewModel
from src.presentation.components.ui_components import (
    StyledButton, ActionButton, SecondaryButton, DangerButton  # Add WarningButton if calibrate is Warning
)
from src.presentation.components.region_entry_widget import RegionEntryWidget


class VisualSetupView(QWidget):
    """
    View for the consolidated "Visual Setup" tab.
    Handles UI for P&L Monitor Region, Flatten Regions, and OCR Calibration.
    """

    def __init__(self, view_model: VisualSetupViewModel, parent: QWidget = None):
        super().__init__(parent)
        self.view_model = view_model
        # Initialize UI element attributes that will be created in _setup_ui
        self.monitor_preview_label: Optional[QLabel] = None
        self.monitor_status_badge: Optional[QLabel] = None  # New from your refactored RegionSetupView
        self.monitor_coords_label: Optional[QLabel] = None
        self.define_edit_monitor_button: Optional[QPushButton] = None
        self.flash_monitor_button: Optional[QPushButton] = None
        self.delete_monitor_button: Optional[QPushButton] = None

        self.flatten_list_widget: Optional[QListWidget] = None
        self.flatten_count_badge: Optional[QLabel] = None  # New from your refactored RegionSetupView
        self.add_flatten_button: Optional[QPushButton] = None

        # OCR Calibration elements
        self.expected_value_input: Optional[QLineEdit] = None
        self.calibrate_button: Optional[QPushButton] = None  # Was WarningButton
        self.calibration_status_label: Optional[QLabel] = None
        self.calibration_progress_bar: Optional[QProgressBar] = None
        self.ocr_source_status_label: Optional[QLabel] = None  # Replaces old source_status_label

        self.advanced_ocr_group: Optional[QGroupBox] = None  # Or QFrame if you change GroupHeader
        self.scale_factor_spinbox: Optional[QDoubleSpinBox] = None
        self.block_size_spinbox: Optional[QSpinBox] = None
        self.c_value_spinbox: Optional[QSpinBox] = None
        self.denoise_h_spinbox: Optional[QSpinBox] = None
        self.tesseract_config_input: Optional[QLineEdit] = None
        self.invert_colors_checkbox: Optional[QCheckBox] = None

        self.reset_ocr_button: Optional[QPushButton] = None
        self.save_manual_ocr_edits_button: Optional[QPushButton] = None
        self.save_calibrated_ocr_profile_button: Optional[QPushButton] = None

        self._setup_ui()
        self._connect_signals()

        self.view_model._logger.debug("VisualSetupView: Scheduling initial UI refresh via VM.refresh_ui_signals.")
        QTimer.singleShot(0, self.view_model.refresh_ui_signals)

    def _setup_ui(self):
        """Creates and arranges the UI elements for the Visual Setup tab."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # --- Top Row: Monitor Region (Left) & OCR Calibration Input (Right) ---
        top_row_layout = QHBoxLayout()
        top_row_layout.setSpacing(15)

        # --- Monitor Region Panel (Left Side) ---
        monitor_panel = QFrame()
        monitor_panel.setObjectName("vsMonitorRegionPanel")  # vs for VisualSetup
        monitor_panel.setProperty("class", "contentSectionPanel")
        monitor_layout = QVBoxLayout(monitor_panel)
        monitor_layout.setContentsMargins(15, 15, 15, 15);
        monitor_layout.setSpacing(10)

        # Header
        monitor_header_layout = QHBoxLayout()
        monitor_title = QLabel("P&L MONITOR REGION");
        monitor_title.setProperty("class", "panelTitle")
        monitor_header_layout.addWidget(monitor_title, 1)
        self.monitor_status_badge = QLabel("N/A");
        self.monitor_status_badge.setObjectName("vsMonitorStatusBadge")
        monitor_header_layout.addWidget(self.monitor_status_badge)
        # TODO: Add monitor icon if desired
        monitor_layout.addLayout(monitor_header_layout)
        monitor_divider = QFrame();
        monitor_divider.setFrameShape(QFrame.Shape.HLine);
        monitor_divider.setObjectName("panelDivider")
        monitor_layout.addWidget(monitor_divider)

        # Preview
        self.monitor_preview_label = QLabel("Define region to see preview");
        self.monitor_preview_label.setObjectName("vsMonitorPreviewLabel")
        self.monitor_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.monitor_preview_label.setMinimumHeight(80);
        self.monitor_preview_label.setMaximumHeight(120)  # Increased max height slightly
        self.monitor_preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        monitor_layout.addWidget(self.monitor_preview_label)

        self.monitor_coords_label = QLabel("Coordinates: N/A");
        self.monitor_coords_label.setObjectName("vsMonitorCoordsLabel")
        monitor_layout.addWidget(self.monitor_coords_label)

        monitor_buttons = QHBoxLayout()
        self.define_edit_monitor_button = StyledButton("Define / Edit P&L Region", icon=":/icons/edit.svg")
        self.flash_monitor_button = SecondaryButton("Flash P&L Region", icon=":/icons/zap.svg")
        self.delete_monitor_button = DangerButton("Delete P&L Region", icon=":/icons/trash.svg")
        monitor_buttons.addWidget(self.define_edit_monitor_button);
        monitor_buttons.addStretch()
        monitor_buttons.addWidget(self.flash_monitor_button);
        monitor_buttons.addWidget(self.delete_monitor_button)
        monitor_layout.addLayout(monitor_buttons)
        monitor_layout.addStretch(1)
        top_row_layout.addWidget(monitor_panel, 2)  # Give more space to monitor region

        # --- OCR Calibration Panel (Right Side) ---
        ocr_panel = QFrame()
        ocr_panel.setObjectName("vsOcrCalibrationPanel")
        ocr_panel.setProperty("class", "contentSectionPanel")
        ocr_layout = QVBoxLayout(ocr_panel)
        ocr_layout.setContentsMargins(15, 15, 15, 15);
        ocr_layout.setSpacing(10)

        # Header
        ocr_title = QLabel("OCR CALIBRATION");
        ocr_title.setProperty("class", "panelTitle")
        ocr_layout.addWidget(ocr_title)
        ocr_divider = QFrame();
        ocr_divider.setFrameShape(QFrame.Shape.HLine);
        ocr_divider.setObjectName("panelDivider")
        ocr_layout.addWidget(ocr_divider)

        self.ocr_source_status_label = QLabel("P&L Monitor Region screenshot will be used.")
        self.ocr_source_status_label.setObjectName("vsOcrSourceStatusLabel")
        self.ocr_source_status_label.setWordWrap(True)
        ocr_layout.addWidget(self.ocr_source_status_label)

        ocr_layout.addWidget(QLabel("Enter exact P&L value from Monitor Region preview:"))
        ocr_input_layout = QHBoxLayout()
        self.expected_value_input = QLineEdit();
        self.expected_value_input.setObjectName("vsExpectedValueInput")
        self.expected_value_input.setPlaceholderText("e.g., -$123.45")
        ocr_input_layout.addWidget(self.expected_value_input, 1)
        from src.presentation.components.ui_components import WarningButton  # Ensure import
        self.calibrate_button = WarningButton("Calibrate OCR", icon=":/icons/settings.svg")  # Using WarningButton
        ocr_input_layout.addWidget(self.calibrate_button)
        ocr_layout.addLayout(ocr_input_layout)

        self.calibration_status_label = QLabel("Ready.");
        self.calibration_status_label.setObjectName("vsCalibrationStatusLabel")
        self.calibration_status_label.setProperty("state", "info");
        self.calibration_status_label.setWordWrap(True)
        ocr_layout.addWidget(self.calibration_status_label)
        self.calibration_progress_bar = QProgressBar();
        self.calibration_progress_bar.setObjectName("vsCalibrationProgress")
        self.calibration_progress_bar.setVisible(False);
        self.calibration_progress_bar.setTextVisible(True)
        ocr_layout.addWidget(self.calibration_progress_bar)

        # Advanced OCR Parameters Group (QGroupBox or QFrame)
        self.advanced_ocr_group = QGroupBox("Advanced OCR Parameters");
        self.advanced_ocr_group.setObjectName("vsAdvancedOcrGroup")
        self.advanced_ocr_group.setCheckable(True);
        self.advanced_ocr_group.setChecked(False)
        self.advanced_ocr_group.setProperty("class", "contentSectionPanel")  # Style as panel

        advanced_content_widget = QWidget()
        adv_form = QFormLayout(advanced_content_widget)
        adv_form.setContentsMargins(10, 5, 10, 5);
        adv_form.setSpacing(8)
        self.scale_factor_spinbox = QDoubleSpinBox();
        self.scale_factor_spinbox.setRange(0.5, 10);
        self.scale_factor_spinbox.setSingleStep(0.1)
        adv_form.addRow("Scale Factor:", self.scale_factor_spinbox)
        self.block_size_spinbox = QSpinBox();
        self.block_size_spinbox.setRange(3, 49);
        self.block_size_spinbox.setSingleStep(2)
        adv_form.addRow("Block Size (Odd):", self.block_size_spinbox)
        self.c_value_spinbox = QSpinBox();
        self.c_value_spinbox.setRange(0, 15);
        self.c_value_spinbox.setSingleStep(1)
        adv_form.addRow("C Value:", self.c_value_spinbox)
        self.denoise_h_spinbox = QSpinBox();
        self.denoise_h_spinbox.setRange(0, 30);
        self.denoise_h_spinbox.setSingleStep(1)  # Allow 0 for no denoise
        adv_form.addRow("Denoise Strength:", self.denoise_h_spinbox)
        self.tesseract_config_input = QLineEdit();
        self.tesseract_config_input.setPlaceholderText("--psm 7 -l eng")
        adv_form.addRow("Tesseract Config:", self.tesseract_config_input)
        self.invert_colors_checkbox = QCheckBox("Invert Colors");
        adv_form.addRow("", self.invert_colors_checkbox)

        # Set content widget for QGroupBox properly
        # QGroupBoxes need a layout set on themselves, then add the content widget to that layout.
        # Or, simpler: set the layout directly on the QGroupBox's content area if it has one.
        # Let's ensure GroupBox's layout is correctly managed.
        # It's often easier to have a QWidget as content, then set its layout.
        # advanced_group_main_layout = QVBoxLayout() # Create a layout for the QGroupBox
        # advanced_group_main_layout.addWidget(advanced_content_widget)
        # self.advanced_ocr_group.setLayout(advanced_group_main_layout)
        # A QGroupBox directly accepts a layout.
        # If GroupHeader is used, it should handle its own internal layout.
        # For a standard QGroupBox:
        layout_for_groupbox_content = QVBoxLayout()  # This layout is for the *content* of the groupbox
        layout_for_groupbox_content.addWidget(advanced_content_widget)
        self.advanced_ocr_group.setLayout(layout_for_groupbox_content)  # Set this as the layout for the groupbox

        self.advanced_ocr_group.toggled.connect(advanced_content_widget.setVisible)
        advanced_content_widget.setVisible(False)
        ocr_layout.addWidget(self.advanced_ocr_group)

        ocr_buttons_layout = QHBoxLayout()
        self.reset_ocr_button = SecondaryButton("Reset OCR Params");
        ocr_buttons_layout.addWidget(self.reset_ocr_button)
        ocr_buttons_layout.addStretch()
        self.save_manual_ocr_edits_button = StyledButton("Save OCR Params");
        ocr_buttons_layout.addWidget(self.save_manual_ocr_edits_button)
        self.save_calibrated_ocr_profile_button = ActionButton("Save Calibrated Profile");
        ocr_buttons_layout.addWidget(self.save_calibrated_ocr_profile_button)
        ocr_layout.addLayout(ocr_buttons_layout)
        ocr_layout.addStretch(1)
        top_row_layout.addWidget(ocr_panel, 3)  # Give more space to OCR

        main_layout.addLayout(top_row_layout)  # Add top row (Monitor + OCR)

        # --- Flatten Regions Panel (Full Width Below Top Row) ---
        flatten_panel = QFrame()
        flatten_panel.setObjectName("vsFlattenRegionsPanel")
        flatten_panel.setProperty("class", "contentSectionPanel")
        flatten_layout = QVBoxLayout(flatten_panel)
        flatten_layout.setContentsMargins(15, 15, 15, 15);
        flatten_layout.setSpacing(10)

        flatten_header_layout = QHBoxLayout()
        flatten_title = QLabel("FLATTEN POSITION REGIONS");
        flatten_title.setProperty("class", "panelTitle")
        flatten_header_layout.addWidget(flatten_title, 1)
        self.flatten_count_badge = QLabel("0 Defined");
        self.flatten_count_badge.setObjectName("vsFlattenCountBadge")
        flatten_header_layout.addWidget(self.flatten_count_badge)
        flatten_layout.addLayout(flatten_header_layout)
        flatten_divider = QFrame();
        flatten_divider.setFrameShape(QFrame.Shape.HLine);
        flatten_divider.setObjectName("panelDivider")
        flatten_layout.addWidget(flatten_divider)

        self.flatten_list_widget = QListWidget();
        self.flatten_list_widget.setObjectName("vsFlattenListWidget")
        flatten_layout.addWidget(self.flatten_list_widget, 1)  # Stretch list

        add_flatten_layout = QHBoxLayout()
        add_flatten_layout.addStretch(1)
        self.add_flatten_button = ActionButton("Add Flatten Region", icon=":/icons/plus.svg")
        add_flatten_layout.addWidget(self.add_flatten_button)
        flatten_layout.addLayout(add_flatten_layout)
        main_layout.addWidget(flatten_panel, 1)  # Give flatten panel vertical stretch factor

        # --- Help Panel (Optional, can be removed or integrated) ---
        help_panel = QFrame()
        help_panel.setObjectName("vsHelpPanel")
        help_panel.setProperty("class", "contentSectionPanel")
        help_layout = QVBoxLayout(help_panel)
        help_layout.setContentsMargins(15, 15, 15, 15);
        help_layout.setSpacing(10)
        help_title = QLabel("HELP & GUIDANCE");
        help_title.setProperty("class", "panelTitle")
        help_layout.addWidget(help_title)
        help_divider = QFrame();
        help_divider.setFrameShape(QFrame.Shape.HLine);
        help_divider.setObjectName("panelDivider")
        help_layout.addWidget(help_divider)
        help_text = QLabel(
            "1. Define P&L Monitor Region.\n2. Add Flatten Regions.\n3. Calibrate OCR for P&L.\n4. Use Flash to verify.")
        help_text.setWordWrap(True)
        help_layout.addWidget(help_text)
        help_layout.addStretch(1)
        main_layout.addWidget(help_panel)  # No stretch for help panel by default


    def _connect_signals(self):
        """Connect signals for the VisualSetupView."""
        if not self.view_model: return

        # --- Monitor Region Connections ---
        self.define_edit_monitor_button.clicked.connect(self.view_model.define_edit_monitor_region)
        self.delete_monitor_button.clicked.connect(self.view_model.delete_monitor_region)
        self.flash_monitor_button.clicked.connect(self.view_model.flash_monitor_region)
        self.view_model.monitor_region_status_changed.connect(
            self.monitor_status_badge.setText)  # Assuming badge shows status directly
        self.view_model.monitor_region_coords_text_changed.connect(self.monitor_coords_label.setText)
        self.view_model.monitor_region_preview_changed.connect(self.monitor_preview_label.setPixmap)  # Simplified
        self.view_model.can_delete_monitor_region_changed.connect(self.delete_monitor_button.setEnabled)
        self.view_model.can_flash_monitor_region_changed.connect(self.flash_monitor_button.setEnabled)

        # --- Flatten Regions Connections ---
        self.add_flatten_button.clicked.connect(self.view_model.add_flatten_region)
        self.view_model.flatten_regions_list_updated.connect(self._update_flatten_list_display)  # Renamed for clarity
        # self.view_model.flatten_region_count_changed.connect(self.flatten_count_badge.setText) # Connect to new signal if VM provides it

        # --- OCR Calibration Connections ---
        self.expected_value_input.editingFinished.connect(
            lambda: self.view_model.set_expected_value(self.expected_value_input.text()))
        self.calibrate_button.clicked.connect(self.view_model.start_calibration)
        self.view_model.calibration_source_status_text_changed.connect(self.ocr_source_status_label.setText)
        self.view_model.can_calibrate_changed.connect(self.calibrate_button.setEnabled)
        self.view_model.expected_value_changed.connect(self.expected_value_input.setText)
        self.view_model.calibration_in_progress_changed.connect(self._handle_ocr_calibration_in_progress)
        self.view_model.calibration_progress_changed.connect(self._update_ocr_calibration_progress)
        self.view_model.calibration_status_text_changed.connect(self._update_ocr_calibration_status_label)

        # Advanced OCR Params
        self.scale_factor_spinbox.valueChanged.connect(self.view_model.set_scale_factor)
        self.block_size_spinbox.valueChanged.connect(self.view_model.set_block_size)
        self.c_value_spinbox.valueChanged.connect(self.view_model.set_c_value)
        self.denoise_h_spinbox.valueChanged.connect(self.view_model.set_denoise_h)
        self.tesseract_config_input.editingFinished.connect(
            lambda: self.view_model.set_tesseract_config(self.tesseract_config_input.text()))
        self.invert_colors_checkbox.toggled.connect(self.view_model.set_invert_colors)

        self.view_model.scale_factor_changed.connect(self.scale_factor_spinbox.setValue)
        self.view_model.threshold_block_size_changed.connect(self.block_size_spinbox.setValue)
        self.view_model.threshold_c_changed.connect(self.c_value_spinbox.setValue)
        self.view_model.denoise_h_changed.connect(self.denoise_h_spinbox.setValue)
        self.view_model.tesseract_config_changed.connect(self.tesseract_config_input.setText)
        self.view_model.invert_colors_changed.connect(self.invert_colors_checkbox.setChecked)

        self.reset_ocr_button.clicked.connect(self.view_model.reset_profile_to_default)
        self.save_manual_ocr_edits_button.clicked.connect(self.view_model.save_manual_ocr_edits)
        self.save_calibrated_ocr_profile_button.clicked.connect(self.view_model.save_calibrated_profile)
        self.view_model.can_save_calibrated_profile_changed.connect(self.save_calibrated_ocr_profile_button.setEnabled)
        self.view_model.can_save_manual_edits_changed.connect(self.save_manual_ocr_edits_button.setEnabled)

    # --- Slots for ViewModel Signals ---
    # (Need to adapt/merge slots from RegionSetupView and OcrCalibrationView)

    @Slot(list)  # Was _update_flatten_list
    def _update_flatten_list_display(self, flatten_regions_data: List[Dict[str, Any]]):
        self.flatten_list_widget.clear()
        if not flatten_regions_data:
            # ... (placeholder item logic as before) ...
            item = QListWidgetItem("No flatten regions defined.")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)  # Make it unselectable
            self.flatten_list_widget.addItem(item)
            if self.flatten_count_badge: self.flatten_count_badge.setText("0 Defined")
            return

        if self.flatten_count_badge: self.flatten_count_badge.setText(f"{len(flatten_regions_data)} Defined")

        for region_data in flatten_regions_data:
            entry_widget = RegionEntryWidget(
                region_id=region_data.get("name", "Unknown"),
                coords_text=region_data.get("coords_text", "N/A"),
                preview_pixmap=region_data.get("preview_pixmap", QPixmap())
            )
            entry_widget.edit_requested.connect(self.view_model.edit_flatten_region)
            entry_widget.delete_requested.connect(self.view_model.delete_flatten_region)
            entry_widget.flash_requested.connect(self.view_model.flash_flatten_region)

            list_item = QListWidgetItem(self.flatten_list_widget)
            list_item.setSizeHint(entry_widget.sizeHint())
            self.flatten_list_widget.addItem(list_item)
            self.flatten_list_widget.setItemWidget(list_item, entry_widget)

    # Slots from OcrCalibrationView (renamed for clarity if needed)
    @Slot(bool)  # Was _handle_calibration_in_progress
    def _handle_ocr_calibration_in_progress(self, in_progress: bool):
        self.calibration_progress_bar.setVisible(in_progress)
        if in_progress:
            self.calibration_progress_bar.setValue(0); self.calibration_progress_bar.setFormat("Calibrating... %p%")
        else:
            self.calibration_progress_bar.setFormat("")
        self.calibrate_button.setDisabled(in_progress)
        self.expected_value_input.setDisabled(in_progress)
        if self.advanced_ocr_group: self.advanced_ocr_group.setDisabled(in_progress)

    @Slot(int, str)  # Was _update_calibration_progress
    def _update_ocr_calibration_progress(self, percent: int, message: str):
        self.calibration_progress_bar.setValue(percent)
        self.calibration_progress_bar.setFormat(f"{message} %p%")

    @Slot(str, str)  # Was _update_calibration_status
    def _update_ocr_calibration_status_label(self, message: str, color_name: str):
        self.calibration_status_label.setText(message)
        state_map = {"green": "success", "red": "error", "orange": "busy", "black": "busy", "gray": "info"}
        state = state_map.get(color_name.lower(), "info")
        self.calibration_status_label.setProperty("state", state)
        self.calibration_status_label.style().unpolish(self.calibration_status_label)
        self.calibration_status_label.style().polish(self.calibration_status_label)

    # You might need to adapt _update_monitor_preview and _update_monitor_status_label
    # if their direct connections to labels are changed due to new badge, etc.
    # For example, monitor_status_badge.setText now handles the status text.