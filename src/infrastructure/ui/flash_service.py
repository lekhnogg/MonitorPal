# src/infrastructure/ui/qt_flash_service.py (or similar path)
from src.domain.services.i_flash_service import IFlashService
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_platform_detection_service import IPlatformDetectionService
from src.domain.services.i_region_service import IRegionService
from src.domain.services.i_ui_service import IUIService # Needs overlay capability added
from src.domain.services.i_background_task_service import IBackgroundTaskService, Worker
from src.domain.common.result import Result
import time

# --- Define the Worker for the flashing animation ---
class FlashWorker(Worker[None]):
    def __init__(self, coords, ui_service: IUIService, logger: ILoggerService):
         super().__init__()
         self.coords = coords
         self.ui_service = ui_service
         self.logger = logger
         self.flash_count = 3
         self.flash_duration_ms = 150 # How long each flash stays visible/hidden

    def execute(self) -> None:
        overlay_result = self.ui_service.create_flash_overlay(self.coords)
        if overlay_result.is_failure:
             self.report_error(f"Failed to create flash overlay: {overlay_result.error}")
             return

        overlay = overlay_result.value
        try:
            for i in range(self.flash_count * 2): # Show + Hide = 1 cycle
                 if self.cancel_requested: break

                 if i % 2 == 0: # Show
                      overlay.show()
                 else: # Hide
                      overlay.hide()

                 time.sleep(self.flash_duration_ms / 1000.0)

        except Exception as e:
             self.report_error(f"Error during flashing: {e}")
        finally:
             # Ensure overlay is cleaned up
             if overlay:
                  overlay.destroy_overlay() # Assumes overlay object has cleanup method
             self.logger.debug("Flash overlay destroyed.")
        return None # Worker completes


# --- Implement the Service ---
class QtFlashService(IFlashService):
    def __init__(self,
                 logger: ILoggerService,
                 platform_detection: IPlatformDetectionService,
                 region_service: IRegionService,
                 ui_service: IUIService, # Needs overlay capability
                 thread_service: IBackgroundTaskService):
        self.logger = logger
        self.platform_detection = platform_detection
        self.region_service = region_service
        self.ui_service = ui_service
        self.thread_service = thread_service

    def flash_region(self, platform: str, region_type: str, region_name: str) -> Result[None]:
        self.logger.info(f"Attempting to flash region '{region_name}' for platform '{platform}'")

        # 1. Activate Platform Window
        activate_result = self.platform_detection.activate_platform_windows(platform)
        if activate_result.is_failure:
             msg = f"Failed to activate platform '{platform}': {activate_result.error}"
             self.logger.error(msg)
             return Result.fail(activate_result.error) # Propagate error

        # Allow a moment for window activation
        time.sleep(0.2)

        # 2. Get Region Coordinates
        region_result = self.region_service.get_region(platform, region_type, region_name)
        if region_result.is_failure:
            msg = f"Failed to get region '{region_name}': {region_result.error}"
            self.logger.error(msg)
            return Result.fail(region_result.error)
        region = region_result.value
        coords = region.coordinates

        # 3. Run Flashing in Background Worker
        worker = FlashWorker(coords, self.ui_service, self.logger)
        task_id = f"flash_{platform}_{region_name}"

        # Define callbacks for worker completion/error if needed (optional here)
        def on_error(err_msg):
             self.logger.error(f"Flashing task failed for '{region_name}': {err_msg}")
        worker.set_on_error(on_error)

        # Execute task (fire and forget mostly, errors logged by worker/callback)
        exec_result = self.thread_service.execute_task_and_restore_result(task_id, worker)

        if exec_result.is_failure:
             # Failed to even start the task
             self.logger.error(f"Failed to start flashing task: {exec_result.error}")
             return exec_result # Return the failure to start the task
        else:
             self.logger.info(f"Flashing task started successfully for '{region_name}'")
             return Result.ok(None) # Indicate task started