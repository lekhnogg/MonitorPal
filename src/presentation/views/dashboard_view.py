# src/presentation/views/dashboard_view.py

from typing import List

# --- Qt Imports ---
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QGroupBox,
    QSizePolicy, QTextEdit, QListWidget, QFrame # Added QFrame
)
from PySide6.QtCore import Slot, Qt
from PySide6.QtGui import QFont # Added QFont

# --- Application Imports ---
from src.presentation.view_models.dashboard_view_model import DashboardViewModel
# Import custom UI components
from src.presentation.components.ui_components import (
    StyledButton, ActionButton, SecondaryButton, WarningButton, LogDisplay, GroupHeader
)

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
        self._apply_initial_vm_state() # Apply initial VM state after connecting

    def _setup_ui(self):
        """Creates and arranges the UI elements for the dashboard."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10) # Add some padding
        main_layout.setSpacing(15) # Add spacing between sections

        # --- Top Row: P&L and Status ---
        top_row_layout = QHBoxLayout()
        top_row_layout.setSpacing(15)

        # P&L Display Box
        pnl_group = QGroupBox("CURRENT P&L")
        pnl_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        pnl_layout = QVBoxLayout(pnl_group)

        self.pnl_display_label = QLabel("N/A")
        pnl_font = QFont()
        pnl_font.setPointSize(28) # Make P&L value large
        pnl_font.setBold(True)
        self.pnl_display_label.setFont(pnl_font)
        self.pnl_display_label.setAlignment(Qt.AlignCenter)
        self.pnl_display_label.setStyleSheet("color: #2c3e50; padding: 10px;") # Dark blue-gray
        pnl_layout.addWidget(self.pnl_display_label)

        # Placeholder for Graph
        # You would replace this with your actual graph widget (e.g., from pyqtgraph or matplotlib)
        graph_placeholder = QLabel("[ P&L Graph Placeholder ]")
        graph_placeholder.setAlignment(Qt.AlignCenter)
        graph_placeholder.setMinimumHeight(50)
        graph_placeholder.setStyleSheet("background-color: #ecf0f1; border: 1px dashed #bdc3c7; color: #7f8c8d;")
        pnl_layout.addWidget(graph_placeholder)

        # Add extra info labels if needed from mockup (Last 5m, Min Value)
        # self.pnl_extra_info_label = QLabel("Last 5m: N/A | Min Value: N/A")
        # pnl_layout.addWidget(self.pnl_extra_info_label)

        top_row_layout.addWidget(pnl_group, 1) # Give P&L group more stretch factor

        # Monitoring Status Box
        status_group = QGroupBox("MONITORING STATUS")
        status_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        status_layout = QGridLayout(status_group) # Use grid for key-value alignment

        self.monitoring_status_label = QLabel("Inactive")
        status_font = QFont()
        status_font.setPointSize(14)
        status_font.setBold(True)
        self.monitoring_status_label.setFont(status_font)
        # Add status indicator (e.g., colored circle) if desired later
        status_layout.addWidget(self.monitoring_status_label, 0, 0, 1, 2, Qt.AlignCenter) # Span 2 columns

        # Separator Line
        line1 = QFrame()
        line1.setFrameShape(QFrame.HLine)
        line1.setFrameShadow(QFrame.Sunken)
        status_layout.addWidget(line1, 1, 0, 1, 2)

        self.monitoring_details_label = QLabel("Select a platform...")
        self.monitoring_details_label.setWordWrap(True)
        status_layout.addWidget(self.monitoring_details_label, 2, 0, 1, 2) # Span 2 columns
        status_layout.setRowStretch(3, 1) # Push content up

        top_row_layout.addWidget(status_group, 1) # Give status group equal stretch factor

        main_layout.addLayout(top_row_layout)

        # --- Middle Row: Quick Actions and Alerts ---
        middle_row_layout = QHBoxLayout()
        middle_row_layout.setSpacing(15)

        # Quick Actions Box
        actions_group = QGroupBox("QUICK ACTIONS")
        actions_layout = QGridLayout(actions_group) # Grid for button layout

        self.start_button = ActionButton("► Start Monitoring")
        self.stop_button = SecondaryButton("■ Stop Monitoring")
        self.flatten_button = WarningButton("⚠ Flatten Positions")
        self.flash_button = StyledButton("⚡ Test Flash Regions")

        actions_layout.addWidget(self.start_button, 0, 0)
        actions_layout.addWidget(self.stop_button, 0, 1)
        actions_layout.addWidget(self.flatten_button, 1, 0)
        actions_layout.addWidget(self.flash_button, 1, 1)

        middle_row_layout.addWidget(actions_group)

        # Recent Alerts Box
        alerts_group = QGroupBox("RECENT ALERTS")
        alerts_layout = QVBoxLayout(alerts_group)
        self.alerts_list = QListWidget() # Use QListWidget for better item handling
        self.alerts_list.setStyleSheet("QListWidget { border: none; background-color: transparent; }")
        self.alerts_list.setAlternatingRowColors(True)
        alerts_layout.addWidget(self.alerts_list)
        middle_row_layout.addWidget(alerts_group)

        main_layout.addLayout(middle_row_layout)

        # --- Bottom Row: Activity Log ---
        log_group = GroupHeader("Activity Log") # Use custom component
        log_layout = QVBoxLayout(log_group)
        self.activity_log_display = LogDisplay(self) # Use custom component
        log_layout.addWidget(self.activity_log_display)
        main_layout.addWidget(log_group, 1) # Allow log to stretch vertically

    def _connect_signals(self):
        """Connect signals from widgets to ViewModel slots and vice versa."""
        # --- View -> ViewModel ---
        self.start_button.clicked.connect(self.view_model.start_monitoring)
        self.stop_button.clicked.connect(self.view_model.stop_monitoring)
        self.flatten_button.clicked.connect(self.view_model.trigger_manual_flatten)
        self.flash_button.clicked.connect(self.view_model.test_flash_regions)

        # --- ViewModel -> View ---
        self.view_model.current_pnl_text_changed.connect(self._update_pnl_display)
        # self.view_model.pnl_history_updated.connect(self._update_pnl_graph) # Connect when graph is implemented
        self.view_model.monitoring_status_text_changed.connect(self._update_monitoring_status)
        self.view_model.monitoring_details_text_changed.connect(self.monitoring_details_label.setText)
        self.view_model.can_start_monitoring_changed.connect(self.start_button.setEnabled)
        self.view_model.can_stop_monitoring_changed.connect(self.stop_button.setEnabled)
        self.view_model.can_flatten_manually_changed.connect(self.flatten_button.setEnabled)
        self.view_model.can_test_flash_changed.connect(self.flash_button.setEnabled)
        self.view_model.recent_alerts_updated.connect(self._update_alerts_list)
        self.view_model.activity_log_appended.connect(self.activity_log_display.append_message)
        # Connect status_message_changed if the main view exposes a way to show it
        # Example: self.view_model.status_message_changed.connect(self.parent().show_status_message) # If parent (MainView) has this method

    def _apply_initial_vm_state(self): # <<< CORRECTED NAME
        """Applies the current state from the ViewModel to the widgets."""
        # Manually trigger the update slots/methods with current VM state
        self._update_pnl_display(self.view_model._current_pnl_text)
        self._update_monitoring_status(self.view_model._monitoring_status_text)
        self.monitoring_details_label.setText(self.view_model._monitoring_details_text)
        self.start_button.setEnabled(self.view_model._can_start)
        self.stop_button.setEnabled(self.view_model._can_stop)
        self.flatten_button.setEnabled(self.view_model._can_flatten)
        self.flash_button.setEnabled(self.view_model._can_test_flash)
        self._update_alerts_list(self.view_model._recent_alerts)

    # --- Slots for ViewModel Signals ---

    @Slot(str)
    def _update_pnl_display(self, pnl_text: str):
        """Updates the main P&L value label."""
        self.pnl_display_label.setText(pnl_text)
        # Optionally change color based on value (positive/negative)
        if pnl_text.startswith("-$") or pnl_text.startswith("LOCKOUT") or pnl_text.startswith("ERROR"):
             self.pnl_display_label.setStyleSheet("color: #e74c3c; padding: 10px;") # Red
        elif pnl_text == "N/A":
             self.pnl_display_label.setStyleSheet("color: #7f8c8d; padding: 10px;") # Gray
        else:
             self.pnl_display_label.setStyleSheet("color: #2ecc71; padding: 10px;") # Green

    @Slot(str)
    def _update_monitoring_status(self, status_text: str):
        """Updates the monitoring status label and potentially its style."""
        self.monitoring_status_label.setText(status_text)
        if "Active" in status_text:
             self.monitoring_status_label.setStyleSheet("color: green;")
        elif "Inactive" in status_text:
             self.monitoring_status_label.setStyleSheet("color: gray;")
        elif "Error" in status_text or "Busy" in status_text:
             self.monitoring_status_label.setStyleSheet("color: orange;")
        else:
             self.monitoring_status_label.setStyleSheet("") # Default color

    @Slot(list)
    def _update_alerts_list(self, alerts: List[str]):
        """Clears and repopulates the recent alerts list."""
        self.alerts_list.clear()
        if alerts:
            self.alerts_list.addItems(alerts)
        else:
            self.alerts_list.addItem("No recent alerts.") # Placeholder

    # @Slot(list)
    # def _update_pnl_graph(self, history_data: list):
    #     """Updates the P&L graph."""
    #     # --- Add graph plotting logic here ---
    #     # This will depend heavily on the chosen graphing library
    #     # Example: self.graph_widget.plot(timestamps, values)
    #     pass