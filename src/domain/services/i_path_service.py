# src/domain/services/i_path_service.py
from abc import ABC, abstractmethod

class IPathService(ABC):
    """Interface for a service that provides standard application paths."""

    @abstractmethod
    def get_base_data_path(self) -> str:
        """Gets the root directory for user-specific application data."""
        pass

    @abstractmethod
    def get_config_file_path(self) -> str:
        """Gets the full path to the main configuration file."""
        pass

    @abstractmethod
    def get_platform_base_path(self, platform: str) -> str:
        """Gets the base directory for a specific platform's data."""
        pass

    @abstractmethod
    def get_platform_regions_path(self, platform: str) -> str:
        """Gets the directory for storing original region screenshots for a platform."""
        pass

    @abstractmethod
    def get_platform_monitoring_path(self, platform: str) -> str:
        """Gets the directory for storing monitoring screenshots for a platform."""
        pass

    # Add other paths as needed (e.g., logs)
    # @abstractmethod
    # def get_log_file_path(self) -> str:
    #     """Gets the path for the main log file."""
    #     pass