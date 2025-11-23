"""
Dialog to display Milky Way visibility information with tabs for next, tonight, and when.
"""

import asyncio
import concurrent.futures
import logging
import threading
from collections.abc import Coroutine
from datetime import datetime
from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QProgressDialog,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


if TYPE_CHECKING:
    from celestron_nexstar.api.events.milky_way import MilkyWayForecast, MilkyWayOpportunity
    from celestron_nexstar.api.location.observer import ObserverLocation


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


class MilkyWayInfoDialog(QDialog):
    """Dialog to display Milky Way visibility information with tabs."""

    def __init__(self, parent: QWidget | None = None, progress: QProgressDialog | None = None) -> None:
        """Initialize the Milky Way info dialog."""
        super().__init__(parent)
        self.setWindowTitle("Milky Way Visibility")
        self.setMinimumWidth(700)
        self.setMinimumHeight(500)
        self.resize(900, 700)  # Set reasonable default size

        # Create layout
        layout = QVBoxLayout(self)

        # Create tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Get monospace font from application property, fallback to system fonts
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        monospace_font = app.property("monospace_font") if app and app.property("monospace_font") else None
        self._font_family = (
            f"'{monospace_font}', 'Courier New', 'Consolas', 'Monaco', 'Menlo', monospace"
            if monospace_font
            else "'Courier New', 'Consolas', 'Monaco', 'Menlo', monospace"
        )

        # Create tabs
        self._create_next_tab()
        self._create_tonight_tab()
        self._create_when_tab()

        # Add button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        # Load all tab data upfront
        if progress:
            progress.setLabelText("Loading next opportunities...")
            QApplication.processEvents()
        self._load_next_info()

        if progress:
            progress.setLabelText("Loading tonight visibility...")
            QApplication.processEvents()
        self._load_tonight_info()
        self._tonight_loaded = True

        if progress:
            progress.setLabelText("Loading visibility windows...")
            QApplication.processEvents()
        self._load_when_info()
        self._when_loaded = True

    def _create_next_tab(self) -> None:
        """Create the next opportunities tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.next_text = QTextEdit()
        self.next_text.setReadOnly(True)
        self.next_text.setAcceptRichText(True)
        self.next_text.setStyleSheet(
            f"""
            QTextEdit {{
                font-family: {self._font_family};
                background-color: transparent;
                border: none;
            }}
        """
        )
        layout.addWidget(self.next_text)

        self.tab_widget.addTab(tab, "Next")

    def _create_tonight_tab(self) -> None:
        """Create the tonight visibility tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.tonight_text = QTextEdit()
        self.tonight_text.setReadOnly(True)
        self.tonight_text.setAcceptRichText(True)
        self.tonight_text.setStyleSheet(
            f"""
            QTextEdit {{
                font-family: {self._font_family};
                background-color: transparent;
                border: none;
            }}
        """
        )
        layout.addWidget(self.tonight_text)

        self.tab_widget.addTab(tab, "Tonight")

    def _create_when_tab(self) -> None:
        """Create the when visibility windows tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.when_text = QTextEdit()
        self.when_text.setReadOnly(True)
        self.when_text.setAcceptRichText(True)
        self.when_text.setStyleSheet(
            f"""
            QTextEdit {{
                font-family: {self._font_family};
                background-color: transparent;
                border: none;
            }}
        """
        )
        layout.addWidget(self.when_text)

        self.tab_widget.addTab(tab, "When")

    def _on_tab_changed(self, index: int) -> None:
        """Handle tab change event."""
        # All data is now loaded upfront, so no action needed
        pass

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
            "bright_green": "#81c784" if is_dark else "#66bb6a",
            "yellow": "#ffc107" if is_dark else "#f57c00",
            "red": "#f44336" if is_dark else "#c62828",
            "error": "#f44336" if is_dark else "#c62828",
        }

    def _format_local_time(self, dt: datetime, lat: float, lon: float) -> str:
        """Format datetime in local timezone."""
        from celestron_nexstar.api.core.utils import format_local_time

        return format_local_time(dt, lat, lon)

    def _load_next_info(self) -> None:
        """Load next opportunities information."""
        colors = self._get_theme_colors()

        try:
            from celestron_nexstar.api.events.milky_way import get_next_milky_way_opportunity
            from celestron_nexstar.api.location.observer import get_observer_location

            location = get_observer_location()
            if not location:
                self.next_text.setHtml(
                    f"<p><span style='color: {colors['error']};'><b>Error:</b> No observer location set. Use 'nexstar location set' to configure your location.</span></p>"
                )
                return

            months = 12  # Default
            min_score = 0.5  # Default

            opportunities, month_data_source = get_next_milky_way_opportunity(
                location, months_ahead=months, min_score=min_score
            )

            html_content = self._format_next_content(opportunities, location, months, month_data_source, colors)
            self.next_text.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading next Milky Way info: {e}", exc_info=True)
            self.next_text.setHtml(
                f"<p><span style='color: {colors['error']};'><b>Error:</b> Failed to load next opportunities: {e}</span></p>"
            )

    def _load_tonight_info(self) -> None:
        """Load tonight visibility information."""
        colors = self._get_theme_colors()

        try:
            from celestron_nexstar.api.events.milky_way import check_milky_way_visibility
            from celestron_nexstar.api.location.observer import get_observer_location

            location = get_observer_location()
            if not location:
                self.tonight_text.setHtml(
                    f"<p><span style='color: {colors['error']};'><b>Error:</b> No observer location set. Use 'nexstar location set' to configure your location.</span></p>"
                )
                return

            forecast = check_milky_way_visibility(location)

            html_content = self._format_tonight_content(forecast, location, colors)
            self.tonight_text.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading tonight Milky Way info: {e}", exc_info=True)
            self.tonight_text.setHtml(
                f"<p><span style='color: {colors['error']};'><b>Error:</b> Failed to load tonight visibility: {e}</span></p>"
            )

    def _load_when_info(self) -> None:
        """Load visibility windows information."""
        colors = self._get_theme_colors()

        try:
            from celestron_nexstar.api.events.milky_way import get_milky_way_visibility_windows
            from celestron_nexstar.api.location.observer import get_observer_location

            location = get_observer_location()
            if not location:
                self.when_text.setHtml(
                    f"<p><span style='color: {colors['error']};'><b>Error:</b> No observer location set. Use 'nexstar location set' to configure your location.</span></p>"
                )
                return

            days = 7  # Default
            windows = get_milky_way_visibility_windows(location, days=days)

            html_content = self._format_when_content(windows, location, days, colors)
            self.when_text.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading when Milky Way info: {e}", exc_info=True)
            self.when_text.setHtml(
                f"<p><span style='color: {colors['error']};'><b>Error:</b> Failed to load visibility windows: {e}</span></p>"
            )

    def _format_next_content(
        self,
        opportunities: list["MilkyWayOpportunity"],
        location: "ObserverLocation",
        months: int,
        month_data_source: dict[int, bool],
        colors: dict[str, str],
    ) -> list[str]:
        """Format next opportunities content as HTML."""
        html_content = []
        html_content.append(
            f"<style>h2 {{ color: {colors['header']}; margin-top: 1em; margin-bottom: 0.5em; }}</style>"
        )

        location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

        # Header
        html_content.append(
            f"<p><span style='color: {colors['header']}; font-size: 14pt; font-weight: bold;'>Next Milky Way Viewing Opportunities for {location_name}</span></p>"
        )
        html_content.append(
            f"<p style='color: {colors['text_dim']};'>Forecast based on moon phase cycles and seasonal patterns</p>"
        )
        html_content.append(
            f"<p style='color: {colors['text_dim']};'>Searching next {months} months, showing top {min(10, len(opportunities))} opportunities</p>"
        )
        html_content.append("<br>")

        if not opportunities:
            html_content.append(
                f"<p><span style='color: {colors['yellow']};'>No Milky Way opportunities found above the score threshold.</span></p>"
            )
            html_content.append(
                f"<p style='color: {colors['text_dim']};'>This may be due to high light pollution or unfavorable conditions in the forecast period.</p>"
            )
            html_content.append(
                f"<p style='color: {colors['text_dim']};'>Try lowering --min-score or increasing --months to see more opportunities.</p>"
            )
            return html_content

        # Display opportunities table
        html_content.append("<h2>Viewing Opportunities</h2>")
        html_content.append("<table style='border-collapse: collapse; width: 100%; border: 1px solid #444;'>")
        html_content.append(
            f"<tr style='background-color: {colors['header']}; color: white;'>"
            "<th style='padding: 8px; text-align: left;'>Month</th>"
            "<th style='padding: 8px; text-align: left;'>Season</th>"
            "<th style='padding: 8px; text-align: right;'>Expected Score</th>"
            "<th style='padding: 8px; text-align: right;'>Moon Phase</th>"
            "<th style='padding: 8px; text-align: right;'>Galactic Center</th>"
            "<th style='padding: 8px; text-align: left;'>Confidence</th>"
            "<th style='padding: 8px; text-align: left;'>Notes</th>"
            "</tr>"
        )

        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

        for opp in opportunities[:10]:
            month_str = f"{month_names[opp.month - 1]} {opp.start_date.year}"

            # Format expected score with color and range if available
            score_pct = opp.expected_visibility_score * 100.0
            if opp.min_visibility_score is not None and opp.max_visibility_score is not None:
                min_pct = opp.min_visibility_score * 100.0
                max_pct = opp.max_visibility_score * 100.0
                if score_pct >= 70:
                    score_display = f"<span style='color: {colors['bright_green']}; font-weight: bold;'>{min_pct:.0f}-{max_pct:.0f}%</span>"
                elif score_pct >= 50:
                    score_display = f"<span style='color: {colors['green']};'>{min_pct:.0f}-{max_pct:.0f}%</span>"
                elif score_pct >= 30:
                    score_display = f"<span style='color: {colors['yellow']};'>{min_pct:.0f}-{max_pct:.0f}%</span>"
                else:
                    score_display = f"<span style='color: {colors['text_dim']};'>{min_pct:.0f}-{max_pct:.0f}%</span>"
            else:
                if score_pct >= 70:
                    score_display = (
                        f"<span style='color: {colors['bright_green']}; font-weight: bold;'>{score_pct:.0f}%</span>"
                    )
                elif score_pct >= 50:
                    score_display = f"<span style='color: {colors['green']};'>{score_pct:.0f}%</span>"
                elif score_pct >= 30:
                    score_display = f"<span style='color: {colors['yellow']};'>{score_pct:.0f}%</span>"
                else:
                    score_display = f"<span style='color: {colors['text_dim']};'>{score_pct:.0f}%</span>"

            # Format moon phase factor
            moon_pct = opp.moon_phase_factor * 100.0
            if moon_pct >= 80:
                moon_display = f"<span style='color: {colors['green']};'>{moon_pct:.0f}%</span>"
            elif moon_pct >= 50:
                moon_display = f"<span style='color: {colors['yellow']};'>{moon_pct:.0f}%</span>"
            else:
                moon_display = f"<span style='color: {colors['red']};'>{moon_pct:.0f}%</span>"

            # Format galactic center factor
            gc_pct = opp.galactic_center_factor * 100.0
            if gc_pct >= 80:
                gc_display = f"<span style='color: {colors['green']};'>{gc_pct:.0f}%</span>"
            elif gc_pct >= 50:
                gc_display = f"<span style='color: {colors['yellow']};'>{gc_pct:.0f}%</span>"
            else:
                gc_display = f"<span style='color: {colors['text_dim']};'>{gc_pct:.0f}%</span>"

            # Format confidence
            if opp.confidence == "high":
                conf_display = f"<span style='color: {colors['green']};'>High</span>"
            elif opp.confidence == "medium":
                conf_display = f"<span style='color: {colors['yellow']};'>Medium</span>"
            else:
                conf_display = f"<span style='color: {colors['text_dim']};'>Low</span>"

            # Truncate notes if too long
            notes_display = opp.notes[:60] + "..." if len(opp.notes) > 60 else opp.notes

            html_content.append(
                f"<tr style='border-bottom: 1px solid #444;'>"
                f"<td style='padding: 6px; color: {colors['cyan']};'>{month_str}</td>"
                f"<td style='padding: 6px; color: {colors['text']};'>{opp.season}</td>"
                f"<td style='padding: 6px; text-align: right;'>{score_display}</td>"
                f"<td style='padding: 6px; text-align: right;'>{moon_display}</td>"
                f"<td style='padding: 6px; text-align: right;'>{gc_display}</td>"
                f"<td style='padding: 6px;'>{conf_display}</td>"
                f"<td style='padding: 6px; color: {colors['text_dim']};'>{notes_display}</td>"
                "</tr>"
            )

        html_content.append("</table>")

        # Understanding the Scores
        html_content.append("<br>")
        html_content.append("<h2>Understanding the Scores</h2>")
        html_content.append(
            f"<ul style='margin-left: 20px; color: {colors['text']};'>"
            f"<li style='margin-bottom: 5px;'>Expected Score shows overall visibility quality (0-100%)</li>"
            f"<li style='margin-bottom: 5px;'>Score ranges (e.g., 45-55%) show best-case to worst-case based on cloud cover estimates</li>"
            f"<li style='margin-bottom: 5px;'>Narrower ranges (e.g., 45-55%) indicate higher confidence than wider ranges (e.g., 30-70%)</li>"
            f"<li style='margin-bottom: 5px;'>Moon Phase shows how dark the moon will be (higher is better)</li>"
            f"<li style='margin-bottom: 5px;'>Galactic Center shows how well-positioned the galactic center will be</li>"
            f"<li style='margin-bottom: 5px;'>Based on moon phase cycles, seasonal patterns, and climatological cloud cover estimates</li>"
            f"<li style='color: {colors['green']}; margin-bottom: 5px;'>✓ Opportunities within 14 days use actual weather forecasts for higher accuracy</li>"
            f"<li style='margin-bottom: 5px;'>Longer-term opportunities use historical data (p40-p60 percentile range for tighter predictions)</li>"
            "</ul>"
        )

        # Cloud Cover Data Source
        html_content.append("<br>")
        html_content.append("<h2>Cloud Cover Data Source</h2>")

        historical_months: list[int] = []
        seasonal_months: list[int] = []

        for month, used_historical in sorted(month_data_source.items()):
            if used_historical:
                historical_months.append(month)
            else:
                seasonal_months.append(month)

        if historical_months:
            month_strs = [month_names[m - 1] for m in historical_months]
            html_content.append(
                f"<p><span style='color: {colors['green']};'>✓ Historical data used for:</span> <span style='color: {colors['text_dim']};'>{', '.join(month_strs)}</span></p>"
            )
            html_content.append(
                f"<p style='color: {colors['text_dim']}; margin-left: 20px;'>Location-specific statistics from Open-Meteo (2000-present)</p>"
            )
            html_content.append(
                f"<p style='color: {colors['text_dim']}; margin-left: 20px;'>Using p40-p60 percentile range (tighter, more confident predictions)</p>"
            )

        if seasonal_months:
            month_strs = [month_names[m - 1] for m in seasonal_months]
            html_content.append(
                f"<p><span style='color: {colors['yellow']};'>⚠ Seasonal estimates used for:</span> <span style='color: {colors['text_dim']};'>{', '.join(month_strs)}</span></p>"
            )
            html_content.append(
                f"<p style='color: {colors['text_dim']}; margin-left: 20px;'>General seasonal cloud cover patterns (historical data not available)</p>"
            )

        if not month_data_source:
            html_content.append(
                f"<p style='color: {colors['text_dim']};'>No cloud cover data available for analyzed months</p>"
            )

        html_content.append(
            f"<p style='color: {colors['text_dim']};'>Historical data is checked first and cached in the database for future use</p>"
        )
        html_content.append(
            f"<p style='color: {colors['text_dim']};'>Use 'nexstar weather historical' to view historical cloud cover data for your location</p>"
        )

        # Visibility Level Calculation
        html_content.append("<br>")
        html_content.append("<h2>Visibility Level Calculation</h2>")
        html_content.append(
            f"<ul style='margin-left: 20px; color: {colors['text_dim']};'>"
            "<li>Excellent: score ≥ 70%</li>"
            "<li>Good: score ≥ 50%</li>"
            "<li>Fair: score ≥ 30%</li>"
            "<li>Poor: score ≥ 10%</li>"
            "<li>None: score < 10%</li>"
            "</ul>"
        )

        # Planning Tips
        html_content.append("<br>")
        html_content.append("<h2>Planning Tips</h2>")
        html_content.append(
            f"<ul style='margin-left: 20px; color: {colors['text']};'>"
            f"<li style='color: {colors['green']}; margin-bottom: 5px;'>Book travel during high-score months for best chances</li>"
            f"<li style='color: {colors['green']}; margin-bottom: 5px;'>Monitor 'nexstar milky-way when' as dates approach for specific forecasts</li>"
            f"<li style='color: {colors['green']}; margin-bottom: 5px;'>Check 'nexstar milky-way tonight' during your visit for real-time conditions</li>"
            f"<li style='color: {colors['yellow']}; margin-bottom: 5px;'>⚠ Even high-score months don't guarantee visibility - weather and timing matter</li>"
            "</ul>"
        )

        return html_content

    def _format_tonight_content(
        self, forecast: "MilkyWayForecast | None", location: "ObserverLocation", colors: dict[str, str]
    ) -> list[str]:
        """Format tonight visibility content as HTML."""
        html_content = []
        html_content.append(
            f"<style>h2 {{ color: {colors['header']}; margin-top: 1em; margin-bottom: 0.5em; }}</style>"
        )

        location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

        # Header
        html_content.append(
            f"<p><span style='color: {colors['header']}; font-size: 14pt; font-weight: bold;'>Milky Way Visibility for {location_name}</span></p>"
        )
        html_content.append(
            f"<p style='color: {colors['text_dim']};'>Milky Way visibility based on dark sky conditions, moon phase, and weather</p>"
        )
        html_content.append("<br>")

        if forecast is None:
            html_content.append(
                f"<p><span style='color: {colors['yellow']};'>⚠ Unable to calculate Milky Way visibility</span></p>"
            )
            html_content.append(
                f"<p style='color: {colors['text_dim']};'>This may be due to missing location or calculation errors.</p>"
            )
            html_content.append(f"<p style='color: {colors['text_dim']};'>Try again in a few minutes.</p>")
            return html_content

        # Main status
        if forecast.is_visible:
            html_content.append(
                f"<p><span style='color: {colors['bright_green']}; font-weight: bold; font-size: 12pt;'>✓ Milky Way is VISIBLE tonight!</span></p>"
            )
        else:
            html_content.append(
                f"<p style='color: {colors['text_dim']}; font-size: 12pt;'>○ Milky Way is not visible tonight</p>"
            )
        html_content.append("<br>")

        # Detailed information table
        html_content.append("<h2>Visibility Details</h2>")
        html_content.append("<table style='border-collapse: collapse; width: 100%; border: 1px solid #444;'>")

        # Visibility Score
        score_pct = forecast.visibility_score * 100.0

        # Visibility Level
        level_calc = {
            "excellent": " (score ≥ 70%)",
            "good": " (score ≥ 50%)",
            "fair": " (score ≥ 30%)",
            "poor": " (score ≥ 10%)",
            "none": " (score < 10%)",
        }
        vis_level_str = forecast.visibility_level.capitalize()
        vis_level_str += (
            f"<span style='color: {colors['text_dim']};'>{level_calc.get(forecast.visibility_level, '')}</span>"
        )

        if forecast.visibility_level == "excellent":
            vis_level_color = colors["bright_green"]
            vis_level_style = f"color: {vis_level_color}; font-weight: bold;"
        elif forecast.visibility_level == "good":
            vis_level_color = colors["green"]
            vis_level_style = f"color: {vis_level_color};"
        elif forecast.visibility_level == "fair" or forecast.visibility_level == "poor":
            vis_level_color = colors["yellow"]
            vis_level_style = f"color: {vis_level_color};"
        else:
            vis_level_color = colors["text_dim"]
            vis_level_style = f"color: {vis_level_color};"

        html_content.append(
            f"<tr style='border-bottom: 1px solid #444;'>"
            f"<td style='padding: 6px; color: {colors['cyan']}; font-weight: bold;'>Visibility Level</td>"
            f"<td style='padding: 6px; {vis_level_style}'>{vis_level_str}</td>"
            "</tr>"
        )

        # Score
        if score_pct >= 70:
            score_color = colors["bright_green"]
            score_desc = " (Excellent conditions)"
            score_style = f"color: {score_color}; font-weight: bold;"
        elif score_pct >= 50:
            score_color = colors["green"]
            score_desc = " (Good conditions)"
            score_style = f"color: {score_color};"
        elif score_pct >= 30:
            score_color = colors["yellow"]
            score_desc = " (Fair conditions)"
            score_style = f"color: {score_color};"
        else:
            score_color = colors["red"]
            score_desc = " (Poor conditions)"
            score_style = f"color: {score_color};"

        html_content.append(
            f"<tr style='border-bottom: 1px solid #444;'>"
            f"<td style='padding: 6px; color: {colors['cyan']}; font-weight: bold;'>Visibility Score</td>"
            f"<td style='padding: 6px; {score_style}'>{score_pct:.1f}%{score_desc}</td>"
            "</tr>"
        )

        # Light pollution (Bortle class)
        if forecast.bortle_class is not None:
            bortle_colors_map = {
                1: (colors["bright_green"], "Class 1 - Excellent"),
                2: (colors["bright_green"], "Class 2 - Excellent"),
                3: (colors["green"], "Class 3 - Rural"),
                4: (colors["yellow"], "Class 4 - Rural/Suburban"),
                5: (colors["yellow"], "Class 5 - Suburban"),
                6: (colors["red"], "Class 6 - Bright Suburban"),
                7: (colors["red"], "Class 7 - Suburban/Urban"),
                8: (colors["red"], "Class 8 - City"),
                9: (colors["red"], "Class 9 - Inner City"),
            }
            bortle_color, bortle_text = bortle_colors_map.get(
                forecast.bortle_class, (colors["text"], f"Class {forecast.bortle_class}")
            )
            bortle_str = f"<span style='color: {bortle_color};'>{bortle_text}</span>"
            if forecast.sqm_value is not None:
                bortle_str += f" <span style='color: {colors['text_dim']};'>(SQM: {forecast.sqm_value:.2f})</span>"
            html_content.append(
                f"<tr style='border-bottom: 1px solid #444;'>"
                f"<td style='padding: 6px; color: {colors['cyan']}; font-weight: bold;'>Light Pollution (Bortle)</td>"
                f"<td style='padding: 6px;'>{bortle_str}</td>"
                "</tr>"
            )
        else:
            html_content.append(
                f"<tr style='border-bottom: 1px solid #444;'>"
                f"<td style='padding: 6px; color: {colors['cyan']}; font-weight: bold;'>Light Pollution (Bortle)</td>"
                f"<td style='padding: 6px; color: {colors['text_dim']};'>Unknown</td>"
                "</tr>"
            )

        # Darkness
        if forecast.is_dark:
            html_content.append(
                f"<tr style='border-bottom: 1px solid #444;'>"
                f"<td style='padding: 6px; color: {colors['cyan']}; font-weight: bold;'>Darkness</td>"
                f"<td style='padding: 6px; color: {colors['green']};'>✓ Dark enough (after sunset, before sunrise)</td>"
                "</tr>"
            )
        else:
            html_content.append(
                f"<tr style='border-bottom: 1px solid #444;'>"
                f"<td style='padding: 6px; color: {colors['cyan']}; font-weight: bold;'>Darkness</td>"
                f"<td style='padding: 6px; color: {colors['yellow']};'>✗ Too bright (need darkness for Milky Way viewing)</td>"
                "</tr>"
            )

        # Moon phase and position
        if forecast.moon_illumination is not None:
            moon_pct = forecast.moon_illumination * 100
            moon_status_parts = []

            if moon_pct < 1:
                moon_status_parts.append(f"<span style='color: {colors['green']};'>New Moon - ideal</span>")
            elif moon_pct < 30:
                moon_status_parts.append(f"<span style='color: {colors['green']};'>Crescent - good</span>")
            elif moon_pct < 70:
                moon_status_parts.append(f"<span style='color: {colors['yellow']};'>Quarter - moderate</span>")
            else:
                moon_status_parts.append(f"<span style='color: {colors['red']};'>Bright moon - poor</span>")

            # Add moon altitude information
            if forecast.moon_altitude is not None:
                if forecast.moon_altitude < 0:
                    moon_status_parts.append(
                        f"<span style='color: {colors['text_dim']};'>(below horizon - no impact)</span>"
                    )
                elif forecast.moon_altitude < 10:
                    moon_status_parts.append(
                        f"<span style='color: {colors['text_dim']};'>(low: {forecast.moon_altitude:.0f}° - minimal impact)</span>"
                    )
                elif forecast.moon_altitude < 30:
                    moon_status_parts.append(
                        f"<span style='color: {colors['text_dim']};'>(moderate: {forecast.moon_altitude:.0f}° - some impact)</span>"
                    )
                else:
                    moon_status_parts.append(
                        f"<span style='color: {colors['text_dim']};'>(high: {forecast.moon_altitude:.0f}° - significant impact)</span>"
                    )

            moon_display = f"{moon_pct:.0f}% illuminated " + " ".join(moon_status_parts)

            html_content.append(
                f"<tr style='border-bottom: 1px solid #444;'>"
                f"<td style='padding: 6px; color: {colors['cyan']}; font-weight: bold;'>Moon Phase</td>"
                f"<td style='padding: 6px;'>{moon_display}</td>"
                "</tr>"
            )

            # Add moonrise/moonset times if available
            if forecast.moonrise_time or forecast.moonset_time:
                moon_times = []
                if forecast.moonset_time:
                    moonset_str = self._format_local_time(forecast.moonset_time, location.latitude, location.longitude)
                    moon_times.append(f"Sets: {moonset_str}")
                if forecast.moonrise_time:
                    moonrise_str = self._format_local_time(
                        forecast.moonrise_time, location.latitude, location.longitude
                    )
                    moon_times.append(f"Rises: {moonrise_str}")
                if moon_times:
                    html_content.append(
                        f"<tr style='border-bottom: 1px solid #444;'>"
                        f"<td style='padding: 6px; color: {colors['cyan']}; font-weight: bold;'>Moon Times</td>"
                        f"<td style='padding: 6px;'>{', '.join(moon_times)}</td>"
                        "</tr>"
                    )
        else:
            html_content.append(
                f"<tr style='border-bottom: 1px solid #444;'>"
                f"<td style='padding: 6px; color: {colors['cyan']}; font-weight: bold;'>Moon Phase</td>"
                f"<td style='padding: 6px; color: {colors['text_dim']};'>Unknown</td>"
                "</tr>"
            )

        # Cloud cover
        if forecast.cloud_cover_percent is not None:
            if forecast.cloud_cover_percent < 20:
                cloud_str = (
                    f"<span style='color: {colors['green']};'>{forecast.cloud_cover_percent:.0f}% (Clear skies)</span>"
                )
            elif forecast.cloud_cover_percent < 50:
                cloud_str = f"<span style='color: {colors['yellow']};'>{forecast.cloud_cover_percent:.0f}% (Partly cloudy)</span>"
            else:
                cloud_str = f"<span style='color: {colors['red']};'>{forecast.cloud_cover_percent:.0f}% (Cloudy - blocks view)</span>"
            html_content.append(
                f"<tr style='border-bottom: 1px solid #444;'>"
                f"<td style='padding: 6px; color: {colors['cyan']}; font-weight: bold;'>Cloud Cover</td>"
                f"<td style='padding: 6px;'>{cloud_str}</td>"
                "</tr>"
            )
        else:
            html_content.append(
                f"<tr style='border-bottom: 1px solid #444;'>"
                f"<td style='padding: 6px; color: {colors['cyan']}; font-weight: bold;'>Cloud Cover</td>"
                f"<td style='padding: 6px; color: {colors['text_dim']};'>Unknown</td>"
                "</tr>"
            )

        # Galactic center
        if forecast.galactic_center_altitude is not None:
            if forecast.galactic_center_visible:
                if forecast.galactic_center_altitude >= 30:
                    gc_str = f"<span style='color: {colors['green']};'>{forecast.galactic_center_altitude:.1f}° (Excellent altitude)</span>"
                else:
                    gc_str = f"<span style='color: {colors['green']};'>{forecast.galactic_center_altitude:.1f}° (Visible)</span>"
            else:
                gc_str = f"<span style='color: {colors['yellow']};'>{forecast.galactic_center_altitude:.1f}° (Below horizon)</span>"
            html_content.append(
                f"<tr style='border-bottom: 1px solid #444;'>"
                f"<td style='padding: 6px; color: {colors['cyan']}; font-weight: bold;'>Galactic Center Altitude</td>"
                f"<td style='padding: 6px;'>{gc_str}</td>"
                "</tr>"
            )
        else:
            html_content.append(
                f"<tr style='border-bottom: 1px solid #444;'>"
                f"<td style='padding: 6px; color: {colors['cyan']}; font-weight: bold;'>Galactic Center Altitude</td>"
                f"<td style='padding: 6px; color: {colors['text_dim']};'>Unknown</td>"
                "</tr>"
            )

        # Peak viewing window
        if forecast.peak_viewing_start and forecast.peak_viewing_end:
            start_str = self._format_local_time(forecast.peak_viewing_start, location.latitude, location.longitude)
            end_str = self._format_local_time(forecast.peak_viewing_end, location.latitude, location.longitude)
            html_content.append(
                f"<tr style='border-bottom: 1px solid #444;'>"
                f"<td style='padding: 6px; color: {colors['cyan']}; font-weight: bold;'>Peak Viewing Window</td>"
                f"<td style='padding: 6px; color: {colors['green']};'>{start_str} - {end_str}</td>"
                "</tr>"
            )

        html_content.append("</table>")

        # Viewing tips
        html_content.append("<br>")
        html_content.append("<h2>Viewing Tips</h2>")
        if forecast.is_visible:
            html_content.append(
                f"<ul style='margin-left: 20px; color: {colors['text']};'>"
                f"<li style='color: {colors['green']}; margin-bottom: 5px;'>Look toward the southern horizon (Northern Hemisphere)</li>"
                f"<li style='color: {colors['green']}; margin-bottom: 5px;'>Best viewed with naked eye or binoculars</li>"
                f"<li style='color: {colors['green']}; margin-bottom: 5px;'>Allow 20-30 minutes for dark adaptation</li>"
                f"<li style='color: {colors['green']}; margin-bottom: 5px;'>The Milky Way appears as a faint band of light across the sky</li>"
            )
            if forecast.cloud_cover_percent and forecast.cloud_cover_percent > 50:
                html_content.append(
                    f"<li style='color: {colors['yellow']}; margin-bottom: 5px;'>⚠ Heavy cloud cover may block the view - check weather forecast</li>"
                )
            if forecast.moon_illumination and forecast.moon_illumination > 0.3:
                if forecast.moon_altitude is not None and forecast.moon_altitude < 0:
                    html_content.append(
                        f"<li style='color: {colors['green']}; margin-bottom: 5px;'>✓ Moon is below horizon - no interference</li>"
                    )
                else:
                    html_content.append(
                        f"<li style='color: {colors['yellow']}; margin-bottom: 5px;'>⚠ Bright moon may reduce visibility of faint Milky Way</li>"
                    )
                    if forecast.moonset_time:
                        moonset_str = self._format_local_time(
                            forecast.moonset_time, location.latitude, location.longitude
                        )
                        html_content.append(
                            f"<li style='color: {colors['text_dim']}; margin-bottom: 5px;'>Moon sets at {moonset_str} - better viewing after that time</li>"
                        )
            if forecast.bortle_class and forecast.bortle_class > 4:
                html_content.append(
                    f"<li style='color: {colors['yellow']}; margin-bottom: 5px;'>⚠ Light pollution may limit visibility - consider darker location</li>"
                )
            html_content.append("</ul>")
        else:
            html_content.append(f"<ul style='margin-left: 20px; color: {colors['text']};'>")
            if forecast.bortle_class and forecast.bortle_class > 4:
                html_content.append(
                    f"<li style='color: {colors['text_dim']}; margin-bottom: 5px;'>Light pollution (Bortle Class {forecast.bortle_class}) is too high for Milky Way viewing</li>"
                )
                html_content.append(
                    f"<li style='color: {colors['text_dim']}; margin-bottom: 5px;'>Need Bortle Class 4 or better (ideally 1-3) for good visibility</li>"
                )
            if not forecast.is_dark:
                html_content.append(
                    f"<li style='color: {colors['text_dim']}; margin-bottom: 5px;'>Wait until after sunset for darkness</li>"
                )
            if forecast.cloud_cover_percent and forecast.cloud_cover_percent > 50:
                html_content.append(
                    f"<li style='color: {colors['text_dim']}; margin-bottom: 5px;'>Heavy cloud cover is blocking visibility</li>"
                )
            if forecast.moon_illumination and forecast.moon_illumination > 0.3:
                if forecast.moon_altitude is not None and forecast.moon_altitude < 0:
                    html_content.append(
                        f"<li style='color: {colors['green']}; margin-bottom: 5px;'>✓ Moon is below horizon - no interference from moon</li>"
                    )
                else:
                    html_content.append(
                        f"<li style='color: {colors['text_dim']}; margin-bottom: 5px;'>Bright moon is washing out the faint Milky Way</li>"
                    )
                    html_content.append(
                        f"<li style='color: {colors['text_dim']}; margin-bottom: 5px;'>Best viewing is during New Moon or crescent phase</li>"
                    )
                    if forecast.moonset_time:
                        moonset_str = self._format_local_time(
                            forecast.moonset_time, location.latitude, location.longitude
                        )
                        html_content.append(
                            f"<li style='color: {colors['text_dim']}; margin-bottom: 5px;'>Moon sets at {moonset_str} - better viewing after that time</li>"
                        )
            if forecast.galactic_center_altitude is not None and not forecast.galactic_center_visible:
                html_content.append(
                    f"<li style='color: {colors['text_dim']}; margin-bottom: 5px;'>Galactic center is below the horizon</li>"
                )
                html_content.append(
                    f"<li style='color: {colors['text_dim']}; margin-bottom: 5px;'>In Northern Hemisphere, best viewing is during summer months</li>"
                )
            html_content.append("</ul>")

        html_content.append("<br>")
        html_content.append(
            f"<p style='color: {colors['text_dim']};'>💡 Tip: Milky Way visibility depends heavily on dark skies. Even Bortle Class 4 locations may show only faint traces.</p>"
        )
        html_content.append(
            f"<p style='color: {colors['text_dim']};'>💡 Tip: Summer months (June-August) offer the best views of the galactic center in the Northern Hemisphere.</p>"
        )
        html_content.append(
            f"<p style='color: {colors['text_dim']};'>💡 Tip: Use 'nexstar location light-pollution' to find darker locations near you.</p>"
        )

        # Visibility Level Calculation
        html_content.append("<br>")
        html_content.append("<h2>Visibility Level Calculation</h2>")
        html_content.append(
            f"<ul style='margin-left: 20px; color: {colors['text_dim']};'>"
            "<li>Excellent: score ≥ 70%</li>"
            "<li>Good: score ≥ 50%</li>"
            "<li>Fair: score ≥ 30%</li>"
            "<li>Poor: score ≥ 10%</li>"
            "<li>None: score < 10%</li>"
            "</ul>"
        )
        html_content.append(
            f"<p style='color: {colors['text_dim']};'>Use 'nexstar milky-way how' for detailed explanation of the scoring algorithm</p>"
        )

        return html_content

    def _format_when_content(
        self,
        windows: list[tuple[datetime, datetime, float, str]],
        location: "ObserverLocation",
        days: int,
        colors: dict[str, str],
    ) -> list[str]:
        """Format visibility windows content as HTML."""
        html_content = []
        html_content.append(
            f"<style>h2 {{ color: {colors['header']}; margin-top: 1em; margin-bottom: 0.5em; }}</style>"
        )

        location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

        # Header
        html_content.append(
            f"<p><span style='color: {colors['header']}; font-size: 14pt; font-weight: bold;'>Milky Way Visibility Windows for {location_name}</span></p>"
        )
        html_content.append(
            f"<p style='color: {colors['text_dim']};'>Forecast for the next {days} days based on dark sky conditions and moon phase</p>"
        )
        html_content.append("<br>")

        if not windows:
            html_content.append(
                f"<p><span style='color: {colors['yellow']};'>No Milky Way visibility windows found in the forecast period.</span></p>"
            )
            html_content.append(
                f"<p style='color: {colors['text_dim']};'>Conditions may not be favorable due to light pollution, moon phase, or weather.</p>"
            )
            html_content.append(
                f"<p style='color: {colors['text_dim']};'>💡 Tip: Milky Way requires dark skies (Bortle Class 4 or better) and dark moon.</p>"
            )
            html_content.append(
                f"<p style='color: {colors['text_dim']};'>💡 Tip: Try 'nexstar milky-way next' to find upcoming opportunities.</p>"
            )
            return html_content

        # Display windows in a table
        html_content.append("<h2>Visibility Windows</h2>")
        html_content.append("<table style='border-collapse: collapse; width: 100%; border: 1px solid #444;'>")
        html_content.append(
            f"<tr style='background-color: {colors['header']}; color: white;'>"
            "<th style='padding: 8px; text-align: left;'>Start Time</th>"
            "<th style='padding: 8px; text-align: left;'>End Time</th>"
            "<th style='padding: 8px; text-align: right;'>Duration</th>"
            "<th style='padding: 8px; text-align: right;'>Max Score</th>"
            "<th style='padding: 8px; text-align: left;'>Visibility</th>"
            "</tr>"
        )

        for start_time, end_time, max_score, visibility_level in windows:
            # Format times in local timezone
            start_str = self._format_local_time(start_time, location.latitude, location.longitude)
            end_str = self._format_local_time(end_time, location.latitude, location.longitude)

            # Calculate duration
            duration = end_time - start_time
            hours = duration.total_seconds() / 3600
            if hours < 24:
                duration_str = f"{hours:.1f}h"
            else:
                days_duration = hours / 24
                duration_str = f"{days_duration:.1f}d"

            # Format score with color
            score_pct = max_score * 100.0
            if score_pct >= 70:
                score_str = f"<span style='color: {colors['bright_green']}; font-weight: bold;'>{score_pct:.0f}%</span>"
            elif score_pct >= 50:
                score_str = f"<span style='color: {colors['green']};'>{score_pct:.0f}%</span>"
            elif score_pct >= 30:
                score_str = f"<span style='color: {colors['yellow']};'>{score_pct:.0f}%</span>"
            else:
                score_str = f"<span style='color: {colors['text_dim']};'>{score_pct:.0f}%</span>"

            # Format visibility level with calculation
            level_calc = {
                "excellent": " (≥70%)",
                "good": " (≥50%)",
                "fair": " (≥30%)",
                "poor": " (≥10%)",
                "none": " (<10%)",
            }
            vis_level_str = visibility_level.capitalize()
            vis_level_str += f"<span style='color: {colors['text_dim']};'>{level_calc.get(visibility_level, '')}</span>"

            if visibility_level == "excellent":
                vis_color = colors["bright_green"]
                vis_style = f"color: {vis_color}; font-weight: bold;"
            elif visibility_level == "good":
                vis_color = colors["green"]
                vis_style = f"color: {vis_color};"
            elif visibility_level == "fair" or visibility_level == "poor":
                vis_color = colors["yellow"]
                vis_style = f"color: {vis_color};"
            else:
                vis_color = colors["text_dim"]
                vis_style = f"color: {vis_color};"

            html_content.append(
                f"<tr style='border-bottom: 1px solid #444;'>"
                f"<td style='padding: 6px; color: {colors['cyan']};'>{start_str}</td>"
                f"<td style='padding: 6px; color: {colors['cyan']};'>{end_str}</td>"
                f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{duration_str}</td>"
                f"<td style='padding: 6px; text-align: right;'>{score_str}</td>"
                f"<td style='padding: 6px; {vis_style}'>{vis_level_str}</td>"
                "</tr>"
            )

        html_content.append("</table>")

        # Viewing tips
        html_content.append("<br>")
        html_content.append("<h2>Viewing Tips</h2>")
        html_content.append(
            f"<ul style='margin-left: 20px; color: {colors['text']};'>"
            f"<li style='color: {colors['green']}; margin-bottom: 5px;'>Look toward the southern horizon (Northern Hemisphere)</li>"
            f"<li style='color: {colors['green']}; margin-bottom: 5px;'>Best viewed with naked eye or binoculars</li>"
            f"<li style='color: {colors['green']}; margin-bottom: 5px;'>Allow 20-30 minutes for dark adaptation</li>"
            f"<li style='color: {colors['green']}; margin-bottom: 5px;'>Check weather forecast for cloud cover during these times</li>"
            f"<li style='color: {colors['yellow']}; margin-bottom: 5px;'>⚠ Forecasts are predictions and may change - check 'nexstar milky-way tonight' for current conditions</li>"
            "</ul>"
        )

        html_content.append("<br>")
        html_content.append(
            f"<p style='color: {colors['text_dim']};'>💡 Tip: Milky Way visibility depends heavily on dark skies and moon phase. Even Bortle Class 4 locations may show only faint traces.</p>"
        )

        # Visibility Level Calculation
        html_content.append("<br>")
        html_content.append("<h2>Visibility Level Calculation</h2>")
        html_content.append(
            f"<ul style='margin-left: 20px; color: {colors['text_dim']};'>"
            "<li>Excellent: score ≥ 70%</li>"
            "<li>Good: score ≥ 50%</li>"
            "<li>Fair: score ≥ 30%</li>"
            "<li>Poor: score ≥ 10%</li>"
            "<li>None: score < 10%</li>"
            "</ul>"
        )
        html_content.append(
            f"<p style='color: {colors['text_dim']};'>Use 'nexstar milky-way how' for detailed explanation of the scoring algorithm</p>"
        )

        return html_content
