#src/domain/services/i_ui_service.py

from abc import ABC, abstractmethod
from typing import Tuple, Optional
from src.domain.common.result import Result


class IUIService(ABC):
    """Interface for UI operations."""

    @abstractmethod
    def show_message(self, title: str, message: str, message_type: str = "info") -> Result[bool]:
        """
        Show a message dialog to the user.

        Args:
            title: Dialog title
            message: Message text
            message_type: Type of message ("info", "warning", "error", "question")

        Returns:
            Result indicating success or failure
        """
        pass

    @abstractmethod
    def show_confirmation(self, title: str, message: str) -> Result[bool]:
        """
        Show a confirmation dialog and return the user's choice.

        Args:
            title: Dialog title
            message: Message text

        Returns:
            Result containing True if confirmed, False if canceled
        """
        pass

    @abstractmethod
    def select_file(self, title: str, filter_pattern: str) -> Result[str]:
        """
        Show a file selection dialog.

        Args:
            title: Dialog title
            filter_pattern: File type filter pattern

        Returns:
            Result containing selected file path or empty string if canceled
        """
        pass

    @abstractmethod
    def select_screen_region(self, message: str) -> Result[Tuple[int, int, int, int]]:
        """
        Allow the user to select a region on the screen.

        Args:
            message: Instructions for the user

        Returns:
            Result containing region coordinates (x, y, width, height)
        """
        pass

    @abstractmethod
    def activate_application_window(self) -> Result[bool]:
        """
        Bring the main application window to the foreground.

        Returns:
            Result indicating success or failure
        """
        pass