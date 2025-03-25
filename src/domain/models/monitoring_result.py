#src/domain/models/monitoring_result.py
"""
Monitoring result model for representing the outcome of a monitoring check.

Contains information about detected values, thresholds, and whether a threshold was exceeded.
"""
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class MonitoringResult:
    """
    Model representing the result of a monitoring check.

    Attributes:
        values: List of detected numeric values
        minimum_value: The minimum value detected (typically the P&L)
        threshold: The threshold that was being monitored against
        threshold_exceeded: Whether the threshold was exceeded
        raw_text: The raw text extracted from the OCR
        timestamp: The timestamp of the check
        region_name: Name of the region being monitored
        screenshot_path: Optional path to the screenshot that was taken
    """
    values: List[float]
    minimum_value: float
    threshold: float
    threshold_exceeded: bool
    raw_text: str
    timestamp: float
    region_name: str
    screenshot_path: Optional[str] = None

    @property
    def has_values(self) -> bool:
        """Check if any values were detected."""
        return len(self.values) > 0