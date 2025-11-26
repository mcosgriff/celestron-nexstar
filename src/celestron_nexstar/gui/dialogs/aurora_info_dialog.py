"""
Dialog to display aurora borealis (Northern Lights) visibility information.
"""

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


class AuroraInfoDialog(QDialog):
    """Dialog to display aurora borealis visibility information."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the aurora info dialog."""
        super().__init__(parent)
        self.setWindowTitle("Aurora Borealis Visibility")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        self.resize(700, 600)  # Set reasonable default size

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

        # Set initial stylesheet (will be updated with theme colors in _load_aurora_info)
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

        # Load aurora information
        self._load_aurora_info()

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
            "header": "#00bcd4" if is_dark else "#00838f",  # Cyan for aurora
            "cyan": "#00bcd4" if is_dark else "#00838f",
            "green": "#4caf50" if is_dark else "#2e7d32",
            "bright_green": "#81c784" if is_dark else "#66bb6a",
            "red": "#f44336" if is_dark else "#c62828",
            "bright_red": "#e57373" if is_dark else "#ef5350",
            "yellow": "#ffc107" if is_dark else "#f57c00",
            "error": "#f44336" if is_dark else "#c62828",
        }

    def _format_kp_index(self, kp: float, colors: dict[str, str]) -> tuple[str, str]:
        """Format Kp index with color based on activity level."""
        if kp >= 8.0:
            return f"{kp:.1f}", f"color: {colors['bright_red']}; font-weight: bold;"
        elif kp >= 7.0:
            return f"{kp:.1f}", f"color: {colors['red']}; font-weight: bold;"
        elif kp >= 6.0:
            return f"{kp:.1f}", f"color: {colors['yellow']}; font-weight: bold;"
        elif kp >= 5.0:
            return f"{kp:.1f}", f"color: {colors['yellow']};"
        elif kp >= 4.0:
            return f"{kp:.1f}", f"color: {colors['cyan']};"
        elif kp >= 3.0:
            return f"{kp:.1f}", f"color: {colors['text_dim']};"
        else:
            return f"{kp:.1f}", f"color: {colors['text_dim']};"

    def _format_visibility_level(self, level: str, colors: dict[str, str]) -> tuple[str, str]:
        """Format visibility level with color."""
        level_map = {
            "very_high": ("Very High", f"color: {colors['bright_green']}; font-weight: bold;"),
            "high": ("High", f"color: {colors['green']}; font-weight: bold;"),
            "moderate": ("Moderate", f"color: {colors['yellow']}; font-weight: bold;"),
            "low": ("Low", f"color: {colors['yellow']};"),
            "none": ("None", f"color: {colors['text_dim']};"),
        }
        return level_map.get(level, (level, f"color: {colors['text']};"))

    def _load_aurora_info(self) -> None:
        """Load aurora visibility information from the API and format it for display."""
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
            from celestron_nexstar.api.events.aurora import check_aurora_visibility
            from celestron_nexstar.api.location.observer import get_observer_location

            # Get location
            location = get_observer_location()
            if not location:
                self.info_text.setHtml(
                    f"<p><span style='color: {colors['error']};'><b>Error:</b> No observer location set. Use 'nexstar location set' to configure your location.</span></p>"
                )
                return

            # Check aurora visibility
            forecast = check_aurora_visibility(location)

            # Build HTML content
            html_content = []
            html_content.append(
                f"<style>h2 {{ color: {colors['header']}; margin-top: 1em; margin-bottom: 0.5em; }}</style>"
            )

            location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"
            html_content.append(
                f"<p><span style='color: {colors['header']}; font-size: 14pt; font-weight: bold;'>Aurora Borealis Visibility for {location_name}</span></p>"
            )
            html_content.append(
                f"<p style='color: {colors['text_dim']};'>Northern Lights visibility based on geomagnetic activity (Kp index)</p>"
            )
            html_content.append("<br>")

            if forecast is None:
                html_content.append(
                    f"<p><span style='color: {colors['yellow']};'>⚠ Unable to fetch geomagnetic activity data (Kp index)</span></p>"
                )
                html_content.append(
                    f"<p style='color: {colors['text_dim']};'>This may be due to network issues or API unavailability.</p>"
                )
                html_content.append(f"<p style='color: {colors['text_dim']};'>Try again in a few minutes.</p>")
                self.info_text.setHtml("\n".join(html_content))
                return

            # Main status
            if forecast.is_visible:
                html_content.append(
                    f"<p><span style='color: {colors['bright_green']}; font-weight: bold; font-size: 12pt;'>✓ Aurora Borealis is VISIBLE tonight!</span></p>"
                )
            else:
                html_content.append(
                    f"<p style='color: {colors['text_dim']}; font-size: 12pt;'>○ Aurora Borealis is not visible tonight</p>"
                )
            html_content.append("<br>")

            # Detailed information table
            html_content.append("<h2>Forecast Details</h2>")
            html_content.append("<table style='border-collapse: collapse; width: 100%;'>")

            # Kp Index
            kp_str, kp_style = self._format_kp_index(forecast.kp_index, colors)
            kp_desc = ""
            if forecast.kp_index >= 8.0:
                kp_desc = " (Extreme)"
            elif forecast.kp_index >= 7.0:
                kp_desc = " (Very High)"
            elif forecast.kp_index >= 6.0:
                kp_desc = " (High)"
            elif forecast.kp_index >= 5.0:
                kp_desc = " (Moderate)"
            elif forecast.kp_index >= 4.0:
                kp_desc = " (Low-Moderate)"
            elif forecast.kp_index >= 3.0:
                kp_desc = " (Low)"
            else:
                kp_desc = " (Very Low)"

            html_content.append(
                f"<tr><td style='color: {colors['cyan']}; padding: 5px;'><b>Geomagnetic Activity (Kp)</b></td>"
                f"<td style='padding: 5px;'><span style='{kp_style}'>{kp_str}{kp_desc}</span></td></tr>"
            )

            # Add G-scale from space weather if available
            try:
                import asyncio

                from celestron_nexstar.api.events.space_weather import get_space_weather_conditions

                # Run async function - this is a sync entry point, so asyncio.run() is safe
                swx = asyncio.run(get_space_weather_conditions())
                if swx.g_scale:
                    g_scale_display = f"G{swx.g_scale.level} ({swx.g_scale.display_name})"
                    if swx.g_scale.level >= 3:
                        g_style = f"color: {colors['red']}; font-weight: bold;"
                    elif swx.g_scale.level >= 1:
                        g_style = f"color: {colors['yellow']};"
                    else:
                        g_style = f"color: {colors['green']};"
                    html_content.append(
                        f"<tr><td style='color: {colors['cyan']}; padding: 5px;'><b>NOAA G-Scale</b></td>"
                        f"<td style='padding: 5px;'><span style='{g_style}'>{g_scale_display}</span></td></tr>"
                    )

                # Add solar wind Bz if available
                if swx.solar_wind_bz is not None:
                    bz_display = f"{swx.solar_wind_bz:.1f} nT"
                    if swx.solar_wind_bz < -5:
                        bz_style = f"color: {colors['green']};"
                        bz_desc = " (favorable for aurora)"
                    elif swx.solar_wind_bz < 0:
                        bz_style = f"color: {colors['yellow']};"
                        bz_desc = ""
                    else:
                        bz_style = f"color: {colors['text']};"
                        bz_desc = ""
                    html_content.append(
                        f"<tr><td style='color: {colors['cyan']}; padding: 5px;'><b>Solar Wind Bz</b></td>"
                        f"<td style='padding: 5px;'><span style='{bz_style}'>{bz_display}{bz_desc}</span></td></tr>"
                    )
            except Exception:
                # Space weather data unavailable, skip
                pass

            # Visibility Probability
            prob_pct = forecast.visibility_probability * 100.0
            if prob_pct >= 70:
                prob_color = colors["bright_green"]
                prob_desc = " (Strong odds)"
            elif prob_pct >= 30:
                prob_color = colors["yellow"]
                prob_desc = " (Possible)"
            else:
                prob_color = colors["red"]
                prob_desc = " (Low odds)"

            html_content.append(
                f"<tr><td style='color: {colors['cyan']}; padding: 5px;'><b>Visibility Probability</b></td>"
                f"<td style='padding: 5px;'><span style='color: {prob_color};'>{prob_pct:.1f}%{prob_desc}</span></td></tr>"
            )

            # Visibility Level
            vis_str, vis_style = self._format_visibility_level(forecast.visibility_level, colors)
            html_content.append(
                f"<tr><td style='color: {colors['cyan']}; padding: 5px;'><b>Visibility Level</b></td>"
                f"<td style='padding: 5px;'><span style='{vis_style}'>{vis_str}</span></td></tr>"
            )

            # Auroral Boundary
            lat_diff = abs(location.latitude) - forecast.latitude_required
            if lat_diff < 0:
                boundary_style = f"color: {colors['yellow']};"
                boundary_text = f"Your latitude ({abs(location.latitude):.1f}°) is {abs(lat_diff):.1f}° below the boundary ({forecast.latitude_required:.1f}°)"
            else:
                boundary_style = f"color: {colors['green']};"
                boundary_text = f"Your latitude ({abs(location.latitude):.1f}°) is {lat_diff:.1f}° above the boundary ({forecast.latitude_required:.1f}°)"
            html_content.append(
                f"<tr><td style='color: {colors['cyan']}; padding: 5px;'><b>Auroral Boundary</b></td>"
                f"<td style='padding: 5px;'><span style='{boundary_style}'>{boundary_text}</span></td></tr>"
            )

            # Light pollution (Bortle class)
            if forecast.bortle_class is not None:
                bortle_colors_map = {
                    1: (f"color: {colors['bright_green']}; font-weight: bold;", "Class 1 - Excellent"),
                    2: (f"color: {colors['bright_green']};", "Class 2 - Excellent"),
                    3: (f"color: {colors['green']};", "Class 3 - Rural"),
                    4: (f"color: {colors['yellow']};", "Class 4 - Rural/Suburban"),
                    5: (f"color: {colors['yellow']};", "Class 5 - Suburban"),
                    6: (f"color: {colors['red']};", "Class 6 - Bright Suburban"),
                    7: (f"color: {colors['red']};", "Class 7 - Suburban/Urban"),
                    8: (f"color: {colors['red']}; font-weight: bold;", "Class 8 - City"),
                    9: (f"color: {colors['red']}; font-weight: bold;", "Class 9 - Inner City"),
                }
                bortle_style, bortle_str = bortle_colors_map.get(
                    forecast.bortle_class, (f"color: {colors['text']};", f"Class {forecast.bortle_class}")
                )
                if forecast.sqm_value is not None:
                    bortle_str += f" (SQM: {forecast.sqm_value:.2f})"
                html_content.append(
                    f"<tr><td style='color: {colors['cyan']}; padding: 5px;'><b>Light Pollution (Bortle)</b></td>"
                    f"<td style='padding: 5px;'><span style='{bortle_style}'>{bortle_str}</span></td></tr>"
                )
            else:
                html_content.append(
                    f"<tr><td style='color: {colors['cyan']}; padding: 5px;'><b>Light Pollution (Bortle)</b></td>"
                    f"<td style='padding: 5px;'><span style='color: {colors['text_dim']};'>Unknown</span></td></tr>"
                )

            # Darkness
            if forecast.is_dark:
                html_content.append(
                    f"<tr><td style='color: {colors['cyan']}; padding: 5px;'><b>Darkness</b></td>"
                    f"<td style='padding: 5px;'><span style='color: {colors['green']};'>✓ Dark enough (after sunset, before sunrise)</span></td></tr>"
                )
            else:
                html_content.append(
                    f"<tr><td style='color: {colors['cyan']}; padding: 5px;'><b>Darkness</b></td>"
                    f"<td style='padding: 5px;'><span style='color: {colors['yellow']};'>✗ Too bright (need darkness for aurora viewing)</span></td></tr>"
                )

            # Cloud cover
            if forecast.cloud_cover_percent is not None:
                if forecast.cloud_cover_percent < 20:
                    cloud_color = colors["green"]
                    cloud_desc = " (Clear skies)"
                elif forecast.cloud_cover_percent < 50:
                    cloud_color = colors["yellow"]
                    cloud_desc = " (Partly cloudy)"
                else:
                    cloud_color = colors["red"]
                    cloud_desc = " (Cloudy - blocks aurora)"
                html_content.append(
                    f"<tr><td style='color: {colors['cyan']}; padding: 5px;'><b>Cloud Cover</b></td>"
                    f"<td style='padding: 5px;'><span style='color: {cloud_color};'>{forecast.cloud_cover_percent:.0f}%{cloud_desc}</span></td></tr>"
                )
            else:
                html_content.append(
                    f"<tr><td style='color: {colors['cyan']}; padding: 5px;'><b>Cloud Cover</b></td>"
                    f"<td style='padding: 5px;'><span style='color: {colors['text_dim']};'>Unknown</span></td></tr>"
                )

            # Moon phase
            if forecast.moon_illumination is not None:
                moon_pct = forecast.moon_illumination * 100
                if moon_pct < 30:
                    moon_color = colors["green"]
                    moon_desc = " (Dark moon - ideal)"
                elif moon_pct < 70:
                    moon_color = colors["yellow"]
                    moon_desc = " (Moderate brightness)"
                else:
                    moon_color = colors["red"]
                    moon_desc = " (Bright moon - may wash out aurora)"
                html_content.append(
                    f"<tr><td style='color: {colors['cyan']}; padding: 5px;'><b>Moon Phase</b></td>"
                    f"<td style='padding: 5px;'><span style='color: {moon_color};'>{moon_pct:.0f}% illuminated{moon_desc}</span></td></tr>"
                )
            else:
                html_content.append(
                    f"<tr><td style='color: {colors['cyan']}; padding: 5px;'><b>Moon Phase</b></td>"
                    f"<td style='padding: 5px;'><span style='color: {colors['text_dim']};'>Unknown</span></td></tr>"
                )

            # Peak viewing window
            if forecast.peak_viewing_start and forecast.peak_viewing_end:
                from celestron_nexstar.api.core.utils import format_local_time

                start_str = format_local_time(forecast.peak_viewing_start, location.latitude, location.longitude)
                end_str = format_local_time(forecast.peak_viewing_end, location.latitude, location.longitude)
                html_content.append(
                    f"<tr><td style='color: {colors['cyan']}; padding: 5px;'><b>Peak Viewing Window</b></td>"
                    f"<td style='padding: 5px;'><span style='color: {colors['green']};'>{start_str} - {end_str}</span></td></tr>"
                )

            # Forecast confidence
            if forecast.is_forecasted:
                html_content.append(
                    f"<tr><td style='color: {colors['cyan']}; padding: 5px;'><b>Data Source</b></td>"
                    f"<td style='padding: 5px;'><span style='color: {colors['yellow']};'>Forecasted (predicted)</span></td></tr>"
                )
            else:
                html_content.append(
                    f"<tr><td style='color: {colors['cyan']}; padding: 5px;'><b>Data Source</b></td>"
                    f"<td style='padding: 5px;'><span style='color: {colors['green']};'>Observed (current)</span></td></tr>"
                )

            html_content.append("</table>")

            # Viewing tips
            html_content.append("<br>")
            html_content.append("<h2>Viewing Tips</h2>")
            if forecast.is_visible:
                html_content.append(
                    f"<ul style='color: {colors['text']}; margin-left: 20px;'>"
                    f"<li style='color: {colors['green']}; margin-bottom: 5px;'>Look toward the northern horizon</li>"
                    f"<li style='color: {colors['green']}; margin-bottom: 5px;'>Aurora is best viewed with naked eye or binoculars</li>"
                    f"<li style='color: {colors['green']}; margin-bottom: 5px;'>Allow 15-20 minutes for dark adaptation</li>"
                    f"<li style='color: {colors['green']}; margin-bottom: 5px;'>Aurora can appear as green, red, purple, or white curtains/bands</li>"
                )
                if forecast.cloud_cover_percent and forecast.cloud_cover_percent > 50:
                    html_content.append(
                        f"<li style='color: {colors['yellow']}; margin-bottom: 5px;'>⚠ Heavy cloud cover may block the aurora - check weather forecast</li>"
                    )
                if forecast.moon_illumination and forecast.moon_illumination > 0.7:
                    html_content.append(
                        f"<li style='color: {colors['yellow']}; margin-bottom: 5px;'>⚠ Bright moon may reduce visibility of faint aurora</li>"
                    )
                html_content.append("</ul>")
            else:
                tips = []
                if forecast.latitude_required > abs(location.latitude):
                    tips.append(
                        f"<li style='color: {colors['text_dim']}; margin-bottom: 5px;'>Your location ({abs(location.latitude):.1f}°N) is too far south</li>"
                    )
                    # Calculate what Kp would be needed
                    needed_kp = None
                    lat_abs = abs(location.latitude)
                    if lat_abs < 40.0:
                        needed_kp = 9.0
                    elif lat_abs < 45.0:
                        needed_kp = 8.0
                    elif lat_abs < 50.0:
                        needed_kp = 7.0
                    elif lat_abs < 55.0:
                        needed_kp = 6.0
                    elif lat_abs < 60.0:
                        needed_kp = 5.0
                    elif lat_abs < 65.0:
                        needed_kp = 4.0
                    elif lat_abs < 70.0:
                        needed_kp = 3.0
                    else:
                        needed_kp = 2.0

                    if needed_kp:
                        tips.append(
                            f"<li style='color: {colors['text_dim']}; margin-bottom: 5px;'>To see aurora at your latitude, you need Kp ≥ {needed_kp:.0f}</li>"
                        )
                    tips.append(
                        f"<li style='color: {colors['text_dim']}; margin-bottom: 5px;'>Current Kp index ({forecast.kp_index:.1f}) requires latitude ≥ {forecast.latitude_required:.1f}°</li>"
                    )
                if not forecast.is_dark:
                    tips.append(
                        f"<li style='color: {colors['text_dim']}; margin-bottom: 5px;'>Wait until after sunset for darkness</li>"
                    )
                if forecast.cloud_cover_percent and forecast.cloud_cover_percent > 50:
                    tips.append(
                        f"<li style='color: {colors['text_dim']}; margin-bottom: 5px;'>Heavy cloud cover is blocking visibility</li>"
                    )
                if tips:
                    html_content.append(f"<ul style='margin-left: 20px;'>{''.join(tips)}</ul>")

            html_content.append("<br>")
            html_content.append(
                f"<p style='color: {colors['text_dim']};'>💡 Tip: Aurora activity can change quickly. Check again in 30-60 minutes for updates.</p>"
            )
            html_content.append(
                f"<p style='color: {colors['text_dim']};'>💡 Tip: Even if not visible now, geomagnetic storms can develop rapidly.</p>"
            )
            html_content.append(
                f"<p style='color: {colors['text_dim']};'>💡 Tip: Use 'nexstar space-weather status' for detailed space weather conditions.</p>"
            )

            self.info_text.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading aurora info: {e}", exc_info=True)
            self.info_text.setHtml(
                f"<p><span style='color: {colors['error']};'><b>Error:</b> Failed to load aurora information: {e}</span></p>"
            )
