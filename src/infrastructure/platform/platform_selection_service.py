from typing import List, Callable, Set

from src.domain.services.i_platform_selection_service import IPlatformSelectionService
from src.domain.services.i_config_repository_service import IConfigRepository
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_platform_detection_service import IPlatformDetectionService


class PlatformSelectionService(IPlatformSelectionService):
    """Service for managing platform selection throughout the application."""

    def __init__(self,
                 config_repository: IConfigRepository,
                 logger: ILoggerService,
                 platform_detection_service: IPlatformDetectionService):
        """Initialize the platform selection service."""
        self.config_repository = config_repository
        self.logger = logger
        self.platform_detection_service = platform_detection_service
        self._listeners: Set[Callable[[str], None]] = set()

    def get_current_platform(self) -> str:
        """Get the currently selected platform."""
        return self.config_repository.get_current_platform()

    def set_current_platform(self, platform: str) -> None:
        """Set the current platform and notify all listeners."""
        current = self.get_current_platform()
        if platform != current:
            # Save to config
            self.config_repository.set_global_setting("current_platform", platform)
            self.logger.info(f"Current platform changed to: {platform}")

            # Notify all listeners
            for listener in self._listeners:
                try:
                    listener(platform)
                except Exception as e:
                    self.logger.error(f"Error notifying platform change listener: {e}")

    def get_available_platforms(self) -> List[str]:
        """Get list of available platforms."""
        result = self.platform_detection_service.get_supported_platforms()
        if result.is_success:
            return list(result.value.keys())
        return []

    def register_platform_change_listener(self, listener: Callable[[str], None]) -> None:
        """Register a listener to be notified of platform changes."""
        self._listeners.add(listener)

    def unregister_platform_change_listener(self, listener: Callable[[str], None]) -> None:
        """Unregister a platform change listener."""
        if listener in self._listeners:
            self._listeners.remove(listener)