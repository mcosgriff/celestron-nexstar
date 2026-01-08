"""
Dialog to display moon information.
"""

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from celestron_nexstar.api.core.utils import get_local_timezone
from celestron_nexstar.api.location.observer import FEET_TO_METERS


try:
    import shiboken6  # type: ignore[import-untyped]

    def _is_valid(obj: object) -> bool:
        # shiboken6.isValid checks whether the underlying C++ object is still alive
        return bool(shiboken6.isValid(obj))

except ImportError:
    # Fallback for environments without shiboken6 (best-effort)
    def _is_valid(obj: object) -> bool:
        return obj is not None


from celestron_nexstar.api.astronomy.solar_system import get_moon_info
from celestron_nexstar.api.core import format_local_time
from celestron_nexstar.api.core.enums import MoonPhase
from celestron_nexstar.api.location.observer import get_observer_location


if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


class MoonPlotWorkerThread(QThread):
    """Worker thread to generate moon plot using starplot."""

    plot_ready = Signal(bytes)  # PNG image data
    error_occurred = Signal(str)  # Error message

    def __init__(self, is_dark_theme: bool, target_date: datetime | None = None, parent: QWidget | None = None) -> None:
        """Initialize the worker thread."""
        super().__init__(parent)
        self.is_dark_theme = is_dark_theme
        self.target_date = target_date

    def run(self) -> None:
        """Generate the moon plot in a background thread."""
        try:
            logger.info("Starting moon plot generation...")
            import starplot  # type: ignore[import-untyped]
            from starplot.styles import PlotStyle, extensions  # type: ignore[import-untyped]

            # Get observer location and time
            logger.debug("Getting observer location...")
            location = get_observer_location()
            # For the "Where to Look" chart, always use current time to show current sky
            # (target_date is used for Info tab to show moon phase for a specific date)
            now = datetime.now(get_local_timezone(location.latitude, location.longitude))

            # Get ephemeris file path
            from celestron_nexstar.api.ephemeris.ephemeris_manager import get_ephemeris_directory

            logger.debug("Getting ephemeris file path...")
            ephemeris_dir = get_ephemeris_directory()
            ephemeris_file = None
            for preferred_name in ["de421.bsp", "de440.bsp", "de421_2001.bsp"]:
                eph_path = ephemeris_dir / preferred_name
                if eph_path.exists():
                    ephemeris_file = preferred_name
                    logger.debug(f"Using ephemeris file: {ephemeris_file}")
                    break

            if ephemeris_file is None:
                # Avoid Skyfield attempting to auto-download (and printing progress to stdout).
                # Require the user to download ephemeris via Settings -> Ephemeris.
                error_msg = (
                    f"No local ephemeris file found in {ephemeris_dir}. "
                    "Download an ephemeris file (recommended: DE421) in Settings and try again."
                )
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                return

            # Create observer
            logger.debug("Creating starplot observer...")
            starplot_observer = starplot.Observer(
                dt=now,
                lat=location.latitude,
                lon=location.longitude,
            )

            # Determine style based on theme
            logger.debug("Determining plot style...")
            if self.is_dark_theme:
                plot_style = PlotStyle().extend(extensions.MAP, extensions.BLUE_NIGHT)
            else:
                plot_style = PlotStyle().extend(extensions.MAP, extensions.BLUE_LIGHT)

            # Get moon position for centering the plot
            logger.debug("Getting moon position...")
            moon_info = get_moon_info(location.latitude, location.longitude, now)
            if not moon_info:
                error_msg = "Could not calculate moon position"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                return

            # Center the plot on the moon's current position
            # Show a 20-degree field of view (±10 degrees from current altitude)
            # Starplot requires altitude_min < altitude_max and values within [0, 90].
            # When the Moon is below the horizon, (alt+10) can be < 0 which yields an invalid range.
            alt_center = max(0.0, min(90.0, float(moon_info.altitude_deg)))
            alt_min = max(0.0, alt_center - 10.0)
            alt_max = min(90.0, alt_center + 10.0)

            # Ensure we have at least a 5-degree window
            if alt_max - alt_min < 5.0:
                if alt_center < 5.0:
                    alt_min = 0.0
                    alt_max = 10.0
                elif alt_center > 85.0:
                    alt_min = 80.0
                    alt_max = 90.0
                else:
                    alt_min = alt_center - 2.5
                    alt_max = alt_center + 2.5

            altitude_range = (alt_min, alt_max)

            # Azimuth: Show ±15 degrees centered on current position
            # Handle 360-degree wrap-around properly
            azimuth_window = 15.0  # degrees on each side
            azimuth_min = (moon_info.azimuth_deg - azimuth_window) % 360
            azimuth_max = (moon_info.azimuth_deg + azimuth_window) % 360

            # Handle wrap-around case (e.g., 350° to 10°)
            if azimuth_min > azimuth_max:
                # Starplot can't handle wrap-around, so we need to shift the range
                # Center the view and avoid the discontinuity
                azimuth_center = moon_info.azimuth_deg
                azimuth_min = azimuth_center - azimuth_window
                azimuth_max = azimuth_center + azimuth_window

            azimuth_range = (azimuth_min, azimuth_max)

            # Create horizon plot
            logger.info(f"Moon position: alt={moon_info.altitude_deg:.2f}°, az={moon_info.azimuth_deg:.2f}°")
            logger.info(f"Creating horizon plot: altitude={altitude_range}, azimuth={azimuth_range}")
            logger.info(f"Plot observer time: {now}")
            plot = starplot.HorizonPlot(
                observer=starplot_observer,
                ephemeris=ephemeris_file,
                altitude=altitude_range,
                azimuth=azimuth_range,
                style=plot_style,
                # 4096 is beautiful but slow; 2048 is much faster and still crisp for an in-dialog plot.
                resolution=2048,
                scale=1.0,
                # autoscale=True,
            )
            logger.debug("Horizon plot created successfully")

            # Plot stars
            logger.debug("Adding stars...")
            # Stars are the expensive part; use a modest magnitude cutoff and disable labels.
            from starplot import _  # type: ignore[import-untyped]

            # plot.stars(where=[_.magnitude < 6.5], where_labels=[False])  # type: ignore[arg-type]
            plot.stars(where=[_.magnitude < 5], bayer_labels=True, where_labels=[_.magnitude < 3])
            logger.debug("Stars added successfully")

            # Plot the moon
            logger.debug("Adding moon...")
            # Use Starplot's HorizonPlot.moon kwargs for better visuals.
            # See: https://starplot.dev/reference-horizonplot/#starplot.HorizonPlot.moon
            plot.moon(true_size=False, show_phase=True, label="Moon", legend_label="Moon")  # type: ignore[no-untyped-call]
            logger.debug("Moon added successfully")

            # Plot horizon
            logger.debug("Adding horizon...")
            plot.horizon()
            logger.debug("Horizon added successfully")

            # Plot gridlines
            logger.debug("Adding gridlines...")
            plot.gridlines()
            logger.debug("Gridlines added successfully")

            # Export to PNG
            logger.info("Exporting plot to PNG...")
            import io

            with io.BytesIO() as img_buffer:
                plot.export(img_buffer, format="png", padding=0.5)  # type: ignore[no-untyped-call]
                img_buffer.seek(0)
                png_data = img_buffer.read()
            logger.info(f"Moon plot generation complete, image size: {len(png_data)} bytes")
            # Validate PNG signature to avoid downstream QPixmap overload/type errors dumping bytes to stdout
            if not png_data.startswith(b"\x89PNG\r\n\x1a\n"):
                error_msg = "Generated plot data is not a valid PNG (missing PNG signature)."
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                return
            self.plot_ready.emit(png_data)

        except Exception as e:
            logger.exception("Error generating moon plot")
            self.error_occurred.emit(f"Error generating plot: {e!s}")


class MoonDiskWorkerThread(QThread):
    """Worker thread to generate an oriented Moon disk rendering."""

    disk_ready = Signal(bytes)  # PNG image data
    error_occurred = Signal(str)  # Error message

    def __init__(self, is_dark_theme: bool, target_date: datetime | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.is_dark_theme = is_dark_theme
        self.target_date = target_date

    @staticmethod
    def _compute_bright_limb_pa_deg(
        moon_ra_rad: float, moon_dec_rad: float, sun_ra_rad: float, sun_dec_rad: float
    ) -> float:
        """
        Position angle of the bright limb, measured from celestial north toward east (degrees).

        Formula (Meeus-style):
          tan(chi) = cos(dec_s) * sin(ra_s - ra_m) /
                     (sin(dec_s) * cos(dec_m) - cos(dec_s) * sin(dec_m) * cos(ra_s - ra_m))
        """
        import math

        d_ra = sun_ra_rad - moon_ra_rad
        y = math.cos(sun_dec_rad) * math.sin(d_ra)
        x = (math.sin(sun_dec_rad) * math.cos(moon_dec_rad)) - (
            math.cos(sun_dec_rad) * math.sin(moon_dec_rad) * math.cos(d_ra)
        )
        chi = math.degrees(math.atan2(y, x))
        # Normalize to [0, 360)
        chi = chi % 360.0
        return chi

    def run(self) -> None:
        try:
            import io
            import math

            import numpy as np
            from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas  # type: ignore[import-untyped]
            from matplotlib.figure import Figure  # type: ignore[import-untyped]
            from matplotlib.patches import Circle, Polygon  # type: ignore[import-untyped]
            from skyfield.api import Topos  # type: ignore[import-untyped]

            from celestron_nexstar.api.ephemeris.ephemeris_manager import get_ephemeris_directory
            from celestron_nexstar.api.ephemeris.skyfield_utils import get_skyfield_ephemeris, get_skyfield_timescale

            location = get_observer_location()
            # Use target date if provided, otherwise current time
            now = (
                self.target_date
                if self.target_date
                else datetime.now(get_local_timezone(location.latitude, location.longitude))
            )

            # Require a local ephemeris that includes the Moon to avoid Skyfield download progress on stdout.
            eph_dir = get_ephemeris_directory()
            de421_path = eph_dir / "de421.bsp"
            if not de421_path.exists():
                self.error_occurred.emit(
                    f"Moon disk rendering requires DE421 ephemeris. Not found at {de421_path}. "
                    "Download DE421 in Settings and try again."
                )
                return

            ts = get_skyfield_timescale()
            t = ts.from_datetime(now)
            eph = get_skyfield_ephemeris("de421.bsp")

            earth = eph["earth"]
            sun = eph["sun"]
            moon = eph["moon"]

            elev_m = float(location.elevation or 0.0) * FEET_TO_METERS
            observer = earth + Topos(
                latitude_degrees=location.latitude, longitude_degrees=location.longitude, elevation_m=elev_m
            )

            # Topocentric apparent positions
            moon_app = observer.at(t).observe(moon).apparent()
            sun_app = observer.at(t).observe(sun).apparent()

            moon_ra, moon_dec, _ = moon_app.radec()
            sun_ra, sun_dec, _ = sun_app.radec()

            moon_ra_rad = float(moon_ra.radians)
            moon_dec_rad = float(moon_dec.radians)
            sun_ra_rad = float(sun_ra.radians)
            sun_dec_rad = float(sun_dec.radians)

            # Illumination fraction from phase angle (same as existing solar_system.get_moon_info)
            sun_geo = earth.at(t).observe(sun)
            moon_geo = earth.at(t).observe(moon)
            sun_pos = sun_geo.position.au
            moon_pos = moon_geo.position.au
            dot = float(sum(sun_pos[i] * moon_pos[i] for i in range(3)))
            sun_dist = float(math.sqrt(sum(sun_pos[i] ** 2 for i in range(3))))
            moon_dist = float(math.sqrt(sum(moon_pos[i] ** 2 for i in range(3))))
            cos_angle = dot / (sun_dist * moon_dist)
            cos_angle = max(-1.0, min(1.0, cos_angle))
            phase_angle = math.acos(cos_angle)
            illumination = (1.0 - math.cos(phase_angle)) / 2.0

            # Waxing/waning from RA difference (same logic as calculate_moon_phase)
            moon_ra_h = float(moon_ra.hours)
            sun_ra_h = float(sun_ra.hours)
            ra_diff = moon_ra_h - sun_ra_h
            if ra_diff > 12:
                ra_diff -= 24
            elif ra_diff < -12:
                ra_diff += 24
            # Positive ra_diff: Moon east of sun → WAXING
            # Negative ra_diff: Moon west of sun → WANING
            is_waxing = ra_diff > 0

            chi_deg = self._compute_bright_limb_pa_deg(moon_ra_rad, moon_dec_rad, sun_ra_rad, sun_dec_rad)

            # Build an oriented disk in "sky chart" orientation: North up, East left.
            # We'll draw in a coordinate system where +y is North and +x is West (so East is left).
            # Then rotate the phase shape so that the bright limb points at the Sun direction angle.
            #
            # Starplot's HorizonPlot.moon(show_phase=True) is for sky position plots; this tab is a disk rendering.
            #
            # Rotation: convert bright-limb position angle (north->east) into our (west,north) axes.
            # In (west,north) coords, the Sun direction unit vector is v = (-sin(chi), cos(chi)).
            # The angle from +x (west) is theta = atan2(vy, vx) = 90 + chi.
            theta_deg = (90.0 + chi_deg) % 360.0
            theta = math.radians(theta_deg)
            rot = np.array([[math.cos(theta), -math.sin(theta)], [math.sin(theta), math.cos(theta)]], dtype=float)

            # Colors
            if self.is_dark_theme:
                bg = "#000000"
                shadow = "#202020"
                light = "#f2f2f2"
                outline = "#9e9e9e"
                text = "#ffffff"
            else:
                bg = "#ffffff"
                shadow = "#7a7a7a"
                light = "#f8f8f8"
                outline = "#333333"
                text = "#000000"

            fig = Figure(figsize=(4.0, 4.0), dpi=200, facecolor=bg)
            FigureCanvas(fig)
            try:
                ax = fig.add_subplot(111)
                ax.set_facecolor(bg)
                ax.set_aspect("equal")
                ax.set_xlim(-1.1, 1.1)
                ax.set_ylim(-1.15, 1.15)
                ax.axis("off")

                # Disk outline base (shadow or lit depending on phase)
                base_color = shadow if illumination <= 0.5 else light
                ax.add_patch(Circle((0, 0), 1.0, facecolor=base_color, edgecolor=outline, linewidth=2.0))

                # Build crescent overlay polygon
                eps = 1e-4
                f = float(max(0.0, min(1.0, illumination)))
                if f <= eps:
                    # New Moon: leave as shadow disk
                    pass
                elif f >= 1.0 - eps:
                    # Full Moon: overwrite with light disk
                    ax.add_patch(Circle((0, 0), 1.0, facecolor=light, edgecolor=outline, linewidth=2.0))
                else:
                    # Scale for terminator ellipse in projection: |cos(phase_angle)| = |1 - 2f|
                    scale = abs(1.0 - 2.0 * f)
                    y = np.linspace(-1.0, 1.0, 500)
                    limb = np.sqrt(np.clip(1.0 - y * y, 0.0, 1.0))

                    lit_side = 1.0 if is_waxing else -1.0  # waxing lit on the right (west) with N up / E left

                    def _poly(side: float, term_scale: float) -> np.ndarray:
                        x_limb = side * limb
                        x_term = side * (term_scale * limb)
                        pts1 = np.column_stack([x_limb, y])
                        pts2 = np.column_stack([x_term[::-1], y[::-1]])
                        pts = np.vstack([pts1, pts2])
                        # Rotate
                        return (rot @ pts.T).T

                    if f <= 0.5:
                        # Add illuminated crescent on top of shadow base
                        pts = _poly(lit_side, scale).tolist()
                        ax.add_patch(Polygon(pts, closed=True, facecolor=light, edgecolor="none"))
                    else:
                        # Add shadow crescent on top of lit base
                        pts = _poly(-lit_side, scale).tolist()
                        ax.add_patch(Polygon(pts, closed=True, facecolor=shadow, edgecolor="none"))

                # Title / info
                wax = "Waxing" if is_waxing else "Waning"
                ax.text(
                    0,
                    1.06,
                    f"{wax} • {f * 100:.1f}% • PA {chi_deg:.0f}°",
                    ha="center",
                    va="bottom",
                    color=text,
                    fontsize=10,
                )

                # Export to PNG bytes
                with io.BytesIO() as buf:
                    fig.savefig(buf, format="png", facecolor=bg, bbox_inches="tight", pad_inches=0.05)
                    buf.seek(0)
                    png_data = buf.read()
                if not png_data.startswith(b"\x89PNG\r\n\x1a\n"):
                    self.error_occurred.emit("Moon disk renderer failed to generate valid PNG bytes.")
                    return
                self.disk_ready.emit(png_data)
            finally:
                # Help matplotlib release references promptly in long-running sessions.
                fig.clear()

        except Exception as e:
            logger.exception("Error generating moon disk")
            self.error_occurred.emit(f"Error generating moon disk: {e!s}")


class MoonInfoDialog(QDialog):
    """Dialog to display moon information."""

    _plot_thread: MoonPlotWorkerThread | None
    _disk_thread: MoonDiskWorkerThread | None

    def __init__(self, parent: QWidget | None = None, target_date: datetime | None = None) -> None:
        """
        Initialize the moon info dialog.

        Args:
            parent: Parent widget
            target_date: Optional target date to calculate for (defaults to current time)
        """
        super().__init__(parent)
        self.target_date = target_date  # Store for use in tabs
        self.setWindowTitle("Moon Information")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        self.resize(600, 700)

        # Initialize thread attribute
        self._plot_thread = None
        self._disk_thread = None

        # Create layout
        layout = QVBoxLayout(self)

        # Create tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Create "Info" tab with text info
        info_tab = QWidget()
        info_layout = QVBoxLayout(info_tab)

        # Create scrollable text area with rich HTML formatting
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setAcceptRichText(True)

        # Get monospace font from application property, fallback to system fonts
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        monospace_font = app.property("monospace_font") if app and app.property("monospace_font") else None
        font_family = f"'{monospace_font}'" if monospace_font else "'Courier New'"

        # Store font family for later use
        self._font_family = font_family

        # Set initial stylesheet
        self.info_text.setStyleSheet(
            f"""
            QTextEdit {{
                font-family: {font_family};
                background-color: transparent;
                border: none;
            }}
        """
        )
        info_layout.addWidget(self.info_text)
        self.tab_widget.addTab(info_tab, "Info")

        # Create "Plot" tab
        plot_tab = QWidget()
        plot_layout = QVBoxLayout(plot_tab)
        plot_layout.setContentsMargins(0, 0, 0, 0)

        # Create widget to hold the plot
        self.plot_widget = QWidget()
        plot_widget_layout = QVBoxLayout(self.plot_widget)
        plot_widget_layout.setContentsMargins(0, 0, 0, 0)

        # Placeholder label
        self.plot_label = QLabel("Loading moon plot...")
        self.plot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        plot_widget_layout.addWidget(self.plot_label)

        plot_layout.addWidget(self.plot_widget)
        self.tab_widget.addTab(plot_tab, "Where to Look")

        # Create "Moon Disk" tab
        disk_tab = QWidget()
        disk_layout = QVBoxLayout(disk_tab)
        disk_layout.setContentsMargins(0, 0, 0, 0)

        self.disk_widget = QWidget()
        disk_widget_layout = QVBoxLayout(self.disk_widget)
        disk_widget_layout.setContentsMargins(0, 0, 0, 0)

        self.disk_label = QLabel("Loading moon disk...")
        self.disk_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        disk_widget_layout.addWidget(self.disk_label)

        self.disk_caption_label = QLabel(
            "Orientation: North is up, East is left. The bright limb points toward the Sun (PA shown in the title)."
        )
        self.disk_caption_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.disk_caption_label.setWordWrap(True)
        # Keep it subtle; we'll set the final color in _load_moon_info() once we know theme colors.
        self.disk_caption_label.setStyleSheet("opacity: 0.85;")
        disk_widget_layout.addWidget(self.disk_caption_label)

        disk_layout.addWidget(self.disk_widget)
        self.tab_widget.addTab(disk_tab, "Moon Disk")

        # Add button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        # Load moon information
        self._load_moon_info()
        self._load_moon_plot()
        self._load_moon_disk()

    def _safe_stop_thread(self, thread: QThread | None) -> None:
        """Best-effort stop/cleanup for QThreads, resilient to already-deleted C++ objects."""
        if thread is None:
            return
        try:
            if not _is_valid(thread):
                return
            # Disconnect signals first (only if it's a MoonPlotWorkerThread)
            if isinstance(thread, MoonPlotWorkerThread):
                try:
                    thread.plot_ready.disconnect()
                    thread.error_occurred.disconnect()
                except (RuntimeError, TypeError):
                    pass  # Signals already disconnected or object deleted
            if isinstance(thread, MoonDiskWorkerThread):
                try:
                    thread.disk_ready.disconnect()
                    thread.error_occurred.disconnect()
                except (RuntimeError, TypeError):
                    pass
            if thread.isRunning():
                thread.requestInterruption()
                thread.wait(3000)
                if thread.isRunning():
                    thread.terminate()
                    thread.wait(1000)
            # Schedule deletion in the Qt event loop (safe when still valid)
            if _is_valid(thread):
                thread.deleteLater()
        except RuntimeError:
            # Underlying C++ object already deleted.
            return

    def _on_plot_thread_finished(self) -> None:
        """Cleanup handler for plot generation thread."""
        sender_obj = self.sender()
        if isinstance(sender_obj, QThread):
            if self._plot_thread is sender_obj:
                self._plot_thread = None
            try:
                if _is_valid(sender_obj):
                    sender_obj.deleteLater()
            except RuntimeError:
                pass

    def _on_disk_thread_finished(self) -> None:
        sender_obj = self.sender()
        if isinstance(sender_obj, QThread):
            if self._disk_thread is sender_obj:
                self._disk_thread = None
            try:
                if _is_valid(sender_obj):
                    sender_obj.deleteLater()
            except RuntimeError:
                pass

    def closeEvent(self, event: Any) -> None:  # noqa: N802
        """Handle dialog close event - clean up threads."""
        # Stop and clean up plot thread
        if self._plot_thread is not None:
            self._safe_stop_thread(self._plot_thread)
            self._plot_thread = None
        if self._disk_thread is not None:
            self._safe_stop_thread(self._disk_thread)
            self._disk_thread = None
        super().closeEvent(event)

    def _is_dark_theme(self) -> bool:
        """Detect if the current theme is dark mode."""
        from PySide6.QtGui import QGuiApplication, QPalette

        app = QGuiApplication.instance()
        if app and isinstance(app, QGuiApplication):
            palette = app.palette()
            window_color = palette.color(QPalette.ColorRole.Window)
            brightness = window_color.lightness()
            return bool(brightness < 128)
        return False

    def _get_theme_colors(self) -> dict[str, str]:
        """Get theme-aware colors."""
        is_dark = self._is_dark_theme()
        return {
            "text": "#ffffff" if is_dark else "#000000",
            "text_dim": "#9e9e9e" if is_dark else "#666666",
            "header": "#ffc107" if is_dark else "#f57c00",
            "cyan": "#00bcd4" if is_dark else "#00838f",
            "green": "#4caf50" if is_dark else "#2e7d32",
        }

    def _azimuth_to_compass(self, azimuth_deg: float) -> str:
        """Convert azimuth in degrees to compass direction.

        Args:
            azimuth_deg: Azimuth in degrees (0-360, where 0=North, 90=East, 180=South, 270=West)

        Returns:
            Compass direction string (N, NE, E, SE, S, SW, W, NW)
        """
        # Normalize azimuth to 0-360
        azimuth = azimuth_deg % 360

        # Define compass directions with their azimuth ranges
        # Each direction covers 45 degrees, centered on the cardinal/intercardinal points
        directions = [
            (0, 22.5, "N"),
            (22.5, 67.5, "NE"),
            (67.5, 112.5, "E"),
            (112.5, 157.5, "SE"),
            (157.5, 202.5, "S"),
            (202.5, 247.5, "SW"),
            (247.5, 292.5, "W"),
            (292.5, 337.5, "NW"),
            (337.5, 360, "N"),
        ]

        for start, end, direction in directions:
            if start <= azimuth < end:
                return direction

        return "N"  # Fallback

    def _load_moon_info(self) -> None:
        """Load moon information and format it for display."""
        colors = self._get_theme_colors()

        # Theme-aware caption styling (moon disk tab)
        if hasattr(self, "disk_caption_label"):
            self.disk_caption_label.setStyleSheet(f"color: {colors['text_dim']};")

        # Update stylesheet with theme-aware colors
        self.info_text.setStyleSheet(
            f"""
            QTextEdit {{
                font-family: {self._font_family};
                background-color: transparent;
                border: none;
            }}
            h2 {{
                color: {colors["header"]};
                margin-top: 1em;
                margin-bottom: 0.5em;
            }}
        """
        )

        try:
            location = get_observer_location()
            logger.info(
                f"Observer location: lat={location.latitude:.4f}, lon={location.longitude:.4f}, elevation={location.elevation} ft ({location.elevation * FEET_TO_METERS:.1f} m)"
            )

            # Determine calculation time based on context:
            # - If target_date is None (main window): use current time for everything
            # - If target_date is set (calendar): use midnight for rise/set, current time for alt/az if today
            local_tz = get_local_timezone(location.latitude, location.longitude)
            now = datetime.now(local_tz)

            if self.target_date is None:
                # Opened from main window - use current time for everything
                calc_time = now
                logger.info(f"Info tab calculating moon info at current time: {calc_time}")
                moon_info = get_moon_info(location.latitude, location.longitude, calc_time, location.elevation)
                moon_info_midnight = None  # Not needed when using current time
            else:
                # Opened from calendar - create clean midnight datetime to avoid timezone drift
                target_midnight = datetime(
                    self.target_date.year,
                    self.target_date.month,
                    self.target_date.day,
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                    tzinfo=local_tz,
                )

                logger.info(f"Calendar target_date: {self.target_date}, target_midnight: {target_midnight}, now: {now}")
                is_today = now.date() == target_midnight.date()
                logger.info(
                    f"Is today check: now.date()={now.date()}, target_midnight.date()={target_midnight.date()}, is_today={is_today}"
                )

                # Always get moonrise/moonset from midnight of the target date
                moon_info_midnight = get_moon_info(
                    location.latitude, location.longitude, target_midnight, location.elevation
                )
                if moon_info_midnight:
                    logger.info(
                        f"Moonrise/moonset calculated for {target_midnight.date()}: rise={moon_info_midnight.moonrise_time}, set={moon_info_midnight.moonset_time}"
                    )

                if is_today:
                    # For today, get current alt/az/illumination
                    calc_time = now
                    logger.info(f"Info tab calculating moon info for today at current time: {calc_time}")
                    moon_info = get_moon_info(location.latitude, location.longitude, calc_time, location.elevation)
                else:
                    # For other days, use midnight for everything
                    calc_time = target_midnight
                    logger.info(f"Info tab calculating moon info for {target_midnight.date()} at midnight: {calc_time}")
                    moon_info = moon_info_midnight

            if moon_info:
                logger.info(
                    f"Info tab moon position: alt={moon_info.altitude_deg:.2f}°, az={moon_info.azimuth_deg:.2f}°"
                )
            if not moon_info:
                html_content = f"""
                    <h2 style='color: {colors["header"]};'>Moon Information</h2>
                    <p style='color: {colors["text"]};'>Error: Could not calculate moon information.</p>
                """
                self.info_text.setHtml(html_content)
                return

            # Format times - always use midnight calculation for rise/set/transit times
            # Determine which midnight to use for transit calculation
            if self.target_date is None:
                # Main window: use today's midnight
                transit_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                # Calendar: use target date's midnight
                transit_date = datetime(
                    self.target_date.year,
                    self.target_date.month,
                    self.target_date.day,
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                    tzinfo=local_tz,
                )

            # Calculate meridian transit
            # Pass moonrise and moonset times so we can search between them
            moonrise_time = None
            moonset_time = None
            if moon_info_midnight:
                moonrise_time = moon_info_midnight.moonrise_time
                moonset_time = moon_info_midnight.moonset_time
            elif self.target_date is None and moon_info:
                moonrise_time = moon_info.moonrise_time
                moonset_time = moon_info.moonset_time

            moonrise_time, moonset_time = self._normalize_moonrise_moonset(
                moonrise_time,
                moonset_time,
                location,
            )

            moonrise_str = "Not available"
            if moonrise_time:
                moonrise_str = format_local_time(moonrise_time, location.latitude, location.longitude)

            transit_time, transit_alt = self._calculate_moon_transit(transit_date, moonrise_time, moonset_time)
            transit_str = "Not available"
            if transit_time:
                transit_str = (
                    f"{format_local_time(transit_time, location.latitude, location.longitude)} ({transit_alt:.0f}°)"
                )

            moonset_str = "Not available"
            if moonset_time:
                moonset_str = format_local_time(moonset_time, location.latitude, location.longitude)

            # Format illumination
            illumination_pct = moon_info.illumination * 100

            # Format phase
            phase_name = moon_info.phase_name.value

            # Get traditional name and special events for full moons
            traditional_name = None
            is_supermoon = False
            distance_km = 0.0

            if moon_info.phase_name == MoonPhase.FULL_MOON:
                traditional_name = self._get_traditional_moon_name(now)
                distance_km = self._calculate_moon_distance(now)

                # Supermoon threshold: within 90% of perigee (356,500 km)
                supermoon_threshold_km = 356500 * 1.10  # 392,150 km
                is_supermoon = distance_km > 0 and distance_km <= supermoon_threshold_km

            # Build special events section
            special_events_html = ""
            if traditional_name or is_supermoon:
                special_events_html = f"""
                    <p style='margin-left: 20px; margin-top: 10px; margin-bottom: 5px;'>
                        <strong style='color: {colors["header"]};'>Special Events:</strong>
                    </p>
                """

                if traditional_name:
                    emoji = self._get_moon_name_emoji(traditional_name)
                    special_events_html += f"""
                        <p style='margin-left: 40px; margin-top: 5px; margin-bottom: 5px;'>
                            <span style='font-size: 16px;'>{emoji}</span>
                            <span style='color: {colors["green"]};'> {traditional_name}</span>
                        </p>
                    """

                if is_supermoon:
                    # Convert km to miles (1 km = 0.621371 miles)
                    distance_miles = distance_km * 0.621371
                    special_events_html += f"""
                        <p style='margin-left: 40px; margin-top: 5px; margin-bottom: 5px;'>
                            <span style='font-size: 16px;'>🌕</span>
                            <span style='color: {colors["green"]};'> Supermoon</span>
                            <span style='color: {colors["text_dim"]};'> (Distance: {distance_miles:,.0f} miles)</span>
                        </p>
                    """

            # Build HTML content
            html_content = f"""
                <h2 style='color: {colors["header"]};'>Moon Information</h2>

                <p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>
                    <strong style='color: {colors["text"]};'>Phase:</strong>
                    <span style='color: {colors["cyan"]};'>{phase_name}</span>
                </p>

                <p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>
                    <strong style='color: {colors["text"]};'>Illumination:</strong>
                    <span style='color: {colors["cyan"]};'>{illumination_pct:.1f}%</span>
                </p>

                {special_events_html}

                <p style='margin-left: 20px; margin-top: 10px; margin-bottom: 5px;'>
                    <strong style='color: {colors["text"]};'>Moonrise:</strong>
                    <span style='color: {colors["cyan"]};'>{moonrise_str}</span>
                </p>

                <p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>
                    <strong style='color: {colors["text"]};'>Passing the Meridian:</strong>
                    <span style='color: {colors["cyan"]};'>{transit_str}</span>
                </p>

                <p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>
                    <strong style='color: {colors["text"]};'>Moonset:</strong>
                    <span style='color: {colors["cyan"]};'>{moonset_str}</span>
                </p>

                <p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>
                    <strong style='color: {colors["text"]};'>Current Position:</strong>
                </p>
                <p style='margin-left: 40px; margin-top: 5px; margin-bottom: 5px;'>
                    <span style='color: {colors["text_dim"]};'>Altitude: {moon_info.altitude_deg:.1f}°</span>
                </p>
                <p style='margin-left: 40px; margin-top: 5px; margin-bottom: 5px;'>
                    <span style='color: {colors["text_dim"]};'>Azimuth: {moon_info.azimuth_deg:.1f}° ({self._azimuth_to_compass(moon_info.azimuth_deg)})</span>
                </p>
            """

            self.info_text.setHtml(html_content)

        except Exception as e:
            logger.exception("Error loading moon information")
            html_content = f"""
                <h2 style='color: {colors["header"]};'>Moon Information</h2>
                <p style='color: {colors["text"]};'>Error: {e!s}</p>
            """
            self.info_text.setHtml(html_content)

    def _get_traditional_moon_name(self, date: datetime) -> str | None:
        """
        Get traditional moon name for a full moon.

        Args:
            date: Date to check

        Returns:
            Traditional name or None
        """
        import json
        from pathlib import Path

        try:
            # Load traditional names
            json_path = Path(__file__).parent.parent.parent / "data" / "seed" / "traditional_moon_names.json"

            with open(json_path) as f:
                traditional_names = json.load(f)

            month = date.month
            month_data = traditional_names.get("month_names", {}).get(str(month))
            if month_data:
                return month_data.get("primary", "")

        except Exception as e:
            logger.debug(f"Could not load traditional moon names: {e}")

        return None

    def _calculate_moon_distance(self, date: datetime) -> float:
        """
        Calculate Earth-Moon distance in kilometers.

        Args:
            date: Date to calculate for

        Returns:
            Distance in kilometers
        """
        try:
            from skyfield.api import Topos

            from celestron_nexstar.api.ephemeris.skyfield_utils import get_skyfield_ephemeris, get_skyfield_timescale

            location = get_observer_location()
            ts = get_skyfield_timescale()
            t = ts.from_datetime(date)
            eph = get_skyfield_ephemeris("de421.bsp")

            earth = eph["earth"]
            moon = eph["moon"]

            elev_m = float(location.elevation or 0.0) * FEET_TO_METERS
            observer = earth + Topos(
                latitude_degrees=location.latitude,
                longitude_degrees=location.longitude,
                elevation_m=elev_m,
            )

            moon_distance = observer.at(t).observe(moon).distance()
            return moon_distance.km

        except Exception as e:
            logger.debug(f"Could not calculate moon distance: {e}")
            return 0.0

    def _normalize_moonrise_moonset(
        self,
        moonrise_time: datetime | None,
        moonset_time: datetime | None,
        location: Any,
    ) -> tuple[datetime | None, datetime | None]:
        """
        Ensure moonset is paired with the next moonrise for the same overnight cycle.

        If the next moonset occurs before the next moonrise (e.g., just after midnight),
        look up the following moonset after the moonrise.
        """
        if not moonrise_time or not moonset_time:
            return moonrise_time, moonset_time

        if moonset_time > moonrise_time:
            return moonrise_time, moonset_time

        try:
            search_dt = moonrise_time + timedelta(minutes=1)
            moon_info_after_rise = get_moon_info(
                location.latitude,
                location.longitude,
                search_dt,
                location.elevation,
            )
            if (
                moon_info_after_rise
                and moon_info_after_rise.moonset_time
                and moon_info_after_rise.moonset_time > moonrise_time
            ):
                logger.info(
                    "Adjusted moonset after moonrise: original=%s adjusted=%s",
                    moonset_time,
                    moon_info_after_rise.moonset_time,
                )
                return moonrise_time, moon_info_after_rise.moonset_time
        except Exception as e:
            logger.debug(f"Could not normalize moonrise/moonset: {e}")

        return moonrise_time, moonset_time

    def _calculate_moon_transit(
        self, date: datetime, moonrise_time: datetime | None = None, moonset_time: datetime | None = None
    ) -> tuple[datetime | None, float]:
        """
        Calculate moon meridian passage (transit) time and altitude for a given date.

        Args:
            date: Date to calculate transit for (should be midnight local time)
            moonrise_time: If provided, search from this time
            moonset_time: If provided, search until this time

        Returns:
            Tuple of (transit_time, altitude_deg) or (None, 0.0) if calculation fails
        """
        try:
            from skyfield import almanac
            from skyfield.api import Topos

            from celestron_nexstar.api.ephemeris.skyfield_utils import get_skyfield_ephemeris, get_skyfield_timescale

            location = get_observer_location()
            ts = get_skyfield_timescale()
            eph = get_skyfield_ephemeris("de421.bsp")

            earth = eph["earth"]
            moon = eph["moon"]

            elev_m = float(location.elevation or 0.0) * FEET_TO_METERS
            topos = Topos(
                latitude_degrees=location.latitude,
                longitude_degrees=location.longitude,
                elevation_m=elev_m,
            )
            observer = earth + topos

            # Search for meridian transit
            from datetime import timedelta

            if moonrise_time and moonset_time:
                # Check if moonset is after moonrise (proper pairing)
                # If moonset is before moonrise, it's from the previous night's cycle
                if moonset_time > moonrise_time:
                    # Search between moonrise and moonset
                    t0 = ts.from_datetime(moonrise_time)
                    t1 = ts.from_datetime(moonset_time)
                    logger.info(f"Searching for transit between moonrise={moonrise_time} and moonset={moonset_time}")
                else:
                    # Moonset is before moonrise (previous cycle), search from moonrise forward
                    t0 = ts.from_datetime(moonrise_time)
                    t1 = ts.from_datetime(moonrise_time + timedelta(hours=18))  # Transit typically within 6-12 hours
                    logger.info(
                        f"Moonset before moonrise (prev cycle), searching from moonrise={moonrise_time} for 18 hours"
                    )
            elif moonrise_time:
                # Only have moonrise, search forward
                t0 = ts.from_datetime(moonrise_time)
                t1 = ts.from_datetime(moonrise_time + timedelta(hours=18))
                logger.info(f"Searching for transit from moonrise={moonrise_time} for 18 hours")
            else:
                # Fallback: search from midnight for 48 hours to catch the transit
                t0 = ts.from_datetime(date)
                t1 = ts.from_datetime(date + timedelta(hours=48))
                logger.info(f"Searching for transit from {date} for 48 hours")

            # Find meridian transits using culmination (when altitude is maximum)
            f = almanac.meridian_transits(eph, moon, topos)
            times, events = almanac.find_discrete(t0, t1, f)

            if len(times) > 0:
                # Filter for upper transits (culminations) only, not lower transits
                # events: True = upper transit (culmination), False = lower transit
                for i, event in enumerate(events):
                    if event:  # Upper transit
                        transit_time_skyfield = times[i]
                        transit_datetime = transit_time_skyfield.utc_datetime().astimezone(date.tzinfo)

                        # Calculate altitude at transit
                        moon_apparent = observer.at(transit_time_skyfield).observe(moon).apparent()
                        alt, _az, _ = moon_apparent.altaz()
                        altitude_deg = float(alt.degrees)

                        logger.info(f"Moon transit calculated: {transit_datetime}, altitude={altitude_deg:.1f}°")
                        return (transit_datetime, altitude_deg)

            logger.debug(f"No moon transit found for {date.date()}")
            return (None, 0.0)

        except Exception as e:
            logger.error(f"Could not calculate moon transit: {e}", exc_info=True)
            return (None, 0.0)

    def _get_moon_name_emoji(self, moon_name: str) -> str:
        """Get emoji for traditional moon name."""
        moon_emoji_map = {
            "Wolf": "🐺",
            "Snow": "❄️",
            "Worm": "🪱",
            "Pink": "🌸",
            "Flower": "🌼",
            "Strawberry": "🍓",
            "Buck": "🦌",
            "Sturgeon": "🐟",
            "Corn": "🌽",
            "Hunter": "🏹",
            "Beaver": "🦫",
            "Cold": "🥶",
            "Harvest": "🌾",
        }

        for key, emoji in moon_emoji_map.items():
            if key in moon_name:
                return emoji

        return "🌕"

    def _load_moon_plot(self) -> None:
        """Load moon plot in a background thread."""
        # Stop any existing thread
        if self._plot_thread is not None:
            self._safe_stop_thread(self._plot_thread)
            self._plot_thread = None

        is_dark = self._is_dark_theme()

        # Create and start worker thread
        self._plot_thread = MoonPlotWorkerThread(is_dark, self.target_date, self)
        self._plot_thread.plot_ready.connect(self._on_plot_ready)
        self._plot_thread.error_occurred.connect(self._on_plot_error)
        self._plot_thread.finished.connect(self._on_plot_thread_finished)
        self._plot_thread.start()

    def _load_moon_disk(self) -> None:
        """Load oriented moon disk in a background thread."""
        if self._disk_thread is not None:
            self._safe_stop_thread(self._disk_thread)
            self._disk_thread = None

        is_dark = self._is_dark_theme()
        self._disk_thread = MoonDiskWorkerThread(is_dark, self.target_date, self)
        self._disk_thread.disk_ready.connect(self._on_disk_ready)
        self._disk_thread.error_occurred.connect(self._on_disk_error)
        self._disk_thread.finished.connect(self._on_disk_thread_finished)
        self._disk_thread.start()

    def _on_plot_ready(self, png_data: bytes) -> None:
        """Handle plot generation completion."""
        # Clear the layout
        layout = self.plot_widget.layout()
        if layout:
            while layout.count():
                child = layout.takeAt(0)
                widget = child.widget()
                if widget:
                    widget.deleteLater()

        # Create pixmap from PNG data
        pixmap = QPixmap()
        # Use the single-arg overload to avoid PySide/Shiboken overload resolution issues
        # (a TypeError here can include the entire PNG buffer in the exception text, spamming stdout).
        ok = pixmap.loadFromData(png_data)
        if not ok:
            self._on_plot_error("Failed to decode generated PNG image data.")
            return

        # Create label with the plot
        plot_label = QLabel()
        plot_label.setPixmap(pixmap)
        plot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        plot_label.setScaledContents(True)

        # Add to layout
        layout = self.plot_widget.layout()
        if layout:
            layout.addWidget(plot_label)

        # Thread will clean itself up via finished signal

    def _on_plot_error(self, error_message: str) -> None:
        """Handle plot generation error."""
        logger.error(f"Moon plot error: {error_message}")

        # Clear the layout
        layout = self.plot_widget.layout()
        if layout:
            while layout.count():
                child = layout.takeAt(0)
                widget = child.widget()
                if widget:
                    widget.deleteLater()

        # Show error message with more details
        error_label = QLabel(f"Error loading plot:\n{error_message}\n\nCheck logs for details.")
        error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        error_label.setWordWrap(True)
        layout = self.plot_widget.layout()
        if layout:
            layout.addWidget(error_label)

        # Thread will clean itself up via finished signal

    def _on_disk_ready(self, png_data: bytes) -> None:
        """Handle moon disk generation completion."""
        # Clear the layout
        layout = self.disk_widget.layout()
        if layout:
            while layout.count():
                child = layout.takeAt(0)
                widget = child.widget()
                if widget:
                    widget.deleteLater()

        pixmap = QPixmap()
        ok = pixmap.loadFromData(png_data)
        if not ok:
            self._on_disk_error("Failed to decode generated Moon disk PNG.")
            return

        disk_label = QLabel()
        disk_label.setPixmap(pixmap)
        disk_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        disk_label.setScaledContents(True)

        if layout:
            layout.addWidget(disk_label)

    def _on_disk_error(self, error_message: str) -> None:
        """Handle moon disk generation error."""
        logger.error(f"Moon disk error: {error_message}")
        layout = self.disk_widget.layout()
        if layout:
            while layout.count():
                child = layout.takeAt(0)
                widget = child.widget()
                if widget:
                    widget.deleteLater()

        error_label = QLabel(f"Error loading moon disk:\n{error_message}\n\nCheck logs for details.")
        error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        error_label.setWordWrap(True)
        if layout:
            layout.addWidget(error_label)
