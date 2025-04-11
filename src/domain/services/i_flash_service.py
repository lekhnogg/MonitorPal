# src/domain/services/i_flash_service.py
from abc import ABC, abstractmethod
from src.domain.common.result import Result

class IFlashService(ABC):
    @abstractmethod
    def flash_region(self, platform: str, region_type: str, region_name: str) -> Result[None]:
        """
        Activates the specified platform's window and visually flashes the
        given region on screen for user identification.

        Args:
            platform: The name of the platform.
            region_type: The type of region ('monitor' or 'flatten').
            region_name: The specific name of the region.

        Returns:
            Result.ok(None) on success, Result.fail(error) on failure.
        """
        pass