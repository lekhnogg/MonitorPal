# src/infrastructure/ocr/tesseract_ocr_service.py

"""
Implementation of the OCR service using Tesseract OCR.
"""
import os
import re
import sys
import cv2
import numpy as np
from typing import List
from PIL import Image, ImageEnhance

# Import Tesseract binding
import pytesseract

from src.domain.services.i_ocr_service import IOcrService
from src.domain.services.i_logger_service import ILoggerService
from src.domain.common.result import Result


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
        Extract text from an image.

        Args:
            image: The PIL Image to process

        Returns:
            Result containing extracted text on success
        """
        try:
            self.logger.debug("Extracting text from image")

            # Preprocess the image
            preprocess_result = self.preprocess_image(image)
            if preprocess_result.is_failure:
                return Result.fail(preprocess_result.error)

            processed_image = preprocess_result.value

            # Configure OCR options
            custom_config = '--oem 3 --psm 6'  # OEM 3 = Default engine, PSM 6 = Assume a single uniform block of text

            # Perform OCR
            extracted_text = pytesseract.image_to_string(processed_image, config=custom_config)

            # Clean up the extracted text
            extracted_text = extracted_text.strip()

            self.logger.debug(f"Extracted text: {extracted_text[:100]}" + ("..." if len(extracted_text) > 100 else ""))
            return Result.ok(extracted_text)

        except Exception as e:
            error_msg = f"Text extraction failed: {str(e)}"
            self.logger.error(error_msg)
            return Result.fail(error_msg)

    def extract_text_from_file(self, image_path: str) -> Result[str]:
        """
        Extract text from an image file.

        Args:
            image_path: Path to the image file

        Returns:
            Result containing extracted text on success
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

            # Extract text from the loaded image
            return self.extract_text(image)

        except Exception as e:
            error_msg = f"Text extraction from file failed: {str(e)}"
            self.logger.error(error_msg)
            return Result.fail(error_msg)

    def preprocess_image(self, image: Image.Image) -> Result[Image.Image]:
        """
        Preprocess an image to improve OCR accuracy.

        Args:
            image: The PIL Image to preprocess

        Returns:
            Result containing the preprocessed PIL Image on success
        """
        try:
            self.logger.debug("Preprocessing image for OCR")

            # Convert PIL image to numpy array for OpenCV processing
            img_np = np.array(image)

            # Convert to grayscale if it's a color image
            if len(img_np.shape) == 3 and img_np.shape[2] >= 3:
                img_gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            else:
                img_gray = img_np

            # Resize image (upscale)
            scale_factor = 2
            h, w = img_gray.shape
            img_resized = cv2.resize(img_gray, (w * scale_factor, h * scale_factor),
                                     interpolation=cv2.INTER_CUBIC)

            # Apply adaptive threshold to get a binary image
            img_thresh = cv2.adaptiveThreshold(
                img_resized, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY, 11, 2
            )

            # Denoise the image
            img_denoised = cv2.fastNlMeansDenoising(img_thresh, None, 10, 7, 21)

            # Convert back to PIL Image
            processed_image = Image.fromarray(img_denoised)

            return Result.ok(processed_image)

        except Exception as e:
            error_msg = f"Image preprocessing failed: {str(e)}"
            self.logger.error(error_msg)
            return Result.fail(error_msg)

    def extract_numeric_values(self, text: str) -> Result[List[float]]:
        """
        Extract numeric values from text.

        Handles various formats including dollar amounts, percentages, etc.

        Args:
            text: The text to process

        Returns:
            Result containing a list of extracted numeric values on success
        """
        try:
            self.logger.debug("Extracting numeric values from text")

            # Preprocessing - replace common OCR errors
            text = text.replace(';', '.')  # Replace semicolons with periods (common OCR error)

            # List to store extracted values
            values = []

            # Pattern 1: Dollar values with $ symbol and optional commas - $1,234.56 or $1234.56
            dollar_pattern = r'\$([\d,]+\.?\d*)'
            dollar_matches = re.findall(dollar_pattern, text)
            for match in dollar_matches:
                try:
                    # Remove commas and convert to float
                    clean_value = match.replace(',', '')
                    value = float(clean_value)
                    values.append(value)
                except ValueError:
                    continue

            # Pattern 2: Negative values in parentheses - (123.45) or ($123.45)
            neg_pattern = r'\((?:\$)?([\d,]+\.?\d*)\)'
            neg_matches = re.findall(neg_pattern, text)
            for match in neg_matches:
                try:
                    # Remove commas, convert to float, and make negative
                    clean_value = match.replace(',', '')
                    value = -float(clean_value)
                    values.append(value)
                except ValueError:
                    continue

            # Pattern 3: Regular numbers with optional decimal point and negative sign - 123.45 or -123.45
            # But don't match numbers that are part of larger values already matched
            # This is a secondary pattern that should only be used if no dollar values are found
            if not values:
                num_pattern = r'(?<!\$)(-?[\d,]+\.?\d*)'
                num_matches = re.findall(num_pattern, text)
                for match in num_matches:
                    if match.strip() and not match.strip().startswith('$'):
                        try:
                            # Remove commas and convert to float
                            clean_value = match.replace(',', '')
                            value = float(clean_value)
                            values.append(value)
                        except ValueError:
                            continue

            # If we have matched multiple partial values that might be fragments of a single value,
            # try to reconstruct the full value if possible
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

            self.logger.debug(f"Extracted numeric values: {values}")
            return Result.ok(values)

        except Exception as e:
            error_msg = f"Numeric value extraction failed: {str(e)}"
            self.logger.error(error_msg)
            return Result.fail(error_msg)