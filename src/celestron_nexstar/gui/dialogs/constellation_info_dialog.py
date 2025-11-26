"""
Dialog to display detailed information about a constellation, including its stars.
"""

import asyncio
import concurrent.futures
import logging
import threading
from collections.abc import Coroutine
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


class ConstellationInfoDialog(QDialog):
    """Dialog to display detailed information about a constellation and its stars."""

    def __init__(self, parent: QWidget | None, constellation_name: str) -> None:
        """Initialize the constellation info dialog."""
        super().__init__(parent)
        self.setWindowTitle(f"Constellation Information: {constellation_name}")
        self.setMinimumWidth(700)
        self.setMinimumHeight(600)
        self.resize(900, 700)

        self.constellation_name = constellation_name

        # Create layout
        layout = QVBoxLayout(self)

        # Create scrollable text area with rich HTML formatting
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setAcceptRichText(True)
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
            from celestron_nexstar.api.core.enums import CelestialObjectType
            from celestron_nexstar.api.core.utils import format_dec, format_ra
            from celestron_nexstar.api.database.database import get_database
            from celestron_nexstar.api.observation.observation_planner import ObservationPlanner

            # Get conditions and recommended stars outside async context
            # (both use asyncio.run internally)
            planner = ObservationPlanner()
            conditions = planner.get_tonight_conditions()
            all_recommended_stars = planner.get_recommended_objects(
                conditions, CelestialObjectType.STAR, max_results=1000, best_for_seeing=False
            )

            # Create a map of star names to recommended objects
            star_map = {}
            for rec in all_recommended_stars:
                star_map[rec.obj.name] = rec
                if rec.obj.common_name:
                    star_map[rec.obj.common_name] = rec

            async def _load_data() -> tuple[dict, list]:
                db = get_database()
                async with db._AsyncSession() as session:
                    # Get constellation info
                    constellations = await get_prominent_constellations(session)
                    constellation = None
                    for const in constellations:
                        if const.name == self.constellation_name:
                            constellation = const
                            break

                    if not constellation:
                        return None, []

                    # Get stars in this constellation
                    stars = await db.filter_objects(
                        object_type="star", constellation=self.constellation_name, limit=100
                    )

                    # Match stars to their recommended objects (from outside async context)
                    star_data = []
                    for star in stars:
                        rec = star_map.get(star.name) or star_map.get(star.common_name or "")
                        if rec:
                            star_data.append(rec)

                    # Sort by visibility probability (chance) descending, then by priority
                    star_data.sort(key=lambda x: (x.visibility_probability, x.priority), reverse=True)

                    return {
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
                    }, star_data

            constellation_data, star_data = _run_async_safe(_load_data())

            if not constellation_data:
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

            # Try to load and display constellation SVG
            try:
                import urllib.parse

                from celestron_nexstar.api.astronomy.constellation_images import get_constellation_svg

                svg_path = get_constellation_svg(constellation_data["name"])
                if svg_path and svg_path.exists():
                    # Read SVG content and embed it in HTML
                    svg_content = svg_path.read_text(encoding="utf-8")
                    # URL encode the SVG content for data URI
                    svg_encoded = urllib.parse.quote(svg_content)
                    # Limit SVG size for display (max width 400px)
                    html_parts.append(
                        f"<div style='margin: 15px 0; text-align: center;'>"
                        f"<img src='data:image/svg+xml;charset=utf-8,{svg_encoded}' "
                        f"style='max-width: 400px; max-height: 400px; width: auto; height: auto; "
                        f"background-color: transparent;' "
                        f"alt='{constellation_data['name']} constellation diagram' />"
                        f"</div>"
                    )
            except Exception as e:
                logger.debug(f"Could not load constellation SVG: {e}")
                # Silently fail - SVG is optional

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
                html_parts.append(
                    "<tr style='background-color: rgba(255, 193, 7, 0.2);'>"
                    "<th style='padding: 8px; text-align: left; border-bottom: 2px solid #ffc107;'>Name</th>"
                    "<th style='padding: 8px; text-align: right; border-bottom: 2px solid #ffc107;'>Mag</th>"
                    "<th style='padding: 8px; text-align: right; border-bottom: 2px solid #ffc107;'>Alt</th>"
                    "<th style='padding: 8px; text-align: right; border-bottom: 2px solid #ffc107;'>Chance</th>"
                    "</tr>"
                )

                for rec in star_data[:50]:  # Limit to top 50 stars
                    obj = rec.obj
                    display_name = obj.common_name or obj.name
                    mag_text = f"{rec.apparent_magnitude:.2f}" if rec.apparent_magnitude else "-"
                    alt_text = f"{rec.altitude:.0f}°"
                    prob_text = f"{rec.visibility_probability:.0%}"

                    # Color code by visibility probability
                    if rec.visibility_probability >= 0.8:
                        prob_color = colors["green"]
                    elif rec.visibility_probability >= 0.5:
                        prob_color = colors["yellow"]
                    else:
                        prob_color = colors["text_dim"]

                    html_parts.append(
                        f"<tr>"
                        f"<td style='padding: 5px; border-bottom: 1px solid rgba(255, 255, 255, 0.1);'>{display_name}</td>"
                        f"<td style='padding: 5px; text-align: right; border-bottom: 1px solid rgba(255, 255, 255, 0.1);'>{mag_text}</td>"
                        f"<td style='padding: 5px; text-align: right; border-bottom: 1px solid rgba(255, 255, 255, 0.1);'>{alt_text}</td>"
                        f"<td style='padding: 5px; text-align: right; border-bottom: 1px solid rgba(255, 255, 255, 0.1);'>"
                        f"<span style='color: {prob_color};'>{prob_text}</span></td>"
                        f"</tr>"
                    )

                html_parts.append("</table>")
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
