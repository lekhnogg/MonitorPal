# src/domain/services/i_screenshot_service.py

"""
Screenshot service interface for capturing and managing screenshots.

Defines the contract for screenshot services in the application.
"""
from abc import ABC, abstractmethod
from typing import Tuple, Any

from src.domain.common.result import Result


class IScreenshotService(ABC):
    """
    Interface for screenshot services.

    Defines methods for capturing, saving, and converting screenshots.
    """

    @abstractmethod
    def capture_region(self, region: Tuple[int, int, int, int]) -> Result[Any]:
        """
        Capture a screenshot of a specific region.

        Args:
            region: (left, top, width, height) of screen region to capture

        Returns:
            Result containing the captured image on success
        """
        pass

    @abstractmethod
    def save_screenshot(self, image: Any, path: str) -> Result[str]:
        """
        Save a screenshot to disk.

        Args:
            image: Screenshot image to save
            path: Path where to save the screenshot

        Returns:
            Result containing the saved file path on success
        """
        pass

    @abstractmethod
    def capture_and_save(self, region: Tuple[int, int, int, int], path: str) -> Result[str]:
        """
        Capture a screenshot of a region and save it to disk.

        Args:
            region: (left, top, width, height) of screen region to capture
            path: Path where to save the screenshot

        Returns:
            Result containing the saved file path on success
        """
        pass

    @abstractmethod
    def to_pyside_pixmap(self, image: Any) -> Result[Any]:
        """
        Convert an image to a PySide6 QPixmap.

        Args:
            image: Image to convert

        Returns:
            Result containing the QPixmap on success
        """
        pass

    @abstractmethod
    def to_bytes(self, image: Any) -> Result[bytes]:
        """
        Convert an image to bytes.

        Args:
            image: Image to convert

        Returns:
            Result containing the image bytes on success
        """
        pass