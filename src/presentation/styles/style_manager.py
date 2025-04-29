# src/presentation/styles/style_manager.py

"""
Centralized styling system for MonitorPal.
Keeps stylesheets separate from UI logic for better maintainability.
"""

import os
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QFile, QTextStream


class StyleManager:
    """Manages application-wide styling and theme."""

    # Base path to stylesheets
    _style_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'stylesheets')

    # Cache for loaded stylesheets
    _stylesheet_cache = {}

    @classmethod
    def apply_application_style(cls, app):
        """Apply global application style to QApplication instance."""
        # Pass path relative to _style_dir, which already includes 'stylesheets'
        app.setStyleSheet(cls.load_stylesheet('application.qss'))  # <-- Corrected path

    @classmethod
    def get_component_style(cls, component_name):
        """Get stylesheet for a specific component."""
        return cls.load_stylesheet(f'components/{component_name}.qss')

    @classmethod
    def get_view_style(cls, view_name):
        """Get stylesheet for a specific view."""
        return cls.load_stylesheet(f'style_views/{view_name}.qss')

    @classmethod
    def get_button_style(cls, button_type):
        """Get stylesheet for a specific button type."""
        return cls.load_stylesheet(f'components/buttons/{button_type}.qss')

    @classmethod
    def load_stylesheet(cls, relative_path):
        """Load stylesheet from file with caching."""
        if relative_path in cls._stylesheet_cache:
            return cls._stylesheet_cache[relative_path]

        full_path = os.path.join(cls._style_dir, relative_path)

        # Handle missing files gracefully
        if not os.path.exists(full_path):
            print(f"Warning: Stylesheet not found: {full_path}")
            return ""

        try:
            file = QFile(full_path)
            if file.open(QFile.ReadOnly | QFile.Text):
                stream = QTextStream(file)
                stylesheet = stream.readAll()
                file.close()

                # Cache the loaded stylesheet
                cls._stylesheet_cache[relative_path] = stylesheet
                return stylesheet
            else:
                print(f"Error: Could not open stylesheet: {full_path}")
                return ""
        except Exception as e:
            print(f"Error loading stylesheet {full_path}: {e}")
            return ""

    @classmethod
    def apply_dark_header_style(cls, widget):
        """Apply the dark header panel style to a widget."""
        widget.setStyleSheet("""
            background-color: #2c3e50; 
            border-radius: 6px;
            color: #ecf0f1;
        """)

    @classmethod
    def apply_toolbar_label_style(cls, label):
        """Apply toolbar label styling."""
        label.setStyleSheet("""
            color: #ecf0f1; 
            font-weight: bold; 
            background-color: #34495e;
            padding: 3px 7px;
            border-radius: 3px;
        """)