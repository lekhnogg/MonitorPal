# src/presentation/views/dashboard_view.py

from typing import List

# --- Qt Imports ---
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QListWidget, QListWidgetItem, QScrollArea
)
from PySide6.QtCore import Slot, Qt
from PySide6.QtGui import QFont, QColor

# --- Application Imports ---
from src.presentation.view_models.dashboard_view_model import DashboardViewModel
# Import custom UI components
from src.presentation.components.ui_components import (
    StyledButton, ActionButton, SecondaryButton, LogDisplay
)
from src.presentation.views import resources_rc

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
        self._apply_initial_vm_state()

    def _setup_ui(self):
        """Creates and arranges the UI elements for the dashboard."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # --- Top Row: Header with P&L and Status ---
        header_frame = QFrame()
        header_frame.setFrameShape(QFrame.StyledPanel)
        header_frame.setStyleSheet("QFrame { background-color: #f7f7f7; border-radius: 4px; }")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(10, 10, 10, 10)

        # P&L Value (Left)
        pnl_layout = QVBoxLayout()
        pnl_layout.setSpacing(0)

        pnl_label = QLabel("CURRENT P&L")
        pnl_label.setStyleSheet("font-size: 11px; color: #666; font-weight: bold;")
        pnl_layout.addWidget(pnl_label)

        self.pnl_display_label = QLabel("N/A")
        pnl_font = QFont()
        pnl_font.setPointSize(24)
        pnl_font.setBold(True)
        self.pnl_display_label.setFont(pnl_font)
        self.pnl_display_label.setStyleSheet("color: #2c3e50; padding: 0px;")
        pnl_layout.addWidget(self.pnl_display_label)

        header_layout.addLayout(pnl_layout)

        # Add vertical separator
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("color: #ddd;")
        header_layout.addWidget(separator)

        # Status (Middle)
        status_layout = QVBoxLayout()
        status_layout.setSpacing(0)

        status_label = QLabel("MONITORING STATUS")
        status_label.setStyleSheet("font-size: 11px; color: #666; font-weight: bold;")
        status_layout.addWidget(status_label)

        self.monitoring_status_label = QLabel("Inactive")
        status_font = QFont()
        status_font.setPointSize(16)
        status_font.setBold(True)
        self.monitoring_status_label.setFont(status_font)
        self.monitoring_status_label.setStyleSheet("color: #7f8c8d;")
        status_layout.addWidget(self.monitoring_status_label)

        header_layout.addLayout(status_layout)

        # Add vertical separator
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.VLine)
        separator2.setFrameShadow(QFrame.Sunken)
        separator2.setStyleSheet("color: #ddd;")
        header_layout.addWidget(separator2)

        # Platform Details (Right)
        details_layout = QVBoxLayout()
        details_layout.setSpacing(0)

        details_label = QLabel("PLATFORM DETAILS")
        details_label.setStyleSheet("font-size: 11px; color: #666; font-weight: bold;")
        details_layout.addWidget(details_label)

        self.monitoring_details_label = QLabel("Select a platform...")
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
        action_frame.setStyleSheet("QFrame { background-color: #eaf2f8; border-radius: 4px; }")
        action_layout = QHBoxLayout(action_frame)
        action_layout.setContentsMargins(10, 5, 10, 5)

        action_label = QLabel("QUICK ACTIONS:")
        action_label.setStyleSheet("font-size: 11px; color: #666; font-weight: bold;")
        action_layout.addWidget(action_label)

        self.start_button = ActionButton("Start", icon=":/icons/play.svg")
        self.start_button.setFixedWidth(90)
        action_layout.addWidget(self.start_button)

        self.stop_button = SecondaryButton("Stop", icon=":/icons/stop-circle.svg")
        self.stop_button.setFixedWidth(90)
        action_layout.addWidget(self.stop_button)

        self.flash_button = StyledButton("Test Flash", icon=":/icons/zap.svg")
        self.flash_button.setFixedWidth(90)
        action_layout.addWidget(self.flash_button)

        action_layout.addStretch()

        main_layout.addWidget(action_frame)

        # --- Content Area: Mini Graph and Alerts ---
        content_layout = QHBoxLayout()
        content_layout.setSpacing(8)

        # Mini Graph (Left)
        graph_frame = QFrame()
        graph_frame.setFrameShape(QFrame.StyledPanel)
        graph_frame.setStyleSheet("QFrame { background-color: #f7f7f7; border-radius: 4px; }")
        graph_layout = QVBoxLayout(graph_frame)
        graph_layout.setContentsMargins(10, 10, 10, 10)

        graph_header = QLabel("P&L TREND")
        graph_header.setStyleSheet("font-size: 11px; color: #666; font-weight: bold;")
        graph_layout.addWidget(graph_header)

        # Graph placeholder with fixed height for compactness
        graph_placeholder = QLabel("[ P&L Graph ]")
        graph_placeholder.setAlignment(Qt.AlignCenter)
        graph_placeholder.setFixedHeight(100)
        graph_placeholder.setStyleSheet("background-color: #ecf0f1; border: 1px dashed #bdc3c7; color: #7f8c8d;")
        graph_layout.addWidget(graph_placeholder)

        content_layout.addWidget(graph_frame, 1)

        # Recent Alerts (Right)
        alerts_frame = QFrame()
        alerts_frame.setFrameShape(QFrame.StyledPanel)
        alerts_frame.setStyleSheet("QFrame { background-color: #f7f7f7; border-radius: 4px; }")
        alerts_layout = QVBoxLayout(alerts_frame)
        alerts_layout.setContentsMargins(10, 10, 10, 10)
        alerts_layout.setSpacing(5)

        alerts_header = QLabel("RECENT ALERTS")
        alerts_header.setStyleSheet("font-size: 11px; color: #666; font-weight: bold;")
        alerts_layout.addWidget(alerts_header)

        self.alerts_list = QListWidget()
        self.alerts_list.setFixedHeight(100)  # Fixed height for compactness
        self.alerts_list.setStyleSheet("QListWidget { border: none; background-color: transparent; }")
        self.alerts_list.setAlternatingRowColors(True)
        alerts_layout.addWidget(self.alerts_list)

        content_layout.addWidget(alerts_frame, 1)

        main_layout.addLayout(content_layout)

        # --- Activity Log Section ---
        log_frame = QFrame()
        log_frame.setFrameShape(QFrame.StyledPanel)
        log_frame.setStyleSheet("QFrame { background-color: #f7f7f7; border-radius: 4px; }")
        log_layout = QVBoxLayout(log_frame)
        log_layout.setContentsMargins(10, 10, 10, 10)

        log_header = QLabel("ACTIVITY LOG")
        log_header.setStyleSheet("font-size: 11px; color: #666; font-weight: bold;")
        log_layout.addWidget(log_header)

        # Scrollable log with fixed height
        log_scroll = QScrollArea()
        log_scroll.setWidgetResizable(True)
        log_scroll.setFrameShape(QFrame.NoFrame)
        log_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        log_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        log_scroll.setFixedHeight(150)

        log_content = QWidget()
        log_content_layout = QVBoxLayout(log_content)
        log_content_layout.setContentsMargins(0, 0, 0, 0)

        self.activity_log_display = LogDisplay(self)
        log_content_layout.addWidget(self.activity_log_display)
        log_content_layout.addStretch()

        log_scroll.setWidget(log_content)
        log_layout.addWidget(log_scroll)

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
        self.view_model.monitoring_details_text_changed.connect(self.monitoring_details_label.setText)
        self.view_model.can_start_monitoring_changed.connect(self.start_button.setEnabled)
        self.view_model.can_stop_monitoring_changed.connect(self.stop_button.setEnabled)
        self.view_model.can_test_flash_changed.connect(self.flash_button.setEnabled)
        self.view_model.recent_alerts_updated.connect(self._update_alerts_list)
        self.view_model.activity_log_appended.connect(self.activity_log_display.append_message)

    def _apply_initial_vm_state(self):
        """Applies the current state from the ViewModel to the widgets."""
        # Manually trigger the update slots/methods with current VM state
        self._update_pnl_display(self.view_model._current_pnl_text)
        self._update_monitoring_status(self.view_model._monitoring_status_text)
        self.monitoring_details_label.setText(self.view_model._monitoring_details_text)
        self.start_button.setEnabled(self.view_model._can_start)
        self.stop_button.setEnabled(self.view_model._can_stop)
        self.flash_button.setEnabled(self.view_model._can_test_flash)
        self._update_alerts_list(self.view_model._recent_alerts)

    # --- Slots for ViewModel Signals ---

    @Slot(str)
    def _update_pnl_display(self, pnl_text: str):
        """Updates the main P&L value label."""
        self.pnl_display_label.setText(pnl_text)
        # Color based on value (positive/negative)
        if pnl_text.startswith("-$") or pnl_text.startswith("LOCKOUT") or pnl_text.startswith("ERROR"):
            self.pnl_display_label.setStyleSheet("color: #e74c3c;")  # Red
        elif pnl_text == "N/A":
            self.pnl_display_label.setStyleSheet("color: #7f8c8d;")  # Gray
        else:
            self.pnl_display_label.setStyleSheet("color: #2ecc71;")  # Green

    @Slot(str)
    def _update_monitoring_status(self, status_text: str):
        """Updates the monitoring status label and potentially its style."""
        self.monitoring_status_label.setText(status_text)
        if "Active" in status_text:
            self.monitoring_status_label.setStyleSheet("color: #2ecc71;")  # Green
        elif "Inactive" in status_text:
            self.monitoring_status_label.setStyleSheet("color: #7f8c8d;")  # Gray
        elif "Error" in status_text or "Busy" in status_text:
            self.monitoring_status_label.setStyleSheet("color: #e67e22;")  # Orange
        else:
            self.monitoring_status_label.setStyleSheet("")  # Default color

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