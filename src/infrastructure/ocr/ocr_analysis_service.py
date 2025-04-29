# src/infrastructure/ocr/ocr_analysis_service.py

import os
import re
import cv2
import numpy as np
from typing import Dict, List, Optional
from PIL import Image

from src.domain.services.i_ocr_analysis_service import IOcrAnalysisService
from src.domain.services.i_logger_service import ILoggerService
from src.domain.models.platform_profile import OcrProfile
from src.domain.common.result import Result
from src.domain.common.errors import ConfigurationError


class OcrAnalysisService(IOcrAnalysisService):
    """Implementation of the OCR analysis service."""

    def __init__(self, logger: ILoggerService):
        """
        Initialize the OCR analysis service.

        Args:
            logger: Logger service for logging
        """
        self.logger = logger

    def get_default_patterns(self, platform_name: Optional[str] = None) -> Dict[str, str]:
        """
        Provides a default set of numeric extraction regex patterns.
        Currently returns the same default for all platforms.

        Args:
            platform_name: Optional platform name (currently unused, but keeps signature)

        Returns:
            A dictionary of default regex patterns.
        """
        self.logger.debug(f"Providing default numeric patterns (Platform context: {platform_name or 'N/A'})")
        # This is the same default pattern set used in PlatformProfile.__post_init__
        # Having it here centralizes it if needed elsewhere or for future customization.
        return {
            "dollar": r'[$§]?([\d,]+(?:[.,]\d+)?)',  # Matches optional $, §, then digits/commas, optional decimal part
            "negative": r'\((?:[$§]?)([\d,]+(?:[.,]\d+)?)\)',  # Matches (optional $), digits/commas/decimal, )
            "negative_dash": r'[-~–—]\s*[$§]?([\d,]+(?:[.,]\d+)?)',
            # Matches dash/tilde, optional space/currency, digits/commas/decimal
            "regular": r'(?<![$§])([-~–—]?[\d,]+(?:[.,]\d+)?)'
            # Matches optional dash/tilde, digits/commas/decimal ONLY if NOT preceded by $ or §
        }

    def detect_optimal_ocr_parameters(self, image_path: str) -> Result[OcrProfile]:
        """Detect optimal OCR parameters from an image."""
        try:
            if not os.path.exists(image_path):
                return Result.fail(ConfigurationError(
                    message=f"Image file not found: {image_path}"
                ))

            # Load the image
            try:
                image = Image.open(image_path)
                # Convert to numpy array for OpenCV processing
                np_image = np.array(image)
            except Exception as e:
                return Result.fail(ConfigurationError(
                    message=f"Failed to load image: {e}",
                    inner_error=e
                ))

            # Create a new profile with detected parameters
            ocr_profile = OcrProfile()

            # Detect inversion (light text on dark background or vice versa)
            ocr_profile.invert_colors = self._detect_inversion_needed(np_image)

            # Detect optimal scale factor
            ocr_profile.scale_factor = self._detect_optimal_scale(np_image)

            # Detect optimal threshold parameters
            threshold_params = self._detect_optimal_threshold(np_image)
            ocr_profile.threshold_block_size = threshold_params["block_size"]
            ocr_profile.threshold_c = threshold_params["c"]

            # Detect optimal denoise parameters
            denoise_params = self._detect_optimal_denoise(np_image)
            ocr_profile.denoise_h = denoise_params["h"]
            ocr_profile.denoise_template_window_size = denoise_params["template_window_size"]
            ocr_profile.denoise_search_window_size = denoise_params["search_window_size"]

            # Set optimal tesseract config based on image characteristics
            ocr_profile.tesseract_config = self._detect_optimal_tesseract_config(np_image)

            self.logger.info(f"Successfully auto-detected OCR parameters")
            return Result.ok(ocr_profile)

        except Exception as e:
            self.logger.error(f"Error detecting OCR parameters: {e}")
            return Result.fail(ConfigurationError(
                message="Failed to detect OCR parameters",
                inner_error=e
            ))

    def _detect_inversion_needed(self, image: np.ndarray) -> bool:
        """Detect if image has light text on dark background."""
        # Convert to grayscale if it's not already
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # Calculate mean brightness
        mean_brightness = np.mean(gray)

        # If the image is primarily dark (mean < 128), it likely has light text on dark background
        return mean_brightness < 128

    def _detect_optimal_scale(self, image: np.ndarray) -> float:
        """Detect optimal scale factor based on image characteristics."""
        # Estimate text size - use image height as a heuristic
        height = image.shape[0]

        # Very small regions (likely small text) need higher scaling
        if height < 30:
            return 3.0
        # Small regions
        elif height < 50:
            return 2.5
        # Medium regions
        elif height < 100:
            return 2.0
        # Large regions
        else:
            return 1.5

    def _detect_optimal_threshold(self, image: np.ndarray) -> dict:
        """Detect optimal threshold parameters for the image."""
        # Convert to grayscale if it's not already
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # Calculate standard deviation to estimate contrast and noise
        std_dev = np.std(gray)

        # Determine block size (must be odd)
        # For low-contrast images, use larger block size
        if std_dev < 40:
            block_size = 15
        elif std_dev < 70:
            block_size = 11
        else:
            block_size = 9

        # Ensure block size is odd
        if block_size % 2 == 0:
            block_size += 1

        # Determine C value based on contrast
        # For low-contrast images, use higher C
        if std_dev < 40:
            c_value = 4
        elif std_dev < 70:
            c_value = 3
        else:
            c_value = 2

        return {
            "block_size": block_size,
            "c": c_value
        }

    def _detect_optimal_denoise(self, image: np.ndarray) -> dict:
        """Detect optimal denoise parameters for the image."""
        # Convert to grayscale if it's not already
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # Calculate standard deviation to estimate image noise
        std_dev = np.std(gray)

        # Determine h parameter for denoising
        # Higher h for noisier images
        if std_dev < 40:  # Low noise
            h = 7
        elif std_dev < 70:  # Medium noise
            h = 10
        else:  # High noise
            h = 13

        # Set template window size
        template_window_size = 7  # Default value

        # Set search window size
        search_window_size = 21  # Default value

        return {
            "h": h,
            "template_window_size": template_window_size,
            "search_window_size": search_window_size
        }

    def _detect_optimal_tesseract_config(self, image: np.ndarray) -> str:
        """Determine optimal tesseract configuration."""
        # Basic config
        config = '--oem 3'  # Use LSTM OCR Engine

        # Determine PSM (Page Segmentation Mode) based on image characteristics
        height, width = image.shape[:2]

        # Detect if image is likely to be a single line or multiple lines
        aspect_ratio = width / height

        if aspect_ratio > 7:  # Very wide and short - likely single line
            config += ' --psm 7'  # Treat image as single line of text
        elif aspect_ratio > 3:  # Wide but not extremely - likely single line
            config += ' --psm 7'  # Treat image as single line of text
        else:  # More square-ish - could be multiple lines
            config += ' --psm 6'  # Assume a block of text

        return config

