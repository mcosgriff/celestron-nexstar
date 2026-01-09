"""
Dialog to display detailed information about a constellation, including its stars.
"""

import itertools
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid  # type: ignore[import-untyped]


if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


class DoubleClickableTextBrowser(QTextBrowser):
    """QTextBrowser that supports custom double-click handling and link clicks."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the text browser."""
        super().__init__(parent)
        self._double_click_handler: Any = None
        self._link_click_handler: Any = None
        self._saved_source: QUrl | None = None
        # Connect to anchorClicked signal for link handling
        self.anchorClicked.connect(self._on_anchor_clicked)

    def set_double_click_handler(self, handler: Any) -> None:
        """Set the handler function to call on double-click."""
        self._double_click_handler = handler

    def set_link_click_handler(self, handler: Any) -> None:
        """Set the handler function to call on link click."""
        self._link_click_handler = handler

    def set_source(self, url: QUrl | str, type: Any = None) -> None:
        """Override setSource to prevent navigation to starinfo:// URLs."""
        url_str = url.toString() if isinstance(url, QUrl) else url
        if url_str.startswith("starinfo://"):
            # Don't navigate to starinfo:// URLs - we handle them via anchorClicked
            # Store the current source to prevent clearing
            if self._saved_source is None:
                self._saved_source = self.source()
            return
        # For other URLs, use default behavior
        self._saved_source = None  # Clear saved source for valid URLs
        super().setSource(url, type)

    def _on_anchor_clicked(self, url: QUrl) -> None:
        """Handle anchor clicks."""
        url_str = url.toString()
        if url_str.startswith("starinfo://"):
            # Handle star info links ourselves - don't let QTextBrowser navigate
            if self._link_click_handler is not None:
                self._link_click_handler(url_str)
            # Don't call setSource for starinfo links to avoid warnings
        elif url_str.startswith(("http://", "https://")):
            # For other links (like http/https), use default behavior (open in browser)
            from PySide6.QtGui import QDesktopServices

            QDesktopServices.openUrl(url)

    def mouseDoubleClickEvent(self, event: Any) -> None:  # noqa: N802
        """Override double-click event to call custom handler if set."""
        if self._double_click_handler:
            self._double_click_handler(event)
        else:
            super().mouseDoubleClickEvent(event)


class MapGenerationWorkerThread(QThread):
    """Worker thread to generate constellation map in the background."""

    map_ready = Signal(bytes)  # type: ignore[type-arg,misc]  # Emits map image data

    def __init__(self, boundaries: dict[str, Any], is_dark_theme: bool) -> None:
        """Initialize the map generation worker thread."""
        super().__init__()
        self.boundaries = boundaries
        self.is_dark_theme = is_dark_theme

    def run(self) -> None:
        """Generate map in background thread."""
        try:
            if self.isInterruptionRequested():
                return

            from starplot import LambertAzEqArea, MapPlot, _  # type: ignore[import-untyped]
            from starplot.styles import PlotStyle, extensions  # type: ignore[import-untyped]

            # Get ephemeris file path (use downloaded ephemeris if available)
            from celestron_nexstar.api.ephemeris.ephemeris_manager import get_ephemeris_directory

            ephemeris_dir = get_ephemeris_directory()
            # Try to find an available ephemeris file (prefer de421 or de440)
            ephemeris_file = None
            for preferred_name in ["de421.bsp", "de440.bsp", "de421_2001.bsp"]:
                eph_path = ephemeris_dir / preferred_name
                if eph_path.exists():
                    ephemeris_file = preferred_name
                    break

            # If no preferred file found, use default (starplot will handle it)
            if ephemeris_file is None:
                ephemeris_file = "de421_2001.bsp"  # Starplot default

            # Determine style based on theme
            if self.is_dark_theme:
                plot_style = PlotStyle().extend(extensions.BLUE_DARK, extensions.MAP)
            else:
                plot_style = PlotStyle().extend(extensions.BLUE_LIGHT, extensions.MAP)

            # Calculate RA/Dec range from boundaries
            # Add padding around the constellation boundaries
            # A bit more padding helps avoid clipping at the edges.
            padding_ra = 0.5  # hours
            # Slightly more padding helps avoid clipping key pattern stars (e.g., Meissa in Orion),
            # but keep it conservative for near-polar constellations where extra DEC padding can
            # dramatically widen the RA extent after projection.
            padding_dec = 3.0  # degrees (non-polar default)

            ra_min_hours = self.boundaries["ra_min_hours"]
            ra_max_hours = self.boundaries["ra_max_hours"]
            # Keep a copy of the *official* bounds for projection heuristics (Cassiopeia example uses polar
            # projection even with a tighter dec_max in the plot window).
            proj_dec_min = float(self.boundaries["dec_min_degrees"])
            proj_dec_max = float(self.boundaries["dec_max_degrees"])
            if proj_dec_max >= 80.0 or proj_dec_min <= -80.0:
                padding_dec = 2.0

            dec_min = proj_dec_min - padding_dec
            dec_max = proj_dec_max + padding_dec
            # Starplot requires declination bounds to be within [-90, 90]
            dec_min = max(-90.0, float(dec_min))
            dec_max = min(90.0, float(dec_max))
            if dec_min >= dec_max:
                # Fallback to a safe 10° window around the constellation center declination
                center_dec = float(self.boundaries.get("dec_degrees", (dec_min + dec_max) / 2))
                dec_min = max(-90.0, center_dec - 5.0)
                dec_max = min(90.0, center_dec + 5.0)

            # Prefer "pattern star" bounds (closer to Starplot examples) over full IAU border bounds.
            # The DB's constellation min/max are derived from border polygons and can be much larger than the
            # visual constellation pattern (e.g. Cassiopeia). Using the brightest stars in the constellation
            # gives a tighter, more human-friendly plot region.
            use_star_bounds = False
            try:
                constellation_name = self.boundaries.get("constellation_name")
                if isinstance(constellation_name, str) and constellation_name.strip():
                    from sqlalchemy import select

                    from celestron_nexstar.api.database.database import get_database
                    from celestron_nexstar.api.database.models import ConstellationModel, StarModel

                    db = get_database()
                    with db.get_session() as session:
                        constellation_model = session.scalar(
                            select(ConstellationModel).where(ConstellationModel.name == constellation_name).limit(1)
                        )
                        if constellation_model is not None:
                            # For map *bounds*, prefer the constellation's main pattern stars (brighter).
                            # This matches Starplot examples better than using all faint stars that can
                            # extend the official IAU region toward the pole and dramatically widen the map.
                            #
                            # Strategy:
                            # - Use *known-magnitude* stars (exclude NULL magnitudes for bounds)
                            # - Prefer brighter subsets first (3.5, 4.0, 4.5), then fall back to 6.5
                            # - Limit to the brightest 60 to avoid "full constellation population" sprawl
                            # - Start with mag 3.5 to include all bright named stars (e.g., Muscida, Talitha in UMa)
                            star_rows: list[tuple[float, float]] = []
                            for mag_limit in (3.5, 4.0, 4.5, 6.5):
                                rows = session.execute(
                                    select(StarModel.ra_hours, StarModel.dec_degrees)
                                    .where(
                                        StarModel.constellation_id == constellation_model.id,
                                        StarModel.ra_hours.isnot(None),
                                        StarModel.dec_degrees.isnot(None),
                                        StarModel.magnitude.isnot(None),
                                        StarModel.magnitude <= mag_limit,
                                    )
                                    .order_by(StarModel.magnitude.asc())
                                    .limit(60)
                                ).all()
                                star_rows = [(float(r[0]), float(r[1])) for r in rows]
                                if len(star_rows) >= 5:
                                    break
                            if len(star_rows) >= 5:
                                ra_vals = [float(r[0]) % 24.0 for r in star_rows]
                                dec_vals = [float(r[1]) for r in star_rows]

                                # Tight declination window from stars (with padding + clamp)
                                dec_min = max(-90.0, min(dec_vals) - padding_dec)
                                dec_max = min(90.0, max(dec_vals) + padding_dec)

                                # Update projection decision variables to use star-based bounds
                                proj_dec_min = min(dec_vals)
                                proj_dec_max = max(dec_vals)

                                # RA window: minimal circular interval containing the stars (gap method)
                                ra_sorted = sorted(ra_vals)
                                gaps: list[tuple[float, float, float]] = []  # (gap, start, end)
                                for a, b in itertools.pairwise(ra_sorted):
                                    gaps.append((b - a, a, b))
                                # wrap gap
                                gaps.append(((ra_sorted[0] + 24.0) - ra_sorted[-1], ra_sorted[-1], ra_sorted[0] + 24.0))
                                gap_size, gap_start, gap_end = max(gaps, key=lambda t: t[0])
                                span_h = 24.0 - gap_size
                                # interval is [gap_end, gap_start + 24] in unwrapped hours
                                interval_start = gap_end
                                interval_end = gap_start + 24.0
                                center_h = (interval_start + interval_end) / 2.0
                                window_h = min(max(span_h + (padding_ra * 2.0), 2.0), 8.0)
                                ra_min_h = center_h - (window_h / 2.0)
                                ra_max_h = center_h + (window_h / 2.0)
                                ra_min_deg = ra_min_h * 15.0
                                ra_max_deg = ra_max_h * 15.0
                                use_star_bounds = True
            except Exception:
                # Keep existing bounds logic if star-based bounds fails for any reason.
                use_star_bounds = False

            # RA window (hours): keep a tight, centered view.
            # For wrap-around constellations (e.g. 23h..2h), we allow ra_max to exceed 24h
            # (and thus ra_max_deg > 360°) like Starplot's Cassiopeia example.
            # RA bounds can wrap across 0h. Some sources provide naive numeric min/max which can
            # incorrectly yield a huge span (e.g. ra_min=1h, ra_max=23h for a constellation that
            # actually spans 23h..1h). Prefer the shorter circular interval whenever span > 12h.
            ra_min_f = float(ra_min_hours) % 24.0
            ra_max_f = float(ra_max_hours) % 24.0
            wraps_around = ra_max_f < ra_min_f
            if wraps_around:
                span_h = (24.0 - ra_min_f) + ra_max_f
                # If the wrapped span is huge, the stored bounds are likely inverted (common with
                # naive min/max over a wrapped interval). Prefer the shorter (non-wrapped) interval.
                if span_h > 12.0:
                    wraps_around = False
                    interval_start_h = ra_max_f
                    interval_end_h = ra_min_f
                    span_h = interval_end_h - interval_start_h
                else:
                    interval_start_h = ra_min_f
                    interval_end_h = ra_min_f + span_h
            else:
                span_h = ra_max_f - ra_min_f
                if span_h > 12.0:
                    wraps_around = True
                    interval_start_h = ra_max_f
                    interval_end_h = ra_min_f + 24.0
                    span_h = interval_end_h - interval_start_h
                else:
                    interval_start_h = ra_min_f
                    interval_end_h = ra_max_f
            # Desired window: actual span + padding, but cap to avoid "whole-sky" views.
            max_window_h = 8.0
            window_h = min(max(span_h + (padding_ra * 2.0), 2.0), max_window_h)
            center_h = ((interval_start_h + interval_end_h) / 2.0) % 24.0

            ra_min_h = center_h - (window_h / 2.0)
            ra_max_h = center_h + (window_h / 2.0)
            # Normalize into a consistent (possibly unwrapped) interval where ra_max_h > ra_min_h.
            if ra_min_h < 0.0:
                ra_min_h += 24.0
                ra_max_h += 24.0
            if ra_max_h <= ra_min_h:
                ra_max_h += 24.0

            # Convert RA from hours to degrees for starplot (RA * 15 = degrees)
            if not use_star_bounds:
                ra_min_deg = ra_min_h * 15.0
                ra_max_deg = ra_max_h * 15.0

            # Final RA normalization / safety:
            # - ensure ra_max_deg > ra_min_deg
            # - keep ra_min_deg within [0, 360) by shifting both ends together
            # - cap span so it can never look like a full-sky plot
            if ra_max_deg <= ra_min_deg:
                ra_max_deg += 360.0
            # Shift into a Cassiopeia-like representation (ra_min in [0,360))
            while ra_min_deg < 0.0:
                ra_min_deg += 360.0
                ra_max_deg += 360.0
            while ra_min_deg >= 360.0:
                ra_min_deg -= 360.0
                ra_max_deg -= 360.0
            # Cap the plotted RA span (in degrees)
            # Hard cap for safety: keep within the same maximum window as our hours cap (8h = 120°).
            max_span_deg = 120.0  # 8h
            span_deg = ra_max_deg - ra_min_deg
            if span_deg > max_span_deg:
                center = (ra_min_deg + ra_max_deg) / 2.0
                ra_min_deg = center - (max_span_deg / 2.0)
                ra_max_deg = center + (max_span_deg / 2.0)

            # Projection:
            # - For near-polar constellations (e.g. Cassiopeia), Starplot examples use a polar-centered
            #   Lambert Azimuthal Equal Area projection (center_dec=±90). This keeps label placement
            #   centered and reduces distortions compared to Miller near the pole.
            # - Otherwise, use Miller for mid-latitude constellations.
            center_dec_deg = float(self.boundaries.get("dec_degrees", (dec_min + dec_max) / 2.0))
            center_dec_deg = max(-90.0, min(90.0, center_dec_deg))
            # Prefer centering RA on the plotted window (handles wrap-around cleanly)
            center_ra_deg = ((ra_min_deg + ra_max_deg) / 2.0) % 360.0

            # IMPORTANT:
            # Starplot's Miller projection effectively behaves like a full-sky projection (it will expand RA to 360°),
            # which is why users see "24h wide" even when we request a narrow RA window. Use LambertAzEqArea for
            # constellation maps so ra_min/ra_max cropping works (matches Starplot examples).
            if proj_dec_max >= 80.0:
                projection = LambertAzEqArea(center_ra=center_ra_deg, center_dec=90)
            elif proj_dec_min <= -80.0:
                projection = LambertAzEqArea(center_ra=center_ra_deg, center_dec=-90)
            else:
                projection = LambertAzEqArea(center_ra=center_ra_deg, center_dec=center_dec_deg)

            # Create map plot
            plot = MapPlot(
                projection=projection,
                ra_min=ra_min_deg,
                ra_max=ra_max_deg,
                dec_min=dec_min,
                dec_max=dec_max,
                ephemeris=ephemeris_file,  # Use downloaded ephemeris file
                style=plot_style,
                # Match Starplot examples (e.g. Cassiopeia): ~4000px is crisp and predictable.
                resolution=4000,
                autoscale=False,
                scale=1.2,
            )

            # Add gridlines.
            # For polar/azimuthal projections, Starplot examples typically show declination gridlines only
            # (otherwise you can end up with a full 0-24h RA ring that *looks* like a 24h-wide plot).
            try:
                if isinstance(projection, LambertAzEqArea):
                    # Match Starplot examples: show a full declination ladder for polar maps.
                    plot.gridlines(dec_locations=list(range(0, 90, 5)))
                else:
                    plot.gridlines()
            except Exception:
                plot.gridlines()
            # Plot only this constellation's lines to match Starplot examples and keep label placement centered.
            iau_id = str(self.boundaries.get("iau_id") or self.boundaries.get("abbreviation") or "").strip().lower()
            if iau_id:
                plot.constellations(where=[_.iau_id == iau_id])  # type: ignore[arg-type]
            else:
                plot.constellations()
            plot.constellation_borders()

            try:
                constellation_name = str(self.boundaries.get("constellation_name") or "")
                logger.info(
                    "Constellation map bounds: name=%s iau_id=%s "
                    "requested_ra_min=%.3f requested_ra_max=%.3f requested_span=%.3f "
                    "requested_dec_min=%.3f requested_dec_max=%.3f "
                    "plot_ra_min=%.3f plot_ra_max=%.3f plot_span=%.3f plot_dec_min=%.3f plot_dec_max=%.3f",
                    constellation_name,
                    iau_id,
                    float(ra_min_deg),
                    float(ra_max_deg),
                    float(ra_max_deg) - float(ra_min_deg),
                    float(dec_min),
                    float(dec_max),
                    float(getattr(plot, "ra_min", ra_min_deg)),
                    float(getattr(plot, "ra_max", ra_max_deg)),
                    float(getattr(plot, "ra_max", ra_max_deg)) - float(getattr(plot, "ra_min", ra_min_deg)),
                    float(getattr(plot, "dec_min", dec_min)),
                    float(getattr(plot, "dec_max", dec_max)),
                )
            except Exception:
                pass

            plot.stars(where=[_.magnitude < 8], bayer_labels=True, where_labels=[_.magnitude < 5])

            plot.open_clusters(
                where=[_.size < 1, _.magnitude < 9],
                where_labels=[False],
                true_size=False,
            )
            plot.open_clusters(
                # plot larger clusters as their true apparent size
                where=[_.size > 1, (_.magnitude < 9) | (_.magnitude.isnull())],
                where_labels=[False],
            )

            plot.nebula(
                where=[(_.magnitude < 9) | (_.magnitude.isnull())],
            )

            plot.constellation_labels()
            plot.milky_way()
            plot.ecliptic()

            # Export to PNG in memory
            import io

            img_buffer = io.BytesIO()
            plot.export(img_buffer, format="png", padding=0.5, transparent=True)  # type: ignore[no-untyped-call]
            img_buffer.seek(0)
            map_data = img_buffer.read()

            # Emit results
            self.map_ready.emit(map_data)
        except Exception as e:
            logger.error(f"Error generating constellation map: {e}", exc_info=True)
            # Emit empty bytes on error
            self.map_ready.emit(b"")


class StarVisibilityWorkerThread(QThread):
    """Worker thread to calculate star visibility for a constellation in the background."""

    stars_ready = Signal(dict, list)  # type: ignore[type-arg,misc]  # Emits (constellation_data, star_data)

    def __init__(
        self,
        constellation_name: str,
        constellation_data: dict[str, Any],
        boundaries: dict[str, float] | None,
    ) -> None:
        """Initialize the star visibility worker thread."""
        super().__init__()
        self.constellation_name = constellation_name
        self.constellation_data = constellation_data
        self.boundaries = boundaries

    def run(self) -> None:
        """Calculate star visibility in background thread."""
        try:
            # Check if thread should stop
            if self.isInterruptionRequested():
                return

            from celestron_nexstar.api.core.enums import SkyBrightness
            from celestron_nexstar.api.core.exceptions import DatabaseError
            from celestron_nexstar.api.core.utils import ra_dec_to_alt_az
            from celestron_nexstar.api.database.database import get_database
            from celestron_nexstar.api.location.light_pollution import get_light_pollution_data
            from celestron_nexstar.api.location.observer import get_observer_location
            from celestron_nexstar.api.observation.observation_planner import ObservationPlanner
            from celestron_nexstar.api.observation.optics import get_current_configuration
            from celestron_nexstar.api.observation.visibility import assess_visibility

            # Get conditions
            location = get_observer_location()
            config = get_current_configuration()
            planner = ObservationPlanner()
            conditions = planner.get_tonight_conditions()

            db = get_database()
            with db.get_session() as session:
                # Get sky brightness from light pollution
                try:
                    light_pollution = get_light_pollution_data(session, location.latitude, location.longitude)
                    bortle_to_sky_brightness = {
                        1: SkyBrightness.EXCELLENT,
                        2: SkyBrightness.EXCELLENT,
                        3: SkyBrightness.GOOD,
                        4: SkyBrightness.FAIR,
                        5: SkyBrightness.FAIR,
                        6: SkyBrightness.POOR,
                        7: SkyBrightness.URBAN,
                        8: SkyBrightness.URBAN,
                        9: SkyBrightness.URBAN,
                    }
                    sky_brightness = bortle_to_sky_brightness.get(
                        light_pollution.bortle_class.value, SkyBrightness.FAIR
                    )
                except DatabaseError:
                    # Light pollution data not available, use default
                    logger.warning("Light pollution data not available, using default sky brightness")
                    sky_brightness = SkyBrightness.FAIR

                # Get stars in this constellation
                stars = db.filter_objects(object_type="star", constellation=self.constellation_name, limit=100)

                # Calculate visibility for each star
                star_data = []
                for star in stars:
                    # Check if thread should stop
                    if self.isInterruptionRequested():
                        return

                    # Calculate visibility info
                    vis_info = assess_visibility(
                        star,
                        config=config,
                        sky_brightness=sky_brightness,
                        min_altitude_deg=20.0,
                        observer_lat=location.latitude,
                        observer_lon=location.longitude,
                        dt=conditions.timestamp,
                    )
                    # Only include stars that are actually visible with the configured telescope/conditions
                    if not vis_info.is_visible:
                        continue

                    # Calculate altitude/azimuth
                    try:
                        alt, az = ra_dec_to_alt_az(  # noqa: RUF059
                            star.ra_hours,
                            star.dec_degrees,
                            location.latitude,
                            location.longitude,
                            conditions.timestamp,
                        )
                    except Exception:
                        alt, _az = 0.0, 0.0

                    # Use the same visibility probability calculation as the stars table
                    visibility_prob_result = planner._calculate_visibility_probability(star, conditions, vis_info)

                    # Handle tuple return (probability, explanations) or just probability
                    if isinstance(visibility_prob_result, tuple):
                        visibility_probability = visibility_prob_result[0]
                    else:
                        visibility_probability = visibility_prob_result

                    star_data.append(
                        {
                            "obj": star,
                            "apparent_magnitude": star.magnitude,
                            "altitude": alt,
                            "visibility_probability": visibility_probability,
                            "vis_info": vis_info,
                        }
                    )

                # Sort by visibility probability descending, then by magnitude (brighter first)
                def sort_key(x: dict[str, Any]) -> tuple[float, float]:
                    """Sort key function for star data."""
                    prob = float(x["visibility_probability"])
                    mag = x["apparent_magnitude"]
                    mag_val = float(mag) if mag is not None else 0.0
                    return (prob, -mag_val)

                star_data.sort(key=sort_key, reverse=True)

                # Emit results
                self.stars_ready.emit(self.constellation_data, star_data)
        except Exception as e:
            logger.error(f"Error calculating star visibility: {e}", exc_info=True)
            # Emit empty star data on error
            self.stars_ready.emit(self.constellation_data, [])


class ConstellationInfoDialog(QDialog):
    """Dialog to display detailed information about a constellation and its stars."""

    _star_visibility_thread: StarVisibilityWorkerThread | None
    _map_generation_thread: MapGenerationWorkerThread | None
    _map_image_data: bytes | None
    _constellation_data: dict[str, Any] | None
    _boundaries: dict[str, float] | None

    def _safe_stop_thread(self, thread: QThread | None) -> None:
        """Best-effort stop/cleanup for QThreads, resilient to already-deleted C++ objects."""
        if thread is None:
            return
        try:
            if not isValid(thread):
                return
            if thread.isRunning():
                thread.requestInterruption()
                thread.wait(3000)
                if thread.isRunning():
                    thread.terminate()
                    thread.wait(1000)
            # Schedule deletion in the Qt event loop (safe when still valid)
            thread.deleteLater()
        except RuntimeError:
            # Underlying C++ object already deleted.
            return

    def _on_map_thread_finished(self) -> None:
        """Cleanup handler for map generation thread."""
        sender_obj = self.sender()
        if isinstance(sender_obj, QThread):
            if self._map_generation_thread is sender_obj:
                self._map_generation_thread = None
            try:
                if isValid(sender_obj):
                    sender_obj.deleteLater()
            except RuntimeError:
                pass

    def _on_star_thread_finished(self) -> None:
        """Cleanup handler for star visibility thread."""
        sender_obj = self.sender()
        if isinstance(sender_obj, QThread):
            if self._star_visibility_thread is sender_obj:
                self._star_visibility_thread = None
            try:
                if isValid(sender_obj):
                    sender_obj.deleteLater()
            except RuntimeError:
                pass

    def __init__(self, parent: QWidget | None, constellation_name: str) -> None:
        """Initialize the constellation info dialog."""
        super().__init__(parent)
        self.setWindowTitle(f"Constellation Information: {constellation_name}")
        self.setMinimumWidth(1000)
        self.setMinimumHeight(500)
        self.resize(1000, 700)  # Wider to accommodate constellation map without horizontal scrollbar

        self.constellation_name = constellation_name
        self.svg_path: Path | None = None  # Store SVG path for double-click viewing
        self._star_visibility_thread = None
        self._map_generation_thread = None
        self._map_image_data = None
        self._constellation_data = None
        self._boundaries = None

        # Create layout
        layout = QVBoxLayout(self)

        # Create scrollable text area with rich HTML formatting
        # Use QTextBrowser for better link support
        self.info_text = DoubleClickableTextBrowser()
        self.info_text.setOpenExternalLinks(False)  # Handle links ourselves
        # Handle double-clicks to enlarge SVG
        self.info_text.set_double_click_handler(self._on_text_double_click)
        # Handle link clicks for star info buttons
        self.info_text.set_link_click_handler(self._on_link_clicked)
        layout.addWidget(self.info_text)

        # Add button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        # Load constellation information
        self._load_constellation_info()

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

    def _format_altitude_user_friendly(self, altitude_deg: float) -> str:
        """Format altitude with user-friendly description."""
        from celestron_nexstar.api.telescope.compass import format_altitude_description

        alt_desc = format_altitude_description(altitude_deg)

        # Add helpful explanation for common angles
        if altitude_deg < 0:
            return f"{altitude_deg:.0f}° (below horizon)"
        elif altitude_deg < 10:
            return f"{altitude_deg:.0f}° ({alt_desc} - about one fist at arm's length)"
        elif altitude_deg < 20:
            return f"{altitude_deg:.0f}° ({alt_desc} - about two fists)"
        elif altitude_deg < 40:
            return f"{altitude_deg:.0f}° ({alt_desc} - about four fists)"
        elif altitude_deg < 50:
            return f"{altitude_deg:.0f}° ({alt_desc} - halfway up)"
        else:
            return f"{altitude_deg:.0f}° ({alt_desc})"

    def _explain_magnitude(self, magnitude: float) -> str:
        """Provide brief explanation of magnitude value."""
        if magnitude < 1:
            return "very bright"
        elif magnitude < 3:
            return "bright"
        elif magnitude < 5:
            return "visible to naked eye"
        elif magnitude < 6:
            return "visible under dark skies"
        else:
            return "binoculars needed"

    def _get_theme_colors(self) -> dict[str, str]:
        """Get theme-aware colors."""
        is_dark = self._is_dark_theme()
        return {
            "text": "#ffffff" if is_dark else "#000000",
            "text_dim": "#9e9e9e" if is_dark else "#666666",
            "header": "#ffc107" if is_dark else "#f57c00",
            "cyan": "#00bcd4" if is_dark else "#00838f",
            "green": "#4caf50" if is_dark else "#2e7d32",
            "red": "#f44336" if is_dark else "#c62828",
            "yellow": "#ffc107" if is_dark else "#f57c00",
            "error": "#f44336" if is_dark else "#c62828",
        }

    def _load_constellation_info(self) -> None:
        """Load constellation information and start background thread for star visibility."""
        colors = self._get_theme_colors()
        try:
            from sqlalchemy import select

            from celestron_nexstar.api.astronomy.constellations import get_prominent_constellations_sync
            from celestron_nexstar.api.database.database import get_database
            from celestron_nexstar.api.database.models import ConstellationModel

            db = get_database()
            with db.get_session() as session:
                # Get constellation model with boundaries
                stmt = select(ConstellationModel).where(ConstellationModel.name == self.constellation_name).limit(1)
                result = session.execute(stmt)
                constellation_model = result.scalar_one_or_none()

                constellation_data: dict[str, Any] = {}
                boundaries: dict[str, Any] | None = None
                if not constellation_model:
                    constellation_data, boundaries = {}, None
                else:
                    # Get constellation info (for display)
                    constellations = get_prominent_constellations_sync(session)
                    constellation = None
                    for const in constellations:
                        if const.name == self.constellation_name:
                            constellation = const
                            break

                    if not constellation:
                        constellation_data, boundaries = {}, None
                    else:
                        # Get constellation boundaries for map generation
                        boundaries = {
                            "ra_min_hours": constellation_model.ra_min_hours,
                            "ra_max_hours": constellation_model.ra_max_hours,
                            "dec_min_degrees": constellation_model.dec_min_degrees,
                            "dec_max_degrees": constellation_model.dec_max_degrees,
                            # Provide center and IAU id for projection centering and filtering.
                            "ra_degrees": float(constellation.ra_hours) * 15.0,
                            "dec_degrees": float(constellation.dec_degrees),
                            "iau_id": str(constellation.abbreviation).strip().lower(),
                            "abbreviation": str(constellation.abbreviation).strip(),
                            "constellation_name": str(constellation.name),
                        }

                        constellation_data = {
                            "name": constellation.name,
                            "abbreviation": constellation.abbreviation,
                            "ra_hours": constellation.ra_hours,
                            "dec_degrees": constellation.dec_degrees,
                            "area_sq_deg": constellation.area_sq_deg,
                            "brightest_star": constellation.brightest_star,
                            "magnitude": constellation.magnitude,
                            "season": constellation.season,
                            "hemisphere": constellation.hemisphere,
                            "description": constellation.description,
                        }

            if not constellation_data or not boundaries:
                self.info_text.setHtml(
                    f"<p style='color: {colors['error']};'><b>Error:</b> Constellation '{self.constellation_name}' not found</p>"
                )
                return

            # Store data for map generation
            self._constellation_data = constellation_data
            self._boundaries = boundaries

            # Show initial HTML with loading message for stars and map
            self._build_html_content(constellation_data, boundaries, None, is_loading=True, map_data=None)

            # Clean up any existing map generation thread
            if self._map_generation_thread is not None:
                self._safe_stop_thread(self._map_generation_thread)
                self._map_generation_thread = None

            # Start background thread to generate map
            if boundaries:
                map_thread = MapGenerationWorkerThread(boundaries, self._is_dark_theme())
                self._map_generation_thread = map_thread
                map_thread.map_ready.connect(self._on_map_ready, Qt.ConnectionType.QueuedConnection)
                map_thread.finished.connect(self._on_map_thread_finished)
                map_thread.start()

            # Clean up any existing star visibility thread
            if self._star_visibility_thread is not None:
                self._safe_stop_thread(self._star_visibility_thread)
                self._star_visibility_thread = None

            # Start background thread to calculate star visibility
            self._star_visibility_thread = StarVisibilityWorkerThread(
                self.constellation_name, constellation_data, boundaries
            )
            self._star_visibility_thread.stars_ready.connect(self._on_stars_ready, Qt.ConnectionType.QueuedConnection)
            self._star_visibility_thread.finished.connect(self._on_star_thread_finished)
            self._star_visibility_thread.start()

        except Exception as e:
            logger.error(f"Error loading constellation info: {e}", exc_info=True)
            self.info_text.setHtml(
                f"<p style='color: {colors['error']};'><b>Error:</b> Failed to load constellation information: {e}</p>"
            )

    def _on_map_ready(self, map_data: bytes) -> None:
        """Handle map generation ready from background thread."""
        try:
            self._map_image_data = map_data if map_data else None
            # Update HTML with map if we have constellation data
            if self._constellation_data and self._boundaries:
                # Get current star data if available (might be None if stars not ready yet)
                # We'll rebuild the HTML with the map
                # Check if we have star data by looking at the current content or storing it
                # For now, just rebuild with whatever star data we might have
                # The stars will update separately when they're ready
                self._build_html_content(
                    self._constellation_data,
                    self._boundaries,
                    None,  # Star data will be updated separately
                    is_loading=False,
                    map_data=self._map_image_data,
                )
        except Exception as e:
            logger.error(f"Error handling map data: {e}", exc_info=True)

    def _on_stars_ready(self, constellation_data: dict[str, Any], star_data: list[dict[str, Any]]) -> None:
        """Handle star visibility data ready from background thread."""
        try:
            # Build and display complete HTML with star data and map (if available)
            self._build_html_content(
                constellation_data,
                self._boundaries,
                star_data,
                is_loading=False,
                map_data=self._map_image_data,
            )
        except Exception as e:
            logger.error(f"Error handling star visibility data: {e}", exc_info=True)
            colors = self._get_theme_colors()
            self.info_text.setHtml(
                f"<p style='color: {colors['error']};'><b>Error:</b> Failed to load star visibility data: {e}</p>"
            )

    def _build_html_content(
        self,
        constellation_data: dict[str, Any],
        boundaries: dict[str, float] | None,
        star_data: list[dict[str, Any]] | None,
        is_loading: bool = False,
        map_data: bytes | None = None,
    ) -> None:
        """Build HTML content for constellation info dialog."""
        colors = self._get_theme_colors()

        # Build HTML content
        html_parts = []

        # Constellation name (bold cyan)
        name_html = f"<p style='font-size: 18px; font-weight: bold; color: {colors['cyan']}; margin-bottom: 10px;'>{constellation_data['name']}"
        if constellation_data.get("abbreviation"):
            name_html += f" <span style='color: {colors['cyan']}; font-weight: normal;'>({constellation_data['abbreviation']})</span>"
        name_html += "</p>"
        html_parts.append(name_html)

        # Generate constellation map using starplot MapPlot
        # Map is generated asynchronously in a background thread
        if boundaries:
            if map_data:
                # Map is ready - display it
                try:
                    import base64

                    img_base64 = base64.b64encode(map_data).decode("utf-8")
                    html_parts.append(
                        f"<div style='margin: 15px 0; text-align: center; padding: 5px; background-color: transparent; display: inline-block;'>"
                        f"<img src='data:image/png;base64,{img_base64}' "
                        f"style='max-width: 900px; max-height: 600px; width: auto; height: auto; display: block;' "
                        f"alt='{constellation_data['name']} constellation map' />"
                        f"<p style='margin-top: 5px; font-size: 0.9em; color: {colors['text_dim']};'>Constellation map generated with starplot</p>"
                        f"</div>"
                    )
                except Exception as e:
                    logger.debug(f"Could not display constellation map: {e}")
            elif is_loading:
                # Map is still loading - show placeholder
                html_parts.append(
                    f"<div style='margin: 15px 0; text-align: center; padding: 15px; background-color: transparent;'>"
                    f"<p style='color: {colors['text_dim']};'>⏳ Generating constellation map...</p>"
                    f"</div>"
                )

            # Coordinates section
            from celestron_nexstar.api.core.utils import format_dec, format_ra

            html_parts.append(
                f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>Coordinates:</p>"
            )
            ra_str = format_ra(constellation_data["ra_hours"])
            dec_str = format_dec(constellation_data["dec_degrees"])
            html_parts.append(
                f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>"
                f"<span style='color: {colors['green']};'>RA:</span> {ra_str}<br>"
                f"<span style='color: {colors['green']};'>Dec:</span> {dec_str}"
                f"</p>"
            )

            # Properties section
            html_parts.append(
                f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>Properties:</p>"
            )
            if constellation_data.get("area_sq_deg"):
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>Area: {constellation_data['area_sq_deg']:.1f} square degrees</p>"
                )
            if constellation_data.get("brightest_star"):
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>Brightest Star: {constellation_data['brightest_star']}</p>"
                )
            if constellation_data.get("magnitude"):
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>Brightest Star Magnitude: {constellation_data['magnitude']:.2f}</p>"
                )
            if constellation_data.get("season"):
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>Best Season: {constellation_data['season']}</p>"
                )
            if constellation_data.get("hemisphere"):
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>Hemisphere: {constellation_data['hemisphere']}</p>"
                )

            # Description
            if constellation_data.get("description"):
                html_parts.append(
                    f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>Description:</p>"
                )
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>{constellation_data['description']}</p>"
                )

            # Stars section
            if is_loading or star_data is None:
                # Show loading message
                html_parts.append(
                    f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>Stars in {constellation_data['name']}:</p>"
                )
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px; color: {colors['text_dim']};'>"
                    f"⏳ Calculating visible stars...</p>"
                )
            else:
                html_parts.append(
                    f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>Stars in {constellation_data['name']} ({len(star_data)} visible):</p>"
                )

                if star_data:
                    # Create table
                    html_parts.append(
                        "<table style='border-collapse: collapse; width: 100%; margin-left: 20px; margin-top: 10px;'>"
                    )
                    # Use theme-aware colors for table header background and borders
                    header_bg = "#fff4d6" if not self._is_dark_theme() else "#4a3d1a"
                    border_color = colors["text_dim"]

                    html_parts.append(
                        f"<tr style='background-color: {header_bg};'>"
                        "<th style='padding: 8px; text-align: left; border-bottom: 2px solid #ffc107;'>Name</th>"
                        "<th style='padding: 8px; text-align: center; border-bottom: 2px solid #ffc107;'>Info</th>"
                        "<th style='padding: 8px; text-align: right; border-bottom: 2px solid #ffc107;'>Mag</th>"
                        "<th style='padding: 8px; text-align: right; border-bottom: 2px solid #ffc107;'>Alt</th>"
                        "<th style='padding: 8px; text-align: right; border-bottom: 2px solid #ffc107;'>Chance</th>"
                        "</tr>"
                    )

                    for star_info in star_data[:50]:  # Limit to top 50 stars
                        obj = star_info["obj"]
                        display_name = obj.common_name or obj.name
                        mag_text = f"{star_info['apparent_magnitude']:.2f}" if star_info["apparent_magnitude"] else "-"
                        # Add user-friendly altitude description
                        alt_deg = star_info["altitude"]
                        alt_text = f"{alt_deg:.0f}°"
                        prob_text = f"{star_info['visibility_probability']:.0%}"

                        # Color code by visibility probability
                        if star_info["visibility_probability"] >= 0.8:
                            prob_color = colors["green"]
                        elif star_info["visibility_probability"] >= 0.5:
                            prob_color = colors["yellow"]
                        else:
                            prob_color = colors["text_dim"]

                        # Create info button link
                        star_name_encoded = display_name.replace('"', "&quot;").replace("'", "&#39;")
                        info_link = f'<a href="starinfo://{star_name_encoded}" style="text-decoration: none; color: {colors["cyan"]}; font-weight: bold;" title="Show star information">\u2139\ufe0f</a>'

                        # Add magnitude explanation
                        mag_explanation = ""
                        if star_info["apparent_magnitude"]:
                            mag_explanation = f" <span style='color: {colors['text_dim']}; font-size: 0.85em;'>({self._explain_magnitude(star_info['apparent_magnitude'])})</span>"

                        html_parts.append(
                            f"<tr>"
                            f"<td style='padding: 5px; border-bottom: 1px solid {border_color};'>{display_name}</td>"
                            f"<td style='padding: 5px; text-align: center; border-bottom: 1px solid {border_color};'>{info_link}</td>"
                            f"<td style='padding: 5px; text-align: right; border-bottom: 1px solid {border_color};'>{mag_text}{mag_explanation}</td>"
                            f"<td style='padding: 5px; text-align: right; border-bottom: 1px solid {border_color}; font-size: 0.9em;'>{alt_text}</td>"
                            f"<td style='padding: 5px; text-align: right; border-bottom: 1px solid {border_color};'>"
                            f"<span style='color: {prob_color};'>{prob_text}</span></td>"
                            f"</tr>"
                        )

                    html_parts.append("</table>")
                    # Add helpful tips
                    html_parts.append(
                        f"<p style='margin-top: 15px; margin-left: 20px; color: {colors['text_dim']}; font-size: 0.9em;'>"
                        f"💡 <b>Tips:</b> Altitude is shown with helpful descriptions (e.g., 'one fist at arm's length' = 10°). "
                        f"Magnitude indicates brightness - lower numbers are brighter. "
                        f"Chance shows visibility probability based on current conditions.</p>"
                    )
                else:
                    html_parts.append(
                        f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px; color: {colors['text_dim']};'>No visible stars found in this constellation.</p>"
                    )

            # Set HTML content
            self.info_text.setHtml("".join(html_parts))

    def _on_text_double_click(self, event: Any) -> None:
        """Handle double-click events - open SVG if available."""
        # Check if we have an SVG
        if self.svg_path is not None and self.svg_path.exists():
            try:
                # Get cursor position at click location
                if hasattr(event, "position"):
                    pos = event.position().toPoint()
                elif hasattr(event, "pos"):
                    pos = event.pos()
                else:
                    pos = event.globalPos()

                cursor = self.info_text.cursorForPosition(pos)
                # If cursor is in the first part of the document (where SVG is), show enlarged view
                if cursor.position() < 5000:  # Rough check - SVG is near the top
                    self._show_enlarged_svg()
                    return
            except Exception:
                # If we can't determine position, just show the enlarged view on any double-click
                # when SVG is available (user can double-click anywhere near the image)
                self._show_enlarged_svg()
                return

        # Call original double-click handler for normal text selection

        QTextEdit.mouseDoubleClickEvent(self.info_text, event)

    def _show_enlarged_svg(self) -> None:
        """Show the constellation SVG in a larger dialog."""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QScrollArea, QSizePolicy, QVBoxLayout

        # Try to import QSvgWidget (it's in QtSvgWidgets in PySide6)
        use_svg_widget = False
        q_svg_widget_class = None
        try:
            from PySide6.QtSvgWidgets import QSvgWidget

            q_svg_widget_class = QSvgWidget
            use_svg_widget = True
        except ImportError:
            pass

        # Get SVG dimensions to size the dialog appropriately
        svg_width = 1000
        svg_height = 1000
        aspect_ratio = 1.0

        if use_svg_widget and q_svg_widget_class is not None:
            try:
                temp_widget = q_svg_widget_class(str(self.svg_path))
                svg_renderer = temp_widget.renderer()
                if svg_renderer and svg_renderer.isValid():
                    svg_size = svg_renderer.defaultSize()
                    if svg_size.isValid() and svg_size.width() > 0 and svg_size.height() > 0:
                        svg_width = svg_size.width()
                        svg_height = svg_size.height()
                        aspect_ratio = svg_height / svg_width
            except Exception:
                pass

        # Calculate dialog size: SVG size + minimal padding for margins and button
        # Add ~80px for margins (10px * 2 on each side) + ~60px for button area
        padding_width = 80
        padding_height = 100  # Extra for button
        dialog_width = min(svg_width + padding_width, 1400)  # Cap at reasonable max
        dialog_height = min(svg_height + padding_height, 1000)  # Cap at reasonable max

        # Create dialog for enlarged view
        dialog = QDialog(self)
        dialog.setWindowTitle(f"{self.constellation_name} - Constellation Diagram")
        dialog.setMinimumWidth(600)
        dialog.setMinimumHeight(400)
        dialog.resize(int(dialog_width), int(dialog_height))

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(5, 5, 5, 5)  # Minimal margins
        layout.setSpacing(5)  # Minimal spacing

        # Create scroll area for the SVG
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Try to use QSvgWidget for better SVG rendering
        svg_widget_success = False
        if use_svg_widget and q_svg_widget_class is not None:
            try:
                # Use a custom widget that maintains aspect ratio
                from PySide6.QtCore import QSize

                # Create a type alias to work around mypy's limitation with conditional imports
                _SvgWidgetBase = q_svg_widget_class  # type: ignore[assignment,misc]  # noqa: N806

                class AspectRatioSvgWidget(_SvgWidgetBase):  # type: ignore[valid-type]
                    """QSvgWidget that maintains aspect ratio when resizing."""

                    def __init__(self, path: str, aspect_ratio: float) -> None:
                        super().__init__(path)
                        self.aspect_ratio = aspect_ratio

                    def sizeHint(self) -> QSize:  # noqa: N802
                        """Return a size hint that maintains aspect ratio."""
                        width = 1000  # Preferred width
                        height = int(width * self.aspect_ratio)
                        return QSize(width, height)

                    def resizeEvent(self, event: Any) -> None:  # noqa: N802
                        """Maintain aspect ratio when resizing."""
                        size = event.size()
                        width = size.width()
                        height = int(width * self.aspect_ratio)

                        # If calculated height exceeds available height, use height instead
                        if height > size.height():
                            height = size.height()
                            width = int(height / self.aspect_ratio)

                        self.resize(width, height)
                        super().resizeEvent(event)

                aspect_svg_widget = AspectRatioSvgWidget(str(self.svg_path), aspect_ratio)
                aspect_svg_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

                # Create a container widget with white background
                container = QLabel()
                container.setStyleSheet("background-color: #ffffff;")
                container_layout = QVBoxLayout(container)
                container_layout.setContentsMargins(10, 10, 10, 10)  # Reduced margins
                container_layout.setSpacing(0)
                container_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                container_layout.addWidget(aspect_svg_widget)

                scroll_area.setWidget(container)
                layout.addWidget(scroll_area)
                svg_widget_success = True

            except Exception as e:
                # Fallback to QTextEdit if QSvgWidget fails
                logger.warning(f"Could not use QSvgWidget, falling back to QTextEdit: {e}")

        # Fallback to QTextEdit if QSvgWidget is not available or failed
        if not svg_widget_success:
            from PySide6.QtWidgets import QTextEdit

            svg_display = QTextEdit()
            svg_display.setReadOnly(True)
            svg_display.setAcceptRichText(True)
            svg_display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

            try:
                if self.svg_path is None:
                    return
                svg_content = self.svg_path.read_text(encoding="utf-8")
                import re
                import urllib.parse

                # Add white background to SVG if needed
                if not re.search(
                    r'<rect[^>]*fill\s*=\s*["\'](?:white|#fff|#ffffff|#f5f5f5|#e0e0e0)', svg_content, re.IGNORECASE
                ):
                    svg_match = re.search(r"(<svg[^>]*>)", svg_content, re.IGNORECASE)
                    if svg_match:
                        viewbox_match = re.search(r'viewBox\s*=\s*["\']([^"\']+)["\']', svg_content, re.IGNORECASE)
                        width_match = re.search(r'width\s*=\s*["\']([^"\']+)["\']', svg_content, re.IGNORECASE)
                        height_match = re.search(r'height\s*=\s*["\']([^"\']+)["\']', svg_content, re.IGNORECASE)

                        x, y, width, height = 0, 0, 1000, 1000

                        if viewbox_match:
                            viewbox_parts = viewbox_match.group(1).split()
                            if len(viewbox_parts) >= 4:
                                x, y, width, height = [float(v) for v in viewbox_parts[:4]]  # type: ignore[assignment]
                        elif width_match and height_match:
                            width = float(re.sub(r"[^\d.]", "", width_match.group(1)))  # type: ignore[assignment]
                            height = float(re.sub(r"[^\d.]", "", height_match.group(1)))  # type: ignore[assignment]

                        bg_rect = (
                            f'<rect x="{x}" y="{y}" width="{width}" height="{height}" fill="#ffffff" stroke="none"/>'
                        )
                        svg_content = svg_content.replace(svg_match.group(1), svg_match.group(1) + bg_rect, 1)

                svg_encoded = urllib.parse.quote(svg_content)

                # Use viewport-based sizing
                html = f"""
                <html>
                <head>
                    <style>
                        body {{
                            margin: 0;
                            padding: 20px;
                            background-color: #ffffff;
                            text-align: center;
                        }}
                        img {{
                            width: 95vw;
                            height: auto;
                            max-width: 95vw;
                            max-height: 90vh;
                        }}
                    </style>
                </head>
                <body>
                    <img src='data:image/svg+xml;charset=utf-8,{svg_encoded}'
                         alt='{self.constellation_name} constellation diagram' />
                </body>
                </html>
                """
                svg_display.setHtml(html)
            except Exception as e2:
                logger.error(f"Error loading enlarged SVG: {e2}")
                svg_display.setHtml(f"<p>Error loading image: {e2}</p>")

            layout.addWidget(svg_display)

        # Add close button
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        # Show dialog
        dialog.exec()

    def _on_link_clicked(self, url: str) -> None:
        """Handle link clicks - open star info dialog."""
        if url.startswith("starinfo://"):
            star_name = url.replace("starinfo://", "")
            # Decode HTML entities
            star_name = star_name.replace("&quot;", '"').replace("&#39;", "'")
            try:
                # Prevent QTextBrowser from clearing content by reloading immediately
                # Use QTimer to ensure it happens after Qt processes the click event
                from PySide6.QtCore import QTimer

                def prevent_clear() -> None:
                    """Reload content to prevent clearing and ensure clean HTML."""
                    self._load_constellation_info()

                # Reload after a short delay to ensure Qt has processed the click
                # This ensures we always have fresh, clean HTML without rgba colors
                QTimer.singleShot(10, prevent_clear)

                from celestron_nexstar.gui.dialogs.object_info_dialog import ObjectInfoDialog

                dialog = ObjectInfoDialog(self, star_name)
                dialog.exec()

                # Reload content after dialog closes to ensure it's fresh and clean
                # This prevents any issues with rgba colors or other HTML parsing problems
                self._load_constellation_info()
            except Exception as e:
                logger.error(f"Error opening star info dialog: {e}", exc_info=True)
                # Reload HTML content on error
                self._load_constellation_info()
