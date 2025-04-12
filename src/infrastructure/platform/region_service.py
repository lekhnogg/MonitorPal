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


    def save_region(self, region: Region) -> Result[bool]:
        """
        Saves region data (metadata & potentially screenshot file).
        Handles single 'monitor' region or named 'flatten' regions.
        """
        try:
            # --- Basic Validation ---
            if not region or not region.name or not region.platform or not region.type or not region.coordinates:
                return Result.fail(ValidationError("Invalid region data provided for saving", details=vars(region)))

            final_screenshot_path = region.screenshot_path # Start with existing path if any
            temp_data_attr = '_temp_screenshot_data'
            new_image_was_saved = False

            # --- Step 1: Check for and save new screenshot data ---
            if hasattr(region, temp_data_attr) and getattr(region, temp_data_attr):
                image_data = getattr(region, temp_data_attr)
                # Use PathService to get the correct path for this region
                # Note: For monitor type, region.name might always be 'monitor'
                calculated_path = self.path_service.get_region_screenshot_path(
                    region.platform, region.type, region.name
                )
                self.logger.info(f"Saving new screenshot data for '{region.name}' to: {calculated_path}")

                # PathService should ensure the directory exists, but save_screenshot might double-check
                save_img_result = self.screenshot_service.save_screenshot(image_data, calculated_path)

                if save_img_result.is_failure:
                    self.logger.error(f"Failed to save new screenshot file '{calculated_path}': {save_img_result.error}")
                    return Result.fail(ResourceError(f"Failed to save required screenshot file", inner_error=save_img_result.error))

                final_screenshot_path = calculated_path # Use the path where we just saved
                new_image_was_saved = True

            # --- Step 2: Prepare data dictionary for the repository ---
            # The repository now only needs the core data, not nested structure details.
            # Ensure coordinates are a list for JSON serialization.
            region_data_to_save = {
                "id": region.id,
                "name": region.name,
                "type": region.type,
                "platform": region.platform, # Include platform info if repo needs it (often doesn't)
                "coordinates": list(region.coordinates),
                "screenshot_path": final_screenshot_path # Use the determined path
            }

            # --- Step 3: Call the updated repository method ---
            # The repository now handles whether it's monitor (overwrite) or flatten (add/update dict)
            repo_save_result = self.config_repository.save_region(region.platform, region_data_to_save)

            # --- Step 4: Cleanup and Final Logging ---
            if hasattr(region, temp_data_attr):
                try: delattr(region, temp_data_attr)
                except AttributeError: pass

            if repo_save_result.is_failure:
                 if new_image_was_saved:
                      self.logger.error(f"Config save failed after saving screenshot '{final_screenshot_path}'. File may be orphaned.")
                 return repo_save_result # Propagate the config save failure

            # Update the region object passed in *after* successful save
            region.screenshot_path = final_screenshot_path

            self.logger.info(f"RegionService: Saved region '{region.name}' ({region.type}) for '{region.platform}'")
            return Result.ok(True)

        except Exception as e:
            # General error during the process
            error = ResourceError(f"RegionService failed to save region: {e}", details={"region_name": region.name if region else 'N/A'}, inner_error=e)
            self.logger.error(str(error), exc_info=True)
            if hasattr(region, '_temp_screenshot_data'):
                try: delattr(region, '_temp_screenshot_data')
                except AttributeError: pass
            return Result.fail(error)

    def get_regions_by_platform(self, platform: str, region_type: str) -> Result[List[Region]]:
        """ Get all regions for a platform of a specific type using the repository. """
        try:
            # Call the repository method which now handles single monitor / multiple flatten
            region_dicts_result = self.config_repository.get_regions_by_platform(platform, region_type)

            if region_dicts_result.is_failure:
                 # Log error if needed, but primarily propagate the Result
                 self.logger.error(f"Repository failed to get regions for {platform}/{region_type}: {region_dicts_result.error}")
                 return Result.fail(region_dicts_result.error) # Pass the failure Result up

            region_dicts = region_dicts_result.value
            regions = []
            for region_data in region_dicts:
                 # Convert dictionary back to Region object
                 try:
                      # Basic check if it looks like valid region data
                      if not isinstance(region_data, dict) or "name" not in region_data or "coordinates" not in region_data:
                           self.logger.warning(f"Skipping invalid region data structure received from repository: {region_data}")
                           continue

                      coords = region_data.get("coordinates")
                      # Ensure coordinates are a tuple
                      if isinstance(coords, list) and len(coords) == 4:
                           coords = tuple(coords)
                      elif not (isinstance(coords, tuple) and len(coords) == 4):
                           self.logger.warning(f"Skipping region '{region_data.get('name', 'N/A')}' due to invalid coordinates: {coords}")
                           continue

                      region = Region(
                          id=region_data.get("id", f"{platform}_{region_type}_{region_data['name']}"), # Construct ID if missing
                          name=region_data["name"],
                          coordinates=coords,
                          type=region_data.get("type", region_type), # Use type from data or context
                          platform=region_data.get("platform", platform), # Use platform from data or context
                          screenshot_path=region_data.get("screenshot_path")
                      )
                      regions.append(region)
                 except Exception as conversion_err:
                      # Log error during conversion of a specific region's data
                      self.logger.error(f"Error converting region data dict to Region object: {conversion_err} - Data: {region_data}", exc_info=True)
                      # Continue processing other regions

            self.logger.debug(f"RegionService: Found {len(regions)} regions type '{region_type}' for '{platform}'.")
            return Result.ok(regions)

        except Exception as e:
            # Catch errors in this service layer itself
            error = ResourceError(f"RegionService failed to get regions: {e}", details={"platform": platform, "type": region_type}, inner_error=e)
            self.logger.error(str(error), exc_info=True)
            return Result.fail(error)

    def get_region(self, platform: str, region_type: str, name: str) -> Result[Region]:
        """ Get a specific region by platform, type and name using the repository. """
        try:
            region_data: Optional[Dict[str, Any]] = None

            # Call the appropriate repository method based on type
            if region_type == "monitor":
                # For monitor, name is implicit, just get the single region
                repo_result = self.config_repository.get_monitor_region(platform)
                if repo_result.is_failure: return Result.fail(repo_result.error) # Propagate error
                region_data = repo_result.value # Value is the dict or None
                # We still check the name consistency if data exists
                if region_data and region_data.get("name") != name:
                    self.logger.warning(f"Monitor region name mismatch in config ('{region_data.get('name')}') vs requested ('{name}') for {platform}.")
                    # Decide how to handle: fail or proceed? Let's fail for consistency.
                    # return Result.fail(ConfigurationError(f"Monitor region name mismatch for {platform}"))

            elif region_type == "flatten":
                repo_result = self.config_repository.get_flatten_region(platform, name)
                if repo_result.is_failure: return Result.fail(repo_result.error) # Propagate error
                region_data = repo_result.value # Value is the dict or None
            else:
                return Result.fail(ValidationError(f"Unknown region type requested: {region_type}"))

            # Check if region data was actually found
            if region_data is None:
                return Result.fail(ValidationError(f"Region '{name}' ({region_type}) not found for platform '{platform}'."))

            # Convert dictionary back to Region object (similar logic as in get_regions_by_platform)
            coords = region_data.get("coordinates")
            if isinstance(coords, list) and len(coords) == 4: coords = tuple(coords)
            elif not (isinstance(coords, tuple) and len(coords) == 4):
                return Result.fail(ConfigurationError(f"Invalid coordinates for region {name}: {coords}"))

            region = Region(
                id=region_data.get("id", f"{platform}_{region_type}_{name}"),
                name=region_data.get("name", name), # Use name from data or the requested name
                coordinates=coords,
                type=region_data.get("type", region_type),
                platform=region_data.get("platform", platform),
                screenshot_path=region_data.get("screenshot_path")
            )
            return Result.ok(region)

        except Exception as e:
            # Catch errors in this service layer itself
            error = ResourceError(f"RegionService failed get region: {e}", details={"name": name, "type": region_type}, inner_error=e)
            self.logger.error(str(error), exc_info=True)
            return Result.fail(error)

    def get_monitor_region(self, platform: str) -> Result[Optional[Region]]:
        """Gets the single monitor region for the platform, if defined."""
        try:
            # Call the repository method which returns the dictionary or None
            repo_result = self.config_repository.get_monitor_region(platform)
            if repo_result.is_failure:
                # Propagate repository error
                return Result.fail(repo_result.error)

            region_data = repo_result.value  # This is the dict or None
            if region_data is None:
                # Monitor region is not defined, return success with None value
                return Result.ok(None)

            # Convert the dictionary received from the repository into a Region object
            coords = region_data.get("coordinates")
            if isinstance(coords, list) and len(coords) == 4:
                coords = tuple(coords)
            elif not (isinstance(coords, tuple) and len(coords) == 4):
                # Fail if coordinates are invalid in the stored data
                return Result.fail(ConfigurationError(f"Invalid coordinates found for monitor region: {coords}"))

            region = Region(
                # Use data from dict, providing defaults/context where necessary
                id=region_data.get("id", f"{platform}_monitor_monitor"),  # Use standard ID format
                name=region_data.get("name", "monitor"),  # Assume standard name
                coordinates=coords,
                type="monitor",  # Explicitly set type
                platform=region_data.get("platform", platform),  # Use platform from context
                screenshot_path=region_data.get("screenshot_path")  # Get path from data
            )
            # Return success with the created Region object
            return Result.ok(region)

        except Exception as e:
            # Catch unexpected errors during processing within this service method
            error = ResourceError(f"RegionService failed get_monitor_region: {e}", details={"platform": platform},
                                  inner_error=e)
            self.logger.error(str(error), exc_info=True)
            return Result.fail(error)

    def capture_region_screenshot(self, coordinates: Tuple[int, int, int, int],
                                  region_id: str, platform: str,
                                  region_type: str) -> Result[Tuple[Any, str]]:
        """ Captures screenshot data and determines the intended save path using PathService. """
        try:
            # Validate inputs
            if not platform or not region_type or not region_id or not coordinates:
                 return Result.fail(ValidationError("Missing required information for screenshot capture"))

            # --- Determine intended path using PathService ---
            # Extract name part from ID if needed by path service, or pass full ID
            parts = region_id.split('_', 2)
            region_name_for_path = parts[2] if len(parts) == 3 else region_id # Extract name if possible
            if region_type == "monitor": region_name_for_path = "monitor" # Standardize name for monitor path

            intended_screenshot_path = self.path_service.get_region_screenshot_path(
                 platform, region_type, region_name_for_path
            )
            # --- End Path Determination ---

            # Capture the actual screenshot data
            capture_result = self.screenshot_service.capture_region(coordinates)
            if capture_result.is_failure:
                 self.logger.error(f"Screenshot capture failed for region {region_id}: {capture_result.error}")
                 return Result.fail(capture_result.error) # Propagate capture error

            image_data = capture_result.value
            self.logger.info(f"Captured screenshot data for {region_id}. Intended save path: {intended_screenshot_path}")
            # Return both the image data and the path where it *should* be saved
            return Result.ok((image_data, intended_screenshot_path))

        except Exception as e:
            error = ResourceError(f"RegionService failed capture_region_screenshot: {e}", details={"region_id": region_id}, inner_error=e)
            self.logger.error(str(error), exc_info=True)
            return Result.fail(error)

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
        """ Deletes a region's metadata via repository and its associated screenshot file. """
        try:
            # --- Determine screenshot path BEFORE deleting metadata ---
            screenshot_path_to_delete = None
            # Use PathService to predict the path based on standard naming
            # Standardize name for monitor type
            name_for_path = "monitor" if region_type == "monitor" else name
            try:
                 screenshot_path_to_delete = self.path_service.get_region_screenshot_path(
                      platform, region_type, name_for_path
                 )
            except Exception as path_err:
                 # Log if path generation fails, but proceed with metadata deletion
                 self.logger.warning(f"Could not determine screenshot path for potential deletion of {platform}/{region_type}/{name}: {path_err}")


            # --- Call the repository to delete the metadata ---
            # The repository handles setting monitor to None or removing flatten key
            repo_delete_result = self.config_repository.delete_region(platform, region_type, name)

            if repo_delete_result.is_failure:
                # If deleting metadata fails, stop and report error
                self.logger.error(f"Repository failed to delete region metadata for {platform}/{name}: {repo_delete_result.error}")
                return repo_delete_result # Propagate error
            # If repo call returns success=False (meaning region wasn't found), treat as success here.
            elif not repo_delete_result.value:
                 self.logger.warning(f"Repository reported region '{name}' ({region_type}) not found for platform '{platform}' during deletion.")
                 # Still attempt to delete file if path was determined? Optional, maybe safer not to.
                 screenshot_path_to_delete = None # Avoid deleting file if metadata wasn't found

            self.logger.info(f"RegionService: Deleted region '{name}' metadata for '{platform}'.")

            # --- Attempt file deletion if path was determined AND metadata deletion succeeded ---
            if screenshot_path_to_delete:
                if os.path.exists(screenshot_path_to_delete):
                    try:
                        os.remove(screenshot_path_to_delete)
                        self.logger.info(f"Deleted screenshot file: {screenshot_path_to_delete}")
                    except OSError as e:
                        # Log warning but don't fail the whole operation just for file deletion failure
                        self.logger.warning(f"Failed to delete screenshot file '{screenshot_path_to_delete}': {e}")
                else:
                    # Log if the predicted file wasn't there anyway
                    self.logger.debug(f"Screenshot file determined for deletion not found: {screenshot_path_to_delete}")

            return Result.ok(True) # Overall success (metadata deleted)

        except Exception as e:
            error = ResourceError(f"RegionService failed to delete region: {e}", details={"name": name, "type": region_type}, inner_error=e)
            self.logger.error(str(error), exc_info=True)
            return Result.fail(error)