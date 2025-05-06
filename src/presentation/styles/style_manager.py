# src/presentation/styles/style_manager.py

"""
Centralized styling system for MonitorPal.
Loads and applies stylesheets, supporting separate and complete theme files
(e.g., light_theme.qss, dark_theme.qss).
"""
import os
import logging
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QFile, QTextStream, QDir

# Configure a logger for the StyleManager
logger = logging.getLogger(__name__) # Uses the module's name for the logger

class StyleManager:
    """
    Manages loading and applying application stylesheets.
    Supports distinct, complete theme files for light and dark modes.
    """
    # Determine the directory where stylesheet files (.qss) are located.
    # This is usually a 'stylesheets' subdirectory next to this style_manager.py file.
    _script_dir: str = os.path.dirname(os.path.abspath(__file__))
    _style_dir: str = os.path.join(_script_dir, 'stylesheets')

    # Cache for loaded stylesheet content to avoid redundant file I/O.
    _light_theme_cache: str | None = None
    _dark_theme_cache: str | None = None

    @classmethod
    def _resolve_path(cls, filename: str) -> str:
        """
        Constructs the full, absolute path to a stylesheet file within the _style_dir.

        Args:
            filename: The name of the stylesheet file (e.g., "light_theme.qss").

        Returns:
            The absolute path to the stylesheet file.
        """
        return os.path.join(cls._style_dir, filename)

    @classmethod
    def _read_stylesheet(cls, file_path: str) -> str:
        """
        Reads the content of a given stylesheet file.

        Args:
            file_path: The absolute path to the stylesheet file.

        Returns:
            The content of the stylesheet as a string, or an empty string if an error occurs.
        """
        logger.debug(f"Attempting to load stylesheet: {file_path}")
        if not os.path.exists(file_path):
            logger.warning(f"Stylesheet not found: {file_path}")
            return ""
        try:
            # Use QFile for reading, which is Qt's preferred way for file operations,
            # especially if dealing with Qt resource system in the future.
            qfile = QFile(file_path)
            if qfile.open(QFile.OpenModeFlag.ReadOnly | QFile.OpenModeFlag.Text):
                stream = QTextStream(qfile)
                content = stream.readAll()
                qfile.close()
                logger.info(f"Successfully loaded '{os.path.basename(file_path)}' ({len(content)} chars)")
                return content
            else:
                logger.error(f"Could not open stylesheet file: {file_path} (Error: {qfile.errorString()})")
                return ""
        except Exception as e:
            logger.error(f"Exception loading stylesheet {file_path}: {e}", exc_info=True)
            return ""

    @classmethod
    def get_light_theme_stylesheet(cls) -> str:
        """
        Loads and caches the light theme stylesheet (e.g., "light_theme.qss").

        Returns:
            The content of the light theme stylesheet, or an empty string on failure.
        """
        if cls._light_theme_cache is None:  # Load only if not already cached
            file_path = cls._resolve_path('light_theme.qss') # Assuming light_theme.qss
            cls._light_theme_cache = cls._read_stylesheet(file_path)
        return cls._light_theme_cache or ""  # Return empty string if loading failed

    @classmethod
    def get_dark_theme_stylesheet(cls) -> str:
        """
        Loads and caches the dark theme stylesheet (e.g., "dark_theme.qss").

        Returns:
            The content of the dark theme stylesheet, or an empty string on failure.
        """
        if cls._dark_theme_cache is None:  # Load only if not already cached
            file_path = cls._resolve_path('dark_theme.qss') # Assuming dark_theme.qss
            cls._dark_theme_cache = cls._read_stylesheet(file_path)
        return cls._dark_theme_cache or ""  # Return empty string if loading failed

    @classmethod
    def apply_application_style(cls, app: QApplication, use_dark_theme: bool = False):
        """
        Loads the appropriate theme stylesheet (light or dark) and applies it
        to the QApplication instance.

        Args:
            app: The QApplication instance.
            use_dark_theme: If True, the dark theme is loaded; otherwise, the light theme is loaded.
        """
        final_style: str = ""
        theme_applied: str = ""

        if use_dark_theme:
            logger.debug("Dark theme requested. Attempting to load dark_theme.qss.")
            final_style = cls.get_dark_theme_stylesheet() # Uses cache
            theme_applied = "Dark"
            if not final_style:
                logger.warning("Dark theme stylesheet (dark_theme.qss) failed to load or was empty. "
                               "Falling back to light theme.")
                # Fallback to light theme if dark theme is unavailable
                final_style = cls.get_light_theme_stylesheet() # Uses cache
                theme_applied = "Light (fallback from dark)"
        else:
            logger.debug("Light theme requested. Attempting to load light_theme.qss.")
            final_style = cls.get_light_theme_stylesheet() # Uses cache
            theme_applied = "Light"

        # Apply the final stylesheet to the application
        if final_style:
            # Add the stylesheet directory to Qt's search paths.
            # This helps Qt resolve relative paths within `url()` properties in QSS files
            # (e.g., for icons: url(icons/my_icon.svg) if 'icons' is a subdir of 'stylesheets').
            # If you use absolute Qt resource paths like `url(:/icons/my_icon.svg)`,
            # this line might be less critical but is good practice.
            QDir.addSearchPath('qss_resources', cls._style_dir) # Use a unique prefix

            app.setStyleSheet(final_style)
            logger.info(f"Applied application style ('{theme_applied}' theme). Total length: {len(final_style)} chars.")
        else:
            logger.error(f"No application style applied. The '{theme_applied}' theme stylesheet "
                         "failed to load or was empty.")

    @classmethod
    def clear_cache(cls):
        """
        Clears the cached stylesheet content. Useful for development if you want to
        force a reload of QSS files without restarting the application (if you
        implement a dynamic reload mechanism).
        """
        logger.debug("Clearing stylesheet cache.")
        cls._light_theme_cache = None
        cls._dark_theme_cache = None

