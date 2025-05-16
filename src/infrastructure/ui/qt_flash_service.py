# src/infrastructure/ui/qt_flash_service.py

import uuid
from typing import List, Tuple, Optional, Any

# --- Qt Imports ---
from PySide6.QtCore import QObject, Signal
# --- ABC Imports for metaclass conflict resolution ---
from abc import ABCMeta, ABC # ABC is the base for IFlashService

# --- Domain Imports ---
from src.domain.services.i_flash_service import IFlashService # This IS an ABC
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_ui_service import IUIService, IFlashOverlay
from src.domain.services.i_background_task_service import IBackgroundTaskService, Worker
from src.domain.common.result import Result
from src.domain.common.errors import ValidationError

import time

# --- Helper class to resolve metaclass conflict between QObject and ABC ---
class QObjectABCMeta(type(QObject), ABCMeta):
    """Metaclass that inherits from both QObject's metaclass and ABCMeta."""
    pass

class QObjectABC(QObject, ABC, metaclass=QObjectABCMeta):
    """
    Base class for objects that need to be both QObject (for signals/slots)
    and an ABC (for defining abstract interfaces that are implemented).
    """
    def __init__(self, parent: Optional[QObject] = None):
        # QObject's __init__ does not strictly need super() if it's the first in MRO for QObject features
        # but good practice for multiple inheritance if other bases also have __init__.
        # ABC does not have an __init__ that needs calling.
        super(QObjectABC, self).__init__(parent)


# --- Worker Definition ---
class FlashWorker(Worker[None]):
    # ... (FlashWorker code remains the same as provided in the corrected version previously)
    def __init__(self,
                 list_of_coords: List[Tuple[int, int, int, int]],
                 ui_service: IUIService,
                 logger: ILoggerService,
                 flash_count: int = 3,
                 flash_duration_ms: int = 120):
        super().__init__()
        self.list_of_coords = list_of_coords
        self.ui_service = ui_service
        self.logger = logger
        self.flash_count = max(1, flash_count)
        self.flash_duration_ms = max(50, flash_duration_ms)
        self.overlays: List[IFlashOverlay] = []

    def execute(self) -> None:  # Return type is None
        self.logger.debug(f"FlashWorker: Execute started for {len(self.list_of_coords)} regions.")

        creation_failed = False
        for i, coords in enumerate(self.list_of_coords):
            if self.cancel_requested:
                self.logger.info("FlashWorker: Cancellation requested during overlay creation.")
                break
            overlay_result = self.ui_service.create_flash_overlay(coords)
            if overlay_result.is_success and overlay_result.value:
                self.overlays.append(overlay_result.value)
                # Removed the per-overlay creation log here to reduce noise for this test, can add back later
                # self.logger.debug(f"  FlashWorker: Overlay {i+1} created for {coords}.")
            else:
                err_msg = f"Failed to create flash overlay {i + 1} for {coords}: {overlay_result.error if overlay_result.is_failure else 'Unknown reason'}"
                self.logger.error(f"FlashWorker: {err_msg}")
                self.report_error(err_msg)
                creation_failed = True
                break

        if creation_failed or self.cancel_requested:
            self.logger.warning("FlashWorker: Stopping early due to overlay creation failure or cancellation.")
            self._cleanup_overlays()
            return None

        if not self.overlays:
            self.logger.warning("FlashWorker: No overlays were created successfully. Nothing to flash.")
            return None

        # This is the critical block
        try:
            self.logger.debug(
                f"FlashWorker: >>> Starting animation loop for {len(self.overlays)} overlays. Flash Count: {self.flash_count}, Duration/State: {self.flash_duration_ms}ms")  # ADDED DETAIL
            visible_state = False  # Start with overlays hidden
            for i_loop_idx in range(self.flash_count * 2):  # Use a different loop variable name
                if self.cancel_requested:
                    self.logger.info("FlashWorker: Cancellation requested during animation loop.")
                    break

                visible_state = not visible_state
                action_name = "Showing" if visible_state else "Hiding"
                # More specific log for inside the loop
                self.logger.debug(
                    f"  FlashWorker: >>> Loop Index {i_loop_idx}, Cycle {(i_loop_idx // 2) + 1}, State {('On' if visible_state else 'Off')}: {action_name} overlays.")

                for overlay_idx, overlay in enumerate(self.overlays):  # Iterate with index for logging
                    try:
                        # self.logger.debug(f"    FlashWorker: Setting overlay {overlay_idx} to visible: {visible_state}") # Potentially too verbose
                        overlay.setVisible(visible_state)
                    except Exception as e:
                        self.logger.error(
                            f"  FlashWorker: Error setting visibility ({action_name}) on overlay {overlay_idx} ({overlay}) at {overlay.geometry()}: {e}")

                sleep_duration_sec = max(0.01, self.flash_duration_ms / 1000.0)
                # self.logger.debug(f"  FlashWorker: Sleeping for {sleep_duration_sec:.3f} seconds.") # Can be verbose
                time.sleep(sleep_duration_sec)
        except Exception as e:
            err_msg = f"FlashWorker: Error during flashing animation loop: {e}"
            self.logger.error(err_msg, exc_info=True)
            self.report_error(err_msg)  # Ensure error is reported up
        finally:
            self._cleanup_overlays()
            self.logger.debug("FlashWorker: Execute finished (finally block).")  # Clarify source of this log

        return None

    def _cleanup_overlays(self):
        if not self.overlays: return
        for overlay in self.overlays:
            try: overlay.setVisible(False)
            except Exception: pass
        for overlay in self.overlays:
             try: overlay.destroy_overlay()
             except Exception: pass
        self.overlays = []
# --- End FlashWorker ---


# --- QtFlashService Implementation ---
# MODIFIED to use QObjectABC as the first base if IFlashService is an ABC
class QtFlashService(QObjectABC, IFlashService):
    flash_animation_completed = Signal(str)
    flash_animation_failed = Signal(str, str)

    def __init__(self,
                 logger: ILoggerService,
                 ui_service: IUIService,
                 thread_service: IBackgroundTaskService):
        # super().__init__() # QObjectABC handles calling QObject's init.
        # If QObjectABC had a more complex __init__ you'd call super(QtFlashService, self).__init__(...)
        # For simple QObject, often QObject.__init__(self) is done directly if it's the only QObject base.
        # Since QObjectABC now exists:
        super().__init__() # This will call QObjectABC's __init__ -> QObject's __init__

        self.logger = logger
        self.ui_service = ui_service
        self.thread_service = thread_service
        self.logger.debug("QtFlashService initialized (with QObjectABC base).")

    def flash_regions(self, list_of_coords: List[Tuple[int, int, int, int]]) -> Result[str]:


        if not list_of_coords:
            return Result.fail(ValidationError("No region coordinates provided to flash."))
        if not isinstance(list_of_coords, list) or not all(
                isinstance(c, tuple) and len(c) == 4 and
                all(isinstance(x, int) for x in c) and
                c[2] > 0 and c[3] > 0
                for c in list_of_coords):
             msg = "Invalid format for list_of_coords. Expected List[Tuple[int, int, width > 0, height > 0]]."
             self.logger.error(f"QtFlashService: {msg}")
             return Result.fail(ValidationError(msg))

        task_id = f"flash_task_{uuid.uuid4().hex[:8]}"
        self.logger.info(f"QtFlashService: Preparing to flash {len(list_of_coords)} region(s) with task_id: {task_id}.")

        flash_worker_instance = FlashWorker(
            list_of_coords=list_of_coords,
            ui_service=self.ui_service,
            logger=self.logger
        )

        def _on_flash_worker_actually_completed(result_payload: Optional[Any]):
            self.logger.info(f"QtFlashService: Flash animation for task '{task_id}' reported as completed. Emitting signal.")
            self.flash_animation_completed.emit(task_id)

        def _on_flash_worker_reported_error(error_message: str):
            self.logger.error(f"QtFlashService: Flash animation for task '{task_id}' reported failure: {error_message}. Emitting signal.")
            self.flash_animation_failed.emit(task_id, error_message)

        flash_worker_instance.set_on_completed(_on_flash_worker_actually_completed)
        flash_worker_instance.set_on_error(_on_flash_worker_reported_error)

        start_task_result = self.thread_service.execute_task(task_id, flash_worker_instance)

        if start_task_result.is_failure:
            error_on_start = f"Failed to start flash task: {start_task_result.error}"
            self.logger.error(f"QtFlashService: Failed to *initiate* flashing task '{task_id}': {error_on_start}")
            self.flash_animation_failed.emit(task_id, error_on_start)
            return Result.fail(error_on_start)
        else:
            self.logger.info(f"QtFlashService: Flashing task '{task_id}' successfully initiated and submitted to background service.")
            return Result.ok(task_id)