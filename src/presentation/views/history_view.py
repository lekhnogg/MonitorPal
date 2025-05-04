# src/presentation/views/history_view.py

from typing import List, Dict, Any, Tuple

# --- Qt Imports ---
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QSplitter, QComboBox,
    QCheckBox, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QSizePolicy
)
from PySide6.QtCore import Slot, Qt, QDateTime, QTimer  # Import QDateTime
from PySide6.QtGui import QColor

# --- Application Imports ---
from src.presentation.view_models.history_view_model import HistoryViewModel
# Import custom UI components
from src.presentation.components.ui_components import (
    StyledButton, ActionButton, SecondaryButton, DangerButton, GroupHeader
)
# Import plotting library if you choose one (e.g., pyqtgraph)
# import pyqtgraph as pg # Example
# Import StyleManager for QSS styling
from src.presentation.styles.style_manager import StyleManager


class HistoryView(QWidget):
    """
    View for the History tab.
    """

    # Define table columns for consistency
    SESSION_HISTORY_COLUMNS = {
        "date": ("Date", 0),
        "start_time": ("Start Time", 1),
        "duration": ("Duration", 2),
        "min_pnl": ("Min P&L", 3),
        "threshold": ("Threshold", 4),
        "locked": ("Locked Out", 5),
    }

    def __init__(self, view_model: HistoryViewModel, parent: QWidget = None):
        super().__init__(parent)
        self.view_model = view_model
        self._setup_ui()
        self._connect_signals()
        self.view_model._logger.debug("View: Scheduling initial UI refresh via VM.refresh_ui_signals.")
        QTimer.singleShot(0, self.view_model.refresh_ui_signals)

    def _setup_ui(self):
        """Creates and arranges the UI elements for the history tab."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(15)

        # --- Top Section: Graph and Controls ---
        graph_group = QGroupBox("P&L History Graph")
        graph_group.setObjectName("graphGroup")
        graph_group_layout = QVBoxLayout(graph_group)
        graph_group_layout.setSpacing(8)

        # Graph Placeholder
        self.graph_placeholder = QLabel("[ P&L Graph Area ]")
        self.graph_placeholder.setObjectName("graphPlaceholder")
        self.graph_placeholder.setAlignment(Qt.AlignCenter)
        self.graph_placeholder.setMinimumHeight(200)
        self.graph_placeholder.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        graph_group_layout.addWidget(self.graph_placeholder, 1)

        # Graph Controls
        graph_controls_layout = QHBoxLayout()
        graph_controls_layout.addWidget(QLabel("Time Range:"))
        self.time_range_combo = QComboBox()
        self.time_range_combo.setObjectName("timeRangeCombo")
        graph_controls_layout.addWidget(self.time_range_combo)
        graph_controls_layout.addStretch(1)

        self.threshold_line_checkbox = QCheckBox("Show Threshold Line")
        self.threshold_line_checkbox.setObjectName("thresholdLineCheckbox")
        graph_controls_layout.addWidget(self.threshold_line_checkbox)
        graph_group_layout.addLayout(graph_controls_layout)

        main_layout.addWidget(graph_group, 1)

        # --- Bottom Section: Session History Table and Controls ---
        history_group = QGroupBox("Session History")
        history_group.setObjectName("historyGroup")
        history_layout = QVBoxLayout(history_group)
        history_layout.setSpacing(8)

        self.history_table = QTableWidget()
        self.history_table.setObjectName("historyTable")
        self.history_table.setColumnCount(len(self.SESSION_HISTORY_COLUMNS))
        self.history_table.setHorizontalHeaderLabels(
            [label for label, index in sorted(self.SESSION_HISTORY_COLUMNS.values(), key=lambda item: item[1])])
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.history_table.setAlternatingRowColors(True)

        # Adjust column widths
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.SESSION_HISTORY_COLUMNS["date"][1], QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.SESSION_HISTORY_COLUMNS["start_time"][1],
                                    QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.SESSION_HISTORY_COLUMNS["duration"][1],
                                    QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.SESSION_HISTORY_COLUMNS["locked"][1], QHeaderView.ResizeMode.ResizeToContents)

        history_layout.addWidget(self.history_table, 1)

        # History Controls
        history_controls_layout = QHBoxLayout()
        self.clear_history_button = DangerButton("Clear History")
        self.clear_history_button.setObjectName("clearHistoryButton")
        self.generate_report_button = StyledButton("Generate Report")
        self.generate_report_button.setObjectName("generateReportButton")
        self.details_button = SecondaryButton("View Details...")
        self.details_button.setObjectName("detailsButton")
        self.details_button.setEnabled(False)

        history_controls_layout.addWidget(self.clear_history_button)
        history_controls_layout.addWidget(self.generate_report_button)
        history_controls_layout.addStretch(1)
        history_controls_layout.addWidget(self.details_button)
        history_layout.addLayout(history_controls_layout)

        main_layout.addWidget(history_group, 1)


    def _connect_signals(self):
        """Connect signals from widgets to ViewModel slots and vice versa."""

        # --- View -> ViewModel ---
        self.time_range_combo.currentTextChanged.connect(self.view_model.set_graph_time_range)
        self.threshold_line_checkbox.toggled.connect(self.view_model.set_threshold_line_visibility)
        self.clear_history_button.clicked.connect(self.view_model.clear_history)
        self.generate_report_button.clicked.connect(self.view_model.generate_report)
        self.details_button.clicked.connect(self._handle_details_button_click)
        # Enable details button only when a row is selected
        self.history_table.itemSelectionChanged.connect(self._handle_table_selection_change)

        # --- ViewModel -> View ---
        self.view_model.pnl_graph_data_updated.connect(self._update_graph)
        self.view_model.graph_time_range_options_changed.connect(self._update_time_range_options)
        self.view_model.graph_current_time_range_changed.connect(self.time_range_combo.setCurrentText)
        self.view_model.graph_threshold_line_visibility_changed.connect(self._update_threshold_line_visibility)
        self.view_model.graph_threshold_value_changed.connect(self._update_threshold_line_value)

        self.view_model.session_history_updated.connect(self._update_session_history_table)

        self.view_model.can_clear_history_changed.connect(self.clear_history_button.setEnabled)
        self.view_model.can_generate_report_changed.connect(self.generate_report_button.setEnabled)
        # Details button enablement handled by table selection

    @Slot(object) # Expects GraphDataType = List[Tuple[float, float]]
    def _update_graph(self, graph_data: List[Tuple[float, float]]):
        """Updates the P&L graph with new data."""
        # --- Placeholder Implementation ---
        if graph_data:
             count = len(graph_data)
             first_ts = QDateTime.fromSecsSinceEpoch(int(graph_data[0][0])).toString(Qt.DateFormat.ISODate) if count > 0 else "N/A"
             last_ts = QDateTime.fromSecsSinceEpoch(int(graph_data[-1][0])).toString(Qt.DateFormat.ISODate) if count > 0 else "N/A"
             self.graph_placeholder.setText(f"[ Graph Area: {count} data points\nFrom {first_ts} to {last_ts} ]")
        else:
             self.graph_placeholder.setText("[ No Graph Data Available ]")
        # --- End Placeholder ---

        # --- Real Implementation (Example using pyqtgraph) ---
        # if hasattr(self, 'pnl_curve'):
        #     if graph_data:
        #         timestamps, values = zip(*graph_data) # Unzip data
        #         self.pnl_curve.setData(x=list(timestamps), y=list(values))
        #         # Auto-range needs to be handled carefully, especially with threshold line
        #         # self.plot_widget.autoRange()
        #     else:
        #         self.pnl_curve.clear()
        # --- End pyqtgraph Example ---


    @Slot(list)
    def _update_time_range_options(self, options: List[str]):
        """Populates the time range combo box."""
        current_text = self.time_range_combo.currentText()
        self.time_range_combo.blockSignals(True)
        self.time_range_combo.clear()
        self.time_range_combo.addItems(options)
        # Restore selection if possible
        if current_text in options:
             self.time_range_combo.setCurrentText(current_text)
        elif options:
             self.time_range_combo.setCurrentIndex(0)
        self.time_range_combo.blockSignals(False)


    @Slot(bool)
    def _update_threshold_line_visibility(self, visible: bool):
        """Updates the threshold line checkbox and graph visibility."""
        self.threshold_line_checkbox.setChecked(visible)
        # --- Real Graph Implementation ---
        # if hasattr(self, 'threshold_line'):
        #     self.threshold_line.setVisible(visible)


    @Slot(float)
    def _update_threshold_line_value(self, threshold_value: float):
        """Updates the position of the threshold line on the graph."""
        # --- Real Graph Implementation ---
        # if hasattr(self, 'threshold_line'):
        #     self.threshold_line.setValue(threshold_value)


    @Slot(object) # Expects SessionHistoryType = List[Dict[str, Any]]
    def _update_session_history_table(self, history_data: List[Dict[str, Any]]):
        """Clears and repopulates the session history table."""
        self.history_table.setRowCount(0) # Clear existing rows
        self.history_table.setRowCount(len(history_data))

        for row_index, session_data in enumerate(history_data):
            for key, (header_text, col_index) in self.SESSION_HISTORY_COLUMNS.items():
                value = session_data.get(key, "N/A") # Get value or default
                item = QTableWidgetItem(str(value)) # Convert to string for display

                # Special formatting/alignment
                if key == "min_pnl":
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    try:
                        # Attempt to extract float from string like '-$134.50'
                        pnl_val_str = str(value).replace('$', '').replace(',', '')
                        pnl_val = float(pnl_val_str)
                        if pnl_val < 0:
                            # QTableWidgetItem also doesn't support properties - use direct styling
                            item.setForeground(QColor("red"))
                        else:
                            item.setForeground(QColor("green"))
                    except ValueError:
                        pass
                elif key == "locked":
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    item.setText("Yes" if value else "No")
                    if value:
                        # Direct styling - no properties
                        item.setForeground(QColor("red"))
                        item.setBackground(QColor("#ffe0e0"))
                elif key == "threshold":
                     item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                     item.setText(f"${float(value):,.2f}" if isinstance(value, (int, float)) else str(value))
                elif key in ["duration", "start_time"]:
                     item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                self.history_table.setItem(row_index, col_index, item)

        # Resize rows to content if desired
        # self.history_table.resizeRowsToContents()


    # --- Slots for Local UI Events ---

    @Slot()
    def _handle_table_selection_change(self):
        """Enables/disables the 'View Details' button based on table selection."""
        selected_rows = self.history_table.selectionModel().selectedRows()
        self.details_button.setEnabled(len(selected_rows) > 0)


    @Slot()
    def _handle_details_button_click(self):
        """Calls the ViewModel to show details for the selected row."""
        selected_rows = self.history_table.selectionModel().selectedRows()
        if selected_rows:
            selected_row_index = selected_rows[0].row() # Get index of the first selected row
            self.view_model.show_session_details(selected_row_index)