# src/presentation/components/ui_components.py
from PySide6.QtWidgets import QPushButton, QLabel, QGroupBox

class StyledButton(QPushButton):
    """Custom styled button with standard appearance."""
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet("""
            QPushButton {
                background-color: #3a7ca5;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #2a6b94;
            }
            QPushButton:pressed {
                background-color: #1a5a83;
            }
        """)

class GroupHeader(QGroupBox):
    """Standard group box with consistent styling."""
    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        self.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #cccccc;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 5px;
            }
        """)