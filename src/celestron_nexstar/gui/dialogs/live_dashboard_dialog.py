"""
Live Dashboard Dialog

Real-time dashboard showing current weather, moon phase, seeing conditions,
and space weather data with auto-refresh.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from celestron_nexstar.api.astronomy.solar_system import MoonInfo, get_moon_info
from celestron_nexstar.api.events.space_weather import (
    SpaceWeatherConditions,
    get_space_weather_conditions,
)
from celestron_nexstar.api.location.observer import ObserverLocation, get_observer_location
from celestron_nexstar.api.location.weather import (
    WeatherData,
    assess_observing_conditions,
    calculate_seeing_conditions,
    fetch_weather,
)


if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


class LiveDashboardDialog(QDialog):
    """Real-time dashboard showing current observing conditions."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the live dashboard dialog."""
        super().__init__(parent)
        self.setWindowTitle("Live Dashboard")
        self.setMinimumWidth(800)
        self.setMinimumHeight(600)
        self.resize(800, 600)

        # Set window icon
        self._set_window_icon()

        # Create layout
        layout = QVBoxLayout(self)

        # Header
        header_label = QLabel("Live Observing Conditions")
        header_label.setStyleSheet("font-size: 16pt; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header_label)

        # Create grid layout for dashboard widgets
        grid_layout = QGridLayout()
        grid_layout.setSpacing(15)

        # Weather section
        self.weather_group = QGroupBox("Weather Conditions")
        self.weather_layout = QVBoxLayout()
        self.weather_labels: dict[str, QLabel] = {}
        self.weather_group.setLayout(self.weather_layout)
        grid_layout.addWidget(self.weather_group, 0, 0)

        # Moon section
        self.moon_group = QGroupBox("Moon")
        self.moon_layout = QVBoxLayout()
        self.moon_labels: dict[str, QLabel] = {}
        self.moon_group.setLayout(self.moon_layout)
        grid_layout.addWidget(self.moon_group, 0, 1)

        # Seeing section
        self.seeing_group = QGroupBox("Seeing Conditions")
        self.seeing_layout = QVBoxLayout()
        self.seeing_labels: dict[str, QLabel] = {}
        self.seeing_group.setLayout(self.seeing_layout)
        grid_layout.addWidget(self.seeing_group, 1, 0)

        # Space Weather section
        self.space_weather_group = QGroupBox("Space Weather")
        self.space_weather_layout = QVBoxLayout()
        self.space_weather_layout.setSpacing(6)
        self.space_weather_labels: dict[str, QLabel] = {}
        self.space_weather_group.setLayout(self.space_weather_layout)
        grid_layout.addWidget(self.space_weather_group, 1, 1)

        # Add grid to main layout
        grid_widget = QWidget()
        grid_widget.setLayout(grid_layout)
        layout.addWidget(grid_widget)

        # Status and last update
        self.status_label = QLabel("Loading...")
        self.status_label.setStyleSheet("color: #888; font-style: italic;")
        layout.addWidget(self.status_label)

        # Refresh button
        refresh_button = QPushButton("Refresh Now")
        refresh_button.clicked.connect(self._refresh_data)
        layout.addWidget(refresh_button)

        # Add button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Auto-refresh timer (refresh every 60 seconds)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_data)
        self.refresh_timer.start(60000)  # 60 seconds

        # Initial data load
        self._refresh_data()

    def _set_window_icon(self) -> None:
        """Set the window icon for the dialog."""
        # Detect theme for icon color
        from PySide6.QtGui import QGuiApplication, QPalette

        is_dark = False
        app = QGuiApplication.instance()
        if app and isinstance(app, QGuiApplication):
            palette = app.palette()
            window_color = palette.color(QPalette.ColorRole.Window)
            brightness = window_color.lightness()
            is_dark = brightness < 128

        # Use theme-appropriate color for icons
        icon_color = "#ffffff" if is_dark else "#000000"

        try:
            import qtawesome as qta  # type: ignore[import-not-found,import-untyped]

            # Try dashboard icon with theme-aware color
            icon = qta.icon("mdi.view-dashboard", color=icon_color)
            if icon.isNull():
                # Try alternative dashboard icons
                for icon_name in ["mdi.chart-line", "mdi.monitor-dashboard", "mdi.chart-box-outline"]:
                    icon = qta.icon(icon_name, color=icon_color)
                    if not icon.isNull():
                        break

            if not icon.isNull():
                self.setWindowIcon(QIcon(icon))
                return
        except Exception:
            pass

        # Fallback to theme icon
        icon = QIcon.fromTheme("view-dashboard")
        if icon.isNull():
            # Try other theme icon names
            for theme_name in ["chart-line", "monitor-dashboard", "dashboard"]:
                icon = QIcon.fromTheme(theme_name)
                if not icon.isNull():
                    break

        if not icon.isNull():
            self.setWindowIcon(icon)

    def _get_theme_colors(self) -> dict[str, str]:
        """Get theme colors based on system theme."""
        from PySide6.QtGui import QGuiApplication

        app = QGuiApplication.instance()
        if app is None or not isinstance(app, QGuiApplication):
            return {
                "text": "#ffffff",
                "text_dim": "#aaaaaa",
                "cyan": "#00ffff",
                "green": "#00ff00",
                "yellow": "#ffff00",
                "red": "#ff0000",
                "header": "#ffff00",
            }

        palette = app.palette()
        is_dark = palette.color(palette.ColorRole.Window).lightness() < 128

        if is_dark:
            return {
                "text": "#ffffff",
                "text_dim": "#aaaaaa",
                "cyan": "#00ffff",
                "green": "#00ff00",
                "yellow": "#ffff00",
                "red": "#ff6666",
                "header": "#ffff00",
            }
        else:
            return {
                "text": "#000000",
                "text_dim": "#666666",
                "cyan": "#0066cc",
                "green": "#008800",
                "yellow": "#cc8800",
                "red": "#cc0000",
                "header": "#cc8800",
            }

    def _create_label(self, text: str, color: str | None = None) -> QLabel:
        """Create a styled label."""
        label = QLabel(text)
        if color:
            label.setStyleSheet(f"color: {color};")
        return label

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        """Clear all widgets from a layout."""
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _refresh_data(self) -> None:
        """Refresh all dashboard data."""
        try:
            location = get_observer_location()
            if not location:
                self.status_label.setText("Error: Location not configured")
                return

            # Fetch all data asynchronously
            # Use asyncio.run() since we're in a sync context
            asyncio.run(self._load_dashboard_data(location))
        except Exception as e:
            logger.error(f"Error refreshing dashboard data: {e}", exc_info=True)
            self.status_label.setText(f"Error loading data: {e}")

    async def _load_dashboard_data(self, location: ObserverLocation) -> None:
        """Load all dashboard data asynchronously."""
        colors = self._get_theme_colors()

        # Fetch weather
        weather = await fetch_weather(location)
        self._update_weather(weather, colors)

        # Fetch moon info (synchronous function)
        try:
            moon_info = get_moon_info(location.latitude, location.longitude, datetime.now(UTC))
            self._update_moon(moon_info, colors)
        except Exception as e:
            logger.debug(f"Could not fetch moon info: {e}")
            self._update_moon(None, colors)

        # Calculate seeing conditions
        if not weather.error:
            try:
                seeing_score = calculate_seeing_conditions(weather)
                status, warning = assess_observing_conditions(weather)
                self._update_seeing(weather, seeing_score, status, warning, colors)
            except Exception as e:
                logger.debug(f"Could not calculate seeing conditions: {e}")
                self._update_seeing(weather, 0.0, "unknown", "", colors)
        else:
            self._update_seeing(weather, 0.0, "unknown", "", colors)

        # Fetch space weather
        try:
            space_weather = await get_space_weather_conditions()
            self._update_space_weather(space_weather, colors)
        except Exception as e:
            logger.debug(f"Could not fetch space weather: {e}")
            self._update_space_weather(None, colors)

        # Update status
        now = datetime.now()
        self.status_label.setText(f"Last updated: {now.strftime('%Y-%m-%d %H:%M:%S')}")

    def _update_weather(self, weather: WeatherData, colors: dict[str, str]) -> None:
        """Update weather section."""
        self._clear_layout(self.weather_layout)
        self.weather_labels = {}

        if weather.error:
            error_label = self._create_label(f"Error: {weather.error}", colors["red"])
            self.weather_layout.addWidget(error_label)
            return

        # Temperature
        if weather.temperature_c is not None:
            temp_label = self._create_label(f"Temperature: {weather.temperature_c:.1f}°F", colors["text"])
            self.weather_layout.addWidget(temp_label)

        # Humidity
        if weather.humidity_percent is not None:
            humidity_label = self._create_label(f"Humidity: {weather.humidity_percent:.0f}%", colors["text"])
            self.weather_layout.addWidget(humidity_label)

        # Cloud Cover
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
            cloud_label = self._create_label(f"Cloud Cover: {cloud_cover:.0f}% ({cloud_desc})", cloud_color)
            self.weather_layout.addWidget(cloud_label)

        # Wind Speed
        if weather.wind_speed_ms is not None:
            wind_label = self._create_label(f"Wind Speed: {weather.wind_speed_ms:.1f} mph", colors["text"])
            self.weather_layout.addWidget(wind_label)

        # Visibility
        if weather.visibility_km is not None:
            vis_label = self._create_label(f"Visibility: {weather.visibility_km:.1f} km", colors["text"])
            self.weather_layout.addWidget(vis_label)

        # Condition
        if weather.condition:
            condition_label = self._create_label(f"Condition: {weather.condition}", colors["text"])
            self.weather_layout.addWidget(condition_label)

        self.weather_layout.addStretch()

    def _update_moon(self, moon_info: MoonInfo | None, colors: dict[str, str]) -> None:
        """Update moon section."""
        self._clear_layout(self.moon_layout)
        self.moon_labels = {}

        if not moon_info:
            error_label = self._create_label("Moon data unavailable", colors["text_dim"])
            self.moon_layout.addWidget(error_label)
            return

        # Moon Phase
        if moon_info.illumination is not None:
            illum_pct = moon_info.illumination * 100
            phase_label = self._create_label(f"Phase: {illum_pct:.0f}% illuminated", colors["text"])
            self.moon_layout.addWidget(phase_label)

        # Moon Altitude
        if moon_info.altitude_deg is not None:
            alt = moon_info.altitude_deg
            if alt > 0:
                alt_color = colors["green"]
                alt_status = "Above horizon"
            else:
                alt_color = colors["text_dim"]
                alt_status = "Below horizon"
            alt_label = self._create_label(f"Altitude: {alt:.1f}° ({alt_status})", alt_color)
            self.moon_layout.addWidget(alt_label)

        # Moon Azimuth
        if moon_info.azimuth_deg is not None:
            az_label = self._create_label(f"Azimuth: {moon_info.azimuth_deg:.1f}°", colors["text"])
            self.moon_layout.addWidget(az_label)

        # Moon impact on observing
        if moon_info.illumination is not None:
            if moon_info.illumination < 0.1:
                impact_color = colors["green"]
                impact_text = "Minimal impact (new moon)"
            elif moon_info.illumination < 0.3:
                impact_color = colors["yellow"]
                impact_text = "Low impact"
            elif moon_info.illumination < 0.7:
                impact_color = colors["yellow"]
                impact_text = "Moderate impact"
            else:
                impact_color = colors["red"]
                impact_text = "High impact (bright moon)"
            impact_label = self._create_label(impact_text, impact_color)
            self.moon_layout.addWidget(impact_label)

        self.moon_layout.addStretch()

    def _update_seeing(
        self,
        weather: WeatherData,
        seeing_score: float,
        status: str,
        warning: str,
        colors: dict[str, str],
    ) -> None:
        """Update seeing conditions section."""
        self._clear_layout(self.seeing_layout)
        self.seeing_labels = {}

        # Seeing Score
        if seeing_score < 20:
            seeing_color = colors["red"]
            seeing_desc = "Very Poor"
        elif seeing_score < 50:
            seeing_color = colors["red"]
            seeing_desc = "Poor"
        elif seeing_score < 70:
            seeing_color = colors["yellow"]
            seeing_desc = "Fair"
        elif seeing_score < 85:
            seeing_color = colors["green"]
            seeing_desc = "Good"
        else:
            seeing_color = colors["green"]
            seeing_desc = "Excellent"

        seeing_label = self._create_label(f"Seeing: {seeing_score:.0f}/100 ({seeing_desc})", seeing_color)
        self.seeing_layout.addWidget(seeing_label)

        # Observing Status
        if status == "excellent" or status == "good":
            status_color = colors["green"]
        elif status == "fair":
            status_color = colors["yellow"]
        else:
            status_color = colors["red"]

        status_label = self._create_label(f"Status: {status.title()}", status_color)
        self.seeing_layout.addWidget(status_label)

        # Warning
        if warning and warning != "Good observing conditions":
            warning_label = self._create_label(f"⚠ {warning}", colors["yellow"])
            self.seeing_layout.addWidget(warning_label)

        self.seeing_layout.addStretch()

    def _update_space_weather(self, space_weather: SpaceWeatherConditions | None, colors: dict[str, str]) -> None:
        """Update space weather section."""
        self._clear_layout(self.space_weather_layout)

        if space_weather is None:
            label = QLabel("Space weather data unavailable")
            label.setStyleSheet(f"color: {colors['text_dim']};")
            self.space_weather_layout.addWidget(label)
            self.space_weather_layout.addStretch()
            return
        self.space_weather_labels = {}

        # Check if space_weather is None or has no data
        has_data = False
        if space_weather:
            # Check if any field has a value
            has_data = any(
                [
                    space_weather.kp_index is not None,
                    space_weather.ap_index is not None,
                    space_weather.solar_wind_speed is not None,
                    space_weather.solar_wind_bt is not None,
                    space_weather.solar_wind_bz is not None,
                    space_weather.solar_wind_density is not None,
                    space_weather.radio_flux_107 is not None,
                    space_weather.xray_flux is not None,
                    space_weather.xray_class is not None,
                    space_weather.r_scale is not None,
                    space_weather.s_scale is not None,
                    space_weather.g_scale is not None,
                ]
            )

        if not has_data:
            error_label = self._create_label("Space weather data unavailable", colors["text_dim"])
            self.space_weather_layout.addWidget(error_label)
            self.space_weather_layout.addStretch()
            return

        # Kp Index
        if space_weather.kp_index is not None:
            kp = space_weather.kp_index
            if kp < 3:
                kp_color = colors["green"]
            elif kp < 5:
                kp_color = colors["yellow"]
            else:
                kp_color = colors["red"]
            kp_label = QLabel(f"Kp Index: {kp:.1f}")
            kp_label.setStyleSheet(f"color: {kp_color}; margin-bottom: 4px;")
            self.space_weather_layout.addWidget(kp_label)

        # Ap Index
        if space_weather.ap_index is not None:
            ap_label = QLabel(f"Ap Index: {space_weather.ap_index:.0f}")
            ap_label.setStyleSheet(f"color: {colors['text']}; margin-bottom: 4px;")
            self.space_weather_layout.addWidget(ap_label)

        # Solar Wind Speed
        if space_weather.solar_wind_speed is not None:
            sw_label = QLabel(f"Solar Wind: {space_weather.solar_wind_speed:.0f} km/s")
            sw_label.setStyleSheet(f"color: {colors['text']}; margin-bottom: 4px;")
            self.space_weather_layout.addWidget(sw_label)

        # Solar Wind Bz
        if space_weather.solar_wind_bz is not None:
            bz = space_weather.solar_wind_bz
            if bz < -5:
                bz_color = colors["green"]
                bz_desc = " (favorable for aurora)"
            else:
                bz_color = colors["text"]
                bz_desc = ""
            bz_label = QLabel(f"Bz: {bz:.1f} nT{bz_desc}")
            bz_label.setStyleSheet(f"color: {bz_color}; margin-bottom: 4px;")
            self.space_weather_layout.addWidget(bz_label)

        # X-ray Flux
        if space_weather.xray_flux is not None:
            xray_label = QLabel(f"X-ray Flux: {space_weather.xray_flux:.2e} W/m²")
            xray_label.setStyleSheet(f"color: {colors['text']}; margin-bottom: 4px;")
            self.space_weather_layout.addWidget(xray_label)

        # X-ray Class
        if space_weather.xray_class:
            xray_class_label = QLabel(f"X-ray Class: {space_weather.xray_class}")
            xray_class_label.setStyleSheet(f"color: {colors['text']}; margin-bottom: 4px;")
            self.space_weather_layout.addWidget(xray_class_label)

        # Radio Flux
        if space_weather.radio_flux_107 is not None:
            radio_label = QLabel(f"Radio Flux (10.7cm): {space_weather.radio_flux_107:.0f} sfu")
            radio_label.setStyleSheet(f"color: {colors['text']}; margin-bottom: 4px;")
            self.space_weather_layout.addWidget(radio_label)

        # G-Scale (Geomagnetic Storm)
        if space_weather.g_scale:
            g_level = space_weather.g_scale.level
            if g_level >= 3:
                g_color = colors["red"]
            elif g_level >= 1:
                g_color = colors["yellow"]
            else:
                g_color = colors["green"]
            g_label = QLabel(f"Geomagnetic: G{space_weather.g_scale.level} - {space_weather.g_scale.description}")
            g_label.setStyleSheet(f"color: {g_color}; margin-bottom: 4px;")
            self.space_weather_layout.addWidget(g_label)

        # R-Scale (Radio Blackout)
        if space_weather.r_scale:
            r_level = space_weather.r_scale.level
            if r_level >= 3:
                r_color = colors["red"]
            elif r_level >= 1:
                r_color = colors["yellow"]
            else:
                r_color = colors["green"]
            r_label = QLabel(f"Radio Blackout: R{space_weather.r_scale.level} - {space_weather.r_scale.description}")
            r_label.setStyleSheet(f"color: {r_color}; margin-bottom: 4px;")
            self.space_weather_layout.addWidget(r_label)

        # Aurora Opportunity (based on Kp and Bz)
        if space_weather.kp_index is not None and space_weather.solar_wind_bz is not None:
            kp = space_weather.kp_index
            bz = space_weather.solar_wind_bz
            if kp >= 5 and bz < -5:
                aurora_label = QLabel("🌟 Aurora Opportunity!")
                aurora_label.setStyleSheet(f"color: {colors['green']}; margin-bottom: 4px; font-weight: bold;")
                self.space_weather_layout.addWidget(aurora_label)

        self.space_weather_layout.addStretch()

    def close_event(self, event: QCloseEvent) -> None:
        """Stop timer when dialog is closed."""
        self.refresh_timer.stop()
        super().closeEvent(event)
