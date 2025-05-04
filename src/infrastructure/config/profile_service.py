# src/infrastructure/config/profile_service.py

import os
import re
from typing import List, Optional, Dict, Any

from src.domain.services.i_profile_service import IProfileService
from src.domain.services.i_config_repository_service import IConfigRepository
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_ocr_analysis_service import IOcrAnalysisService
# Import the constants defined in platform_profile
from src.domain.models.platform_profile import PlatformProfile, OcrProfile, DEFAULT_TESSERACT_CONFIG
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

    def get_profile(self, platform_name: str) -> Result[PlatformProfile]:
        """Get the profile for a specific platform from the nested config."""
        if not platform_name:
            return Result.fail(ValidationError("Platform name cannot be empty for get_profile."))

        self.logger.debug(f"Getting profile for platform: {platform_name}")
        try:
            platform_settings = self.config_repository.get_platform_settings(platform_name)
            profile_dict = platform_settings.get("platform_profile")

            if profile_dict is None or not isinstance(profile_dict, dict):
                self.logger.info(f"No saved profile found for '{platform_name}' in config. Creating default.")
                # Create default profile (which now uses updated _get_platform_default_ocr_profile)
                # and save it if needed.
                return self.create_default_profile(platform_name)

            self.logger.debug(f"Loading existing profile for '{platform_name}' from config.")
            ocr_profile = self._parse_ocr_profile_dict(platform_name, profile_dict.get("ocr_profile"))

            # Load numeric patterns, falling back to defaults IF NOT PRESENT in config
            # Get defaults first
            default_patterns = self._get_default_patterns_for_platform(platform_name)
            # Check if numeric_patterns key EXISTS in the loaded profile dict
            if "numeric_patterns" in profile_dict:
                 # If key exists, use its value (even if None or empty, let downstream handle)
                 numeric_patterns = profile_dict["numeric_patterns"]
                 # Optional: Validate if it's a dict, fallback to default if invalid type
                 if not isinstance(numeric_patterns, (dict, type(None))):
                      self.logger.warning(f"Invalid type for 'numeric_patterns' in config for {platform_name}. Using defaults.")
                      numeric_patterns = default_patterns
                 elif numeric_patterns is None: # Explicitly null in config
                      self.logger.debug(f"Using null 'numeric_patterns' as specified in config for {platform_name}.")
                      # Decide if null should mean default or truly empty
                      # Let's assume null in config means use default for robustness:
                      numeric_patterns = default_patterns
            else:
                 # Key doesn't exist, use default
                 self.logger.debug(f"'numeric_patterns' key missing for {platform_name}. Using defaults.")
                 numeric_patterns = default_patterns


            platform_profile = PlatformProfile(
                platform_name=platform_name,
                ocr_profile=ocr_profile,
                # Ensure patterns are a dict or None before assignment
                numeric_patterns=numeric_patterns if isinstance(numeric_patterns, dict) else default_patterns,
                is_enabled=bool(profile_dict.get("is_enabled", True)),
                additional_settings=profile_dict.get("additional_settings") # Uses default_factory now
            )

            return Result.ok(platform_profile)

        except Exception as e:
            self.logger.error(f"Error getting profile for {platform_name}: {e}", exc_info=True)
            return Result.fail(ConfigurationError(
                message=f"Failed to get profile for {platform_name}",
                details={"platform_name": platform_name},
                inner_error=e
            ))

    def save_profile(self, profile: PlatformProfile) -> Result[bool]:
        """Save a platform profile into the nested platform settings."""
        if not profile or not profile.platform_name:
            return Result.fail(ValidationError("Invalid profile object provided for saving."))

        platform_name = profile.platform_name
        self.logger.debug(f"Attempting to save profile for platform: {platform_name}")

        try:
            # Use existing OcrProfile or create a default one if missing
            ocr_profile_obj = profile.ocr_profile if profile.ocr_profile else OcrProfile()

            # Validate block size before saving
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
                # Ensure saved config is a valid string
                "tesseract_config": str(ocr_profile_obj.tesseract_config) if ocr_profile_obj.tesseract_config else DEFAULT_TESSERACT_CONFIG,
                "invert_colors": bool(ocr_profile_obj.invert_colors),
                "additional_params": ocr_profile_obj.additional_params # Already uses default_factory
            }
            profile_dict_to_save = {
                "ocr_profile": ocr_profile_dict_to_save,
                # Save numeric patterns; if None on profile, save default patterns
                "numeric_patterns": profile.numeric_patterns if profile.numeric_patterns is not None else self._get_default_patterns_for_platform(platform_name),
                "is_enabled": bool(profile.is_enabled),
                "additional_settings": profile.additional_settings # Already uses default_factory
            }

            platform_settings = self.config_repository.get_platform_settings(platform_name)
            platform_settings["platform_profile"] = profile_dict_to_save
            save_result = self.config_repository.save_platform_settings(
                platform=platform_name,
                settings=platform_settings
            )

            if save_result.is_success:
                self.logger.info(f"Profile for '{platform_name}' saved successfully.")
                return Result.ok(True)
            else:
                # ... (keep existing error handling for save failure) ...
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
        # ... (Keep existing implementation) ...
        profiles = []
        try:
            platforms_result = self.config_repository.get_all_platforms()
            if platforms_result.is_failure:
                 self.logger.error(f"Error getting platform list for get_all_profiles: {platforms_result.error}")
                 return Result.fail(platforms_result.error)

            platform_names = platforms_result.value
            if not platform_names:
                 self.logger.debug("No platforms found in configuration.")
                 return Result.ok([])

            for platform_name in platform_names:
                profile_result = self.get_profile(platform_name)
                if profile_result.is_success:
                    profiles.append(profile_result.value)
                else:
                    self.logger.error(f"Failed to load profile for '{platform_name}' while getting all profiles: {profile_result.error}")

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
        AND saves it to the configuration.
        """
        if not platform_name:
            return Result.fail(ValidationError("Platform name cannot be empty for create_default_profile."))

        self.logger.info(f"Creating and saving default profile for {platform_name}.")
        try:
            # Get the default OCR profile (now includes updated tesseract config)
            ocr_profile = self._get_platform_default_ocr_profile(platform_name)
            # Get default patterns
            default_patterns = self._get_default_patterns_for_platform(platform_name)

            # Create the default PlatformProfile object
            default_platform_profile = PlatformProfile(
                platform_name=platform_name,
                ocr_profile=ocr_profile,
                numeric_patterns=default_patterns
                # is_enabled=True and additional_settings={} handled by dataclass defaults
            )

            # Save this default profile (save_profile ensures structure is correct)
            save_result = self.save_profile(default_platform_profile)

            if save_result.is_failure:
                 self.logger.error(f"CRITICAL: Failed to save the created default profile for {platform_name}: {save_result.error}")
                 return Result.fail(save_result.error)

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
         return self.ocr_analysis_service.get_default_patterns(platform_name)

    def _parse_ocr_profile_dict(self, platform_name: str, ocr_dict: Optional[Dict[str, Any]]) -> OcrProfile:
        """Safely parses OCR profile data from a dictionary, using defaults."""
        if ocr_dict is None or not isinstance(ocr_dict, dict):
            self.logger.warning(f"Missing or invalid 'ocr_profile' dict for {platform_name}. Using platform defaults.")
            return self._get_platform_default_ocr_profile(platform_name)

        # --- Use the NEW dataclass default Tesseract config as fallback ---
        default_tess_config = OcrProfile.tesseract_config # Get default from class definition
        # ---

        try: scale_factor = float(ocr_dict.get("scale_factor", 2.0))
        except (ValueError, TypeError): scale_factor = 2.0
        try: block_size = int(ocr_dict.get("threshold_block_size", 11))
        except (ValueError, TypeError): block_size = 11
        try: c_value = int(ocr_dict.get("threshold_c", 2))
        except (ValueError, TypeError): c_value = 2
        try: denoise_h = int(ocr_dict.get("denoise_h", 10))
        except (ValueError, TypeError): denoise_h = 10
        try: denoise_template = int(ocr_dict.get("denoise_template_window_size", 7))
        except (ValueError, TypeError): denoise_template = 7
        try: denoise_search = int(ocr_dict.get("denoise_search_window_size", 21))
        except (ValueError, TypeError): denoise_search = 21

        if block_size < 3: block_size = 3
        if block_size % 2 == 0: block_size += 1

        return OcrProfile(
            scale_factor=scale_factor,
            threshold_block_size=block_size,
            threshold_c=c_value,
            denoise_h=denoise_h,
            denoise_template_window_size=denoise_template,
            denoise_search_window_size=denoise_search,
            # --- Use NEW default here ---
            tesseract_config=str(ocr_dict.get("tesseract_config", default_tess_config)),
            # ---
            invert_colors=bool(ocr_dict.get("invert_colors", False)),
            additional_params=ocr_dict.get("additional_params")
        )

    # --- MODIFIED METHOD ---
    def _get_platform_default_ocr_profile(self, platform_name: str) -> OcrProfile:
        """
        Get default OCR profile parameters for a specific platform,
        ensuring the standard robust tesseract config is used.
        """
        self.logger.debug(f"Getting default OCR profile for platform: {platform_name}")

        # --- Use the imported DEFAULT_TESSERACT_CONFIG ---
        tess_config = DEFAULT_TESSERACT_CONFIG
        # ---

        # Define platform-specific overrides for parameters OTHER than tesseract_config
        if platform_name == "Quantower":
            return OcrProfile(
                scale_factor=2.0, threshold_block_size=11, threshold_c=2,
                tesseract_config=tess_config, invert_colors=False # Keep invert_colors specific
            )
        elif platform_name == "NinjaTrader":
            return OcrProfile(
                scale_factor=2.5, threshold_block_size=15, threshold_c=3,
                tesseract_config=tess_config, invert_colors=False
            )
        elif platform_name == "TradingView":
            return OcrProfile(
                scale_factor=2.2, threshold_block_size=13, threshold_c=2,
                tesseract_config=tess_config, invert_colors=True # Keep invert_colors specific
            )
        elif platform_name == "Tradovate":
            return OcrProfile(
                scale_factor=1.8, threshold_block_size=9, threshold_c=2,
                tesseract_config=tess_config, invert_colors=False
            )
        else:
            # Generic default uses the OcrProfile dataclass defaults,
            # which now includes the desired tesseract_config.
            self.logger.debug(f"No specific default OCR profile adjustments found for '{platform_name}'. Using dataclass defaults.")
            return OcrProfile()
    # --- END MODIFIED METHOD ---