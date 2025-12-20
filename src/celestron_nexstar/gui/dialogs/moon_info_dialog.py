"""
Dialog to display moon information.
"""

import logging
from datetime import UTC, datetime
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
from celestron_nexstar.api.location.observer import get_observer_location


if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


class MoonPlotWorkerThread(QThread):
    """Worker thread to generate moon plot using starplot."""

    plot_ready = Signal(bytes)  # PNG image data
    error_occurred = Signal(str)  # Error message

    def __init__(self, is_dark_theme: bool, parent: QWidget | None = None) -> None:
        """Initialize the worker thread."""
        super().__init__(parent)
        self.is_dark_theme = is_dark_theme

    def run(self) -> None:
        """Generate the moon plot in a background thread."""
        try:
            logger.info("Starting moon plot generation...")
            import starplot  # type: ignore[import-untyped]
            from starplot.styles import PlotStyle, extensions  # type: ignore[import-untyped]

            # Get observer location and time
            logger.debug("Getting observer location...")
            location = get_observer_location()
            now = datetime.now(UTC)

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
            # Show a 90-degree field of view
            # Starplot requires altitude_min < altitude_max and values within [0, 90].
            # When the Moon is below the horizon, (alt+45) can be < 0 which yields an invalid range.
            alt_center = max(0.0, min(90.0, float(moon_info.altitude_deg)))
            alt_min = max(0.0, alt_center - 45.0)
            alt_max = min(90.0, alt_center + 45.0)
            if alt_max <= alt_min:
                # Minimal valid window
                alt_min = max(0.0, alt_center - 1.0)
                alt_max = min(90.0, alt_center + 1.0)
            if alt_max <= alt_min:
                # Last resort: full altitude range
                alt_min, alt_max = 0.0, 90.0
            altitude_range = (alt_min, alt_max)
            # Azimuth wraps around 360
            azimuth_min = (moon_info.azimuth_deg - 45) % 360
            azimuth_max = (moon_info.azimuth_deg + 45) % 360
            azimuth_range = (0, 360) if azimuth_min > azimuth_max else (azimuth_min, azimuth_max)
            # Starplot limits azimuth range to 180 degrees max
            if azimuth_range[1] - azimuth_range[0] > 180:
                azimuth_range = (0, 180)

            # Create horizon plot
            logger.info(f"Creating horizon plot: altitude={altitude_range}, azimuth={azimuth_range}")
            plot = starplot.HorizonPlot(
                observer=starplot_observer,
                ephemeris=ephemeris_file,
                altitude=altitude_range,
                azimuth=azimuth_range,
                style=plot_style,
                # 4096 is beautiful but slow; 2048 is much faster and still crisp for an in-dialog plot.
                resolution=2048,
                scale=1.0,
                autoscale=True,
            )
            logger.debug("Horizon plot created successfully")

            # Plot stars
            logger.debug("Adding stars...")
            # Stars are the expensive part; use a modest magnitude cutoff and disable labels.
            from starplot import _  # type: ignore[import-untyped]

            plot.stars(where=[_.magnitude < 6.5], where_labels=[False])  # type: ignore[arg-type]
            logger.debug("Stars added successfully")

            # Plot the moon
            logger.debug("Adding moon...")
            # Use Starplot's HorizonPlot.moon kwargs for better visuals.
            # See: https://starplot.dev/reference-horizonplot/#starplot.HorizonPlot.moon
            plot.moon(true_size=True, show_phase=True, label="Moon", legend_label="Moon")  # type: ignore[no-untyped-call]
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

    def __init__(self, is_dark_theme: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.is_dark_theme = is_dark_theme

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
            now = datetime.now(UTC)

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

            elev_m = 0.0
            try:
                from celestron_nexstar.api.location.observer import FEET_TO_METERS

                elev_m = float(location.elevation or 0.0) * FEET_TO_METERS
            except Exception:
                elev_m = 0.0
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

            # Waxing/waning from RA difference + illumination (same logic as calculate_moon_phase)
            moon_ra_h = float(moon_ra.hours)
            sun_ra_h = float(sun_ra.hours)
            ra_diff = moon_ra_h - sun_ra_h
            if ra_diff > 12:
                ra_diff -= 24
            elif ra_diff < -12:
                ra_diff += 24
            if illumination > 0.5:
                is_waxing = False
            elif illumination < 0.5:
                is_waxing = True
            else:
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

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the moon info dialog."""
        super().__init__(parent)
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
        font_family = (
            f"'{monospace_font}', 'Courier New', 'Consolas', 'Monaco', 'Menlo', monospace"
            if monospace_font
            else "'Courier New', 'Consolas', 'Monaco', 'Menlo', monospace"
        )

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
            now = datetime.now(UTC)

            moon_info = get_moon_info(location.latitude, location.longitude, now)
            if not moon_info:
                html_content = f"""
                    <h2 style='color: {colors["header"]};'>Moon Information</h2>
                    <p style='color: {colors["text"]};'>Error: Could not calculate moon information.</p>
                """
                self.info_text.setHtml(html_content)
                return

            # Format times
            moonrise_str = "Not available"
            if moon_info.moonrise_time:
                moonrise_str = format_local_time(moon_info.moonrise_time, location.latitude, location.longitude)

            moonset_str = "Not available"
            if moon_info.moonset_time:
                moonset_str = format_local_time(moon_info.moonset_time, location.latitude, location.longitude)

            # Format illumination
            illumination_pct = moon_info.illumination * 100

            # Format phase
            phase_name = moon_info.phase_name.value

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

                <p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>
                    <strong style='color: {colors["text"]};'>Moonrise:</strong>
                    <span style='color: {colors["cyan"]};'>{moonrise_str}</span>
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
                    <span style='color: {colors["text_dim"]};'>Azimuth: {moon_info.azimuth_deg:.1f}°</span>
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

    def _load_moon_plot(self) -> None:
        """Load moon plot in a background thread."""
        # Stop any existing thread
        if self._plot_thread is not None:
            self._safe_stop_thread(self._plot_thread)
            self._plot_thread = None

        is_dark = self._is_dark_theme()

        # Create and start worker thread
        self._plot_thread = MoonPlotWorkerThread(is_dark, self)
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
        self._disk_thread = MoonDiskWorkerThread(is_dark, self)
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
