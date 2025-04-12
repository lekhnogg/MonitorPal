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

            # Preprocessing - replace common OCR errors
            processed_text = text
            # --- ADDED PRE-CLEANING FOR COMMA/PERIOD ---
            # If we see a comma followed by exactly two digits at the end,
            # especially after a number, it's highly likely it should be a period.
            # Example: -$1,280,00 -> -$1,280.00
            original_processed_text = processed_text  # Store for logging comparison
            processed_text = re.sub(r'(\d),(\d{2})$', r'\1.\2', processed_text)
            # Also handle cases like 1,280,00 without trailing symbols
            processed_text = re.sub(r'(\d),(\d{2})\b', r'\1.\2', processed_text)  # Use word boundary \b
            if processed_text != original_processed_text:
                self.logger.debug(f"Applied comma->period correction: '{processed_text[:100]}...'")
            # --- END ADDED PRE-CLEANING ---

            # Continue with other preprocessing
            processed_text = processed_text.replace(';', '.')  # Common Tesseract error
            processed_text = processed_text.replace(' ', '')  # Remove spaces
            processed_text = processed_text.replace('S', '$')  # Common OCR mistake
            processed_text = processed_text.replace('s', '$')  # Common OCR mistake
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
                            # NOTE: _clean_and_convert_value should be the ORIGINAL version
                            # (without the complex separator logic changes we tried before)
                            numeric_value = self._clean_and_convert_value(captured_group, full_match_text)

                            if numeric_value is not None:
                                # Check for uniqueness based on rounded value (e.g., 2 decimal places)
                                rounded = round(numeric_value, 2)
                                if rounded not in seen_rounded_values:
                                    extracted_values.append(numeric_value)
                                    seen_rounded_values.add(rounded)
                                    self.logger.debug(
                                        f"  Added value {numeric_value} (Rounded: {rounded}) using pattern '{pattern_name}' from match '{full_match_text}'")
                                else:
                                    self.logger.debug(
                                        f"  Duplicate value {numeric_value} (Rounded: {rounded}) ignored.")
                        else:
                            self.logger.debug(
                                f"Pattern '{pattern_name}' matched '{full_match_text}' but captured no group (or group was None).")

                except re.error as e:
                    self.logger.error(f"Regex error processing pattern '{pattern_name}': {e}")
                except Exception as e:
                    self.logger.error(f"Unexpected error processing pattern '{pattern_name}': {e}", exc_info=True)

            self.logger.debug(f"Final extracted numeric values: {extracted_values}")
            return Result.ok(extracted_values)

        except Exception as e:
            # Log general exceptions during the process
            error_msg = f"Numeric value extraction with patterns failed: {str(e)}"
            self.logger.error(error_msg, exc_info=True)  # Include stack trace
            return Result.fail(error_msg)

    def _clean_and_convert_value(self, value_str: str, full_match: str) -> Optional[float]:
        """
        [Internal Helper] Cleans the extracted string value and converts it to a float.
        Handles different signs, decimal separators, and thousands separators intelligently.
        """
        if not isinstance(value_str, str) or not value_str:
            self.logger.debug(f"Cleaning skipped: Input captured group is not a non-empty string ('{value_str}').")
            return None

        original_match_text = full_match.strip() if isinstance(full_match, str) else ""

        try:
            # Step 1: Detect sign from the original full match
            is_negative = original_match_text.startswith(('-', '~', '–', '—')) or \
                          (original_match_text.startswith('(') and original_match_text.endswith(')'))
            self.logger.debug(
                f"Cleaning captured group '{value_str}' from match '{original_match_text}'. Detected negative: {is_negative}")

            # Step 2: Initial Cleanup
            # Remove currency symbols, parentheses, spaces, and other noise
            clean = re.sub(r'[$§@\s()]+', '', value_str.strip())

            # Replace common OCR misreads
            clean = clean.replace('l', '1').replace('O', '0').replace('S', '5').replace('B', '8')
            self.logger.debug(f"  After removing noise: '{clean}'")

            if not clean:
                return None

            # Step 3: Analyze structure and determine separators
            # Count occurrences
            num_periods = clean.count('.')
            num_commas = clean.count(',')

            # Find positions of last separator of each type
            last_period_pos = clean.rfind('.')
            last_comma_pos = clean.rfind(',')

            # Use more robust format detection based on common financial formats
            decimal_separator_char = '.'  # Default
            thousands_separator_char = ','  # Default

            # Handle specific formats based on patterns commonly seen in financial contexts

            # Case: $1,234.56 (US/UK format)
            if '$' in original_match_text and num_commas >= 1 and num_periods == 1:
                if last_period_pos > last_comma_pos:
                    # Standard format with $ sign, using period as decimal
                    decimal_separator_char = '.'
                    thousands_separator_char = ','
                    self.logger.debug(f"  Format detected: US/UK with $ sign")

            # Case where a single period appears at the end (likely decimal): 1.234.56
            elif num_periods > 0 and last_period_pos > 0 and last_period_pos == len(clean) - 3:
                # Period appears exactly 2 digits from the end - likely a decimal point
                decimal_separator_char = '.'
                # If multiple periods, earlier ones are thousands separators
                thousands_separator_char = '.' if num_periods > 1 else ','
                self.logger.debug(f"  Format detected: Period as decimal (2 digits after)")

            # Case where a single comma appears at the end (likely decimal): 1,234,56
            elif num_commas > 0 and last_comma_pos > 0 and last_comma_pos == len(clean) - 3:
                # Comma appears exactly 2 digits from the end - likely a decimal point
                decimal_separator_char = ','
                # If multiple commas, earlier ones are thousands separators
                thousands_separator_char = ',' if num_commas > 1 else '.'
                self.logger.debug(f"  Format detected: Comma as decimal (2 digits after)")

            # Case of mixed separators - use standard rules based on position
            elif num_periods >= 1 and num_commas >= 1:
                if last_comma_pos > last_period_pos:
                    # Last separator is comma - European format
                    decimal_separator_char = ','
                    thousands_separator_char = '.'
                    self.logger.debug(f"  Format detected: European (comma decimal)")
                else:
                    # Last separator is period - US/UK format
                    decimal_separator_char = '.'
                    thousands_separator_char = ','
                    self.logger.debug(f"  Format detected: US/UK (period decimal)")

            # Only commas present - analyze position and count
            elif num_commas >= 1 and num_periods == 0:
                if num_commas == 1 and len(clean) - last_comma_pos <= 3:
                    # Single comma close to the end - likely decimal
                    decimal_separator_char = ','
                    thousands_separator_char = None
                    self.logger.debug(f"  Format detected: Comma as decimal (single comma near end)")
                else:
                    # Multiple commas or positioned as thousands - assume US format with thousands commas
                    decimal_separator_char = '.'
                    thousands_separator_char = ','
                    self.logger.debug(f"  Format detected: Commas as thousands")

            # Only periods present - analyze position and count
            elif num_periods >= 1 and num_commas == 0:
                if num_periods == 1 and len(clean) - last_period_pos <= 3:
                    # Single period close to the end - likely decimal
                    decimal_separator_char = '.'
                    thousands_separator_char = None
                    self.logger.debug(f"  Format detected: Period as decimal (single period near end)")
                else:
                    # Multiple periods - assume European format with thousands periods
                    decimal_separator_char = '.'
                    thousands_separator_char = '.'
                    self.logger.debug(f"  Format detected: Periods as both")

            self.logger.debug(
                f"  Determined decimal char: '{decimal_separator_char}', thousands char: '{thousands_separator_char}'")

            # Step 4: Process thousands separators
            if thousands_separator_char:
                clean = clean.replace(thousands_separator_char, '')
                self.logger.debug(f"  Removed thousands separator ('{thousands_separator_char}'): '{clean}'")

            # Step 5: Standardize decimal separator to period for float conversion
            if decimal_separator_char == ',':
                # Count commas left after removing thousands
                remaining_commas = clean.count(',')
                if remaining_commas == 1:
                    clean = clean.replace(',', '.')
                    self.logger.debug(f"  Standardized decimal separator (comma to period): '{clean}'")
                elif remaining_commas == 0:
                    self.logger.debug(f"  No decimal comma found after processing. String: '{clean}'")
                else:
                    # Multiple commas remain - take the last one as decimal
                    comma_positions = [pos for pos, char in enumerate(clean) if char == ',']
                    # Keep only the last comma, replace it with period
                    new_clean = ""
                    for i, char in enumerate(clean):
                        if char == ',' and i == comma_positions[-1]:
                            new_clean += '.'
                        elif char == ',':
                            # Skip other commas
                            continue
                        else:
                            new_clean += char
                    clean = new_clean
                    self.logger.debug(f"  Handled multiple remaining commas, using last as decimal: '{clean}'")

            # Step 6: Final cleanup - ensure we keep only digits and one decimal point
            final_clean = ""
            decimal_found = False
            leading_sign = ''

            # Handle leading minus sign
            clean_for_digits = clean
            if clean.startswith(('-', '~', '–', '—')):
                leading_sign = '-'
                clean_for_digits = clean[1:]

            # Process each character
            for char in clean_for_digits:
                if char.isdigit():
                    final_clean += char
                elif char == '.' and not decimal_found:
                    final_clean += char
                    decimal_found = True

            clean = leading_sign + final_clean
            self.logger.debug(f"  Final string before float: '{clean}'")

            if not clean or clean == '-' or clean == '.':
                return None

            # Step 7: Convert
            value = float(clean)

            # Step 8: Apply sign based on original detection
            if is_negative:
                value = -abs(value)
            elif value < 0:
                self.logger.debug(
                    f"    Value parsed negative ({value}) but context wasn't explicitly negative. Keeping.")

            self.logger.debug(f"  Successfully cleaned and converted to: {value}")
            return value

        except (ValueError, TypeError) as e:
            self.logger.warning(f"Could not convert '{clean if 'clean' in locals() else value_str}' to float: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected cleaning error for '{original_match_text}': {e}", exc_info=True)
            return None