from abc import ABC, abstractmethod
from typing import List, Callable


class IPlatformSelectionService(ABC):
    """Interface for managing platform selection throughout the application."""

    @abstractmethod
    def get_current_platform(self) -> str:
        """Get the currently selected platform."""
        pass

    @abstractmethod
    def set_current_platform(self, platform: str) -> None:
        """Set the current platform and notify all observers."""
        pass

    @abstractmethod
    def get_available_platforms(self) -> List[str]:
        """Get list of available platforms."""
        pass

    @abstractmethod
    def register_platform_change_listener(self, listener: Callable[[str], None]) -> None:
        """Register a listener to be notified of platform changes."""
        pass

    @abstractmethod
    def unregister_platform_change_listener(self, listener: Callable[[str], None]) -> None:
        """Unregister a platform change listener."""
        pass