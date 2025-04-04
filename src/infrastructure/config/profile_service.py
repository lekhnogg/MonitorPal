from typing import List, Optional, Dict

from src.domain.services.i_profile_service import IProfileService
from src.domain.services.i_config_repository_service import IConfigRepository
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_ocr_analysis_service import IOcrAnalysisService
from src.domain.models.platform_profile import PlatformProfile, OcrProfile
from src.domain.common.result import Result
from src.domain.common.errors import ConfigurationError

import os


class ProfileService(IProfileService):
    """Implementation of profile service using the configuration repository."""

    def __init__(self, config_repository: IConfigRepository, logger: ILoggerService,
                 ocr_analysis_service: IOcrAnalysisService):
        """
        Initialize the profile service.

        Args:
            config_repository: Configuration repository
            logger: Logger service
            ocr_analysis_service: OCR analysis service for parameter detection
        """
        self.config_repository = config_repository
        self.logger = logger
        self.ocr_analysis_service = ocr_analysis_service
        self._ensure_default_profiles()

    def _ensure_default_profiles(self) -> None:
        """Ensure default profiles exist for all supported platforms."""
        defaults = ["Quantower", "NinjaTrader", "TradingView", "Tradovate"]

        # Create defaults for any missing platforms
        for platform in defaults:
            self.get_profile(platform)  # This will create default if missing

    def get_profile(self, platform_name: str) -> Result[PlatformProfile]:
        """Get the profile for a specific platform."""
        try:
            # Get profiles from configuration
            profiles = self.config_repository.get_global_setting("platform_profiles", {})

            if platform_name not in profiles:
                # Return a default profile if not found
                return self.create_default_profile(platform_name)

            # Convert dictionary to PlatformProfile object
            profile_dict = profiles[platform_name]

            # Create profile objects from stored data
            ocr_dict = profile_dict.get("ocr_profile", {})

            # Handle backward compatibility for invert_colors
            if "invert_colors" not in ocr_dict:
                ocr_dict["invert_colors"] = False

            ocr_profile = OcrProfile(**ocr_dict)

            platform_profile = PlatformProfile(
                platform_name=platform_name,
                ocr_profile=ocr_profile,
                numeric_patterns=profile_dict.get("numeric_patterns", {}),
                is_enabled=profile_dict.get("is_enabled", True),
                additional_settings=profile_dict.get("additional_settings", {})
            )

            return Result.ok(platform_profile)

        except Exception as e:
            self.logger.error(f"Error getting profile for {platform_name}: {e}")
            return Result.fail(ConfigurationError(
                message=f"Failed to get profile for {platform_name}",
                details={"platform_name": platform_name},
                inner_error=e
            ))

    def save_profile(self, profile: PlatformProfile) -> Result[bool]:
        """Save a platform profile."""
        try:
            # Get existing profiles
            profiles = self.config_repository.get_global_setting("platform_profiles", {})

            # Convert profile to dictionary for storage
            profile_dict = {
                "ocr_profile": {
                    "scale_factor": float(profile.ocr_profile.scale_factor),  # Ensure correct type
                    "threshold_block_size": int(profile.ocr_profile.threshold_block_size),
                    "threshold_c": int(profile.ocr_profile.threshold_c),
                    "denoise_h": int(profile.ocr_profile.denoise_h),
                    "denoise_template_window_size": int(profile.ocr_profile.denoise_template_window_size),
                    "denoise_search_window_size": int(profile.ocr_profile.denoise_search_window_size),
                    "tesseract_config": str(profile.ocr_profile.tesseract_config),
                    "invert_colors": bool(profile.ocr_profile.invert_colors),
                    "additional_params": profile.ocr_profile.additional_params or {}
                },
                "numeric_patterns": profile.numeric_patterns or {},
                "is_enabled": bool(profile.is_enabled),
                "additional_settings": profile.additional_settings or {}
            }

            # Update profiles
            profiles[profile.platform_name] = profile_dict

            # Save to configuration
            return self.config_repository.set_global_setting("platform_profiles", profiles)
        except Exception as e:
            self.logger.error(f"Error saving profile: {e}")
            return Result.fail(ConfigurationError(
                message="Failed to save profile",
                inner_error=e
            ))

    def get_all_profiles(self) -> Result[List[PlatformProfile]]:
        """Get all available platform profiles."""
        try:
            profiles = []
            profile_dicts = self.config_repository.get_global_setting("platform_profiles", {})

            for platform_name in profile_dicts:
                profile_result = self.get_profile(platform_name)
                if profile_result.is_success:
                    profiles.append(profile_result.value)

            return Result.ok(profiles)

        except Exception as e:
            self.logger.error(f"Error getting all profiles: {e}")
            return Result.fail(ConfigurationError(
                message="Failed to get all profiles",
                inner_error=e
            ))

    def create_default_profile(self, platform_name: str, image_path: Optional[str] = None) -> Result[PlatformProfile]:
        """
        Create a default profile for a platform.

        Args:
            platform_name: Name of the platform
            image_path: Optional path to image for auto-detection
        """
        try:
            # Try auto-detection first if image is provided
            if image_path and os.path.exists(image_path):
                self.logger.info(f"Attempting to auto-detect OCR profile for {platform_name}")
                ocr_profile_result = self.ocr_analysis_service.detect_optimal_ocr_parameters(image_path)

                if ocr_profile_result.is_success:
                    ocr_profile = ocr_profile_result.value
                    self.logger.info(f"Successfully auto-detected OCR profile for {platform_name}")
                else:
                    self.logger.warning(f"Auto-detection failed, using platform defaults: {ocr_profile_result.error}")
                    ocr_profile = self._get_platform_default_ocr_profile(platform_name)
            else:
                # No image provided, use platform defaults
                ocr_profile = self._get_platform_default_ocr_profile(platform_name)

            # Create and save profile
            profile = PlatformProfile(
                platform_name=platform_name,
                ocr_profile=ocr_profile,
                numeric_patterns=self.ocr_analysis_service.get_default_patterns(platform_name)
            )

            save_result = self.save_profile(profile)
            if save_result.is_failure:
                return save_result

            return Result.ok(profile)

        except Exception as e:
            self.logger.error(f"Error creating default profile: {e}")
            return Result.fail(ConfigurationError(
                message=f"Failed to create default profile",
                inner_error=e
            ))

    def _get_platform_default_ocr_profile(self, platform_name: str) -> OcrProfile:
        """Get default OCR profile for a specific platform."""
        if platform_name == "Quantower":
            return OcrProfile(
                scale_factor=2.0,
                threshold_block_size=11,
                threshold_c=2,
                tesseract_config='--oem 3 --psm 7',
                invert_colors=False
            )
        elif platform_name == "NinjaTrader":
            return OcrProfile(
                scale_factor=2.5,
                threshold_block_size=15,
                threshold_c=3,
                tesseract_config='--oem 3 --psm 7',
                invert_colors=False
            )
        elif platform_name == "TradingView":
            return OcrProfile(
                scale_factor=2.2,
                threshold_block_size=13,
                threshold_c=2,
                tesseract_config='--oem 3 --psm 7',
                invert_colors=True
            )
        elif platform_name == "Tradovate":
            return OcrProfile(
                scale_factor=1.8,
                threshold_block_size=9,
                threshold_c=2,
                tesseract_config='--oem 3 --psm 7',
                invert_colors=False
            )
        else:
            # Generic default
            return OcrProfile()

    def test_pattern_extraction(self, text: str, patterns: Dict[str, str]) -> Result[List[float]]:
        """Test pattern extraction on sample text."""
        return self.ocr_analysis_service.test_pattern_extraction(text, patterns)