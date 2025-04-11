# src/infrastructure/platform/region_service.py
import os
import re
from typing import List, Dict, Optional, Tuple, Any
from PIL import Image

from src.domain.services.i_region_service import IRegionService
from src.domain.services.i_config_repository_service import IConfigRepository
from src.domain.services.i_screenshot_service import IScreenshotService
from src.domain.services.i_path_service import IPathService
from src.domain.services.i_logger_service import ILoggerService
from src.domain.models.region_model import Region
from src.domain.common.result import Result
from src.domain.common.errors import ResourceError, ValidationError, ConfigurationError


class RegionService(IRegionService):
    """Service implementation for managing screen regions."""

    def __init__(self, config_repository: IConfigRepository,
                 screenshot_service: IScreenshotService,
                 path_service: IPathService, # Added path_service
                 logger: ILoggerService):
        self.config_repository = config_repository
        self.screenshot_service = screenshot_service
        self.path_service = path_service # Store path_service
        self.logger = logger

    def _get_original_screenshot_path(self, region: Region) -> str:
        """ Helper to construct the standard path for an original region screenshot. """
        if not region.platform or not region.type or not region.name:
            self.logger.warning(f"Attempted to get path for incomplete region: {region}")
            # PathService should handle base path determination robustly
            return os.path.join(self.path_service.get_base_data_path(), "invalid_region_path.png")

        regions_dir = self.path_service.get_platform_regions_path(region.platform)  # Ensures dir exists
        safe_region_name = re.sub(r'[^\w\-]+', '_', region.name)
        filename = f"{region.platform}_{region.type}_{safe_region_name}_original.png"
        return os.path.join(regions_dir, filename)

    def save_region(self, region: Region) -> Result[bool]:
        """
        Saves region metadata (coords and screenshot path) to config.
        If temp screenshot data exists on region._temp_screenshot_data, saves
        the file and uses the resulting path. Otherwise uses region.screenshot_path
        ONLY IF it's a valid string, otherwise sets path to None.
        """
        try:
            # --- Basic Validation ---
            if not region.name or not region.platform or not region.type or not region.coordinates:
                return Result.fail(ValidationError("Invalid region data for saving", details=vars(region)))

            final_screenshot_path_to_save = None # Initialize path to None
            temp_data_attr = '_temp_screenshot_data'
            new_image_was_saved = False # Flag if we just saved a new file

            # --- Step 1: Check for and save new screenshot data ---
            if hasattr(region, temp_data_attr) and getattr(region, temp_data_attr):
                image_data = getattr(region, temp_data_attr)
                calculated_path = self._get_original_screenshot_path(region)
                self.logger.info(f"Saving new screenshot data for '{region.name}' to: {calculated_path}")

                save_img_result = self.screenshot_service.save_screenshot(image_data, calculated_path)

                if save_img_result.is_failure:
                    self.logger.error(f"Failed to save new screenshot file '{calculated_path}': {save_img_result.error}")
                    # Fail the whole save if we couldn't save the mandatory new screenshot
                    return Result.fail(ResourceError(f"Failed to save required screenshot file", inner_error=save_img_result.error))

                # Successfully saved new image, use this path
                final_screenshot_path_to_save = calculated_path
                new_image_was_saved = True # Mark that we saved a file

            # --- Step 2: If no new data, check existing path attribute ---
            elif hasattr(region, 'screenshot_path') and region.screenshot_path is not None:
                # IMPORTANT: Validate that the existing attribute value IS A STRING
                if isinstance(region.screenshot_path, str):
                    # It's a string, assume it's the correct existing path
                    final_screenshot_path_to_save = region.screenshot_path
                    self.logger.debug(f"Using existing valid screenshot path string for region '{region.name}': {final_screenshot_path_to_save}")
                else:
                    # The attribute exists but is NOT a string (e.g., the bad tuple)
                    # Log a serious warning/error and DISCARD the invalid value.
                    self.logger.error(f"Region '{region.name}' had an invalid type for screenshot_path ({type(region.screenshot_path)}). Discarding invalid path value. Value was: {repr(region.screenshot_path)}")
                    final_screenshot_path_to_save = None # Force path to None

            # --- Step 3: Prepare data for config ---
            # final_screenshot_path_to_save is now either None or a valid string path
            region_data_to_save = {
                "coordinates": list(region.coordinates),
                "screenshot_path": final_screenshot_path_to_save # Use the validated/determined path
            }

            # --- Step 4: Save to config repository ---
            platform_settings = self.config_repository.get_platform_settings(region.platform)
            key = f"{region.type}_regions"
            if key not in platform_settings: platform_settings[key] = {}
            platform_settings[key][region.name] = region_data_to_save

            result = self.config_repository.save_platform_settings(region.platform, platform_settings)

            # --- Step 5: Cleanup and Final Logging ---
            # Remove temp attribute now (if it existed)
            if hasattr(region, temp_data_attr):
                try:
                    delattr(region, temp_data_attr)
                except AttributeError:
                    pass # Ignore if already gone

            if result.is_failure:
                 if new_image_was_saved: # Log orphan only if we just saved it
                      self.logger.error(f"Config save failed after saving screenshot '{final_screenshot_path_to_save}'. File may be orphaned.")
                 return result # Propagate the config save failure

            # Update the original region object's path attribute AFTER successful save
            region.screenshot_path = final_screenshot_path_to_save

            self.logger.info(f"Saved region '{region.name}' metadata for '{region.platform}' (Screenshot: {region.screenshot_path})")
            return Result.ok(True)

        except Exception as e:
            # General error during the process
            error = ResourceError(f"Failed to save region: {e}", details={"r": region.name}, inner_error=e)
            self.logger.error(str(error), exc_info=True)
            # Clean up temp attribute in case of exception too
            if hasattr(region, '_temp_screenshot_data'):
                try: delattr(region, '_temp_screenshot_data')
                except AttributeError: pass
            return Result.fail(error)

    def get_regions_by_platform(self, platform: str, region_type: str) -> Result[List[Region]]:
        """ Get all regions for a platform of a specific type from config. """
        try:
            platform_settings = self.config_repository.get_platform_settings(platform)
            regions = []
            key = f"{region_type}_regions"
            if key in platform_settings:
                 region_dict = platform_settings[key]
                 if not isinstance(region_dict, dict): self.logger.error(f"Config error: Expected dict for '{key}' in '{platform}'."); return Result.fail(ConfigurationError(f"Invalid config structure for {key}"))

                 for name, region_data in region_dict.items():
                    if not isinstance(region_data, dict): self.logger.warning(f"Skipping region '{name}': Invalid data format."); continue
                    coords = region_data.get("coordinates")
                    screenshot_path = region_data.get("screenshot_path") # Get path from config
                    if coords is None: self.logger.warning(f"Skipping region '{name}': Missing coordinates."); continue
                    if not isinstance(coords, list) or len(coords) != 4: self.logger.warning(f"Skipping region '{name}': Invalid coords format."); continue

                    region_id = f"{platform}_{region_type}_{name}"
                    region = Region(id=region_id, name=name, coordinates=tuple(coords), type=region_type, platform=platform, screenshot_path=screenshot_path) # Use stored path
                    regions.append(region)
            self.logger.debug(f"Found {len(regions)} regions type '{region_type}' for '{platform}'.")
            return Result.ok(regions)
        except Exception as e: error = ResourceError(f"Failed get regions: {e}", details={"p": platform}, inner_error=e); self.logger.error(str(error), exc_info=True); return Result.fail(error)

    def get_region(self, platform: str, region_type: str, name: str) -> Result[Region]:
        """ Get a specific region by platform, type and name from config. """
        try:
            platform_settings = self.config_repository.get_platform_settings(platform)
            key = f"{region_type}_regions"
            if key not in platform_settings or name not in platform_settings[key]: return Result.fail(ValidationError(f"Region not found: {name}", details={"p": platform}))

            region_data = platform_settings[key][name]
            if not isinstance(region_data, dict): self.logger.error(f"Config error: Expected dict for region '{name}'."); return Result.fail(ConfigurationError(f"Invalid config for region {name}"))

            coords = region_data.get("coordinates")
            screenshot_path = region_data.get("screenshot_path") # Get path from config
            if coords is None: return Result.fail(ConfigurationError(f"Region '{name}' has no coordinates."))
            if not isinstance(coords, list) or len(coords) != 4: return Result.fail(ConfigurationError(f"Invalid coordinates format for region {name}"))

            region_id = f"{platform}_{region_type}_{name}"
            region = Region(id=region_id, name=name, coordinates=tuple(coords), type=region_type, platform=platform, screenshot_path=screenshot_path) # Use stored path
            return Result.ok(region)
        except Exception as e: error = ResourceError(f"Failed get region: {e}", details={"n": name}, inner_error=e); self.logger.error(str(error), exc_info=True); return Result.fail(error)

    def capture_region_screenshot(self, coordinates: Tuple[int, int, int, int],
                                  region_id: str, platform: str,
                                  region_type: str) -> Result[Tuple[Any, str]]:
        """ Captures screenshot data and determines the intended save path, returns both. """
        try:
            if not platform or not region_type or not region_id: return Result.fail(ValidationError("Missing info for screenshot capture"))

            parts = region_id.split('_', 2); temp_name = parts[2] if len(parts) == 3 else region_id
            temp_region = Region(id=region_id, name=temp_name, coordinates=coordinates, type=region_type, platform=platform)
            intended_screenshot_path = self._get_original_screenshot_path(temp_region)

            result = self.screenshot_service.capture_region(coordinates)
            if result.is_failure: self.logger.error(f"Capture failed for {region_id}: {result.error}"); return Result.fail(result.error)

            image_data = result.value
            self.logger.info(f"Captured screenshot data for {region_id}. Intended path: {intended_screenshot_path}")
            return Result.ok((image_data, intended_screenshot_path))
        except Exception as e: error = ResourceError(f"Failed capture data: {e}", details={"id": region_id}, inner_error=e); self.logger.error(str(error), exc_info=True); return Result.fail(error)

    def load_region_screenshot(self, region: Region) -> Result[Any]:
        """Load the screenshot for a region."""
        try:
            if not region.screenshot_path or not os.path.exists(region.screenshot_path):
                return Result.fail(ResourceError(
                    message="Screenshot not found",
                    details={"region": region.name, "path": region.screenshot_path}
                ))

            image = Image.open(region.screenshot_path)
            return Result.ok(image)
        except Exception as e:
            error = ResourceError(
                message=f"Failed to load screenshot: {e}",
                details={"region": region.name},
                inner_error=e
            )
            self.logger.error(str(error))
            return Result.fail(error)

    def delete_region(self, platform: str, region_type: str, name: str) -> Result[bool]:
        """ Delete a region's metadata and its associated original screenshot file. """
        try:
            platform_settings = self.config_repository.get_platform_settings(platform)
            key = f"{region_type}_regions"
            if key not in platform_settings or name not in platform_settings[key]: return Result.fail(
                ValidationError(f"Region not found for deletion: {name}", details={"p": platform}))

            region_data = platform_settings[key].get(name, {})
            path_value_from_config = region_data.get("screenshot_path") if isinstance(region_data, dict) else None
            screenshot_path_to_delete = None

            # Validate the path retrieved from config before trying to use it
            if isinstance(path_value_from_config, str):
                screenshot_path_to_delete = path_value_from_config
            elif path_value_from_config is not None:
                # Log if the stored value wasn't a string or None
                self.logger.warning(
                    f"Invalid screenshot_path type ({type(path_value_from_config)}) found in config for region '{name}' during deletion. Cannot delete associated file.")

            # --- Proceed with metadata deletion ---
            del platform_settings[key][name]
            result = self.config_repository.save_platform_settings(platform, platform_settings)
            if result.is_failure: self.logger.error(
                f"Failed save config after removing '{name}'. Screenshot delete aborted."); return result
            self.logger.info(f"Deleted region '{name}' metadata for '{platform}'.")

            # --- Attempt file deletion only if path was a valid string ---
            if screenshot_path_to_delete:
                if os.path.exists(screenshot_path_to_delete):
                    try:
                        os.remove(screenshot_path_to_delete); self.logger.info(
                            f"Deleted screenshot file: {screenshot_path_to_delete}")
                    except OSError as e:
                        self.logger.warning(f"Failed delete screenshot file '{screenshot_path_to_delete}': {e}")
                else:
                    self.logger.warning(f"Screenshot file not found for deletion: {screenshot_path_to_delete}")
            elif path_value_from_config is not None:
                # Logged warning above about invalid type, no deletion attempted.
                pass
            else:
                self.logger.debug(
                    f"No valid screenshot path found in config for deleted region '{name}', no file deleted.")

            return Result.ok(True)
        except Exception as e:
            error = ResourceError(f"Failed delete region: {e}", details={"n": name}, inner_error=e); self.logger.error(
                str(error), exc_info=True); return Result.fail(error)