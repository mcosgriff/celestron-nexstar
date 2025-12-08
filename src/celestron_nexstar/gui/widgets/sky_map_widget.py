"""
Interactive Sky Map Widget

Real-time sky view showing current telescope position, celestial objects, and constellation lines.
Uses starplot library for high-quality astronomical charts.
"""

from __future__ import annotations

import io
import logging
from datetime import UTC, datetime
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


class SkyMapWidget(QWidget):
    """Interactive sky map widget showing stars and celestial objects using starplot."""

    def __init__(
        self,
        parent: QWidget | None = None,
        telescope: NexStarTelescope | None = None,
    ) -> None:
        """Initialize the sky map widget."""
        super().__init__(parent)

        self.telescope = telescope

        # View state
        self.magnitude_limit = 6.0  # Maximum magnitude to display

        # Calculate default view based on observer location
        # This ensures the default is appropriate for the user's location
        try:
            from celestron_nexstar.api.location.observer import get_observer_location

            location = get_observer_location()
            # For northern hemisphere: use South (180°), for southern: use North (0°)
            # This shows the celestial pole region which is most useful
            self.azimuth = 180.0 if location.latitude >= 0 else 0.0
            # Use a good viewing angle: 60-70° is optimal for most observing
            # Slightly adjust based on latitude for better default view
            self.altitude = max(50.0, min(70.0, 60.0 + abs(location.latitude) * 0.1))
        except Exception:
            # Fallback to reasonable defaults if location can't be determined
            self.azimuth = 180.0
            self.altitude = 60.0

        # Map generation thread (will be created on first update)
        self._map_thread: _MapGenerationThread | None = None

        # Loading dialog (will be created when needed)
        self._loading_dialog: QProgressDialog | None = None

        # Create UI
        self._create_ui()

        # Update timer for periodic updates (only if telescope is connected)
        # Sky map doesn't need frequent updates - stars move slowly
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_map)
        # Only auto-update if telescope is connected (to track movement)
        # Otherwise, update manually or on view changes
        if telescope and hasattr(telescope, "is_connected") and telescope.is_connected():
            self.update_timer.start(30000)  # Update every 30 seconds when tracking telescope
        else:
            # No auto-updates if no telescope - user can manually refresh
            self.update_timer.stop()

        # Initial map generation
        self._update_map()

    def _create_ui(self) -> None:
        """Create the UI layout and controls."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Controls toolbar
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(5, 5, 5, 5)

        # Coordinate system label (will be updated with actual values)
        self.coord_label = QLabel("Azimuth: --°  Altitude: --°")
        controls_layout.addWidget(self.coord_label)

        controls_layout.addStretch()

        # Reset button
        reset_btn = QPushButton("Reset View")
        reset_btn.clicked.connect(self._reset_view)
        controls_layout.addWidget(reset_btn)

        layout.addLayout(controls_layout)

        # Image label to display the star chart
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(800, 800)
        self.image_label.setStyleSheet("background-color: black;")
        layout.addWidget(self.image_label)

    def _update_map(self) -> None:
        """Update the sky map display in a background thread."""
        # Cancel any existing map generation thread
        if self._map_thread is not None and self._map_thread.isRunning():
            self._map_thread.terminate()
            self._map_thread.wait()

        # Close any existing loading dialog
        if self._loading_dialog is not None:
            self._loading_dialog.close()
            self._loading_dialog = None

        # Show loading dialog
        self._loading_dialog = QProgressDialog("Generating sky map...", None, 0, 0, self)
        self._loading_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self._loading_dialog.setCancelButton(None)  # Disable cancel button
        self._loading_dialog.setMinimumDuration(0)  # Show immediately
        self._loading_dialog.show()

        # Process events to show the dialog immediately
        QApplication.processEvents()

        # Set timeout to close dialog if thread hangs (60 seconds)
        QTimer.singleShot(60000, self._on_generation_timeout)

        # Determine style based on theme (must be done in main thread)
        from PySide6.QtGui import QGuiApplication, QPalette

        app = QGuiApplication.instance()
        is_dark = False
        if app and isinstance(app, QGuiApplication):
            palette = app.palette()
            window_color = palette.color(QPalette.ColorRole.Window)
            brightness = window_color.lightness()
            is_dark = brightness < 128

        # Use current view state (will be updated from telescope in background thread if connected)
        azimuth = self.azimuth
        altitude = self.altitude

        # Create and start map generation thread
        self._map_thread = _MapGenerationThread(
            magnitude_limit=self.magnitude_limit,
            azimuth=azimuth,
            altitude=altitude,
            telescope=self.telescope,  # Pass telescope so thread can query it
            is_dark_theme=is_dark,  # Pass theme info to avoid Qt access in background thread
        )
        self._map_thread.image_ready.connect(self._on_image_ready)
        self._map_thread.finished.connect(self._on_map_generation_finished)
        self._map_thread.start()

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
        pixmap = QPixmap()
        if pixmap.loadFromData(image_data):
            # Scale to fit label while maintaining aspect ratio
            scaled_pixmap = pixmap.scaled(
                self.image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.image_label.setPixmap(scaled_pixmap)
        else:
            logger.error("Failed to load star chart image")

        # Update coordinate label
        self.coord_label.setText(f"Azimuth: {self.azimuth:.1f}°  Altitude: {self.altitude:.1f}°")

    def _on_map_generation_finished(self) -> None:
        """Handle map generation thread finished signal."""
        # Close loading dialog
        if self._loading_dialog is not None:
            self._loading_dialog.close()
            self._loading_dialog = None

    def _on_generation_timeout(self) -> None:
        """Handle timeout if generation takes too long."""
        if self._loading_dialog is not None and self._loading_dialog.isVisible():
            logger.warning("Sky map generation timed out after 60 seconds")
            self._loading_dialog.close()
            self._loading_dialog = None
            # Terminate the thread if it's still running
            if self._map_thread is not None and self._map_thread.isRunning():
                logger.warning("Terminating hung map generation thread")
                self._map_thread.terminate()
                self._map_thread.wait(5000)  # Wait up to 5 seconds for termination

    def _reset_view(self) -> None:
        """Reset view to default (calculated from observer location)."""
        # Recalculate defaults based on current location
        try:
            from celestron_nexstar.api.location.observer import get_observer_location

            location = get_observer_location()
            # For northern hemisphere: use South (180°), for southern: use North (0°)
            self.azimuth = 180.0 if location.latitude >= 0 else 0.0
            # Use a good viewing angle: 60-70° is optimal for most observing
            self.altitude = max(50.0, min(70.0, 60.0 + abs(location.latitude) * 0.1))
        except Exception:
            # Fallback to reasonable defaults if location can't be determined
            self.azimuth = 180.0
            self.altitude = 60.0

        self._update_map()

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


class _MapGenerationThread(QThread):
    """Background thread for generating star chart images."""

    image_ready = Signal(bytes)  # type: ignore[arg-type]

    def __init__(
        self,
        magnitude_limit: float,
        azimuth: float,
        altitude: float,
        telescope: NexStarTelescope | None = None,
        is_dark_theme: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the map generation thread."""
        super().__init__(parent)
        self.magnitude_limit = magnitude_limit
        self.azimuth = azimuth
        self.altitude = altitude
        self.telescope = telescope
        self.is_dark_theme = is_dark_theme

    def run(self) -> None:
        """Generate the star chart image in background thread."""
        try:
            logger.info("Starting sky map generation...")

            # Try to get current telescope position if connected
            azimuth = self.azimuth
            altitude = self.altitude

            if self.telescope is not None:
                try:
                    logger.debug("Checking telescope connection...")
                    # Check if telescope is connected
                    if hasattr(self.telescope, "is_connected") and self.telescope.is_connected():
                        logger.debug("Getting telescope position...")
                        # Get current position from telescope using worker thread
                        # This is already in a background thread, so we can use asyncio.run() directly
                        import asyncio

                        position = asyncio.run(self.telescope.get_position_alt_az())
                        azimuth = position.azimuth
                        altitude = position.altitude
                        logger.debug(f"Using telescope position: Az={azimuth:.1f}°, Alt={altitude:.1f}°")
                except Exception as e:
                    # If telescope query fails, use default values
                    logger.debug(f"Could not get telescope position, using defaults: {e}")

            logger.debug("Importing starplot...")
            # Import starplot - deal.activate() is no longer called, so imports work normally
            import starplot

            horizon_plot = starplot.HorizonPlot
            observer = starplot.Observer
            styles = starplot.styles

            logger.debug("Getting observer location...")
            # Get observer location and time
            from celestron_nexstar.api.location.observer import get_observer_location

            location = get_observer_location()
            now = datetime.now(UTC)

            logger.debug("Getting ephemeris file path...")
            # Get ephemeris file path (use downloaded ephemeris if available)
            from pathlib import Path

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
                plot_style = styles.PlotStyle().extend(styles.extensions.MAP, styles.extensions.BLUE_NIGHT)
            else:
                plot_style = styles.PlotStyle().extend(styles.extensions.MAP, styles.extensions.BLUE_LIGHT)

            logger.debug("Calculating view ranges...")
            # Create horizon plot
            # Starplot expects altitude and azimuth as ranges (min, max) in degrees
            # For a centered view, we'll show a 90-degree field of view around the center
            altitude_range = (max(0, altitude - 45), min(90, altitude + 45))
            # Azimuth wraps around 360, so handle that carefully
            azimuth_min = (azimuth - 45) % 360
            azimuth_max = (azimuth + 45) % 360
            # If the range crosses 0/360, use full range; otherwise use the calculated range
            azimuth_range = (0, 360) if azimuth_min > azimuth_max else (azimuth_min, azimuth_max)
            # Starplot limits azimuth range to 180 degrees max
            if azimuth_range[1] - azimuth_range[0] > 180:
                azimuth_range = (0, 180)

            logger.info(f"Creating horizon plot: altitude={altitude_range}, azimuth={azimuth_range}")
            # Try creating plot with minimal features first to test if it works
            plot = horizon_plot(
                observer=starplot_observer,
                ephemeris=ephemeris_file,  # Use downloaded ephemeris file
                altitude=altitude_range,  # (min_altitude, max_altitude) in degrees (0-90)
                azimuth=azimuth_range,  # (min_azimuth, max_azimuth) in degrees (0-360, 0=North)
                style=plot_style,
                resolution=4096,
                scale=1.25,
                autoscale=True,
            )
            logger.debug("Horizon plot created successfully")

            # Calculate which cardinal direction labels are visible in the azimuth range
            visible_labels = {}
            cardinal_directions = {0: "North", 90: "East", 180: "South", 270: "West"}
            az_min, az_max = azimuth_range

            # Handle wrapping around 0/360
            if az_min > az_max:
                # Range wraps around (e.g., 315 to 45)
                for direction, label in cardinal_directions.items():
                    if direction >= az_min or direction <= az_max:
                        visible_labels[direction] = label
            else:
                # Normal range
                for direction, label in cardinal_directions.items():
                    if az_min <= direction <= az_max:
                        visible_labels[direction] = label

            logger.debug("Adding stars...")
            # Add stars (filter by magnitude)
            # Starplot uses ibis expressions for filtering
            from starplot import _  # type: ignore[import-untyped]

            plot.stars(where=[_.magnitude < self.magnitude_limit])  # type: ignore[arg-type]
            logger.debug("Stars added successfully")

            logger.debug("Adding constellations...")
            # Add constellations
            plot.constellations()
            logger.debug("Constellations added successfully")
            plot.constellation_labels()

            logger.debug("Adding horizon...")
            # Add horizon with cardinal direction labels that are visible in the current view
            # Azimuth: 0=North, 90=East, 180=South, 270=West
            if visible_labels:
                plot.horizon(labels=visible_labels)
                logger.debug(f"Horizon added with labels: {visible_labels}")
            else:
                plot.horizon()  # No labels if none are visible
                logger.debug("Horizon added without labels (none visible in range)")
            logger.debug("Horizon added successfully")

            # Skip DSOs for now to speed up generation
            # logger.debug("Adding deep sky objects...")
            # plot.dsos(where=[(_.magnitude.isnull()) | (_.magnitude < self.magnitude_limit)])

            logger.info("Exporting plot to PNG...")
            # Export to PNG in memory
            img_buffer = io.BytesIO()
            plot.export(img_buffer, format="png")  # type: ignore[no-untyped-call]
            img_buffer.seek(0)
            image_data = img_buffer.read()

            logger.info(f"Sky map generation complete, image size: {len(image_data)} bytes")

            # DEBUG: Save image to file for verification (only first time, then overwrite)
            # This prevents accumulating many files during testing
            debug_dir = Path.home() / ".cache" / "celestron-nexstar" / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            debug_file = debug_dir / "sky_map_debug.png"  # Single file, overwritten each time
            try:
                with open(debug_file, "wb") as f:
                    f.write(image_data)
                logger.debug(f"DEBUG: Saved sky map image to {debug_file}")
            except Exception as e:
                logger.warning(f"DEBUG: Could not save image to file: {e}")

            # Emit signal with image data (will be handled in main thread)
            self.image_ready.emit(image_data)

        except Exception as e:
            logger.error(f"Error generating sky map: {e}", exc_info=True)
            # Emit empty image data to signal completion even on error
            # This ensures the loading dialog closes
            self.image_ready.emit(b"")
