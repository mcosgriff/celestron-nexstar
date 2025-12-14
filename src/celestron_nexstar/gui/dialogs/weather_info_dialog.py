"""
Dialog to display current weather information.
"""

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QTabWidget,
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
        self.resize(600, 700)  # Match ObjectInfoDialog width

        # Create layout
        layout = QVBoxLayout(self)

        # Create tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Create "Current" tab with text info
        current_tab = QWidget()
        current_layout = QVBoxLayout(current_tab)

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

        # Store font family for later use in _load_weather_info
        self._font_family = font_family

        # Set initial stylesheet (will be updated with theme colors in _load_weather_info)
        self.info_text.setStyleSheet(
            f"""
            QTextEdit {{
                font-family: {font_family};
                background-color: transparent;
                border: none;
            }}
        """
        )
        current_layout.addWidget(self.info_text)
        self.tab_widget.addTab(current_tab, "Current")

        # Create "Charts" tab
        charts_tab = QWidget()
        charts_layout = QVBoxLayout(charts_tab)
        charts_layout.setContentsMargins(0, 0, 0, 0)
        self.charts_widget = QWidget()
        charts_widget_layout = QVBoxLayout(self.charts_widget)
        charts_widget_layout.setContentsMargins(0, 0, 0, 0)
        charts_layout.addWidget(self.charts_widget)
        self.tab_widget.addTab(charts_tab, "Charts")

        # Add button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        # Load weather information (this will also update stylesheet with theme colors)
        self._load_weather_info()
        self._load_weather_charts()

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

    def _load_weather_info(self) -> None:
        """Load weather information from the API and format it for display."""
        colors = self._get_theme_colors()

        # Update stylesheet with theme-aware colors (even though HTML uses inline styles)
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
            .location {{
                color: {colors["cyan"]};
                font-size: 14pt;
                font-weight: bold;
            }}
            .status_excellent {{ color: {colors["green"]}; font-weight: bold; }}
            .status_good {{ color: {colors["cyan"]}; font-weight: bold; }}
            .status_fair {{ color: {colors["yellow"]}; font-weight: bold; }}
            .status_poor {{ color: {colors["red"]}; font-weight: bold; }}
            .detail_label {{ color: {colors["text_dim"]}; }}
            .detail_value {{ color: {colors["text"]}; }}
            .green_text {{ color: {colors["green"]}; }}
            .yellow_text {{ color: {colors["yellow"]}; }}
            .red_text {{ color: {colors["red"]}; }}
            .dim_text {{ color: {colors["text_dim"]}; }}
        """
        )

        try:
            from celestron_nexstar.api.location.observer import get_observer_location
            from celestron_nexstar.api.location.weather import (
                assess_observing_conditions,
                calculate_seeing_conditions,
                fetch_weather,
            )

            # Get location and weather
            location = get_observer_location()
            weather = fetch_weather(location)

            # Build HTML content with inline styles for colors
            html_content = []
            html_content.append(f"""
            <style>
                h2 {{ color: {colors["header"]}; margin-top: 1em; margin-bottom: 0.5em; }}
            </style>
            """)

            # Location header (cyan)
            location_name = location.name or f"{location.latitude:.4f}°, {location.longitude:.4f}°"
            html_content.append(
                f"<p><span style='color: {colors['cyan']}; font-size: 14pt; font-weight: bold;'>Current Weather: {location_name}</span></p>"
            )

            if weather.error:
                html_content.append(
                    f"<p><span style='color: {colors['error']};'><b>Error:</b> Weather data unavailable: {weather.error}</span></p>"
                )
                self.info_text.setHtml("\n".join(html_content))
                return

            # Weather parameters
            html_content.append("<h2>Weather Conditions</h2>")

            # Temperature (cyan label, green value)
            if weather.temperature_c is not None:
                html_content.append(
                    f"<p><span style='color: {colors['cyan']};'>Temperature:</span> <span style='color: {colors['green']};'>{weather.temperature_c:.1f}°F</span></p>"
                )

            # Dew Point (cyan label, white value)
            if weather.dew_point_f is not None:
                html_content.append(
                    f"<p><span style='color: {colors['cyan']};'>Dew Point:</span> <span style='color: {colors['text']};'>{weather.dew_point_f:.1f}°F</span></p>"
                )

            # Humidity (cyan label, white value)
            if weather.humidity_percent is not None:
                html_content.append(
                    f"<p><span style='color: {colors['cyan']};'>Humidity:</span> <span style='color: {colors['text']};'>{weather.humidity_percent:.0f}%</span></p>"
                )

            # Cloud Cover (cyan label, conditional value color)
            if weather.cloud_cover_percent is not None:
                cloud_cover = weather.cloud_cover_percent
                if cloud_cover < 20:
                    cloud_color = colors["green"]
                    cloud_desc = "Clear"
                elif cloud_cover < 50:
                    cloud_color = colors["yellow"]
                    cloud_desc = "Partly Cloudy"
                elif cloud_cover < 80:
                    cloud_color = colors["yellow"]
                    cloud_desc = "Mostly Cloudy"
                else:
                    cloud_color = colors["red"]
                    cloud_desc = "Overcast"
                html_content.append(
                    f"<p><span style='color: {colors['cyan']};'>Cloud Cover:</span> <span style='color: {cloud_color};'>{cloud_cover:.0f}% ({cloud_desc})</span></p>"
                )

            # Wind Speed (cyan label, conditional value color)
            if weather.wind_speed_ms is not None:
                wind_mph = weather.wind_speed_ms  # Already in mph
                if wind_mph < 10:
                    wind_color = colors["green"]
                    wind_desc = "Calm"
                elif wind_mph < 20:
                    wind_color = colors["yellow"]
                    wind_desc = "Moderate"
                else:
                    wind_color = colors["red"]
                    wind_desc = "Strong"
                html_content.append(
                    f"<p><span style='color: {colors['cyan']};'>Wind Speed:</span> <span style='color: {wind_color};'>{wind_mph:.1f} mph ({wind_desc})</span></p>"
                )

            # Visibility (cyan label, white value)
            if weather.visibility_km is not None:
                visibility_mi = weather.visibility_km * 0.621371
                html_content.append(
                    f"<p><span style='color: {colors['cyan']};'>Visibility:</span> <span style='color: {colors['text']};'>{visibility_mi:.1f} mi</span></p>"
                )

            # Condition (cyan label, white value)
            if weather.condition:
                html_content.append(
                    f"<p><span style='color: {colors['cyan']};'>Condition:</span> <span style='color: {colors['text']};'>{weather.condition}</span></p>"
                )

            # Last Updated (cyan label, dim value)
            if weather.last_updated:
                html_content.append(
                    f"<p><span style='color: {colors['cyan']};'>Last Updated:</span> <span style='color: {colors['text_dim']};'>{weather.last_updated}</span></p>"
                )

            # Observing Conditions Assessment
            html_content.append("<h2>Observing Conditions</h2>")
            status, warning = assess_observing_conditions(weather)

            # Status indicator (matching CLI colors)
            if status == "excellent":
                status_color = colors["green"]
                status_icon = "✓"
            elif status == "good":
                status_color = colors["cyan"]
                status_icon = "○"
            elif status == "fair":
                status_color = colors["yellow"]
                status_icon = "⚠"
            else:  # poor
                status_color = colors["red"]
                status_icon = "✗"

            html_content.append(
                f"<p><b>Observing Conditions:</b> <span style='color: {status_color}; font-weight: bold;'>{status_icon} {status.title()}</span></p>"
            )
            if warning:
                html_content.append(f"<p style='color: {colors['text_dim']};'>{warning}</p>")

            # Seeing Conditions
            html_content.append("<h2>Seeing Conditions</h2>")
            seeing_score = calculate_seeing_conditions(weather)

            if seeing_score >= 80:
                seeing_color = colors["green"]
                seeing_desc = "Excellent"
            elif seeing_score >= 60:
                seeing_color = colors["yellow"]
                seeing_desc = "Good"
            elif seeing_score >= 40:
                seeing_color = colors["yellow"]
                seeing_desc = "Fair"
            else:
                seeing_color = colors["red"]
                seeing_desc = "Poor"

            html_content.append(
                f"<p><b>Seeing Conditions:</b> <span style='color: {seeing_color};'>{seeing_desc}</span> ({seeing_score:.0f}/100)</p>"
            )
            html_content.append(
                f"<p style='color: {colors['text_dim']};'>Atmospheric steadiness for image sharpness</p>"
            )

            self.info_text.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading weather info: {e}", exc_info=True)
            self.info_text.setHtml(
                f"<p><span style='color: {colors['error']};'><b>Error:</b> Failed to load weather information: {e}</span></p>"
            )

    def _load_weather_charts(self) -> None:
        """Load weather charts showing current day from 12 AM to now."""
        try:
            from celestron_nexstar.api.core.utils import get_local_timezone
            from celestron_nexstar.api.location.observer import get_observer_location
            from celestron_nexstar.api.location.weather import fetch_weather_for_charts

            location = get_observer_location()
            if not location:
                return

            # Get local timezone
            local_tz = get_local_timezone(location.latitude, location.longitude)
            if not local_tz:
                return

            # Fetch weather data (past 3 days + 24 hours future to ensure we have today's data)
            all_forecasts = fetch_weather_for_charts(location, future_hours=24)

            # Filter to only current day (12 AM to now in local time)
            now_utc = datetime.now(UTC)
            now_local = now_utc.astimezone(local_tz)
            today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
            today_start_utc = today_start_local.astimezone(UTC)

            # Filter forecasts to only include today (from 12 AM to now)
            forecasts = [f for f in all_forecasts if today_start_utc <= f.timestamp <= now_utc]

            if not forecasts:
                logger.warning("No weather data available for charts")
                return

            # Create matplotlib figure with Qt backend
            import matplotlib

            matplotlib.use("QtAgg")  # Use Qt backend for PySide6 integration
            from matplotlib.backends.backend_qt5agg import (
                FigureCanvasQTAgg as FigureCanvas,  # type: ignore[attr-defined]
            )
            from matplotlib.figure import Figure

            # Clear existing charts
            layout = self.charts_widget.layout()
            if layout:
                for i in reversed(range(layout.count())):
                    item = layout.itemAt(i)
                    if item:
                        widget = item.widget()
                        if widget:
                            widget.setParent(None)

            # Create figure with subplots
            fig = Figure(figsize=(12, 10))
            canvas = FigureCanvas(fig)

            # Set theme colors
            is_dark = self._is_dark_theme()
            if is_dark:
                fig.patch.set_facecolor("#1e1e1e")  # type: ignore[attr-defined]
                text_color = "#ffffff"
                grid_color = "#444444"
            else:
                fig.patch.set_facecolor("#ffffff")  # type: ignore[attr-defined]
                text_color = "#000000"
                grid_color = "#cccccc"

            # Prepare data
            timestamps = [f.timestamp for f in forecasts]
            temperatures = [f.temperature_f for f in forecasts]
            cloud_cover = [f.cloud_cover_percent for f in forecasts]
            humidity = [f.humidity_percent for f in forecasts]
            wind_speed = [f.wind_speed_mph for f in forecasts]

            # Find current time index
            current_idx = next((i for i, ts in enumerate(timestamps) if ts >= now_utc), len(timestamps) - 1)

            # Convert datetime to matplotlib date numbers for axvline
            import matplotlib.dates as mdates

            current_time_mpl = mdates.date2num(
                timestamps[current_idx] if current_idx < len(timestamps) else timestamps[-1]
            )

            # Create subplots
            ax1 = fig.add_subplot(4, 1, 1)  # Temperature
            ax2 = fig.add_subplot(4, 1, 2)  # Cloud Cover
            ax3 = fig.add_subplot(4, 1, 3)  # Humidity
            ax4 = fig.add_subplot(4, 1, 4)  # Wind Speed

            # Plot Temperature
            ax1.plot(timestamps, temperatures, color="#ff6b6b", linewidth=2, label="Temperature")
            ax1.axvline(current_time_mpl, color=text_color, linestyle="--", alpha=0.5, label="Now")
            ax1.set_ylabel("Temperature (°F)", color=text_color)
            ax1.tick_params(colors=text_color)
            ax1.grid(True, color=grid_color, alpha=0.3)
            ax1.set_title("Temperature", color=text_color, fontweight="bold")
            ax1.legend(loc="upper left", facecolor="none", edgecolor="none", labelcolor=text_color)

            # Plot Cloud Cover
            ax2.fill_between(timestamps, cloud_cover, 0, color="#4a90e2", alpha=0.3, label="Cloud Cover")
            ax2.plot(timestamps, cloud_cover, color="#4a90e2", linewidth=2)
            ax2.axvline(current_time_mpl, color=text_color, linestyle="--", alpha=0.5)
            ax2.set_ylabel("Cloud Cover (%)", color=text_color)
            ax2.set_ylim(0, 100)
            ax2.tick_params(colors=text_color)
            ax2.grid(True, color=grid_color, alpha=0.3)
            ax2.set_title("Cloud Cover", color=text_color, fontweight="bold")
            ax2.legend(loc="upper left", facecolor="none", edgecolor="none", labelcolor=text_color)

            # Plot Humidity
            ax3.plot(timestamps, humidity, color="#50c878", linewidth=2, label="Humidity")
            ax3.axvline(current_time_mpl, color=text_color, linestyle="--", alpha=0.5)
            ax3.set_ylabel("Humidity (%)", color=text_color)
            ax3.set_ylim(0, 100)
            ax3.tick_params(colors=text_color)
            ax3.grid(True, color=grid_color, alpha=0.3)
            ax3.set_title("Humidity", color=text_color, fontweight="bold")
            ax3.legend(loc="upper left", facecolor="none", edgecolor="none", labelcolor=text_color)

            # Plot Wind Speed
            ax4.plot(timestamps, wind_speed, color="#ffa500", linewidth=2, label="Wind Speed")
            ax4.axvline(current_time_mpl, color=text_color, linestyle="--", alpha=0.5)
            ax4.set_ylabel("Wind Speed (mph)", color=text_color)
            ax4.set_xlabel("Time", color=text_color)
            ax4.tick_params(colors=text_color)
            ax4.grid(True, color=grid_color, alpha=0.3)
            ax4.set_title("Wind Speed", color=text_color, fontweight="bold")
            ax4.legend(loc="upper left", facecolor="none", edgecolor="none", labelcolor=text_color)

            # Format x-axis dates - show time (HH format) on all charts
            # Use 4-hour interval for better spacing
            for ax in [ax1, ax2, ax3, ax4]:
                ax.tick_params(axis="x", rotation=0)  # No rotation needed for time-only
                ax.xaxis.set_major_formatter(mdates.DateFormatter("%H"))  # Just hour (01, 06, 12, 23, etc.)
                ax.xaxis.set_major_locator(mdates.HourLocator(interval=4))  # Every 4 hours
                # Add padding to top, bottom, and left (y-axis) of each chart
                ax.margins(y=0.15, x=0.02)  # 15% margin on top/bottom, 2% on left/right for y-axis labels

            # Adjust layout with more spacing between subplots
            # Add extra left padding to prevent y-axis labels from being cut off
            fig.tight_layout(pad=2.0)  # Padding around the figure
            fig.subplots_adjust(hspace=0.4, left=0.12)  # More spacing between charts, left margin for y-axis labels

            # Add canvas to widget
            layout = self.charts_widget.layout()
            if layout is None:
                from PySide6.QtWidgets import QVBoxLayout

                layout = QVBoxLayout(self.charts_widget)
                layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(canvas)

        except Exception as e:
            logger.error(f"Error loading weather charts: {e}", exc_info=True)
