# src/application/app.py

import os
import logging
from typing import Optional

# --- Domain Imports ---
from src.domain.common.di_container import DIContainer
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_background_task_service import IBackgroundTaskService
from src.domain.services.i_config_repository_service import IConfigRepository
from src.domain.services.i_path_service import IPathService
from src.domain.services.i_platform_detection_service import IPlatformDetectionService
from src.domain.services.i_window_manager_service import IWindowManager
from src.domain.services.i_screenshot_service import IScreenshotService
from src.domain.services.i_ocr_service import IOcrService
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

# --- Infrastructure Imports ---
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

    # --- Core Singletons ---
    logger = ConsoleLoggerService(level=logging.DEBUG)
    container.register_instance(ILoggerService, logger)

    path_service = PathService(logger=logger)
    container.register_instance(IPathService, path_service)

    config_repo = JsonConfigRepository(path_service=path_service, logger=logger)
    container.register_instance(IConfigRepository, config_repo)
    path_service.set_config_repository(config_repo) # Link back for potential override check

    thread_service = QtBackgroundTaskService(logger)
    container.register_instance(IBackgroundTaskService, thread_service)

    window_manager = WindowsWindowManager(logger) # Pass logger directly
    container.register_instance(IWindowManager, window_manager)

    # --- Singleton Instances (Formerly Factories) ---

    # Create instances ONCE, ensuring dependencies are resolved/passed correctly.
    # The container resolves interfaces to their registered singleton instances.

    ui_service = QtUIService(logger)
    container.register_instance(IUIService, ui_service)

    screenshot_service = QtScreenshotService(logger)
    container.register_instance(IScreenshotService, screenshot_service)

    ocr_service = TesseractOcrService(logger)
    container.register_instance(IOcrService, ocr_service)

    ocr_analysis_service = OcrAnalysisService(logger)
    container.register_instance(IOcrAnalysisService, ocr_analysis_service)

    platform_detection_service = WindowsPlatformDetectionService(
        logger=logger,
        window_manager=window_manager # Pass the singleton instance
    )
    container.register_instance(IPlatformDetectionService, platform_detection_service)

    region_service = RegionService(
        config_repository=config_repo,
        screenshot_service=screenshot_service, # Pass the singleton instance
        path_service=path_service,
        logger=logger
    )
    container.register_instance(IRegionService, region_service)

    platform_selection_service = PlatformSelectionService(
        config_repository=config_repo,
        logger=logger,
        platform_detection_service=platform_detection_service # Pass the singleton instance
    )
    container.register_instance(IPlatformSelectionService, platform_selection_service)

    profile_service = ProfileService(
        config_repository=config_repo,
        logger=logger,
        ocr_analysis_service=ocr_analysis_service # Pass the singleton instance
    )
    container.register_instance(IProfileService, profile_service)

    cold_turkey_service = WindowsColdTurkeyService(
        logger=logger,
        config_repository=config_repo
    )
    container.register_instance(IColdTurkeyService, cold_turkey_service)

    verification_service = WindowsVerificationService(
        logger=logger,
        cold_turkey_service=cold_turkey_service, # Pass the singleton instance
        thread_service=thread_service,
        ui_service=ui_service, # Pass the singleton instance
        config_repository=config_repo
    )
    container.register_instance(IVerificationService, verification_service)

    lockout_service = WindowsLockoutService(
        logger=logger,
        config_repository=config_repo,
        platform_detection_service=platform_detection_service, # Pass the singleton instance
        window_manager=window_manager,
        ui_service=ui_service, # Pass the singleton instance
        cold_turkey_service=cold_turkey_service, # Pass the singleton instance
        thread_service=thread_service
    )
    container.register_instance(ILockoutService, lockout_service)

    monitoring_service = MonitoringService(
        screenshot_service=screenshot_service, # Pass the singleton instance
        ocr_service=ocr_service,
        thread_service=thread_service,
        platform_detection_service=platform_detection_service, # Pass the singleton instance
        config_repository=config_repo,
        path_service=path_service,
        logger=logger,
        profile_service=profile_service, # Pass the singleton instance
        region_service=region_service # Pass the singleton instance
    )
    container.register_instance(IMonitoringService, monitoring_service)

    flash_service = QtFlashService(
        logger=logger,
        platform_detection=platform_detection_service, # Pass the singleton instance
        region_service=region_service, # Pass the singleton instance
        ui_service=ui_service, # Pass the singleton instance
        thread_service=thread_service
    )
    container.register_instance(IFlashService, flash_service)

    # --- End of Singleton Instances ---

    logger.info("Application dependencies initialized (using singletons where appropriate)")
    return container


# --- Keep get_container() as is ---
_container: Optional[DIContainer] = None

def get_container() -> DIContainer:
    """Gets the singleton DI container, initializing it if necessary."""
    global _container
    if _container is None:
        _container = initialize_app()
    return _container