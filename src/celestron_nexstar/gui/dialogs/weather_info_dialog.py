"""
Dialog to display current weather information.
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


class WeatherInfoDialog(QDialog):
    """Dialog to display current weather information."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the weather info dialog."""
        super().__init__(parent)
        self.setWindowTitle("Current Weather")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)

        # Create layout
        layout = QVBoxLayout(self)

        # Create scrollable text area with rich HTML formatting
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setAcceptRichText(True)

        # Get monospace font from application property, fallback to system fonts
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        monospace_font = "JetBrains Mono" if app and app.property("monospace_font") else None
        font_family = (
            f"'{monospace_font}', 'Courier New', 'Consolas', 'Monaco', 'Menlo', monospace"
            if monospace_font
            else "'Courier New', 'Consolas', 'Monaco', 'Menlo', monospace"
        )

        self.info_text.setStyleSheet(
            f"""
            QTextEdit {{
                font-family: {font_family};
                background-color: transparent;
                border: none;
            }}
            h2 {{
                color: #ffc107; /* Yellow for headers */
                margin-top: 1em;
                margin-bottom: 0.5em;
            }}
            .location {{
                color: #00bcd4; /* Cyan for location */
                font-size: 14pt;
                font-weight: bold;
            }}
            .status_excellent {{ color: #4caf50; font-weight: bold; }} /* Green */
            .status_good {{ color: #00bcd4; font-weight: bold; }} /* Cyan */
            .status_fair {{ color: #ffc107; font-weight: bold; }} /* Yellow */
            .status_poor {{ color: #f44336; font-weight: bold; }} /* Red */
            .detail_label {{ color: #9e9e9e; }} /* Dim gray */
            .detail_value {{ color: #ffffff; }} /* White */
            .green_text {{ color: #4caf50; }}
            .yellow_text {{ color: #ffc107; }}
            .red_text {{ color: #f44336; }}
            .dim_text {{ color: #9e9e9e; }}
        """
        )
        layout.addWidget(self.info_text)

        # Add button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        # Load weather information
        self._load_weather_info()

    def _load_weather_info(self) -> None:
        """Load weather information from the API and format it for display."""
        try:
            from celestron_nexstar.api.location.observer import get_observer_location
            from celestron_nexstar.api.location.weather import (
                assess_observing_conditions,
                calculate_seeing_conditions,
                fetch_weather,
            )

            # Get location and weather
            location = get_observer_location()
            weather = asyncio.run(fetch_weather(location))

            # Build HTML content with inline styles for colors
            html_content = []
            html_content.append("""
            <style>
                h2 { color: #ffc107; margin-top: 1em; margin-bottom: 0.5em; }
            </style>
            """)

            # Location header (cyan)
            location_name = location.name or f"{location.latitude:.4f}°, {location.longitude:.4f}°"
            html_content.append(
                f"<p><span style='color: #00bcd4; font-size: 14pt; font-weight: bold;'>Current Weather: {location_name}</span></p>"
            )
            html_content.append("<br>")

            if weather.error:
                html_content.append(
                    f"<p><span style='color: #f44336;'><b>Error:</b> Weather data unavailable: {weather.error}</span></p>"
                )
                self.info_text.setHtml("\n".join(html_content))
                return

            # Weather parameters
            html_content.append("<h2>Weather Conditions</h2>")

            # Temperature (cyan label, green value)
            if weather.temperature_c is not None:
                html_content.append(
                    f"<p><span style='color: #00bcd4;'>Temperature:</span> <span style='color: #4caf50;'>{weather.temperature_c:.1f}°F</span></p>"
                )

            # Dew Point (cyan label, white value)
            if weather.dew_point_f is not None:
                html_content.append(
                    f"<p><span style='color: #00bcd4;'>Dew Point:</span> <span style='color: #ffffff;'>{weather.dew_point_f:.1f}°F</span></p>"
                )

            # Humidity (cyan label, white value)
            if weather.humidity_percent is not None:
                html_content.append(
                    f"<p><span style='color: #00bcd4;'>Humidity:</span> <span style='color: #ffffff;'>{weather.humidity_percent:.0f}%</span></p>"
                )

            # Cloud Cover (cyan label, conditional value color)
            if weather.cloud_cover_percent is not None:
                cloud_cover = weather.cloud_cover_percent
                if cloud_cover < 20:
                    cloud_color = "#4caf50"  # Green
                    cloud_desc = "Clear"
                elif cloud_cover < 50:
                    cloud_color = "#ffc107"  # Yellow
                    cloud_desc = "Partly Cloudy"
                elif cloud_cover < 80:
                    cloud_color = "#ffc107"  # Yellow
                    cloud_desc = "Mostly Cloudy"
                else:
                    cloud_color = "#f44336"  # Red
                    cloud_desc = "Overcast"
                html_content.append(
                    f"<p><span style='color: #00bcd4;'>Cloud Cover:</span> <span style='color: {cloud_color};'>{cloud_cover:.0f}% ({cloud_desc})</span></p>"
                )

            # Wind Speed (cyan label, conditional value color)
            if weather.wind_speed_ms is not None:
                wind_mph = weather.wind_speed_ms  # Already in mph
                if wind_mph < 10:
                    wind_color = "#4caf50"  # Green
                    wind_desc = "Calm"
                elif wind_mph < 20:
                    wind_color = "#ffc107"  # Yellow
                    wind_desc = "Moderate"
                else:
                    wind_color = "#f44336"  # Red
                    wind_desc = "Strong"
                html_content.append(
                    f"<p><span style='color: #00bcd4;'>Wind Speed:</span> <span style='color: {wind_color};'>{wind_mph:.1f} mph ({wind_desc})</span></p>"
                )

            # Visibility (cyan label, white value)
            if weather.visibility_km is not None:
                visibility_mi = weather.visibility_km * 0.621371
                html_content.append(
                    f"<p><span style='color: #00bcd4;'>Visibility:</span> <span style='color: #ffffff;'>{visibility_mi:.1f} mi</span></p>"
                )

            # Condition (cyan label, white value)
            if weather.condition:
                html_content.append(
                    f"<p><span style='color: #00bcd4;'>Condition:</span> <span style='color: #ffffff;'>{weather.condition}</span></p>"
                )

            # Last Updated (cyan label, dim value)
            if weather.last_updated:
                html_content.append(
                    f"<p><span style='color: #00bcd4;'>Last Updated:</span> <span style='color: #9e9e9e;'>{weather.last_updated}</span></p>"
                )

            # Observing Conditions Assessment
            html_content.append("<br>")
            html_content.append("<h2>Observing Conditions</h2>")
            status, warning = assess_observing_conditions(weather)

            # Status indicator (matching CLI colors)
            if status == "excellent":
                status_color = "#4caf50"  # Green
                status_icon = "✓"
            elif status == "good":
                status_color = "#00bcd4"  # Cyan
                status_icon = "○"
            elif status == "fair":
                status_color = "#ffc107"  # Yellow
                status_icon = "⚠"
            else:  # poor
                status_color = "#f44336"  # Red
                status_icon = "✗"

            html_content.append(
                f"<p><b>Observing Conditions:</b> <span style='color: {status_color}; font-weight: bold;'>{status_icon} {status.title()}</span></p>"
            )
            if warning:
                html_content.append(f"<p style='color: #9e9e9e;'>{warning}</p>")

            # Seeing Conditions
            html_content.append("<br>")
            html_content.append("<h2>Seeing Conditions</h2>")
            seeing_score = calculate_seeing_conditions(weather)

            if seeing_score >= 80:
                seeing_color = "#4caf50"  # Green
                seeing_desc = "Excellent"
            elif seeing_score >= 60:
                seeing_color = "#ffc107"  # Yellow
                seeing_desc = "Good"
            elif seeing_score >= 40:
                seeing_color = "#ffc107"  # Yellow
                seeing_desc = "Fair"
            else:
                seeing_color = "#f44336"  # Red
                seeing_desc = "Poor"

            html_content.append(
                f"<p><b>Seeing Conditions:</b> <span style='color: {seeing_color};'>{seeing_desc}</span> ({seeing_score:.0f}/100)</p>"
            )
            html_content.append("<p style='color: #9e9e9e;'>Atmospheric steadiness for image sharpness</p>")

            self.info_text.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading weather info: {e}", exc_info=True)
            self.info_text.setHtml(
                f"<p><span style='color: #f44336;'><b>Error:</b> Failed to load weather information: {e}</span></p>"
            )
