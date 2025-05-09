#src/domain/services/i_ui_service.py

from abc import ABC, abstractmethod
from typing import Tuple, Optional, Any
from src.domain.common.result import Result



class IFlashOverlay(ABC):
    @abstractmethod
    def show(self): pass
    @abstractmethod
    def hide(self): pass
    @abstractmethod
    def destroy_overlay(self): pass

class IUIService(ABC):
    """Interface for UI operations."""

    @abstractmethod
    def show_message(self, title: str, message: str, message_type: str = "info") -> Result[bool]:
        """Show a message dialog to the user."""
        pass  # Implementation goes in concrete class

    @abstractmethod
    def show_confirmation(self, title: str, message: str) -> Result[bool]:
        """Show a confirmation dialog and return the user's choice."""
        pass

    @abstractmethod
    def select_file(self, title: str, filter_pattern: str) -> Result[str]:
        """Show a file selection dialog."""
        pass

    @abstractmethod
    def select_screen_region(self, message: str) -> Result[Tuple[int, int, int, int]]:
        """Allow the user to select a region on the screen."""
        pass

    @abstractmethod
    def activate_application_window(self) -> Result[bool]:
        """Bring the main application window to the foreground."""
        pass

    @abstractmethod
    def create_flash_overlay(self, coords: Tuple[int, int, int, int]) -> Result[IFlashOverlay]:
        """Creates a non-interactive overlay for flashing."""
        pass

    @abstractmethod
    def select_save_file(self, title: str, filter_pattern: str, default_filename: str = "") -> Result[Optional[str]]:
        pass