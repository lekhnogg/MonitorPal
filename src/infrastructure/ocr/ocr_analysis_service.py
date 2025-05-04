# src/infrastructure/ocr/ocr_analysis_service.py

import os
import re
import cv2 # Ensure cv2 is imported if used (it is)
import numpy as np # Ensure numpy is imported (it is)
from typing import Dict, List, Optional
from PIL import Image # Ensure PIL is imported (it is)

from src.domain.services.i_ocr_analysis_service import IOcrAnalysisService
from src.domain.services.i_logger_service import ILoggerService
# Import OcrProfile and the constants for consistency
from src.domain.models.platform_profile import OcrProfile, DEFAULT_TESSERACT_WHITELIST, DEFAULT_TESSERACT_CONFIG
from src.domain.common.result import Result
from src.domain.common.errors import ConfigurationError, ResourceError # Added ResourceError


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
        """
        # No changes needed here, keep existing implementation
        self.logger.debug(f"Providing default numeric patterns (Platform context: {platform_name or 'N/A'})")
        return {
            "dollar": r'[$§]?([\d,]+(?:[.,]\d+)?)',
            "negative": r'\((?:[$§]?)([\d,]+(?:[.,]\d+)?)\)',
            "negative_dash": r'[-~–—]\s*[$§]?([\d,]+(?:[.,]\d+)?)',
            "regular": r'(?<![$§])([-~–—]?[\d,]+(?:[.,]\d+)?)'
        }

    def detect_optimal_ocr_parameters(self, image_path: str) -> Result[OcrProfile]:
        """
        Detect *baseline* optimal OCR parameters from an image.
        These serve as a starting point for calibration or manual tuning.
        """
        try:
            if not os.path.exists(image_path):
                return Result.fail(ConfigurationError(
                    message=f"Image file not found for parameter detection: {image_path}"
                ))

            # Load the image using PIL for consistency, then convert
            try:
                pil_image = Image.open(image_path)
                # Ensure it's RGB before converting to BGR for OpenCV
                if pil_image.mode != 'RGB':
                    pil_image = pil_image.convert('RGB')
                # Convert PIL RGB to OpenCV BGR
                np_image = np.array(pil_image)[:, :, ::-1].copy() # Convert RGB -> BGR
            except Exception as e:
                # Use ResourceError for file loading/conversion issues
                return Result.fail(ResourceError(
                    message=f"Failed to load or convert image: {e}",
                    details={"path": image_path},
                    inner_error=e
                ))

            # --- Create profile using dataclass defaults FIRST ---
            # This ensures we get the new default tesseract_config initially
            ocr_profile = OcrProfile()

            # --- Run detection helpers to potentially OVERRIDE defaults ---
            ocr_profile.invert_colors = self._detect_inversion_needed(np_image)
            ocr_profile.scale_factor = self._detect_optimal_scale(np_image)
            threshold_params = self._detect_optimal_threshold(np_image)
            ocr_profile.threshold_block_size = threshold_params["block_size"]
            ocr_profile.threshold_c = threshold_params["c"]
            denoise_params = self._detect_optimal_denoise(np_image)
            ocr_profile.denoise_h = denoise_params["h"]
            ocr_profile.denoise_template_window_size = denoise_params["template_window_size"]
            ocr_profile.denoise_search_window_size = denoise_params["search_window_size"]
            # --- Detect optimal config (PSM + Whitelist) ---
            ocr_profile.tesseract_config = self._detect_optimal_tesseract_config(np_image) # This method is now updated

            self.logger.info(f"Auto-detected baseline OCR parameters: {ocr_profile}")
            return Result.ok(ocr_profile)

        except Exception as e:
            self.logger.error(f"Error detecting OCR parameters: {e}", exc_info=True)
            return Result.fail(ConfigurationError(
                message="Failed to detect OCR parameters",
                inner_error=e
            ))

    def _detect_inversion_needed(self, image: np.ndarray) -> bool:
        """Detect if image has light text on dark background."""
        # Keep existing implementation
        if len(image.shape) == 3 and image.shape[2] == 3: # Check for 3 channels (BGR)
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        elif len(image.shape) == 2: # Already grayscale
             gray = image
        else: # Unexpected shape, fallback
             self.logger.warning(f"Unexpected image shape for inversion detection: {image.shape}. Assuming no inversion needed.")
             return False

        mean_brightness = np.mean(gray)
        return mean_brightness < 128

    def _detect_optimal_scale(self, image: np.ndarray) -> float:
        """Detect optimal scale factor based on image characteristics."""
        # Keep existing implementation
        height = image.shape[0]
        if height < 30: return 3.0
        elif height < 50: return 2.5
        elif height < 100: return 2.0
        else: return 1.5

    def _detect_optimal_threshold(self, image: np.ndarray) -> dict:
        """Detect optimal threshold parameters for the image."""
        # Keep existing implementation
        if len(image.shape) == 3 and image.shape[2] == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        elif len(image.shape) == 2:
            gray = image
        else:
             self.logger.warning(f"Unexpected image shape for threshold detection: {image.shape}. Using default params.")
             return {"block_size": 11, "c": 2}

        std_dev = np.std(gray)
        if std_dev < 40: block_size = 15; c_value = 4
        elif std_dev < 70: block_size = 11; c_value = 3
        else: block_size = 9; c_value = 2
        if block_size % 2 == 0: block_size += 1
        block_size = max(3, block_size) # Ensure minimum 3

        return {"block_size": block_size, "c": c_value}

    def _detect_optimal_denoise(self, image: np.ndarray) -> dict:
        """Detect optimal denoise parameters for the image."""
        # Keep existing implementation, but maybe default h to 0? Denoising is often not needed.
        if len(image.shape) == 3 and image.shape[2] == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        elif len(image.shape) == 2:
            gray = image
        else:
             self.logger.warning(f"Unexpected image shape for denoise detection: {image.shape}. Using default params.")
             return {"h": 0, "template_window_size": 7, "search_window_size": 21} # Default h=0

        std_dev = np.std(gray)
        # Let's default h to 0 (off) unless noise seems high
        h = 0
        if std_dev >= 70: h = 10 # Medium noise estimate
        if std_dev >= 100: h = 13 # High noise estimate

        template_window_size = 7
        search_window_size = 21

        return {"h": h, "template_window_size": template_window_size, "search_window_size": search_window_size}

    # --- MODIFIED METHOD ---
    def _detect_optimal_tesseract_config(self, image: np.ndarray) -> str:
        """
        Determine baseline tesseract configuration including PSM and whitelist.
        """
        # Basic config
        config = '--oem 3'  # Use LSTM OCR Engine

        # Determine PSM based on image aspect ratio heuristic
        height, width = image.shape[:2]
        aspect_ratio = width / height if height > 0 else 0 # Avoid division by zero

        # Default to PSM 7 for single lines, which is common for P&L
        psm = 7
        if aspect_ratio <= 3 and aspect_ratio > 0: # More square-ish
             psm = 6 # Assume block
        # You could add more heuristics here if needed

        config += f' --psm {psm}'

        # --- Always ADD the default whitelist to the detected baseline ---
        config += f" {DEFAULT_TESSERACT_WHITELIST}"
        # --- End Add ---

        self.logger.debug(f"Detected baseline Tesseract config: {config}")
        return config
    # --- END MODIFIED METHOD ---