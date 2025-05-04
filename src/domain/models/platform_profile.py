# src/domain/models/platform_profile.py
from dataclasses import dataclass, field # Import field for mutable defaults
from typing import Dict, Any, Optional
# import numpy as np # Not strictly needed unless used elsewhere

# Define your whitelist string once for consistency
# Includes digits, period, comma, minus, parentheses, dollar sign. Add others if needed (e.g., §€£).
DEFAULT_TESSERACT_WHITELIST = "-c tessedit_char_whitelist=0123456789.,-()$"
# Define the default Tesseract config string combining recommended OEM, PSM, and whitelist
DEFAULT_TESSERACT_CONFIG = f"--oem 3 --psm 7 {DEFAULT_TESSERACT_WHITELIST}"

@dataclass(unsafe_hash=True)
class OcrProfile:
    """
    OCR-specific parameters for a platform.

    Note: unsafe_hash=True should be used with caution if instances are mutable
          and used in sets or dictionary keys. Ensure instances are treated
          as immutable in such contexts.
    """
    scale_factor: float = 2.0
    threshold_block_size: int = 11 # Should ideally be odd and >= 3
    threshold_c: int = 2
    denoise_h: int = 10 # Strength of denoising (0 or negative to disable)
    denoise_template_window_size: int = 7 # Must be odd and positive if denoising
    denoise_search_window_size: int = 21 # Must be odd and positive if denoising
    # --- Default Tesseract config now includes PSM 7 and Whitelist ---
    tesseract_config: str = DEFAULT_TESSERACT_CONFIG
    # --- End Change ---
    invert_colors: bool = False
    # Use default_factory for mutable types like dict
    additional_params: Optional[Dict[str, Any]] = field(default_factory=dict)

    # Optional: Add validation in post_init if desired
    # def __post_init__(self):
    #     if self.threshold_block_size < 3: self.threshold_block_size = 3
    #     if self.threshold_block_size % 2 == 0: self.threshold_block_size += 1
    #     # Add validation for denoise window sizes if denoise_h > 0 ?


@dataclass
class PlatformProfile:
    """Complete profile for a trading platform."""
    platform_name: str
    # Use default_factory for mutable OcrProfile
    ocr_profile: OcrProfile = field(default_factory=OcrProfile)
    # Default patterns are now handled by ProfileService/OcrAnalysisService
    numeric_patterns: Optional[Dict[str, str]] = None
    is_enabled: bool = True
    # Use default_factory for mutable types like dict
    additional_settings: Optional[Dict[str, Any]] = field(default_factory=dict)

    # __post_init__ is no longer strictly necessary here if OcrProfile uses
    # default_factory and numeric_patterns are handled elsewhere.
    # If you keep it, ensure it doesn't interfere with default_factory.
    # def __post_init__(self):
    #     # This check might conflict with default_factory=OcrProfile
    #     if self.ocr_profile is None:
    #          self.ocr_profile = OcrProfile()