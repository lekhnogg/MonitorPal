import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
    QPushButton, QComboBox, QTextEdit, QLabel, QGroupBox
)
from PySide6.QtCore import Qt

# Import the DI container to access the services
from src.domain.services.i_platform_detection_service import IPlatformDetectionService
from src.domain.services.i_window_manager_service import IWindowManager
from src.domain.services.i_logger_service import ILoggerService

# Import the app module containing the DI container
from src.application import app


class PlatformDetectionTestApp(QMainWindow):
    def __init__(self):
        super().__init__()

        # Get services from DI container
        self.container = app.get_container()
        self.platform_service = self.container.resolve(IPlatformDetectionService)
        self.window_manager = self.container.resolve(IWindowManager)
        self.logger = self.container.resolve(ILoggerService)

        self.logger.info("Platform Detection Test App started")

        # Setup UI
        self.setWindowTitle("Platform Detection Test")
        self.setup_ui()

    def setup_ui(self):
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Create main layout
        main_layout = QVBoxLayout(central_widget)

        # Platform selection group
        platform_group = QGroupBox("Platform Selection")
        platform_layout = QVBoxLayout(platform_group)

        # Platform dropdown
        dropdown_layout = QHBoxLayout()
        platform_label = QLabel("Platform:")
        self.platform_combo = QComboBox()

        # Get supported platforms from the service
        platforms_result = self.platform_service.get_supported_platforms()
        if platforms_result.is_success:
            platforms = platforms_result.value
            # Add platforms to combo box
            for platform_name in platforms.keys():
                self.platform_combo.addItem(platform_name)
        else:
            self.logger.error(f"Failed to get supported platforms: {platforms_result.error}")

        dropdown_layout.addWidget(platform_label)
        dropdown_layout.addWidget(self.platform_combo)
        dropdown_layout.addStretch()
        platform_layout.addLayout(dropdown_layout)

        # Action buttons
        button_layout = QHBoxLayout()

        self.detect_button = QPushButton("Detect Platform")
        self.detect_button.clicked.connect(self.detect_platform)
        self.detect_button.setStyleSheet("padding: 8px;")

        self.activate_button = QPushButton("Detect & Activate")
        self.activate_button.clicked.connect(self.detect_and_activate)
        self.activate_button.setStyleSheet("padding: 8px;")

        button_layout.addWidget(self.detect_button)
        button_layout.addWidget(self.activate_button)
        platform_layout.addLayout(button_layout)

        main_layout.addWidget(platform_group)

        # Results group
        results_group = QGroupBox("Detection Results")
        results_layout = QVBoxLayout(results_group)

        # Results display
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        results_layout.addWidget(self.results_text)

        main_layout.addWidget(results_group)

        # Initial message
        self.results_text.append("Select a platform and click one of the detection buttons")

        # Set window size
        self.resize(600, 500)

    def detect_platform(self):
        """Detect the platform without bringing it to foreground"""
        platform_name = self.platform_combo.currentText()
        self.results_text.clear()
        self.results_text.append(f"Detecting platform: {platform_name}...\n")

        # First check if platform is running
        running_result = self.platform_service.is_platform_running(platform_name)

        if running_result.is_failure:
            self.results_text.append(f"❌ Error checking if platform is running: {running_result.error}")
            return

        is_running = running_result.value
        if not is_running:
            self.results_text.append(f"❌ {platform_name} is not running")
            return

        self.results_text.append(f"✅ {platform_name} is running")

        # Try to detect the window without activating it
        window_result = self.platform_service.detect_platform_window(platform_name)

        if window_result.is_failure:
            self.results_text.append(f"❌ Failed to detect window: {window_result.error}")
            return

        window_info = window_result.value
        self.results_text.append(f"\nWindow detected:")
        self.results_text.append(f"  Title: {window_info.get('title', 'N/A')}")
        self.results_text.append(f"  Handle: {window_info.get('hwnd', 'N/A')}")
        self.results_text.append(f"  Process ID: {window_info.get('pid', 'N/A')}")

        # Check if window is currently active
        active_result = self.platform_service.is_platform_window_active(window_info)
        if active_result.is_success:
            is_active = active_result.value
            self.results_text.append(f"\nWindow is currently {'active' if is_active else 'inactive'}")

    def detect_and_activate(self):
        """Detect the platform and bring it to foreground"""
        platform_name = self.platform_combo.currentText()
        self.results_text.clear()
        self.results_text.append(f"Detecting and activating platform: {platform_name}...\n")

        # First check if platform is running
        running_result = self.platform_service.is_platform_running(platform_name)

        if running_result.is_failure:
            self.results_text.append(f"❌ Error checking if platform is running: {running_result.error}")
            return

        is_running = running_result.value
        if not is_running:
            self.results_text.append(f"❌ {platform_name} is not running")
            return

        self.results_text.append(f"✅ {platform_name} is running")

        # Try to activate platform windows
        self.results_text.append(f"\nAttempting to bring {platform_name} to foreground...")
        activate_result = self.platform_service.activate_platform_windows(platform_name)

        if activate_result.is_success:
            self.results_text.append(f"✅ Successfully activated {platform_name} windows")

            # Try to detect window again to get updated info
            window_result = self.platform_service.detect_platform_window(platform_name)
            if window_result.is_success:
                window_info = window_result.value
                self.results_text.append(f"\nActive window info:")
                self.results_text.append(f"  Title: {window_info.get('title', 'N/A')}")
                self.results_text.append(f"  Handle: {window_info.get('hwnd', 'N/A')}")
        else:
            self.results_text.append(f"❌ Failed to activate windows: {activate_result.error}")


if __name__ == "__main__":
    # Initialize Qt application
    qt_app = QApplication(sys.argv)

    # Create and show the main window
    main_window = PlatformDetectionTestApp()
    main_window.show()

    # Run the application
    sys.exit(qt_app.exec())