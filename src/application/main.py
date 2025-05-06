# src/application/main.py

import sys
import os
import logging # For early logging if DI fails

# --- Qt Imports ---
from PySide6.QtWidgets import QApplication, QMessageBox

# --- Application Imports ---
from src.application.app import get_container
from src.presentation.views.main_view import MainView
from src.domain.services.i_logger_service import ILoggerService
from src.presentation.styles.style_manager import StyleManager
from src.domain.services.i_config_repository_service import IConfigRepository

# --- Global Logger for this module (used if DI logger isn't available yet) ---
module_logger = logging.getLogger(__name__)

def run_application():
    """
    Main entry point for the MonitorPal application.
    Initializes Qt, DI container, logging, applies theme, creates and shows the main window.
    """
    # 0. Configure basic logging early for startup issues
    # This will be overridden/supplemented by the DI logger once initialized.
    logging.basicConfig(
        level=logging.DEBUG, # Set to INFO for production
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 1. Create the Qt Application instance
    app = QApplication(sys.argv)

    # Optional: Set application metadata
    app.setApplicationName("MonitorPal")
    app.setOrganizationName("GlebDev") # Replace if necessary
    app.setApplicationVersion("1.0.0") # Update as your app versions

    # Optional: Set a consistent visual style (Fusion is good for cross-platform)
    app.setStyle("Fusion")

    # 2. Initialize Dependency Injection Container and Core Services
    container = None
    logger = None
    config_repo = None

    try:
        # Ensure 'src' is in PYTHONPATH if running main.py directly from project root
        # or if packaged in a way that 'src' isn't automatically discoverable.
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
            module_logger.debug(f"Added project root to sys.path: {project_root}")

        container = get_container()
        logger = container.resolve(ILoggerService) # Get the DI-configured logger
        config_repo = container.resolve(IConfigRepository)

        logger.info("----------------------------------------------------")
        logger.info(f"Starting MonitorPal v{app.applicationVersion()}")
        logger.info("----------------------------------------------------")
        logger.info("DI Container initialized successfully.")

    except Exception as e:
        # Fallback logging if DI/Logger setup fails critically
        # Using module_logger or print if DI logger failed.
        critical_msg = f"CRITICAL ERROR: Failed to initialize application dependencies: {e}"
        module_logger.critical(critical_msg, exc_info=True)
        print(critical_msg, file=sys.stderr) # Ensure it's visible
        try:
            QMessageBox.critical(
                None,
                "Application Startup Error",
                f"Failed to initialize essential application components:\n{e}\n\n"
                "The application cannot continue. Please check logs or try reinstalling."
            )
        except Exception as qe:
            module_logger.error(f"Could not display critical error QMessageBox: {qe}", exc_info=True)
        sys.exit(1)

    # 3. Apply Visual Theme Based on Configuration
    try:
        # Default to "dark" if the setting is missing or invalid
        current_theme_str = config_repo.get_global_setting("theme", "dark")
        use_dark_theme = current_theme_str == "dark"
        logger.info(f"Applying theme from configuration: '{current_theme_str}' (use_dark_theme: {use_dark_theme})")
        StyleManager.apply_application_style(app, use_dark_theme=use_dark_theme)
    except Exception as e:
        logger.error(f"Error applying theme from config at startup: {e}. Defaulting to dark theme.", exc_info=True)
        StyleManager.apply_application_style(app, use_dark_theme=True) # Fallback

    # 4. Create the Main Window
    main_window = None
    try:
        # MainView constructor expects the DI container
        main_window = MainView(container=container)
        logger.info("MainView instance created.")
    except ImportError as e:
        logger.critical(f"CRITICAL ERROR: Failed to import a required View/ViewModel for MainView: {e}", exc_info=True)
        QMessageBox.critical(None, "Application Component Error", f"A required application component is missing:\n{e}\n\nPlease ensure all files are present.")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"CRITICAL ERROR: Failed to create MainView: {e}", exc_info=True)
        QMessageBox.critical(None, "Application Creation Error", f"Failed to create the main application window:\n{e}\n\nPlease check logs.")
        sys.exit(1)

    # 5. Load Qt Resources (e.g., for icons)
    try:
        # This import executes the code in resources_rc.py, registering resources.
        import src.presentation.views.resources_rc
        logger.debug("Successfully imported compiled Qt resources (resources_rc.py).")
    except ImportError:
        logger.error(
            "ERROR: Could not import compiled Qt resources (resources_rc.py). "
            "Icons and other resources might be missing. "
            "Ensure you have compiled your .qrc file (e.g., resources.qrc) to resources_rc.py."
        )
        # Depending on severity, you might want to show a QMessageBox and exit.
        # QMessageBox.warning(None, "Resource Error", "Application resources (icons, etc.) could not be loaded.")


    # 6. Show the Main Window
    try:
        main_window.show()
        logger.info("MainView shown to the user.")
    except Exception as e:
        logger.critical(f"CRITICAL ERROR: Failed to show MainView: {e}", exc_info=True)
        QMessageBox.critical(None, "Application Display Error", f"Failed to display the main application window:\n{e}\n\nPlease check logs.")
        sys.exit(1)

    # 7. Start the Qt Event Loop
    logger.info("Starting Qt event loop...")
    exit_code = app.exec()

    logger.info(f"Qt event loop finished. Application exiting with code: {exit_code}")

    # 8. Exit the application
    sys.exit(exit_code)

# Standard Python entry point guard
if __name__ == "__main__":
    run_application()