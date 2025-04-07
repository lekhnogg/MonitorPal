# src/domain/services/i_ocr_analysis_service.py

from abc import ABC, abstractmethod
from typing import Dict, List
from src.domain.common.result import Result
from src.domain.models.platform_profile import OcrProfile


class IOcrAnalysisService(ABC):
    """
    Interface for analyzing images to determine optimal OCR parameters.

    This service is responsible for analyzing images to determine optimal OCR settings
    and analyzing text to generate or improve regex patterns for value extraction.
    """

    @abstractmethod
    def detect_optimal_ocr_parameters(self, image_path: str) -> Result[OcrProfile]:
        """
        Analyze image to determine optimal OCR parameters.

        Args:
            image_path: Path to the image file to analyze

        Returns:
            Result containing an OCR profile with optimal parameters
        """
        pass


