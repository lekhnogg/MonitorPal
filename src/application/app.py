#src/domain/common/di_container.py

import os
import logging
from typing import Optional

from src.domain.common.di_container import DIContainer
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_background_task_service import IBackgroundTaskService
from src.domain.services.i_config_repository_service import IConfigRepository
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

from src.infrastructure.logging.logger_service import ConsoleLoggerService
from src.infrastructure.threading.qt_background_task_service import QtBackgroundTaskService
from src.infrastructure.config.json_config_repository import JsonConfigRepository
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
def initialize_app() -> DIContainer:
    container = DIContainer()

    # Core services
    logger = ConsoleLoggerService(level=logging.DEBUG)
    container.register_instance(ILoggerService, logger)

    config_file = os.path.join(os.getcwd(), "config.json")
    config_repo = JsonConfigRepository(config_file, logger)
    container.register_instance(IConfigRepository, config_repo)

    thread_service = QtBackgroundTaskService(logger)
    container.register_instance(IBackgroundTaskService, thread_service)

    # Window management and UI services
    container.register_factory(
        IWindowManager,
        lambda: WindowsWindowManager(container.resolve(ILoggerService))
    )

    container.register_factory(
        IUIService,
        lambda: QtUIService(container.resolve(ILoggerService))
    )

    # Platform services
    container.register_factory(
        IScreenshotService,
        lambda: QtScreenshotService(container.resolve(ILoggerService))
    )

    container.register_factory(
        IOcrService,
        lambda: TesseractOcrService(container.resolve(ILoggerService))
    )


    container.register_factory(
        IPlatformSelectionService,
        lambda: PlatformSelectionService(
            config_repository=container.resolve(IConfigRepository),
            logger=container.resolve(ILoggerService),
            platform_detection_service=container.resolve(IPlatformDetectionService)
        )
    )

    container.register_factory(
        IProfileService,
        lambda: ProfileService(
            config_repository=container.resolve(IConfigRepository),
            logger=container.resolve(ILoggerService)
        )
    )

    container.register_factory(
        IPlatformDetectionService,
        lambda: WindowsPlatformDetectionService(
            logger=container.resolve(ILoggerService),
            window_manager=container.resolve(IWindowManager)
        )
    )

    # Cold Turkey integration - register this first
    container.register_factory(
        IColdTurkeyService,
        lambda: WindowsColdTurkeyService(
            logger=container.resolve(ILoggerService),
            config_repository=container.resolve(IConfigRepository),
            window_manager=container.resolve(IWindowManager)
        )
    )

    # Verification service - now depends on Cold Turkey service
    container.register_factory(
        IVerificationService,
        lambda: WindowsVerificationService(
            logger=container.resolve(ILoggerService),
            cold_turkey_service=container.resolve(IColdTurkeyService),
            thread_service=container.resolve(IBackgroundTaskService),
            ui_service=container.resolve(IUIService)  # <-- Add this parameter
        )
    )

    # Core application services
    container.register_factory(
        ILockoutService,
        lambda: WindowsLockoutService(
            logger=container.resolve(ILoggerService),
            config_repository=container.resolve(IConfigRepository),
            platform_detection_service=container.resolve(IPlatformDetectionService),
            window_manager=container.resolve(IWindowManager),
            ui_service=container.resolve(IUIService),
            cold_turkey_service=container.resolve(IColdTurkeyService),
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
            logger=container.resolve(ILoggerService),
            profile_service = container.resolve(IProfileService)
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