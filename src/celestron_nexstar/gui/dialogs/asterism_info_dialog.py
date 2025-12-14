"""
Dialog to display detailed information about an asterism.
"""

import logging
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


class LinkClickableTextBrowser(QTextBrowser):
    """QTextBrowser that supports link click handling."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the text browser."""
        super().__init__(parent)
        self._link_click_handler: Any = None
        self._saved_source: QUrl | None = None
        # Connect to anchorClicked signal for link handling
        self.anchorClicked.connect(self._on_anchor_clicked)

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
        if url_str.startswith("starinfo://") and self._link_click_handler:
            # Handle star info links ourselves - don't let QTextBrowser navigate
            self._link_click_handler(url_str)
            # Don't call setSource for starinfo links to avoid warnings
        else:
            # For other links (like http/https), use default behavior (open in browser)
            # Only if it's a valid external URL
            if url_str.startswith(("http://", "https://")):
                from PySide6.QtGui import QDesktopServices

                QDesktopServices.openUrl(url)


class AsterismInfoDialog(QDialog):
    """Dialog to display detailed information about an asterism."""

    def __init__(self, parent: QWidget | None, asterism_name: str) -> None:
        """Initialize the asterism info dialog."""
        super().__init__(parent)
        self.setWindowTitle(f"Asterism Information: {asterism_name}")
        self.setMinimumWidth(1000)
        self.setMinimumHeight(500)
        self.resize(1000, 700)  # Wider to accommodate asterism map without horizontal scrollbar

        self.asterism_name = asterism_name

        # Create layout
        layout = QVBoxLayout(self)

        # Create scrollable text area with rich HTML formatting
        # Use QTextBrowser for better link support
        self.info_text = LinkClickableTextBrowser()
        self.info_text.setOpenExternalLinks(False)  # Handle links ourselves
        # Handle link clicks for star info buttons
        self.info_text.set_link_click_handler(self._on_link_clicked)
        layout.addWidget(self.info_text)

        # Add button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        # Load asterism information
        self._load_asterism_info()

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
            "red": "#f44336" if is_dark else "#c62828",
            "yellow": "#ffc107" if is_dark else "#f57c00",
            "error": "#f44336" if is_dark else "#c62828",
        }

    def _load_asterism_info(self) -> None:
        """Load asterism information."""
        colors = self._get_theme_colors()
        try:
            from celestron_nexstar.api.astronomy.constellations import get_famous_asterisms
            from celestron_nexstar.api.core.utils import format_dec, format_ra
            from celestron_nexstar.api.database.models import get_db_session

            with get_db_session() as session:
                asterisms = get_famous_asterisms(session)
                asterism = None
                for asterism_obj in asterisms:
                    if asterism_obj.name == self.asterism_name:
                        asterism = asterism_obj
                        break

            if not asterism:
                self.info_text.setHtml(
                    f"<p style='color: {colors['error']};'><b>Error:</b> Asterism '{self.asterism_name}' not found</p>"
                )
                return

            # Build HTML content
            html_parts = []

            # Asterism name (bold cyan)
            name_html = f"<p style='font-size: 18px; font-weight: bold; color: {colors['cyan']}; margin-bottom: 10px;'>{asterism.name}"
            if asterism.alt_names:
                alt_names_str = ", ".join(asterism.alt_names)
                name_html += f" <span style='color: {colors['text_dim']}; font-weight: normal; font-size: 14px;'>({alt_names_str})</span>"
            name_html += "</p>"
            html_parts.append(name_html)

            # Generate asterism map using starplot MapPlot
            # Based on example: https://starplot.dev/examples/map-orion/
            try:
                import base64
                import io

                # Generate map in background thread to avoid blocking UI
                def _generate_map() -> bytes | None:
                    try:
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
                        is_dark = self._is_dark_theme()
                        if is_dark:
                            plot_style = PlotStyle().extend(extensions.BLUE_DARK, extensions.MAP)
                        else:
                            plot_style = PlotStyle().extend(extensions.BLUE_LIGHT, extensions.MAP)

                        # Calculate RA/Dec range from actual member star positions
                        # Query database to get positions of all member stars
                        ra_values: list[float] = []
                        dec_values: list[float] = []

                        if asterism.member_stars:

                            def _get_star_positions() -> tuple[list[float], list[float]]:
                                """Get RA/Dec positions of asterism stars from database.

                                Prefer deriving membership from the asterism's own line geometry (more reliable than
                                the seed member list). Fall back to resolving the member list by name if geometry
                                isn't available.
                                """
                                ra_positions: list[float] = []
                                dec_positions: list[float] = []

                                from geoalchemy2 import functions as geofunc
                                from sqlalchemy import func, select

                                from celestron_nexstar.api.core.enums import CelestialObjectType
                                from celestron_nexstar.api.database.database import get_database
                                from celestron_nexstar.api.database.models import AsterismModel, StarModel

                                db = get_database()
                                with db._get_session() as session:
                                    asterism_model = session.scalar(
                                        select(AsterismModel).where(AsterismModel.name == asterism.name).limit(1)
                                    )

                                    # Primary path: derive nearby stars from asterism geometry.
                                    if asterism_model is not None and asterism_model.geometry is not None:
                                        # Distance threshold (degrees) and brightness cutoff for "pattern stars".
                                        max_distance_deg = 1.5
                                        mag_limit = 6.0
                                        limit = 80

                                        star_ids = list(
                                            session.execute(
                                                select(StarModel.id)
                                                .join(AsterismModel, AsterismModel.id == asterism_model.id)
                                                .where(
                                                    AsterismModel.geometry.isnot(None),
                                                    StarModel.geometry.isnot(None),
                                                    geofunc.ST_Distance(AsterismModel.geometry, StarModel.geometry)
                                                    <= max_distance_deg,
                                                    (StarModel.magnitude.is_(None))
                                                    | (StarModel.magnitude <= mag_limit),
                                                )
                                                .order_by(func.coalesce(StarModel.magnitude, 99.0))
                                                .limit(limit)
                                            )
                                            .scalars()
                                            .all()
                                        )
                                        if star_ids:
                                            star_models = (
                                                session.execute(select(StarModel).where(StarModel.id.in_(star_ids)))
                                                .scalars()
                                                .all()
                                            )
                                            for sm in star_models:
                                                ra_hours = sm.ra_hours
                                                if ra_hours < 0:
                                                    ra_hours += 24.0
                                                elif ra_hours >= 24:
                                                    ra_hours -= 24.0
                                                ra_positions.append(float(ra_hours))
                                                dec_positions.append(float(sm.dec_degrees))

                                # Fallback: resolve seed member list by name if geometry path didn't find enough.
                                if len(ra_positions) < 2 and asterism.member_stars:
                                    for star_name in asterism.member_stars:
                                        resolved = db.get_by_name(star_name.strip())
                                        if resolved is None or resolved.object_type != CelestialObjectType.STAR:
                                            continue

                                        ra_hours = float(resolved.ra_hours)
                                        if ra_hours < 0:
                                            ra_hours += 24.0
                                        elif ra_hours >= 24:
                                            ra_hours -= 24.0
                                        ra_positions.append(ra_hours)
                                        dec_positions.append(float(resolved.dec_degrees))

                                return ra_positions, dec_positions

                            # Get star positions
                            star_ra_list, star_dec_list = _get_star_positions()
                            ra_values.extend(star_ra_list)
                            dec_values.extend(star_dec_list)

                        # If we found star positions, use them; otherwise fall back to center + size
                        if ra_values and dec_values:
                            # Calculate min/max from actual star positions
                            ra_min_hours = min(ra_values)
                            ra_max_hours = max(ra_values)
                            ra_span = ra_max_hours - ra_min_hours

                            # Check if stars wrap around 0/24h boundary
                            # If span is > 12 hours, the stars likely wrap around
                            wraps_around = ra_span > 12.0

                            if wraps_around:
                                # Stars wrap around - calculate center and use reasonable range
                                # Find the gap (the part of the sky NOT covered by stars)
                                # The gap is from ra_max to ra_min (wrapping)
                                gap_start = ra_max_hours
                                gap_end = ra_min_hours + 24.0
                                gap_size = gap_end - gap_start

                                # Use the center of the star region (opposite of gap center)
                                gap_center = (gap_start + gap_end) / 2
                                if gap_center >= 24:
                                    gap_center = gap_center - 24.0

                                # Star region center is opposite the gap
                                star_center = (gap_center + 12.0) % 24.0

                                # Use a range that covers all stars (24 - gap_size) plus padding
                                star_span = 24.0 - gap_size
                                # A bit more padding helps prevent edge clipping (notably for circumpolar asterisms)
                                padding_ra = 1.0  # hours
                                range_size = star_span + (padding_ra * 2)
                                # For circumpolar patterns (e.g., Little Dipper), RA can span many hours.
                                # Don't over-cap or we risk clipping.
                                range_size = min(range_size, 16.0)  # Cap at 16 hours max

                                ra_min = (star_center - range_size / 2) % 24.0
                                ra_max = (star_center + range_size / 2) % 24.0

                                # If still wraps, use simpler approach
                                if ra_min > ra_max:
                                    # Use min/max with padding, but handle wrap
                                    ra_min = max(0, ra_min_hours - padding_ra)
                                    ra_max = min(24, ra_max_hours + padding_ra)
                                    if ra_min >= ra_max:
                                        # Final fallback
                                        ra_min = 0
                                        ra_max = 4
                            else:
                                # Normal case - stars don't wrap
                                ra_min_hours = min(ra_values)
                                ra_max_hours = max(ra_values)

                                # Add padding around the stars
                                padding_ra = 1.0  # hours

                                ra_min = ra_min_hours - padding_ra
                                ra_max = ra_max_hours + padding_ra

                                # Handle RA boundaries - clamp to valid range
                                # But if clamping would create a huge range (> 6 hours), use center-based approach instead
                                if ra_min < 0:
                                    ra_min = 0
                                if ra_max > 24:
                                    ra_max = 24

                                # Check if the range is reasonable (not too large)
                                ra_range = ra_max - ra_min
                                if ra_range > 6.0:
                                    # Range is too large, use center-based approach with actual span
                                    ra_center = (ra_min_hours + ra_max_hours) / 2
                                    actual_span = ra_max_hours - ra_min_hours
                                    # Use actual span plus padding, but cap at reasonable size
                                    range_size = min(actual_span + (padding_ra * 2), 6.0)
                                    ra_min = max(0, ra_center - range_size / 2)
                                    ra_max = min(24, ra_center + range_size / 2)

                            # Calculate Dec range
                            dec_min = min(dec_values)
                            dec_max = max(dec_values)

                            # Add padding around the stars
                            padding_dec = 2.0  # degrees
                            dec_min = dec_min - padding_dec
                            dec_max = dec_max + padding_dec

                            # Clamp declination to valid range
                            dec_min = max(-90, dec_min)
                            dec_max = min(90, dec_max)

                            # Final validation: ensure ra_min < ra_max (if not wrapping)
                            if not wraps_around and ra_min >= ra_max:
                                # Fallback: use default range around center
                                ra_center = (ra_min_hours + ra_max_hours) / 2
                                ra_min = max(0, ra_center - 1)
                                ra_max = min(24, ra_center + 1)

                            # Clamp declination to valid range
                            dec_min = max(-90, dec_min)
                            dec_max = min(90, dec_max)
                        else:
                            # Fallback: use asterism center and size if no star positions found
                            size_deg = asterism.size_degrees if asterism.size_degrees else 10.0
                            padding_deg = 2.0  # degrees
                            total_size = size_deg + (padding_deg * 2)

                            # Calculate RA range (convert size to hours: degrees / 15)
                            ra_center = asterism.ra_hours
                            ra_size_hours = total_size / 15.0
                            ra_min = ra_center - (ra_size_hours / 2)
                            ra_max = ra_center + (ra_size_hours / 2)

                            # Handle RA wrap-around
                            if ra_min < 0:
                                ra_min = 0
                            if ra_max > 24:
                                ra_max = 24

                            # Ensure ra_min < ra_max
                            if ra_min >= ra_max:
                                ra_min = max(0, ra_center - 1)
                                ra_max = min(24, ra_center + 1)

                            # Calculate Dec range
                            dec_center = asterism.dec_degrees
                            dec_min = dec_center - (total_size / 2)
                            dec_max = dec_center + (total_size / 2)

                            # Clamp declination to valid range
                            dec_min = max(-90, dec_min)
                            dec_max = min(90, dec_max)

                        # Final validation: ensure ra_min < ra_max before converting to degrees
                        # This handles edge cases where clamping or wrapping might cause issues
                        if ra_min >= ra_max:
                            # Use a safe default range around the center
                            if ra_values:
                                ra_center = (min(ra_values) + max(ra_values)) / 2
                            else:
                                ra_center = asterism.ra_hours if asterism else 12.0
                            ra_min = max(0, ra_center - 1)
                            ra_max = min(24, ra_center + 1)
                            # If still equal (shouldn't happen, but be safe)
                            if ra_min >= ra_max:
                                ra_min = 0
                                ra_max = 4

                        # Convert RA from hours to degrees for starplot (RA * 15 = degrees)
                        ra_min_deg = ra_min * 15
                        ra_max_deg = ra_max * 15

                        # Normalize RA bounds so Starplot doesn't interpret them as a full-sky span.
                        if ra_max_deg <= ra_min_deg:
                            ra_max_deg += 360.0
                        while ra_min_deg < 0.0:
                            ra_min_deg += 360.0
                            ra_max_deg += 360.0
                        while ra_min_deg >= 360.0:
                            ra_min_deg -= 360.0
                            ra_max_deg -= 360.0
                        max_span_deg = 120.0  # 8h cap to keep asterisms tightly framed
                        span_deg = ra_max_deg - ra_min_deg
                        if span_deg > max_span_deg:
                            center = (ra_min_deg + ra_max_deg) / 2.0
                            ra_min_deg = center - (max_span_deg / 2.0)
                            ra_max_deg = center + (max_span_deg / 2.0
                            )

                        # Use LambertAzEqArea (Starplot examples) so ra_min/ra_max cropping works.
                        center_ra_deg = ((ra_min_deg + ra_max_deg) / 2.0) % 360.0
                        center_dec_deg = float((dec_min + dec_max) / 2.0)
                        if float(dec_max) >= 70.0:
                            center_dec_deg = 90.0
                        elif float(dec_min) <= -70.0:
                            center_dec_deg = -90.0
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
                            resolution=4096,  # Good quality for asterism view
                            autoscale=False,
                            scale=1.5,
                        )

                        # Add constellation features
                        # NOTE: For near-polar views, Starplot often expands longitude to a full 360° internally.
                        # In that case, showing RA labels can make the plot *look* "24h wide" even when the asterism
                        # is properly framed. Hide labels when the underlying plot span is full-sky.
                        try:
                            dec_start = int(max(-90.0, float(dec_min)) // 5 * 5)
                            dec_end = int(min(90.0, (float(dec_max) // 5 * 5) + 5))
                            plot_span = float(getattr(plot, "ra_max", ra_max_deg)) - float(getattr(plot, "ra_min", ra_min_deg))
                            hide_labels = plot_span >= 359.9
                            plot.gridlines(
                                labels=not hide_labels,
                                dec_locations=[d for d in range(dec_start, dec_end + 1, 5)],
                            )
                        except Exception:
                            plot.gridlines()
                        plot.constellations()
                        plot.constellation_borders()

                        try:
                            logger.info(
                                "Asterism map bounds: name=%s requested_ra_min=%.3f requested_ra_max=%.3f requested_span=%.3f "
                                "requested_dec_min=%.3f requested_dec_max=%.3f plot_ra_min=%.3f plot_ra_max=%.3f plot_span=%.3f "
                                "plot_dec_min=%.3f plot_dec_max=%.3f",
                                asterism.name,
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

                        # Add stars (magnitude < 8, labels for magnitude < 5)
                        plot.stars(where=[_.magnitude < 8], bayer_labels=True, where_labels=[_.magnitude < 5])  # type: ignore[arg-type]

                        # Add open clusters
                        plot.open_clusters(
                            where=[_.size < 1, _.magnitude < 9],  # type: ignore[arg-type]
                            where_labels=[False],
                            true_size=False,
                        )
                        plot.open_clusters(
                            where=[_.size > 1, (_.magnitude < 9) | (_.magnitude.isnull())],  # type: ignore[arg-type]
                            where_labels=[False],
                        )

                        # Add nebula
                        plot.nebula(where=[(_.magnitude < 9) | (_.magnitude.isnull())])  # type: ignore[arg-type]

                        # Add constellation labels
                        try:
                            plot.constellation_labels()
                        except RuntimeError as e:
                            if "reentrant" not in str(e).lower() and "font" not in str(e).lower():
                                raise

                        # Add Milky Way and ecliptic
                        # Milky way may fail for small RA/Dec ranges, so wrap in try/except
                        try:
                            plot.milky_way()
                        except (ValueError, RuntimeError) as e:
                            # Milky way may fail for small RA/Dec ranges or edge cases
                            logger.debug(f"Could not render milky way: {e}")
                        plot.ecliptic()

                        # Export to PNG in memory
                        img_buffer = io.BytesIO()
                        # Slightly more padding reduces the chance of clipping at edges.
                        plot.export(img_buffer, format="png", padding=0.5, transparent=True)  # type: ignore[no-untyped-call]
                        img_buffer.seek(0)
                        return img_buffer.read()

                    except Exception as e:
                        logger.error(f"Error generating asterism map: {e}", exc_info=True)
                        return None

                # Generate map in background thread
                from concurrent.futures import ThreadPoolExecutor

                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(_generate_map)
                    map_image_data = future.result(timeout=30)  # 30 second timeout

                if map_image_data:
                    # Convert to base64 for embedding in HTML
                    img_base64 = base64.b64encode(map_image_data).decode("utf-8")
                    html_parts.append(
                        f"<div style='margin: 15px 0; text-align: center; padding: 5px; background-color: transparent; display: inline-block;'>"
                        f"<img src='data:image/png;base64,{img_base64}' "
                        f"style='max-width: 900px; max-height: 600px; width: auto; height: auto; display: block;' "
                        f"alt='{asterism.name} asterism map' />"
                        f"<p style='margin-top: 5px; font-size: 0.9em; color: {colors['text_dim']};'>Asterism map generated with starplot</p>"
                        f"</div>"
                    )
            except Exception as e:
                logger.debug(f"Could not generate asterism map: {e}")
                # Silently fail - map is optional

            # Coordinates section
            html_parts.append(
                f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>Coordinates:</p>"
            )
            ra_str = format_ra(asterism.ra_hours)
            dec_str = format_dec(asterism.dec_degrees)
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
            if asterism.size_degrees:
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>Size: {asterism.size_degrees:.1f}°</p>"
                )
            if asterism.parent_constellation:
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>Parent Constellation: {asterism.parent_constellation}</p>"
                )
            if asterism.season:
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>Best Season: {asterism.season}</p>"
                )
            if asterism.hemisphere:
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>Hemisphere: {asterism.hemisphere}</p>"
                )
            if hasattr(asterism, "shape_description") and asterism.shape_description:
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>Shape: {asterism.shape_description}</p>"
                )

            # Description
            if asterism.description:
                html_parts.append(
                    f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>Description:</p>"
                )
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>{asterism.description}</p>"
                )

            # Guidepost info
            if hasattr(asterism, "guidepost_info") and asterism.guidepost_info:
                html_parts.append(
                    f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>Using as a Guidepost:</p>"
                )
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>{asterism.guidepost_info}</p>"
                )

            # Cultural information
            if hasattr(asterism, "cultural_info") and asterism.cultural_info:
                html_parts.append(
                    f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>Cultural & Mythological Information:</p>"
                )
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>{asterism.cultural_info}</p>"
                )

            # Historical notes
            if hasattr(asterism, "historical_notes") and asterism.historical_notes:
                html_parts.append(
                    f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>Historical Notes:</p>"
                )
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>{asterism.historical_notes}</p>"
                )

            # Component stars
            if asterism.member_stars:
                html_parts.append(
                    f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>Component Stars:</p>"
                )
                # Create a table with info buttons
                html_parts.append(
                    "<table style='border-collapse: collapse; width: 100%; margin-left: 20px; margin-top: 10px;'>"
                )
                # Use theme-aware colors for table header background and borders
                header_bg = "#fff4d6" if not self._is_dark_theme() else "#4a3d1a"
                border_color = colors["text_dim"]

                html_parts.append(
                    f"<tr style='background-color: {header_bg};'>"
                    "<th style='padding: 8px; text-align: left; border-bottom: 2px solid #ffc107;'>Star Name</th>"
                    "<th style='padding: 8px; text-align: center; border-bottom: 2px solid #ffc107;'>Info</th>"
                    "</tr>"
                )

                for star_name in asterism.member_stars:
                    star_name_encoded = star_name.replace('"', "&quot;").replace("'", "&#39;")
                    info_link = f'<a href="starinfo://{star_name_encoded}" style="text-decoration: none; color: {colors["cyan"]}; font-weight: bold;" title="Show star information">\u2139\ufe0f</a>'
                    html_parts.append(
                        f"<tr>"
                        f"<td style='padding: 5px; border-bottom: 1px solid {border_color};'>{star_name}</td>"
                        f"<td style='padding: 5px; text-align: center; border-bottom: 1px solid {border_color};'>{info_link}</td>"
                        f"</tr>"
                    )

                html_parts.append("</table>")

            # Visible stars in this asterism (from DB relationships, filtered by current telescope configuration)
            try:
                from sqlalchemy import select

                from celestron_nexstar.api.core.enums import CelestialObjectType, SkyBrightness
                from celestron_nexstar.api.database.database import get_database
                from celestron_nexstar.api.database.models import AsterismModel
                from celestron_nexstar.api.location.light_pollution import get_light_pollution_data
                from celestron_nexstar.api.location.observer import get_observer_location
                from celestron_nexstar.api.observation.observation_planner import ObservationPlanner
                from celestron_nexstar.api.observation.visibility import assess_visibility

                # Get asterism model row for relationship lookup
                db = get_database()
                with db._get_session() as session:
                    asterism_model = session.scalar(
                        select(AsterismModel).where(AsterismModel.name == asterism.name).limit(1)
                    )

                    visible_star_names: list[str] = []
                    if asterism_model is not None:
                        # Prefer deriving pattern membership from the asterism geometry (nearby stars),
                        # rather than relying on the stored member list which may be incomplete.
                        from celestron_nexstar.api.database.models import StarModel

                        star_models: list[StarModel] = []
                        if asterism_model.geometry is not None:
                            from geoalchemy2 import functions as geofunc
                            from sqlalchemy import func

                            max_distance_deg = 1.5
                            mag_limit = 6.0
                            limit = 200

                            star_ids = list(
                                session.execute(
                                    select(StarModel.id)
                                    .join(AsterismModel, AsterismModel.id == asterism_model.id)
                                    .where(
                                        AsterismModel.geometry.isnot(None),
                                        StarModel.geometry.isnot(None),
                                        geofunc.ST_Distance(AsterismModel.geometry, StarModel.geometry)
                                        <= max_distance_deg,
                                        (StarModel.magnitude.is_(None)) | (StarModel.magnitude <= mag_limit),
                                    )
                                    .order_by(func.coalesce(StarModel.magnitude, 99.0))
                                    .limit(limit)
                                )
                                .scalars()
                                .all()
                            )
                            if star_ids:
                                star_models = list(
                                    session.execute(select(StarModel).where(StarModel.id.in_(star_ids))).scalars().all()
                                )

                        # Determine sky brightness from light pollution if available (used for telescope limiting magnitude)
                        location = get_observer_location()
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
                        try:
                            lp = get_light_pollution_data(session, location.latitude, location.longitude)
                            sky_brightness = bortle_to_sky_brightness.get(lp.bortle_class.value, SkyBrightness.FAIR)
                        except Exception:
                            sky_brightness = SkyBrightness.FAIR

                        planner = ObservationPlanner()
                        conditions = planner.get_tonight_conditions()

                        # Filter derived member stars by actual visibility.
                        if star_models:
                            from celestron_nexstar.api.catalogs.catalogs import CelestialObject

                            for sm in star_models:
                                obj = CelestialObject(
                                    name=sm.common_name or sm.name or "",
                                    common_name=sm.common_name,
                                    ra_hours=sm.ra_hours,
                                    dec_degrees=sm.dec_degrees,
                                    magnitude=sm.magnitude,
                                    object_type=CelestialObjectType.STAR,
                                    catalog=sm.catalog,
                                    description=sm.description,
                                    parent_planet=None,
                                    constellation=sm.constellation_name,
                                    asterism=asterism.name,
                                )

                                vis_info = assess_visibility(
                                    obj,
                                    sky_brightness=sky_brightness,
                                    min_altitude_deg=20.0,
                                    observer_lat=location.latitude,
                                    observer_lon=location.longitude,
                                    dt=conditions.timestamp,
                                )
                                if vis_info.is_visible:
                                    visible_star_names.append(obj.common_name or obj.name)
                        else:
                            # Fallback: use member list if geometry is missing/unavailable.
                            for star_name in asterism.member_stars:
                                resolved_obj = db.get_by_name(star_name.strip())
                                if resolved_obj is None or resolved_obj.object_type != CelestialObjectType.STAR:
                                    continue

                                vis_info = assess_visibility(
                                    resolved_obj,  # type: ignore[arg-type]
                                    sky_brightness=sky_brightness,
                                    min_altitude_deg=20.0,
                                    observer_lat=location.latitude,
                                    observer_lon=location.longitude,
                                    dt=conditions.timestamp,
                                )
                                if vis_info.is_visible:
                                    visible_star_names.append(resolved_obj.common_name or resolved_obj.name)

                    if visible_star_names:
                        html_parts.append(
                            f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>"
                            f"Visible Stars in this Asterism ({len(visible_star_names)}):</p>"
                        )
                        html_parts.append(
                            "<table style='border-collapse: collapse; width: 100%; margin-left: 20px; margin-top: 10px;'>"
                        )
                        header_bg = "#fff4d6" if not self._is_dark_theme() else "#4a3d1a"
                        border_color = colors["text_dim"]
                        html_parts.append(
                            f"<tr style='background-color: {header_bg};'>"
                            "<th style='padding: 8px; text-align: left; border-bottom: 2px solid #ffc107;'>Star Name</th>"
                            "<th style='padding: 8px; text-align: center; border-bottom: 2px solid #ffc107;'>Info</th>"
                            "</tr>"
                        )
                        for star_name in sorted(set(visible_star_names)):
                            star_name_encoded = star_name.replace('"', "&quot;").replace("'", "&#39;")
                            info_link = f'<a href="starinfo://{star_name_encoded}" style="text-decoration: none; color: {colors["cyan"]}; font-weight: bold;" title="Show star information">\u2139\ufe0f</a>'
                            html_parts.append(
                                f"<tr>"
                                f"<td style='padding: 5px; border-bottom: 1px solid {border_color};'>{star_name}</td>"
                                f"<td style='padding: 5px; text-align: center; border-bottom: 1px solid {border_color};'>{info_link}</td>"
                                f"</tr>"
                            )
                        html_parts.append("</table>")
            except Exception as e:
                logger.debug(f"Could not compute visible asterism stars: {e}")

            # Wikipedia link
            if hasattr(asterism, "wikipedia_url") and asterism.wikipedia_url:
                html_parts.append(
                    f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>Reference:</p>"
                )
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>"
                    f"<a href='{asterism.wikipedia_url}' style='color: {colors['cyan']};'>{asterism.wikipedia_url}</a>"
                    f"</p>"
                )

            # Set HTML content
            self.info_text.setHtml("".join(html_parts))

        except Exception as e:
            logger.error(f"Error loading asterism info: {e}", exc_info=True)
            self.info_text.setHtml(
                f"<p style='color: {colors['error']};'><b>Error:</b> Failed to load asterism information: {e}</p>"
            )

    def _on_link_clicked(self, url: str) -> None:
        """Handle link clicks - open star info dialog."""
        if url.startswith("starinfo://"):
            star_name = url.replace("starinfo://", "")
            # Decode HTML entities
            star_name = star_name.replace("&quot;", '"').replace("&#39;", "'")
            try:
                # Prevent QTextBrowser from clearing content by restoring immediately
                # Use QTimer to ensure it happens after Qt processes the click event
                from PySide6.QtCore import QTimer

                def prevent_clear() -> None:
                    """Reload content to prevent clearing and ensure clean HTML."""
                    self._load_asterism_info()

                # Reload after a short delay to ensure Qt has processed the click
                # This ensures we always have fresh, clean HTML without rgba colors
                QTimer.singleShot(10, prevent_clear)

                from celestron_nexstar.gui.dialogs.object_info_dialog import ObjectInfoDialog

                dialog = ObjectInfoDialog(self, star_name)
                dialog.exec()

                # Reload content after dialog closes to ensure it's fresh and clean
                # This prevents any issues with rgba colors or other HTML parsing problems
                self._load_asterism_info()
            except Exception as e:
                logger.error(f"Error opening star info dialog: {e}", exc_info=True)
                # Reload HTML content on error
                self._load_asterism_info()
