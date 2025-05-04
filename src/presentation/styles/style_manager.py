# src/presentation/styles/style_manager.py

"""
Centralized styling system for MonitorPal.
Keeps stylesheets separate from UI logic for better maintainability.
"""
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QFile, QTextStream

class StyleManager:
    _style_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'stylesheets')
    _loaded_style = "" # Store the loaded application style

    @classmethod
    def load_application_stylesheet(cls):
        """Loads the main application stylesheet."""
        if cls._loaded_style: # Basic caching
            return cls._loaded_style

        full_path = os.path.join(cls._style_dir, 'application.qss')
        print(f"StyleManager: Loading application stylesheet: {full_path}")
        if not os.path.exists(full_path):
            print(f"StyleManager WARNING: Stylesheet not found: {full_path}")
            return ""
        try:
            file = QFile(full_path)
            if file.open(QFile.ReadOnly | QFile.Text):
                stream = QTextStream(file)
                cls._loaded_style = stream.readAll()
                file.close()
                print(f"StyleManager: Loaded application.qss ({len(cls._loaded_style)} chars)")
                return cls._loaded_style
            else:
                print(f"StyleManager ERROR: Could not open stylesheet: {full_path}")
                return ""
        except Exception as e:
            print(f"StyleManager ERROR loading stylesheet {full_path}: {e}")
            return ""

    @classmethod
    def apply_application_style(cls, app: QApplication):
        """Applies the loaded global style to the app."""
        style = cls.load_application_stylesheet()
        if style:
            app.setStyleSheet(style)
            print("StyleManager: Applied application style.")
        else:
            print("StyleManager: No application style applied (was empty or failed to load).")