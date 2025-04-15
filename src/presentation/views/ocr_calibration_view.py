# src/presentation/views/ocr_calibration_view.py

from typing import Dict, Optional

# --- Qt Imports ---
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QGroupBox, QSplitter,
    QProgressBar, QFormLayout, QSpinBox, QDoubleSpinBox, QCheckBox, QSizePolicy,
    QSpacerItem
)
from PySide6.QtCore import Slot, Qt, QSize
from PySide6.QtGui import QPixmap, QFont # Added QFont

# --- Application Imports ---
from src.presentation.view_models.ocr_calibration_view_model import OcrCalibrationViewModel
# Import custom UI components
from src.presentation.components.ui_components import (
    StyledButton, ActionButton, SecondaryButton, WarningButton, DangerButton, GroupHeader
)

class OcrCalibrationView(QWidget):
    """
    View for the OCR Calibration tab.

    Displays the source image, allows user input for expected value,
    shows calibration progress and results (including detected formats
    and OCR parameters), and provides controls to start calibration and
    save/reset profiles.
    """

    def __init__(self, view_model: OcrCalibrationViewModel, parent: QWidget = None):
        """
        Initialize the OcrCalibrationView.

        Args:
            view_model: The corresponding OcrCalibrationViewModel instance.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.view_model = view_model
        self.pattern_checkboxes: Dict[str, QCheckBox] = {}
        self._setup_ui()
        self._connect_signals()
        self._apply_initial_vm_state()
        # Initial state applied via VM signals on init

    def _setup_ui(self):
        """Creates and arranges the UI elements for the OCR calibration tab."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(15)

        # --- Top Row: Source Image and Calibration Input/Status ---
        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(top_splitter, 1)

        # Left Side: Calibration Source Image
        source_group = QGroupBox("CALIBRATION SOURCE IMAGE")
        source_layout = QVBoxLayout(source_group)

        self.source_preview_label = QLabel("Define Monitor Region with screenshot first.")
        self.source_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.source_preview_label.setStyleSheet(
            "border: 1px solid #ccc; background-color: #f0f0f0; color: #555;"
            "min-height: 150px; min-width: 200px;"
        )
        self.source_preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        source_layout.addWidget(self.source_preview_label, 1)

        self.source_status_label = QLabel("N/A")
        self.source_status_label.setWordWrap(True)
        self.source_status_label.setStyleSheet("font-size: 9pt; color: grey;")
        source_layout.addWidget(self.source_status_label)

        top_splitter.addWidget(source_group)

        # Right Side: Value Calibration Input & Status
        value_group = QGroupBox("VALUE CALIBRATION")
        value_layout = QVBoxLayout(value_group)
        value_layout.setSpacing(8)

        value_layout.addWidget(QLabel(
            "Enter the exact P&L value shown in the screenshot:"
        ))

        input_layout = QHBoxLayout()
        self.expected_value_input = QLineEdit()
        self.expected_value_input.setPlaceholderText("e.g., -$123.45 or (1,234.56) or 100.00")
        input_layout.addWidget(self.expected_value_input, 1)

        self.calibrate_button = WarningButton("Calibrate OCR")
        self.calibrate_button.setMinimumWidth(100)
        input_layout.addWidget(self.calibrate_button)
        value_layout.addLayout(input_layout)

        self.calibration_status_label = QLabel("Ready.")
        self.calibration_status_label.setWordWrap(True)
        self.calibration_status_label.setFont(QFont("Arial", 10, QFont.Weight.Bold)) # Make status bold
        value_layout.addWidget(self.calibration_status_label)

        self.calibration_progress_bar = QProgressBar()
        self.calibration_progress_bar.setTextVisible(True) # Show percentage text
        self.calibration_progress_bar.setVisible(False)
        self.calibration_progress_bar.setMinimum(0)
        self.calibration_progress_bar.setMaximum(100)
        value_layout.addWidget(self.calibration_progress_bar)
        value_layout.addStretch(1)

        top_splitter.addWidget(value_group)
        top_splitter.setSizes([self.width() // 2, self.width() // 2])

        # --- Detected Number Formats Section ---
        self.pattern_group = GroupHeader("DETECTED NUMBER FORMATS (Read-Only)")
        pattern_layout = QVBoxLayout(self.pattern_group)
        pattern_layout.setSpacing(2)
        patterns_info = {
            "dollar": "Positive Currency ($123.45, $1,234.56)",
            "negative": "Negative in Parens ((123.45), ($1,234.56))",
            "negative_dash": "Negative with Dash (-123.45, -$1,234.56, ~123.45)",
            "regular": "Plain Numbers (123.45, -123.45, 1234)"
        }
        for key, description in patterns_info.items():
            checkbox = QCheckBox(description)
            checkbox.setEnabled(False)
            checkbox.setStyleSheet("QCheckBox::indicator { width: 0px; }")
            self.pattern_checkboxes[key] = checkbox
            pattern_layout.addWidget(checkbox)
        self.pattern_group.setVisible(False)
        main_layout.addWidget(self.pattern_group)

        # --- Advanced OCR Parameters Section ---
        self.advanced_group = GroupHeader("ADVANCED OCR PARAMETERS")
        self.advanced_group.setCheckable(True)
        self.advanced_group.setChecked(False)
        advanced_content_widget = QWidget()
        advanced_form_layout = QFormLayout(advanced_content_widget)
        advanced_form_layout.setContentsMargins(9, 9, 9, 9)
        advanced_form_layout.setHorizontalSpacing(20)
        advanced_form_layout.setVerticalSpacing(8)

        self.scale_factor_spinbox = QDoubleSpinBox()
        self.scale_factor_spinbox.setRange(0.5, 10.0); self.scale_factor_spinbox.setSingleStep(0.1)
        self.scale_factor_spinbox.setDecimals(1)
        advanced_form_layout.addRow("Scale Factor:", self.scale_factor_spinbox)

        self.block_size_spinbox = QSpinBox()
        self.block_size_spinbox.setRange(3, 49); self.block_size_spinbox.setSingleStep(2) # Must be odd
        advanced_form_layout.addRow("Threshold Block Size:", self.block_size_spinbox)

        self.c_value_spinbox = QSpinBox()
        self.c_value_spinbox.setRange(0, 15); self.c_value_spinbox.setSingleStep(1)
        advanced_form_layout.addRow("Threshold C Value:", self.c_value_spinbox)

        self.denoise_h_spinbox = QSpinBox()
        self.denoise_h_spinbox.setRange(1, 30); self.denoise_h_spinbox.setSingleStep(1)
        advanced_form_layout.addRow("Denoise Strength (h):", self.denoise_h_spinbox)

        self.tesseract_config_input = QLineEdit()
        self.tesseract_config_input.setPlaceholderText("e.g., --oem 3 --psm 7")
        advanced_form_layout.addRow("Tesseract Config:", self.tesseract_config_input)

        self.invert_colors_checkbox = QCheckBox("Invert Colors (for light text on dark background)")
        advanced_form_layout.addRow("", self.invert_colors_checkbox)

        advanced_group_layout = QVBoxLayout(self.advanced_group)
        advanced_group_layout.setContentsMargins(0, 20, 0, 0)
        advanced_group_layout.setSpacing(0)
        advanced_group_layout.addWidget(advanced_content_widget)
        self.advanced_group.toggled.connect(advanced_content_widget.setVisible)
        advanced_content_widget.setVisible(False)

        main_layout.addWidget(self.advanced_group)
        main_layout.addStretch(1)

        # --- Bottom Buttons ---
        bottom_button_layout = QHBoxLayout()
        bottom_button_layout.addStretch(1)
        self.reset_button = SecondaryButton("Reset to Default")
        self.save_manual_edits_button = StyledButton("Save Parameter Edits") # Fix 3 Button
        self.save_calibrated_button = ActionButton("Save Calibrated Profile")
        bottom_button_layout.addWidget(self.reset_button)
        bottom_button_layout.addWidget(self.save_manual_edits_button) # Add new button
        bottom_button_layout.addWidget(self.save_calibrated_button)
        main_layout.addLayout(bottom_button_layout)


    def _connect_signals(self):
        """Connect signals from widgets to ViewModel slots and vice versa."""
        # --- View -> ViewModel ---
        self.expected_value_input.editingFinished.connect(
            lambda: self.view_model.set_expected_value(self.expected_value_input.text())
        )
        self.calibrate_button.clicked.connect(self.view_model.start_calibration)
        self.save_calibrated_button.clicked.connect(self.view_model.save_calibrated_profile) # Connect correct button
        self.save_manual_edits_button.clicked.connect(self.view_model.save_manual_ocr_edits) # Connect new button
        self.reset_button.clicked.connect(self.view_model.reset_profile_to_default)

        # Connect advanced parameter widgets to VM setters (needed for Fix 3)
        self.scale_factor_spinbox.valueChanged.connect(self.view_model.set_scale_factor)
        self.block_size_spinbox.valueChanged.connect(self.view_model.set_block_size)
        self.c_value_spinbox.valueChanged.connect(self.view_model.set_c_value)
        self.denoise_h_spinbox.valueChanged.connect(self.view_model.set_denoise_h)
        self.tesseract_config_input.editingFinished.connect(
            lambda: self.view_model.set_tesseract_config(self.tesseract_config_input.text())
        )
        self.invert_colors_checkbox.toggled.connect(self.view_model.set_invert_colors)

        # --- ViewModel -> View ---
        self.view_model.calibration_source_preview_changed.connect(self._update_source_preview)
        self.view_model.calibration_source_status_text_changed.connect(self.source_status_label.setText)
        self.view_model.can_calibrate_changed.connect(self.calibrate_button.setEnabled)

        self.view_model.calibration_in_progress_changed.connect(self._handle_calibration_in_progress)
        self.view_model.calibration_progress_changed.connect(self._update_calibration_progress)
        self.view_model.calibration_status_text_changed.connect(self._update_calibration_status)

        self.view_model.detected_patterns_changed.connect(self._update_detected_patterns)
        self.view_model.show_detected_patterns_changed.connect(self.pattern_group.setVisible)

        self.view_model.scale_factor_changed.connect(self.scale_factor_spinbox.setValue)
        self.view_model.threshold_block_size_changed.connect(self.block_size_spinbox.setValue)
        self.view_model.threshold_c_changed.connect(self.c_value_spinbox.setValue)
        self.view_model.denoise_h_changed.connect(self.denoise_h_spinbox.setValue)
        self.view_model.tesseract_config_changed.connect(self.tesseract_config_input.setText)
        self.view_model.invert_colors_changed.connect(self.invert_colors_checkbox.setChecked)

        self.view_model.can_save_calibrated_profile_changed.connect(self.save_calibrated_button.setEnabled)
        self.view_model.can_save_manual_edits_changed.connect(self.save_manual_edits_button.setEnabled)

    def _apply_initial_vm_state(self):
        """Applies the current state from the ViewModel to the widgets."""
        # Source Preview & Status - Read directly from VM state
        self._update_source_preview(self.view_model._source_preview_pixmap)
        self.source_status_label.setText(self.view_model._source_status_text)
        self.calibrate_button.setEnabled(self.view_model._calibration_source_image_path is not None)

        # Calibration Status & Progress (Starts inactive)
        self._update_calibration_status("Ready.", "gray") # Set initial text
        self._handle_calibration_in_progress(False) # Ensure progress bar hidden

        # Detected Patterns (Starts hidden)
        self.pattern_group.setVisible(False)
        self._update_detected_patterns({}) # Clear checkboxes initially

        # Advanced OCR Parameters from VM's current profile state
        # Ensure VM's _current_ocr_profile is correctly initialized/loaded
        profile = self.view_model._current_ocr_profile
        self.scale_factor_spinbox.setValue(profile.scale_factor)
        # Ensure block size is odd when setting view (important!)
        block_size = profile.threshold_block_size
        if block_size % 2 == 0 and block_size > 1: block_size -=1 # Should not happen if VM setter fixes, but safe check
        elif block_size < 3: block_size = 3
        self.block_size_spinbox.setValue(block_size)
        self.c_value_spinbox.setValue(profile.threshold_c)
        self.denoise_h_spinbox.setValue(profile.denoise_h)
        self.tesseract_config_input.setText(profile.tesseract_config)
        self.invert_colors_checkbox.setChecked(profile.invert_colors)

        # Button States
        self.save_calibrated_button.setEnabled(False) # Always starts disabled
        self.save_manual_edits_button.setEnabled(self.view_model._selected_platform is not None)
        self.reset_button.setEnabled(self.view_model._selected_platform is not None)
    # --- Slots for ViewModel Signals ---

    @Slot(QPixmap)
    def _update_source_preview(self, pixmap: QPixmap):
        """Updates the source image preview."""
        if pixmap and not pixmap.isNull():
            # Scale pixmap to fit the label while preserving aspect ratio
            # Use label's current size for better responsiveness if window is resized
            scaled_pixmap = pixmap.scaled(
                self.source_preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.source_preview_label.setPixmap(scaled_pixmap)
            self.source_preview_label.setText("")
        else:
            self.source_preview_label.setPixmap(QPixmap())
            self.source_preview_label.setText("Define Monitor Region with screenshot first.")

    @Slot(bool)
    def _handle_calibration_in_progress(self, in_progress: bool):
        """Handles UI changes when calibration starts/stops."""
        self.calibration_progress_bar.setVisible(in_progress)
        if in_progress:
            self.calibration_progress_bar.setValue(0) # Reset progress on start
            self.calibration_progress_bar.setFormat("Calibrating... %p%")
        else:
            self.calibration_progress_bar.setFormat("") # Clear text when done

        self.calibrate_button.setDisabled(in_progress)
        self.expected_value_input.setDisabled(in_progress)
        # Also disable editing advanced params during calibration
        self.advanced_group.setDisabled(in_progress)


    @Slot(int, str)
    def _update_calibration_progress(self, percent: int, message: str):
        """Updates the progress bar value and format text."""
        self.calibration_progress_bar.setValue(percent)
        self.calibration_progress_bar.setFormat(f"{message} %p%") # Show message in progress bar


    @Slot(str, str)
    def _update_calibration_status(self, message: str, color_name: str):
        """Updates the main calibration status label text and color."""
        self.calibration_status_label.setText(message)
        self.calibration_status_label.setStyleSheet(f"color: {color_name}; font-weight: bold;")

    @Slot(dict)
    def _update_detected_patterns(self, patterns_state: Dict[str, bool]):
        """Updates the checkboxes for detected number formats."""
        for key, checkbox in self.pattern_checkboxes.items():
            if checkbox: # Check if checkbox exists
                is_detected = patterns_state.get(key, False)
                checkbox.setChecked(is_detected)
                font = checkbox.font()
                font.setBold(is_detected)
                checkbox.setFont(font)
                checkbox.setStyleSheet("QCheckBox::indicator { width: %spx; }" % ("13" if is_detected else "0"))