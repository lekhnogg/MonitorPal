# src/domain/services/i_ocr_service.py

"""
OCR service interface for extracting text from images.

Defines the contract for OCR services in the application.
"""
from abc import ABC, abstractmethod
from typing import Any, List

from src.domain.common.result import Result


class IOcrService(ABC):
    """
    Interface for OCR (Optical Character Recognition) services.

    Defines methods for extracting and processing text from images.
    """

    @abstractmethod
    def extract_text(self, image: Any) -> Result[str]:
        """
        Extract text from an image.

        Args:
            image: The image to process (PIL Image or similar)

        Returns:
            Result containing extracted text on success
        """
        pass

    @abstractmethod
    def extract_text_from_file(self, image_path: str) -> Result[str]:
        """
        Extract text from an image file.

        Args:
            image_path: Path to the image file

        Returns:
            Result containing extracted text on success
        """
        pass

    @abstractmethod
    def preprocess_image(self, image: Any) -> Result[Any]:
        """
        Preprocess an image to improve OCR accuracy.

        Args:
            image: The image to preprocess

        Returns:
            Result containing the preprocessed image on success
        """
        pass

    @abstractmethod
    def extract_numeric_values(self, text: str) -> Result[List[float]]:
        """
        Extract numeric values from text.

        Handles various formats including dollar amounts, percentages, etc.

        Args:
            text: The text to process

        Returns:
            Result containing a list of extracted numeric values on success
        """
        pass