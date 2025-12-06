"""
Zenith Star Chart Widget

Full-sky star chart showing the entire visible sky from the zenith (straight up).
Uses starplot's ZenithPlot for a complete overhead view.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import io
import logging
import threading
from collections.abc import Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QProgressDialog,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


# Starplot and duckdb are imported in main.py before deal.activate() is called
# This ensures they're cached in sys.modules and avoid deal's import hook

if TYPE_CHECKING:
    from celestron_nexstar import NexStarTelescope

logger = logging.getLogger(__name__)


def _run_async_safe(coro: Coroutine[Any, Any, Any]) -> Any:
    """
    Run an async coroutine from a sync context, handling both cases:
    - If called from sync context: uses asyncio.run()
    - If called from async context: creates new event loop in thread

    Args:
        coro: The coroutine to run

    Returns:
        The result of the coroutine
    """
    try:
        # Check if we're in an async context
        asyncio.get_running_loop()
        # We're in an async context, need to use a thread with new event loop
        future: concurrent.futures.Future[Any] = concurrent.futures.Future()

        def run_in_thread() -> None:
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                result = new_loop.run_until_complete(coro)
                future.set_result(result)
                new_loop.close()
            except Exception as e:
                future.set_exception(e)

        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join()
        return future.result()
    except RuntimeError:
        # No running loop, use asyncio.run()
        return asyncio.run(coro)


class ZenithStarChartWidget(QWidget):
    """Zenith star chart widget showing full sky view using starplot."""

    def __init__(
        self,
        parent: QWidget | None = None,
        telescope: NexStarTelescope | None = None,
    ) -> None:
        """Initialize the zenith star chart widget."""
        super().__init__(parent)

        self.telescope = telescope

        # View state
        self.magnitude_limit = 4.6  # Maximum magnitude to display (matching example)
        self.magnitude_limit_labels = 2.4  # Maximum magnitude for labels (matching example)

        # Chart generation thread (will be created on first update)
        self._chart_thread: _ChartGenerationThread | None = None

        # Loading dialog (will be created when needed)
        self._loading_dialog: QProgressDialog | None = None

        # Create UI
        self._create_ui()

        # Update timer for periodic updates (only if telescope is connected)
        # Sky chart doesn't need frequent updates - stars move slowly
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_chart)
        # Only auto-update if telescope is connected (to track movement)
        # Otherwise, update manually or on view changes
        if telescope and hasattr(telescope, "is_connected") and telescope.is_connected():
            self.update_timer.start(60000)  # Update every 60 seconds when tracking telescope
        else:
            # No auto-updates if no telescope - user can manually refresh
            self.update_timer.stop()

        # Initial chart generation
        self._update_chart()

    def _create_ui(self) -> None:
        """Create the UI layout and controls."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Controls toolbar
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(5, 5, 5, 5)

        # Info label
        self.info_label = QLabel("Full Sky View")
        controls_layout.addWidget(self.info_label)

        controls_layout.addStretch()

        # Refresh button
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._update_chart)
        controls_layout.addWidget(refresh_btn)

        layout.addLayout(controls_layout)

        # Image label to display the star chart
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(800, 800)
        self.image_label.setStyleSheet("background-color: black;")
        layout.addWidget(self.image_label)

    def _update_chart(self) -> None:
        """Update the star chart display in a background thread."""
        # Cancel any existing chart generation thread
        if self._chart_thread is not None and self._chart_thread.isRunning():
            self._chart_thread.terminate()
            self._chart_thread.wait()

        # Close any existing loading dialog
        if self._loading_dialog is not None:
            self._loading_dialog.close()
            self._loading_dialog = None

        # Show loading dialog
        self._loading_dialog = QProgressDialog("Generating star chart...", None, 0, 0, self)
        self._loading_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self._loading_dialog.setCancelButton(None)  # Disable cancel button
        self._loading_dialog.setMinimumDuration(0)  # Show immediately
        self._loading_dialog.show()

        # Process events to show the dialog immediately
        QApplication.processEvents()

        # Determine style based on theme (must be done in main thread)
        from PySide6.QtGui import QGuiApplication, QPalette

        app = QGuiApplication.instance()
        is_dark = False
        if app and isinstance(app, QGuiApplication):
            palette = app.palette()
            window_color = palette.color(QPalette.ColorRole.Window)
            brightness = window_color.lightness()
            is_dark = brightness < 128

        # Create and start chart generation thread
        self._chart_thread = _ChartGenerationThread(
            magnitude_limit=self.magnitude_limit,
            magnitude_limit_labels=self.magnitude_limit_labels,
            telescope=self.telescope,  # Pass telescope so thread can query it
            is_dark_theme=is_dark,  # Pass theme info to avoid Qt access in background thread
        )
        self._chart_thread.image_ready.connect(self._on_image_ready)
        self._chart_thread.finished.connect(self._on_chart_generation_finished)
        self._chart_thread.start()

        # Set timeout to close dialog if thread hangs (60 seconds)
        QTimer.singleShot(60000, self._on_generation_timeout)

    def _on_image_ready(self, image_data: bytes) -> None:
        """Handle image ready signal from background thread."""
        # Close loading dialog when image is ready (or if empty, indicating error)
        if self._loading_dialog is not None:
            self._loading_dialog.close()
            self._loading_dialog = None

        # If image data is empty, there was an error - don't try to display
        if not image_data:
            logger.warning("Received empty image data, skipping display")
            return

        # Load into QPixmap and display
        # QPixmap has size limits (typically 128-256MB), so we need to scale large images
        # before loading them into QPixmap
        from PySide6.QtGui import QImage

        # First load as QImage (no size limit), then convert to QPixmap after scaling
        image = QImage()
        if not image.loadFromData(image_data):
            logger.error("Failed to load star chart image data")
            return

        # Check if image is too large for QPixmap (estimate: width * height * 4 bytes per pixel)
        # QPixmap limit is typically around 128-256MB, so we'll use 100MB as a safe limit
        estimated_size_mb = (image.width() * image.height() * 4) / (1024 * 1024)
        max_size_mb = 100  # Safe limit for QPixmap

        if estimated_size_mb > max_size_mb:
            # Scale down the image before converting to QPixmap
            scale_factor = (max_size_mb / estimated_size_mb) ** 0.5  # Square root for width/height
            new_width = int(image.width() * scale_factor)
            new_height = int(image.height() * scale_factor)
            logger.info(
                f"Image too large ({estimated_size_mb:.1f}MB), scaling from {image.width()}x{image.height()} "
                f"to {new_width}x{new_height} before loading into QPixmap"
            )
            image = image.scaled(
                new_width,
                new_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

        # Convert to QPixmap and scale to fit label
        pixmap = QPixmap.fromImage(image)
        if not pixmap.isNull():
            # Scale to fit label while maintaining aspect ratio
            scaled_pixmap = pixmap.scaled(
                self.image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.image_label.setPixmap(scaled_pixmap)
        else:
            logger.error("Failed to convert image to QPixmap")

    def _on_chart_generation_finished(self) -> None:
        """Handle chart generation thread finished signal."""
        # Close loading dialog
        if self._loading_dialog is not None:
            self._loading_dialog.close()
            self._loading_dialog = None

    def _on_generation_timeout(self) -> None:
        """Handle timeout if generation takes too long."""
        if self._loading_dialog is not None and self._loading_dialog.isVisible():
            logger.warning("Star chart generation timed out after 60 seconds")
            self._loading_dialog.close()
            self._loading_dialog = None
            # Terminate the thread if it's still running
            if self._chart_thread is not None and self._chart_thread.isRunning():
                logger.warning("Terminating hung chart generation thread")
                self._chart_thread.terminate()
                self._chart_thread.wait(5000)  # Wait up to 5 seconds for termination

    def resizeEvent(self, event: Any) -> None:  # noqa: N802
        """Handle widget resize - update image scaling."""
        super().resizeEvent(event)  # type: ignore[arg-type]
        # Don't regenerate on resize - just scale the existing image
        # Regenerating on every resize would be too expensive
        if hasattr(self, "image_label") and self.image_label.pixmap():
            # Just rescale the existing pixmap
            pixmap = self.image_label.pixmap()
            if pixmap:
                scaled_pixmap = pixmap.scaled(
                    self.image_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.image_label.setPixmap(scaled_pixmap)


class _ChartGenerationThread(QThread):
    """Background thread for generating star chart images."""

    image_ready = Signal(bytes)  # type: ignore[arg-type]

    def __init__(
        self,
        magnitude_limit: float,
        magnitude_limit_labels: float,
        telescope: NexStarTelescope | None = None,
        is_dark_theme: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the chart generation thread."""
        super().__init__(parent)
        self.magnitude_limit = magnitude_limit
        self.magnitude_limit_labels = magnitude_limit_labels
        self.telescope = telescope
        self.is_dark_theme = is_dark_theme

    def run(self) -> None:
        """Generate the star chart image in background thread."""
        try:
            logger.info("Starting star chart generation...")

            logger.debug("Importing starplot...")
            # Import starplot - deal.activate() is no longer called, so imports work normally
            import starplot

            zenith_plot = starplot.ZenithPlot
            observer = starplot.Observer
            styles = starplot.styles

            logger.debug("Getting observer location...")
            # Get observer location and time
            from celestron_nexstar.api.location.observer import get_observer_location

            location = get_observer_location()
            now = datetime.now(UTC)

            logger.debug("Getting ephemeris file path...")
            # Get ephemeris file path (use downloaded ephemeris if available)
            from celestron_nexstar.api.ephemeris.ephemeris_manager import get_ephemeris_directory

            ephemeris_dir = get_ephemeris_directory()
            # Try to find an available ephemeris file (prefer de421 or de440)
            ephemeris_file = None
            for preferred_name in ["de421.bsp", "de440.bsp", "de421_2001.bsp"]:
                eph_path = ephemeris_dir / preferred_name
                if eph_path.exists():
                    ephemeris_file = preferred_name
                    logger.debug(f"Using ephemeris file: {ephemeris_file}")
                    break

            # If no preferred file found, use default (starplot will handle it)
            if ephemeris_file is None:
                ephemeris_file = "de421_2001.bsp"  # Starplot default
                logger.debug(f"No ephemeris file found, using starplot default: {ephemeris_file}")

            logger.debug("Creating starplot observer...")
            # Create observer
            starplot_observer = observer(
                dt=now,
                lat=location.latitude,
                lon=location.longitude,
            )

            logger.debug("Determining plot style...")
            # Determine style based on theme (passed from main thread to avoid Qt access in background thread)
            if self.is_dark_theme:
                plot_style = styles.PlotStyle().extend(styles.extensions.BLUE_NIGHT)
            else:
                plot_style = styles.PlotStyle().extend(styles.extensions.BLUE_LIGHT)

            logger.info("Creating zenith plot...")
            # Create zenith plot (full sky view from above)
            # Based on example: https://starplot.dev/examples/star-chart-basic/
            plot = zenith_plot(
                observer=starplot_observer,
                ephemeris=ephemeris_file,  # Use downloaded ephemeris file
                style=plot_style,
                resolution=4096,
                autoscale=True,  # Automatically scale for best appearance
            )
            logger.debug("Zenith plot created successfully")

            logger.debug("Adding horizon...")
            plot.horizon()
            logger.debug("Horizon added successfully")

            logger.debug("Adding constellations...")
            plot.constellations()
            logger.debug("Constellations added successfully")

            logger.debug("Adding stars...")
            # Add stars (filter by magnitude)
            # Starplot uses ibis expressions for filtering
            from starplot import _  # type: ignore[import-untyped]

            plot.stars(
                where=[_.magnitude < self.magnitude_limit],
                where_labels=[_.magnitude < self.magnitude_limit_labels],
            )  # type: ignore[arg-type]
            logger.debug("Stars added successfully")

            logger.debug("Adding constellation labels...")
            # Constellation labels may fail in background thread due to font loading issues
            # Wrap in try/except to gracefully handle the error
            try:
                plot.constellation_labels()
                logger.debug("Constellation labels added successfully")
            except RuntimeError as e:
                if "reentrant" in str(e).lower() or "font" in str(e).lower() or "glyph" in str(e).lower():
                    logger.warning("Could not render constellation labels (font loading issue in background thread)")
                else:
                    raise

            logger.info("Exporting plot to PNG...")
            # Export to PNG in memory
            img_buffer = io.BytesIO()
            plot.export(img_buffer, format="png", transparent=True, padding=0.1)  # type: ignore[no-untyped-call]
            img_buffer.seek(0)
            image_data = img_buffer.read()

            logger.info(f"Star chart generation complete, image size: {len(image_data)} bytes")

            # DEBUG: Save image to file for verification (only first time, then overwrite)
            # This prevents accumulating many files during testing
            debug_dir = Path.home() / ".cache" / "celestron-nexstar" / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            debug_file = debug_dir / "zenith_star_chart_debug.png"  # Single file, overwritten each time
            try:
                with open(debug_file, "wb") as f:
                    f.write(image_data)
                logger.debug(f"DEBUG: Saved star chart image to {debug_file}")
            except Exception as e:
                logger.warning(f"DEBUG: Could not save image to file: {e}")

            # Emit signal with image data (will be handled in main thread)
            self.image_ready.emit(image_data)

        except Exception as e:
            logger.error(f"Error generating star chart: {e}", exc_info=True)
            # Emit empty image data to signal completion even on error
            # This ensures the loading dialog closes
            self.image_ready.emit(b"")
