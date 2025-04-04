# src/infrastructure/platform/screenshot_service.py
"""
Qt-native implementation of the screenshot service using QScreen.
"""
from typing import Tuple, Optional
from PIL import Image
import io
import os

from PySide6.QtCore import QByteArray, QBuffer, QRect
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap, QImage

from src.domain.services.i_screenshot_service import IScreenshotService
from src.domain.services.i_logger_service import ILoggerService
from src.domain.common.result import Result
from src.domain.common.errors import ResourceError, ValidationError


class QtScreenshotService(IScreenshotService):
    """
    Qt-native implementation of the screenshot service using QScreen.

    This service captures screenshots using Qt's native screenshot capabilities
    and processes them with the Python Imaging Library (PIL).
    """

    def __init__(self, logger: ILoggerService):
        """
        Initialize the screenshot service.

        Args:
            logger: Logger service for logging
        """
        self.logger = logger

    def capture_region(self, region: Tuple[int, int, int, int]) -> Result[Image.Image]:
        """
        Capture a screenshot of a specific region using Qt's native capabilities.

        Args:
            region: (left, top, width, height) of screen region to capture

        Returns:
            Result containing the captured PIL Image on success
        """
        try:
            # Validate region
            if not region or len(region) != 4:
                return Result.fail(ValidationError(
                    message="Invalid region format",
                    details={"region": region, "expected": "(left, top, width, height)"}
                ))

            self.logger.debug(f"Capturing screenshot of region: {region}")
            left, top, width, height = region

            # Get all available screens
            app = QApplication.instance()
            screens = app.screens()

            self.logger.debug(f"Total monitors detected: {len(screens)}")

            # Find which screen contains the majority of this region
            target_screen = None
            best_overlap_area = 0

            for screen in screens:
                geometry = screen.geometry()
                screen_rect = QRect(geometry.x(), geometry.y(), geometry.width(), geometry.height())
                region_rect = QRect(left, top, width, height)

                # Calculate the intersection area
                intersection = screen_rect.intersected(region_rect)
                if intersection.isValid():
                    overlap_area = intersection.width() * intersection.height()
                    if overlap_area > best_overlap_area:
                        best_overlap_area = overlap_area
                        target_screen = screen

            # If no screen contains the region, use the primary screen
            if not target_screen:
                self.logger.debug(f"Region doesn't appear to be contained fully within any monitor")
                target_screen = QApplication.primaryScreen()
                self.logger.debug(f"Using primary screen for capture: {target_screen.name()}")
            else:
                self.logger.debug(f"Region appears to be on monitor #{screens.index(target_screen) + 1}")

            # Get the screen geometry to calculate relative coordinates
            screen_geo = target_screen.geometry()

            # Calculate coordinates relative to the target screen
            relative_left = left - screen_geo.x()
            relative_top = top - screen_geo.y()

            # Capture the screenshot using the calculated coordinates
            pixmap = target_screen.grabWindow(0, relative_left, relative_top, width, height)

            if pixmap.isNull():
                return Result.fail(ResourceError(
                    message="Failed to capture screenshot, resulting pixmap is null",
                    details={"region": region}
                ))

            # Convert QPixmap to PIL Image
            self.logger.debug(f"Converting QPixmap to PIL Image...")
            image = self._qpixmap_to_pil(pixmap)
            if not image:
                return Result.fail(ResourceError(
                    message="Failed to convert QPixmap to PIL Image",
                    details={"region": region}
                ))
            return Result.ok(image)
        except Exception as e:
            return Result.fail(ResourceError(
                message="Failed to capture screenshot",
                details={"region": region},
                inner_error=e
            ))

    def _qpixmap_to_pil(self, pixmap: QPixmap) -> Optional[Image.Image]:
        """Convert QPixmap to PIL Image using an intermediate buffer."""
        try:
            # Save QPixmap to a byte array in PNG format
            byte_array = QByteArray()
            buffer = QBuffer(byte_array)
            buffer.open(QBuffer.WriteOnly)
            pixmap.save(buffer, "PNG")
            buffer.close()

            # Load byte data into PIL Image
            return Image.open(io.BytesIO(byte_array.data()))
        except Exception as e:
            self.logger.error(f"Error converting QPixmap to PIL Image: {e}")
            return None

    def to_pyside_pixmap(self, image: Image.Image) -> Result[QPixmap]:
        """
        Convert a PIL Image to a PySide6 QPixmap.

        Args:
            image: PIL Image to convert

        Returns:
            Result containing the QPixmap on success
        """
        try:
            image_bytes = self._image_to_bytes(image)
            if isinstance(image_bytes, Result):
                if image_bytes.is_failure:
                    return image_bytes
                image_bytes = image_bytes.value

            # Create and load the QPixmap directly from bytes
            pixmap = QPixmap()
            success = pixmap.loadFromData(image_bytes)

            if not success or pixmap.isNull():
                return Result.fail(ResourceError(
                    message="Failed to convert image to QPixmap",
                    details={"image_size": f"{image.width}x{image.height}"}
                ))

            self.logger.debug(f"Converted PIL Image to QPixmap: {pixmap.width()}x{pixmap.height()}")
            return Result.ok(pixmap)
        except Exception as e:
            return Result.fail(ResourceError(
                message="Failed to convert image to QPixmap",
                inner_error=e
            ))

    def save_screenshot(self, image: Image.Image, path: str) -> Result[str]:
        """
        Save a screenshot to disk.

        Args:
            image: PIL Image to save
            path: Path where to save the screenshot

        Returns:
            Result containing the saved file path on success
        """
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

            # Save image
            image.save(path)
            self.logger.debug(f"Screenshot saved to {path}")

            return Result.ok(path)
        except Exception as e:
            return Result.fail(ResourceError(
                message="Failed to save screenshot",
                details={"path": path},
                inner_error=e
            ))

    def capture_and_save(self, region: Tuple[int, int, int, int], path: str) -> Result[str]:
        """
        Capture a screenshot of a region and save it to disk.

        Args:
            region: (left, top, width, height) of screen region to capture
            path: Path where to save the screenshot

        Returns:
            Result containing the saved file path on success
        """
        capture_result = self.capture_region(region)
        if capture_result.is_failure:
            return capture_result  # Return the failure result directly

        return self.save_screenshot(capture_result.value, path)

    def _image_to_bytes(self, image: Image.Image) -> Result[bytes]:
        """
        Internal helper to convert a PIL Image to bytes.
        """
        try:
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format='PNG')
            return Result.ok(img_byte_arr.getvalue())
        except Exception as e:
            return Result.fail(ResourceError(
                message="Failed to convert image to bytes",
                inner_error=e
            ))

    def to_bytes(self, image: Image.Image) -> Result[bytes]:
        """
        Convert a PIL Image to bytes.

        Args:
            image: PIL Image to convert

        Returns:
            Result containing the image bytes on success
        """
        result = self._image_to_bytes(image)
        if result.is_success:
            self.logger.debug(f"Converted image to bytes, size: {len(result.value)} bytes")
        return result