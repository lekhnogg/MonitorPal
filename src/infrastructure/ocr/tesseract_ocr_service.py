#src/infrastructure/ocr/tesseract_ocr_service.py

"""
Implementation of the OCR service using Tesseract OCR.
"""
import os
import re
import sys
import cv2
import numpy as np
from typing import List, Dict
from PIL import Image, ImageEnhance

# Import Tesseract binding
import pytesseract

from src.domain.services.i_ocr_service import IOcrService
from src.domain.services.i_logger_service import ILoggerService
from src.domain.common.result import Result
from src.domain.common.errors import ResourceError
from src.domain.models.platform_profile import OcrProfile

class TesseractOcrService(IOcrService):
    """
    Implementation of the OCR service using Tesseract OCR.

    This service processes images using Tesseract OCR to extract text
    and numeric values.
    """

    def __init__(self, logger: ILoggerService):
        """
        Initialize the OCR service.

        Args:
            logger: Logger service for logging
        """
        self.logger = logger

        # Configure Tesseract path
        self._configure_tesseract_path()

    def _configure_tesseract_path(self) -> None:
        """
        Configure the Tesseract path based on the environment.

        Follows similar logic to the original implementation but with improved error handling.
        """
        try:
            # Check if running as compiled executable (PyInstaller)
            if getattr(sys, 'frozen', False):
                base_path = sys._MEIPASS  # PyInstaller creates a temp folder and stores path in _MEIPASS
                tesseract_path = os.path.join(base_path, "resources", "Tesseract-OCR", "tesseract.exe")
                pytesseract.pytesseract.tesseract_cmd = tesseract_path
                self.logger.info(f"Configured Tesseract path for executable: {tesseract_path}")
            else:
                # Running as script - try multiple common installation locations
                possible_paths = [
                    r'C:\Program Files\Tesseract-OCR\tesseract.exe',
                    r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
                    r'C:\Users\Gabe\AppData\Local\Programs\Tesseract-OCR\tesseract.exe',
                    r'/usr/bin/tesseract',  # Linux
                    r'/usr/local/bin/tesseract',  # macOS
                    # Add more common paths if needed
                ]

                for path in possible_paths:
                    if os.path.exists(path):
                        pytesseract.pytesseract.tesseract_cmd = path
                        self.logger.info(f"Configured Tesseract path: {path}")
                        return

                # If no path found, log warning but continue
                # (pytesseract will use system default if available)
                self.logger.warning("Tesseract OCR not found in common locations. " +
                                    "Please install Tesseract or configure the path manually.")
        except Exception as e:
            # Log error but continue - may still work if Tesseract is in PATH
            self.logger.error(f"Error configuring Tesseract path: {e}")

    def extract_text(self, image: Image.Image) -> Result[str]:
        """
        Legacy method - now uses default profile.

        For better results, use extract_text_with_profile directly.
        """
        # Create a default profile
        default_profile = OcrProfile()

        # Use the profile-based method
        return self.extract_text_with_profile(image, default_profile)

    def extract_text_from_file(self, image_path: str) -> Result[str]:
        """
        Extract text from an image file using default profile.

        For better results, load the file and use extract_text_with_profile with
        a platform-specific profile.
        """
        try:
            self.logger.debug(f"Extracting text from file: {image_path}")

            # Check if file exists
            if not os.path.exists(image_path):
                return Result.fail(f"Image file not found: {image_path}")

            # Open the image
            try:
                image = Image.open(image_path)
            except Exception as e:
                return Result.fail(f"Failed to open image file: {str(e)}")

            # Extract using default profile
            default_profile = OcrProfile()
            return self.extract_text_with_profile(image, default_profile)

        except Exception as e:
            error_msg = f"Text extraction from file failed: {str(e)}"
            self.logger.error(error_msg)
            return Result.fail(error_msg)

    def preprocess_image(self, image: Image.Image) -> Result[Image.Image]:
        """
        Legacy method - now uses default profile.

        For better results, use _preprocess_with_profile directly.
        """
        default_profile = OcrProfile()
        return self._preprocess_with_profile(image, default_profile)

    def extract_numeric_values(self, text: str) -> Result[List[float]]:
        """
        Legacy method for extracting numeric values.

        For better results, use extract_numeric_values_with_patterns with
        platform-specific patterns.
        """
        # Create default patterns
        default_patterns = {
            "dollar": r'\$([\d,]+\.?\d*)',
            "negative": r'\((?:\$)?([\d,]+\.?\d*)\)',
            "negative_dash": r'-\$?([\d,]+\.?\d*)',
            "regular": r'(?<!\$)(-?[\d,]+\.?\d*)'
        }

        # Use the pattern-based method
        return self.extract_numeric_values_with_patterns(text, default_patterns)

    def extract_text_with_profile(self, image: Image.Image, profile: OcrProfile) -> Result[str]:
        """Extract text from an image using a specific OCR profile."""
        try:
            self.logger.debug("Extracting text with custom profile")

            # Preprocess with profile parameters
            preprocess_result = self._preprocess_with_profile(image, profile)
            if preprocess_result.is_failure:
                return Result.fail(preprocess_result.error)

            processed_image = preprocess_result.value

            # Use profile's tesseract config
            custom_config = profile.tesseract_config

            # Perform OCR
            extracted_text = pytesseract.image_to_string(processed_image, config=custom_config)
            extracted_text = extracted_text.strip()

            self.logger.debug(
                f"Extracted text with profile: {extracted_text[:100]}" + ("..." if len(extracted_text) > 100 else ""))
            return Result.ok(extracted_text)
        except FileNotFoundError as e:
            error = ResourceError(
                message="Tesseract OCR executable not found",
                inner_error=e
            )
            self.logger.error(str(error))
            return Result.fail(error)
        except Exception as e:
            error = ResourceError(
                message="Text extraction with profile failed",
                details={"image_size": f"{image.width}x{image.height}" if hasattr(image, 'width') else "unknown"},
                inner_error=e
            )
            self.logger.error(str(error))
            return Result.fail(error)

    def _preprocess_with_profile(self, image: Image.Image, profile: OcrProfile) -> Result[Image.Image]:
        """Preprocess an image using profile parameters with improved handling for colored text."""
        try:
            self.logger.debug("Preprocessing image with profile parameters")

            # Convert to numpy
            img_np = np.array(image)

            # Check if the image is color (has 3 channels)
            is_color = len(img_np.shape) == 3 and img_np.shape[2] >= 3

            # Special handling for red text on dark background
            if is_color:
                # Calculate channel averages to detect dominant colors
                r_avg = np.mean(img_np[:, :, 0])
                g_avg = np.mean(img_np[:, :, 1])
                b_avg = np.mean(img_np[:, :, 2])

                # Check if red is the dominant color (red higher than other channels)
                is_red_dominant = r_avg > g_avg * 1.5 and r_avg > b_avg * 1.5

                # Check if background is dark
                brightness = (r_avg + g_avg + b_avg) / 3
                is_dark_bg = brightness < 128

                # For red text on dark background, use red channel with enhanced contrast
                if is_red_dominant and is_dark_bg:
                    self.logger.debug("Detected red text on dark background, applying special processing")

                    # Extract just the red channel
                    red_channel = img_np[:, :, 0].copy()

                    # Apply contrast enhancement to the red channel
                    # Stretch the histogram to improve contrast
                    min_val = np.percentile(red_channel, 5)  # 5th percentile for black level
                    max_val = np.percentile(red_channel, 95)  # 95th percentile for white level

                    # Ensure we don't divide by zero
                    if max_val > min_val:
                        # Stretch the histogram
                        red_channel = np.clip((red_channel - min_val) * (255.0 / (max_val - min_val)), 0, 255).astype(
                            np.uint8)

                    # Apply morphological operations to enhance thin lines (like - and $)
                    kernel = np.ones((2, 2), np.uint8)
                    red_channel = cv2.dilate(red_channel, kernel, iterations=1)

                    # Set this as our grayscale image
                    img_gray = red_channel

                    # Force inversion for this case, since we're looking for red text
                    img_gray = cv2.bitwise_not(img_gray)

                    # Skip the standard inversion logic below since we've handled it
                    skip_standard_inversion = True
                else:
                    # Standard grayscale conversion for non-red-text cases
                    img_gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
                    skip_standard_inversion = False
            else:
                # Non-color image, use as is
                img_gray = img_np
                skip_standard_inversion = False

            # Apply color inversion if specified in profile and not already handled
            if profile.invert_colors and not skip_standard_inversion:
                self.logger.debug("Inverting image colors")
                img_gray = cv2.bitwise_not(img_gray)

            # Apply profile parameters
            h, w = img_gray.shape
            img_resized = cv2.resize(
                img_gray,
                (int(w * profile.scale_factor), int(h * profile.scale_factor)),
                interpolation=cv2.INTER_CUBIC
            )

            # For better OCR of financial symbols, we need to adjust the threshold parameters
            threshold_block_size = profile.threshold_block_size
            threshold_c = profile.threshold_c

            # Ensure block size is odd
            if threshold_block_size % 2 == 0:
                threshold_block_size += 1

            img_thresh = cv2.adaptiveThreshold(
                img_resized,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                threshold_block_size,
                threshold_c
            )

            # Apply less aggressive denoising to preserve thin lines
            reduced_h = max(5, profile.denoise_h // 2)  # Reduce strength of denoising
            img_denoised = cv2.fastNlMeansDenoising(
                img_thresh,
                None,
                reduced_h,
                profile.denoise_template_window_size,
                profile.denoise_search_window_size
            )

            # Convert back to PIL Image
            processed_image = Image.fromarray(img_denoised)
            return Result.ok(processed_image)

        except Exception as e:
            error = ResourceError(
                message="Image preprocessing with profile failed",
                details={"image_size": f"{image.width}x{image.height}" if hasattr(image, 'width') else "unknown"},
                inner_error=e
            )
            self.logger.error(str(error))
            return Result.fail(error)

    def extract_numeric_values_with_patterns(self, text: str, patterns: Dict[str, str]) -> Result[List[float]]:
        """Extract numeric values from text using custom regex patterns."""
        try:
            self.logger.debug("Extracting numeric values with custom patterns")

            # Preprocessing - replace common OCR errors
            text = text.replace(';', '.')  # Replace semicolons with periods (common OCR error)

            # CRITICAL: Always treat tilde as negative sign
            text = text.replace('~', '-')  # Replace tilde with minus sign

            # List to store extracted values
            values = []

            # Process each pattern
            for pattern_name, pattern in patterns.items():
                self.logger.debug(f"Processing pattern '{pattern_name}': {pattern}")

                matches = re.findall(pattern, text)
                for match in matches:
                    try:
                        # Remove commas and convert to float
                        clean_value = match.replace(',', '')

                        # Handle negative values in patterns
                        if pattern_name == "negative":
                            value = -float(clean_value)
                        elif pattern_name == "negative_dash" or pattern_name == "minus_dollar":
                            value = -float(clean_value)
                        else:
                            value = float(clean_value)

                        values.append(value)
                        self.logger.debug(f"Extracted value: {value} from match: {match}")
                    except ValueError:
                        self.logger.debug(f"Failed to convert match to float: {match}")
                        continue

            # Apply the same post-processing logic as in the original method
            if len(values) > 1 and not any('$' in text for _ in text):
                # Check for cases like "96062.0, 50.0" which should be "96062.50"
                reconstructed = False
                for i in range(len(values) - 1):
                    v1_str = str(values[i])
                    v2_str = str(values[i + 1])
                    # If v1 is a whole number and v2 is a small decimal
                    if v1_str.endswith('.0') and 0 < values[i + 1] < 1:
                        try:
                            # Reconstruct like "96062" + ".50"
                            full_value = float(v1_str[:-2] + '.' + v2_str.split('.')[-1])
                            values = [full_value]  # Replace with the reconstructed value
                            reconstructed = True
                            break
                        except:
                            pass

                # If no reconstruction worked, look for decimal fragments
                if not reconstructed:
                    # If we have values like [96062.0, 50.0], try to see if they should be 96062.50
                    for i in range(len(values)):
                        if i < len(values) - 1 and values[i] > 100 and values[i + 1] < 100:
                            # This might be a split decimal - check the original text
                            # to see if they appear next to each other
                            v1_pos = text.find(str(int(values[i])))
                            v2_pos = text.find(str(int(values[i + 1])))
                            if v1_pos != -1 and v2_pos != -1 and 0 < v2_pos - v1_pos < 20:
                                # They're close in the text, likely a split value
                                combined = float(f"{int(values[i])}.{int(values[i + 1])}")
                                values = [combined]
                                break

            self.logger.debug(f"Extracted numeric values with patterns: {values}")
            return Result.ok(values)

        except Exception as e:
            error_msg = f"Numeric value extraction with patterns failed: {str(e)}"
            self.logger.error(error_msg)
            return Result.fail(error_msg)