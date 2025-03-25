# src/domain/models/region_model.py
from dataclasses import dataclass
from typing import Tuple, Optional

@dataclass
class Region:
    """Region model representing a screen area with reference to a screenshot."""
    id: str  # Unique identifier
    name: str  # User-friendly name
    coordinates: Tuple[int, int, int, int]  # (x, y, width, height)
    type: str  # "monitor" or "flatten"
    platform: str  # Platform this region belongs to
    screenshot_path: Optional[str] = None  # Path to saved screenshot