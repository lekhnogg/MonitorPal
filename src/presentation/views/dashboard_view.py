# src/presentation/views/dashboard_view.py

from typing import List, Dict, Any, Optional, Tuple  # Added Dict, Any

# --- Qt Imports ---
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QListWidget, QListWidgetItem,
    QGroupBox, QPushButton, QGraphicsColorizeEffect, QGridLayout  # Added QGroupBox, QPushButton
)
from PySide6.QtCore import Slot, Qt, QTimer, Signal, QSize  # Added Signal
from PySide6.QtGui import QFont, QColor, QPixmap, QIcon

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
    request_tab_navigation = Signal(str) # Emits the target tab key (e.g., "Settings")

    def __init__(self, view_model: DashboardViewModel, parent: QWidget = None):
        """
        Initialize the DashboardView.

        Args:
            view_model: The corresponding DashboardViewModel instance.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.view_model = view_model

        self.pnl_icon_label: Optional[QLabel] = None
        self.pnl_display_label: Optional[QLabel] = None
        self.status_icon_label: Optional[QLabel] = None
        self.monitoring_status_label: Optional[QLabel] = None
        self.region_icon_label: Optional[QLabel] = None
        self.region_name_label: Optional[QLabel] = None
        self.region_position_label: Optional[QLabel] = None
        self.prereq_badge_label: Optional[QLabel] = None
        self.alerts_list: Optional[QListWidget] = None
        self.activity_log_display: Optional[LogDisplay] = None
        self.start_button: Optional[ActionButton] = None
        self.stop_button: Optional[DangerButton] = None
        self.flash_button: Optional[StyledButton] = None

        # --- Crucially, initialize prereq_widgets and prerequisite_setup_data HERE ---
        self.prereq_widgets: Dict[str, Dict[str, Any]] = {}
        self.prerequisite_setup_data: List[Tuple[str, str]] = [
            ("ct_path", "Cold Turkey Application Path"),
            ("ct_block_setup", "Cold Turkey Trading Block"),
            ("monitor_region", "P&L Monitor Region"),
            ("flatten_regions", "Flatten Position Regions"),
            ("pnl_detector", "P&L Detector"),
        ]

        self._setup_ui()  # This method will now populate self.prereq_widgets
        self._connect_signals()

        # Schedule the VM to emit its initial state signals
        if hasattr(self.view_model, '_logger') and self.view_model._logger:  # Safety check
            self.view_model._logger.debug("DashboardView: Scheduling initial UI refresh via VM.refresh_ui_signals.")
        else:
            print("DEBUG: DashboardView.__init__ - ViewModel has no _logger attribute or it's None.")

        # Ensure view_model is not None before accessing refresh_ui_signals
        if self.view_model and hasattr(self.view_model, 'refresh_ui_signals'):
            QTimer.singleShot(0, self.view_model.refresh_ui_signals)
        elif self.view_model:
            # Log if the method is missing, which would be a critical error
            if hasattr(self.view_model, '_logger') and self.view_model._logger:
                self.view_model._logger.error("DashboardViewModel is missing 'refresh_ui_signals' method!")
            else:
                print("ERROR: DashboardViewModel is missing 'refresh_ui_signals' method!")
        else:
            # This case should ideally not happen if __init__ receives a valid view_model
            print("ERROR: DashboardView initialized with no ViewModel!")


    def _setup_ui(self):
        """Creates and arranges the UI elements for the dashboard."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)


        # -----------------------------------------
        # --- Status Cards (Top Row) ---
        # -----------------------------------------
        status_cards_layout = QHBoxLayout()
        status_cards_layout.setSpacing(15)

        # --- P&L Card ---
        pnl_card = QFrame()
        pnl_card.setObjectName("pnlStatusCard")  # Keep specific objectName if needed
        pnl_card.setProperty("class", "statusInfoCard")  # <<< CHANGED FROM "darkPanel"
        pnl_card_layout = QVBoxLayout(pnl_card)
        pnl_card_layout.setContentsMargins(15, 15, 15, 15)
        pnl_card_layout.setSpacing(5)

        pnl_header_layout = QHBoxLayout()
        pnl_title = QLabel("CURRENT P&L")
        pnl_title.setProperty("class", "panelTitle")  # This class is fine, describes the label's role
        pnl_header_layout.addWidget(pnl_title, 1)

        self.pnl_icon_label = QLabel()
        self.pnl_icon_label.setObjectName("pnlCardIcon")
        self.pnl_icon_label.setFixedSize(24, 24)
        self.pnl_icon_label.setPixmap(
            QPixmap(":/icons/trending-up.svg").scaled(18, 18, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        pnl_header_layout.addWidget(self.pnl_icon_label)
        pnl_card_layout.addLayout(pnl_header_layout)

        self.pnl_display_label = QLabel("N/A")
        self.pnl_display_label.setObjectName("pnlDisplayLabel")
        self.pnl_display_label.setProperty("state", "neutral")
        pnl_card_layout.addWidget(self.pnl_display_label)

        pnl_chart = QFrame()
        pnl_chart.setObjectName("pnlChartPlaceholder")  # This is specific, fine
        pnl_chart.setMinimumHeight(20);
        pnl_chart.setMaximumHeight(20)
        pnl_card_layout.addWidget(pnl_chart)
        pnl_card_layout.addStretch(1)
        status_cards_layout.addWidget(pnl_card, 1)

        # --- Status Card ---
        status_card = QFrame()
        status_card.setObjectName("monitoringStatusCard")  # Keep specific objectName
        status_card.setProperty("class", "statusInfoCard")  # <<< CHANGED
        status_card_layout = QVBoxLayout(status_card)
        status_card_layout.setContentsMargins(15, 15, 15, 15)
        status_card_layout.setSpacing(5)

        status_header_layout = QHBoxLayout()
        status_title = QLabel("MONITORING STATUS")
        status_title.setProperty("class", "panelTitle")
        status_header_layout.addWidget(status_title, 1)

        self.status_icon_label = QLabel()
        self.status_icon_label.setObjectName("statusCardIcon")
        self.status_icon_label.setFixedSize(24, 24)
        self.status_icon_label.setPixmap(
            QPixmap(":/icons/activity.svg").scaled(18, 18, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        status_header_layout.addWidget(self.status_icon_label)
        status_card_layout.addLayout(status_header_layout)

        self.monitoring_status_label = QLabel("Inactive")
        self.monitoring_status_label.setObjectName("monitoringStatusLabel")
        self.monitoring_status_label.setProperty("state", "inactive")
        status_card_layout.addWidget(self.monitoring_status_label)
        status_card_layout.addStretch(1)
        status_cards_layout.addWidget(status_card, 1)

        # --- Region Card ---
        region_card = QFrame()
        region_card.setObjectName("regionStatusCard")  # Keep specific objectName
        region_card.setProperty("class", "statusInfoCard")  # <<< CHANGED
        region_card_layout = QVBoxLayout(region_card)
        region_card_layout.setContentsMargins(15, 15, 15, 15)
        region_card_layout.setSpacing(5)

        region_header_layout = QHBoxLayout()
        region_title = QLabel("MONITOR REGION")
        region_title.setProperty("class", "panelTitle")
        region_header_layout.addWidget(region_title, 1)

        self.region_icon_label = QLabel()
        self.region_icon_label.setObjectName("regionCardIcon")
        self.region_icon_label.setFixedSize(24, 24)
        self.region_icon_label.setPixmap(
            QPixmap(":/icons/monitor.svg").scaled(18, 18, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        region_header_layout.addWidget(self.region_icon_label)
        region_card_layout.addLayout(region_header_layout)

        self.region_name_label = QLabel("N/A")
        self.region_name_label.setObjectName("regionNameLabel")
        region_card_layout.addWidget(self.region_name_label)

        self.region_position_label = QLabel("Position: N/A")
        self.region_position_label.setObjectName("regionPositionLabel")
        region_card_layout.addWidget(self.region_position_label)
        region_card_layout.addStretch(1)
        status_cards_layout.addWidget(region_card, 1)

        main_layout.addLayout(status_cards_layout)

        # -----------------------------------------
        # --- Main Content Grid ---
        # -----------------------------------------
        main_content_layout = QGridLayout()
        main_content_layout.setSpacing(15)
        main_content_layout.setColumnStretch(0, 1)
        main_content_layout.setColumnStretch(1, 1)
        main_content_layout.setColumnStretch(2, 1)

        # -----------------------------------------
        # --- Prerequisites Panel ---
        # -----------------------------------------
        prereq_panel = QFrame()
        prereq_panel.setObjectName("prereqPanel")
        prereq_panel.setProperty("class", "contentSectionPanel")  # Neutral class name
        prereq_layout = QVBoxLayout(prereq_panel)
        prereq_layout.setContentsMargins(15, 15, 15, 15)
        prereq_layout.setSpacing(8)

        prereq_header_layout = QHBoxLayout()
        prereq_title = QLabel("MONITORING CHECKLIST")
        prereq_title.setProperty("class", "panelTitle")
        prereq_header_layout.addWidget(prereq_title)
        prereq_header_layout.addStretch(1)

        self.prereq_badge_label = QLabel("Loading...")  # Initialized in __init__
        self.prereq_badge_label.setObjectName("prereqBadge")
        prereq_header_layout.addWidget(self.prereq_badge_label)
        prereq_layout.addLayout(prereq_header_layout)

        prereq_divider = QFrame()
        prereq_divider.setFrameShape(QFrame.Shape.HLine)
        prereq_divider.setFrameShadow(QFrame.Shadow.Sunken)
        prereq_divider.setObjectName("panelDivider")
        prereq_layout.addWidget(prereq_divider)

        # self.prereq_widgets is already an instance dict: {}
        # self.prerequisite_setup_data is an instance list of tuples
        for key, display_name_in_ui in self.prerequisite_setup_data:  # Use instance attribute
            row_layout = QHBoxLayout();
            row_layout.setSpacing(6)

            icon_label = QLabel();
            icon_label.setFixedSize(18, 18)
            icon_label.setObjectName(f"prereqIcon_{key}");
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row_layout.addWidget(icon_label)

            status_label = QLabel(f"{display_name_in_ui}: Loading...")
            status_label.setObjectName(f"prereqText_{key}")
            status_label.setWordWrap(True)
            row_layout.addWidget(status_label, 1)

            action_button = SecondaryButton("...")  # Placeholder text
            action_button.setObjectName(f"prereqAction_{key}")
            action_button.setVisible(False);
            action_button.setMinimumWidth(90)
            action_button.setStyleSheet("padding-top: 1px; padding-bottom: 1px;")  # Specific override
            row_layout.addWidget(action_button)

            prereq_layout.addLayout(row_layout)
            # Populate the instance dictionary
            self.prereq_widgets[key] = {
                "icon": icon_label,
                "text": status_label,
                "display_name": display_name_in_ui,  # Store for _update_prerequisite_row
                "button": action_button
            }
        prereq_layout.addStretch(1)
        main_content_layout.addWidget(prereq_panel, 0, 0, 2, 1)

        # -----------------------------------------
        # --- Quick Actions Panel ---
        # -----------------------------------------
        actions_panel = QFrame()
        actions_panel.setObjectName("actionsPanel")
        actions_panel.setProperty("class", "contentSectionPanel")  # Good, uses neutral class
        actions_layout = QVBoxLayout(actions_panel)  # This is the main layout for the whole "Quick Actions" panel
        actions_layout.setContentsMargins(15, 15, 15, 15)
        actions_layout.setSpacing(8)

        actions_header = QLabel("QUICK ACTIONS")
        actions_header.setProperty("class", "panelTitle")
        actions_layout.addWidget(actions_header)

        actions_divider = QFrame()
        actions_divider.setFrameShape(QFrame.Shape.HLine)
        actions_divider.setFrameShadow(QFrame.Shadow.Sunken)
        actions_divider.setObjectName("panelDivider")
        actions_layout.addWidget(actions_divider)

        # --- Vertical Button Layout ---
        # Renamed for clarity, was 'buttons_layout', now 'quick_action_buttons_layout'
        quick_action_buttons_layout = QVBoxLayout()  # <<< CHANGED TO QVBoxLayout
        quick_action_buttons_layout.setSpacing(10)  # Vertical spacing between buttons (adjust as needed)

        self.start_button = ActionButton("Start", icon=":/icons/play.svg")
        self.start_button.setObjectName("startButton")
        self.start_button.setToolTip("Start monitoring the selected platform")
        quick_action_buttons_layout.addWidget(self.start_button)  # Add to the vertical layout

        self.stop_button = DangerButton("Stop", icon=":/icons/stop-circle.svg")
        self.stop_button.setObjectName("stopButton")
        self.stop_button.setToolTip("Stop active monitoring")
        quick_action_buttons_layout.addWidget(self.stop_button)  # Add to the vertical layout

        self.flash_button = StyledButton("Test Flash", icon=":/icons/zap.svg")
        self.flash_button.setObjectName("flashButton")
        self.flash_button.setToolTip("Flash defined regions for the selected platform")
        quick_action_buttons_layout.addWidget(self.flash_button)  # Add to the vertical layout

        # If you want these buttons to be at the top of their allocated space in the 'actions_panel':
        quick_action_buttons_layout.addStretch(1)
        # If you want them centered vertically within their space, don't add stretch here,
        # but ensure the parent 'actions_layout' handles alignment if it has extra space.

        actions_layout.addLayout(
            quick_action_buttons_layout)  # Add the vertical button layout to the panel's main layout

        # This stretch pushes the entire button group (and header/divider) towards the top of the actions_panel.
        # Keep this if you want the Quick Actions section to not take up all vertical space if available.
        actions_layout.addStretch(1)

        main_content_layout.addWidget(actions_panel, 0, 1)  # Add to the grid

        # -----------------------------------------
        # --- Alerts Panel ---
        # -----------------------------------------
        alerts_panel = QFrame()
        alerts_panel.setObjectName("alertsPanel")  # Keep specific objectName
        alerts_panel.setProperty("class", "contentSectionPanel")  # <<< CHANGED
        alerts_layout = QVBoxLayout(alerts_panel)
        alerts_layout.setContentsMargins(15, 15, 15, 15);
        alerts_layout.setSpacing(8)

        alerts_title = QLabel("RECENT ALERTS");
        alerts_title.setProperty("class", "panelTitle")
        alerts_layout.addWidget(alerts_title)
        alerts_divider = QFrame();
        alerts_divider.setFrameShape(QFrame.Shape.HLine)
        alerts_divider.setFrameShadow(QFrame.Shadow.Sunken);
        alerts_divider.setObjectName("panelDivider")
        alerts_layout.addWidget(alerts_divider)
        self.alerts_list = QListWidget();
        self.alerts_list.setObjectName("alertsList")
        self.alerts_list.setAlternatingRowColors(True)
        alerts_layout.addWidget(self.alerts_list, 1)
        main_content_layout.addWidget(alerts_panel, 0, 2, 2, 1)

        main_layout.addLayout(main_content_layout, 1)

        # -----------------------------------------
        # --- Activity Log Panel ---
        # -----------------------------------------
        log_panel = QFrame()
        log_panel.setObjectName("logPanel")  # Keep specific objectName
        log_panel.setProperty("class", "contentSectionPanel")  # <<< CHANGED
        log_layout = QVBoxLayout(log_panel)
        log_layout.setContentsMargins(15, 15, 15, 15);
        log_layout.setSpacing(8)

        log_title = QLabel("ACTIVITY LOG");
        log_title.setProperty("class", "panelTitle")
        log_layout.addWidget(log_title)
        log_divider = QFrame();
        log_divider.setFrameShape(QFrame.Shape.HLine)
        log_divider.setFrameShadow(QFrame.Shadow.Sunken);
        log_divider.setObjectName("panelDivider")
        log_layout.addWidget(log_divider)
        self.activity_log_display = LogDisplay(self)  # LogDisplay sets its own objectName
        self.activity_log_display.setMinimumHeight(100)
        log_layout.addWidget(self.activity_log_display)
        main_layout.addWidget(log_panel, 0)

    def _connect_signals(self):
        """Connect signals from widgets to ViewModel slots and vice versa."""

        # --- Guards for critical ViewModel and UI elements ---
        if not self.view_model:
            # If there's no ViewModel, no signals can be connected. This is a critical failure.
            # A logger at a higher application level or in __init__ should catch VM not being passed.
            # For robustness here, we can log and return.
            print(
                "ERROR: DashboardView._connect_signals - ViewModel is None. Cannot connect signals.")  # Fallback print
            # If self.view_model could have _logger:
            # if hasattr(self.view_model, '_logger') and self.view_model._logger:
            #    self.view_model._logger.critical("DashboardView: ViewModel is None in _connect_signals.")
            return

        # Check essential UI elements that will have signals connected
        # These should have been created in _setup_ui and assigned to self.
        essential_ui_elements = {
            "start_button": self.start_button,
            "stop_button": self.stop_button,
            "flash_button": self.flash_button,
            "pnl_display_label": self.pnl_display_label,
            "monitoring_status_label": self.monitoring_status_label,
            "prereq_badge_label": self.prereq_badge_label,
            "alerts_list": self.alerts_list,
            "activity_log_display": self.activity_log_display
        }

        for name, element in essential_ui_elements.items():
            if element is None:
                log_msg = f"DashboardView: UI element '{name}' is None in _connect_signals. Signals cannot be connected."
                if hasattr(self.view_model, '_logger') and self.view_model._logger:
                    self.view_model._logger.error(log_msg)
                else:
                    print(f"ERROR: {log_msg}")
                # Decide if you want to return here or try to connect what's available.
                # For critical buttons, probably best to log and be aware.
                # Depending on the element, you might choose to return.
                # For now, we'll log and continue, but this indicates a setup problem.

        # --- View -> ViewModel ---
        if self.start_button:
            self.start_button.clicked.connect(self.view_model.start_monitoring)
        if self.stop_button:
            self.stop_button.clicked.connect(self.view_model.stop_monitoring)
        if self.flash_button:
            self.flash_button.clicked.connect(self.view_model.test_flash_regions)

        # --- ViewModel -> View ---
        if self.pnl_display_label:
            self.view_model.current_pnl_text_changed.connect(self._update_pnl_display)
        if self.monitoring_status_label:
            self.view_model.monitoring_status_text_changed.connect(self._update_monitoring_status)

        if self.prereq_badge_label:  # Check if the badge label exists
            self.view_model.prerequisites_completion_changed.connect(self.prereq_badge_label.setText)

        self.view_model.prerequisite_status_updated.connect(self._update_prerequisite_row)

        if self.start_button:
            self.view_model.can_start_monitoring_changed.connect(self.start_button.setEnabled)
        if self.stop_button:
            self.view_model.can_stop_monitoring_changed.connect(self.stop_button.setEnabled)
        if self.flash_button:
            self.view_model.can_test_flash_changed.connect(self.flash_button.setEnabled)

        if self.alerts_list:
            self.view_model.recent_alerts_updated.connect(self._update_alerts_list)
        if self.activity_log_display:
            self.view_model.activity_log_appended.connect(self.activity_log_display.append_message)

        # --- Prerequisite Action Buttons ---
        if hasattr(self, 'prereq_widgets') and self.prereq_widgets:  # Ensure it's not empty
            for key, widgets_dict in self.prereq_widgets.items():
                action_button = widgets_dict.get("button")
                if action_button and isinstance(action_button, QPushButton):
                    action_button.clicked.connect(self._handle_prerequisite_action_click)
                else:
                    log_msg_prereq = f"DashboardView: Prerequisite button for key '{key}' not found or not a QPushButton."
                    if hasattr(self.view_model, '_logger') and self.view_model._logger:
                        self.view_model._logger.warning(log_msg_prereq)
                    else:
                        print(f"WARNING: {log_msg_prereq}")
        else:
            log_msg_no_prereq_widgets = "DashboardView: 'prereq_widgets' dictionary not found or empty. Cannot connect prerequisite action buttons."
            if hasattr(self.view_model, '_logger') and self.view_model._logger:
                self.view_model._logger.warning(log_msg_no_prereq_widgets)
            else:
                print(f"WARNING: {log_msg_no_prereq_widgets}")

        if hasattr(self.view_model, '_logger') and self.view_model._logger:
            self.view_model._logger.debug("DashboardView: Signal connections established.")
        else:
            print("DEBUG: DashboardView: Signal connections established.")

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
        """Clears and repopulates the recent alerts list with enhanced styling."""
        self.alerts_list.clear()

        if alerts:
            for alert in alerts:
                item = QListWidgetItem()

                # Determine alert type and icon
                alert_type = "info"  # default
                icon_path = ":/icons/info.svg"

                if "error" in alert.lower() or "threshold" in alert.lower() or "lockout" in alert.lower():
                    alert_type = "error"
                    icon_path = ":/icons/alert-triangle.svg"
                elif "warning" in alert.lower():
                    alert_type = "warning"
                    icon_path = ":/icons/alert-triangle.svg"
                elif "success" in alert.lower() or "verified" in alert.lower():
                    alert_type = "success"
                    icon_path = ":/icons/check-circle.svg"

                # Set the icon
                item.setIcon(QIcon(icon_path))

                # Set the text
                item.setText(alert)

                # Set alert type property for styling
                item.setData(Qt.UserRole, alert_type)

                # Set size hint for better spacing
                item.setSizeHint(QSize(0, 36))  # Adjust height as needed

                self.alerts_list.addItem(item)
        else:
            placeholder_item = QListWidgetItem("No recent alerts.")
            placeholder_item.setForeground(QColor("#7f8c8d"))
            placeholder_item.setIcon(QIcon(":/icons/info.svg"))
            self.alerts_list.addItem(placeholder_item)


    @Slot(str, str, str, bool)
    def _update_prerequisite_row(self, key: str, status_description: str, status_state: str, show_action: bool):
        """Updates the UI row for a specific prerequisite using QLabel and QGraphicsColorizeEffect."""
        if not hasattr(self, 'prereq_widgets') or key not in self.prereq_widgets:
            if hasattr(self, 'view_model') and hasattr(self.view_model, '_logger'):
                self.view_model._logger.error(
                    f"DashboardView: Received update for unknown/uninitialized prerequisite key '{key}'")
            return

        widgets = self.prereq_widgets[key]
        text_label: QLabel = widgets["text"]
        icon_label: QLabel = widgets["icon"]
        action_button: QPushButton = widgets["button"]
        display_name: str = widgets["display_name"]  # Get the stored display name

        # --- Update Text Label ---
        # Construct the full text here in the View
        text_label.setText(f"{display_name}: {status_description}")
        # --- END Text Label Update ---

        # --- Update Icon Path (Use base Feather names) ---
        icon_path = ""
        if status_state == "ok":
            icon_path = ":/icons/check-circle.svg"
        elif status_state == "warning":
            icon_path = ":/icons/alert-triangle.svg"
        elif status_state == "error" or status_state == "missing":
            icon_path = ":/icons/x-circle.svg"
        else:
            icon_path = ":/icons/info.svg"
        base_pixmap = QPixmap()
        if icon_path:
            loaded_pixmap = QPixmap(icon_path)
            if not loaded_pixmap.isNull():
                base_pixmap = loaded_pixmap.scaled(16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            else:
                icon_label.setText("?");
                self.view_model._logger.warning(f"Icon not found: {icon_path}")
        icon_label.setPixmap(base_pixmap)
        color_map = {"ok": QColor("#27ae60"), "warning": QColor("#f39c12"), "error": QColor("#e74c3c"),
                     "missing": QColor("#e74c3c"), "info": QColor("#95a5a6"), "neutral": QColor("#95a5a6")}
        target_color = color_map.get(status_state, QColor("#95a5a6"))
        effect = icon_label.graphicsEffect()
        colorize_effect = effect if isinstance(effect, QGraphicsColorizeEffect) else None
        if not colorize_effect:
            if effect: icon_label.setGraphicsEffect(None)
            colorize_effect = QGraphicsColorizeEffect(icon_label);
            icon_label.setGraphicsEffect(colorize_effect)
        if colorize_effect:
            colorize_effect.setColor(target_color);
            colorize_effect.setStrength(1.0);
            colorize_effect.setEnabled(True)
        # --- END Icon and Effect ---

        # --- Update Button Visibility and Text/Target ---
        action_button.setVisible(show_action)
        if show_action:
            target_tab = "Unknown";
            button_text = "Fix Issue"
            if key == "ct_path":
                target_tab = "Settings";
                button_text = "Set Path"
            elif key == "ct_block_setup":  # New combined key
                target_tab = "Settings";
                button_text = "Configure Block"
            elif key == "monitor_region":
                target_tab = "Visual Setup";
                button_text = "Define Region"
            elif key == "flatten_regions":
                target_tab = "Visual Setup";
                button_text = "Add Regions"
            elif key == "pnl_detector":  # Renamed key
                target_tab = "Visual Setup";
                button_text = "Configure Detector"  # Or "Calibrate"

            action_button.setText(button_text)
            action_button.setProperty("targetTab", target_tab)
        else:
            action_button.setProperty("targetTab", None)

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
