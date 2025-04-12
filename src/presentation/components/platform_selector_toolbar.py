# src/presentation/components/platform_selector_toolbar.py
from typing import List, Optional
from PySide6.QtWidgets import QToolBar, QLabel, QComboBox, QWidget, QSizePolicy
from PySide6.QtCore import Signal, Slot

from src.domain.services.i_platform_selection_service import IPlatformSelectionService


class PlatformSelectorToolbar(QToolBar):
    """
    Toolbar with global platform selection dropdown.
    Manages its own state based on the PlatformSelectionService
    and emits platform_changed ONLY on user interaction.
    """

    platform_changed = Signal(str) # Emitted when the user selects a new platform

    def __init__(self, platform_service: IPlatformSelectionService, parent=None):
        """Initialize the platform selector toolbar."""
        super().__init__("Platform Selection", parent)
        self.platform_service = platform_service
        self.setMovable(False)
        self.setFloatable(False)

        # Add summary labels BEFORE the spacer
        self.addWidget(QLabel(" Region: "))
        self.region_label = QLabel("N/A")
        self.region_label.setStyleSheet("font-weight: bold;")
        self.addWidget(self.region_label)

        self.addSeparator()  # Visual separation

        self.addWidget(QLabel(" Threshold: "))
        self.threshold_label = QLabel("N/A")
        self.threshold_label.setStyleSheet("font-weight: bold;")
        self.addWidget(self.threshold_label)

        self.addSeparator()

        self.addWidget(QLabel(" Duration: "))
        self.duration_label = QLabel("N/A")
        self.duration_label.setStyleSheet("font-weight: bold;")
        self.addWidget(self.duration_label)

        self.addWidget(QLabel(" Patterns: "))
        self.patterns_label = QLabel("N/A")
        self.patterns_label.setStyleSheet("font-weight: bold;")
        # Optional: Add tooltip placeholder
        self.patterns_label.setToolTip("Detected number format patterns (Default/Custom/etc.)")
        self.addWidget(self.patterns_label)

        # Add spacer to push dropdown to the right
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.addWidget(spacer)

        # Add label
        self.addWidget(QLabel("Platform: "))

        # Create platform dropdown
        self.platform_combo = QComboBox()
        self.platform_combo.setMinimumWidth(150)

        # --- Initialization Logic ---
        # Block signals during initial population
        self.platform_combo.blockSignals(True)
        try:
            platforms = self.platform_service.get_available_platforms()
            current = self.platform_service.get_current_platform()

            self.platform_combo.addItems(platforms)

            if current and current in platforms:
                self.platform_combo.setCurrentText(current)
            elif platforms:
                 self.platform_combo.setCurrentIndex(0) # Default to first

            # Log initial state for debugging if needed
            # print(f"Toolbar Initialized. Platforms: {platforms}, Current: {self.platform_combo.currentText()}")

        finally:
            # --- Always unblock signals after setup ---
            self.platform_combo.blockSignals(False)

        # --- Connect signal AFTER initial setup ---
        # Connect to a slot specifically for user actions
        self.platform_combo.currentTextChanged.connect(self._handle_user_selection)

        # Register as listener for platform changes from elsewhere
        # This allows the toolbar to UPDATE its display if the platform is changed programmatically
        self.platform_service.register_platform_change_listener(self._on_external_platform_change)

        self.addWidget(self.platform_combo)

    # --- Slot for USER changes ONLY ---
    @Slot(str)
    def _handle_user_selection(self, platform: str) -> None:
        """Handles user selection in the dropdown."""
        if not platform:
            return # Ignore empty selection if clearing

        # Prevent infinite loops if service calls back immediately (shouldn't happen with good design)
        if self.platform_service.get_current_platform() == platform:
             return

        # 1. Update the service (which handles saving config)
        # Use result handling if set_current_platform returns Result
        result = self.platform_service.set_current_platform(platform)

        # 2. If service update was successful, THEN emit signal for main app
        if result.is_success: # Assuming set_current_platform returns Result
            self.platform_changed.emit(platform)
        else:
            # Optionally log error or show message to user via parent() access if needed
            print(f"ERROR: Failed to set platform via service: {result.error}")
            # Consider reverting combo box selection?
            self.platform_combo.blockSignals(True)
            self.platform_combo.setCurrentText(self.platform_service.get_current_platform()) # Revert to actual current
            self.platform_combo.blockSignals(False)

    @Slot(str)
    def _on_external_platform_change(self, platform: str) -> None:
        """Handles platform change notifications from the service."""
        # Check if the dropdown needs updating
        if platform and self.platform_combo.currentText() != platform:
            # Update dropdown UI WITHOUT triggering _handle_user_selection
            # print(f"Toolbar reacting to external change: {platform}")
            self.platform_combo.blockSignals(True)
            self.platform_combo.setCurrentText(platform)
            self.platform_combo.blockSignals(False)

    def update_platforms(self, platforms: List[str], current_platform: Optional[str] = None):
        """Updates the list of available platforms and sets the current selection."""
        # Determine the desired selection AFTER update
        # If current_platform is provided, use it. Otherwise, keep the current one if it still exists.
        target_platform = current_platform
        if target_platform is None:
            current_in_combo = self.platform_combo.currentText()
            if current_in_combo in platforms:
                target_platform = current_in_combo # Keep existing if valid

        # Block signals during update
        self.platform_combo.blockSignals(True)
        try:
            self.platform_combo.clear()
            self.platform_combo.addItems(platforms)

            if target_platform and target_platform in platforms:
                self.platform_combo.setCurrentText(target_platform)
            elif platforms:
                self.platform_combo.setCurrentIndex(0) # Default to first if target invalid
                # If defaulting changed the platform, the service needs to know
                # This case is tricky - should updating the *list* change the *selection*?
                # Maybe better to just set it to the target if possible, else leave it blank/first item
                # without forcing a selection change? Let's stick to setting the target for now.

        finally:
            self.platform_combo.blockSignals(False)

    def update_summary(self, region_status: Optional[str], threshold: Optional[float], duration: Optional[int]):
        """Updates the summary labels in the toolbar (Region, Threshold, Duration)."""
        # Region Status (now accepts string like "Defined", "Not Defined", "(x,y,w,h)", "Error")
        self.region_label.setText(region_status if region_status else "N/A")

        # Threshold (logic remains same)
        if threshold is not None:
            display_threshold = threshold if threshold <= 0 else -threshold
            self.threshold_label.setText(f"${display_threshold:,.2f}")
        else:
            self.threshold_label.setText("N/A")

        # Duration (logic remains same)
        if duration is not None:
            self.duration_label.setText(f"{duration} min")
        else:
             self.duration_label.setText("N/A")

    def update_pattern_summary(self, description: str):
        """Updates the pattern summary label."""
        self.patterns_label.setText(description if description else "N/A")

    def get_current_selection(self) -> str:
         """Returns the platform currently selected in the combo box."""
         return self.platform_combo.currentText()