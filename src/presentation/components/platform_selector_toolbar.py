from typing import List

from PySide6.QtWidgets import QToolBar, QLabel, QComboBox, QWidget, QSizePolicy
from PySide6.QtCore import Signal

from src.domain.services.i_platform_selection_service import IPlatformSelectionService


class PlatformSelectorToolbar(QToolBar):
    """Toolbar with global platform selection dropdown."""

    platform_changed = Signal(str)

    def __init__(self, platform_service: IPlatformSelectionService, parent=None):
        """Initialize the platform selector toolbar."""
        super().__init__("Platform Selection", parent)
        self.platform_service = platform_service
        self.setMovable(False)
        self.setFloatable(False)

        # Add spacer to push dropdown to the right
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.addWidget(spacer)

        # Add label
        self.addWidget(QLabel("Platform: "))

        # Create platform dropdown
        self.platform_combo = QComboBox()
        self.platform_combo.setMinimumWidth(150)

        # Populate with available platforms
        platforms = self.platform_service.get_available_platforms()
        self.platform_combo.addItems(platforms)

        # Set current platform
        current = self.platform_service.get_current_platform()
        if current and current in platforms:
            self.platform_combo.setCurrentText(current)

        # Connect signal to service
        self.platform_combo.currentTextChanged.connect(self._on_platform_changed)

        # Register as listener for platform changes from elsewhere
        self.platform_service.register_platform_change_listener(self._on_external_platform_change)

        self.addWidget(self.platform_combo)

    def _on_platform_changed(self, platform: str) -> None:
        """Handle platform change in the dropdown."""
        if platform:
            # Update service
            self.platform_service.set_current_platform(platform)
            # Emit signal for any local components that need to know
            self.platform_changed.emit(platform)

    def _on_external_platform_change(self, platform: str) -> None:
        """Handle platform change from external sources."""
        if platform and self.platform_combo.currentText() != platform:
            # Update dropdown without triggering change events
            self.platform_combo.blockSignals(True)
            self.platform_combo.setCurrentText(platform)
            self.platform_combo.blockSignals(False)

    def update_platforms(self, platforms: List[str], current_platform: str = None):
        """Update the list of available platforms."""
        # Save current selection
        current = self.platform_combo.currentText() if current_platform is None else current_platform

        # Update items
        self.platform_combo.clear()
        self.platform_combo.addItems(platforms)

        # Restore selection if possible
        if current and current in platforms:
            self.platform_combo.setCurrentText(current)
        elif platforms:
            self.platform_combo.setCurrentIndex(0)