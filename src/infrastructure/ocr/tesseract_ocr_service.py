#src/infrastructure/ocr/tesseract_ocr_service.py

"""
Implementation of the OCR service using Tesseract OCR.
"""
import os
import re
import sys
import cv2
import numpy as np
from typing import List, Dict, Optional
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
        """Extract numeric values from text using custom regex patterns and robust cleaning."""
        try:
            self.logger.debug("Extracting numeric values with custom patterns")

            if not text:
                self.logger.debug("Input text is empty, cannot extract values.")
                return Result.ok([])

            # Preprocessing - replace common OCR errors NOT handled by regex/cleaning yet
            processed_text = text.replace(';', '.')  # Common Tesseract error
            processed_text = processed_text.replace(' ',
                                                    '')  # Remove spaces to help regex matching adjacent items sometimes

            self.logger.debug(f"Preprocessed text for pattern matching: '{processed_text[:100]}...'")

            # List to store extracted values and set to track unique rounded values
            extracted_values = []
            seen_rounded_values = set()

            # Process each pattern
            for pattern_name, pattern in patterns.items():
                self.logger.debug(f"Processing pattern '{pattern_name}': {pattern}")
                try:
                    # Use re.finditer to get match objects (includes full match context)
                    for match in re.finditer(pattern, processed_text):
                        full_match_text = match.group(0)  # Get the whole matched string
                        captured_group = None

                        # Find the primary captured group (usually the number part)
                        if match.groups():
                            # Iterate through captured groups, find the first non-None one
                            for group in match.groups():
                                if group is not None:
                                    captured_group = group
                                    break  # Use the first one found

                        if captured_group:
                            # Use the robust cleaning and conversion helper function
                            numeric_value = self._clean_and_convert_value(captured_group, full_match_text)

                            if numeric_value is not None:
                                # Check for uniqueness based on rounded value (e.g., 2 decimal places)
                                rounded = round(numeric_value, 2)
                                if rounded not in seen_rounded_values:
                                    extracted_values.append(numeric_value)
                                    seen_rounded_values.add(rounded)
                                    self.logger.debug(
                                        f"  Added value {numeric_value} (Rounded: {rounded}) using pattern '{pattern_name}' from match '{full_match_text}'")
                                # else: # Optional: Log if duplicate found
                                #    self.logger.debug(f"  Duplicate value {numeric_value} (Rounded: {rounded}) ignored.")
                        # else: # Optional: Log if pattern matched but captured no group
                        #    self.logger.debug(f"Pattern '{name}' matched '{full_match_text}' but captured no group (or group was None).")

                except re.error as e:
                    self.logger.error(f"Regex error processing pattern '{pattern_name}': {e}")
                except Exception as e:
                    self.logger.error(f"Unexpected error processing pattern '{pattern_name}': {e}", exc_info=True)

            # Remove the old post-processing logic here - it's less reliable than robust cleaning
            # OLD LOGIC REMOVED:
            # if len(values) > 1 and not any('$' in text for _ in text):
            #     ... (removed reconstruction logic) ...

            # Filter out potential outliers if needed? (Optional, complex)
            # E.g., if you extract [ -500.0, 1000000.0 ], the second might be noise.
            # This requires domain knowledge or statistical methods. Keep it simple for now.

            self.logger.debug(f"Final extracted numeric values: {extracted_values}")
            return Result.ok(extracted_values)

        except Exception as e:
            # Log general exceptions during the process
            error_msg = f"Numeric value extraction with patterns failed: {str(e)}"
            self.logger.error(error_msg, exc_info=True)  # Include stack trace
            return Result.fail(error_msg)

    def _clean_and_convert_value(self, value_str: str, full_match: str) -> Optional[float]:
        """
        Cleans the extracted string value and converts it to a float.
        Handles different signs, decimal separators, and thousands separators.
        """
        # Ensure value_str is a string, sometimes regex might capture non-strings if pattern is odd
        if not isinstance(value_str, str):
            self.logger.debug(f"Cleaning skipped: Captured group '{value_str}' is not a string.")
            return None
        if not value_str:
            self.logger.debug("Cleaning skipped: Input captured group is empty.")
            return None

        # Use the original full match for robust sign detection
        original_match_text = full_match.strip() if isinstance(full_match, str) else ""

        try:
            # 1. Detect sign from the *original full match* for robustness
            is_negative = original_match_text.startswith(('-', '~', '–', '—')) or \
                          (original_match_text.startswith('(') and original_match_text.endswith(')'))
            self.logger.debug(
                f"Cleaning captured group '{value_str}' from match '{original_match_text}'. Detected negative: {is_negative}")

            # 2. Initial cleanup: Remove known non-numeric noise
            # Includes currency, common symbols, whitespace. Add platform specifics if needed.
            noise_chars = r'[$§@\s]+'
            clean = re.sub(noise_chars, '', value_str.strip())
            # Also replace common misinterpretations if not handled by regex
            clean = clean.replace('l', '1').replace('O', '0').replace('S', '5').replace('B', '8')
            self.logger.debug(f"  After removing noise/misinterpretations: '{clean}'")

            # Handle edge case where cleaning leaves nothing
            if not clean:
                self.logger.debug("  Cleaning resulted in empty string.")
                return None

            # 3. Handle decimal separator intelligently (comma vs period)
            has_period = '.' in clean
            has_comma = ',' in clean

            if has_period and has_comma:
                # Both present: Assume period is decimal, remove comma as thousands separator
                clean = clean.replace(',', '')
                self.logger.debug(f"  Both separators found. Removed comma: '{clean}'")
            elif has_comma and not has_period:
                # Only comma present: Assume it's the decimal, replace with period
                clean = clean.replace(',', '.')
                self.logger.debug(f"  Only comma found. Replaced with period: '{clean}'")
            # Case: Only period -> do nothing
            # Case: Neither -> do nothing

            # 4. Remove any remaining commas ONLY if a decimal point exists now
            if '.' in clean:
                parts = clean.split('.')
                if len(parts) >= 2:  # Should be 2, but handle >2 defensively
                    # Remove thousands separators from the integer part only
                    parts[0] = re.sub(r',', '', parts[0])
                    # Join back, keeping only the first decimal part
                    clean = parts[0] + '.' + parts[1]
                    self.logger.debug(f"  Removed remaining thousands commas (if any): '{clean}'")
                else:  # Only integer part after split (e.g., "1,000.")
                    clean = re.sub(r',', '', parts[0])
                    self.logger.debug(f"  Removed thousands commas from integer-only part: '{clean}'")
            else:
                # No decimal point, remove all commas (they must be thousands separators)
                clean = re.sub(r',', '', clean)
                self.logger.debug(f"  No decimal, removed all commas: '{clean}'")

            # 5. Final cleanup: Remove any non-digit characters except leading '-' and single '.'
            leading_dash = ''
            # Standardize recognized negative indicators to '-'
            if clean.startswith(('-', '~', '–', '—')):
                leading_dash = '-'
            clean = re.sub(r'^[-~–—]+', '', clean)  # Remove sign for processing digits

            # Keep only digits and the first decimal point
            final_clean = ""
            decimal_found = False
            for char in clean:
                if char.isdigit():
                    final_clean += char
                elif char == '.' and not decimal_found:
                    final_clean += char
                    decimal_found = True
                # else: discard char

            # Handle empty string after cleanup
            if not final_clean:
                self.logger.debug(f"  Final cleanup resulted in empty string.")
                return None

            clean = leading_dash + final_clean
            self.logger.debug(f"  After final digit/decimal cleanup: '{clean}'")

            # 6. Convert to float
            if clean == '-':  # Handle just a dash remaining
                return None
            value = float(clean)

            # 7. Apply sign consistently
            # Ensure value is negative if a negative sign/parens were detected originally
            if is_negative and value >= 0:
                value = -abs(value)
            # Ensure value is positive if no negative sign/parens were detected originally
            # (Unless the number itself starts with '-', e.g. matched by 'regular')
            elif not is_negative and value < 0 and not original_match_text.startswith(('-', '~', '–', '—')):
                # This case means 'regular' pattern matched a negative number like '-500'
                # but the original match wasn't explicitly negative via () or leading sign variation.
                # Here, we trust the extracted number's sign.
                pass  # Allow negative if number itself is negative and no positive indicator
                # Alternative: force positive: value = abs(value) if strict needed

            self.logger.debug(f"  Successfully cleaned and converted to: {value}")
            return value

        except (ValueError, TypeError) as e:
            self.logger.warning(
                f"Could not convert cleaned value '{clean}' (from group '{value_str}', match '{original_match_text}') to float: {e}")
            return None
        except Exception as e:
            self.logger.error(
                f"Unexpected error during cleaning/conversion for '{value_str}' / '{original_match_text}': {e}",
                exc_info=True)
            return None