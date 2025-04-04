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

    @abstractmethod
    def analyze_text_for_patterns(self, text: str, platform_name: str = None) -> Result[Dict[str, str]]:
        """
        Analyze text to detect optimal pattern structure.

        Args:
            text: Sample text to analyze
            platform_name: Optional platform name for platform-specific optimizations

        Returns:
            Result containing a dictionary of regex pattern names and patterns
        """
        pass

    @abstractmethod
    def suggest_pattern_improvements(self, text: str, existing_patterns: Dict[str, str]) -> Result[Dict[str, str]]:
        """
        Suggest improvements to existing patterns based on sample text.

        Args:
            text: Sample text to analyze
            existing_patterns: Dictionary of existing pattern names and patterns

        Returns:
            Result containing an updated dictionary of pattern names and patterns
        """
        pass

    @abstractmethod
    def test_pattern_extraction(self, text: str, patterns: Dict[str, str]) -> Result[List[float]]:
        """
        Test pattern extraction on sample text.

        Args:
            text: Text to test pattern extraction on
            patterns: Dictionary of pattern names and patterns

        Returns:
            Result containing a list of extracted values
        """
        pass

    @abstractmethod
    def get_default_patterns(self, platform_name: str) -> Dict[str, str]:
        """
        Get default regex patterns for a specific platform.

        Args:
            platform_name: Name of the platform

        Returns:
            Dictionary of default pattern names and patterns
        """
        pass
