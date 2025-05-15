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
    StyledButton, ActionButton, SecondaryButton, LogDisplay, DangerButton, create_colored_svg_icon
)
from src.presentation.views import resources_rc # Ensure icons are imported

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

        # --- Attributes for the new consolidated card ---
        self.live_status_card: Optional[QFrame] = None  # The main container

        self.status_indicator_icon_label: Optional[QLabel] = None  # New: For CheckCircle, Info, XCircle etc.
        self.pnl_title_label: Optional[QLabel] = None  # Existing: "CURRENT P&L"
        self.pnl_display_label: Optional[QLabel] = None  # Existing: The P&L value
        # self.pnl_small_trend_bar: Optional[QFrame] = None # Optional: like the React example's mini chart/bar

        self.monitoring_target_title_label: Optional[QLabel] = None  # New: "MONITORING:"
        self.monitoring_target_info_label: Optional[QLabel] = None  # New: "Platform - Region: Defined/Not Set"

        # --- Other existing attributes for lower sections ---
        self.prereq_badge_label: Optional[QLabel] = None
        self.alerts_list: Optional[QListWidget] = None
        self.activity_log_display: Optional[LogDisplay] = None
        self.start_button: Optional[ActionButton] = None
        self.stop_button: Optional[DangerButton] = None
        self.flash_button: Optional[StyledButton] = None
        self.prereq_widgets: Dict[str, Dict[str, Any]] = {}
        self.prerequisite_setup_data: List[Tuple[str, str]] = [
            ("ct_path", "Cold Turkey Application Path"),
            ("ct_block_setup", "Cold Turkey Trading Block"),
            ("monitor_region", "P&L Monitor Region"),
            ("flatten_regions", "Flatten Position Regions"),
            ("pnl_detector", "P&L Detector"),
        ]

        self._setup_ui()
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
        # --- NEW: Consolidated Live Status Card (Top Row) ---
        # -----------------------------------------
        self.live_status_card = QFrame()
        self.live_status_card.setObjectName("liveStatusCard")  # New object name
        self.live_status_card.setProperty("class", "statusInfoCard")  # Use existing styling
        live_status_card_main_layout = QHBoxLayout(self.live_status_card)  # Main HBox for card
        live_status_card_main_layout.setContentsMargins(15, 10, 15, 10)  # Adjusted padding
        live_status_card_main_layout.setSpacing(15)

        # --- Left Part of Live Status Card: P&L and Status Indicator ---
        left_section_widget = QWidget()  # Container for left items
        left_section_layout = QVBoxLayout(left_section_widget)
        left_section_layout.setContentsMargins(0, 0, 0, 0)
        left_section_layout.setSpacing(3)  # Tight spacing

        # Row 1: P&L Title and Status Indicator Icon
        pnl_header_row_layout = QHBoxLayout()
        pnl_header_row_layout.setSpacing(6)

        self.status_indicator_icon_label = QLabel()
        self.status_indicator_icon_label.setObjectName("statusIndicatorIcon")
        self.status_indicator_icon_label.setFixedSize(20, 20)  # Adjust size as needed
        # Icon will be set by ViewModel based on monitoring state
        pnl_header_row_layout.addWidget(self.status_indicator_icon_label)

        self.pnl_title_label = QLabel("CURRENT P&L")
        self.pnl_title_label.setProperty("class", "cardTitle")  # Use smaller cardTitle class
        pnl_header_row_layout.addWidget(self.pnl_title_label)
        pnl_header_row_layout.addStretch(1)  # Push title and icon left
        left_section_layout.addLayout(pnl_header_row_layout)

        # Row 2: P&L Value
        self.pnl_display_label = QLabel("N/A")
        self.pnl_display_label.setObjectName("pnlDisplayLabel")  # Keep this ID for main P&L styling
        self.pnl_display_label.setProperty("state", "neutral")
        # Align left if desired for this layout
        # self.pnl_display_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        left_section_layout.addWidget(self.pnl_display_label)

        # Optional: Small P&L progress/trend bar (like React example)
        # self.pnl_small_trend_bar = QFrame()
        # self.pnl_small_trend_bar.setObjectName("pnlSmallTrendBar")
        # self.pnl_small_trend_bar.setMinimumHeight(8); self.pnl_small_trend_bar.setMaximumHeight(8)
        # self.pnl_small_trend_bar.setStyleSheet("background-color: #374151; border-radius: 4px;") # Placeholder
        # left_section_layout.addWidget(self.pnl_small_trend_bar)

        left_section_layout.addStretch(1)  # Push P&L info to the top of its VBox

        live_status_card_main_layout.addWidget(left_section_widget, 1)  # P&L + Status Icon takes some space

        # --- Optional: Vertical Separator Line ---
        v_separator = QFrame()
        v_separator.setFrameShape(QFrame.Shape.VLine)
        v_separator.setFrameShadow(QFrame.Shadow.Sunken)
        v_separator.setObjectName("cardVerticalSeparator")  # For QSS styling
        live_status_card_main_layout.addWidget(v_separator)

        # --- Right Part of Live Status Card: Monitoring Target Info ---
        right_section_widget = QWidget()  # Container for right items
        right_section_layout = QVBoxLayout(right_section_widget)
        right_section_layout.setContentsMargins(0, 0, 0, 0)
        right_section_layout.setSpacing(3)

        self.monitoring_target_title_label = QLabel("MONITORING TARGET")
        self.monitoring_target_title_label.setProperty("class", "cardTitle")
        right_section_layout.addWidget(self.monitoring_target_title_label)

        self.monitoring_target_info_label = QLabel("Platform: N/A - Region: N/A")
        self.monitoring_target_info_label.setObjectName("monitoringTargetInfoLabel")
        # This label can have its tooltip updated by the VM with coordinates
        right_section_layout.addWidget(self.monitoring_target_info_label)

        right_section_layout.addStretch(1)  # Push info to the top

        live_status_card_main_layout.addWidget(right_section_widget, 2)  # Give target info more space

        main_layout.addWidget(self.live_status_card)  # Add the consolidated card to the main layout
        # --- END NEW Consolidated Card ---

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
        if not self.view_model:
            # Using print as logger might not be initialized if VM itself is None early on
            print("ERROR: DashboardView._connect_signals - ViewModel is None. Cannot connect signals.")
            return

        self.view_model._logger.debug("DashboardView: Establishing signal connections...")

        # --- View -> ViewModel (User Actions) ---
        if hasattr(self, 'start_button') and self.start_button:
            self.start_button.clicked.connect(self.view_model.start_monitoring)
        if hasattr(self, 'stop_button') and self.stop_button:
            self.stop_button.clicked.connect(self.view_model.stop_monitoring)
        if hasattr(self, 'flash_button') and self.flash_button:
            self.flash_button.clicked.connect(self.view_model.test_flash_regions)

        # --- ViewModel -> View (UI Updates) ---

        # Consolidated "Live Status Card" Updates
        if hasattr(self, 'pnl_display_label') and self.pnl_display_label:
            self.view_model.current_pnl_text_changed.connect(self._update_pnl_display_text_and_state)
        else:
            self.view_model._logger.warning("DashboardView: pnl_display_label not found for connection.")

        if hasattr(self, 'status_indicator_icon_label') and self.status_indicator_icon_label:
            self.view_model.status_indicator_icon_info_changed.connect(self._update_status_indicator)
        else:
            self.view_model._logger.warning("DashboardView: status_indicator_icon_label not found for connection.")

        if hasattr(self, 'monitoring_target_info_label') and self.monitoring_target_info_label:
            # self.view_model.monitoring_target_text_changed.connect(self.monitoring_target_info_label.setText) # Old direct connection
            self.view_model.monitoring_target_text_changed.connect(self._set_monitoring_target_text)
        else:
            self.view_model._logger.warning("DashboardView: monitoring_target_info_label not found for connection.")
        # Prerequisites Panel Updates
        if hasattr(self, 'prereq_badge_label') and self.prereq_badge_label:
            self.view_model.prerequisites_completion_changed.connect(self.prereq_badge_label.setText)
        self.view_model.prerequisite_status_updated.connect(
            self._update_prerequisite_row)  # Assuming _update_prerequisite_row exists

        # Quick Actions Button Enablement
        if hasattr(self, 'start_button') and self.start_button:
            self.view_model.can_start_monitoring_changed.connect(self.start_button.setEnabled)
        if hasattr(self, 'stop_button') and self.stop_button:
            self.view_model.can_stop_monitoring_changed.connect(self.stop_button.setEnabled)
        if hasattr(self, 'flash_button') and self.flash_button:
            self.view_model.can_test_flash_changed.connect(self.flash_button.setEnabled)

        # Alerts List Update
        if hasattr(self, 'alerts_list') and self.alerts_list:
            self.view_model.recent_alerts_updated.connect(
                self._update_alerts_list)  # Assuming _update_alerts_list exists

        # Activity Log Update
        if hasattr(self, 'activity_log_display') and self.activity_log_display:
            self.view_model.activity_log_appended.connect(self.activity_log_display.append_message)

        # Prerequisite Action Buttons (assuming self.prereq_widgets is populated in _setup_ui)
        if hasattr(self, 'prereq_widgets') and self.prereq_widgets:
            for key, widgets_dict in self.prereq_widgets.items():
                action_button = widgets_dict.get("button")
                if action_button and isinstance(action_button, QPushButton):
                    # Check if already connected to avoid duplicate connections if _connect_signals is called multiple times
                    # This is a bit advanced; usually, connect_signals is called once.
                    # For simplicity now, we assume it's called once.
                    action_button.clicked.connect(self._handle_prerequisite_action_click)  # Assuming this slot exists
                else:
                    self.view_model._logger.warning(
                        f"DashboardView: Prerequisite button for key '{key}' not found or not a QPushButton.")
        else:
            self.view_model._logger.warning(
                "DashboardView: 'prereq_widgets' dictionary not found or empty. Cannot connect prerequisite action buttons.")

        self.view_model._logger.debug("DashboardView: Signal connections established/updated.")

    # --- Slots for ViewModel Signals ---

    @Slot(str)
    def _set_monitoring_target_text(self, text: str):  # Or a more descriptive name
        if hasattr(self, 'monitoring_target_info_label') and self.monitoring_target_info_label:
            if self.view_model and hasattr(self.view_model, '_logger'):
                self.view_model._logger.debug(f"DashboardView: Setting monitoring_target_info_label to '{text}'.")

            self.monitoring_target_info_label.setText(text)
            # Keep the unpolish/polish for robustness on initial load
            self.monitoring_target_info_label.style().unpolish(self.monitoring_target_info_label)
            self.monitoring_target_info_label.style().polish(self.monitoring_target_info_label)
            # self.monitoring_target_info_label.update() # update() is probably not needed if unpolish/polish is there
        else:
            if self.view_model and hasattr(self.view_model, '_logger'):
                self.view_model._logger.warning(
                    "DIAG: monitoring_target_info_label not found in _diag_update_target_text")

    @Slot(str)
    def _update_pnl_display_text_and_state(self, pnl_text: str):  # Renamed and used for consolidated card
        if not self.pnl_display_label: return
        self.pnl_display_label.setText(pnl_text)
        state = "neutral"
        if "N/A" == pnl_text:
            state = "neutral"
        elif "-" in pnl_text or "LOCKOUT" in pnl_text or "ERROR" in pnl_text:
            state = "negative"
        elif pnl_text != "Starting..." and pnl_text != "Waiting for data...":
            state = "positive"  # Avoid "positive" for intermediate states

        self.pnl_display_label.setProperty("state", state)
        self.pnl_display_label.style().unpolish(self.pnl_display_label)
        self.pnl_display_label.style().polish(self.pnl_display_label)

    # --- NEW Slot for status indicator icon ---
    @Slot(str, str)  # icon_key, tooltip_text
    def _update_status_indicator(self, icon_key: str, tooltip_text: str):
        if not hasattr(self, 'status_indicator_icon_label') or not self.status_indicator_icon_label: return
        if not hasattr(self, 'view_model') or not self.view_model or not hasattr(self.view_model, '_logger'): return

        icon_path = ":/icons/info.svg"  # Default icon
        is_dark = self.property("darkTheme") == True

        icon_color = QColor("#9ca3af") if is_dark else QColor("#6b7280")

        if icon_key == "active":
            icon_path = ":/icons/check-circle.svg"
            icon_color = QColor("#4ade80") if is_dark else QColor("#10b981")
        elif icon_key == "inactive":
            icon_path = ":/icons/info.svg"
            icon_color = QColor("#9ca3af") if is_dark else QColor("#6b7280")
        elif icon_key == "error":
            icon_path = ":/icons/x-circle.svg"
            icon_color = QColor("#f87171") if is_dark else QColor("#ef4444")
        elif icon_key == "busy":
            icon_path = ":/icons/activity.svg"
            icon_color = QColor("#facc15") if is_dark else QColor("#f59e0b")

        try:
            icon_size = QSize(18, 18)
            colored_icon = create_colored_svg_icon(icon_path, icon_color, icon_size)
            self.status_indicator_icon_label.setPixmap(colored_icon.pixmap(icon_size))
        except Exception as e:
            self.view_model._logger.error(f"Error setting status indicator icon ('{icon_key}'): {e}")
            self.status_indicator_icon_label.setText("?")
            self.status_indicator_icon_label.setPixmap(QPixmap())

        self.status_indicator_icon_label.setToolTip(tooltip_text)

    def _update_alerts_list(self, alerts: List[str]):
        """Clears and repopulates the recent alerts list with enhanced styling."""
        if not self.alerts_list: return  # Safety check
        self.alerts_list.clear()

        is_dark_theme = self.property("darkTheme") == True  # Check current theme

        if alerts:
            for alert_text_with_level in alerts:  # Assuming alerts might now be "timestamp: [LEVEL] message"
                item = QListWidgetItem()

                alert_type = "info"  # default
                icon_path = ":/icons/info.svg"
                base_text = alert_text_with_level

                # Determine alert type and icon from the message content more robustly
                if "[ERROR]" in alert_text_with_level.upper() or "THRESHOLD" in alert_text_with_level.upper() or "LOCKOUT" in alert_text_with_level.upper():
                    alert_type = "error"
                    icon_path = ":/icons/x-circle.svg"  # Or alert-triangle
                elif "[WARNING]" in alert_text_with_level.upper():
                    alert_type = "warning"
                    icon_path = ":/icons/alert-triangle.svg"
                elif "[SUCCESS]" in alert_text_with_level.upper() or "VERIFIED" in alert_text_with_level.upper():
                    alert_type = "success"
                    icon_path = ":/icons/check-circle.svg"

                # Define icon colors based on type and theme
                icon_color = QColor()
                if alert_type == "error":
                    icon_color = QColor("#f87171") if is_dark_theme else QColor("#ef4444")  # Red
                elif alert_type == "warning":
                    icon_color = QColor("#fcd34d") if is_dark_theme else QColor("#f59e0b")  # Amber
                elif alert_type == "success":
                    icon_color = QColor("#4ade80") if is_dark_theme else QColor("#10b981")  # Green
                else:  # info
                    icon_color = QColor("#60a5fa") if is_dark_theme else QColor("#3b82f6")  # Blue

                try:
                    colored_icon = create_colored_svg_icon(icon_path, icon_color, QSize(16, 16))
                    item.setIcon(colored_icon)
                except Exception as e:
                    if hasattr(self, 'view_model') and self.view_model:
                        self.view_model._logger.error(f"Error setting alert icon for '{alert_text_with_level}': {e}")

                item.setText(alert_text_with_level)  # Set the full text
                item.setData(Qt.ItemDataRole.UserRole, alert_type)  # For QSS: QListWidget::item[alertType="error"]
                item.setSizeHint(QSize(0, 32))  # Adjust height for icon + text
                self.alerts_list.addItem(item)
        else:
            # ... (your existing placeholder item logic) ...
            placeholder_item = QListWidgetItem("No recent alerts.")
            # Optional: Style placeholder differently or set a default icon
            # info_icon_color = QColor("#9ca3af") if is_dark_theme else QColor("#6b7280")
            # placeholder_item.setIcon(create_colored_svg_icon(":/icons/info.svg", info_icon_color, QSize(16,16)))
            placeholder_item.setForeground(QColor("#9ca3af") if is_dark_theme else QColor("#6b7280"))
            self.alerts_list.addItem(placeholder_item)

    @Slot(str, str, str, bool)
    def _update_prerequisite_row(self, key: str, status_description: str, status_state: str, show_action: bool):
        """Updates the UI row for a specific prerequisite using create_colored_svg_icon."""
        if not hasattr(self, 'prereq_widgets') or key not in self.prereq_widgets:
            # Log error if ViewModel is available
            if hasattr(self, 'view_model') and self.view_model and hasattr(self.view_model, '_logger'):
                self.view_model._logger.error(
                    f"DashboardView: Received update for unknown/uninitialized prerequisite key '{key}'")
            return

        widgets = self.prereq_widgets[key]
        text_label: QLabel = widgets["text"]
        icon_label: QLabel = widgets["icon"]  # This is the QLabel where the icon will be set
        action_button: QPushButton = widgets["button"]
        display_name: str = widgets["display_name"]

        # 1. Update Text Label
        text_label.setText(f"{display_name}: {status_description}")

        # 2. Determine Icon Path based on status_state
        icon_path = ""
        if status_state == "ok":
            icon_path = ":/icons/check-circle.svg"
        elif status_state == "warning":
            icon_path = ":/icons/alert-triangle.svg"
        elif status_state == "error" or status_state == "missing":
            icon_path = ":/icons/x-circle.svg"
        else:  # "info", "pending", "neutral", or any other default
            icon_path = ":/icons/info.svg"

        # 3. Determine Icon Color based on status_state AND current theme
        is_dark_theme = self.property("darkTheme") == True

        # Define theme-aware colors for the icons
        # These colors are for the icons themselves, not necessarily text or backgrounds elsewhere.
        ok_icon_color = QColor("#4ade80") if is_dark_theme else QColor("#10b981")  # Green
        warning_icon_color = QColor("#fcd34d") if is_dark_theme else QColor("#f59e0b")  # Amber/Yellow
        error_icon_color = QColor("#f87171") if is_dark_theme else QColor("#ef4444")  # Red
        info_icon_color = QColor("#9ca3af") if is_dark_theme else QColor("#6b7280")  # Muted Gray

        icon_color_map = {
            "ok": ok_icon_color,
            "warning": warning_icon_color,
            "error": error_icon_color,
            "missing": error_icon_color,  # Same as error
            "info": info_icon_color,
            "pending": info_icon_color,  # Use info color for pending
            "neutral": info_icon_color  # Use info color for neutral
        }
        actual_icon_color_to_use = icon_color_map.get(status_state, info_icon_color)

        # 4. Create and Set the Colored Icon
        if icon_path:
            try:
                # Ensure icon_label has no old graphics effect if switching from QGraphicsColorizeEffect
                if icon_label.graphicsEffect():
                    icon_label.setGraphicsEffect(None)

                colored_icon = create_colored_svg_icon(icon_path, actual_icon_color_to_use, QSize(16, 16))
                icon_label.setPixmap(colored_icon.pixmap(QSize(16, 16)))  # Set directly on the QLabel
                icon_label.setText("")  # Clear any fallback text
            except Exception as e:
                icon_label.setText("!")  # Fallback if icon creation fails
                icon_label.setPixmap(QPixmap())  # Clear pixmap
                if hasattr(self, 'view_model') and self.view_model and hasattr(self.view_model, '_logger'):
                    self.view_model._logger.warning(f"Icon error for prereq '{key}': {icon_path}, {e}")
        else:
            icon_label.setPixmap(QPixmap())  # Clear pixmap if no icon path
            icon_label.setText("")

        # 5. Update Button Visibility and Text/Target (existing logic)
        action_button.setVisible(show_action)
        if show_action:
            target_tab = "Unknown";
            button_text = "Fix Issue"
            if key == "ct_path":
                target_tab = "Settings"; button_text = "Set Path"
            elif key == "ct_block_setup":
                target_tab = "Settings"; button_text = "Configure Block"
            elif key == "monitor_region":
                target_tab = "Visual Setup"; button_text = "Define Region"
            elif key == "flatten_regions":
                target_tab = "Visual Setup"; button_text = "Add Regions"
            elif key == "pnl_detector":
                target_tab = "Visual Setup"; button_text = "Configure Detector"
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
