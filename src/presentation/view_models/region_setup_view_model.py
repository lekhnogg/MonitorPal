# src/presentation/view_models/region_setup_view_model.py

import os
from typing import List, Optional, Dict, Any, Tuple

# --- Qt Imports ---
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QPixmap # For holding previews

from src.domain.common.errors import ErrorCategory
# --- Application Imports ---
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_region_service import IRegionService
from src.domain.services.i_platform_selection_service import IPlatformSelectionService
from src.domain.services.i_flash_service import IFlashService
from src.domain.services.i_ui_service import IUIService # For triggering region selection
from src.domain.services.i_screenshot_service import IScreenshotService # For converting preview data
from src.domain.models.region_model import Region
from src.domain.common.result import Result


class RegionSetupViewModel(QObject):
    """
    ViewModel for the Region Setup tab.

    Manages the definition and display of P&L Monitoring and Flatten regions
    for the selected platform.
    """

    # --- Signals for View updates ---

    # P&L Monitoring Region Section
    monitor_region_status_changed = Signal(str) # "Defined", "Not Defined", "Error"
    monitor_region_coords_text_changed = Signal(str) # "(x, y, w, h)" or "N/A"
    monitor_region_preview_changed = Signal(QPixmap) # Send QPixmap for display
    can_delete_monitor_region_changed = Signal(bool)
    can_flash_monitor_region_changed = Signal(bool)
    monitor_region_saved = Signal(str)  # Emits the platform name for which it was saved

    # Flatten Position Regions Section
    # Signal carries List[Dict], where each dict has keys like 'name', 'coords_text', 'preview_pixmap'
    flatten_regions_list_updated = Signal(list)
    can_add_flatten_region_changed = Signal(bool)

    # General Status/Error Message
    status_message_changed = Signal(str, str) # message, level ("INFO", "ERROR", etc.)

    def __init__(self,
                 logger: ILoggerService,
                 region_service: IRegionService,
                 platform_selection_service: IPlatformSelectionService,
                 flash_service: IFlashService,
                 ui_service: IUIService,
                 screenshot_service: IScreenshotService, # Needed for preview conversion
                 parent: Optional[QObject] = None):
        """
        Initialize the RegionSetupViewModel.
        """
        super().__init__(parent)

        # --- Store Services ---
        self._logger = logger
        self._region_service = region_service
        self._platform_selection_service = platform_selection_service
        self._flash_service = flash_service
        self._ui_service = ui_service
        self._screenshot_service = screenshot_service

        # --- Internal State Attributes ---
        self._selected_platform: Optional[str] = None
        # Note: We don't store the actual Region objects long-term here.
        # We fetch them from the service when needed and emit formatted data/previews.
        self._monitor_status_text: str = "N/A"
        self._monitor_coords_text: str = "N/A"
        self._monitor_preview_pixmap: QPixmap = QPixmap()
        self._can_delete_monitor: bool = False
        self._can_flash_monitor: bool = False
        self._flatten_list_data: List[Dict[str, Any]] = []
        self._can_add_flatten: bool = False
        # --- Initialization ---
        self._logger.debug("Initializing RegionSetupViewModel...")
        self._platform_selection_service.register_platform_change_listener(
            self._handle_platform_selection_change
        )
        initial_platform = self._platform_selection_service.get_current_platform()
        # Trigger initial load and UI update for the current platform
        self._load_regions_for_platform(initial_platform)
        self._logger.debug("RegionSetupViewModel initialized.")



    # --- Command Slots (Called by the View) ---

    @Slot()
    def define_edit_monitor_region(self):
        """Handles defining or editing the single monitor region."""
        if not self._selected_platform:
            self.status_message_changed.emit("No platform selected.", "ERROR")
            return

        region_type = "monitor"
        region_name = "monitor" # Use a fixed, standard name

        # Check if editing or defining anew
        existing_region_result = self._region_service.get_monitor_region(self._selected_platform)
        is_editing = existing_region_result.is_success and existing_region_result.value is not None
        action_text = "editing" if is_editing else "defining"
        self.status_message_changed.emit(f"Starting region selection for {action_text} the P&L region...", "INFO")

        # --- Use UI service to select region ---
        # This call blocks until selection is done or cancelled (handled by UIService)
        region_result = self._ui_service.select_screen_region(f"Please select the P&L Monitoring region")

        if region_result.is_failure:
            self.status_message_changed.emit(f"Region selection failed: {region_result.error}", "ERROR")
            return
        if region_result.value is None:
            self.status_message_changed.emit("Region selection cancelled.", "INFO")
            return

        coordinates = region_result.value
        self._logger.info(f"User selected P&L region coordinates: {coordinates}")

        # Create the Region object
        region_id = f"{self._selected_platform}_{region_type}_{region_name}"
        region = Region(
            id=region_id, name=region_name, coordinates=coordinates,
            type=region_type, platform=self._selected_platform
        )

        # --- Capture Screenshot Data ---
        # This returns Result[Tuple[ImageData, IntendedPath]]
        capture_result = self._region_service.capture_region_screenshot(
            coordinates, region.id, region.platform, region.type
        )

        image_data = None
        if capture_result.is_success:
            image_data, _ = capture_result.value # Don't need intended path here
            # Attach image data temporarily for save_region
            setattr(region, '_temp_screenshot_data', image_data)
            self.status_message_changed.emit(f"Captured screenshot for region '{region.name}'.", "INFO")
        elif capture_result.is_failure:
            self.status_message_changed.emit(f"Failed to capture screenshot: {capture_result.error}", "WARNING")
            # Proceed to save metadata without image

        # --- Save the Region (Repository handles overwriting monitor region) ---
        save_result = self._region_service.save_region(region)

        if save_result.is_failure:
            self.status_message_changed.emit(f"Failed to save monitor region: {save_result.error}", "ERROR")
            # Show critical message maybe? self.ui_service.show_message(...)
            return

        # --- Emit the new signal on successful save ---
        self.monitor_region_saved.emit(self._selected_platform)

        self.status_message_changed.emit(f"Successfully defined/updated monitor region: {coordinates}", "SUCCESS")

        # --- Refresh the display for the current platform ---
        self._load_monitor_region(self._selected_platform)


    @Slot()
    def delete_monitor_region(self):
        """Deletes the single monitor region for the current platform."""
        if not self._selected_platform:
            self.status_message_changed.emit("No platform selected.", "ERROR")
            return

        # --- Confirmation Dialog (using UIService) ---
        confirm_result = self._ui_service.show_confirmation(
            "Confirm Delete",
            f"Delete the P&L Monitoring region for {self._selected_platform}?"
        )
        if confirm_result.is_failure or not confirm_result.value:
             self.status_message_changed.emit("Monitor region deletion cancelled.", "INFO")
             return

        self.status_message_changed.emit(f"Deleting monitor region for {self._selected_platform}...", "INFO")

        # Call service (Repository handles setting monitor_region to None)
        delete_result = self._region_service.delete_region(self._selected_platform, "monitor", "monitor")

        if delete_result.is_failure and delete_result.error.category != ErrorCategory.VALIDATION:
            # Ignore "Not Found" validation errors, but report others
            self.status_message_changed.emit(f"Failed to delete monitor region: {delete_result.error}", "ERROR")
            return

        self.status_message_changed.emit(f"Deleted monitor region for {self._selected_platform}", "SUCCESS")
        # Refresh display
        self._load_monitor_region(self._selected_platform)


    @Slot()
    def flash_monitor_region(self):
        """Flashes the monitor region for the current platform."""
        if not self._selected_platform:
             self.status_message_changed.emit("No platform selected.", "ERROR")
             return

        self.status_message_changed.emit(f"Flashing monitor region for {self._selected_platform}...", "INFO")
        flash_result = self._flash_service.flash_region(self._selected_platform, "monitor", "monitor")
        if flash_result.is_failure:
             self.status_message_changed.emit(f"Failed to initiate flash: {flash_result.error}", "ERROR")
        # No success message needed here, service logs success internally

    @Slot()
    def add_flatten_region(self):
        """Starts the process to add a new flatten region."""
        if not self._selected_platform:
            self.status_message_changed.emit("No platform selected.", "ERROR")
            return

        region_type = "flatten"

        # --- Get default name ---
        flatten_regions_result = self._region_service.get_regions_by_platform(self._selected_platform, region_type)
        count = len(flatten_regions_result.value) if flatten_regions_result.is_success else 0
        default_name = f"Flatten_{count + 1}"

        self.status_message_changed.emit(f"Starting region selection for adding a flatten region...", "INFO")

        # --- Select Area ---
        region_result = self._ui_service.select_screen_region("Please select the Flatten Position button region")
        if region_result.is_failure:
            self.status_message_changed.emit(f"Region selection failed: {region_result.error}", "ERROR")
            return
        if region_result.value is None:
            self.status_message_changed.emit("Region selection cancelled.", "INFO")
            return
        coordinates = region_result.value

        # --- Get Name (Using QInputDialog via UIService - Needs adding) ---
        # Assuming UIService needs a method like get_text_input(title, label, default) -> Result[Optional[str]]
        # For now, we'll use a placeholder and log.
        # name_result = self._ui_service.get_text_input("Name Flatten Region", "Enter a unique name:", default_name)
        # if name_result.is_failure or name_result.value is None:
        #      self.status_message_changed.emit("Region naming cancelled.", "INFO")
        #      return
        # name = name_result.value.strip()
        # --- Placeholder until UIService.get_text_input exists ---
        name = default_name # Use default name for now
        self._logger.warning("UIService needs get_text_input; using default name for flatten region.")
        # --- End Placeholder ---

        # TODO: Add validation loop here once get_text_input exists
        # - Check if name is empty
        # - Check if name already exists using self._region_service.get_region
        # - Ask for overwrite confirmation if exists

        # Create Region Object
        region_id = f"{self._selected_platform}_{region_type}_{name}"
        region = Region(id=region_id, name=name, coordinates=coordinates, type=region_type, platform=self._selected_platform)

        # Capture Screenshot
        capture_result = self._region_service.capture_region_screenshot(coordinates, region.id, region.platform, region.type)
        if capture_result.is_success:
            setattr(region, '_temp_screenshot_data', capture_result.value[0])
        else:
            self.status_message_changed.emit(f"Failed capture screenshot for '{name}': {capture_result.error}", "WARNING")

        # Save Region
        save_result = self._region_service.save_region(region)
        if save_result.is_failure:
            self.status_message_changed.emit(f"Failed to save flatten region '{name}': {save_result.error}", "ERROR")
            return

        self.status_message_changed.emit(f"Added flatten region '{name}': {coordinates}", "SUCCESS")
        # Refresh the flatten list display
        self._load_flatten_regions(self._selected_platform)

    @Slot(str) # Expects the region name (ID for the entry widget)
    def edit_flatten_region(self, region_name: str):
        """Starts the process to edit an existing flatten region."""
        if not self._selected_platform:
            self.status_message_changed.emit("No platform selected.", "ERROR")
            return

        self.status_message_changed.emit(f"Editing flatten region '{region_name}'...", "INFO")

        # Get current region data (optional, needed for coords only if UI doesn't provide)
        # get_result = self._region_service.get_region(self._selected_platform, "flatten", region_name)
        # if get_result.is_failure: # ... handle error ...

        # Select New Area
        region_result = self._ui_service.select_screen_region(
            f"Select the NEW area for the '{region_name}' flatten region"
        )
        if region_result.is_failure:
            self.status_message_changed.emit(f"Region edit failed: {region_result.error}", "ERROR")
            return
        if region_result.value is None:
            self.status_message_changed.emit("Region edit cancelled.", "INFO")
            return
        new_coordinates = region_result.value

        # Ask to recapture screenshot (Optional - could always recapture)
        recapture_result = self._ui_service.show_confirmation("Recapture Screenshot?",
                                         "Capture a new screenshot for the updated region?")
        recapture = recapture_result.is_success and recapture_result.value

        # Create/Update Region Object
        region_id = f"{self._selected_platform}_flatten_{region_name}"
        region = Region(id=region_id, name=region_name, coordinates=new_coordinates,
                        type="flatten", platform=self._selected_platform)

        if recapture:
            capture_result = self._region_service.capture_region_screenshot(
                new_coordinates, region.id, region.platform, region.type
            )
            if capture_result.is_success:
                setattr(region, '_temp_screenshot_data', capture_result.value[0])
            else:
                self.status_message_changed.emit(f"Failed capture new screenshot for '{region_name}': {capture_result.error}", "WARNING")

        # Save updated region
        save_result = self._region_service.save_region(region)
        if save_result.is_failure:
            self.status_message_changed.emit(f"Failed save edited region '{region_name}': {save_result.error}", "ERROR")
            return

        self.status_message_changed.emit(f"Updated flatten region '{region_name}': {new_coordinates}", "SUCCESS")
        # Refresh the flatten list display
        self._load_flatten_regions(self._selected_platform)

    @Slot(str) # Expects the region name
    def delete_flatten_region(self, region_name: str):
        """Deletes a specific flatten region."""
        if not self._selected_platform:
             self.status_message_changed.emit("No platform selected.", "ERROR"); return

        confirm_result = self._ui_service.show_confirmation("Confirm Delete",
             f"Delete the flatten region '{region_name}' for {self._selected_platform}?"
        )
        if confirm_result.is_failure or not confirm_result.value:
             self.status_message_changed.emit(f"Deletion of flatten region '{region_name}' cancelled.", "INFO")
             return

        self.status_message_changed.emit(f"Deleting flatten region '{region_name}'...", "INFO")

        # Call service (Repository removes from flatten_regions dict)
        delete_result = self._region_service.delete_region(self._selected_platform, "flatten", region_name)

        if delete_result.is_failure and delete_result.error.category != ErrorCategory.VALIDATION:
             # Ignore "Not Found" validation errors
             self.status_message_changed.emit(f"Failed to delete flatten region '{region_name}': {delete_result.error}", "ERROR")
             return

        self.status_message_changed.emit(f"Deleted flatten region {region_name}", "SUCCESS")
        # Refresh the flatten list display
        self._load_flatten_regions(self._selected_platform)


    @Slot(str) # Expects the region name
    def flash_flatten_region(self, region_name: str):
        """Flashes a specific flatten region."""
        if not self._selected_platform:
             self.status_message_changed.emit("No platform selected.", "ERROR")
             return

        self.status_message_changed.emit(f"Flashing flatten region '{region_name}' for {self._selected_platform}...", "INFO")
        flash_result = self._flash_service.flash_region(self._selected_platform, "flatten", region_name)
        if flash_result.is_failure:
             self.status_message_changed.emit(f"Failed to initiate flash for '{region_name}': {flash_result.error}", "ERROR")


    # --- Private Helper / Update Methods ---

    @Slot(str)
    def _handle_platform_selection_change(self, platform: str):
        self._logger.debug(f"RegionSetupViewModel received platform change: {platform}")
        self._load_regions_for_platform(platform)

    def _load_regions_for_platform(self, platform: str):
        self._selected_platform = platform
        self._logger.info(f"Loading regions for platform: {platform}")

        if not platform:
            # Update state and emit signals for cleared state
            self._monitor_status_text = "Select Platform"
            self._monitor_coords_text = "N/A"
            self._monitor_preview_pixmap = QPixmap()
            self._can_delete_monitor = False
            self._can_flash_monitor = False
            self._flatten_list_data = []
            self._can_add_flatten = False

            self.monitor_region_status_changed.emit(self._monitor_status_text)
            self.monitor_region_coords_text_changed.emit(self._monitor_coords_text)
            self.monitor_region_preview_changed.emit(self._monitor_preview_pixmap)
            self.can_delete_monitor_region_changed.emit(self._can_delete_monitor)
            self.can_flash_monitor_region_changed.emit(self._can_flash_monitor)
            self.flatten_regions_list_updated.emit(self._flatten_list_data)
            self.can_add_flatten_region_changed.emit(self._can_add_flatten)
            return

        # Enable adding flatten regions
        self._can_add_flatten = True
        self.can_add_flatten_region_changed.emit(self._can_add_flatten)

        self._load_monitor_region(platform)
        self._load_flatten_regions(platform)

    def _load_monitor_region(self, platform: str):
        if not platform: return
        result = self._region_service.get_monitor_region(platform)
        preview_pixmap = QPixmap()

        if result.is_success and result.value is not None:
            region = result.value
            x, y, w, h = region.coordinates
            # --- Update Internal State ---
            self._monitor_status_text = "Defined"
            self._monitor_coords_text = f"({x}, {y}, {w}, {h})"
            self._can_delete_monitor = True
            self._can_flash_monitor = True
            preview_pixmap = self._load_region_preview(region)
            self._monitor_preview_pixmap = preview_pixmap
        else:
            # --- Update Internal State ---
            self._monitor_status_text = "Not Defined"
            self._monitor_coords_text = "N/A"
            self._can_delete_monitor = False
            self._can_flash_monitor = False
            self._monitor_preview_pixmap = QPixmap()
            if result.is_failure:
                self.status_message_changed.emit(f"Error loading monitor region: {result.error}", "WARNING")

        # --- Emit Signals ---
        self.monitor_region_status_changed.emit(self._monitor_status_text)
        self.monitor_region_coords_text_changed.emit(self._monitor_coords_text)
        self.monitor_region_preview_changed.emit(self._monitor_preview_pixmap)
        self.can_delete_monitor_region_changed.emit(self._can_delete_monitor)
        self.can_flash_monitor_region_changed.emit(self._can_flash_monitor)

    def _load_flatten_regions(self, platform: str):
        if not platform: return
        result = self._region_service.get_regions_by_platform(platform, "flatten")
        flatten_region_list_data = []

        if result.is_success and result.value:
            flatten_regions = result.value
            for region in flatten_regions:
                coords = region.coordinates
                preview_pixmap = self._load_region_preview(region)
                region_item_data = {
                    "name": region.name,
                    "coords_text": f"({coords[0]}, {coords[1]}, {coords[2]}, {coords[3]})",
                    "preview_pixmap": preview_pixmap
                }
                flatten_region_list_data.append(region_item_data)
        elif result.is_failure:
            self.status_message_changed.emit(f"Error loading flatten regions: {result.error}", "WARNING")

        # --- Update Internal State & Emit Signal ---
        self._flatten_list_data = flatten_region_list_data
        self.flatten_regions_list_updated.emit(self._flatten_list_data)


    def _load_region_preview(self, region: Region) -> QPixmap:
        """Helper to load and convert a region's screenshot to QPixmap."""
        empty_pixmap = QPixmap()
        if not region or not region.screenshot_path:
            return empty_pixmap

        load_result = self._region_service.load_region_screenshot(region)
        if load_result.is_failure:
            self._logger.warning(f"Failed to load screenshot file for {region.name}: {load_result.error}")
            return empty_pixmap

        # Convert PIL Image data to QPixmap
        pixmap_result = self._screenshot_service.to_pyside_pixmap(load_result.value)
        if pixmap_result.is_failure:
            self._logger.warning(f"Failed to convert screenshot to QPixmap for {region.name}: {pixmap_result.error}")
            return empty_pixmap

        return pixmap_result.value