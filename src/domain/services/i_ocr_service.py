#src/domain/services/i_ocr_service.py

"""
OCR service interface for extracting text from images.

Defines the contract for OCR services in the application.
"""
from abc import ABC, abstractmethod
from typing import Any, List, Dict

from src.domain.common.result import Result
from src.domain.models.platform_profile import OcrProfile

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

    @abstractmethod
    def extract_text_with_profile(self, image: Any, profile: OcrProfile) -> Result[str]:
        """
        Extract text from an image using specific OCR profile.

        This is the primary method for text extraction that should be used
        whenever a platform-specific extraction is needed.

        Args:
            image: The image to process
            profile: OCR profile with processing parameters

        Returns:
            Result containing extracted text
        """
        pass

    @abstractmethod
    def extract_numeric_values_with_patterns(self, text: str, patterns: Dict[str, str]) -> Result[List[float]]:
        """
        Extract numeric values using custom regex patterns.

        Args:
            text: The text to process
            patterns: Dictionary of named regex patterns

        Returns:
            Result containing list of extracted values
        """
        pass