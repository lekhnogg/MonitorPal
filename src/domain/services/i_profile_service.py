# src/domain/services/i_profile_service.py
from abc import ABC, abstractmethod
from typing import List, Optional

from src.domain.models.platform_profile import PlatformProfile
from src.domain.common.result import Result


class IProfileService(ABC):
    """Service for managing platform-specific profiles."""

    @abstractmethod
    def get_profile(self, platform_name: str) -> Result[PlatformProfile]:
        """Get the profile for a specific platform."""
        pass

    @abstractmethod
    def save_profile(self, profile: PlatformProfile) -> Result[bool]:
        """Save a platform profile."""
        pass

    @abstractmethod
    def get_all_profiles(self) -> Result[List[PlatformProfile]]:
        """Get all available platform profiles."""
        pass

    @abstractmethod
    def create_default_profile(self, platform_name: str) -> Result[PlatformProfile]:
        """Create a default profile for a platform."""
        pass