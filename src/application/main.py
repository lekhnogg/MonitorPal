# src/application/main.py

import sys
import os

# --- Qt Imports ---
from PySide6.QtWidgets import QApplication

# --- Application Imports ---
# Import the function that sets up DI and the getter
# Ensure app.py exists and is correct relative to this file
from src.application.app import get_container
# Import the main window class (View) - Ensure this file will exist
from src.presentation.views.main_view import MainView
# Import the Logger service interface (optional, for early logging)
from src.domain.services.i_logger_service import ILoggerService
from src.presentation.styles.style_manager import StyleManager


def run_application():
    # 1. Create the Qt Application instance
    app = QApplication(sys.argv)

    # Optional: Set application metadata
    app.setApplicationName("MonitorPal")
    app.setOrganizationName("GlebDev")
    app.setApplicationVersion("1.0.0")

    # Optional: Set a consistent visual style
    app.setStyle("Fusion")

    # ADD THIS LINE to apply your global styles:
    StyleManager.apply_application_style(app)

    # 2. Initialize Dependency Injection and Logging
    try:
        # Make sure src is in the Python path if running main.py directly
        src_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if src_path not in sys.path:
            sys.path.insert(0, src_path)

        container = get_container()
        logger = container.resolve(ILoggerService)
        logger.info("----------------------------------------------------")
        logger.info(f"Starting MonitorPal v{app.applicationVersion()}")
        logger.info("----------------------------------------------------")
        logger.info("DI Container initialized.")
    except Exception as e:
        # Basic fallback logging if DI/Logger setup fails critically
        print(f"CRITICAL ERROR: Failed to initialize application dependencies: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        # Show a basic message box if possible (QApplication exists)
        try:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(None, "Application Error", f"Failed to initialize dependencies:\n{e}\n\nPlease check logs or reinstall.")
        except Exception as qe:
             print(f"ERROR: Could not even show critical error message box: {qe}", file=sys.stderr)
        sys.exit(1) # Exit if critical setup fails

    try:
        # Pass the container so MainView can resolve services/VMs
        main_window = MainView(container=container)
        logger.info("MainView created.")
    except ImportError as e:
        # Specific check for missing View/ViewModel files during development
        logger.error(f"CRITICAL ERROR: Failed to import required View/ViewModel for MainView: {e}", exc_info=True)
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(None, "Application Error", f"Missing application component:\n{e}\n\nPlease ensure all View/ViewModel files exist.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"CRITICAL ERROR: Failed to create MainView: {e}", exc_info=True)
        try:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(None, "Application Error", f"Failed to create main window:\n{e}\n\nPlease check logs.")
        except Exception as qe:
            logger.error(f"Could not show main window creation error message box: {qe}")
        sys.exit(1)

    # 4. Show the Main Window
    try:
        import src.presentation.views.resources_rc
        print("DEBUG: Successfully imported compiled resources (resources_rc.py)")  # Optional debug print
    except ImportError:
        print("ERROR: Could not import compiled resources (resources_rc.py). Did you compile the .qrc file?",
              file=sys.stderr)
        # Decide if this is fatal - usually is if icons are required.
        # sys.exit(1)
    # --- *** END IMPORT *** ---

    try:
        main_window.show()
        logger.info("MainView shown.")
    except Exception as e:
        logger.error(f"CRITICAL ERROR: Failed to show MainView: {e}", exc_info=True)
        sys.exit(1)

    # 5. Start the Qt Event Loop
    #    This call blocks until the application is quit (e.g., window closed).
    logger.info("Starting Qt event loop...")
    exit_code = app.exec()

    logger.info(f"Qt event loop finished with exit code: {exit_code}")

    # 6. Exit the application
    sys.exit(exit_code)

# --- Standard Python entry point guard ---
if __name__ == "__main__":
    run_application()