# src/presentation/views/history_view.py

from typing import List, Dict, Any, Tuple, Optional

# --- Qt Imports ---
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QSplitter, QComboBox,
    QCheckBox, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QSizePolicy, QFrame
)
from PySide6.QtCore import Slot, Qt, QDateTime, QTimer, QSize  # Import QDateTime
from PySide6.QtGui import QColor, QPixmap, QPen, QFont

import pyqtgraph as pg
# Configure pyqtgraph to use PySide6
pg.setConfigOptions(antialias=True)

# --- Application Imports ---
from src.presentation.view_models.history_view_model import HistoryViewModel, GraphDataType
# Import custom UI components
from src.presentation.components.ui_components import (
    StyledButton, ActionButton, SecondaryButton, DangerButton, GroupHeader, create_colored_svg_icon
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
        # --- Add attributes for plot items ---
        self.plot_widget: Optional[pg.PlotWidget] = None
        self.pnl_curve: Optional[pg.PlotDataItem] = None
        self.threshold_line: Optional[pg.InfiniteLine] = None
        # --- End Add ---
        self._setup_ui()
        self._connect_signals()
        self.view_model._logger.debug("View: Scheduling initial UI refresh via VM.refresh_ui_signals.")
        QTimer.singleShot(0, self.view_model.refresh_ui_signals)

    def _setup_ui(self):
        """Creates and arranges the UI elements for the history tab."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # -----------------------------------------
        # --- P&L Graph Panel (Top Section) ---
        # -----------------------------------------
        graph_panel = QFrame()
        graph_panel.setObjectName("historyGraphPanel")  # Changed from graphGroup
        graph_panel.setProperty("class", "contentSectionPanel")
        graph_layout = QVBoxLayout(graph_panel)
        graph_layout.setContentsMargins(15, 15, 15, 15)  # Inner padding from QSS example
        graph_layout.setSpacing(8)

        # --- Header with Icon ---
        graph_header_layout = QHBoxLayout()
        graph_title = QLabel("P&L TREND")  # Changed title
        graph_title.setProperty("class", "panelTitle")
        graph_header_layout.addWidget(graph_title, 1)

        self.graph_icon_label = QLabel()  # Keep if you want an icon
        self.graph_icon_label.setObjectName("graphPanelIcon")
        self.graph_icon_label.setFixedSize(24, 24)
        # Icon will be set by theme update, using trending-up.svg
        # self.graph_icon_label.setPixmap(QPixmap(":/icons/trending-up.svg").scaled(18,18,...))
        graph_header_layout.addWidget(self.graph_icon_label)
        graph_layout.addLayout(graph_header_layout)

        graph_divider = QFrame();
        graph_divider.setFrameShape(QFrame.Shape.HLine);
        graph_divider.setObjectName("panelDivider")
        graph_layout.addWidget(graph_divider)

        # --- Graph Widget ---
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setObjectName("historyPnlPlotWidget")

        # --- Theme-dependent background for plot ---
        # We'll set this in on_theme_refresh_requested
        # self.plot_widget.setBackground('w') # Light theme
        # self.plot_widget.setBackground(QColor(31, 41, 55)) # Dark: bg-gray-800 approx

        self.date_axis = pg.DateAxisItem(orientation='bottom')
        self.plot_widget.setAxisItems({'bottom': self.date_axis})

        # Axis Styling (to match Recharts: small font, no lines)
        axis_pen = pg.mkPen(style=Qt.PenStyle.NoPen)  # No line for axis itself
        self.plot_widget.getAxis('bottom').setPen(axis_pen)
        self.plot_widget.getAxis('left').setPen(axis_pen)
        self.plot_widget.getAxis('bottom').setTextPen(QColor("#6b7280"))  # Light theme tick color (gray-500)
        self.plot_widget.getAxis('left').setTextPen(QColor("#6b7280"))  # Light theme tick color
        # Font for axis ticks (can also be set via QSS on PlotWidget if it propagates)
        axis_font = QFont();
        axis_font.setPointSize(8);  # Corresponds to text-xs / 12px in Recharts is often 8-9pt
        self.plot_widget.getAxis('bottom').setTickFont(axis_font)
        self.plot_widget.getAxis('left').setTickFont(axis_font)
        self.plot_widget.getAxis('left').setWidth(50)  # Adjust width for Y-axis labels if needed

        # Grid Styling
        self.plot_widget.showGrid(x=True, y=True, alpha=0.1)  # Very faint grid
        # To match Recharts light grid: pg.mkPen(color=(243, 244, 246), style=Qt.PenStyle.DashLine)
        # For dark theme, grid could be: pg.mkPen(color=(55, 65, 81), style=Qt.PenStyle.DashLine)
        # This will also be set in on_theme_refresh_requested

        self.plot_widget.setMinimumHeight(256)  # h-64 in Tailwind
        self.plot_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Create PlotDataItem for P&L
        # Color will be set in on_theme_refresh_requested
        self.pnl_curve = pg.PlotDataItem(name="P&L")
        # For smooth curve like 'monotone':
        # self.pnl_curve.setCurveType('cubic') # Not exactly 'monotone' but gives smoothness
        # self.pnl_curve.setSymbolBrush(pg.mkBrush(color=...)) # For dots
        # self.pnl_curve.setSymbolPen(pg.mkPen(color=..., width=...))
        # self.pnl_curve.setSymbol('o') # Circle symbol
        # self.pnl_curve.setSymbolSize(8) # Default dot size (r=4 -> size 8)
        self.plot_widget.addItem(self.pnl_curve)

        # Threshold Line
        # Color will be set in on_theme_refresh_requested
        self.threshold_line = pg.InfiniteLine(angle=0, movable=False, label='Threshold')
        # self.threshold_line.label.setColor(...) # Style label color
        self.plot_widget.addItem(self.threshold_line)
        self.threshold_line.hide()

        graph_layout.addWidget(self.plot_widget, 1)

        # --- Graph Controls ---
        # Removing time range combo for now if graph is per-session
        controls_panel = QFrame()
        controls_panel.setObjectName("graphControlsPanel")
        # controls_panel.setProperty("class", "statusInfoCard") # Optional: if you want card styling for controls
        controls_layout = QHBoxLayout(controls_panel)
        controls_layout.setContentsMargins(0, 5, 0, 0)  # Minimal margins for control strip
        controls_layout.setSpacing(10)
        controls_layout.addStretch(1)  # Push checkbox to the right
        self.threshold_line_checkbox = QCheckBox("Show Threshold Line")
        self.threshold_line_checkbox.setObjectName("thresholdLineCheckbox")
        controls_layout.addWidget(self.threshold_line_checkbox)
        graph_layout.addWidget(controls_panel)  # Add controls below graph

        main_layout.addWidget(graph_panel, 1)  # Graph panel gets priority for stretch

        # -----------------------------------------
        # --- Session History Panel (Bottom Section) ---
        # -----------------------------------------
        history_panel = QFrame()
        history_panel.setObjectName("historyPanel")
        history_panel.setProperty("class", "contentSectionPanel")
        history_layout = QVBoxLayout(history_panel)
        history_layout.setContentsMargins(15, 15, 15, 15)
        history_layout.setSpacing(8)

        # --- Header with Icon ---
        history_header_layout = QHBoxLayout()
        history_title = QLabel("SESSION HISTORY")
        history_title.setProperty("class", "panelTitle")
        history_header_layout.addWidget(history_title, 1)

        self.history_icon_label = QLabel()
        self.history_icon_label.setObjectName("historyPanelIcon")
        self.history_icon_label.setFixedSize(24, 24)
        self.history_icon_label.setPixmap(
            QPixmap(":/icons/clock.svg").scaled(18, 18, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        history_header_layout.addWidget(self.history_icon_label)
        history_layout.addLayout(history_header_layout)

        # --- Header Divider ---
        history_divider = QFrame()
        history_divider.setFrameShape(QFrame.Shape.HLine)
        history_divider.setFrameShadow(QFrame.Shadow.Sunken)
        history_divider.setObjectName("panelDivider")
        history_layout.addWidget(history_divider)

        # --- History Table ---
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

        # --- History Controls Panel ---
        history_controls_layout = QHBoxLayout()
        self.clear_history_button = DangerButton("Clear History", icon=":/icons/trash-2.svg")
        self.clear_history_button.setObjectName("clearHistoryButton")
        self.clear_history_button.setToolTip("Clear all session history data")
        history_controls_layout.addWidget(self.clear_history_button)

        self.generate_report_button = StyledButton("Generate Report", icon=":/icons/file-text.svg")
        self.generate_report_button.setObjectName("generateReportButton")
        self.generate_report_button.setToolTip("Create a detailed report from session history")
        history_controls_layout.addWidget(self.generate_report_button)

        history_controls_layout.addStretch(1)

        self.details_button = SecondaryButton("View Details...", icon=":/icons/eye.svg")
        self.details_button.setObjectName("detailsButton")
        self.details_button.setToolTip("View detailed information for the selected session")
        self.details_button.setEnabled(False)
        history_controls_layout.addWidget(self.details_button)

        history_layout.addLayout(history_controls_layout)
        main_layout.addWidget(history_panel, 1)


    def _connect_signals(self):
        """Connect signals from widgets to ViewModel slots and vice versa."""

        # --- View -> ViewModel ---
        #self.time_range_combo.currentTextChanged.connect(self.view_model.set_graph_time_range)
        self.threshold_line_checkbox.toggled.connect(self.view_model.set_threshold_line_visibility)
        self.clear_history_button.clicked.connect(self.view_model.clear_history)
        self.generate_report_button.clicked.connect(self.view_model.generate_report)
        self.details_button.clicked.connect(self._handle_details_button_click)
        # Enable details button only when a row is selected
        self.history_table.itemSelectionChanged.connect(self._handle_table_selection_change)

        # --- ViewModel -> View ---
        self.view_model.pnl_graph_data_updated.connect(self._update_graph)
        #self.view_model.graph_time_range_options_changed.connect(self._update_time_range_options)
        #self.view_model.graph_current_time_range_changed.connect(self.time_range_combo.setCurrentText)
        self.view_model.graph_threshold_line_visibility_changed.connect(self._update_threshold_line_visibility)
        self.view_model.graph_threshold_value_changed.connect(self._update_threshold_line_value)

        self.view_model.session_history_updated.connect(self._update_session_history_table)

        self.view_model.can_clear_history_changed.connect(self.clear_history_button.setEnabled)
        self.view_model.can_generate_report_changed.connect(self.generate_report_button.setEnabled)
        # Details button enablement handled by table selection

    @Slot(object)
    def _update_graph(self, graph_data: GraphDataType):
        if not self.plot_widget or not self.pnl_curve: return

        if graph_data:
            timestamps = [item[0] for item in graph_data]
            pnl_values = [item[1] for item in graph_data]
            self.pnl_curve.setData(x=timestamps, y=pnl_values)
            self.plot_widget.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
            self.plot_widget.setTitle("")  # Clear title when data is present
        else:
            self.pnl_curve.clear()
            self.plot_widget.setTitle("No P&L data for selected session", color=(128, 128, 128))  # Muted color
            # Reset ranges to avoid keeping old zoom
            self.plot_widget.setXRange(0, 1, padding=0)
            self.plot_widget.setYRange(0, 1, padding=0)

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
        if self.threshold_line:
            # Only show if a valid threshold has been set for the current graph
            is_threshold_valid = hasattr(self.view_model, '_current_graph_threshold') and \
                                 isinstance(self.view_model._current_graph_threshold, (int, float))

            if visible and is_threshold_valid:
                self.threshold_line.show()
            else:
                self.threshold_line.hide()

    @Slot(float)
    def _update_threshold_line_value(self, threshold_value: float):
        if self.threshold_line:
            self.threshold_line.setValue(threshold_value)
            # Visibility is handled by _update_threshold_line_visibility now

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

    @Slot()
    def on_theme_refresh_requested(self):
        self.view_model._logger.debug(f"{self.__class__.__name__}: Handling theme refresh request.")
        is_dark = self.property("darkTheme") == True

        # Update Graph Icon
        if hasattr(self, 'graph_icon_label') and self.graph_icon_label:
            icon_color = QColor("#4ade80") if is_dark else QColor("#10b981")  # Green
            try:
                icon = create_colored_svg_icon(":/icons/trending-up.svg", icon_color, QSize(18, 18))
                self.graph_icon_label.setPixmap(icon.pixmap(QSize(18, 18)))
            except Exception as e:
                self.view_model._logger.error(f"Error setting graph panel icon: {e}")

        # Update History Panel Icon
        if hasattr(self, 'history_icon_label') and self.history_icon_label:
            icon_color = QColor("#9ca3af") if is_dark else QColor("#6b7280")  # Muted gray
            try:
                icon = create_colored_svg_icon(":/icons/clock.svg", icon_color, QSize(18, 18))
                self.history_icon_label.setPixmap(icon.pixmap(QSize(18, 18)))
            except Exception as e:
                self.view_model._logger.error(f"Error setting history panel icon: {e}")

        # Update Plot Widget Appearance
        if self.plot_widget:
            bg_color = QColor(31, 41, 55) if is_dark else QColor("white")  # approx gray-800 vs white
            axis_text_color = QColor("#9ca3af") if is_dark else QColor("#6b7280")  # gray-400 vs gray-500
            grid_color = QColor(55, 65, 81) if is_dark else QColor(229, 231, 235)  # gray-700 vs gray-200
            pnl_line_color = QColor("#4ade80") if is_dark else QColor("#10b981")  # green-400 vs green-600
            threshold_line_color = QColor("#f87171") if is_dark else QColor("#ef4444")  # red-400 vs red-500

            self.plot_widget.setBackground(bg_color)
            self.plot_widget.getAxis('bottom').setTextPen(axis_text_color)
            self.plot_widget.getAxis('left').setTextPen(axis_text_color)
            self.plot_widget.getPlotItem().getGrid().setPen(
                pg.mkPen(color=grid_color, style=Qt.PenStyle.DashLine))  # Set grid pen

            if self.pnl_curve:
                # For dots:
                # symbol_brush_color = QColor(pnl_line_color)
                # symbol_pen_color = QColor(pnl_line_color) # Or slightly darker for outline
                # self.pnl_curve.setSymbolBrush(pg.mkBrush(color=symbol_brush_color))
                # self.pnl_curve.setSymbolPen(pg.mkPen(color=symbol_pen_color, width=1))
                # self.pnl_curve.setSymbol('o')
                # self.pnl_curve.setSymbolSize(6) # r=3
                # For line:
                self.pnl_curve.setPen(pg.mkPen(color=pnl_line_color, width=2))  # React was strokeWidth={3}

            if self.threshold_line:
                self.threshold_line.setPen(pg.mkPen(color=threshold_line_color, width=1.5, style=Qt.PenStyle.DashLine))
                # Threshold line label color
                # self.threshold_line.label.setColor(axis_text_color) # Or specific color

        # It's good practice to tell the ViewModel to re-emit its data too,
        # as some view elements might be constructed based on that data + theme.
        if self.view_model and hasattr(self.view_model, 'refresh_ui_signals'):
            self.view_model.refresh_ui_signals()
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