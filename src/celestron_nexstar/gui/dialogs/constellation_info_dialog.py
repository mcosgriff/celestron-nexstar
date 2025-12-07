"""
Dialog to display detailed information about a constellation, including its stars.
"""

import asyncio
import concurrent.futures
import logging
import threading
from collections.abc import Coroutine
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


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

    def mouseDoubleClickEvent(self, event: Any) -> None:  # noqa: N802
        """Override double-click event to call custom handler if set."""
        if self._double_click_handler:
            self._double_click_handler(event)
        else:
            super().mouseDoubleClickEvent(event)


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


class ConstellationInfoDialog(QDialog):
    """Dialog to display detailed information about a constellation and its stars."""

    def __init__(self, parent: QWidget | None, constellation_name: str) -> None:
        """Initialize the constellation info dialog."""
        super().__init__(parent)
        self.setWindowTitle(f"Constellation Information: {constellation_name}")
        self.setMinimumWidth(1000)
        self.setMinimumHeight(500)
        self.resize(1000, 700)  # Wider to accommodate constellation map without horizontal scrollbar

        self.constellation_name = constellation_name
        self.svg_path: Path | None = None  # Store SVG path for double-click viewing

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
        """Load constellation information and its stars."""
        colors = self._get_theme_colors()
        try:
            from celestron_nexstar.api.astronomy.constellations import get_prominent_constellations
            from celestron_nexstar.api.core.enums import SkyBrightness
            from celestron_nexstar.api.core.utils import format_dec, format_ra, ra_dec_to_alt_az
            from celestron_nexstar.api.database.database import get_database
            from celestron_nexstar.api.location.light_pollution import get_light_pollution_data
            from celestron_nexstar.api.location.observer import get_observer_location
            from celestron_nexstar.api.observation.observation_planner import ObservationPlanner
            from celestron_nexstar.api.observation.optics import get_current_configuration
            from celestron_nexstar.api.observation.visibility import assess_visibility

            # Get conditions once (needed for visibility calculations)
            planner = ObservationPlanner()
            conditions = planner.get_tonight_conditions()
            location = get_observer_location()
            config = get_current_configuration()

            async def _load_data() -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any] | None]:
                db = get_database()
                async with db._AsyncSession() as session:
                    # Get sky brightness from light pollution
                    light_pollution = await get_light_pollution_data(session, location.latitude, location.longitude)
                    # Map Bortle class to SkyBrightness (matching observation_planner.py)
                    bortle_to_sky_brightness = {
                        1: SkyBrightness.EXCELLENT,
                        2: SkyBrightness.EXCELLENT,
                        3: SkyBrightness.GOOD,
                        4: SkyBrightness.FAIR,
                        5: SkyBrightness.FAIR,
                        6: SkyBrightness.POOR,
                        7: SkyBrightness.URBAN,  # Suburban/urban transition
                        8: SkyBrightness.URBAN,
                        9: SkyBrightness.URBAN,
                    }
                    sky_brightness = bortle_to_sky_brightness.get(
                        light_pollution.bortle_class.value, SkyBrightness.FAIR
                    )
                    # Get constellation model with boundaries
                    from sqlalchemy import select

                    from celestron_nexstar.api.database.models import ConstellationModel

                    stmt = select(ConstellationModel).where(ConstellationModel.name == self.constellation_name).limit(1)
                    result = await session.execute(stmt)
                    constellation_model = result.scalar_one_or_none()

                    if not constellation_model:
                        return {}, [], None

                    # Get constellation info (for display)
                    constellations = await get_prominent_constellations(session)
                    constellation = None
                    for const in constellations:
                        if const.name == self.constellation_name:
                            constellation = const
                            break

                    if not constellation:
                        return {}, [], None

                    # Get constellation boundaries for map generation
                    boundaries = {
                        "ra_min_hours": constellation_model.ra_min_hours,
                        "ra_max_hours": constellation_model.ra_max_hours,
                        "dec_min_degrees": constellation_model.dec_min_degrees,
                        "dec_max_degrees": constellation_model.dec_max_degrees,
                    }

                    # Get stars in this constellation
                    stars = await db.filter_objects(
                        object_type="star", constellation=self.constellation_name, limit=100
                    )

                    # Calculate visibility for each star directly (much faster than getting all recommended objects)
                    # Note: stars are already CelestialObject instances from filter_objects
                    star_data = []
                    for star in stars:
                        # Calculate visibility info (sky_brightness is defined in the async function scope)
                        vis_info = assess_visibility(
                            star,
                            config=config,
                            sky_brightness=sky_brightness,  # type: ignore[name-defined]  # Defined in async function scope
                            min_altitude_deg=20.0,
                            observer_lat=location.latitude,
                            observer_lon=location.longitude,
                            dt=conditions.timestamp,
                        )

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

                    return (
                        {
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
                        },
                        star_data,
                        boundaries,
                    )

            constellation_data, star_data, boundaries = _run_async_safe(_load_data())

            if not constellation_data or not boundaries:
                self.info_text.setHtml(
                    f"<p style='color: {colors['error']};'><b>Error:</b> Constellation '{self.constellation_name}' not found</p>"
                )
                return

            # Build HTML content
            html_parts = []

            # Constellation name (bold cyan)
            name_html = f"<p style='font-size: 18px; font-weight: bold; color: {colors['cyan']}; margin-bottom: 10px;'>{constellation_data['name']}"
            if constellation_data.get("abbreviation"):
                name_html += f" <span style='color: {colors['cyan']}; font-weight: normal;'>({constellation_data['abbreviation']})</span>"
            name_html += "</p>"
            html_parts.append(name_html)

            # Generate constellation map using starplot MapPlot
            # Based on example: https://starplot.dev/examples/map-orion/
            try:
                import base64
                import io

                # Generate map in background thread to avoid blocking UI
                def _generate_map() -> bytes | None:
                    try:
                        from starplot import MapPlot, Miller, _  # type: ignore[import-untyped]
                        from starplot.styles import PlotStyle, extensions

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

                        # Calculate RA/Dec range from boundaries
                        # Add padding around the constellation boundaries
                        padding_ra = 0.5  # hours
                        padding_dec = 2.0  # degrees

                        ra_min_hours = boundaries["ra_min_hours"]
                        ra_max_hours = boundaries["ra_max_hours"]
                        dec_min = boundaries["dec_min_degrees"] - padding_dec
                        dec_max = boundaries["dec_max_degrees"] + padding_dec

                        # Handle RA wrap-around (e.g., constellation spans 22h to 2h)
                        # If ra_max < ra_min, the constellation wraps around 0/24h
                        wraps_around = ra_max_hours < ra_min_hours

                        if wraps_around:
                            # Constellation wraps around - use a range that doesn't cross 0/24
                            # For wrapped constellations, we'll use a centered approach
                            # Calculate the actual span (accounting for wrap)
                            span = (24 - ra_min_hours) + ra_max_hours
                            # Use center point and add padding
                            center_ra = (ra_min_hours + span / 2) % 24
                            # Create a range that fits within 0-24 without wrapping
                            range_size = span + (padding_ra * 2)
                            # Cap range at reasonable size (max 8 hours = 120 degrees)
                            range_size = min(range_size, 8)
                            ra_min = (center_ra - range_size / 2) % 24
                            ra_max = (center_ra + range_size / 2) % 24
                            # If still wraps, use a simpler approach
                            if ra_min > ra_max:
                                # Use the constellation's min/max with padding, but clamp
                                ra_min = max(0, ra_min_hours - padding_ra)
                                ra_max = min(24, ra_max_hours + padding_ra)
                                # If still invalid, use default centered range
                                if ra_min >= ra_max:
                                    center_ra = (ra_min_hours + ra_max_hours + 24) / 2 % 24
                                    ra_min = max(0, center_ra - 2)
                                    ra_max = min(24, center_ra + 2)
                        else:
                            # Normal case - constellation doesn't wrap
                            ra_min = ra_min_hours - padding_ra
                            ra_max = ra_max_hours + padding_ra
                            # Clamp to valid range
                            if ra_min < 0:
                                ra_min = 0
                            if ra_max > 24:
                                ra_max = 24

                        # Final validation: ensure ra_min < ra_max
                        if ra_min >= ra_max:
                            # Fallback: use constellation center with default range
                            if wraps_around:
                                center_ra = (ra_min_hours + ra_max_hours + 24) / 2 % 24
                            else:
                                center_ra = (ra_min_hours + ra_max_hours) / 2
                            range_size = 4  # 4 hours = 60 degrees
                            ra_min = max(0, center_ra - range_size / 2)
                            ra_max = min(24, center_ra + range_size / 2)
                            # Final check
                            if ra_min >= ra_max:
                                ra_min = 0
                                ra_max = 4  # Default 4-hour range

                        # Convert RA from hours to degrees for starplot (RA * 15 = degrees)
                        ra_min_deg = ra_min * 15
                        ra_max_deg = ra_max * 15

                        # Create map plot
                        plot = MapPlot(
                            projection=Miller(),
                            ra_min=ra_min_deg,
                            ra_max=ra_max_deg,
                            dec_min=dec_min,
                            dec_max=dec_max,
                            ephemeris=ephemeris_file,  # Use downloaded ephemeris file
                            style=plot_style,
                            resolution=4096,  # Good quality for constellation view
                            autoscale=False,
                            scale=1.5,
                        )

                        # Add constellation features
                        plot.gridlines()
                        plot.constellations()
                        plot.constellation_borders()

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
                        plot.export(img_buffer, format="png", padding=0.3, transparent=True)  # type: ignore[no-untyped-call]
                        img_buffer.seek(0)
                        return img_buffer.read()

                    except Exception as e:
                        logger.error(f"Error generating constellation map: {e}", exc_info=True)
                        return None

                # Generate map in background thread
                from concurrent.futures import ThreadPoolExecutor

                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(_generate_map)
                    map_image_data = future.result(timeout=30)  # 30 second timeout

                if map_image_data:
                    # Convert to base64 for embedding in HTML
                    import base64

                    img_base64 = base64.b64encode(map_image_data).decode("utf-8")
                    html_parts.append(
                        f"<div style='margin: 15px 0; text-align: center; padding: 5px; background-color: transparent; display: inline-block;'>"
                        f"<img src='data:image/png;base64,{img_base64}' "
                        f"style='max-width: 900px; max-height: 600px; width: auto; height: auto; display: block;' "
                        f"alt='{constellation_data['name']} constellation map' />"
                        f"<p style='margin-top: 5px; font-size: 0.9em; color: {colors['text_dim']};'>Constellation map generated with starplot</p>"
                        f"</div>"
                    )
                else:
                    logger.warning("Failed to generate constellation map")
            except Exception as e:
                logger.debug(f"Could not generate constellation map: {e}")
                # Silently fail - map is optional

            # Coordinates section
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
                    alt_text = self._format_altitude_user_friendly(alt_deg)
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

        except Exception as e:
            logger.error(f"Error loading constellation info: {e}", exc_info=True)
            self.info_text.setHtml(
                f"<p style='color: {colors['error']};'><b>Error:</b> Failed to load constellation information: {e}</p>"
            )

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
