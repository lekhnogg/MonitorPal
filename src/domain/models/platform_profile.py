# src/domain/models/platform_profile.py
from dataclasses import dataclass
from typing import Dict, Any, Optional


@dataclass
class OcrProfile:
    """OCR-specific parameters for a platform."""
    scale_factor: float = 2.0
    threshold_block_size: int = 11
    threshold_c: int = 2
    denoise_h: int = 10
    denoise_template_window_size: int = 7
    denoise_search_window_size: int = 21
    tesseract_config: str = '--oem 3 --psm 6'
    invert_colors: bool = False  # Add this new parameter
    additional_params: Optional[Dict[str, Any]] = None


@dataclass
class PlatformProfile:
    """Complete profile for a trading platform."""
    platform_name: str
    ocr_profile: OcrProfile = None
    numeric_patterns: Dict[str, str] = None
    is_enabled: bool = True
    additional_settings: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.ocr_profile is None:
            self.ocr_profile = OcrProfile()
        if self.numeric_patterns is None:
            self.numeric_patterns = {
                "dollar": r'\$([\d,]+\.?\d*)',
                "negative": r'\((?:\$)?([\d,]+\.?\d*)\)',
                "regular": r'(?<!\$)(-?[\d,]+\.?\d*)'
            }