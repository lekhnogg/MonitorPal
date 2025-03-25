# src/infrastructure/platform/region_service.py
import os
from typing import List, Dict, Optional, Tuple, Any
from PIL import Image

from src.domain.services.i_region_service import IRegionService
from src.domain.services.i_config_repository_service import IConfigRepository
from src.domain.services.i_screenshot_service import IScreenshotService
from src.domain.services.i_logger_service import ILoggerService
from src.domain.models.region_model import Region
from src.domain.common.result import Result
from src.domain.common.errors import ResourceError, ValidationError


class RegionService(IRegionService):
    """Service implementation for managing screen regions."""

    def __init__(self, config_repository: IConfigRepository,
                 screenshot_service: IScreenshotService,
                 logger: ILoggerService):
        self.config_repository = config_repository
        self.screenshot_service = screenshot_service
        self.logger = logger
        self.base_dir = os.path.join(os.getcwd(), "data", "screenshots")
        os.makedirs(self.base_dir, exist_ok=True)

    def save_region(self, region: Region) -> Result[bool]:
        """Save a region with its screenshot."""
        try:
            # Validate region
            if not region.name or not region.platform or not region.type:
                return Result.fail(ValidationError(
                    message="Invalid region data",
                    details={"region": str(region)}
                ))

            # Get platform settings
            platform_settings = self.config_repository.get_platform_settings(region.platform)

            # Update the appropriate region collection
            key = f"{region.type}_regions"
            if key not in platform_settings:
                platform_settings[key] = {}

            # Store only coordinates in config
            platform_settings[key][region.name] = list(region.coordinates)

            # Save updated settings
            result = self.config_repository.save_platform_settings(region.platform, platform_settings)
            if result.is_failure:
                return result

            self.logger.info(f"Saved region {region.name} for platform {region.platform}")
            return Result.ok(True)
        except Exception as e:
            error = ResourceError(
                message=f"Failed to save region: {e}",
                details={"region": region.name, "platform": region.platform},
                inner_error=e
            )
            self.logger.error(str(error))
            return Result.fail(error)

    def get_regions_by_platform(self, platform: str, region_type: str) -> Result[List[Region]]:
        """Get all regions for a platform of a specific type."""
        try:
            platform_settings = self.config_repository.get_platform_settings(platform)
            regions = []

            key = f"{region_type}_regions"
            if key in platform_settings:
                for name, coords in platform_settings[key].items():
                    # Create region model
                    region_id = f"{platform}_{region_type}_{name}"

                    # Check if screenshot exists
                    screenshot_path = self._get_screenshot_path(region_id, platform, region_type)
                    if not os.path.exists(screenshot_path):
                        screenshot_path = None

                    region = Region(
                        id=region_id,
                        name=name,
                        coordinates=tuple(coords),
                        type=region_type,
                        platform=platform,
                        screenshot_path=screenshot_path
                    )
                    regions.append(region)

            return Result.ok(regions)
        except Exception as e:
            error = ResourceError(
                message=f"Failed to get regions: {e}",
                details={"platform": platform, "type": region_type},
                inner_error=e
            )
            self.logger.error(str(error))
            return Result.fail(error)

    def get_region(self, platform: str, region_type: str, name: str) -> Result[Region]:
        """Get a specific region by platform, type and name."""
        try:
            platform_settings = self.config_repository.get_platform_settings(platform)

            key = f"{region_type}_regions"
            if key not in platform_settings or name not in platform_settings[key]:
                return Result.fail(ValidationError(
                    message=f"Region not found: {name}",
                    details={"platform": platform, "type": region_type, "name": name}
                ))

            coords = platform_settings[key][name]
            region_id = f"{platform}_{region_type}_{name}"

            # Check if screenshot exists
            screenshot_path = self._get_screenshot_path(region_id, platform, region_type)
            if not os.path.exists(screenshot_path):
                screenshot_path = None

            region = Region(
                id=region_id,
                name=name,
                coordinates=tuple(coords),
                type=region_type,
                platform=platform,
                screenshot_path=screenshot_path
            )

            return Result.ok(region)
        except Exception as e:
            error = ResourceError(
                message=f"Failed to get region: {e}",
                details={"platform": platform, "type": region_type, "name": name},
                inner_error=e
            )
            self.logger.error(str(error))
            return Result.fail(error)

    def capture_region_screenshot(self, coordinates: Tuple[int, int, int, int],
                                  region_id: str, platform: str,
                                  region_type: str) -> Result[str]:
        """Capture and save a screenshot for a region."""
        try:
            # Ensure directory exists
            directory = os.path.join(self.base_dir, platform, region_type)
            os.makedirs(directory, exist_ok=True)

            # Generate filename
            screenshot_path = self._get_screenshot_path(region_id, platform, region_type)

            # Capture and save
            result = self.screenshot_service.capture_and_save(coordinates, screenshot_path)
            if result.is_failure:
                return result

            return Result.ok(screenshot_path)
        except Exception as e:
            error = ResourceError(
                message=f"Failed to capture screenshot: {e}",
                details={"region_id": region_id},
                inner_error=e
            )
            self.logger.error(str(error))
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
        """Delete a region."""
        try:
            platform_settings = self.config_repository.get_platform_settings(platform)

            key = f"{region_type}_regions"
            if key not in platform_settings or name not in platform_settings[key]:
                return Result.fail(ValidationError(
                    message=f"Region not found: {name}",
                    details={"platform": platform, "type": region_type, "name": name}
                ))

            # Remove from settings
            del platform_settings[key][name]

            # Save updated settings
            result = self.config_repository.save_platform_settings(platform, platform_settings)
            if result.is_failure:
                return result

            # Try to delete screenshot if it exists
            region_id = f"{platform}_{region_type}_{name}"
            screenshot_path = self._get_screenshot_path(region_id, platform, region_type)
            if os.path.exists(screenshot_path):
                try:
                    os.remove(screenshot_path)
                except Exception as e:
                    self.logger.warning(f"Failed to delete screenshot file: {e}")

            self.logger.info(f"Deleted region {name} for platform {platform}")
            return Result.ok(True)
        except Exception as e:
            error = ResourceError(
                message=f"Failed to delete region: {e}",
                details={"platform": platform, "type": region_type, "name": name},
                inner_error=e
            )
            self.logger.error(str(error))
            return Result.fail(error)

    def _get_screenshot_path(self, region_id: str, platform: str, region_type: str) -> str:
        """Get the path where a screenshot should be stored."""
        directory = os.path.join(self.base_dir, platform, region_type)
        return os.path.join(directory, f"{region_id}.png")