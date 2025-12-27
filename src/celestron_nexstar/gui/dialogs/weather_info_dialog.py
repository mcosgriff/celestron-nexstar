"""
Dialog to display current weather information.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QEvent, QObject
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


class WheelEventFilter(QObject):
    """Event filter to redirect wheel events from matplotlib canvas to scroll area."""

    def __init__(self, scroll_area: Any) -> None:
        """Initialize with target scroll area."""
        super().__init__()
        self.scroll_area = scroll_area

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Filter wheel events and redirect to scroll area."""
        if event.type() == QEvent.Type.Wheel:
            # Forward wheel event to scroll area
            from PySide6.QtCore import QCoreApplication
            from PySide6.QtGui import QWheelEvent

            wheel_event = QWheelEvent(event)  # type: ignore[arg-type]
            QCoreApplication.sendEvent(self.scroll_area, wheel_event)
            return True
        return False


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
        font_family = f"'{monospace_font}'" if monospace_font else "'Courier New'"

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

        # Create "Advanced" tab with advanced atmospheric metrics
        advanced_tab = QWidget()
        advanced_layout = QVBoxLayout(advanced_tab)

        self.advanced_text = QTextEdit()
        self.advanced_text.setReadOnly(True)
        self.advanced_text.setAcceptRichText(True)
        self.advanced_text.setStyleSheet(
            f"""
            QTextEdit {{
                font-family: {font_family};
                background-color: transparent;
                border: none;
            }}
        """
        )
        advanced_layout.addWidget(self.advanced_text)
        self.tab_widget.addTab(advanced_tab, "Advanced")

        # Create "Charts" tab with scroll area
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QScrollArea

        charts_tab = QWidget()
        charts_layout = QVBoxLayout(charts_tab)
        charts_layout.setContentsMargins(0, 0, 0, 0)

        # Create scroll area for charts
        self.charts_scroll_area = QScrollArea()
        self.charts_scroll_area.setWidgetResizable(True)
        self.charts_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.charts_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.charts_scroll_area.setFocusPolicy(Qt.FocusPolicy.WheelFocus)  # Enable mouse wheel scrolling

        self.charts_widget = QWidget()
        charts_widget_layout = QVBoxLayout(self.charts_widget)
        charts_widget_layout.setContentsMargins(0, 0, 0, 0)

        self.charts_scroll_area.setWidget(self.charts_widget)
        charts_layout.addWidget(self.charts_scroll_area)
        self.tab_widget.addTab(charts_tab, "Charts")

        # Add button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        # Load weather information (this will also update stylesheet with theme colors)
        self._load_weather_info()
        self._load_advanced_metrics()
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
                # Convert UTC timestamp to local time
                last_updated_str = weather.last_updated
                if last_updated_str == "now":
                    last_updated_display = "Just now"
                else:
                    try:
                        # Parse ISO timestamp and convert to local timezone
                        from celestron_nexstar.api.core.utils import get_local_timezone

                        utc_time = datetime.fromisoformat(last_updated_str.replace("Z", "+00:00"))
                        if utc_time.tzinfo is None:
                            utc_time = utc_time.replace(tzinfo=UTC)

                        # Get local timezone
                        local_tz = get_local_timezone(location.latitude, location.longitude)
                        local_time = utc_time.astimezone(local_tz)
                        last_updated_display = local_time.strftime("%Y-%m-%d %H:%M:%S %Z")
                    except (ValueError, AttributeError):
                        # Fallback if parsing fails
                        last_updated_display = last_updated_str

                html_content.append(
                    f"<p><span style='color: {colors['cyan']};'>Last Updated:</span> <span style='color: {colors['text_dim']};'>{last_updated_display}</span></p>"
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

    def _load_advanced_metrics(self) -> None:
        """Load advanced atmospheric metrics in the Advanced tab."""
        colors = self._get_theme_colors()

        try:
            from celestron_nexstar.api.location.observer import get_observer_location
            from celestron_nexstar.api.location.weather import (
                calculate_seeing_conditions,
                calculate_seeing_conditions_v2,
                fetch_weather,
            )

            location = get_observer_location()
            if not location:
                self.advanced_text.setHtml(
                    f"<p style='color: {colors['error']};'><b>Error:</b> No observer location configured.</p>"
                )
                return

            weather = fetch_weather(location)

            if weather.error:
                self.advanced_text.setHtml(f"<p style='color: {colors['error']};'><b>Error:</b> {weather.error}</p>")
                return

            html = []

            # Header
            html.append(f"<h1 style='color: {colors['header']};'>Advanced Atmospheric Metrics</h1>")

            # Cloud Layer Analysis
            html.append(f"<h2 style='color: {colors['header']};'>Cloud Layer Distribution</h2>")
            if weather.cloud_cover_low is not None:
                html.append(
                    f"<p><span style='color: {colors['cyan']};'>Low Clouds (0-3km):</span> {weather.cloud_cover_low:.0f}%</p>"
                )
            if weather.cloud_cover_mid is not None:
                html.append(
                    f"<p><span style='color: {colors['cyan']};'>Mid Clouds (3-8km):</span> {weather.cloud_cover_mid:.0f}%</p>"
                )
            if weather.cloud_cover_high is not None:
                html.append(
                    f"<p><span style='color: {colors['cyan']};'>High Clouds (8km+):</span> {weather.cloud_cover_high:.0f}%</p>"
                )

            # Atmospheric Stability
            html.append(f"<h2 style='color: {colors['header']};'>Atmospheric Stability</h2>")

            if weather.cape is not None:
                cape_color = (
                    colors["green"]
                    if weather.cape < 500
                    else colors["yellow"]
                    if weather.cape < 1500
                    else colors["red"]
                )
                cape_desc = "Stable" if weather.cape < 500 else "Moderate" if weather.cape < 1500 else "Unstable"
                html.append(
                    f"<p><span style='color: {colors['cyan']};'>CAPE:</span> <span style='color: {cape_color};'>{weather.cape:.0f} J/kg ({cape_desc})</span></p>"
                )

            if weather.boundary_layer_height_m is not None:
                html.append(
                    f"<p><span style='color: {colors['cyan']};'>Boundary Layer Height:</span> {weather.boundary_layer_height_m:.0f}m</p>"
                )

            if weather.vapour_pressure_deficit is not None:
                vpd_color = (
                    colors["green"]
                    if weather.vapour_pressure_deficit > 1.0
                    else colors["yellow"]
                    if weather.vapour_pressure_deficit > 0.5
                    else colors["red"]
                )
                html.append(
                    f"<p><span style='color: {colors['cyan']};'>Vapour Pressure Deficit:</span> <span style='color: {vpd_color};'>{weather.vapour_pressure_deficit:.2f} kPa</span></p>"
                )

            if weather.freezing_level_height_m is not None:
                html.append(
                    f"<p><span style='color: {colors['cyan']};'>Freezing Level:</span> {weather.freezing_level_height_m:.0f}m</p>"
                )

            # Wind Profile
            html.append(f"<h2 style='color: {colors['header']};'>Wind Profile</h2>")

            if weather.wind_speed_ms is not None:
                html.append(
                    f"<p><span style='color: {colors['cyan']};'>Surface Wind (10m):</span> {weather.wind_speed_ms:.1f} mph</p>"
                )

            if weather.wind_speed_80m_mph is not None:
                html.append(
                    f"<p><span style='color: {colors['cyan']};'>Wind @ 80m:</span> {weather.wind_speed_80m_mph:.1f} mph</p>"
                )

            if weather.wind_speed_120m_mph is not None:
                html.append(
                    f"<p><span style='color: {colors['cyan']};'>Wind @ 120m:</span> {weather.wind_speed_120m_mph:.1f} mph</p>"
                )

            # Wind shear calculation
            if all([weather.wind_speed_ms, weather.wind_speed_120m_mph]):
                shear = abs(weather.wind_speed_120m_mph - weather.wind_speed_ms)
                shear_color = colors["green"] if shear < 10 else colors["yellow"] if shear < 20 else colors["red"]
                shear_desc = "Low" if shear < 10 else "Moderate" if shear < 20 else "High"
                html.append(
                    f"<p><span style='color: {colors['cyan']};'>Wind Shear (10-120m):</span> <span style='color: {shear_color};'>{shear:.1f} mph ({shear_desc})</span></p>"
                )

            # Visibility & Precipitation
            html.append(f"<h2 style='color: {colors['header']};'>Visibility & Precipitation</h2>")

            if weather.visibility_m is not None:
                vis_km = weather.visibility_m / 1000.0
                vis_color = colors["green"] if vis_km > 10 else colors["yellow"] if vis_km > 5 else colors["red"]
                html.append(
                    f"<p><span style='color: {colors['cyan']};'>Visibility:</span> <span style='color: {vis_color};'>{vis_km:.1f} km</span></p>"
                )

            if weather.precipitation_probability is not None:
                precip_color = (
                    colors["green"]
                    if weather.precipitation_probability < 20
                    else colors["yellow"]
                    if weather.precipitation_probability < 50
                    else colors["red"]
                )
                html.append(
                    f"<p><span style='color: {colors['cyan']};'>Precipitation Probability:</span> <span style='color: {precip_color};'>{weather.precipitation_probability:.0f}%</span></p>"
                )

            if weather.precipitation_mm is not None and weather.precipitation_mm > 0:
                html.append(
                    f"<p><span style='color: {colors['cyan']};'>Precipitation:</span> {weather.precipitation_mm:.1f} mm</p>"
                )

            if weather.pressure_msl is not None:
                html.append(
                    f"<p><span style='color: {colors['cyan']};'>Pressure (MSL):</span> {weather.pressure_msl:.1f} hPa</p>"
                )

            # Seeing Score Comparison
            html.append(f"<h2 style='color: {colors['header']};'>Seeing Score Comparison</h2>")
            html.append("<p><em>Compare old and new seeing algorithms:</em></p>")

            # Calculate both scores
            old_score = calculate_seeing_conditions(weather)
            new_score, components = calculate_seeing_conditions_v2(weather)

            html.append(f"<p><span style='color: {colors['cyan']};'>Old Algorithm:</span> {old_score:.0f}/100</p>")
            html.append(f"<p><span style='color: {colors['cyan']};'>New Algorithm:</span> {new_score:.0f}/100</p>")
            diff = new_score - old_score
            diff_color = colors["green"] if diff > 0 else colors["red"] if diff < 0 else colors["yellow"]
            html.append(
                f"<p><span style='color: {colors['cyan']};'>Difference:</span> <span style='color: {diff_color};'>{diff:+.0f} points</span></p>"
            )

            # Component breakdown
            if components:
                html.append(f"<h3 style='color: {colors['header']};'>Component Scores (New Algorithm):</h3>")
                html.append("<ul>")
                for name, score in components.items():
                    formatted_name = name.replace("_", " ").title()
                    html.append(f"<li>{formatted_name}: {score:.0f}/100</li>")
                html.append("</ul>")

            self.advanced_text.setHtml("\n".join(html))

        except Exception as e:
            logger.exception("Error loading advanced metrics")
            self.advanced_text.setHtml(
                f"<p style='color: {colors['error']};'><b>Error:</b> Failed to load advanced metrics: {e}</p>"
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

            # Use a +/- 6 hour window around "now" (total 12 hours) in local time
            now_utc = datetime.now(UTC)
            now_local = now_utc.astimezone(local_tz)
            window_start_local = now_local - timedelta(hours=6)
            window_end_local = now_local + timedelta(hours=6)
            window_start_utc = window_start_local.astimezone(UTC)
            window_end_utc = window_end_local.astimezone(UTC)

            # Filter forecasts to only the 12-hour window
            from dataclasses import replace

            forecasts = []
            for f in all_forecasts:
                ts = f.timestamp
                ts_utc = ts.replace(tzinfo=UTC) if getattr(ts, "tzinfo", None) is None else ts.astimezone(UTC)
                if window_start_utc <= ts_utc <= window_end_utc:
                    forecasts.append(replace(f, timestamp=ts_utc))

            if not forecasts:
                logger.warning("No weather data available for charts")
                return

            # Create matplotlib figure with Qt backend
            import matplotlib

            matplotlib.use("QtAgg")  # Use Qt backend for PySide6 integration
            from matplotlib.backends.backend_qt5agg import (  # type: ignore[attr-defined]
                FigureCanvasQTAgg as FigureCanvas,
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

            # Create figure with 6 subplots (expanded from 4)
            # Increased height to give each chart more vertical space
            # Height of 40 ensures scroll bar appears and charts are well-spaced
            fig = Figure(figsize=(12, 40), dpi=100)
            canvas = FigureCanvas(fig)
            # Set fixed minimum size to force scrolling (40 inches * 100 dpi = 4000 pixels)
            canvas.setMinimumHeight(1000)
            # Improves hover responsiveness for interactive tooltips.
            canvas.setMouseTracking(True)

            # Set theme colors
            is_dark = self._is_dark_theme()
            if is_dark:
                fig.patch.set_facecolor("#1e1e1e")  # type: ignore[attr-defined]
                text_color = "#ffffff"
                grid_color = "#444444"
                axes_facecolor = "#1a1a1a"
            else:
                fig.patch.set_facecolor("#ffffff")  # type: ignore[attr-defined]
                text_color = "#000000"
                grid_color = "#cccccc"
                axes_facecolor = "#ffffff"

            # Prepare data
            timestamps_utc = [f.timestamp for f in forecasts]
            timestamps = [ts.astimezone(local_tz) for ts in timestamps_utc]
            temperatures = [f.temperature_f for f in forecasts]
            dew_points = [f.dew_point_f if f.dew_point_f is not None else float("nan") for f in forecasts]
            cloud_cover = [f.cloud_cover_percent for f in forecasts]
            humidity = [f.humidity_percent for f in forecasts]
            wind_speed = [f.wind_speed_mph for f in forecasts]

            # New advanced metrics
            cloud_low = [f.cloud_cover_low if f.cloud_cover_low is not None else 0 for f in forecasts]
            cloud_mid = [f.cloud_cover_mid if f.cloud_cover_mid is not None else 0 for f in forecasts]
            cloud_high = [f.cloud_cover_high if f.cloud_cover_high is not None else 0 for f in forecasts]
            wind_80m = [f.wind_speed_80m_mph if f.wind_speed_80m_mph is not None else float("nan") for f in forecasts]
            wind_120m = [
                f.wind_speed_120m_mph if f.wind_speed_120m_mph is not None else float("nan") for f in forecasts
            ]

            # Check if we have layered cloud data
            has_cloud_layers = any(f.cloud_cover_low is not None for f in forecasts)
            has_upper_winds = any(f.wind_speed_80m_mph is not None for f in forecasts)

            # Calculate atmospheric stability scores for each forecast
            from celestron_nexstar.api.location.weather import WeatherData, _calc_atmospheric_stability_score

            stability_scores = []
            for f in forecasts:
                weather_data = WeatherData(
                    cape=f.cape,
                    boundary_layer_height_m=f.boundary_layer_height_m,
                    vapour_pressure_deficit=getattr(f, "vapour_pressure_deficit", None),
                )
                score = _calc_atmospheric_stability_score(weather_data)
                stability_scores.append(score)

            # Convert datetime to matplotlib date numbers for axvline and x-limits
            import matplotlib.dates as mdates

            current_time_mpl = mdates.date2num(now_local)
            start_time_mpl = mdates.date2num(window_start_local)
            end_time_mpl = mdates.date2num(window_end_local)

            # Create 6 subplots
            ax1 = fig.add_subplot(6, 1, 1)  # Temperature
            ax2 = fig.add_subplot(6, 1, 2)  # Cloud Cover (enhanced with layers)
            ax3 = fig.add_subplot(6, 1, 3)  # Humidity
            ax4 = fig.add_subplot(6, 1, 4)  # Wind Speed
            ax5 = fig.add_subplot(6, 1, 5)  # Atmospheric Stability (NEW)
            ax6 = fig.add_subplot(6, 1, 6)  # Wind Profile (NEW)
            for ax in (ax1, ax2, ax3, ax4, ax5, ax6):
                ax.set_facecolor(axes_facecolor)

            # Plot Temperature
            (temp_line,) = ax1.plot(timestamps, temperatures, color="#ff6b6b", linewidth=2, label="_nolegend_")
            (dew_line,) = ax1.plot(
                timestamps, dew_points, color="#50c8e0", linewidth=1.5, linestyle="--", label="_nolegend_"
            )
            ax1.axvline(current_time_mpl, color=text_color, linestyle="--", alpha=0.5)
            ax1.set_ylabel("Temperature (°F)", color=text_color)
            ax1.tick_params(colors=text_color)
            ax1.grid(True, color=grid_color, alpha=0.3)
            ax1.set_title("Temperature", color=text_color, fontweight="bold")
            ax1.set_xlim(start_time_mpl, end_time_mpl)

            # Plot Cloud Cover (enhanced with layers if available)
            if has_cloud_layers:
                # Three separate lines for cloud layers (like wind profile)
                (cloud_low_line,) = ax2.plot(timestamps, cloud_low, color="#ff6b6b", linewidth=2.5, label="_nolegend_")
                (cloud_mid_line,) = ax2.plot(
                    timestamps, cloud_mid, color="#ffa500", linewidth=1.8, linestyle="--", label="_nolegend_"
                )
                (cloud_high_line,) = ax2.plot(
                    timestamps, cloud_high, color="#4a90e2", linewidth=1.8, linestyle=":", label="_nolegend_"
                )
            else:
                # Simple cloud cover
                (cloud_low_line,) = ax2.plot(timestamps, cloud_cover, color="#4a90e2", linewidth=2, label="_nolegend_")

            ax2.axvline(current_time_mpl, color=text_color, linestyle="--", alpha=0.5)
            ax2.set_ylabel("Cloud Cover (%)", color=text_color)
            ax2.set_ylim(0, 100)
            ax2.tick_params(colors=text_color)
            ax2.grid(True, color=grid_color, alpha=0.3)
            ax2.set_title("Cloud Cover", color=text_color, fontweight="bold")
            ax2.set_xlim(start_time_mpl, end_time_mpl)

            # Plot Humidity
            (humidity_line,) = ax3.plot(timestamps, humidity, color="#50c878", linewidth=2, label="_nolegend_")
            ax3.axvline(current_time_mpl, color=text_color, linestyle="--", alpha=0.5)
            ax3.set_ylabel("Humidity (%)", color=text_color)
            ax3.set_ylim(0, 100)
            ax3.tick_params(colors=text_color)
            ax3.grid(True, color=grid_color, alpha=0.3)
            ax3.set_title("Humidity", color=text_color, fontweight="bold")
            ax3.set_xlim(start_time_mpl, end_time_mpl)

            # Plot Wind Speed
            (wind_line,) = ax4.plot(timestamps, wind_speed, color="#ffa500", linewidth=2, label="_nolegend_")
            ax4.axvline(current_time_mpl, color=text_color, linestyle="--", alpha=0.5)
            ax4.set_ylabel("Wind Speed (mph)", color=text_color)
            ax4.tick_params(colors=text_color)
            ax4.grid(True, color=grid_color, alpha=0.3)
            ax4.set_title("Wind Speed", color=text_color, fontweight="bold")
            ax4.set_xlim(start_time_mpl, end_time_mpl)

            # Plot Atmospheric Stability (NEW)
            (stability_line,) = ax5.plot(timestamps, stability_scores, color="#9b59b6", linewidth=2, label="_nolegend_")
            ax5.fill_between(timestamps, stability_scores, 0, color="#9b59b6", alpha=0.2)
            ax5.axvline(current_time_mpl, color=text_color, linestyle="--", alpha=0.5)
            ax5.set_ylabel("Stability Score", color=text_color)
            ax5.set_ylim(0, 100)
            ax5.tick_params(colors=text_color)
            ax5.grid(True, color=grid_color, alpha=0.3)
            ax5.set_title("Atmospheric Stability (CAPE, BLH, VPD)", color=text_color, fontweight="bold")
            ax5.set_xlim(start_time_mpl, end_time_mpl)

            # Plot Wind Profile (NEW)
            (wind_10m_line,) = ax6.plot(timestamps, wind_speed, color="#3498db", linewidth=2.5, label="_nolegend_")
            if has_upper_winds:
                (wind_80m_line,) = ax6.plot(
                    timestamps, wind_80m, color="#2ecc71", linewidth=1.8, linestyle="--", label="_nolegend_"
                )
                (wind_120m_line,) = ax6.plot(
                    timestamps, wind_120m, color="#f39c12", linewidth=1.8, linestyle=":", label="_nolegend_"
                )
            ax6.axvline(current_time_mpl, color=text_color, linestyle="--", alpha=0.5)
            ax6.set_ylabel("Wind Speed (mph)", color=text_color)
            ax6.set_xlabel("Time", color=text_color)
            ax6.tick_params(colors=text_color)
            ax6.grid(True, color=grid_color, alpha=0.3)
            ax6.set_title("Wind Profile", color=text_color, fontweight="bold")
            ax6.set_xlim(start_time_mpl, end_time_mpl)

            # Format x-axis dates - show time (HH) on all charts within 12h window
            for ax in [ax1, ax2, ax3, ax4, ax5, ax6]:
                ax.tick_params(axis="x", rotation=0)  # No rotation needed for time-only
                ax.xaxis.set_major_formatter(mdates.DateFormatter("%H", tz=local_tz))  # 24-hour local hour
                ax.xaxis.set_major_locator(
                    mdates.HourLocator(interval=2, tz=local_tz)
                )  # Every 2 hours for a 12h window
                # Add padding to top, bottom, and left (y-axis) of each chart
                ax.margins(y=0.30, x=0.0)  # 30% margin on top/bottom for better readability

            # Adjust layout with explicit spacing (no tight_layout to avoid override)
            # Add extra left padding to prevent y-axis labels from being cut off
            # Balanced hspace for clear separation without excessive whitespace
            fig.subplots_adjust(hspace=1.2, left=0.12, right=0.95, top=0.98, bottom=0.02)

            # Optional: interactive hover tooltips (like NWS graphical forecast).
            # This is best-effort; if mplcursors isn't installed, charts still render normally.
            try:
                import mplcursors  # type: ignore[import-untyped]

                line_units: dict[int, str] = {
                    id(temp_line): "°F",
                    id(dew_line): "°F",
                    id(humidity_line): "%",
                    id(wind_line): "mph",
                    id(stability_line): "/100",
                    id(wind_10m_line): "mph",
                    id(cloud_low_line): "%",
                }
                line_names: dict[int, str] = {
                    id(temp_line): "Temperature",
                    id(dew_line): "Dew Point",
                    id(humidity_line): "Humidity",
                    id(wind_line): "Wind Speed",
                    id(stability_line): "Stability Score",
                    id(wind_10m_line): "Wind (10m)",
                    id(cloud_low_line): "Cloud Low (0-3km)" if has_cloud_layers else "Cloud Cover",
                }

                # Build cursor lines list - only include lines that exist
                cursor_lines = [
                    temp_line,
                    dew_line,
                    cloud_low_line,
                    humidity_line,
                    wind_line,
                    stability_line,
                    wind_10m_line,
                ]

                # Add cloud layer lines if available
                if has_cloud_layers:
                    try:
                        line_units[id(cloud_mid_line)] = "%"
                        line_units[id(cloud_high_line)] = "%"
                        line_names[id(cloud_mid_line)] = "Cloud Mid (3-8km)"
                        line_names[id(cloud_high_line)] = "Cloud High (8km+)"
                        cursor_lines.extend([cloud_mid_line, cloud_high_line])
                    except NameError:
                        # Cloud layer lines weren't created, skip them
                        pass

                # Add upper wind lines if available
                if has_upper_winds:
                    # These variables only exist if has_upper_winds is True
                    try:
                        line_units[id(wind_80m_line)] = "mph"
                        line_units[id(wind_120m_line)] = "mph"
                        line_names[id(wind_80m_line)] = "Wind (80m)"
                        line_names[id(wind_120m_line)] = "Wind (120m)"
                        cursor_lines.extend([wind_80m_line, wind_120m_line])
                    except NameError:
                        # Upper wind lines weren't created, skip them
                        pass

                cursor = mplcursors.cursor(cursor_lines, hover=True)

                @cursor.connect("add")  # type: ignore[misc]
                def _on_add(sel: Any) -> None:
                    artist = sel.artist
                    series = line_names.get(id(artist), "Value")
                    unit = line_units.get(id(artist), "")

                    try:
                        idx = int(getattr(sel, "index", 0))
                    except Exception:
                        idx = 0

                    try:
                        x = artist.get_xdata()[idx]
                        # x is datetime-like in our charts
                        ts_local = x.astimezone(local_tz) if getattr(x, "tzinfo", None) else x
                        time_str = ts_local.strftime("%H:%M")
                    except Exception:
                        time_str = ""

                    y = float(sel.target[1]) if hasattr(sel, "target") else None
                    text = f"{series}" if y is None else f"{series}\n{time_str}  {y:.1f}{' ' + unit if unit else ''}"

                    sel.annotation.set_text(text)
                    sel.annotation.get_bbox_patch().set_alpha(0.9)
                    sel.annotation.get_bbox_patch().set_facecolor("#222222" if is_dark else "#ffffff")
                    sel.annotation.get_bbox_patch().set_edgecolor("#777777" if is_dark else "#cccccc")
                    sel.annotation.set_color("#ffffff" if is_dark else "#000000")
            except Exception:
                # Hover is optional; ignore if missing or unsupported backend.
                pass

            # Install event filter to redirect wheel events to scroll area
            wheel_filter = WheelEventFilter(self.charts_scroll_area)
            canvas.installEventFilter(wheel_filter)
            # Keep a reference to prevent garbage collection
            canvas._wheel_filter = wheel_filter  # type: ignore[attr-defined]

            # Add canvas to widget
            layout = self.charts_widget.layout()
            if layout is None:
                from PySide6.QtWidgets import QVBoxLayout

                layout = QVBoxLayout(self.charts_widget)
                layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(canvas)

        except Exception as e:
            logger.error(f"Error loading weather charts: {e}", exc_info=True)
