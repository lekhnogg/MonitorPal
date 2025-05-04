# src/infrastructure/ui/qt_flash_service.py

import time
import uuid
from typing import List, Tuple, Optional, Callable, Dict, Any

# --- Domain Imports ---
from src.domain.services.i_flash_service import IFlashService # Uses updated interface
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_ui_service import IUIService, IFlashOverlay # Needs create_flash_overlay
from src.domain.services.i_background_task_service import IBackgroundTaskService, Worker
from src.domain.common.result import Result
from src.domain.common.errors import PlatformError, ValidationError

# NOTE: Assumes IFlashOverlay interface and QtFlashOverlay implementation
# are defined correctly in qt_ui_service.py or imported if separate.


# --- Define the Worker for the flashing animation ---
class FlashWorker(Worker[None]):
    """
    Background worker to handle the visual flashing of MULTIPLE overlays
    by toggling their visibility state.
    """
    def __init__(self,
                 list_of_coords: List[Tuple[int, int, int, int]],
                 ui_service: IUIService,
                 logger: ILoggerService,
                 flash_count: int = 3,
                 flash_duration_ms: int = 120):
        """
        Initialize the FlashWorker for multiple regions.

        Args:
            list_of_coords: A list of (x, y, width, height) coordinate tuples.
            ui_service: The UI service used to create/manage overlay widgets.
            logger: The logger service.
            flash_count: How many times overlays should blink on and off.
            flash_duration_ms: Duration (in milliseconds) for each visible/hidden state.
        """
        super().__init__()
        self.list_of_coords = list_of_coords
        self.ui_service = ui_service
        self.logger = logger
        self.flash_count = max(1, flash_count)
        self.flash_duration_ms = max(50, flash_duration_ms)
        self.overlays: List[IFlashOverlay] = []

    def execute(self) -> None:
        """Performs the flashing animation for all overlays by toggling visibility."""
        self.logger.debug(f"FlashWorker execute started for {len(self.list_of_coords)} regions.")

        # Create all overlays first
        creation_failed = False
        for i, coords in enumerate(self.list_of_coords):
            if self.cancel_requested: break
            overlay_result = self.ui_service.create_flash_overlay(coords)
            if overlay_result.is_success and overlay_result.value:
                self.overlays.append(overlay_result.value)
                self.logger.debug(f"  Overlay {i+1} created for {coords}: {overlay_result.value}")
            else:
                err_msg = f"Failed to create flash overlay {i+1} for {coords}: {overlay_result.error if overlay_result.is_failure else 'Unknown reason'}"
                self.logger.error(err_msg)
                self.report_error(err_msg)
                creation_failed = True
                break

        if creation_failed or self.cancel_requested:
             self.logger.warning("FlashWorker stopping early due to creation failure or cancellation.")
             self._cleanup_overlays()
             return None

        if not self.overlays:
             self.logger.warning("FlashWorker: No overlays were created successfully.")
             return None

        try:
            # Start animation loop
            self.logger.debug(f"Starting animation loop for {len(self.overlays)} overlays.")
            visible_state = False # Start hidden
            for i in range(self.flash_count * 2): # Total states (on/off cycles)
                if self.cancel_requested:
                    self.logger.info("FlashWorker cancelled during animation loop.")
                    break

                # Toggle the target visibility state for this step
                visible_state = not visible_state
                action_name = "Showing" if visible_state else "Hiding"
                self.logger.debug(f"Flash Cycle {i//2 + 1}: {action_name} overlays")

                # Apply the target visibility state to all overlays
                for overlay in self.overlays:
                    try:
                        # Use setVisible - this is thread-safe in Qt
                        overlay.setVisible(visible_state)
                    except Exception as e:
                        # Log error for specific overlay but continue loop
                        self.logger.error(f"Error setting visibility ({action_name}) on overlay {overlay} at {overlay.geometry()}: {e}")

                # Wait after applying the state to all
                sleep_duration = max(0.01, self.flash_duration_ms / 1000.0)
                time.sleep(sleep_duration)
            # End animation loop

        except Exception as e:
             # Catch errors during the loop itself
             err_msg = f"Error during flashing animation loop: {e}"
             self.logger.error(err_msg, exc_info=True)
             self.report_error(err_msg)
        finally:
             # Ensure cleanup runs regardless of how the loop finishes
             self._cleanup_overlays()
             self.logger.debug("FlashWorker execute finished.")

        return None # Explicitly return None

    def _cleanup_overlays(self):
        """Helper method to hide and destroy all created overlays."""
        if not self.overlays: return
        self.logger.debug(f"Cleaning up {len(self.overlays)} flash overlays...")
        # Use a separate loop for hide and destroy to ensure all are hidden first
        for overlay in self.overlays:
            try:
                overlay.setVisible(False) # Ensure hidden using setVisible
            except Exception as hide_err:
                 self.logger.warning(f"Error hiding overlay {overlay} during cleanup: {hide_err}")

        # Give the event loop a tiny moment to process hide events if needed
        # time.sleep(0.05) # Usually not necessary with deleteLater

        for overlay in self.overlays:
             try:
                  # destroy_overlay should call deleteLater on the widget
                  overlay.destroy_overlay()
             except Exception as cleanup_err:
                  self.logger.error(f"Error destroying overlay {overlay}: {cleanup_err}")
        self.overlays = [] # Clear the list
# --- End FlashWorker ---



# --- Implement the Service ---
class QtFlashService(IFlashService):
    """
    Qt implementation of the flash service using background tasks.
    This version accepts coordinates directly.
    """
    # --- Updated __init__ (Removes platform_detection and region_service) ---
    def __init__(self,
                 logger: ILoggerService,
                 ui_service: IUIService,
                 thread_service: IBackgroundTaskService):
        """
        Initialize the QtFlashService.

        Args:
            logger: Logger service instance.
            ui_service: UI service instance (must provide overlay creation).
            thread_service: Background task service instance.
        """
        self.logger = logger
        self.ui_service = ui_service
        self.thread_service = thread_service
        self.logger.debug("QtFlashService initialized (Simplified).")
    # --- End __init__ ---


    # --- Implement flash_regions (The only public method now) ---
    def flash_regions(self, list_of_coords: List[Tuple[int, int, int, int]]) -> Result[None]:
        """
        Flashes multiple screen regions simultaneously given their coordinates.
        Uses a background task.

        Args:
            list_of_coords: A list of coordinate tuples (x, y, w > 0, h > 0).

        Returns:
            Result indicating if the flashing task was successfully started.
        """
        # --- Input Validation ---
        if not list_of_coords:
            self.logger.warning("flash_regions called with empty list.")
            return Result.fail(ValidationError("No region coordinates provided to flash."))

        if not isinstance(list_of_coords, list) or not all(
                isinstance(c, tuple) and len(c) == 4 and all(isinstance(x, int) for x in c) and c[2] > 0 and c[3] > 0
                for c in list_of_coords):
             msg = "Invalid format for list_of_coords. Expected List[Tuple[int, int, int > 0, int > 0]]."
             self.logger.error(msg)
             return Result.fail(ValidationError(msg))
        # --- End Validation ---

        self.logger.info(f"Attempting to flash {len(list_of_coords)} region(s).")

        # --- Create ONE worker with the list of coordinates ---
        worker = FlashWorker(
            list_of_coords=list_of_coords,
            ui_service=self.ui_service,
            logger=self.logger
            # Pass flash_count/duration here if they become parameters
        )

        # --- Generate a single unique Task ID for this multi-flash operation ---
        task_id = f"flash_multi_region_{uuid.uuid4().hex[:8]}"
        self.logger.debug(f"Generated multi-flash task ID: {task_id}")

        # --- Define Error Callback ---
        def on_error(err_msg: str):
             # This handles errors reported *from within* the FlashWorker.execute method
             self.logger.error(f"Error reported by flashing task (TaskID: {task_id}): {err_msg}")
             # Potentially show a UI message here if needed, using self.ui_service
        worker.set_on_error(on_error)
        # --- End Error Callback ---

        # --- Execute the SINGLE Task ---
        # Use execute_task_and_restore_result for automatic cleanup via finished signal
        exec_result = self.thread_service.execute_task_and_restore_result(task_id, worker)
        # --- End Execute Task ---

        if exec_result.is_failure:
             # This handles errors *starting* the task in BackgroundTaskService (e.g., thread creation failed)
             self.logger.error(f"Failed to *start* multi-region flashing task '{task_id}': {exec_result.error}")
             return Result.fail(exec_result.error) # Return the failure Result from execute_task
        else:
             self.logger.info(f"Multi-region flashing task '{task_id}' initiated successfully.")
             # Return success indicating the task was successfully submitted.
             # The flash happens asynchronously.
             return Result.ok(None)
    # --- End flash_regions ---
# --- End QtFlashService Class ---