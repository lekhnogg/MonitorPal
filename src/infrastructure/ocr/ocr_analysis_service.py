# src/infrastructure/ocr/ocr_analysis_service.py

import os
import re
import cv2
import numpy as np
from typing import Dict, List
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

# --------------- REGEX PATTERN LOGIC ------------

    def analyze_text_for_patterns(self, text: str, platform_name: str = None) -> Result[Dict[str, str]]:
        """Analyze text to detect optimal pattern structure."""
        try:
            # Start with base patterns that work for most platforms
            patterns = self.get_default_patterns(platform_name if platform_name else "Default")

            # Check for specific formats in the text
            if text:
                # Look for currency symbols
                if '€' in text:
                    patterns["euro"] = r'€([\d,]+\.?\d*)'
                if '£' in text:
                    patterns["pound"] = r'£([\d,]+\.?\d*)'
                if '¥' in text:
                    patterns["yen"] = r'¥([\d,]+\.?\d*)'

                # Look for specific P&L text patterns
                if "PNL" in text or "P&L" in text:
                    patterns["pnl_label"] = r'P(?:&|NL)[:\s]+([-\d.,]+)'

                # Look for percentage values
                if '%' in text:
                    patterns["percentage"] = r'([-\d.,]+)%'

            self.logger.info(f"Generated patterns from text analysis")
            return Result.ok(patterns)

        except Exception as e:
            self.logger.error(f"Error analyzing text for patterns: {e}")
            return Result.fail(ConfigurationError(
                message="Failed to analyze text for patterns",
                inner_error=e
            ))

    def suggest_pattern_improvements(self, text: str, existing_patterns: Dict[str, str]) -> Result[Dict[str, str]]:
        """Suggest improvements to existing patterns based on sample text."""
        try:
            # Start with existing patterns
            improved_patterns = existing_patterns.copy()

            # Extract values with existing patterns to see what's missing
            all_extractions = []
            for pattern_name, pattern in existing_patterns.items():
                matches = re.findall(pattern, text)
                all_extractions.extend(matches)

            # Look for numeric sequences not captured by existing patterns
            uncaptured = []
            for match in re.finditer(r'[-\d.,]+', text):
                if not any(match.group() in extraction for extraction in all_extractions):
                    uncaptured.append(match.group())

            # If we found uncaptured values, suggest new patterns
            if uncaptured:
                # Analyze the context of uncaptured values
                for value in uncaptured:
                    # Find position in text
                    pos = text.find(value)
                    if pos > 0:
                        # Look at preceding character for context
                        prefix = text[pos - 1]
                        if prefix not in '0123456789.,()-+$€£¥ ':
                            # This might be a new identifier - add a pattern
                            pattern_name = f"context_{prefix}"
                            improved_patterns[pattern_name] = f'\\{prefix}([-\\d.,]+)'

            return Result.ok(improved_patterns)

        except Exception as e:
            self.logger.error(f"Error suggesting pattern improvements: {e}")
            return Result.fail(ConfigurationError(
                message="Failed to suggest pattern improvements",
                inner_error=e
            ))

    def test_pattern_extraction(self, text: str, patterns: Dict[str, str]) -> Result[List[float]]:
        """Test pattern extraction on sample text."""
        try:
            values = []
            seen_values = set()  # To track unique values

            # Determine which pattern to use
            pattern_to_use = None
            if "custom" in patterns:
                pattern_to_use = patterns["custom"]
            elif "standard" in patterns:
                pattern_to_use = patterns["standard"]

            if pattern_to_use:
                # Use the single pattern approach
                for match in re.finditer(pattern_to_use, text):
                    # Get all groups
                    groups = match.groups()

                    # Find the first non-None group (the actual captured number)
                    value_str = None
                    for group in groups:
                        if group is not None:
                            value_str = group
                            break

                    if value_str:
                        try:
                            # Clean up the string
                            clean_value = value_str.replace(',', '')

                            # Determine if this is a negative value
                            full_match = match.group(0)
                            is_negative = full_match.startswith('-') or full_match.startswith('(')

                            # Convert to a float
                            value = float(clean_value)

                            # Make negative if needed
                            if is_negative and value > 0:
                                value = -value

                            # Only add unique values
                            rounded = round(value, 2)
                            if rounded not in seen_values:
                                seen_values.add(rounded)
                                values.append(value)
                                self.logger.debug(f"Extracted {value} using pattern")
                        except (ValueError, TypeError):
                            # Skip if we can't convert to float
                            continue
            else:
                # No custom or standard pattern found, log warning
                self.logger.warning("No valid pattern found for extraction")

            return Result.ok(values)
        except Exception as e:
            self.logger.error(f"Error testing pattern extraction: {e}")
            return Result.fail(ConfigurationError(
                message="Failed to test pattern extraction",
                inner_error=e
            ))

    def get_default_patterns(self, platform_name: str) -> Dict[str, str]:
        """Get default regex patterns for a specific platform."""
        # Base patterns shared across platforms
        patterns = {
            "dollar": r'\$([\d,]+\.?\d*)',
            "negative": r'\((?:\$)?([\d,]+\.?\d*)\)',
            "negative_dash": r'[-~]\$?([\d,]+\.?\d*)',  # Include tilde as possible minus sign
            "regular": r'(?<!\$)(-?[\d,]+\.?\d*)'
        }

        # Add platform-specific patterns
        if platform_name == "NinjaTrader":
            patterns["ninja_at"] = r'@\s*([-~\d.,]+)'  # Include tilde here too
        elif platform_name == "TradingView":
            patterns["pnl_label"] = r'PNL[:\s]+([-~\d.,]+)'  # And here

        return patterns