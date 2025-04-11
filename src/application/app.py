#src/application/app.py

import os
import logging
from typing import Optional

from src.domain.common.di_container import DIContainer
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_background_task_service import IBackgroundTaskService
from src.domain.services.i_config_repository_service import IConfigRepository
from src.domain.services.i_path_service import IPathService
from src.domain.services.i_platform_detection_service import IPlatformDetectionService
from src.domain.services.i_window_manager_service import IWindowManager
from src.domain.services.i_screenshot_service import IScreenshotService
from src.domain.services.i_ocr_service import IOcrService # Import is present
from src.domain.services.i_monitoring_service import IMonitoringService
from src.domain.services.i_lockout_service import ILockoutService
from src.domain.services.i_verification_service import IVerificationService
from src.domain.services.i_cold_turkey_service import IColdTurkeyService
from src.domain.services.i_ui_service import IUIService
from src.domain.services.i_profile_service import IProfileService
from src.domain.services.i_platform_selection_service import IPlatformSelectionService
from src.domain.services.i_region_service import IRegionService
from src.domain.services.i_ocr_analysis_service import IOcrAnalysisService
from src.domain.services.i_flash_service import IFlashService

# Infrastructure Imports
from src.infrastructure.logging.logger_service import ConsoleLoggerService
from src.infrastructure.threading.qt_background_task_service import QtBackgroundTaskService
from src.infrastructure.config.json_config_repository import JsonConfigRepository
from src.infrastructure.system.path_service import PathService
from src.infrastructure.platform.windows_platform_detection_service import WindowsPlatformDetectionService
from src.infrastructure.platform.window_manager import WindowsWindowManager
from src.infrastructure.platform.screenshot_service import QtScreenshotService
from src.infrastructure.ocr.tesseract_ocr_service import TesseractOcrService
from src.infrastructure.platform.monitoring_service import MonitoringService
from src.infrastructure.platform.lockout_service import WindowsLockoutService
from src.infrastructure.platform.verification_service import WindowsVerificationService
from src.infrastructure.platform.windows_cold_turkey_service import WindowsColdTurkeyService
from src.infrastructure.ui.qt_ui_service import QtUIService
from src.infrastructure.config.profile_service import ProfileService
from src.infrastructure.platform.platform_selection_service import PlatformSelectionService
from src.infrastructure.platform.region_service import RegionService
from src.infrastructure.ocr.ocr_analysis_service import OcrAnalysisService
from src.infrastructure.ui.flash_service import QtFlashService

def initialize_app() -> DIContainer:
    container = DIContainer()

    # Core services (These are good candidates for singletons)
    logger = ConsoleLoggerService(level=logging.DEBUG)
    container.register_instance(ILoggerService, logger)

    path_service = PathService(logger=logger)
    container.register_instance(IPathService, path_service)

    config_repo = JsonConfigRepository(path_service=path_service, logger=logger)
    container.register_instance(IConfigRepository, config_repo)
    path_service.set_config_repository(config_repo) # Link back

    thread_service = QtBackgroundTaskService(logger)
    container.register_instance(IBackgroundTaskService, thread_service)

    # Window management (Singleton makes sense)
    window_manager = WindowsWindowManager(container.resolve(ILoggerService))
    container.register_instance(IWindowManager, window_manager)

    # UI service (Usually a singleton in Qt apps, but factory is okay if needed)
    container.register_factory(
        IUIService,
        lambda: QtUIService(container.resolve(ILoggerService))
    )

    # Platform services
    # Screenshot service (Factory okay, unlikely to hold much state)
    container.register_factory(
        IScreenshotService,
        lambda: QtScreenshotService(container.resolve(ILoggerService))
    )

    # 1. Create the instance ONCE
    ocr_service_instance = TesseractOcrService(logger) # Use the already resolved logger
    # 2. Register the specific INSTANCE
    container.register_instance(IOcrService, ocr_service_instance)


    # OCR Analysis Service (Factory okay, likely stateless analysis methods)
    container.register_factory(
        IOcrAnalysisService,
        lambda: OcrAnalysisService(
            logger=container.resolve(ILoggerService)
        )
    )

    # Region Service (Factory okay, might depend on changing config)
    container.register_factory(
        IRegionService,
        lambda: RegionService(
            config_repository=container.resolve(IConfigRepository), # Gets singleton
            screenshot_service=container.resolve(IScreenshotService), # Gets new instance
            path_service=container.resolve(IPathService), # Gets singleton
            logger=logger
        )
    )

    # Platform Selection Service (Factory okay, depends on config)
    container.register_factory(
        IPlatformSelectionService,
        lambda: PlatformSelectionService(
            config_repository=container.resolve(IConfigRepository), # Gets singleton
            logger=container.resolve(ILoggerService),
            platform_detection_service=container.resolve(IPlatformDetectionService) # Resolves factory -> new instance
        )
    )

    # Profile Service (Factory okay, depends on config)
    container.register_factory(
        IProfileService,
        lambda: ProfileService(
            config_repository=container.resolve(IConfigRepository), # Gets singleton
            logger=container.resolve(ILoggerService),
            ocr_analysis_service=container.resolve(IOcrAnalysisService) # Resolves factory -> new instance
        )
    )

    # Platform Detection Service (Factory okay)
    container.register_factory(
        IPlatformDetectionService,
        lambda: WindowsPlatformDetectionService(
            logger=container.resolve(ILoggerService),
            window_manager=container.resolve(IWindowManager) # Gets singleton
        )
    )

    # Cold Turkey integration (Factory okay)
    container.register_factory(
        IColdTurkeyService,
        lambda: WindowsColdTurkeyService(
            logger=container.resolve(ILoggerService),
            config_repository=container.resolve(IConfigRepository), # Gets singleton
            window_manager=container.resolve(IWindowManager) # Gets singleton
        )
    )

    # Verification service (Factory okay)
    container.register_factory(
        IVerificationService,
        lambda: WindowsVerificationService(
            logger=container.resolve(ILoggerService),
            cold_turkey_service=container.resolve(IColdTurkeyService), # Resolves factory -> new instance
            thread_service=container.resolve(IBackgroundTaskService), # Gets singleton
            ui_service=container.resolve(IUIService) # Resolves factory -> new instance
            # Note: Does not directly resolve IOcrService here
        )
    )

    # Core application services
    # Lockout Service (Factory okay)
    container.register_factory(
        ILockoutService,
        lambda: WindowsLockoutService(
            logger=container.resolve(ILoggerService),
            config_repository=container.resolve(IConfigRepository), # Gets singleton
            platform_detection_service=container.resolve(IPlatformDetectionService), # Resolves factory -> new instance
            window_manager=container.resolve(IWindowManager), # Gets singleton
            ui_service=container.resolve(IUIService), # Resolves factory -> new instance
            cold_turkey_service=container.resolve(IColdTurkeyService), # Resolves factory -> new instance
            thread_service=container.resolve(IBackgroundTaskService) # Gets singleton
        )
    )

    # Monitoring Service (Now gets singleton IOcrService)
    container.register_factory(
        IMonitoringService,
        lambda: MonitoringService(
            screenshot_service=container.resolve(IScreenshotService), # Resolves factory -> new instance
            ocr_service=container.resolve(IOcrService), # --- FIX: Resolves the SINGLETON instance ---
            thread_service=container.resolve(IBackgroundTaskService), # Gets singleton
            platform_detection_service=container.resolve(IPlatformDetectionService), # Resolves factory -> new instance
            config_repository=container.resolve(IConfigRepository), # Gets singleton
            path_service=container.resolve(IPathService), # Gets singleton
            logger=logger,
            profile_service=container.resolve(IProfileService), # Resolves factory -> new instance
        )
    )

    container.register_factory(
        IFlashService,
        lambda: QtFlashService(
            logger=container.resolve(ILoggerService),
            platform_detection=container.resolve(IPlatformDetectionService),
            region_service=container.resolve(IRegionService),
            ui_service=container.resolve(IUIService),  # Assuming overlay support added
            thread_service=container.resolve(IBackgroundTaskService)
        )
    )

    logger.info("Application dependencies initialized")
    return container


# --- Keep get_container() as is ---
_container: Optional[DIContainer] = None

def get_container() -> DIContainer:
    """Gets the singleton DI container, initializing it if necessary."""
    global _container
    if _container is None:
        # This print helps confirm initialize_app runs only once
        # print("DEBUG: Initializing DI container...")
        _container = initialize_app()
    return _container
