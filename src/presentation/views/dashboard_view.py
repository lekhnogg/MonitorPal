# src/presentation/views/dashboard_view.py

from typing import List

# --- Qt Imports ---
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QListWidget, QListWidgetItem, QScrollArea
)
from PySide6.QtCore import Slot, Qt, QTimer
from PySide6.QtGui import QFont, QColor

# --- Application Imports ---
from src.presentation.view_models.dashboard_view_model import DashboardViewModel
# Import custom UI components
from src.presentation.components.ui_components import (
    StyledButton, ActionButton, SecondaryButton, LogDisplay, DangerButton
)
from src.presentation.views import resources_rc
#Import the StyleManager for component-specific styles
from src.presentation.styles.style_manager import StyleManager


class DashboardView(QWidget):
    """
    View for the Dashboard tab, displaying monitoring status and quick actions.
    """

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
        header_frame.setObjectName("headerFrame")  # For stylesheet targeting
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(15, 15, 15, 15)

        # P&L Value (Left)
        pnl_layout = QVBoxLayout()
        pnl_layout.setSpacing(2)

        pnl_label = QLabel("CURRENT P&L")
        pnl_label.setProperty("title", "true")  # For stylesheet targeting
        pnl_layout.addWidget(pnl_label)

        self.pnl_display_label = QLabel("N/A")
        self.pnl_display_label.setObjectName("pnlDisplayLabel")
        self.pnl_display_label.setProperty("state", "neutral")  # Initial state for styling
        pnl_layout.addWidget(self.pnl_display_label)

        header_layout.addLayout(pnl_layout)

        # Add vertical separator
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setProperty("class", "HeaderSeparator")  # For stylesheet targeting
        header_layout.addWidget(separator)

        # Status (Middle)
        status_layout = QVBoxLayout()
        status_layout.setSpacing(2)

        status_label = QLabel("MONITORING STATUS")
        status_label.setProperty("title", "true")
        status_layout.addWidget(status_label)

        self.monitoring_status_label = QLabel("Inactive")
        self.monitoring_status_label.setObjectName("monitoringStatusLabel")
        self.monitoring_status_label.setProperty("state", "inactive")  # Initial state for styling
        status_layout.addWidget(self.monitoring_status_label)

        header_layout.addLayout(status_layout)

        # Add vertical separator
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.VLine)
        separator2.setFrameShadow(QFrame.Sunken)
        separator2.setProperty("class", "HeaderSeparator")
        header_layout.addWidget(separator2)

        # Platform Details (Right)
        details_layout = QVBoxLayout()
        details_layout.setSpacing(2)

        details_label = QLabel("PLATFORM DETAILS")
        details_label.setProperty("title", "true")
        details_layout.addWidget(details_label)

        self.monitoring_details_label = QLabel("Select a platform...")
        self.monitoring_details_label.setProperty("display", "true")  # For stylesheet targeting
        self.monitoring_details_label.setWordWrap(True)
        details_layout.addWidget(self.monitoring_details_label)

        header_layout.addLayout(details_layout)

        # Set stretch factors
        header_layout.setStretchFactor(pnl_layout, 2)
        header_layout.setStretchFactor(status_layout, 2)
        header_layout.setStretchFactor(details_layout, 3)

        main_layout.addWidget(header_frame)

        # --- Action Strip ---
        action_frame = QFrame()
        action_frame.setObjectName("actionFrame")
        action_layout = QHBoxLayout(action_frame)
        action_layout.setContentsMargins(15, 8, 15, 8)

        action_label = QLabel("QUICK ACTIONS:")
        # <<< Set property for consistent styling if needed >>>
        action_label.setProperty("class", "ActionStripLabel")
        action_layout.addWidget(action_label)

        self.start_button = ActionButton("Start", icon=":/icons/play.svg")  # Use ActionButton
        self.start_button.setObjectName("startButton")  # Keep specific objectName if needed by QSS
        action_layout.addWidget(self.start_button)

        self.stop_button = DangerButton("Stop", icon=":/icons/stop-circle.svg")  # Use DangerButton
        self.stop_button.setObjectName("stopButton")  # Keep specific objectName if needed by QSS
        action_layout.addWidget(self.stop_button)

        self.flash_button = StyledButton("Test Flash", icon=":/icons/zap.svg")  # Use StyledButton
        self.flash_button.setObjectName("flashButton")  # Keep specific objectName if needed by QSS
        action_layout.addWidget(self.flash_button)

        action_layout.addStretch()

        main_layout.addWidget(action_frame)

        # --- Content Area: Mini Graph and Alerts ---
        content_layout = QHBoxLayout()
        content_layout.setSpacing(12)

        # Mini Graph (Left)
        graph_frame = QFrame()
        graph_frame.setFrameShape(QFrame.StyledPanel)
        graph_frame.setProperty("class", "ContentPanel")
        graph_layout = QVBoxLayout(graph_frame)
        graph_layout.setContentsMargins(12, 12, 12, 12)

        graph_header = QLabel("P&L TREND")
        graph_header.setProperty("title", "true")
        graph_layout.addWidget(graph_header)

        # Graph placeholder
        graph_placeholder = QLabel("[ P&L Graph ]")
        graph_placeholder.setObjectName("graphPlaceholder")
        graph_placeholder.setAlignment(Qt.AlignCenter)
        graph_placeholder.setFixedHeight(120)
        graph_layout.addWidget(graph_placeholder)

        content_layout.addWidget(graph_frame, 1)

        # Recent Alerts (Right)
        alerts_frame = QFrame()
        alerts_frame.setFrameShape(QFrame.StyledPanel)
        alerts_frame.setProperty("class", "ContentPanel")
        alerts_layout = QVBoxLayout(alerts_frame)
        alerts_layout.setContentsMargins(12, 12, 12, 12)
        alerts_layout.setSpacing(5)

        alerts_header = QLabel("RECENT ALERTS")
        alerts_header.setProperty("title", "true")
        alerts_layout.addWidget(alerts_header)

        self.alerts_list = QListWidget()
        self.alerts_list.setObjectName("alertsList")
        self.alerts_list.setFixedHeight(120)
        self.alerts_list.setAlternatingRowColors(True)
        alerts_layout.addWidget(self.alerts_list)

        content_layout.addWidget(alerts_frame, 1)

        main_layout.addLayout(content_layout)

        # --- Activity Log Section ---
        log_frame = QFrame()
        log_frame.setFrameShape(QFrame.StyledPanel)
        log_frame.setObjectName("logFrame")
        log_frame.setProperty("class", "ContentPanel")
        log_layout = QVBoxLayout(log_frame)
        log_layout.setContentsMargins(12, 12, 12, 12)

        log_header = QLabel("ACTIVITY LOG")
        log_header.setProperty("title", "true")
        log_layout.addWidget(log_header)

        # --- Use LogDisplay Directly ---
        self.activity_log_display = LogDisplay(self)  # Create LogDisplay (inherits QTextEdit)
        # Set scrollbar policy on the QTextEdit itself
        self.activity_log_display.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.activity_log_display.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        log_layout.addWidget(self.activity_log_display)  # Add directly to the frame's layout

        # Add the frame to the main layout, allowing it to stretch
        main_layout.addWidget(log_frame, 1)  # The '1' allows vertical stretching

    def _connect_signals(self):
        """Connect signals from widgets to ViewModel slots and vice versa."""
        # --- View -> ViewModel ---
        self.start_button.clicked.connect(self.view_model.start_monitoring)
        self.stop_button.clicked.connect(self.view_model.stop_monitoring)
        self.flash_button.clicked.connect(self.view_model.test_flash_regions)

        # --- ViewModel -> View ---
        self.view_model.current_pnl_text_changed.connect(self._update_pnl_display)
        self.view_model.monitoring_status_text_changed.connect(self._update_monitoring_status)
        self.view_model.monitoring_details_text_changed.connect(self.monitoring_details_label.setText)
        self.view_model.can_start_monitoring_changed.connect(self.start_button.setEnabled)
        self.view_model.can_stop_monitoring_changed.connect(self.stop_button.setEnabled)
        self.view_model.can_test_flash_changed.connect(self.flash_button.setEnabled)
        self.view_model.recent_alerts_updated.connect(self._update_alerts_list)
        self.view_model.activity_log_appended.connect(self.activity_log_display.append_message)

    # --- Slots for ViewModel Signals ---

    @Slot(str)
    def _update_pnl_display(self, pnl_text: str):
        """Updates the main P&L value label."""
        self.pnl_display_label.setText(pnl_text)

        # Color based on value using state property for stylesheet
        if "-" in pnl_text or pnl_text.startswith("LOCKOUT") or pnl_text.startswith("ERROR"):
            self.pnl_display_label.setProperty("state", "negative")
        elif pnl_text == "N/A":
            self.pnl_display_label.setProperty("state", "neutral")
        else:
            self.pnl_display_label.setProperty("state", "positive")

        # Force style refresh
        self.pnl_display_label.style().unpolish(self.pnl_display_label)
        self.pnl_display_label.style().polish(self.pnl_display_label)

    @Slot(str)
    def _update_monitoring_status(self, status_text: str):
        """Updates the monitoring status label and potentially its style."""
        self.monitoring_status_label.setText(status_text)

        # Set state property based on status for stylesheet
        if "Active" in status_text:
            self.monitoring_status_label.setProperty("state", "active")
        elif "Inactive" in status_text:
            self.monitoring_status_label.setProperty("state", "inactive")
        elif "Error" in status_text:
            self.monitoring_status_label.setProperty("state", "error")
        elif "Busy" in status_text:
            self.monitoring_status_label.setProperty("state", "busy")
        else:
            self.monitoring_status_label.setProperty("state", "neutral")

        # Force style refresh
        self.monitoring_status_label.style().unpolish(self.monitoring_status_label)
        self.monitoring_status_label.style().polish(self.monitoring_status_label)

    @Slot(list)
    def _update_alerts_list(self, alerts: List[str]):
        """Clears and repopulates the recent alerts list."""
        self.alerts_list.clear()
        if alerts:
            for alert in alerts:
                item = QListWidgetItem(alert)
                # Style important alerts differently
                if "threshold" in alert.lower() or "error" in alert.lower():
                    item.setForeground(QColor("#e74c3c"))  # Red for critical alerts
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.alerts_list.addItem(item)
        else:
            placeholder_item = QListWidgetItem("No recent alerts.")
            placeholder_item.setForeground(QColor("#7f8c8d"))  # Gray
            self.alerts_list.addItem(placeholder_item)