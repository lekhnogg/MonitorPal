# -*- coding: utf-8 -*-
# --- src/application/main.py ---

import sys
import os
import logging

# --- Qt Imports ---
from PySide6.QtWidgets import QApplication, QMessageBox

# --- Application Imports ---
from src.application.app import get_container
from src.presentation.views.main_view import MainView
from src.domain.services.i_logger_service import ILoggerService
from src.presentation.styles.style_manager import StyleManager
from src.domain.services.i_config_repository_service import IConfigRepository

# --- Global Logger for this module ---
module_logger = logging.getLogger(__name__)


def run_application():
    """
    Main entry point for the MonitorPal application.
    """
    # 1. Configure basic logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 2. Create the Qt Application instance
    app = QApplication(sys.argv)
    app.setApplicationName("MonitorPal")
    app.setOrganizationName("GlebDev")
    app.setApplicationVersion("1.0.0")
    app.setStyle("Fusion")

    # 3. Initialize Dependency Injection Container and Core Services
    try:
        # Ensure 'src' is in PYTHONPATH if running main.py directly
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        container = get_container()
        logger = container.resolve(ILoggerService)
        config_repo = container.resolve(IConfigRepository)

        logger.info("Starting MonitorPal")
        logger.info("DI Container initialized successfully")
    except Exception as e:
        critical_msg = f"CRITICAL ERROR: Failed to initialize application dependencies: {e}"
        module_logger.critical(critical_msg, exc_info=True)
        QMessageBox.critical(None, "Application Startup Error",
                             f"Failed to initialize essential application components:\n{e}")
        sys.exit(1)

    # 4. Create the Main Window FIRST, before applying theme
    try:
        main_window = MainView(container=container)
        logger.info("MainView instance created successfully")
    except Exception as e:
        logger.critical(f"CRITICAL ERROR: Failed to create MainView: {e}", exc_info=True)
        QMessageBox.critical(None, "Application Component Error",
                             f"Failed to create application interface:\n{e}")
        sys.exit(1)

    # 5. THEN apply theme (CORRECT ORDER - window first, then property, then styles)
    try:
        # Load theme setting
        current_theme_str = config_repo.get_global_setting("theme", "dark")
        use_dark_theme = current_theme_str == "dark"
        logger.info(f"Using theme: {current_theme_str}")

        # Set property on MainView BEFORE applying stylesheet
        main_window.setProperty("darkTheme", use_dark_theme)

        # Apply stylesheet AFTER setting property
        StyleManager.apply_application_style(app, use_dark_theme=use_dark_theme)
        logger.info("Theme applied successfully")

        # Force style update cycle
        main_window.style().unpolish(main_window)
        main_window.style().polish(main_window)
        main_window.update()
        QApplication.processEvents()
    except Exception as e:
        logger.error(f"Error applying theme: {e}. Continuing with default theme.", exc_info=True)

    # 6. Load Qt Resources
    try:
        import src.presentation.views.resources_rc
        logger.debug("Qt resources loaded successfully")
    except ImportError:
        logger.warning("Could not load Qt resources. Icons may be missing.")

    # 7. Show the Main Window and Start Event Loop
    try:
        main_window.show()
        logger.info("Application UI displayed successfully")

        # Start the Qt Event Loop
        exit_code = app.exec()
        logger.info(f"Application exiting with code: {exit_code}")
        sys.exit(exit_code)
    except Exception as e:
        logger.critical(f"CRITICAL ERROR: Application startup failed: {e}", exc_info=True)
        QMessageBox.critical(None, "Application Error",
                             f"Application failed to start:\n{e}")
        sys.exit(1)


# Standard Python entry point guard
if __name__ == "__main__":
    run_application()