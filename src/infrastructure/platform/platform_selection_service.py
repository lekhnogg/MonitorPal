from typing import List, Callable, Set

# --- ADD Imports ---
from src.domain.common.result import Result
from src.domain.common.errors import ConfigurationError
# --- END Imports ---

from src.domain.services.i_platform_selection_service import IPlatformSelectionService
from src.domain.services.i_config_repository_service import IConfigRepository
from src.domain.services.i_logger_service import ILoggerService
from src.domain.services.i_platform_detection_service import IPlatformDetectionService


class PlatformSelectionService(IPlatformSelectionService):
    """Service for managing platform selection throughout the application."""

    def __init__(self,
                 config_repository: IConfigRepository,
                 logger: ILoggerService,
                 platform_detection_service: IPlatformDetectionService):
        """Initialize the platform selection service."""
        self.config_repository = config_repository
        self.logger = logger
        self.platform_detection_service = platform_detection_service
        self._listeners: Set[Callable[[str], None]] = set()

    def get_current_platform(self) -> str:
        """Get the currently selected platform."""
        # Ensure config is loaded if cache is None (might be needed if service is used very early)
        # Although config repo handles this internally mostly.
        self.config_repository.load_config()
        return self.config_repository.get_current_platform()

    # --- MODIFY Method Signature and Logic ---
    def set_current_platform(self, platform: str) -> Result[bool]:
        """
        Set the current platform, save to config, and notify listeners on success.

        Returns:
            Result.ok(True) if the platform was changed and saved successfully.
            Result.ok(False) if the platform was already the current one (no change needed).
            Result.fail(error) if saving the configuration failed.
        """
        if not platform:
             self.logger.warning("Attempted to set an empty platform name.")
             # Or return Result.fail(ValidationError("Platform name cannot be empty"))
             return Result.ok(False) # Treat as no change needed for now

        current = self.get_current_platform()
        if platform == current:
            # No change needed, return success indicating no action taken
            return Result.ok(False)

        # Attempt to save to config
        save_result = self.config_repository.set_global_setting("current_platform", platform)

        if save_result.is_success:
            self.logger.info(f"Current platform changed and saved to: {platform}")

            # Notify all listeners AFTER successful save
            # Use a copy in case a listener tries to unregister during iteration
            listeners_copy = self._listeners.copy()
            for listener in listeners_copy:
                try:
                    listener(platform)
                except Exception as e:
                    self.logger.error(f"Error notifying platform change listener {listener.__qualname__}: {e}", exc_info=True)

            return Result.ok(True) # Indicate successful change and save
        else:
            # Save failed, log the error and return the failure Result
            self.logger.error(f"Failed to save platform change to '{platform}': {save_result.error}")
            # Wrap the error if needed, or return it directly
            return Result.fail(ConfigurationError(
                 message=f"Failed to save current platform setting to '{platform}'",
                 inner_error=save_result.error # Preserve original error context
            ))
    # --- END Modification ---


    def get_available_platforms(self) -> List[str]:
        """Get list of available platforms."""
        # Consider adding caching here if platform detection is slow and doesn't change often
        result = self.platform_detection_service.get_supported_platforms()
        if result.is_success and result.value: # Check if value exists
            return list(result.value.keys())
        elif result.is_failure:
             self.logger.error(f"Failed to get supported platforms: {result.error}")
        return []

    def register_platform_change_listener(self, listener: Callable[[str], None]) -> None:
        """Register a listener to be notified of platform changes."""
        if callable(listener):
            self._listeners.add(listener)
            self.logger.debug(f"Registered platform change listener: {listener.__qualname__}")
        else:
             self.logger.warning(f"Attempted to register a non-callable listener: {listener}")


    def unregister_platform_change_listener(self, listener: Callable[[str], None]) -> None:
        """Unregister a platform change listener."""
        if listener in self._listeners:
            self._listeners.remove(listener)
            self.logger.debug(f"Unregistered platform change listener: {listener.__qualname__}")