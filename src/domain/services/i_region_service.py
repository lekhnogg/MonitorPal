# src/domain/services/i_region_service.py
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Tuple, Any
from src.domain.common.result import Result
from src.domain.models.region_model import Region


class IRegionService(ABC):
    """Service for managing screen regions."""

    @abstractmethod
    def save_region(self, region: Region) -> Result[bool]:
        """Save a region with its screenshot."""
        pass

    @abstractmethod
    def get_regions_by_platform(self, platform: str, region_type: str) -> Result[List[Region]]:
        """Get all regions for a platform of a specific type."""
        pass

    @abstractmethod
    def get_region(self, platform: str, region_type: str, name: str) -> Result[Region]:
        """Get a specific region by platform, type and name."""
        pass

    @abstractmethod
    def capture_region_screenshot(self, coordinates: Tuple[int, int, int, int],
                                  region_id: str, platform: str,
                                  region_type: str) -> Result[str]:
        """Capture and save a screenshot for a region."""
        pass

    @abstractmethod
    def load_region_screenshot(self, region: Region) -> Result[Any]:
        """Load the screenshot for a region."""
        pass

    @abstractmethod
    def delete_region(self, platform: str, region_type: str, name: str) -> Result[bool]:
        """Delete a region."""
        pass