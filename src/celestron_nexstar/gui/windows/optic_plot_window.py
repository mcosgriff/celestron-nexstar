"""
Optic Plot Window

Window for displaying an optic plot showing what you'll see through your telescope.
"""

from __future__ import annotations

import io
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QGuiApplication, QImage, QPalette, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressDialog,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class OpticPlotWindow(QDialog):
    """Dialog to display an optic plot showing what you'll see through your telescope."""

    def __init__(
        self,
        parent: QWidget | None = None,
        object_name: str = "",
        object_type: str | None = None,
        ra_hours: float = 0.0,
        dec_degrees: float = 0.0,
    ) -> None:
        """Initialize the optic plot window."""
        super().__init__(parent)
        self.setWindowTitle(f"Optic Plot: {object_name}")
        self.setMinimumWidth(800)
        self.setMinimumHeight(600)
        self.resize(1000, 800)

        self.object_name = object_name
        self.object_type = object_type
        self.ra_hours = ra_hours
        self.dec_degrees = dec_degrees

        self._loading_dialog: QProgressDialog | None = None
        self._plot_thread: _PlotGenerationThread | None = None

        self._create_ui()
        self._generate_plot()

    def _create_ui(self) -> None:
        """Create the UI layout."""
        layout = QVBoxLayout(self)

        # Image label with scroll area to handle images larger than viewport
        from PySide6.QtWidgets import QScrollArea

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)  # We'll control sizing
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setStyleSheet("background-color: black;")

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: black;")
        self.image_label.setScaledContents(False)  # We'll handle scaling manually

        self.scroll_area.setWidget(self.image_label)
        layout.addWidget(self.scroll_area)

        # Button box
        button_box = QHBoxLayout()
        button_box.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_box.addWidget(close_btn)

        layout.addLayout(button_box)

    def _generate_plot(self) -> None:
        """Generate the optic plot in a background thread."""
        if self._plot_thread is not None and self._plot_thread.isRunning():
            self._plot_thread.terminate()
            self._plot_thread.wait()

        if self._loading_dialog is not None:
            self._loading_dialog.close()
            self._loading_dialog = None

        # NOTE: QProgressDialog overload expects a cancel button label string (even if we later hide it).
        self._loading_dialog = QProgressDialog("Generating optic plot...", "", 0, 0, self)
        self._loading_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self._loading_dialog.setCancelButton(None)
        self._loading_dialog.setMinimumDuration(0)
        self._loading_dialog.show()
        QApplication.processEvents()

        app = QGuiApplication.instance()
        is_dark = False
        if app and isinstance(app, QGuiApplication):
            palette = app.palette()
            window_color = palette.color(QPalette.ColorRole.Window)
            brightness = window_color.lightness()
            is_dark = brightness < 128

        self._plot_thread = _PlotGenerationThread(
            object_name=self.object_name,
            object_type=self.object_type,
            ra_hours=self.ra_hours,
            dec_degrees=self.dec_degrees,
            is_dark_theme=is_dark,
        )
        self._plot_thread.image_ready.connect(self._on_image_ready)
        self._plot_thread.finished.connect(self._on_plot_generation_finished)
        self._plot_thread.start()

    def _on_image_ready(self, image_data: bytes) -> None:
        """Handle image ready signal from background thread."""
        if self._loading_dialog is not None:
            self._loading_dialog.close()
            self._loading_dialog = None

        if not image_data:
            logger.warning("Received empty image data, skipping display")
            self.image_label.setText("Failed to generate optic plot")
            return

        image = QImage.fromData(image_data)
        if image.isNull():
            logger.error("Failed to load QImage from data")
            self.image_label.setText("Failed to load optic plot image")
            return

        pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            logger.error("Failed to convert QImage to QPixmap")
            self.image_label.setText("Failed to convert image")
            return

        # Store original pixmap for potential zooming
        self._original_pixmap = pixmap

        # Scale image to fit viewport while maintaining aspect ratio
        # Get available space in scroll area (accounting for dialog margins and button)
        scroll_area_size = self.scroll_area.size()
        if scroll_area_size.width() <= 1 or scroll_area_size.height() <= 1:
            # Scroll area not yet sized, use dialog size as estimate
            dialog_size = self.size()
            available_width = dialog_size.width() - 40  # Account for margins
            available_height = dialog_size.height() - 100  # Account for margins and button
        else:
            available_width = scroll_area_size.width() - 20  # Account for scrollbar
            available_height = scroll_area_size.height() - 20

        # Calculate scale factor to fit in available space
        scale_factor = min(
            available_width / pixmap.width(),
            available_height / pixmap.height(),
            1.0,  # Don't scale up, only down
        )

        # Scale the pixmap
        if scale_factor < 1.0:
            new_width = int(pixmap.width() * scale_factor)
            new_height = int(pixmap.height() * scale_factor)
            scaled_pixmap = pixmap.scaled(
                new_width,
                new_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            logger.debug(
                f"Scaled image from {pixmap.width()}x{pixmap.height()} to {new_width}x{new_height} (scale: {scale_factor:.2f})"
            )
        else:
            scaled_pixmap = pixmap
            logger.debug(f"Image fits at original size: {pixmap.width()}x{pixmap.height()}")

        # Set pixmap and resize label to fit
        self.image_label.setPixmap(scaled_pixmap)
        self.image_label.resize(scaled_pixmap.size())

    def _on_plot_generation_finished(self) -> None:
        """Handle plot generation thread finished signal."""
        if self._loading_dialog is not None:
            self._loading_dialog.close()
            self._loading_dialog = None

    def resizeEvent(self, event: Any) -> None:  # noqa: N802
        """Handle widget resize - rescale image to fit new size."""
        super().resizeEvent(event)
        # Rescale image if we have one
        if hasattr(self, "_original_pixmap") and self._original_pixmap:
            pixmap = self._original_pixmap
            scroll_area_size = self.scroll_area.size()
            if scroll_area_size.width() > 1 and scroll_area_size.height() > 1:
                available_width = scroll_area_size.width() - 20
                available_height = scroll_area_size.height() - 20

                scale_factor = min(available_width / pixmap.width(), available_height / pixmap.height(), 1.0)

                if scale_factor < 1.0:
                    new_width = int(pixmap.width() * scale_factor)
                    new_height = int(pixmap.height() * scale_factor)
                    scaled_pixmap = pixmap.scaled(
                        new_width,
                        new_height,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                else:
                    scaled_pixmap = pixmap

                self.image_label.setPixmap(scaled_pixmap)
                self.image_label.resize(scaled_pixmap.size())


class _PlotGenerationThread(QThread):
    """Background thread for generating optic plot images."""

    image_ready = Signal(bytes)
    error_message = Signal(str)

    def __init__(
        self,
        object_name: str,
        object_type: str | None,
        ra_hours: float,
        dec_degrees: float,
        is_dark_theme: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the plot generation thread."""
        super().__init__(parent)
        self.object_name = object_name
        self.object_type = object_type
        self.ra_hours = ra_hours
        self.dec_degrees = dec_degrees
        self.is_dark_theme = is_dark_theme

    def run(self) -> None:
        """Generate the optic plot image in background thread."""
        try:
            logger.info("Starting optic plot generation...")

            from starplot import Observer, OpticPlot, _  # type: ignore[import-untyped]
            from starplot.callables import color_by_bv  # type: ignore[import-untyped]
            from starplot.models import DSO, Reflector, Refractor  # type: ignore[import-untyped]
            from starplot.styles import (  # type: ignore[import-untyped]
                MarkerStyle,
                MarkerSymbolEnum,
                ObjectStyle,
                PlotStyle,
                extensions,
            )

            # Get optical configuration
            from celestron_nexstar.api.observation.optics import get_current_configuration

            config = get_current_configuration()

            # Convert telescope to starplot Optic model
            # NexStar telescopes are Schmidt-Cassegrain (reflectors)
            # Check if it's a reflector (has obstruction) or refractor
            if config.telescope.obstruction_diameter_mm > 0:
                # Reflector (Schmidt-Cassegrain)
                optic = Reflector(
                    focal_length=config.telescope.focal_length_mm,
                    eyepiece_focal_length=config.eyepiece.focal_length_mm,
                    eyepiece_fov=config.eyepiece.apparent_fov_deg,
                )
            else:
                # Refractor
                optic = Refractor(
                    focal_length=config.telescope.focal_length_mm,
                    eyepiece_focal_length=config.eyepiece.focal_length_mm,
                    eyepiece_fov=config.eyepiece.apparent_fov_deg,
                )

            # Get observer location
            from celestron_nexstar.api.location.observer import get_observer_location

            location = get_observer_location()
            from celestron_nexstar.api.core.utils import get_local_timezone

            local_tz = get_local_timezone(location.latitude, location.longitude) or UTC
            now = datetime.now(local_tz)

            # Create starplot observer
            starplot_observer = Observer(
                dt=now,
                lat=location.latitude,
                lon=location.longitude,
            )

            # Get ephemeris file path
            from celestron_nexstar.api.ephemeris.ephemeris_manager import get_ephemeris_directory

            ephemeris_dir = get_ephemeris_directory()
            ephemeris_file = None
            for preferred_name in ["de421.bsp", "de440.bsp", "de421_2001.bsp"]:
                eph_path = ephemeris_dir / preferred_name
                if eph_path.exists():
                    ephemeris_file = preferred_name
                    logger.debug(f"Using ephemeris file: {ephemeris_file}")
                    break

            if ephemeris_file is None:
                ephemeris_file = "de421_2001.bsp"
                logger.debug(f"No ephemeris file found, using starplot default: {ephemeris_file}")

            # Determine style based on theme
            if self.is_dark_theme:
                plot_style = PlotStyle().extend(extensions.BLUE_DARK, extensions.OPTIC)
            else:
                plot_style = PlotStyle().extend(extensions.BLUE_LIGHT, extensions.OPTIC)

            # Convert RA from hours to degrees
            ra_deg = self.ra_hours * 15.0

            logger.info(f"Creating optic plot for {self.object_name} at RA={ra_deg:.2f}°, Dec={self.dec_degrees:.2f}°")

            # Check if object is above the horizon before creating plot
            from skyfield.api import Star, wgs84

            # Create skyfield time and observer
            from celestron_nexstar.api.ephemeris.skyfield_utils import (
                get_skyfield_ephemeris,
                get_skyfield_loader,
            )

            sf_loader = get_skyfield_loader()
            ts = sf_loader.timescale()
            t = ts.now()

            # Create observer location
            # To observe stars, we need a position relative to the solar system barycenter (ICRS),
            # so we combine the Earth's position from the ephemeris with the observer's location on Earth.
            planets = get_skyfield_ephemeris(ephemeris_file)
            earth = planets["earth"]
            sf_observer = earth + wgs84.latlon(location.latitude, location.longitude)

            # Create a Star object at the target's coordinates
            target_star = Star(ra_hours=self.ra_hours, dec_degrees=self.dec_degrees)

            # Calculate altitude from observer's perspective
            observer_at_time = sf_observer.at(t)
            target_astrometric = observer_at_time.observe(target_star)
            alt, _az, _distance = target_astrometric.apparent().altaz()

            if alt.degrees < 0:
                logger.warning(
                    f"Object {self.object_name} is below horizon (altitude={alt.degrees:.1f}°), cannot generate optic plot"
                )
                # Emit empty data with specific error message
                # The receiving end will handle this by showing "Failed to generate optic plot"
                self.image_ready.emit(b"")
                return

            # Create optic plot
            plot = OpticPlot(
                ra=ra_deg,
                dec=self.dec_degrees,
                optic=optic,
                observer=starplot_observer,
                ephemeris=ephemeris_file,
                style=plot_style,
                resolution=2600,
                autoscale=True,
            )

            # Add stars (magnitude < 14, color by B-V, labels for bright stars)
            plot.stars(where=[_.magnitude < 14], color_fn=color_by_bv, bayer_labels=True)  # type: ignore[arg-type]

            # Add deep sky objects - use a more lenient magnitude limit to include more objects
            # The specific target object will be added separately if it's a DSO
            plot.dsos(where=[_.magnitude < 10], where_labels=[False])  # type: ignore[arg-type]

            # Add the specific target object based on its type
            if self.object_type:
                try:
                    object_type_lower = self.object_type.lower()

                    if object_type_lower == "planet":
                        # Plot all planets - the target planet will be included if visible
                        # Planets are plotted at their true apparent size
                        plot.planets(true_size=True)
                        logger.debug(f"Added planets to plot (target: {self.object_name})")

                    elif object_type_lower == "moon":
                        # Plot the Moon
                        plot.moon(true_size=True, show_phase=True)
                        logger.debug("Added Moon to plot")

                    elif object_type_lower in ("galaxy", "nebula", "cluster"):
                        # For DSOs, try to get the specific object and plot it
                        # First, try to find it by Messier number or NGC number
                        dso = None
                        # Try Messier number (e.g., "M31", "M42")
                        if self.object_name.upper().startswith("M"):
                            try:
                                m_num = int(self.object_name.upper().replace("M", "").strip())
                                dso = DSO.get(m=m_num)
                                logger.debug(f"Found DSO by Messier number: M{m_num}")
                            except (ValueError, AttributeError):
                                pass

                        # Try NGC number (e.g., "NGC 224", "NGC 1976")
                        if dso is None and "NGC" in self.object_name.upper():
                            try:
                                ngc_num = int(self.object_name.upper().replace("NGC", "").strip())
                                dso = DSO.get(ngc=ngc_num)
                                logger.debug(f"Found DSO by NGC number: NGC {ngc_num}")
                            except (ValueError, AttributeError):
                                pass

                        # Try by name
                        if dso is None:
                            try:
                                dso = DSO.get(name=self.object_name)
                                logger.debug(f"Found DSO by name: {self.object_name}")
                            except (ValueError, AttributeError):
                                pass

                        # If we found the DSO, plot it with a marker
                        if dso:
                            # Create a style for the target object (make it stand out)
                            target_style = ObjectStyle(
                                marker=MarkerStyle(
                                    symbol=MarkerSymbolEnum.CIRCLE,
                                    size=20,
                                    fill_color="#ff0000",  # Red to make it stand out
                                    edge_color="#ffffff",
                                    edge_width=2,
                                ),
                                label=ObjectStyle().label,  # Use default label style
                            )

                            # Plot the DSO as a marker
                            plot.marker(
                                ra=dso.ra,
                                dec=dso.dec,
                                style=target_style,
                                label=self.object_name,
                                gid_marker="target-dso-marker",
                                gid_label="target-dso-label",
                            )
                            logger.debug(
                                f"Added target DSO {self.object_name} to plot at RA={dso.ra:.2f}°, Dec={dso.dec:.2f}°"
                            )
                        else:
                            logger.warning(f"Could not find DSO {self.object_name} in starplot database")

                    elif object_type_lower == "star":
                        # Stars are already plotted above, but we could highlight the specific star
                        # For now, stars are included in the general star plot
                        logger.debug("Target is a star, already included in star plot")

                except Exception as e:
                    logger.warning(f"Could not add target object {self.object_name} to plot: {e}")

            # Add info text (must be called before export)
            # The info() method adjusts axis limits to make room for the info table
            plot.info()

            logger.info("Exporting plot to PNG...")
            img_buffer = io.BytesIO()
            # Use sufficient padding to ensure info table at bottom is visible
            plot.export(img_buffer, format="png", padding=0.3, transparent=True)  # type: ignore[no-untyped-call]
            img_buffer.seek(0)
            image_data = img_buffer.read()

            logger.info(f"Optic plot generation complete, image size: {len(image_data)} bytes")

            # DEBUG: Save image to file for verification
            debug_dir = Path.home() / ".cache" / "celestron-nexstar" / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            debug_file = debug_dir / f"optic_plot_{self.object_name.replace(' ', '_')}_debug.png"
            try:
                with open(debug_file, "wb") as f:
                    f.write(image_data)
                logger.debug(f"DEBUG: Saved optic plot image to {debug_file}")
            except Exception as e:
                logger.warning(f"DEBUG: Could not save image to file: {e}")

            self.image_ready.emit(image_data)

        except Exception as e:
            logger.error(f"Error generating optic plot: {e}", exc_info=True)
            self.image_ready.emit(b"")
