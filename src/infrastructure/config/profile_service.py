# src/infrastructure/config/profile_service.py

import os
import re # Keep re if needed for pattern validation maybe, though not used currently
from typing import List, Optional, Dict, Any # Added Any

from src.domain.services.i_profile_service import IProfileService
from src.domain.services.i_config_repository_service import IConfigRepository
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_ocr_analysis_service import IOcrAnalysisService # Keep this
from src.domain.models.platform_profile import PlatformProfile, OcrProfile
from src.domain.common.result import Result
from src.domain.common.errors import ConfigurationError, ValidationError, ResourceError


class ProfileService(IProfileService):
    """
    Implementation of profile service using the configuration repository.
    Reads/writes profiles from nested structure within platform settings.
    """

    def __init__(self, config_repository: IConfigRepository, logger: ILoggerService,
                 ocr_analysis_service: IOcrAnalysisService):
        """
        Initialize the profile service.

        Args:
            config_repository: Configuration repository instance.
            logger: Logger service instance.
            ocr_analysis_service: OCR analysis service for parameter detection
                                  and default patterns.
        """
        self.config_repository = config_repository
        self.logger = logger
        self.ocr_analysis_service = ocr_analysis_service
        # Removed _ensure_default_profiles here - defaults are now created
        # on-demand by get_profile if missing.

    def get_profile(self, platform_name: str) -> Result[PlatformProfile]:
        """Get the profile for a specific platform from the nested config."""
        if not platform_name: # Added validation
            return Result.fail(ValidationError("Platform name cannot be empty for get_profile."))

        self.logger.debug(f"Getting profile for platform: {platform_name}") # Added logging
        try:
            # Get settings dictionary for the specific platform using the repo
            platform_settings = self.config_repository.get_platform_settings(platform_name)

            # Look for the 'platform_profile' key *within* these settings
            profile_dict = platform_settings.get("platform_profile")

            # If profile doesn't exist in the correct nested location, create/save default
            if profile_dict is None or not isinstance(profile_dict, dict):
                self.logger.info(f"No saved profile found for '{platform_name}' in config. Creating default.")
                return self.create_default_profile(platform_name) # Returns Result[PlatformProfile]

            # --- Profile dictionary exists, parse it ---
            self.logger.debug(f"Loading existing profile for '{platform_name}' from config.")

            # Parse OCR Profile data safely using helper
            ocr_profile = self._parse_ocr_profile_dict(platform_name, profile_dict.get("ocr_profile"))

            # Parse Numeric Patterns with defaults
            default_patterns = self._get_default_patterns_for_platform(platform_name)
            numeric_patterns = profile_dict.get("numeric_patterns", default_patterns)
            if not isinstance(numeric_patterns, dict) or not numeric_patterns:
                self.logger.warning(f"Invalid or empty 'numeric_patterns' for {platform_name}. Using defaults.")
                numeric_patterns = default_patterns

            # Create the final PlatformProfile object
            platform_profile = PlatformProfile(
                platform_name=platform_name,
                ocr_profile=ocr_profile,
                numeric_patterns=numeric_patterns,
                is_enabled=bool(profile_dict.get("is_enabled", True)),
                additional_settings=profile_dict.get("additional_settings")
            )

            return Result.ok(platform_profile)

        except Exception as e:
            self.logger.error(f"Error getting profile for {platform_name}: {e}", exc_info=True) # Added traceback
            return Result.fail(ConfigurationError(
                message=f"Failed to get profile for {platform_name}",
                details={"platform_name": platform_name},
                inner_error=e
            ))

    def save_profile(self, profile: PlatformProfile) -> Result[bool]:
        """Save a platform profile into the nested platform settings."""
        if not profile or not profile.platform_name: # Added validation
            return Result.fail(ValidationError("Invalid profile object provided for saving."))

        platform_name = profile.platform_name
        self.logger.debug(f"Attempting to save profile for platform: {platform_name}") # Added logging

        try:
            # Convert profile object to a clean dictionary for storage
            ocr_profile_obj = profile.ocr_profile if profile.ocr_profile else OcrProfile()
            save_block_size = int(ocr_profile_obj.threshold_block_size)
            if save_block_size < 3: save_block_size = 3
            if save_block_size % 2 == 0: save_block_size += 1
            ocr_profile_dict_to_save = {
                "scale_factor": float(ocr_profile_obj.scale_factor),
                "threshold_block_size": save_block_size,
                "threshold_c": int(ocr_profile_obj.threshold_c),
                "denoise_h": int(ocr_profile_obj.denoise_h),
                "denoise_template_window_size": int(ocr_profile_obj.denoise_template_window_size),
                "denoise_search_window_size": int(ocr_profile_obj.denoise_search_window_size),
                "tesseract_config": str(ocr_profile_obj.tesseract_config),
                "invert_colors": bool(ocr_profile_obj.invert_colors),
                "additional_params": ocr_profile_obj.additional_params or None
            }
            profile_dict_to_save = {
                "ocr_profile": ocr_profile_dict_to_save,
                "numeric_patterns": profile.numeric_patterns or {},
                "is_enabled": bool(profile.is_enabled),
                "additional_settings": profile.additional_settings or None
            }

            # Get the current full settings dictionary for this specific platform
            platform_settings = self.config_repository.get_platform_settings(platform_name)

            # Update *only* the 'platform_profile' key within that dictionary
            platform_settings["platform_profile"] = profile_dict_to_save

            # Save the entire modified platform settings dictionary back using the correct repo method
            save_result = self.config_repository.save_platform_settings(
                platform=platform_name,
                settings=platform_settings
            )

            # Check and return result, ensuring correct error type
            if save_result.is_success:
                self.logger.info(f"Profile for '{platform_name}' saved successfully.")
                return Result.ok(True)
            else:
                self.logger.error(f"Failed to save platform settings for '{platform_name}': {save_result.error}")
                err = save_result.error
                if not isinstance(err, (ConfigurationError, ResourceError, ValidationError)):
                    err = ConfigurationError(f"Failed to save platform settings for {platform_name}", inner_error=err)
                return Result.fail(err)

        except Exception as e:
            self.logger.error(f"Unexpected error saving profile for {platform_name}: {e}", exc_info=True)
            return Result.fail(ConfigurationError(
                message=f"Unexpected error saving profile for {platform_name}",
                inner_error=e
            ))

    def get_all_profiles(self) -> Result[List[PlatformProfile]]:
        """Get all available platform profiles by iterating configured platforms."""
        profiles = []
        try:
            # Get the list of platforms that HAVE settings defined
            platforms_result = self.config_repository.get_all_platforms()
            if platforms_result.is_failure:
                 # Log error getting platform list, return failure
                 self.logger.error(f"Error getting platform list for get_all_profiles: {platforms_result.error}")
                 return Result.fail(platforms_result.error)

            platform_names = platforms_result.value
            if not platform_names:
                 self.logger.debug("No platforms found in configuration.")
                 return Result.ok([]) # Return empty list if no platforms configured

            # For each platform name, get its profile (which creates default if needed)
            for platform_name in platform_names:
                profile_result = self.get_profile(platform_name)
                if profile_result.is_success:
                    profiles.append(profile_result.value)
                else:
                    # Log error for specific profile load failure but continue with others
                    self.logger.error(f"Failed to load profile for '{platform_name}' while getting all profiles: {profile_result.error}")
                    # Option: could add a default/placeholder profile here if needed

            return Result.ok(profiles)

        except Exception as e:
            self.logger.error(f"Error getting all profiles: {e}", exc_info=True)
            return Result.fail(ConfigurationError(
                message="Failed to get all profiles",
                inner_error=e
            ))

    def create_default_profile(self, platform_name: str, image_path: Optional[str] = None) -> Result[PlatformProfile]:
        """
        Creates a default PlatformProfile object based on platform name
        AND saves it to the configuration using the corrected save_profile.

        Args:
            platform_name: Name of the platform.
            image_path: Optional path (Not implemented).

        Returns:
            Result containing the created (and saved) PlatformProfile object,
            or an error Result if creation/saving failed critically.
        """
        if not platform_name: # Added validation
            return Result.fail(ValidationError("Platform name cannot be empty for create_default_profile."))

        self.logger.info(f"Creating and saving default profile for {platform_name}.")
        try:
            # --- Determine default OCR profile ---
            if image_path and os.path.exists(image_path):
                 self.logger.warning(f"Image path provided for '{platform_name}' default profile, but auto-detection not implemented.")
            ocr_profile = self._get_platform_default_ocr_profile(platform_name)

            # --- Determine default patterns ---
            default_patterns = self._get_default_patterns_for_platform(platform_name)

            # --- Create the default PlatformProfile object ---
            default_platform_profile = PlatformProfile(
                platform_name=platform_name,
                ocr_profile=ocr_profile,
                numeric_patterns=default_patterns
            )

            # --- Save this default profile to the configuration ---
            # Calls the NOW CORRECTED save_profile method
            save_result = self.save_profile(default_platform_profile)

            if save_result.is_failure:
                 self.logger.error(f"CRITICAL: Failed to save the created default profile for {platform_name}: {save_result.error}")
                 # Return the failure result from save_profile
                 return Result.fail(save_result.error)

            # Return the created (and successfully saved) default profile object
            return Result.ok(default_platform_profile)

        except Exception as e:
            self.logger.error(f"Error creating/saving default profile for {platform_name}: {e}", exc_info=True)
            return Result.fail(ConfigurationError(
                message=f"Failed to create/save default profile for {platform_name}",
                inner_error=e
            ))

    # --- Helper Methods ---
    def _get_default_patterns_for_platform(self, platform_name: Optional[str] = None) -> Dict[str, str]:
         """Gets default patterns using the OCR Analysis Service."""
         # Pass platform_name to potentially customize patterns later
         return self.ocr_analysis_service.get_default_patterns(platform_name)

    def _parse_ocr_profile_dict(self, platform_name: str, ocr_dict: Optional[Dict[str, Any]]) -> OcrProfile:
        """Safely parses OCR profile data from a dictionary, using defaults."""
        if ocr_dict is None or not isinstance(ocr_dict, dict):
            self.logger.warning(f"Missing or invalid 'ocr_profile' dict for {platform_name}. Using defaults.")
            # Use the same helper that create_default_profile uses
            return self._get_platform_default_ocr_profile(platform_name)

        # Use .get() with defaults and try-except for type conversions
        try:
            scale_factor = float(ocr_dict.get("scale_factor", 2.0))
        except (ValueError, TypeError):
            scale_factor = 2.0
        try:
            block_size = int(ocr_dict.get("threshold_block_size", 11))
        except (ValueError, TypeError):
            block_size = 11
        try:
            c_value = int(ocr_dict.get("threshold_c", 2))
        except (ValueError, TypeError):
            c_value = 2
        try:
            denoise_h = int(ocr_dict.get("denoise_h", 10))
        except (ValueError, TypeError):
            denoise_h = 10
        try:
            denoise_template = int(ocr_dict.get("denoise_template_window_size", 7))
        except (ValueError, TypeError):
            denoise_template = 7
        try:
            denoise_search = int(ocr_dict.get("denoise_search_window_size", 21))
        except (ValueError, TypeError):
            denoise_search = 21

        # Ensure block size is odd and >= 3
        if block_size < 3: block_size = 3
        if block_size % 2 == 0: block_size += 1

        return OcrProfile(
            scale_factor=scale_factor,
            threshold_block_size=block_size,
            threshold_c=c_value,
            denoise_h=denoise_h,
            denoise_template_window_size=denoise_template,
            denoise_search_window_size=denoise_search,
            tesseract_config=str(ocr_dict.get("tesseract_config", '--oem 3 --psm 6')),
            invert_colors=bool(ocr_dict.get("invert_colors", False)),
            # Get additional_params, allowing it to be None
            additional_params=ocr_dict.get("additional_params")
        )

    def _get_platform_default_ocr_profile(self, platform_name: str) -> OcrProfile:
        """Get default OCR profile parameters for a specific platform."""
        self.logger.debug(f"Getting default OCR profile for platform: {platform_name}")
        # Define platform-specific defaults here
        if platform_name == "Quantower":
            return OcrProfile(
                scale_factor=2.0, threshold_block_size=11, threshold_c=2,
                tesseract_config='--oem 3 --psm 7', invert_colors=False
            )
        elif platform_name == "NinjaTrader":
            return OcrProfile(
                scale_factor=2.5, threshold_block_size=15, threshold_c=3,
                tesseract_config='--oem 3 --psm 7', invert_colors=False
            )
        elif platform_name == "TradingView":
            return OcrProfile(
                scale_factor=2.2, threshold_block_size=13, threshold_c=2,
                tesseract_config='--oem 3 --psm 7', invert_colors=True
            )
        elif platform_name == "Tradovate":
            return OcrProfile(
                scale_factor=1.8, threshold_block_size=9, threshold_c=2,
                tesseract_config='--oem 3 --psm 7', invert_colors=False
            )
        else:
            # Generic default if platform name doesn't match known ones
            self.logger.warning(f"No specific default OCR profile found for '{platform_name}'. Using generic defaults.")
            return OcrProfile() # Returns dataclass with its defaults