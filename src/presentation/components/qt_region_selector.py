# src/presentation/components/qt_region_selector.py
"""
Qt-native region selection tool using QDialog and QMainWindow overlay.
Styling is handled via StyleManager and QSS.
"""
import time
from typing import Tuple, Optional

# --- Qt Imports ---
from PySide6.QtCore import Qt, QRect, QPoint, QSize, QTimer, Signal, QEventLoop
from PySide6.QtGui import QPainter, QPen, QColor, QGuiApplication, QPixmap, QCursor
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QMainWindow, QWidget, QRubberBand
)

# --- Application Imports ---
from src.presentation.styles.style_manager import StyleManager
# Removed imports for Worker and ILoggerService as the Worker class is removed


class RegionSelectorDialog(QDialog):
    """Dialog for showing instructions before region selection."""

    def __init__(self, message: str, parent=None):
        """Initialize the instruction dialog."""
        super().__init__(parent)
        self.setObjectName("RegionSelectorDialog") # Set object name for QSS
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.setWindowTitle("Region Selection")
        self.setModal(True)
        # Let QSS control sizing if possible, but set a minimum/fixed if needed
        self.setMinimumWidth(400)
        # Apply component stylesheet
        self.setStyleSheet(StyleManager.get_component_style("region_selector_dialog"))

        # Layout
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Message with icon
        message_layout = QHBoxLayout()
        icon_label = QLabel()
        icon_label.setObjectName("dialogIconLabel")
        icon_label.setFixedSize(32, 32) # Keep fixed size for icon placeholder
        message_layout.addWidget(icon_label, 0)

        formatted_message = message.replace("\n", "<br>")
        msg_label = QLabel(f"<b>{formatted_message}</b>")
        msg_label.setObjectName("dialogMessageLabel")
        msg_label.setWordWrap(True)
        msg_label.setTextFormat(Qt.RichText)
        message_layout.addWidget(msg_label, 1)
        layout.addLayout(message_layout)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("dialogCancelButton")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        self.continue_btn = QPushButton("Continue")
        self.continue_btn.setObjectName("dialogContinueButton")
        self.continue_btn.setDefault(True)
        self.continue_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.continue_btn)
        layout.addLayout(button_layout)

        self.center_on_screen()

    def center_on_screen(self):
        """Center dialog on the primary screen."""
        try:
            screen = QGuiApplication.primaryScreen()
            if screen:
                center_point = screen.availableGeometry().center()
                frame_geo = self.frameGeometry()
                frame_geo.moveCenter(center_point)
                self.move(frame_geo.topLeft())
        except Exception as e:
            print(f"Error centering dialog: {e}") # Use logger if available


class QtRegionSelector(QMainWindow):
    """
    Full-screen overlay for selecting a rectangular region.
    Styling for internal labels is handled by QSS.
    Background and selection border are drawn manually in paintEvent.
    """
    region_selected = Signal(tuple)  # Emits global (x, y, width, height)
    selection_cancelled = Signal()

    def __init__(self, parent=None):
        """Initialize the region selection tool."""
        super().__init__(parent)
        self.setObjectName("QtRegionSelectorOverlay") # Object name for main window

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Calculate geometry covering all screens using QGuiApplication
        virtual_geo = QGuiApplication.primaryScreen().virtualGeometry()
        self.screen_geometry = virtual_geo
        self.setGeometry(self.screen_geometry)

        self.setCursor(Qt.CrossCursor)

        # Central widget (may not be strictly necessary if not applying complex QSS to main window)
        # But useful as a parent for labels if styling the main window directly causes issues.
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        # Apply specific styles to the central widget or its children via QSS
        self.central_widget.setObjectName("selectorCentralWidget")
        self.central_widget.setStyleSheet(StyleManager.get_component_style("qt_region_selector"))


        # Rubber band for visual feedback during drag
        self.rubber_band = QRubberBand(QRubberBand.Rectangle, self.central_widget) # Parent is central widget

        # State variables
        self.origin = QPoint()
        self.selection_rect: Optional[QRect] = None # Store the selection rectangle relative to the window
        self.is_selecting = False

        # Instructions label (parented to central widget)
        self.instructions = QLabel("Click and drag to select a region. Press Esc to cancel.", self.central_widget)
        self.instructions.setObjectName("selectorInstructionsLabel")
        self.instructions.setAlignment(Qt.AlignCenter)
        self.instructions.adjustSize() # Adjust size based on content and QSS padding/font
        # Position near bottom-center AFTER adjusting size
        self.instructions.move(
            (self.width() - self.instructions.width()) // 2,
            self.height() - self.instructions.height() - 50
        )
        self.instructions.show() # Ensure it's visible

        # Dimensions label (parented to central widget)
        self.dimensions_label = QLabel(self.central_widget)
        self.dimensions_label.setObjectName("selectorDimensionsLabel")
        self.dimensions_label.hide() # Initially hidden

    def paintEvent(self, event):
        """Paint the overlay background and selection border."""
        painter = QPainter(self)
        # Draw semi-transparent background overlay directly on the main window
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80))

        # Selection rectangle border is drawn manually for clarity over transparency
        if self.is_selecting and self.selection_rect:
             # Draw red border around selection rectangle
             pen = QPen(QColor(255, 0, 0, 200), 2) # Slightly transparent red
             pen.setStyle(Qt.PenStyle.SolidLine)
             painter.setPen(pen)
             painter.setBrush(Qt.BrushStyle.NoBrush) # Don't fill the rect here
             # Draw the rectangle based on the stored selection_rect
             painter.drawRect(self.selection_rect)

             # Note: The visual "clearing" is handled by the rubber band now.
             # The manual clearing in paintEvent is removed as QRubberBand handles it better.


    def mousePressEvent(self, event):
        """Start selection."""
        if event.button() == Qt.LeftButton:
            self.origin = event.pos() # Position relative to this window
            # Start rubber band geometry relative to its parent (central_widget)
            # mapFromParent is not needed if origin is already relative to window
            self.rubber_band.setGeometry(QRect(self.origin, QSize()))
            self.rubber_band.show()
            self.selection_rect = QRect(self.origin, QSize()) # Initialize selection rect
            self.is_selecting = True
            self.update() # Redraw to show initial state if needed

    def mouseMoveEvent(self, event):
        """Update selection rectangle and rubber band."""
        if self.is_selecting:
            current_pos = event.pos()
            self.selection_rect = QRect(self.origin, current_pos).normalized()
            # Update rubber band geometry (relative to its parent)
            self.rubber_band.setGeometry(self.selection_rect)

            # Update dimensions label
            width = self.selection_rect.width()
            height = self.selection_rect.height()
            self.dimensions_label.setText(f"{width} × {height} px")
            self.dimensions_label.adjustSize()
            # Position label relative to cursor, ensuring it stays within bounds
            label_pos = event.pos() + QPoint(15, 15) # Offset from cursor
            label_pos.setX(min(label_pos.x(), self.width() - self.dimensions_label.width() - 5))
            label_pos.setY(min(label_pos.y(), self.height() - self.dimensions_label.height() - 5))
            label_pos.setX(max(label_pos.x(), 5))
            label_pos.setY(max(label_pos.y(), 5))
            self.dimensions_label.move(label_pos)
            self.dimensions_label.show()
            # No need to call self.update() here, QRubberBand handles its own painting mostly

    def mouseReleaseEvent(self, event):
        """Finalize selection."""
        if event.button() == Qt.LeftButton and self.is_selecting:
            self.is_selecting = False
            self.rubber_band.hide() # Hide rubber band
            self.dimensions_label.hide() # Hide dimensions

            min_size = 5
            # Use the final selection_rect stored during mouseMove
            if self.selection_rect and self.selection_rect.width() > min_size and self.selection_rect.height() > min_size:
                # Get coordinates relative to the window
                local_rect = self.selection_rect
                # Map the top-left corner to global screen coordinates
                global_top_left = self.mapToGlobal(local_rect.topLeft())
                # Emit global coordinates
                self.region_selected.emit((
                    global_top_left.x(),
                    global_top_left.y(),
                    local_rect.width(),
                    local_rect.height()
                ))
                QTimer.singleShot(50, self.close) # Close quickly after selection
            else:
                 # Selection too small or cancelled during drag, reset
                 self.selection_rect = None
                 self.update() # Repaint to remove any drawn border

    def keyPressEvent(self, event):
        """Handle Escape key for cancellation."""
        if event.key() == Qt.Key_Escape:
            self.selection_cancelled.emit()
            self.close()
        # Optional: Confirm with Enter/Return (already handled in mouseRelease)
        # elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
        #     self.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, self.mapFromGlobal(QCursor.pos()), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))


# --- Orchestration Function ---
def select_region_qt(message="Select a region by clicking and dragging") -> Optional[Tuple[int, int, int, int]]:
    """
    Displays instruction dialog, then full-screen overlay for region selection.
    Uses QEventLoop to block synchronously while processing UI events.

    Args:
        message: Instruction message for the dialog.

    Returns:
        Selected region (x, y, width, height) in global screen coordinates, or None if cancelled.
    """
    try:
        app = QApplication.instance()
        if not app:
            print("ERROR: No QApplication instance found for select_region_qt.") # Use logger
            return None

        # 1. Show Instructions
        dialog = RegionSelectorDialog(message)
        if dialog.exec() != QDialog.Accepted:
            print("Region selection cancelled at dialog.") # Use logger
            return None
        app.processEvents() # Ensure dialog closes visually

        # 2. Prepare Selector and State
        selected_region: Optional[Tuple[int, int, int, int]] = None
        selection_done = False # Flag to break the event loop

        selector = QtRegionSelector()

        # 3. Connect Signals
        def on_region_selected(region_tuple):
            nonlocal selected_region, selection_done
            print(f"Signal received: region_selected {region_tuple}") # Debugging
            selected_region = region_tuple
            selection_done = True

        def on_selection_cancelled():
            nonlocal selection_done
            print("Signal received: selection_cancelled") # Debugging
            selection_done = True

        selector.region_selected.connect(on_region_selected)
        selector.selection_cancelled.connect(on_selection_cancelled)

        # 4. Show Selector and Wait using QEventLoop
        selector.show()
        selector.activateWindow() # Try to bring it to front

        loop = QEventLoop()
        # Use a QTimer to periodically check the flag and quit the loop,
        # allowing other Qt events (like painting, mouse handling) to process.
        timer = QTimer()
        timer.setInterval(100) # Check every 100ms
        timer.timeout.connect(lambda: loop.quit() if selection_done else None)
        timer.start()

        print("Starting region selection event loop...") # Debugging
        loop.exec() # Blocks here until loop.quit() is called
        print("Region selection event loop finished.") # Debugging
        timer.stop()

        # 5. Ensure selector is closed after loop exits
        # Check isVisible() before closing to avoid errors if already closed by user (Esc)
        if selector.isVisible():
            selector.close()
            selector.deleteLater() # Schedule for deletion

        print(f"Returning selected region: {selected_region}") # Debugging
        return selected_region

    except Exception as e:
        import traceback
        print(f"ERROR during region selection process: {e}\n{traceback.format_exc()}") # Use logger
        # Clean up selector if it exists and an error occurred
        if 'selector' in locals() and isinstance(selector, QMainWindow) and selector.isVisible():
             try:
                  selector.close()
                  selector.deleteLater()
             except Exception as cleanup_e:
                  print(f"Error closing selector during exception handling: {cleanup_e}")
        return None