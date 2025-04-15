# src/application/main.py

import sys
import os
import logging # Optional: For configuring root logger if needed beyond service

# --- Qt Imports ---
from PySide6.QtWidgets import QApplication

# --- Application Imports ---
# Import the function that sets up DI and the getter
# Ensure app.py exists and is correct relative to this file
from src.application.app import initialize_app, get_container
# Import the main window class (View) - Ensure this file will exist
from src.presentation.views.main_view import MainView
# Import the Logger service interface (optional, for early logging)
from src.domain.services.i_logger_service import ILoggerService

def run_application():
    """
    Initializes and runs the MonitorPal Qt application.
    """
    # 1. Create the Qt Application instance
    #    This needs to be done *before* any other Qt components are created.
    app = QApplication(sys.argv)

    # Optional: Set application metadata
    app.setApplicationName("MonitorPal")
    app.setOrganizationName("GlebDev") # Or your name/organization
    app.setApplicationVersion("1.0.0") # Update as needed

    # Optional: Set a consistent visual style
    app.setStyle("Fusion")

    # 2. Initialize Dependency Injection and Logging
    #    get_container() will call initialize_app() if it hasn't run yet.
    try:
        # Make sure src is in the Python path if running main.py directly
        # This might be needed depending on your execution environment
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

    # 3. Create the Main Window (View)
    #    The MainView is responsible for creating its layout (including tabs)
    #    and obtaining/connecting its necessary ViewModels.
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