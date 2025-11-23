"""
Dialog to display detailed information about a celestial object.
"""

import asyncio
import logging
from typing import TYPE_CHECKING

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


class ObjectInfoDialog(QDialog):
    """Dialog to display detailed information about a celestial object."""

    def __init__(self, parent: QWidget | None, object_name: str) -> None:
        """Initialize the object info dialog."""
        super().__init__(parent)
        self.setWindowTitle(f"Object Information: {object_name}")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)

        self.object_name = object_name

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

        # Load object information
        self._load_object_info()

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

    def _explain_object_type(self, object_type: str) -> str:
        """Get human-readable explanation of object type."""
        explanations = {
            "star": "A star",
            "planet": "A planet in our solar system",
            "galaxy": "A galaxy",
            "nebula": "A nebula (cloud of gas and dust)",
            "cluster": "A star cluster",
            "double_star": "A double or multiple star system",
            "asterism": "A recognizable star pattern",
            "constellation": "A constellation",
            "moon": "A moon or natural satellite",
        }
        return explanations.get(object_type, object_type)

    def _get_azimuth_direction(self, azimuth_deg: float) -> str:
        """Convert azimuth to cardinal direction."""
        if azimuth_deg < 22.5 or azimuth_deg >= 337.5:
            return "N"
        elif azimuth_deg < 67.5:
            return "NE"
        elif azimuth_deg < 112.5:
            return "E"
        elif azimuth_deg < 157.5:
            return "SE"
        elif azimuth_deg < 202.5:
            return "S"
        elif azimuth_deg < 247.5:
            return "SW"
        elif azimuth_deg < 292.5:
            return "W"
        else:
            return "NW"

    def _load_object_info(self) -> None:
        """Load object information from the API."""
        colors = self._get_theme_colors()
        try:
            from celestron_nexstar.api.catalogs.catalogs import get_object_by_name
            from celestron_nexstar.api.core.enums import CelestialObjectType
            from celestron_nexstar.api.core.utils import format_dec, format_ra
            from celestron_nexstar.api.observation.visibility import assess_visibility

            # Get object by name
            matches = asyncio.run(get_object_by_name(self.object_name))

            if not matches:
                self.info_text.setHtml(
                    f"<p style='color: {colors['error']};'><b>Error:</b> Object '{self.object_name}' not found</p>"
                )
                return

            # Use first match (in GUI, we should have exact match from table)
            obj = matches[0]

            # If multiple matches, use the first one
            if len(matches) > 1:
                logger.warning(f"Multiple matches found for '{self.object_name}', using first: {obj.name}")

            # Assess visibility
            visibility_info = assess_visibility(obj)

            # Get visibility probability if possible
            visibility_probability = None
            visibility_explanations: list[str] = []
            try:
                from celestron_nexstar.api.observation.observation_planner import ObservationPlanner

                planner = ObservationPlanner()
                conditions = planner.get_tonight_conditions()
                result = planner._calculate_visibility_probability(obj, conditions, visibility_info)
                if isinstance(result, tuple):
                    visibility_probability, visibility_explanations = result
                else:
                    visibility_probability = result
            except Exception:
                pass

            # Build HTML content
            html_parts = []

            # Name and common name (bold cyan)
            name_html = f"<p style='font-size: 18px; font-weight: bold; color: {colors['cyan']}; margin-bottom: 10px;'>{obj.name}"
            if obj.common_name and obj.common_name != obj.name:
                name_html += f" <span style='color: {colors['cyan']}; font-weight: normal;'>({obj.common_name})</span>"
            name_html += "</p>"
            html_parts.append(name_html)

            # Coordinates section (bold yellow header, green values)
            html_parts.append(
                f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>Coordinates:</p>"
            )
            ra_str = format_ra(obj.ra_hours)
            dec_str = format_dec(obj.dec_degrees)
            html_parts.append(
                f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>"
                f"<span style='color: {colors['green']};'>RA:</span> {ra_str}<br>"
                f"<span style='color: {colors['green']};'>Dec:</span> {dec_str}"
                f"</p>"
            )

            # Properties section (bold yellow header)
            html_parts.append(
                f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>Properties:</p>"
            )
            type_explanation = self._explain_object_type(obj.object_type.value)
            type_text = obj.object_type.value
            if type_explanation != obj.object_type.value:
                type_text += f" ({type_explanation})"
            html_parts.append(
                f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>Type: {type_text}</p>"
            )
            if obj.magnitude is not None:
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>Magnitude: {obj.magnitude:.2f}</p>"
                )
            html_parts.append(
                f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>Catalog: {obj.catalog}</p>"
            )

            # Visibility section (bold yellow header)
            html_parts.append(
                f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>Visibility:</p>"
            )
            if visibility_info.is_visible:
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>"
                    f"Status: <span style='color: {colors['green']}; font-weight: bold;'>✓ Visible</span></p>"
                )
            else:
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>"
                    f"Status: <span style='color: {colors['red']}; font-weight: bold;'>✗ Not Visible</span></p>"
                )

            if visibility_info.altitude_deg is not None:
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>"
                    f"Altitude: {visibility_info.altitude_deg:.1f}°</p>"
                )
            if visibility_info.azimuth_deg is not None:
                direction = self._get_azimuth_direction(visibility_info.azimuth_deg)
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>"
                    f"Azimuth: {visibility_info.azimuth_deg:.1f}° ({direction})</p>"
                )
            if visibility_info.limiting_magnitude is not None:
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>"
                    f"Limiting Magnitude: {visibility_info.limiting_magnitude:.2f}</p>"
                )
            if visibility_info.observability_score is not None:
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>"
                    f"Observability Score: {visibility_info.observability_score:.0%}</p>"
                )

            # Visibility probability with color coding
            if visibility_probability is not None:
                if visibility_probability >= 0.8:
                    prob_color = colors["green"]
                    prob_weight = "bold"
                elif visibility_probability >= 0.5:
                    prob_color = colors["yellow"]
                    prob_weight = "normal"
                elif visibility_probability >= 0.3:
                    prob_color = colors["red"]
                    prob_weight = "normal"
                else:
                    prob_color = colors["text_dim"]
                    prob_weight = "normal"
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>"
                    f"Chance of Seeing: <span style='color: {prob_color}; font-weight: {prob_weight};'>"
                    f"{visibility_probability:.0%}</span></p>"
                )

                # Add explanations if probability is low
                if (
                    visibility_probability < 0.3
                    and visibility_info.observability_score > 0.8
                    and visibility_explanations
                ):
                    html_parts.append(
                        f"<p style='margin-left: 20px; margin-top: 10px; margin-bottom: 5px; "
                        f"color: {colors['text_dim']}; font-style: italic;'>Why chance is low:</p>"
                    )
                    for explanation in visibility_explanations:
                        html_parts.append(
                            f"<p style='margin-left: 40px; margin-top: 2px; margin-bottom: 2px; "
                            f"color: {colors['text_dim']};'>• {explanation}</p>"
                        )

            # Reasons for not being visible
            if visibility_info.reasons:
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 10px; margin-bottom: 5px; "
                    f"color: {colors['text_dim']}; font-style: italic;'>Details:</p>"
                )
                for reason in visibility_info.reasons:
                    html_parts.append(
                        f"<p style='margin-left: 40px; margin-top: 2px; margin-bottom: 2px; "
                        f"color: {colors['text_dim']};'>• {reason}</p>"
                    )

            # Moons (if this is a planet)
            if obj.object_type == CelestialObjectType.PLANET.value:
                try:
                    from celestron_nexstar.api.database.database import get_database

                    db = get_database()
                    moons = asyncio.run(db.get_moons_by_parent_planet(obj.name))
                    if moons:
                        html_parts.append(
                            f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>Moons:</p>"
                        )
                        for moon in moons:
                            mag_str = f" (mag {moon.magnitude:.2f})" if moon.magnitude else ""
                            html_parts.append(
                                f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>"
                                f"• {moon.name}{mag_str}</p>"
                            )
                except Exception:
                    pass

            # Moon Phase Impact section (bold yellow header)
            try:
                from celestron_nexstar.api.astronomy.solar_system import get_moon_info
                from celestron_nexstar.api.location.observer import get_observer_location
                from celestron_nexstar.api.observation.planning_utils import get_moon_phase_impact

                location = get_observer_location()
                if location:
                    moon_info = get_moon_info(location.latitude, location.longitude)
                    if moon_info:
                        moon_phase = moon_info.phase_name if moon_info else None
                        moon_illum = moon_info.illumination if moon_info else None

                        impact = get_moon_phase_impact(obj.object_type.value, moon_phase, moon_illum)

                        html_parts.append(
                            f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>Moon Phase Impact:</p>"
                        )

                        # Current moon phase and illumination
                        if moon_info.phase_name:
                            phase_name = (
                                moon_info.phase_name.value
                                if hasattr(moon_info.phase_name, "value")
                                else str(moon_info.phase_name)
                            )
                            html_parts.append(
                                f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>"
                                f"Current moon phase: <span style='color: {colors['cyan']};'>{phase_name}</span></p>"
                            )
                        if moon_info.illumination is not None:
                            html_parts.append(
                                f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>"
                                f"Moon illumination: <span style='color: {colors['cyan']};'>{moon_info.illumination * 100:.0f}%</span></p>"
                            )

                        # Impact level with color coding
                        impact_level = impact.get("impact_level", "unknown")
                        if impact_level == "none" or impact_level == "minimal":
                            impact_color = colors["green"]
                        elif impact_level == "moderate":
                            impact_color = colors["yellow"]
                        elif impact_level == "significant" or impact_level == "severe":
                            impact_color = colors["red"]
                        else:
                            impact_color = colors["text_dim"]

                        html_parts.append(
                            f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>"
                            f"Impact level: <span style='color: {impact_color}; font-weight: bold;'>{impact_level.title()}</span></p>"
                        )

                        # Recommended
                        recommended = impact.get("recommended", True)
                        rec_color = colors["green"] if recommended else colors["red"]
                        rec_text = "Yes" if recommended else "No"
                        html_parts.append(
                            f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>"
                            f"Recommended: <span style='color: {rec_color}; font-weight: bold;'>{rec_text}</span></p>"
                        )

                        # Notes
                        notes = impact.get("notes", [])
                        if notes and isinstance(notes, list):
                            html_parts.append(
                                f"<p style='margin-left: 20px; margin-top: 10px; margin-bottom: 5px; "
                                f"color: {colors['text_dim']}; font-style: italic;'>Notes:</p>"
                            )
                            for note in notes:
                                html_parts.append(
                                    f"<p style='margin-left: 40px; margin-top: 2px; margin-bottom: 2px; "
                                    f"color: {colors['text_dim']};'>• {note}</p>"
                                )
            except Exception as e:
                logger.debug(f"Error loading moon impact info: {e}")

            # Visibility Timeline section (bold yellow header)
            try:
                from celestron_nexstar.api.core.utils import format_local_time
                from celestron_nexstar.api.location.observer import get_observer_location
                from celestron_nexstar.api.observation.planning_utils import get_object_visibility_timeline
                from celestron_nexstar.api.observation.visibility import get_object_altitude_azimuth

                location = get_observer_location()
                if location:
                    timeline = get_object_visibility_timeline(obj, location.latitude, location.longitude, days=1)

                    html_parts.append(
                        f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>Visibility Timeline:</p>"
                    )

                    if timeline.is_never_visible:
                        html_parts.append(
                            "<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px; "
                            f"color: {colors['yellow']};'>This object is never visible from your location.</p>"
                        )
                    elif timeline.is_always_visible:
                        html_parts.append(
                            "<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px; "
                            f"color: {colors['green']};'>This object is always visible (circumpolar).</p>"
                        )
                        if timeline.transit_time:
                            time_str = format_local_time(timeline.transit_time, location.latitude, location.longitude)
                            html_parts.append(
                                f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>"
                                f"Transit (highest): <span style='color: {colors['cyan']};'>{time_str}</span></p>"
                            )
                            html_parts.append(
                                f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>"
                                f"Maximum altitude: <span style='color: {colors['green']};'>{timeline.max_altitude:.1f}°</span></p>"
                            )
                    else:
                        # Show rise, transit, and set times
                        # Always show transit if available (even for circumpolar objects that aren't marked as always_visible)
                        if timeline.transit_time:
                            time_str = format_local_time(timeline.transit_time, location.latitude, location.longitude)
                            html_parts.append(
                                f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>"
                                f"<span style='color: {colors['cyan']};'>Transit (Highest):</span> <span style='color: {colors['text']};'>{time_str}</span> "
                                f"<span style='color: {colors['green']};'>({timeline.max_altitude:.1f}°)</span></p>"
                            )

                        if timeline.rise_time:
                            time_str = format_local_time(timeline.rise_time, location.latitude, location.longitude)
                            alt, _ = get_object_altitude_azimuth(
                                obj, location.latitude, location.longitude, timeline.rise_time
                            )
                            html_parts.append(
                                f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>"
                                f"<span style='color: {colors['cyan']};'>Rise:</span> <span style='color: {colors['text']};'>{time_str}</span> "
                                f"<span style='color: {colors['text_dim']};'>({alt:.1f}°)</span></p>"
                            )

                        if timeline.set_time:
                            time_str = format_local_time(timeline.set_time, location.latitude, location.longitude)
                            alt, _ = get_object_altitude_azimuth(
                                obj, location.latitude, location.longitude, timeline.set_time
                            )
                            html_parts.append(
                                f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>"
                                f"<span style='color: {colors['cyan']};'>Set:</span> <span style='color: {colors['text']};'>{time_str}</span> "
                                f"<span style='color: {colors['text_dim']};'>({alt:.1f}°)</span></p>"
                            )
            except Exception as e:
                logger.error(f"Error loading timeline info: {e}", exc_info=True)

            # Description
            if obj.description:
                colors = self._get_theme_colors()
                html_parts.append(
                    f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>Description:</p>"
                )
                # Format description (preserve line breaks)
                formatted_desc = obj.description.replace("\n", "<br>")
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px; "
                    f"line-height: 1.5;'>{formatted_desc}</p>"
                )

            # Set HTML content
            html_content = "".join(html_parts)
            self.info_text.setHtml(html_content)

        except Exception as e:
            logger.error(f"Error loading object info for '{self.object_name}': {e}", exc_info=True)
            colors = self._get_theme_colors()
            self.info_text.setHtml(
                f"<p style='color: {colors['error']};'><b>Error:</b> Failed to load object information: {e}</p>"
            )
