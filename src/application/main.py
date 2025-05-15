# -*- coding: utf-8 -*-
# --- src/application/main.py ---

import sys
import os
import logging
from typing import Optional

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
    # 1. Configure basic logging (for early startup issues)
    logging.basicConfig(
        level=logging.INFO,  # Or logging.DEBUG for more verbose startup
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 2. Create the Qt Application instance
    app = QApplication(sys.argv)
    app.setApplicationName("MonitorPal")
    app.setOrganizationName("GlebDev")
    app.setApplicationVersion("1.0.0")  # Good to set this
    app.setStyle("Fusion")  # Setting a consistent style

    # 3. Initialize Dependency Injection Container and Core Services
    logger: Optional[ILoggerService] = None  # Initialize for broader scope if needed
    try:
        # Ensure 'src' is in PYTHONPATH if running main.py directly
        # (This is good practice, though often handled by IDEs or project structure)
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        container = get_container()
        logger = container.resolve(ILoggerService)  # Now use the injected logger
        config_repo = container.resolve(IConfigRepository)

        logger.info("Starting MonitorPal")
        logger.info("DI Container initialized successfully")
    except Exception as e:
        critical_msg = f"CRITICAL ERROR: Failed to initialize application dependencies: {e}"
        module_logger.critical(critical_msg, exc_info=True)  # Use module_logger if container logger failed
        QMessageBox.critical(None, "Application Startup Error",
                             f"Failed to initialize essential application components:\n{e}")
        sys.exit(1)

    # 4. Create the Main Window FIRST
    # MainView's __init__ calls _instantiate_view_models(), so VMs will be available after this.
    try:
        main_window = MainView(container=container)  # Pass the DI container
        logger.info("MainView instance created successfully")
    except Exception as e:
        logger.critical(f"CRITICAL ERROR: Failed to create MainView: {e}", exc_info=True)
        QMessageBox.critical(None, "Application Component Error",
                             f"Failed to create application interface:\n{e}")
        sys.exit(1)

    # --- 4.5. CONNECT Inter-ViewModel Signals ---
    # This is the ideal place, after MainView and its internal ViewModels are created.
    if main_window.main_view_model and main_window.dashboard_vm:
        logger.info(
            "Connecting DashboardViewModel.monitoring_session_activity_changed to MainViewModel.on_monitoring_activity_changed.")
        try:
            main_window.dashboard_vm.monitoring_session_activity_changed.connect(
                main_window.main_view_model.on_monitoring_activity_changed
            )
            logger.debug("Successfully connected inter-ViewModel signal for monitoring activity.")
        except AttributeError as e:  # Specific check for missing signal/slot
            logger.error(
                f"Failed to connect inter-ViewModel signal (AttributeError): {e}. Check signal/slot names and VM attributes.",
                exc_info=True)
        except Exception as e:  # Catch other potential connection errors
            logger.error(f"An unexpected error occurred during inter-ViewModel signal connection: {e}", exc_info=True)
    else:
        # This would be a critical failure in MainView's initialization.
        logger.critical(
            "CRITICAL: MainView's ViewModels (main_view_model or dashboard_vm) are not available post-init. Cannot connect inter-ViewModel signals. Application state may be inconsistent.")
        # Optionally, show a critical error to the user here as well, as this implies a deeper issue.
        QMessageBox.critical(main_window, "ViewModel Initialization Error",
                             "Essential application components (ViewModels within MainView) failed to initialize. Application may not function correctly.")

    # 5. THEN apply theme (CORRECT ORDER - window first, then property, then styles)
    try:
        current_theme_str = config_repo.get_global_setting("theme", "dark")
        use_dark_theme = current_theme_str == "dark"
        logger.info(f"Applying theme: {current_theme_str}")

        main_window.setProperty("darkTheme", use_dark_theme)
        StyleManager.apply_application_style(app, use_dark_theme=use_dark_theme)

        main_window.style().unpolish(main_window)
        main_window.style().polish(main_window)
        main_window.update()  # Ensure visual update
        QApplication.processEvents()  # Process events to help rendering
        logger.info("Theme applied and UI refreshed successfully.")
    except Exception as e:
        logger.error(f"Error applying theme: {e}. Continuing with default system theme or last known style.",
                     exc_info=True)
        # Optionally, inform the user if theme application fails significantly.

    # 6. Load Qt Resources
    try:
        import src.presentation.views.resources_rc  # Your resources file
        logger.debug("Qt resources (resources_rc.py) loaded successfully.")
    except ImportError:
        logger.warning("Could not load Qt resources (resources_rc.py). Icons and other resources may be missing.")
    except Exception as e_res:  # Catch other potential errors during resource loading
        logger.error(f"Error loading Qt resources: {e_res}", exc_info=True)

    # 7. Show the Main Window and Start Event Loop
    try:
        logger.debug("Attempting to show MainView.")
        main_window.show()
        logger.info("Application UI displayed successfully. Starting event loop.")

        exit_code = app.exec()
        logger.info(f"Application exiting with code: {exit_code}")
        sys.exit(exit_code)
    except Exception as e:
        logger.critical(f"CRITICAL ERROR: Application execution failed: {e}", exc_info=True)
        QMessageBox.critical(None, "Application Runtime Error",
                             f"A critical error occurred and the application must close:\n{e}")
        sys.exit(1)


# Standard Python entry point guard
if __name__ == "__main__":
    run_application()