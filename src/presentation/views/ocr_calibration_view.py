# src/presentation/views/ocr_calibration_view.py

from typing import Dict, Optional

# --- Qt Imports ---
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QGroupBox, QSplitter,
    QProgressBar, QFormLayout, QSpinBox, QDoubleSpinBox, QCheckBox, QSizePolicy,
    QSpacerItem
)
# <<< Add QTimer Import >>>
from PySide6.QtCore import Slot, Qt, QSize, QTimer
from PySide6.QtGui import QPixmap, QFont

# --- Application Imports ---
from src.presentation.styles.style_manager import StyleManager
from src.presentation.view_models.ocr_calibration_view_model import OcrCalibrationViewModel
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
        # Schedule the ViewModel to re-emit its state signals once the event loop starts
        self.view_model._logger.debug("View: Scheduling initial UI refresh via VM.refresh_ui_signals.")
        QTimer.singleShot(0, self.view_model.refresh_ui_signals)

    def _setup_ui(self):
        """Creates and arranges the UI elements for the OCR calibration tab."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(15)

        # --- Top Row: Source Image and Calibration Input/Status ---
        # <<< Replace QSplitter with QHBoxLayout >>>
        top_layout = QHBoxLayout()
        top_layout.setSpacing(15) # Add spacing between the two top groups

        # Left Side: Calibration Source Image
        source_group = QGroupBox("CALIBRATION SOURCE IMAGE")
        source_group.setObjectName("sourceGroup")
        source_group.setProperty("class", "card")  # ADD THIS LINE
        source_layout = QVBoxLayout(source_group)

        self.source_preview_label = QLabel("Define Monitor Region with screenshot first.")
        self.source_preview_label.setObjectName("sourcePreviewLabel")
        self.source_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # <<< Adjust SizePolicy and add Maximum Height >>>
        self.source_preview_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred) # Don't expand aggressively
        self.source_preview_label.setMinimumSize(100, 50) # Smaller minimum height
        self.source_preview_label.setMaximumHeight(75)  # <<< SET MAX HEIGHT (like region setup)
        source_layout.addWidget(self.source_preview_label, 0) # <<< REMOVE STRETCH FACTOR (let QSS/maxHeight control size)

        self.source_status_label = QLabel("N/A")
        self.source_status_label.setObjectName("sourceStatusLabel")
        self.source_status_label.setWordWrap(True)
        source_layout.addWidget(self.source_status_label) # No stretch factor
        source_layout.addStretch(1) # Add stretch *below* content if needed to push it up

        # <<< Add source_group to top_layout >>>
        top_layout.addWidget(source_group, 1) # Allow horizontal stretch (adjust ratio if needed)

        # Right Side: Value Calibration Input & Status
        value_group = QGroupBox("VALUE CALIBRATION")
        value_group.setObjectName("valueGroup")
        value_group.setProperty("class", "card")
        value_layout = QVBoxLayout(value_group)
        value_layout.setSpacing(8)

        value_layout.addWidget(QLabel(
            "Enter the exact P&L value shown in the screenshot:"
        ))

        input_layout = QHBoxLayout()
        self.expected_value_input = QLineEdit()
        self.expected_value_input.setObjectName("valueInput")
        self.expected_value_input.setPlaceholderText("e.g., -$123.45 or (1,234.56) or 100.00")
        input_layout.addWidget(self.expected_value_input, 1) # Allow input to stretch

        self.calibrate_button = WarningButton("Calibrate OCR")
        self.calibrate_button.setMinimumWidth(100)
        input_layout.addWidget(self.calibrate_button)
        value_layout.addLayout(input_layout)

        self.calibration_status_label = QLabel("Ready.")
        self.calibration_status_label.setObjectName("calibrationStatusLabel")
        self.calibration_status_label.setProperty("state", "ready")
        self.calibration_status_label.setWordWrap(True)
        value_layout.addWidget(self.calibration_status_label)

        self.calibration_progress_bar = QProgressBar()
        self.calibration_progress_bar.setObjectName("calibrationProgressBar")
        self.calibration_progress_bar.setTextVisible(True)
        self.calibration_progress_bar.setVisible(False)
        self.calibration_progress_bar.setMinimum(0)
        self.calibration_progress_bar.setMaximum(100)
        value_layout.addWidget(self.calibration_progress_bar)
        value_layout.addStretch(1) # Push elements up

        # <<< Add value_group to top_layout >>>
        top_layout.addWidget(value_group, 1) # Allow horizontal stretch (adjust ratio if needed)

        # <<< Add top_layout to main_layout (NO STRETCH) >>>
        main_layout.addLayout(top_layout) # Add the QHBoxLayout, don't give it vertical stretch

        # --- Advanced OCR Parameters Section ---
        self.advanced_group = GroupHeader("ADVANCED OCR PARAMETERS")
        self.advanced_group.setObjectName("advancedGroup")
        self.advanced_group.setProperty("class", "card")
        self.advanced_group.setCheckable(True)
        self.advanced_group.setChecked(False) # Start collapsed
        advanced_content_widget = QWidget()
        advanced_form_layout = QFormLayout(advanced_content_widget)
        advanced_form_layout.setContentsMargins(9, 9, 9, 9)
        advanced_form_layout.setHorizontalSpacing(20)
        advanced_form_layout.setVerticalSpacing(8)

        # Create and add widgets to the form layout
        self.scale_factor_spinbox = QDoubleSpinBox()
        self.scale_factor_spinbox.setRange(0.5, 10.0); self.scale_factor_spinbox.setSingleStep(0.1)
        self.scale_factor_spinbox.setDecimals(1)
        advanced_form_layout.addRow("Scale Factor:", self.scale_factor_spinbox)

        self.block_size_spinbox = QSpinBox()
        self.block_size_spinbox.setRange(3, 49); self.block_size_spinbox.setSingleStep(2) # Must be odd
        advanced_form_layout.addRow("Threshold Block Size (Odd):", self.block_size_spinbox)

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
        advanced_form_layout.addRow("", self.invert_colors_checkbox) # Add checkbox without a label on the left

        # Add the content widget to the main layout of the GroupHeader
        advanced_group_main_layout = QVBoxLayout(self.advanced_group)
        advanced_group_main_layout.setContentsMargins(0, 20, 0, 0) # Adjust top margin
        advanced_group_main_layout.setSpacing(0)
        advanced_group_main_layout.addWidget(advanced_content_widget)

        # Connect toggle signal and set initial visibility
        self.advanced_group.toggled.connect(advanced_content_widget.setVisible)
        advanced_content_widget.setVisible(False) # Start collapsed

        main_layout.addWidget(self.advanced_group)
        main_layout.addStretch(1) # Push everything above this up

        # --- Bottom Buttons ---
        bottom_button_layout = QHBoxLayout()
        bottom_button_layout.addStretch(1)
        self.reset_button = SecondaryButton("Reset to Default")
        self.reset_button.setObjectName("resetButton")
        self.save_manual_edits_button = StyledButton("Save Parameter Edits")
        self.save_manual_edits_button.setObjectName("saveManualEditsButton")
        self.save_calibrated_button = ActionButton("Save Calibrated Profile")
        self.save_calibrated_button.setObjectName("saveProfileButton")

        bottom_button_layout.addWidget(self.reset_button)
        bottom_button_layout.addWidget(self.save_manual_edits_button)
        bottom_button_layout.addWidget(self.save_calibrated_button)
        main_layout.addLayout(bottom_button_layout)


    def _connect_signals(self):
        """Connect signals from widgets to ViewModel slots and vice versa."""
        # --- View -> ViewModel ---
        self.expected_value_input.editingFinished.connect(
            lambda: self.view_model.set_expected_value(self.expected_value_input.text())
        )
        self.calibrate_button.clicked.connect(self.view_model.start_calibration)
        self.save_calibrated_button.clicked.connect(self.view_model.save_calibrated_profile)
        self.save_manual_edits_button.clicked.connect(self.view_model.save_manual_ocr_edits)
        self.reset_button.clicked.connect(self.view_model.reset_profile_to_default)

        # Connect advanced parameter widgets to VM setters
        self.scale_factor_spinbox.valueChanged.connect(self.view_model.set_scale_factor)
        self.block_size_spinbox.valueChanged.connect(self.view_model.set_block_size)
        self.c_value_spinbox.valueChanged.connect(self.view_model.set_c_value)
        self.denoise_h_spinbox.valueChanged.connect(self.view_model.set_denoise_h)
        self.tesseract_config_input.editingFinished.connect(
            lambda: self.view_model.set_tesseract_config(self.tesseract_config_input.text())
        )
        self.invert_colors_checkbox.toggled.connect(self.view_model.set_invert_colors)

        # --- ViewModel -> View ---
        # These connections remain, the View slots will now be called by
        # the signals emitted from refresh_ui_signals initially,
        # and then by regular state changes later.
        self.view_model.calibration_source_preview_changed.connect(self._update_source_preview)
        self.view_model.calibration_source_status_text_changed.connect(self.source_status_label.setText)
        self.view_model.can_calibrate_changed.connect(self.calibrate_button.setEnabled)
        self.view_model.expected_value_changed.connect(self.expected_value_input.setText)
        self.view_model.calibration_in_progress_changed.connect(self._handle_calibration_in_progress)
        self.view_model.calibration_progress_changed.connect(self._update_calibration_progress)
        self.view_model.calibration_status_text_changed.connect(self._update_calibration_status)

        self.view_model.scale_factor_changed.connect(self.scale_factor_spinbox.setValue)
        self.view_model.threshold_block_size_changed.connect(self.block_size_spinbox.setValue)
        self.view_model.threshold_c_changed.connect(self.c_value_spinbox.setValue)
        self.view_model.denoise_h_changed.connect(self.denoise_h_spinbox.setValue)
        self.view_model.tesseract_config_changed.connect(self.tesseract_config_input.setText)
        self.view_model.invert_colors_changed.connect(self.invert_colors_checkbox.setChecked)

        self.view_model.can_save_calibrated_profile_changed.connect(self.save_calibrated_button.setEnabled)
        self.view_model.can_save_manual_edits_changed.connect(self.save_manual_edits_button.setEnabled)

    # --- Slots for ViewModel Signals (Remain Unchanged) ---
    @Slot(QPixmap)
    def _update_source_preview(self, pixmap: QPixmap):
        """Updates the source image preview."""
        if pixmap and not pixmap.isNull():
            # Scale pixmap to fit the label's *maximum* allowed size now
            scaled_pixmap = pixmap.scaled(
                self.source_preview_label.maximumWidth(),  # Use label's max width constraint
                self.source_preview_label.maximumHeight(),  # Use label's max height constraint
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.source_preview_label.setPixmap(scaled_pixmap)
            self.source_preview_label.setText("")  # Clear placeholder
        else:
            self.source_preview_label.setPixmap(QPixmap())  # Clear image
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
        if hasattr(self, 'advanced_group'): # Check if group exists
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
        # Set state property based on color for QSS styling
        state_map = {"green": "success", "red": "error", "orange": "busy", "black": "busy"} # Map black to busy too
        # Explicitly map gray to a neutral state like 'info' or 'neutral'
        state = state_map.get(color_name, "info" if color_name == "gray" else "ready") # Default to 'ready' otherwise
        self.calibration_status_label.setProperty("state", state)
        # Force style refresh (Important if using QSS based on the state property)
        self.calibration_status_label.style().unpolish(self.calibration_status_label)
        self.calibration_status_label.style().polish(self.calibration_status_label)
