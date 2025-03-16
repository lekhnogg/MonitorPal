# src/presentation/components/qt_region_selector.py
"""
Qt-native region selection tool for the monitoring service.

Provides a UI for selecting screen regions to monitor using Qt components.
"""
import time
from typing import Tuple, Optional

from PySide6.QtCore import Qt, QRect, QPoint, QSize, QTimer, Signal, QObject, QEventLoop
from PySide6.QtGui import QPainter, QPen, QColor, QBrush, QGuiApplication, QScreen, QPixmap, QCursor
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QMainWindow, QWidget, QRubberBand
)

from src.domain.services.i_background_task_service import Worker
from src.domain.services.i_logger_service import ILoggerService


class RegionSelectorDialog(QDialog):
    """Dialog for showing instructions before region selection."""

    def __init__(self, message: str, parent=None):
        """
        Initialize the instruction dialog.

        Args:
            message: Instruction message to display
            parent: Parent widget
        """
        super().__init__(parent)
        self.setWindowFlags(
            self.windowFlags() |
            Qt.WindowStaysOnTopHint
        )
        self.setWindowTitle("Region Selection")
        self.setModal(True)
        self.setFixedWidth(450)

        # Layout
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Message with icon in horizontal layout
        message_layout = QHBoxLayout()

        # Add icon
        icon_label = QLabel()
        icon_label.setFixedSize(32, 32)
        icon_label.setStyleSheet("background-color: #3a7ca5; border-radius: 4px;")
        message_layout.addWidget(icon_label, 0)

        # Message with HTML formatting
        formatted_message = message.replace("\n", "<br>")
        msg_label = QLabel(f"<b>{formatted_message}</b>")
        msg_label.setWordWrap(True)
        msg_label.setTextFormat(Qt.RichText)
        message_layout.addWidget(msg_label, 1)

        layout.addLayout(message_layout)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        self.continue_btn = QPushButton("Continue")
        self.continue_btn.setDefault(True)
        self.continue_btn.clicked.connect(self.accept)
        self.continue_btn.setStyleSheet(
            "background-color: #3a7ca5; color: white; padding: 8px 16px;"
        )
        button_layout.addWidget(self.continue_btn)

        layout.addLayout(button_layout)

        # Center on screen
        self.center_on_screen()

    def center_on_screen(self):
        """Center dialog on the primary screen."""
        frame_geo = self.frameGeometry()
        screen = QGuiApplication.primaryScreen()
        center_point = screen.availableGeometry().center()
        frame_geo.moveCenter(center_point)
        self.move(frame_geo.topLeft())


class QtRegionSelector(QMainWindow):
    """
    A full-screen, semi-transparent overlay that lets the user click and drag
    to select a rectangular region using Qt's native components.
    """
    region_selected = Signal(tuple)  # (x, y, width, height)
    selection_cancelled = Signal()

    def __init__(self, parent=None):
        """Initialize the region selection tool."""
        super().__init__(parent)

        # Make this window borderless, topmost
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool  # So it doesn't appear in taskbar
        )

        # Make the background translucent
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Set geometry to cover all screens
        desktop = QApplication.desktop() if hasattr(QApplication, 'desktop') else None
        if desktop:
            # Use virtual desktop that spans all monitors
            self.screen_geometry = desktop.virtualGeometry()
        else:
            # Fallback to QGuiApplication for Qt6
            screens = QGuiApplication.screens()
            if len(screens) > 1:
                # Combine geometries of all screens
                left = min(screen.geometry().left() for screen in screens)
                top = min(screen.geometry().top() for screen in screens)
                right = max(screen.geometry().right() for screen in screens)
                bottom = max(screen.geometry().bottom() for screen in screens)
                self.screen_geometry = QRect(left, top, right - left, bottom - top)
            else:
                self.screen_geometry = QGuiApplication.primaryScreen().geometry()

        self.setGeometry(self.screen_geometry)

        # Set the cursor to crosshair
        self.setCursor(Qt.CrossCursor)

        # Create a central widget
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)

        # Create a rubber band for selection
        self.rubber_band = QRubberBand(QRubberBand.Rectangle, self)

        # Variables for storing the selection
        self.origin = QPoint()
        self.current = QPoint()
        self.start_pos = None
        self.selection_rect = None
        self.is_selecting = False

        # Instructions label
        self.instructions = QLabel("Click and drag to select a region. Press Esc to cancel.", self)
        self.instructions.setStyleSheet(
            "color: white; background-color: rgba(0, 0, 0, 150); padding: 10px; border-radius: 5px;"
        )
        self.instructions.setAlignment(Qt.AlignCenter)
        self.instructions.adjustSize()
        self.instructions.move(
            (self.width() - self.instructions.width()) // 2,
            self.height() - self.instructions.height() - 50
        )

        # Dimensions label
        self.dimensions_label = QLabel(self)
        self.dimensions_label.setStyleSheet(
            "color: white; background-color: rgba(0, 0, 0, 150); padding: 5px; border-radius: 3px;"
        )
        self.dimensions_label.hide()

    def paintEvent(self, event):
        """Paint the overlay with the selection rectangle."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Fill entire screen with semi-transparent background
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80))

        # If selection in progress, highlight the selected area
        if self.is_selecting and self.selection_rect:
            # Draw inner clear rectangle for the selected area
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(self.selection_rect, Qt.transparent)

            # Reset to normal composition mode for the border
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

            # Draw red border around selection
            pen = QPen(QColor(255, 0, 0), 2)
            painter.setPen(pen)
            painter.drawRect(self.selection_rect)

    def mousePressEvent(self, event):
        """Handle mouse press - start region selection."""
        if event.button() == Qt.LeftButton:
            self.origin = event.pos()
            self.rubber_band.setGeometry(QRect(self.origin, QSize()))
            self.rubber_band.show()
            self.is_selecting = True
            self.start_pos = event.pos()
            self.selection_rect = QRect(self.start_pos, self.start_pos)
            self.current = event.pos()
            self.update()

    def mouseMoveEvent(self, event):
        """Handle mouse movement - update selection rectangle."""
        if self.is_selecting:
            self.current = event.pos()
            self.selection_rect = QRect(self.start_pos, self.current).normalized()
            self.rubber_band.setGeometry(self.selection_rect)

            # Update dimensions label
            width = self.selection_rect.width()
            height = self.selection_rect.height()
            self.dimensions_label.setText(f"{width} × {height} px")
            self.dimensions_label.adjustSize()

            # Position the dimensions label near the current mouse position
            label_x = event.pos().x() + 15
            label_y = event.pos().y() + 15

            # Ensure the label stays within screen bounds
            if label_x + self.dimensions_label.width() > self.width():
                label_x = self.width() - self.dimensions_label.width() - 10
            if label_y + self.dimensions_label.height() > self.height():
                label_y = self.height() - self.dimensions_label.height() - 10

            self.dimensions_label.move(label_x, label_y)
            self.dimensions_label.show()

            self.update()

    def mouseReleaseEvent(self, event):
        """Handle mouse release - finalize selection and close."""
        if event.button() == Qt.LeftButton and self.is_selecting:
            self.is_selecting = False

            # Ensure we have a valid selection (not just a click)
            min_size = 5  # Minimum area to recognize as an intentional selection
            if self.selection_rect.width() > min_size and self.selection_rect.height() > min_size:
                # Convert to (x, y, width, height) format
                local_x = self.selection_rect.x()
                local_y = self.selection_rect.y()
                width = self.selection_rect.width()
                height = self.selection_rect.height()

                # Convert to global coordinates by adding the window's position
                global_point = self.mapToGlobal(QPoint(local_x, local_y))
                global_x = global_point.x()
                global_y = global_point.y()

                # Emit the signal with the global coordinates
                self.region_selected.emit((global_x, global_y, width, height))

                # Give a brief moment to see the final selection
                QTimer.singleShot(200, self.close)
            else:
                # Reset if it was just a click or tiny movement
                self.rubber_band.hide()
                self.selection_rect = None
                self.dimensions_label.hide()
                self.update()

    def keyPressEvent(self, event):
        """Handle key press - cancel on Escape, confirm on Enter."""
        if event.key() == Qt.Key_Escape:
            self.selection_cancelled.emit()
            self.close()
        # Accept Enter/Return to confirm current selection
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter) and self.selection_rect:
            if self.selection_rect.width() > 5 and self.selection_rect.height() > 5:
                x = self.selection_rect.x()
                y = self.selection_rect.y()
                width = self.selection_rect.width()
                height = self.selection_rect.height()
                self.region_selected.emit((x, y, width, height))
            self.close()


class QtRegionSelectorWorker(Worker[Optional[Tuple[int, int, int, int]]]):
    """Worker for selecting a region from the screen using Qt components."""

    def __init__(self, message: str, logger: ILoggerService):
        """Initialize the worker."""
        super().__init__()
        self.message = message
        self.logger = logger
        self.selected_region = None

    def execute(self) -> Optional[Tuple[int, int, int, int]]:
        """Execute the region selection process."""
        try:
            app = QApplication.instance()
            if not app:
                self.logger.error("No QApplication instance found")
                return None

            # Show instruction dialog
            dialog = RegionSelectorDialog(self.message)
            if dialog.exec() != QDialog.Accepted:
                return None

            # Create signals for communication
            self.region_selector = QtRegionSelector()

            # Connect signals
            self.region_selector.region_selected.connect(self._on_region_selected)
            self.region_selector.selection_cancelled.connect(self._on_selection_cancelled)

            # Show the selector
            self.region_selector.show()
            self.region_selector.activateWindow()

            # Wait for selection (max 60 seconds)
            timeout = 60  # seconds
            start_time = time.time()

            while self.selected_region is None:
                app.processEvents()

                # Check for timeout
                if time.time() - start_time > timeout:
                    self.logger.warning("Region selection timed out")
                    return None

                # Check for cancellation
                if self.cancel_requested:
                    self.logger.info("Region selection cancelled")
                    self.region_selector.close()
                    return None

                # Sleep to reduce CPU usage
                time.sleep(0.1)

            return self.selected_region

        except Exception as e:
            self.logger.error(f"Error in region selection: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None

    def _on_region_selected(self, region):
        """Handle region selection."""
        self.selected_region = region

    def _on_selection_cancelled(self):
        """Handle cancellation."""
        self.selected_region = None


def select_region_qt(message="Select a region by clicking and dragging") -> Optional[Tuple[int, int, int, int]]:
    """
    Display an instruction dialog, then a full-screen overlay to allow the user
    to select a rectangular region using Qt components.

    Args:
        message: Instruction message to display

    Returns:
        The selected region as (left, top, width, height), or None if canceled
    """
    try:
        # Ensure we have a QApplication instance
        app = QApplication.instance()
        if not app:
            print("No QApplication instance found. Cannot create selection tool.")
            return None

        # Create instruction dialog
        dialog = RegionSelectorDialog(message)

        # Show dialog and wait for user response
        if dialog.exec() != QDialog.Accepted:
            return None

        # Process events to ensure dialog is fully closed
        app.processEvents()

        # Create region selector
        selected_region = None
        selection_done = False

        selector = QtRegionSelector()

        # Connect signals
        def on_region_selected(region):
            nonlocal selected_region, selection_done
            selected_region = region
            selection_done = True

        def on_selection_cancelled():
            nonlocal selection_done
            selection_done = True

        selector.region_selected.connect(on_region_selected)
        selector.selection_cancelled.connect(on_selection_cancelled)

        # Show selector
        selector.show()
        selector.activateWindow()

        # Wait for selection to complete using QEventLoop instead of sleep
        loop = QEventLoop()
        timer = QTimer()
        timer.setInterval(50)  # 50ms checks
        timer.timeout.connect(lambda: loop.quit() if selection_done else None)
        timer.start()
        loop.exec()  # Much more responsive than sleep approach
        timer.stop()

        return selected_region

    except Exception as e:
        import traceback
        print(f"Error in region selection: {e}")
        print(traceback.format_exc())
        return None