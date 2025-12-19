"""
Dialog to display detailed information about a celestial object.
"""

import base64
import io
import logging
import re
from typing import TYPE_CHECKING, Any, cast

from PySide6.QtCore import QThread, Signal, Slot, Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from celestron_nexstar.api.favorites import add_favorite, is_favorite, remove_favorite


if TYPE_CHECKING:
    from celestron_nexstar.api.catalogs.catalogs import CelestialObject


logger = logging.getLogger(__name__)


class DSOMapWorker(QThread):
    """Background worker to generate a starplot map for DSOs."""

    map_ready = Signal(bytes)
    error = Signal(str)

    def __init__(self, ra_hours: float, dec_degrees: float, is_dark: bool) -> None:
        super().__init__()
        self.ra_hours = ra_hours
        self.dec_degrees = dec_degrees
        self.is_dark = is_dark

    def run(self) -> None:
        try:
            from starplot import LambertAzEqArea, MapPlot, _  # type: ignore[import-untyped]
            from starplot.styles import PlotStyle, extensions  # type: ignore[import-untyped]

            # Build style
            if self.is_dark:
                plot_style = PlotStyle().extend(extensions.BLUE_DARK, extensions.MAP)
            else:
                plot_style = PlotStyle().extend(extensions.BLUE_LIGHT, extensions.MAP)

            # Center on object; small FoV for context using MapPlot's RA/Dec bounds
            ra_deg = (self.ra_hours * 15.0) % 360.0
            dec_deg = float(self.dec_degrees)
            fov_deg = 12.0

            # Clamp declination and build a tight window
            dec_min = max(-90.0, dec_deg - fov_deg / 2.0)
            dec_max = min(90.0, dec_deg + fov_deg / 2.0)

            # Keep RA span narrow and normalized
            ra_min = ra_deg - fov_deg / 2.0
            ra_max = ra_deg + fov_deg / 2.0
            while ra_min < 0.0:
                ra_min += 360.0
                ra_max += 360.0
            while ra_min >= 360.0:
                ra_min -= 360.0
                ra_max -= 360.0
            if ra_max <= ra_min:
                ra_max = ra_min + fov_deg

            projection = LambertAzEqArea(center_ra=ra_deg, center_dec=dec_deg)
            plot = MapPlot(
                projection=projection,
                ra_min=ra_min,
                ra_max=ra_max,
                dec_min=dec_min,
                dec_max=dec_max,
                style=plot_style,
                resolution=2200,
                autoscale=False,
                scale=1.1,
            )

            # Add sky context: constellations + DSOs around the target
            plot.gridlines()
            plot.constellations()
            plot.constellation_borders()
            plot.stars(  # type: ignore[arg-type]
                where=[_.magnitude < 9],
                bayer_labels=True,
                flamsteed_labels=True,
            )
            plot.galaxies(where=[(_.magnitude.isnull()) | (_.magnitude < 12)])  # type: ignore[arg-type]
            plot.nebula(where=[(_.magnitude.isnull()) | (_.magnitude < 12)], true_size=True)  # type: ignore[arg-type]
            plot.open_clusters(  # type: ignore[arg-type]
                where=[(_.magnitude.isnull()) | (_.magnitude < 11)],
                true_size=False,
            )
            plot.globular_clusters(  # type: ignore[arg-type]
                where=[(_.magnitude.isnull()) | (_.magnitude < 11)],
                true_size=True,
            )

            fig = plot.fig
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
            buf.seek(0)
            self.map_ready.emit(buf.read())
        except Exception as e:
            self.error.emit(str(e))


class ObjectInfoDialog(QDialog):
    """Dialog to display detailed information about a celestial object."""

    def __init__(self, parent: QWidget | None, object_name: str) -> None:
        """Initialize the object info dialog."""
        super().__init__(parent)
        self.setWindowTitle(f"Object Information: {object_name}")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        self.resize(600, 700)  # Default width for all info dialogs

        self.object_name = object_name
        self.object_type: str | None = None  # Will be set when object info is loaded
        self.object_ra_hours: float | None = None  # Will be set when object info is loaded
        self.object_dec_degrees: float | None = None  # Will be set when object info is loaded
        self.object: CelestialObject | None = None  # Will be set when object info is loaded
        self._dso_map_worker: DSOMapWorker | None = None
        self._dso_map_placeholder_id = "dso-map-placeholder"
        self._dso_map_placeholder = (
            f"<p id='{self._dso_map_placeholder_id}' style='margin-left:20px; color: #888;'>"
            "Generating finder map…</p>"
        )

        # Create layout
        layout = QVBoxLayout(self)

        # Create scrollable text area with rich HTML formatting
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setAcceptRichText(True)
        # Only show scrollbars when needed; avoid always-on bar
        self.info_text.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.info_text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.info_text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        layout.addWidget(self.info_text)

        # Add button box with favorite toggle
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)

        # Add Optic Plot button (to the left of favorite button)
        self.optic_plot_button = button_box.addButton("Optic Plot", QDialogButtonBox.ButtonRole.ActionRole)
        self.optic_plot_button.clicked.connect(self._on_optic_plot_clicked)
        self.optic_plot_button.setToolTip("Generate optic plot showing what you'll see through your telescope")
        # Will be enabled/disabled after checking configuration

        # Add favorite/unfavorite button
        self.favorite_button = button_box.addButton("", QDialogButtonBox.ButtonRole.ActionRole)
        self.favorite_button.setCheckable(True)
        self.favorite_button.clicked.connect(self._on_favorite_toggled)
        # Will be updated after object info is loaded

        # Add "Add to Goto Queue" button (to the right of favorite button)
        self.add_to_queue_button = button_box.addButton("Add to Queue", QDialogButtonBox.ButtonRole.ActionRole)
        self.add_to_queue_button.clicked.connect(self._on_add_to_queue_clicked)
        self.add_to_queue_button.setToolTip("Add this object to the goto queue")

        layout.addWidget(button_box)

        # Load object information (this will also update favorite button)
        self._load_object_info()

        # Update favorite button and check optic plot button state after object info is loaded
        # Use QTimer to ensure it runs after the dialog is shown
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, self._update_favorite_button)
        QTimer.singleShot(0, self._update_optic_plot_button)

        # Update favorite button after object info is loaded
        # Use a timer to ensure object info is loaded first
        from PySide6.QtCore import QTimer

        QTimer.singleShot(100, self._update_favorite_button)

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

    def _format_altitude_user_friendly(self, altitude_deg: float) -> str:
        """Format altitude with user-friendly description and explanation."""
        from celestron_nexstar.api.telescope.compass import format_altitude_description

        alt_desc = format_altitude_description(altitude_deg)

        # Add helpful explanation for common angles
        if altitude_deg < 0:
            return f"{altitude_deg:.1f}° (below horizon - not visible)"
        elif altitude_deg < 10:
            return f"{altitude_deg:.1f}° ({alt_desc} - about the width of your fist at arm's length)"
        elif altitude_deg < 20:
            return f"{altitude_deg:.1f}° ({alt_desc} - about two fists at arm's length)"
        elif altitude_deg < 40:
            return f"{altitude_deg:.1f}° ({alt_desc} - about four fists at arm's length)"
        elif altitude_deg < 50:
            return f"{altitude_deg:.1f}° ({alt_desc} - halfway between horizon and overhead)"
        elif altitude_deg < 80:
            return f"{altitude_deg:.1f}° ({alt_desc})"
        else:
            return f"{altitude_deg:.1f}° ({alt_desc} - almost directly above you)"

    def _explain_magnitude(self, magnitude: float) -> str:
        """Provide user-friendly explanation of magnitude value."""
        if magnitude < -1:
            return "very bright - easily visible"
        elif magnitude < 0:
            return "extremely bright"
        elif magnitude < 1:
            return "very bright"
        elif magnitude < 2:
            return "bright"
        elif magnitude < 3:
            return "moderately bright"
        elif magnitude < 4:
            return "visible to naked eye"
        elif magnitude < 5:
            return "visible under dark skies"
        elif magnitude < 6:
            return "visible under very dark skies"
        elif magnitude < 8:
            return "binoculars or small telescope needed"
        elif magnitude < 10:
            return "telescope required"
        elif magnitude < 12:
            return "large telescope needed"
        else:
            return "very faint - requires large telescope"

    def _explain_limiting_magnitude(self, limiting_mag: float, object_mag: float | None) -> str:
        """Explain limiting magnitude and whether object is visible."""
        if object_mag is None:
            return f"(you can see objects down to magnitude {limiting_mag:.2f})"

        if object_mag <= limiting_mag:
            return f"(object at {object_mag:.2f} should be visible)"
        else:
            diff = object_mag - limiting_mag
            return f"(object at {object_mag:.2f} is {diff:.2f} magnitudes too faint to see)"

    def _load_object_info(self) -> None:
        """Load object information from the API."""
        colors = self._get_theme_colors()
        try:
            from celestron_nexstar.api.catalogs.catalogs import get_object_by_name
            from celestron_nexstar.api.core.enums import CelestialObjectType
            from celestron_nexstar.api.core.utils import format_dec, format_ra
            from celestron_nexstar.api.observation.visibility import assess_visibility

            # Get object by name
            matches = get_object_by_name(self.object_name)

            if not matches:
                self.info_text.setHtml(
                    f"<p style='color: {colors['error']};'><b>Error:</b> Object '{self.object_name}' not found</p>"
                )
                return

            # Use first match (in GUI, we should have exact match from table)
            obj = matches[0]

            # Store object for later use (e.g., adding to goto queue)
            self.object = obj

            # Store object coordinates for optic plot
            self.object_ra_hours = obj.ra_hours
            self.object_dec_degrees = obj.dec_degrees

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
                # Add user-friendly magnitude explanation
                mag_explanation = self._explain_magnitude(obj.magnitude)
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>"
                    f"Magnitude: {obj.magnitude:.2f} <span style='color: {colors['text_dim']}; font-size: 0.9em;'>({mag_explanation})</span></p>"
                )
            # Display constellation for stars and other objects that have constellation data
            if obj.constellation:
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>"
                    f"Constellation: <span style='color: {colors['cyan']};'>{obj.constellation}</span></p>"
                )
                # For stars, also show asterism (if any) directly under constellation
                if obj.object_type.value == "star":
                    asterism_text = (
                        f"<span style='color: {colors['cyan']};'>{obj.asterism}</span>"
                        if obj.asterism
                        else f"<span style='color: {colors['text_dim']};'>—</span>"
                    )
                    html_parts.append(
                        f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>"
                        f"Asterism: {asterism_text}</p>"
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
                # Add user-friendly altitude description
                alt_desc = self._format_altitude_user_friendly(visibility_info.altitude_deg)
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>Altitude: {alt_desc}</p>"
                )
            if visibility_info.azimuth_deg is not None:
                direction = self._get_azimuth_direction(visibility_info.azimuth_deg)
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>"
                    f"Azimuth: {visibility_info.azimuth_deg:.1f}° ({direction})</p>"
                )
            if visibility_info.limiting_magnitude is not None:
                # Add explanation for limiting magnitude
                mag_explanation = self._explain_limiting_magnitude(visibility_info.limiting_magnitude, obj.magnitude)
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>"
                    f"Limiting Magnitude: {visibility_info.limiting_magnitude:.2f} {mag_explanation}</p>"
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
                    moons = db.get_moons_by_parent_planet(obj.name)
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

            # Component Stars (if this is a double star)
            if obj.object_type == CelestialObjectType.DOUBLE_STAR.value:
                try:
                    from celestron_nexstar.api.database.database import get_database

                    db = get_database()
                    # Determine search radius: use separation if available (size_arcmin), otherwise default to 2 arcmin
                    size_arcmin = getattr(obj, "size_arcmin", None)
                    search_radius = (
                        float(size_arcmin) if isinstance(size_arcmin, (int, float)) and size_arcmin > 0 else 2.0
                    )
                    # Cap at 5 arcmin to avoid too many results
                    search_radius = min(search_radius, 5.0)

                    # Search for stars near the double star position
                    nearby_objects = db.search_by_coordinates(
                        obj.ra_hours, obj.dec_degrees, radius_arcmin=search_radius, limit=10
                    )

                    # Filter to only stars (exclude the double star itself and other object types)
                    component_stars = []
                    for nearby_obj, separation_arcmin in nearby_objects:
                        if (
                            nearby_obj.object_type == CelestialObjectType.STAR.value
                            and nearby_obj.name != obj.name
                            and nearby_obj.catalog != "wds"  # Exclude other double stars
                        ):
                            component_stars.append((nearby_obj, separation_arcmin))

                    # Sort by separation (closest first)
                    component_stars.sort(key=lambda x: x[1])

                    if component_stars:
                        html_parts.append(
                            f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>Component Stars:</p>"
                        )
                        for star, separation_arcmin in component_stars[:5]:  # Show up to 5 closest stars
                            mag_str = f" (mag {star.magnitude:.2f})" if star.magnitude else ""
                            sep_str = (
                                f" - {separation_arcmin:.2f}' away"
                                if separation_arcmin < 1.0
                                else f" - {separation_arcmin:.1f}' away"
                            )
                            display_name = star.common_name if star.common_name else star.name
                            html_parts.append(
                                f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>"
                                f"• {display_name}{mag_str}<span style='color: {colors['text_dim']};'>{sep_str}</span></p>"
                            )
                        if len(component_stars) > 5:
                            html_parts.append(
                                f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px; "
                                f"color: {colors['text_dim']}; font-style: italic;'>"
                                f"... and {len(component_stars) - 5} more nearby star(s)</p>"
                            )
                    else:
                        # If no stars found, show a note
                        html_parts.append(
                            f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>Component Stars:</p>"
                        )
                        html_parts.append(
                            f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px; "
                            f"color: {colors['text_dim']}; font-style: italic;'>"
                            f"No component stars found in database within {search_radius:.1f}'</p>"
                        )
                except Exception as e:
                    logger.debug(f"Error loading component stars for double star: {e}", exc_info=True)
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

                            # Check if transit is during daytime (object won't be visible)
                            is_daytime_at_transit = False
                            try:
                                from celestron_nexstar.api.astronomy.solar_system import get_sun_info

                                sun_info = get_sun_info(location.latitude, location.longitude, timeline.transit_time)
                                if sun_info:
                                    is_daytime_at_transit = sun_info.is_daytime
                            except Exception:
                                pass

                            transit_warning = (
                                " <span style='color: {warn_color}; font-style: italic;'>(Daytime - not visible)</span>".format(
                                    warn_color=colors["yellow"]
                                )
                                if is_daytime_at_transit
                                else ""
                            )

                            html_parts.append(
                                f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>"
                                f"Transit (highest): <span style='color: {colors['cyan']};'>{time_str}</span>{transit_warning}</p>"
                            )
                            transit_color = colors["yellow"] if is_daytime_at_transit else colors["green"]
                            html_parts.append(
                                f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>"
                                f"Maximum altitude: <span style='color: {transit_color};'>{timeline.max_altitude:.1f}°</span></p>"
                            )
                    else:
                        # Show rise, transit, and set times
                        # Always show transit if available (even for circumpolar objects that aren't marked as always_visible)
                        if timeline.transit_time:
                            time_str = format_local_time(timeline.transit_time, location.latitude, location.longitude)

                            # Check if transit is during daytime (object won't be visible)
                            is_daytime_at_transit = False
                            try:
                                from celestron_nexstar.api.astronomy.solar_system import get_sun_info

                                sun_info = get_sun_info(location.latitude, location.longitude, timeline.transit_time)
                                if sun_info:
                                    is_daytime_at_transit = sun_info.is_daytime
                            except Exception:
                                pass

                            transit_color = colors["yellow"] if is_daytime_at_transit else colors["green"]
                            transit_warning = (
                                " <span style='color: {warn_color}; font-style: italic;'>(Daytime - not visible)</span>".format(
                                    warn_color=colors["yellow"]
                                )
                                if is_daytime_at_transit
                                else ""
                            )

                            html_parts.append(
                                f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>"
                                f"<span style='color: {colors['cyan']};'>Transit (Highest):</span> <span style='color: {colors['text']};'>{time_str}</span> "
                                f"<span style='color: {transit_color};'>({timeline.max_altitude:.1f}°)</span>{transit_warning}</p>"
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

            # Start DSO map worker for galaxies/nebulae/clusters if coordinates available
            if obj.object_type.value in {"galaxy", "nebula", "cluster"} and (
                obj.ra_hours is not None and obj.dec_degrees is not None
            ):
                # Insert placeholder into the existing HTML
                map_header = (
                    f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>"
                    "Finder Map:</p>"
                )
                html_with_placeholder = html_content + map_header + self._dso_map_placeholder
                self.info_text.setHtml(html_with_placeholder)
                self._start_dso_map_worker(obj.ra_hours, obj.dec_degrees)

            # Store object type for favorite button
            if hasattr(obj, "object_type") and obj.object_type:
                self.object_type = obj.object_type.value
            else:
                self.object_type = None

        except Exception as e:
            logger.error(f"Error loading object info for '{self.object_name}': {e}", exc_info=True)
            colors = self._get_theme_colors()
            self.info_text.setHtml(
                f"<p style='color: {colors['error']};'><b>Error:</b> Failed to load object information: {e}</p>"
            )
            self.object_type = None

        # Update favorite button and optic plot button after loading
        self._update_favorite_button()
        self._update_optic_plot_button()

    def _start_dso_map_worker(self, ra_hours: float, dec_degrees: float) -> None:
        """Start background worker to generate DSO map."""
        self._stop_dso_map_worker()
        worker = DSOMapWorker(ra_hours=ra_hours, dec_degrees=dec_degrees, is_dark=self._is_dark_theme())
        worker.map_ready.connect(self._on_dso_map_ready)
        worker.error.connect(self._on_dso_map_error)
        self._dso_map_worker = worker
        worker.start()

    def _stop_dso_map_worker(self) -> None:
        """Stop DSO map worker if running."""
        if self._dso_map_worker is not None:
            try:
                if self._dso_map_worker.isRunning():
                    self._dso_map_worker.requestInterruption()
                    self._dso_map_worker.quit()
                    self._dso_map_worker.wait(2000)
            except Exception:
                pass
            self._dso_map_worker = None

    def closeEvent(self, event: Any) -> None:  # noqa: N802
        """Ensure background worker is stopped on close."""
        self._stop_dso_map_worker()
        super().closeEvent(event)

    @Slot(bytes)
    def _on_dso_map_ready(self, png_data: bytes) -> None:
        """Replace placeholder with generated map."""
        try:
            png_b64 = base64.b64encode(png_data).decode("ascii")
            img_html = (
                f"<div id='{self._dso_map_placeholder_id}_container' style='margin-left: 10px; margin-top: 5px;'>"
                f"<img src='data:image/png;base64,{png_b64}' "
                f"style='max-width: 100%; max-height: 420px; border: 1px solid #555; border-radius: 6px;'/>"
                "</div>"
                f"<p style='margin-left: 10px; font-size: 0.9em; color: #888;'>"
                "Finder map generated with starplot</p>"
            )
            html = self.info_text.toHtml()
            pattern = re.compile(
                r"<p[^>]*id=['\"]" + re.escape(self._dso_map_placeholder_id) + r"['\"][^>]*>.*?</p>",
                re.DOTALL,
            )
            if pattern.search(html):
                html = pattern.sub(img_html, html, count=1)
            else:
                html += img_html
            self.info_text.setHtml(html)
        except Exception as e:
            logger.error(f"Error updating DSO map: {e}", exc_info=True)

    @Slot(str)
    def _on_dso_map_error(self, error: str) -> None:
        """Show error in placeholder."""
        colors = self._get_theme_colors()
        err_html = (
            f"<p id='{self._dso_map_placeholder_id}' style='margin-left:20px; color: {colors['error']};'>"
            f"Error generating finder map: {error}</p>"
        )
        html = self.info_text.toHtml()
        pattern = re.compile(
            r"<p[^>]*id=['\"]" + re.escape(self._dso_map_placeholder_id) + r"['\"][^>]*>.*?</p>",
            re.DOTALL,
        )
        if pattern.search(html):
            html = pattern.sub(err_html, html, count=1)
        else:
            html += err_html
        self.info_text.setHtml(html)

    def _update_favorite_button(self) -> None:
        """Update the favorite button state and icon."""
        try:
            is_fav = is_favorite(self.object_name)
            self.favorite_button.setChecked(is_fav)

            # Set button text and tooltip
            if is_fav:
                self.favorite_button.setText("★ Unfavorite")
                self.favorite_button.setToolTip("Remove from favorites")
            else:
                self.favorite_button.setText("☆ Favorite")
                self.favorite_button.setToolTip("Add to favorites")
        except Exception as e:
            logger.error(f"Error updating favorite button: {e}", exc_info=True)

    def _update_optic_plot_button(self) -> None:
        """Update the optic plot button state based on configuration and object coordinates."""
        try:
            from celestron_nexstar.api.observation.optics import load_configuration

            # Check if telescope/eyepiece is configured
            config = load_configuration()
            has_config = config is not None

            # Check if object has coordinates
            has_coordinates = self.object_ra_hours is not None and self.object_dec_degrees is not None

            # Enable button only if both config and coordinates are available
            self.optic_plot_button.setEnabled(has_config and has_coordinates)

            if not has_config:
                self.optic_plot_button.setToolTip("Configure telescope and eyepiece in Settings to enable optic plots")
            elif not has_coordinates:
                self.optic_plot_button.setToolTip("Object does not have coordinates")
            else:
                self.optic_plot_button.setToolTip("Generate optic plot showing what you'll see through your telescope")
        except Exception as e:
            logger.error(f"Error updating optic plot button: {e}", exc_info=True)
            self.optic_plot_button.setEnabled(False)

    def _on_optic_plot_clicked(self) -> None:
        """Handle optic plot button click - open optic plot window."""
        try:
            if self.object_ra_hours is None or self.object_dec_degrees is None:
                logger.warning("Cannot generate optic plot: object has no coordinates")
                return

            from celestron_nexstar.gui.windows.optic_plot_window import OpticPlotWindow

            dialog = OpticPlotWindow(
                self,
                object_name=self.object_name,
                object_type=self.object_type,
                ra_hours=self.object_ra_hours,
                dec_degrees=self.object_dec_degrees,
            )
            dialog.exec()
        except Exception as e:
            logger.error(f"Error opening optic plot: {e}", exc_info=True)

    def _on_favorite_toggled(self) -> None:
        """Handle favorite button toggle."""
        try:
            is_checked = self.favorite_button.isChecked()

            if is_checked:
                # Add to favorites
                success = add_favorite(self.object_name, self.object_type)
                if success:
                    self._update_favorite_button()
            else:
                # Remove from favorites
                success = remove_favorite(self.object_name)
                if success:
                    self._update_favorite_button()
        except Exception as e:
            logger.error(f"Error toggling favorite: {e}", exc_info=True)
            # Reset button state on error
            self._update_favorite_button()

    def _on_add_to_queue_clicked(self) -> None:
        """Handle add to goto queue button click."""
        if not self.object:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "No Object", "Object information not loaded yet.")
            return

        try:
            # Get the main window from parent
            from PySide6.QtCore import QObject
            from PySide6.QtWidgets import QMessageBox

            main_window: QObject | None = self.parent()
            # Traverse up the parent chain to find MainWindow-like object
            while main_window is not None:
                if hasattr(main_window, "_on_goto_queue"):
                    break
                main_window = main_window.parent() if hasattr(main_window, "parent") else None

            if main_window is None:
                QMessageBox.warning(self, "Error", "Could not find main window.")
                return
            host = cast(Any, main_window)

            # Create or get goto queue window (silently, without showing it)
            if not hasattr(host, "_goto_queue_window") or host._goto_queue_window is None:
                from celestron_nexstar.gui.windows.goto_queue_window import GotoQueueWindow

                host._goto_queue_window = GotoQueueWindow(
                    host, telescope=host.telescope if hasattr(host, "telescope") else None
                )
                host._goto_queue_window.destroyed.connect(lambda: setattr(host, "_goto_queue_window", None))

            # Add object to queue
            if host._goto_queue_window is not None:
                # Update telescope reference if needed
                if hasattr(host, "telescope") and host._goto_queue_window.telescope != host.telescope:
                    host._goto_queue_window.telescope = host.telescope

                # Update object position for dynamic objects
                updated_obj = self.object.with_current_position()
                host._goto_queue_window.add_object(updated_obj)

                # Just show a confirmation message - don't open the window
                display_name = updated_obj.common_name or updated_obj.name
                QMessageBox.information(self, "Added to Queue", f"'{display_name}' has been added to the goto queue.")
            else:
                QMessageBox.warning(self, "Error", "Could not open goto queue window.")
        except Exception as e:
            logger.error(f"Error adding object to queue: {e}", exc_info=True)
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "Error", f"Failed to add object to queue: {e}")
