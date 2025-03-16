# NewLayout/src/application/app.py (Modified)
import os
import logging
from typing import Optional

from src.domain.common.di_container import DIContainer
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_background_task_service import IBackgroundTaskService
from src.domain.services.i_config_repository_service import IConfigRepository
from src.domain.services.i_platform_detection_service import IPlatformDetectionService

from src.infrastructure.logging.logger_service import ConsoleLoggerService
from src.infrastructure.threading.qt_background_task_service import QtBackgroundTaskService
from src.infrastructure.config.json_config_repository import JsonConfigRepository
from src.infrastructure.platform.windows_platform_detection_service import WindowsPlatformDetectionService
from src.domain.services.i_screenshot_service import IScreenshotService
from src.infrastructure.platform.screenshot_service import QtScreenshotService
from src.domain.services.i_ocr_service import IOcrService
from src.infrastructure.ocr.tesseract_ocr_service import TesseractOcrService
from src.domain.services.i_monitoring_service import IMonitoringService
from src.infrastructure.platform.monitoring_service import MonitoringService
from src.domain.services.i_lockout_service import ILockoutService
from src.infrastructure.platform.lockout_service import WindowsLockoutService
from src.domain.services.i_verification_service import IVerificationService
from src.infrastructure.platform.verification_service import WindowsVerificationService
from src.domain.services.i_window_manager_service import IWindowManager
from src.infrastructure.platform.window_manager import WindowsWindowManager

def initialize_app() -> DIContainer:
    container = DIContainer()

    logger = ConsoleLoggerService(level=logging.DEBUG)
    container.register_instance(ILoggerService, logger)

    config_file = os.path.join(os.getcwd(), "config.json")
    config_repo = JsonConfigRepository(config_file, logger)
    container.register_instance(IConfigRepository, config_repo)

    # --- Thread Service Setup (Simplified) ---
    thread_service = QtBackgroundTaskService(logger)
    container.register_instance(IBackgroundTaskService, thread_service)
    # --- End Thread Service Setup ---

    container.register_factory(IWindowManager,
                               lambda: WindowsWindowManager(container.resolve(ILoggerService)))
    container.register_factory(
        IScreenshotService,
        lambda: QtScreenshotService(container.resolve(ILoggerService))
    )
    container.register_factory(
        IOcrService,
        lambda: TesseractOcrService(container.resolve(ILoggerService))
    )
    container.register_factory(
        IPlatformDetectionService,
        lambda: WindowsPlatformDetectionService(
            logger=container.resolve(ILoggerService),
            window_manager=container.resolve(IWindowManager)
        )
    )
    container.register_factory(
        ILockoutService,
        lambda: WindowsLockoutService(
            logger=container.resolve(ILoggerService),
            config_repository=container.resolve(IConfigRepository),
            platform_detection_service=container.resolve(IPlatformDetectionService),
            thread_service=container.resolve(IBackgroundTaskService)
        )
    )
    container.register_factory(
        IMonitoringService,
        lambda: MonitoringService(
            screenshot_service=container.resolve(IScreenshotService),
            ocr_service=container.resolve(IOcrService),
            thread_service=container.resolve(IBackgroundTaskService),
            platform_detection_service=container.resolve(IPlatformDetectionService),
            config_repository=container.resolve(IConfigRepository),
            logger=container.resolve(ILoggerService)
        )
    )
    container.register_factory(
        IVerificationService,
        lambda: WindowsVerificationService(
            logger=container.resolve(ILoggerService),
            config_repository=container.resolve(IConfigRepository),
            thread_service = container.resolve(IBackgroundTaskService)
        )
    )
    logger.info("Application dependencies initialized")

    return container

_container: Optional[DIContainer] = None

def get_container() -> DIContainer:
    global _container
    if _container is None:
        _container = initialize_app()
    return _container