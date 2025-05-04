# src/domain/services/i_flash_service.py
from abc import ABC, abstractmethod
from typing import List, Tuple
from src.domain.common.result import Result

class IFlashService(ABC):

    @abstractmethod
    def flash_regions(self, list_of_coords: List[Tuple[int, int, int, int]]) -> Result[None]:
        """
        Flashes multiple screen regions simultaneously given their coordinates.

        Args:
            list_of_coords: A list of coordinate tuples (x, y, w, h) for the regions.

        Returns:
            Result indicating if the flashing task was successfully started.
        """
        pass