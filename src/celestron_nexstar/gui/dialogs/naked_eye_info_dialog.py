"""
Dialog to display naked-eye viewing information.
"""

import asyncio
import concurrent.futures
import logging
import threading
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


if TYPE_CHECKING:
    pass


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


class NakedEyeInfoDialog(QDialog):
    """Dialog to display naked-eye viewing information."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the naked-eye info dialog."""
        super().__init__(parent)
        self.setWindowTitle("Naked-Eye Stargazing Tonight")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        self.resize(800, 700)  # Set reasonable default size

        # Create layout
        layout = QVBoxLayout(self)

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

        # Set initial stylesheet (will be updated with theme colors in _load_naked_eye_info)
        self.info_text.setStyleSheet(
            f"""
            QTextEdit {{
                font-family: {font_family};
                background-color: transparent;
                border: none;
            }}
        """
        )
        layout.addWidget(self.info_text)

        # Add button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        # Load naked-eye information
        self._load_naked_eye_info()

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
            "header": "#00bcd4" if is_dark else "#00838f",  # Cyan
            "cyan": "#00bcd4" if is_dark else "#00838f",
            "green": "#4caf50" if is_dark else "#2e7d32",
            "yellow": "#ffc107" if is_dark else "#f57c00",
            "red": "#f44336" if is_dark else "#c62828",
            "error": "#f44336" if is_dark else "#c62828",
        }

    def _format_local_time(self, dt: datetime, lat: float, lon: float) -> str:
        """Format datetime in local timezone."""
        from celestron_nexstar.api.core.utils import format_local_time

        return format_local_time(dt, lat, lon)

    def _load_naked_eye_info(self) -> None:
        """Load naked-eye viewing information from the API and format it for display."""
        colors = self._get_theme_colors()

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
            from celestron_nexstar.api.location.observer import get_observer_location

            # Get location
            location = get_observer_location()
            if not location:
                self.info_text.setHtml(
                    f"<p><span style='color: {colors['error']};'><b>Error:</b> No observer location set. Use 'nexstar location set' to configure your location.</span></p>"
                )
                return

            lat, lon = location.latitude, location.longitude
            location_name = location.name or f"{lat:.2f}°, {lon:.2f}°"

            # Get current time and sunset/sunrise
            now = datetime.now(UTC)
            from celestron_nexstar.api.astronomy.sun_moon import calculate_sun_times

            sun_times = calculate_sun_times(lat, lon, now)
            sunset = sun_times.get("sunset")
            sunrise = sun_times.get("sunrise")

            # Build HTML content
            html_content = []
            html_content.append(
                f"<style>h2 {{ color: {colors['header']}; margin-top: 1em; margin-bottom: 0.5em; }}</style>"
            )

            # Header
            html_content.append(
                f"<p><span style='color: {colors['header']}; font-size: 14pt; font-weight: bold;'>Naked-Eye Stargazing for {location_name}</span></p>"
            )
            html_content.append(
                f"<p style='color: {colors['text_dim']};'>Viewing Method: Naked-eye (no equipment needed)</p>"
            )
            html_content.append(
                f"<p style='color: {colors['text_dim']};'>Limiting Magnitude: ~6.0 (varies with sky darkness and dark adaptation)</p>"
            )

            sunset_str = self._format_local_time(sunset, lat, lon) if sunset else "—"
            sunrise_str = self._format_local_time(sunrise, lat, lon) if sunrise else "—"
            html_content.append(
                f"<p style='color: {colors['text_dim']};'>Sunset: {sunset_str} | Sunrise: {sunrise_str}</p>"
            )
            html_content.append("<br>")

            # Load async content using safe async runner
            async def _load_async_content() -> list[str]:
                """Load all async content."""
                content_parts = []

                # ISS Passes
                from celestron_nexstar.api.events.iss_tracking import get_iss_passes_cached
                from celestron_nexstar.api.telescope.compass import azimuth_to_compass_8point, format_object_path

                iss_passes = await get_iss_passes_cached(
                    lat, lon, start_time=now, days=7, min_altitude_deg=20.0, db_session=None
                )

                content_parts.append("<h2>ISS Visible Passes</h2>")
                content_parts.append(
                    f"<p style='color: {colors['text_dim']};'>Bright satellite passes visible without equipment</p>"
                )
                content_parts.append("<br>")

                if iss_passes:
                    visible_passes = []
                    for iss_pass in iss_passes:
                        # Only show sunlit passes that are clearly visible to naked eye (>30° altitude)
                        if iss_pass.is_visible and iss_pass.max_altitude_deg >= 30:
                            visible_passes.append(iss_pass)
                            if len(visible_passes) >= 10:  # Limit to 10 best passes
                                break

                    if visible_passes:
                        content_parts.append(
                            "<table style='border-collapse: collapse; width: 100%; border: 1px solid #444;'>"
                        )
                        content_parts.append(
                            f"<tr style='background-color: {colors['header']}; color: white;'>"
                            "<th style='padding: 8px; text-align: left;'>Date</th>"
                            "<th style='padding: 8px; text-align: left;'>Rise Time</th>"
                            "<th style='padding: 8px; text-align: right;'>Max Alt</th>"
                            "<th style='padding: 8px; text-align: left;'>Path</th>"
                            "<th style='padding: 8px; text-align: right;'>Duration</th>"
                            "<th style='padding: 8px; text-align: left;'>Quality</th>"
                            "</tr>"
                        )

                        for iss_pass in visible_passes:
                            rise_time_str = self._format_local_time(iss_pass.rise_time, lat, lon)
                            date_str = iss_pass.rise_time.strftime("%a %b %d")

                            path = format_object_path(
                                iss_pass.rise_azimuth_deg,
                                iss_pass.max_azimuth_deg,
                                iss_pass.max_altitude_deg,
                                iss_pass.set_azimuth_deg,
                            )

                            duration_min = iss_pass.duration_seconds // 60
                            quality = iss_pass.quality_rating

                            if quality == "Excellent" or quality == "Very Good":
                                quality_color = colors["green"]
                            elif quality == "Good":
                                quality_color = colors["yellow"]
                            else:
                                quality_color = colors["text_dim"]

                            content_parts.append(
                                f"<tr style='border-bottom: 1px solid #444;'>"
                                f"<td style='padding: 6px; color: {colors['cyan']};'>{date_str}</td>"
                                f"<td style='padding: 6px; color: {colors['green']};'>{rise_time_str}</td>"
                                f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{iss_pass.max_altitude_deg:.0f}°</td>"
                                f"<td style='padding: 6px; color: {colors['text_dim']};'>{path}</td>"
                                f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{duration_min}m {iss_pass.duration_seconds % 60}s</td>"
                                f"<td style='padding: 6px; color: {quality_color};'>{quality}</td>"
                                "</tr>"
                            )

                        content_parts.append("</table>")
                        content_parts.append(
                            f"<p style='color: {colors['text_dim']};'>Only showing passes with max altitude >30° for best naked-eye visibility</p>"
                        )
                    else:
                        content_parts.append(
                            f"<p><span style='color: {colors['yellow']};'>No excellent naked-eye ISS passes in the next 7 days</span></p>"
                        )
                        content_parts.append(
                            f"<p style='color: {colors['text_dim']};'>Try lowering altitude requirement or check back later</p>"
                        )
                else:
                    content_parts.append(
                        f"<p><span style='color: {colors['yellow']};'>No visible ISS passes in the next 7 days</span></p>"
                    )

                content_parts.append("<br>")

                # Meteor Showers
                from celestron_nexstar.api.astronomy.meteor_showers import (
                    get_active_showers,
                    get_peak_showers,
                    get_radiant_position,
                )
                from celestron_nexstar.api.database.models import get_db_session

                async with get_db_session() as db_session:
                    active_showers = await get_active_showers(db_session, now)
                    peak_showers = await get_peak_showers(db_session, now, tolerance_days=3)

                content_parts.append("<h2>Active Meteor Showers</h2>")
                content_parts.append(
                    f"<p style='color: {colors['text_dim']};'>Best observed with naked eye - no equipment needed!</p>"
                )
                content_parts.append("<br>")

                if active_showers:
                    content_parts.append(
                        "<table style='border-collapse: collapse; width: 100%; border: 1px solid #444;'>"
                    )
                    content_parts.append(
                        f"<tr style='background-color: {colors['header']}; color: white;'>"
                        "<th style='padding: 8px; text-align: left;'>Shower</th>"
                        "<th style='padding: 8px; text-align: left;'>Status</th>"
                        "<th style='padding: 8px; text-align: right;'>ZHR</th>"
                        "<th style='padding: 8px; text-align: left;'>Radiant</th>"
                        "<th style='padding: 8px; text-align: left;'>Best Time</th>"
                        "</tr>"
                    )

                    # Calculate midnight for radiant position
                    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    if midnight < now:
                        from datetime import timedelta

                        midnight = midnight + timedelta(days=1)

                    for shower in active_showers:
                        is_peak = shower in peak_showers
                        status = "At Peak" if is_peak else "Active"
                        status_color = colors["green"] if is_peak else colors["text"]

                        alt, az = get_radiant_position(shower, lat, lon, midnight)
                        radiant_dir = azimuth_to_compass_8point(az)
                        radiant_text = f"{radiant_dir}, {alt:.0f}° high"

                        # Best viewing time
                        best_time = "After midnight" if alt > 30 else "Late evening"

                        content_parts.append(
                            f"<tr style='border-bottom: 1px solid #444;'>"
                            f"<td style='padding: 6px; font-weight: bold; color: {colors['text']};'>{shower.name}</td>"
                            f"<td style='padding: 6px; color: {status_color};'>{status}</td>"
                            f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{shower.zhr_peak}</td>"
                            f"<td style='padding: 6px; color: {colors['text_dim']};'>{radiant_text}</td>"
                            f"<td style='padding: 6px; color: {colors['text_dim']};'>{best_time}</td>"
                            "</tr>"
                        )

                    content_parts.append("</table>")
                    content_parts.append(
                        f"<p style='color: {colors['text_dim']};'>ZHR = Zenithal Hourly Rate (meteors per hour under perfect conditions)</p>"
                    )
                    content_parts.append(
                        f"<p style='color: {colors['text_dim']};'>Don't stare at the radiant - meteors appear throughout the sky</p>"
                    )
                    content_parts.append(
                        f"<p style='color: {colors['text_dim']};'>Best viewing: Lie back, look at dark sky, give eyes 20+ minutes to adapt</p>"
                    )
                else:
                    content_parts.append(
                        f"<p><span style='color: {colors['yellow']};'>No major meteor showers currently active</span></p>"
                    )

                content_parts.append("<br>")

                # Prominent Constellations
                from celestron_nexstar.api.astronomy.constellations import (
                    get_prominent_constellations,
                    get_visible_asterisms,
                    get_visible_constellations,
                )
                from celestron_nexstar.api.core.enums import CelestialObjectType
                from celestron_nexstar.api.core.utils import ra_dec_to_alt_az
                from celestron_nexstar.api.database.database import get_database

                # Calculate midnight for constellation calculations
                midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
                if midnight < now:
                    from datetime import timedelta

                    midnight = midnight + timedelta(days=1)

                # Get visible constellations
                async with get_db_session() as db_session:
                    visible_constellations = await get_visible_constellations(
                        db_session, lat, lon, midnight, min_altitude_deg=15.0
                    )

                # Track which constellations have low centers (below normal viewing threshold)
                normal_threshold = 30.0  # 30° for naked-eye
                low_altitude_constellations = set()

                # Mark constellations already in the list that are below normal threshold
                for constellation, alt, _az in visible_constellations:
                    if alt < normal_threshold:
                        low_altitude_constellations.add(constellation.name)

                # Also include constellations that have visible stars, even if center is low
                # Get visible stars first to find their constellations
                max_magnitude = 6.0  # Naked-eye limiting magnitude
                db = get_database()
                stars_for_const = await db.filter_objects(
                    object_type=CelestialObjectType.STAR,
                    max_magnitude=max_magnitude,
                    limit=500,
                )

                # Find unique constellations from visible stars
                constellations_with_stars = set()
                for star in stars_for_const:
                    if star.magnitude is None:
                        continue
                    alt, az = ra_dec_to_alt_az(
                        star.ra_hours,
                        star.dec_degrees,
                        lat,
                        lon,
                        midnight,
                    )
                    if alt >= 30.0 and star.constellation:
                        constellations_with_stars.add(star.constellation)

                # Add constellations that have visible stars but aren't already in the list
                async with get_db_session() as db_session:
                    all_prominent = await get_prominent_constellations(db_session)
                existing_names = {c.name for c, _, _ in visible_constellations}

                for constellation in all_prominent:
                    if constellation.name in constellations_with_stars and constellation.name not in existing_names:
                        # Calculate altitude for this constellation
                        alt, az = ra_dec_to_alt_az(
                            constellation.ra_hours,
                            constellation.dec_degrees,
                            lat,
                            lon,
                            midnight,
                        )
                        # Include even if slightly below threshold (as long as it has visible stars)
                        if alt >= 0:  # Above horizon
                            visible_constellations.append((constellation, alt, az))
                            # Mark if center is below normal threshold
                            if alt < normal_threshold:
                                low_altitude_constellations.add(constellation.name)

                # Re-sort by altitude
                visible_constellations.sort(key=lambda x: x[1], reverse=True)

                # Separate into fully visible and partially visible
                fully_visible = [
                    (c, alt, az) for c, alt, az in visible_constellations if c.name not in low_altitude_constellations
                ]
                partially_visible = [
                    (c, alt, az) for c, alt, az in visible_constellations if c.name in low_altitude_constellations
                ]

                # Helper function to get current season
                def _get_current_season(dt: datetime) -> str:
                    month = dt.month
                    if month in (3, 4, 5):
                        return "Spring"
                    elif month in (6, 7, 8):
                        return "Summer"
                    elif month in (9, 10, 11):
                        return "Fall"
                    else:  # 12, 1, 2
                        return "Winter"

                content_parts.append("<h2>Prominent Constellations (Tonight)</h2>")
                content_parts.append(
                    f"<p style='color: {colors['text_dim']};'>Easy-to-spot constellations for beginners</p>"
                )
                content_parts.append("<br>")

                if fully_visible:
                    current_season = _get_current_season(now)

                    content_parts.append(
                        "<table style='border-collapse: collapse; width: 100%; border: 1px solid #444;'>"
                    )
                    content_parts.append(
                        f"<tr style='background-color: {colors['header']}; color: white;'>"
                        "<th style='padding: 8px; text-align: left;'>Constellation</th>"
                        "<th style='padding: 8px; text-align: right;'>Direction</th>"
                        "<th style='padding: 8px; text-align: right;'>Altitude</th>"
                        "<th style='padding: 8px; text-align: left;'>Key Star</th>"
                        "<th style='padding: 8px; text-align: left;'>What to Look For</th>"
                        "</tr>"
                    )

                    for constellation, alt, az in fully_visible[:10]:  # Top 10
                        direction = azimuth_to_compass_8point(az)

                        # Key star with magnitude
                        key_star = f"{constellation.brightest_star} ({constellation.magnitude:.2f})"

                        # Add season note if out of season
                        description = constellation.description
                        if constellation.season != current_season:
                            description = (
                                f"{description} (best in {constellation.season.lower()}, visible out of season)"
                            )

                        content_parts.append(
                            f"<tr style='border-bottom: 1px solid #444;'>"
                            f"<td style='padding: 6px; font-weight: bold; color: {colors['text']};'>{constellation.name}</td>"
                            f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{direction}</td>"
                            f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{alt:.0f}°</td>"
                            f"<td style='padding: 6px; color: {colors['text_dim']};'>{key_star}</td>"
                            f"<td style='padding: 6px; color: {colors['text_dim']};'>{description}</td>"
                            "</tr>"
                        )

                    content_parts.append("</table>")
                    content_parts.append(
                        f"<p style='color: {colors['text_dim']};'>💡 Tip: Estimate altitude with your hand - hold arm outstretched: fist = 10°, thumb = 2°, pinky = 1°</p>"
                    )
                else:
                    content_parts.append(
                        f"<p><span style='color: {colors['yellow']};'>No prominent constellations currently visible</span></p>"
                    )

                # Partially visible constellations
                if partially_visible:
                    content_parts.append("<br>")
                    content_parts.append("<h2>Constellations Partially Visible</h2>")
                    content_parts.append(
                        f"<p style='color: {colors['text_dim']};'>Some stars visible, but whole constellation is low in the sky</p>"
                    )
                    content_parts.append("<br>")

                    current_season = _get_current_season(now)

                    content_parts.append(
                        "<table style='border-collapse: collapse; width: 100%; border: 1px solid #444;'>"
                    )
                    content_parts.append(
                        f"<tr style='background-color: {colors['header']}; color: white;'>"
                        "<th style='padding: 8px; text-align: left;'>Constellation</th>"
                        "<th style='padding: 8px; text-align: right;'>Direction</th>"
                        "<th style='padding: 8px; text-align: right;'>Altitude</th>"
                        "<th style='padding: 8px; text-align: left;'>Key Star</th>"
                        "<th style='padding: 8px; text-align: left;'>Note</th>"
                        "</tr>"
                    )

                    for constellation, alt, az in partially_visible:
                        direction = azimuth_to_compass_8point(az)

                        # Key star with magnitude
                        key_star = f"{constellation.brightest_star} ({constellation.magnitude:.2f})"

                        # Check if constellation is out of season
                        season_note = ""
                        if constellation.season != current_season:
                            season_note = f" (best in {constellation.season.lower()}, visible out of season)"

                        content_parts.append(
                            f"<tr style='border-bottom: 1px solid #444;'>"
                            f"<td style='padding: 6px; font-weight: bold; color: {colors['text']};'>{constellation.name}</td>"
                            f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{direction}</td>"
                            f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{alt:.0f}°</td>"
                            f"<td style='padding: 6px; color: {colors['text_dim']};'>{key_star}</td>"
                            f"<td style='padding: 6px; color: {colors['text_dim']};'>Only some stars visible - whole constellation low{season_note}</td>"
                            "</tr>"
                        )

                    content_parts.append("</table>")

                content_parts.append("<br>")

                # Bright Stars
                content_parts.append("<h2>Bright Stars (Tonight)</h2>")
                content_parts.append(
                    f"<p style='color: {colors['text_dim']};'>Naked-eye visible stars (magnitude ≤ 6.0)</p>"
                )
                content_parts.append("<br>")

                # Get visible stars
                visible_stars_list = []
                for star in stars_for_const:
                    if star.magnitude is None:
                        continue
                    alt, az = ra_dec_to_alt_az(
                        star.ra_hours,
                        star.dec_degrees,
                        lat,
                        lon,
                        midnight,
                    )
                    if alt >= 30.0:
                        visible_stars_list.append((star, alt, az))

                # Sort by magnitude (brightest first), then by altitude
                visible_stars_list.sort(key=lambda x: (x[0].magnitude or 99, -x[1]))

                if visible_stars_list:
                    visible_stars_list = visible_stars_list[:15]  # Top 15

                    content_parts.append(
                        "<table style='border-collapse: collapse; width: 100%; border: 1px solid #444;'>"
                    )
                    content_parts.append(
                        f"<tr style='background-color: {colors['header']}; color: white;'>"
                        "<th style='padding: 8px; text-align: left;'>Star</th>"
                        "<th style='padding: 8px; text-align: right;'>Direction</th>"
                        "<th style='padding: 8px; text-align: right;'>Altitude</th>"
                        "<th style='padding: 8px; text-align: right;'>Magnitude</th>"
                        "<th style='padding: 8px; text-align: left;'>Constellation</th>"
                        "<th style='padding: 8px; text-align: left;'>Notes</th>"
                        "</tr>"
                    )

                    for star, alt, az in visible_stars_list:
                        direction = azimuth_to_compass_8point(az)
                        star_name = star.common_name or star.name
                        mag_str = f"{star.magnitude:.2f}" if star.magnitude else "—"
                        constellation_name = star.constellation or "—"
                        notes = star.description or ""

                        content_parts.append(
                            f"<tr style='border-bottom: 1px solid #444;'>"
                            f"<td style='padding: 6px; font-weight: bold; color: {colors['text']};'>{star_name}</td>"
                            f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{direction}</td>"
                            f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{alt:.0f}°</td>"
                            f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{mag_str}</td>"
                            f"<td style='padding: 6px; color: {colors['text_dim']};'>{constellation_name}</td>"
                            f"<td style='padding: 6px; color: {colors['text_dim']};'>{notes}</td>"
                            "</tr>"
                        )

                    content_parts.append("</table>")
                    content_parts.append(
                        f"<p style='color: {colors['text_dim']};'>💡 Tip: Estimate altitude with your hand - hold arm outstretched: fist = 10°, thumb = 2°, pinky = 1°</p>"
                    )
                else:
                    content_parts.append(
                        f"<p><span style='color: {colors['yellow']};'>No bright stars currently visible</span></p>"
                    )

                content_parts.append("<br>")

                # Visible Asterisms
                content_parts.append("<h2>Star Patterns to Find (Asterisms)</h2>")
                content_parts.append(
                    f"<p style='color: {colors['text_dim']};'>Famous patterns that are easy to recognize</p>"
                )
                content_parts.append("<br>")

                async with get_db_session() as db_session:
                    visible_asterisms = await get_visible_asterisms(
                        db_session, lat, lon, midnight, min_altitude_deg=30.0
                    )

                if visible_asterisms:
                    # Group by familiarity/importance
                    priority_asterisms = [
                        "Big Dipper",
                        "Orion's Belt",
                        "Summer Triangle",
                        "Winter Triangle",
                        "Pleiades",
                    ]

                    content_parts.append(
                        "<table style='border-collapse: collapse; width: 100%; border: 1px solid #444;'>"
                    )
                    content_parts.append(
                        f"<tr style='background-color: {colors['header']}; color: white;'>"
                        "<th style='padding: 8px; text-align: left;'>Pattern</th>"
                        "<th style='padding: 8px; text-align: right;'>Direction</th>"
                        "<th style='padding: 8px; text-align: right;'>Altitude</th>"
                        "<th style='padding: 8px; text-align: left;'>How to Find It</th>"
                        "</tr>"
                    )

                    # Show priority asterisms first
                    shown = set()
                    for asterism, alt, az in visible_asterisms:
                        if asterism.name in priority_asterisms and asterism.name not in shown:
                            direction = azimuth_to_compass_8point(az)
                            description = asterism.description or ""

                            content_parts.append(
                                f"<tr style='border-bottom: 1px solid #444;'>"
                                f"<td style='padding: 6px; font-weight: bold; color: {colors['text']};'>{asterism.name}</td>"
                                f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{direction}</td>"
                                f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{alt:.0f}°</td>"
                                f"<td style='padding: 6px; color: {colors['text_dim']};'>{description}</td>"
                                "</tr>"
                            )
                            shown.add(asterism.name)

                    # Then show others
                    for asterism, alt, az in visible_asterisms[:10]:
                        if asterism.name not in shown:
                            direction = azimuth_to_compass_8point(az)
                            description = asterism.description or ""

                            content_parts.append(
                                f"<tr style='border-bottom: 1px solid #444;'>"
                                f"<td style='padding: 6px; font-weight: bold; color: {colors['text']};'>{asterism.name}</td>"
                                f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{direction}</td>"
                                f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{alt:.0f}°</td>"
                                f"<td style='padding: 6px; color: {colors['text_dim']};'>{description}</td>"
                                "</tr>"
                            )
                            shown.add(asterism.name)

                    content_parts.append("</table>")
                    content_parts.append(
                        f"<p style='color: {colors['text_dim']};'>💡 Tip: Estimate altitude with your hand - hold arm outstretched: fist = 10°, thumb = 2°, pinky = 1°</p>"
                    )
                else:
                    content_parts.append(
                        f"<p><span style='color: {colors['yellow']};'>No prominent asterisms currently visible</span></p>"
                    )

                return content_parts

            # Run async content loading
            async_content = _run_async_safe(_load_async_content())
            html_content.extend(async_content)

            # Viewing tips
            html_content.append("<br>")
            html_content.append("<h2>Stargazing Tips (No Equipment Needed)</h2>")
            html_content.append(
                f"<ul style='margin-left: 20px; color: {colors['text']};'>"
                f"<li style='margin-bottom: 5px;'>Find a dark location away from city lights</li>"
                f"<li style='margin-bottom: 5px;'>Allow 20-30 minutes for your eyes to fully adapt to darkness</li>"
                f"<li style='margin-bottom: 5px;'>Avoid looking at phones or bright lights (use red light if needed)</li>"
                f"<li style='margin-bottom: 5px;'>Lie back on a blanket or reclining chair for comfortable viewing</li>"
                f"<li style='margin-bottom: 5px;'>Start with bright stars and asterisms, then find fainter objects</li>"
                f"<li style='margin-bottom: 5px;'>Use averted vision: look slightly to the side to see fainter objects</li>"
                f"<li style='margin-bottom: 5px;'><b>Estimating altitude:</b> Hold your arm outstretched - your fist = ~10°, thumb = ~2°, pinky = ~1°</li>"
                f"<li style='margin-bottom: 5px;'>Best viewing: New moon or when moon has set</li>"
                "</ul>"
            )

            self.info_text.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading naked-eye info: {e}", exc_info=True)
            self.info_text.setHtml(
                f"<p><span style='color: {colors['error']};'><b>Error:</b> Failed to load naked-eye viewing information: {e}</span></p>"
            )
