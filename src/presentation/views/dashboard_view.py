# src/presentation/views/dashboard_view.py

from typing import List, Dict, Any # Added Dict, Any

# --- Qt Imports ---
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QListWidget, QListWidgetItem,
    QGroupBox, QPushButton, QGraphicsColorizeEffect  # Added QGroupBox, QPushButton
)
from PySide6.QtCore import Slot, Qt, QTimer, Signal # Added Signal
from PySide6.QtGui import QFont, QColor, QPixmap # Added QPixmap

# --- Application Imports ---
from src.presentation.view_models.dashboard_view_model import DashboardViewModel
# Import custom UI components
from src.presentation.components.ui_components import (
    StyledButton, ActionButton, SecondaryButton, LogDisplay, DangerButton
)
from src.presentation.views import resources_rc # Ensure icons are imported
# Import the StyleManager for component-specific styles (if needed, though less likely now)
# from src.presentation.styles.style_manager import StyleManager


class DashboardView(QWidget):
    """
    View for the Dashboard tab, displaying monitoring status and quick actions.
    """
    # --- NEW Signal for Navigation ---
    request_tab_navigation = Signal(str) # Emits the target tab key (e.g., "Settings")
    # --- END NEW ---

    def __init__(self, view_model: DashboardViewModel, parent: QWidget = None):
        """
        Initialize the DashboardView.

        Args:
            view_model: The corresponding DashboardViewModel instance.
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
        """Creates and arranges the UI elements for the dashboard."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(12)  # Increased spacing between elements

        # --- Top Row: Header with P&L and Status ---
        header_frame = QFrame()
        header_frame.setFrameShape(QFrame.StyledPanel)
        header_frame.setObjectName("headerFrame")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(15, 15, 15, 15)

        # P&L Value (Left)
        pnl_layout = QVBoxLayout()
        pnl_layout.setSpacing(2)
        pnl_label = QLabel("CURRENT P&L")
        pnl_label.setProperty("title", "true")
        pnl_layout.addWidget(pnl_label)
        self.pnl_display_label = QLabel("N/A")
        self.pnl_display_label.setObjectName("pnlDisplayLabel")
        self.pnl_display_label.setProperty("state", "neutral")
        pnl_layout.addWidget(self.pnl_display_label)
        header_layout.addLayout(pnl_layout)

        # Separator 1
        separator = QFrame(); separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken); separator.setProperty("class", "HeaderSeparator")
        header_layout.addWidget(separator)

        # Status (Middle)
        status_layout = QVBoxLayout()
        status_layout.setSpacing(2)
        status_label = QLabel("MONITORING STATUS")
        status_label.setProperty("title", "true")
        status_layout.addWidget(status_label)
        self.monitoring_status_label = QLabel("Inactive")
        self.monitoring_status_label.setObjectName("monitoringStatusLabel")
        self.monitoring_status_label.setProperty("state", "inactive")
        status_layout.addWidget(self.monitoring_status_label)
        header_layout.addLayout(status_layout)

        # --- REMOVED Platform Details Section ---

        # Set stretch factors for remaining header items
        header_layout.setStretchFactor(pnl_layout, 1) # Adjust stretch as needed
        header_layout.setStretchFactor(status_layout, 1)

        main_layout.addWidget(header_frame)

        # --- NEW: Monitoring Prerequisites Section ---
        prereq_group = QGroupBox("Monitoring Prerequisites")
        prereq_group.setObjectName("prerequisitesGroup")
        self.prereq_layout = QVBoxLayout(prereq_group) # Store layout reference
        self.prereq_layout.setContentsMargins(9, 9, 9, 9)
        self.prereq_layout.setSpacing(5) # Adjust spacing between rows

        # Create placeholder rows (we'll add widgets in code later)
        # We store references to the labels/buttons for easy updating
        self.prereq_widgets: Dict[str, Dict[str, Any]] = {} # Type hint added
        prerequisite_keys = [
             ("monitor_region", "P&L Monitor Region"),
             ("ocr_profile", "OCR Profile"),
             ("ct_path", "Cold Turkey Path"),
             ("ct_block_name", "CT Block Name"),
             ("ct_verified", "CT Block Verified"),
             ("flatten_regions", "Flatten Regions"),
        ]

        for key, display_name in prerequisite_keys:
            row_layout = QHBoxLayout()
            icon_label = QLabel() # Placeholder for icon
            icon_label.setFixedSize(18, 18) # Consistent size for icon
            icon_label.setObjectName(f"prereqIcon_{key}") # For potential styling
            status_label = QLabel(f"{display_name}: Loading...")
            status_label.setObjectName(f"prereqText_{key}")
            action_button = SecondaryButton("Go to Setup") # Use SecondaryButton
            action_button.setObjectName(f"prereqAction_{key}")
            action_button.setVisible(False) # Start hidden
            action_button.setMinimumWidth(90) # Give buttons some minimum width

            row_layout.addWidget(icon_label)
            row_layout.addWidget(status_label, 1) # Allow text label to stretch
            row_layout.addWidget(action_button)

            self.prereq_layout.addLayout(row_layout)
            # Store references for easy access later
            self.prereq_widgets[key] = {
                 "icon": icon_label,
                 "text": status_label,
                 "button": action_button
             }

        self.prereq_layout.addStretch(1) # Push rows up if space allows
        main_layout.insertWidget(1, prereq_group) # Insert it below the header
        # --- END NEW Prerequisites Section ---


        # --- Action Strip --- (No Changes Needed Here)
        action_frame = QFrame()
        action_frame.setObjectName("actionFrame")
        action_layout = QHBoxLayout(action_frame)
        action_layout.setContentsMargins(15, 8, 15, 8)
        action_label = QLabel("QUICK ACTIONS:"); action_label.setProperty("class", "ActionStripLabel")
        action_layout.addWidget(action_label)
        self.start_button = ActionButton("Start", icon=":/icons/play.svg"); self.start_button.setObjectName("startButton")
        action_layout.addWidget(self.start_button)
        self.stop_button = DangerButton("Stop", icon=":/icons/stop-circle.svg"); self.stop_button.setObjectName("stopButton")
        action_layout.addWidget(self.stop_button)
        self.flash_button = StyledButton("Test Flash", icon=":/icons/zap.svg"); self.flash_button.setObjectName("flashButton")
        action_layout.addWidget(self.flash_button)
        action_layout.addStretch()
        main_layout.addWidget(action_frame)

        # --- Content Area: Mini Graph and Alerts --- (No Changes Needed Here)
        content_layout = QHBoxLayout(); content_layout.setSpacing(12)
        graph_frame = QFrame(); graph_frame.setFrameShape(QFrame.StyledPanel); graph_frame.setProperty("class", "ContentPanel")
        graph_layout = QVBoxLayout(graph_frame); graph_layout.setContentsMargins(12, 12, 12, 12)
        graph_header = QLabel("P&L TREND"); graph_header.setProperty("title", "true")
        graph_layout.addWidget(graph_header)
        graph_placeholder = QLabel("[ P&L Graph ]"); graph_placeholder.setObjectName("graphPlaceholder")
        graph_placeholder.setAlignment(Qt.AlignCenter); graph_placeholder.setFixedHeight(120)
        graph_layout.addWidget(graph_placeholder)
        content_layout.addWidget(graph_frame, 1)

        alerts_frame = QFrame(); alerts_frame.setFrameShape(QFrame.StyledPanel); alerts_frame.setProperty("class", "ContentPanel")
        alerts_layout = QVBoxLayout(alerts_frame); alerts_layout.setContentsMargins(12, 12, 12, 12); alerts_layout.setSpacing(5)
        alerts_header = QLabel("RECENT ALERTS"); alerts_header.setProperty("title", "true")
        alerts_layout.addWidget(alerts_header)
        self.alerts_list = QListWidget(); self.alerts_list.setObjectName("alertsList"); self.alerts_list.setFixedHeight(120)
        self.alerts_list.setAlternatingRowColors(True)
        alerts_layout.addWidget(self.alerts_list)
        content_layout.addWidget(alerts_frame, 1)
        main_layout.addLayout(content_layout)

        # --- Activity Log Section --- (No Changes Needed Here)
        log_frame = QFrame(); log_frame.setFrameShape(QFrame.StyledPanel); log_frame.setObjectName("logFrame"); log_frame.setProperty("class", "ContentPanel")
        log_layout = QVBoxLayout(log_frame); log_layout.setContentsMargins(12, 12, 12, 12)
        log_header = QLabel("ACTIVITY LOG"); log_header.setProperty("title", "true")
        log_layout.addWidget(log_header)
        self.activity_log_display = LogDisplay(self)
        self.activity_log_display.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.activity_log_display.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        log_layout.addWidget(self.activity_log_display)
        main_layout.addWidget(log_frame, 1)

    def _connect_signals(self):
        """Connect signals from widgets to ViewModel slots and vice versa."""
        # --- View -> ViewModel ---
        self.start_button.clicked.connect(self.view_model.start_monitoring)
        self.stop_button.clicked.connect(self.view_model.stop_monitoring)
        self.flash_button.clicked.connect(self.view_model.test_flash_regions)

        # --- ViewModel -> View ---
        self.view_model.current_pnl_text_changed.connect(self._update_pnl_display)
        self.view_model.monitoring_status_text_changed.connect(self._update_monitoring_status)
        # REMOVED: self.view_model.monitoring_details_text_changed connection

        # --- NEW: Connect prerequisite signal ---
        self.view_model.prerequisite_status_updated.connect(self._update_prerequisite_row)
        # --- END NEW ---

        self.view_model.can_start_monitoring_changed.connect(self.start_button.setEnabled)
        self.view_model.can_stop_monitoring_changed.connect(self.stop_button.setEnabled)
        self.view_model.can_test_flash_changed.connect(self.flash_button.setEnabled)
        self.view_model.recent_alerts_updated.connect(self._update_alerts_list)
        self.view_model.activity_log_appended.connect(self.activity_log_display.append_message)

        # --- NEW: Connect Prerequisite Action Buttons ---
        # Check if prereq_widgets exists before connecting
        if hasattr(self, 'prereq_widgets'):
            for key, widgets in self.prereq_widgets.items():
                widgets["button"].clicked.connect(self._handle_prerequisite_action_click)
        # --- END NEW ---

    # --- Slots for ViewModel Signals ---

    @Slot(str)
    def _update_pnl_display(self, pnl_text: str):
        """Updates the main P&L value label."""
        # (Keep existing implementation)
        self.pnl_display_label.setText(pnl_text)
        if "-" in pnl_text or pnl_text.startswith("LOCKOUT") or pnl_text.startswith("ERROR"):
            self.pnl_display_label.setProperty("state", "negative")
        elif pnl_text == "N/A":
            self.pnl_display_label.setProperty("state", "neutral")
        else:
            self.pnl_display_label.setProperty("state", "positive")
        self.pnl_display_label.style().unpolish(self.pnl_display_label)
        self.pnl_display_label.style().polish(self.pnl_display_label)

    @Slot(str)
    def _update_monitoring_status(self, status_text: str):
        """Updates the monitoring status label and potentially its style."""
        # (Keep existing implementation)
        self.monitoring_status_label.setText(status_text)
        if "Active" in status_text: state = "active"
        elif "Inactive" in status_text: state = "inactive"
        elif "Error" in status_text: state = "error"
        elif "Busy" in status_text: state = "busy"
        else: state = "neutral"
        self.monitoring_status_label.setProperty("state", state)
        self.monitoring_status_label.style().unpolish(self.monitoring_status_label)
        self.monitoring_status_label.style().polish(self.monitoring_status_label)

    @Slot(list)
    def _update_alerts_list(self, alerts: List[str]):
        """Clears and repopulates the recent alerts list."""
        # (Keep existing implementation)
        self.alerts_list.clear()
        if alerts:
            for alert in alerts:
                item = QListWidgetItem(alert)
                if "threshold" in alert.lower() or "error" in alert.lower():
                    item.setForeground(QColor("#e74c3c"))
                    font = item.font(); font.setBold(True); item.setFont(font)
                self.alerts_list.addItem(item)
        else:
            placeholder_item = QListWidgetItem("No recent alerts.")
            placeholder_item.setForeground(QColor("#7f8c8d"))
            self.alerts_list.addItem(placeholder_item)

    # --- NEW: Slot to update prerequisite rows ---
    @Slot(str, str, str, bool)
    def _update_prerequisite_row(self, key: str, status_text: str, status_state: str, show_action: bool):
        """Updates the UI row for a specific prerequisite using QLabel and QGraphicsColorizeEffect."""
        if not hasattr(self, 'prereq_widgets') or key not in self.prereq_widgets:
            if hasattr(self, 'view_model') and hasattr(self.view_model, '_logger'):
                self.view_model._logger.error(
                    f"DashboardView: Received update for unknown/uninitialized prerequisite key '{key}'")
            return

        widgets = self.prereq_widgets[key]
        text_label: QLabel = widgets["text"]
        icon_label: QLabel = widgets["icon"]  # <<< Now it's a QLabel
        action_button: QPushButton = widgets["button"]

        # Update Text Label
        display_name = text_label.text().split(':')[0]
        text_label.setText(f"{display_name}: {status_text}")

        # --- Update Icon Path (Use base Feather names) ---
        icon_path = ""
        if status_state == "ok":
            icon_path = ":/icons/check-circle.svg"
        elif status_state == "warning":
            icon_path = ":/icons/alert-triangle.svg"
        elif status_state == "error" or status_state == "missing":
            icon_path = ":/icons/x-circle.svg"
        else:
            icon_path = ":/icons/info.svg"  # info, pending, etc.

        # --- Load base icon pixmap ---
        base_pixmap = QPixmap()  # Start with empty
        if icon_path:
            loaded_pixmap = QPixmap(icon_path)
            if not loaded_pixmap.isNull():
                # Scale the base pixmap *before* applying effect
                base_pixmap = loaded_pixmap.scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio,
                                                   Qt.TransformationMode.SmoothTransformation)
            else:
                icon_label.setText("?")  # Fallback character
                if hasattr(self, 'view_model'): self.view_model._logger.warning(f"Icon not found: {icon_path}")

        # Set the base pixmap (might be empty if icon failed to load)
        icon_label.setPixmap(base_pixmap)

        # --- Apply or update the colorize effect ---
        # Define color map
        color_map = {
            "ok": QColor("#27ae60"),  # Green
            "warning": QColor("#f39c12"),  # Yellow/Orange
            "error": QColor("#e74c3c"),  # Red
            "missing": QColor("#e74c3c"),  # Red
            "info": QColor("#95a5a6"),  # Gray
            "neutral": QColor("#95a5a6")  # Gray
        }
        target_color = color_map.get(status_state, QColor("#95a5a6"))  # Default to gray

        # Get existing effect or create a new one
        effect = icon_label.graphicsEffect()
        colorize_effect = None
        if isinstance(effect, QGraphicsColorizeEffect):
            colorize_effect = effect
        else:
            # Remove any non-colorize effect if present
            if effect: icon_label.setGraphicsEffect(None)
            # Create and set the new effect
            colorize_effect = QGraphicsColorizeEffect(icon_label)
            icon_label.setGraphicsEffect(colorize_effect)

        # Configure and enable the effect
        if colorize_effect:  # Ensure effect exists
            colorize_effect.setColor(target_color)
            colorize_effect.setStrength(1.0)  # Use 1.0 for full color change
            colorize_effect.setEnabled(True)  # Ensure it's active
        # --- End Effect Application ---

        # Update Button Visibility and Text/Target (No change needed here)
        action_button.setVisible(show_action)
        if show_action:
            target_tab = "Unknown";
            button_text = "Fix Issue"
            if key == "monitor_region":
                target_tab = "Region Setup"; button_text = "Define Region"
            elif key == "flatten_regions":
                target_tab = "Region Setup"; button_text = "Add Regions"
            elif key == "ct_path":
                target_tab = "Settings"; button_text = "Set Path"
            elif key == "ct_block_name":
                target_tab = "Settings"; button_text = "Set Name"
            elif key == "ct_verified":
                target_tab = "Settings"; button_text = "Verify Block"
            elif key == "ocr_profile":
                target_tab = "OCR Calibration"; button_text = "Calibrate"
            action_button.setText(button_text)
            action_button.setProperty("targetTab", target_tab)
        else:
            action_button.setProperty("targetTab", None)

    # --- NEW: Slot to handle action button clicks ---
    @Slot()
    def _handle_prerequisite_action_click(self):
        """Handles clicks on any prerequisite action button."""
        sender_button = self.sender() # Get the button that was clicked
        if not isinstance(sender_button, QPushButton):
            return # Should not happen

        # Retrieve the target tab key stored in the button's property
        target_tab_key = sender_button.property("targetTab")

        if target_tab_key:
            if hasattr(self, 'view_model') and hasattr(self.view_model, '_logger'):
                 self.view_model._logger.info(f"Dashboard action button clicked, requesting navigation to tab: '{target_tab_key}'")
            self.request_tab_navigation.emit(target_tab_key) # Emit signal for MainView
        else:
            if hasattr(self, 'view_model') and hasattr(self.view_model, '_logger'):
                 self.view_model._logger.warning(f"Action button {sender_button.objectName()} clicked, but no targetTab property found.")
    # --- END NEW ---