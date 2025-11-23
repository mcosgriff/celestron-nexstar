"""
Dialog to display time-based observation recommendations.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

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


class TimeSlotsInfoDialog(QDialog):
    """Dialog to display time-based observation recommendations."""

    def __init__(
        self,
        parent: QWidget | None = None,
        start_hour: int = 20,
        end_hour: int = 23,
        interval: int = 1,
    ) -> None:
        """Initialize the time slots dialog."""
        super().__init__(parent)
        self.setWindowTitle("Time-Based Recommendations")
        self.setMinimumWidth(700)
        self.setMinimumHeight(600)

        self.start_hour = start_hour
        self.end_hour = end_hour
        self.interval = interval

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
                margin-top: 1em;
                margin-bottom: 0.5em;
            }}
        """
        )
        layout.addWidget(self.info_text)

        # Add button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        # Load time slots information
        self._load_time_slots()

    def _load_time_slots(self) -> None:
        """Load time slots and recommendations from the API and format for display."""
        colors = self._get_theme_colors()
        try:
            from celestron_nexstar.api.astronomy.solar_system import get_sun_info
            from celestron_nexstar.api.core.utils import format_local_time
            from celestron_nexstar.api.location.observer import get_observer_location
            from celestron_nexstar.api.observation.planning_utils import get_time_based_recommendations

            location = get_observer_location()
            if not location:
                self.info_text.setHtml(
                    f"<p><span style='color: {colors['error']};'><b>Error:</b> No observer location set.</span></p>"
                )
                return

            # Create time slots (same logic as CLI command)
            sun_info = get_sun_info(location.latitude, location.longitude)
            if not sun_info or not sun_info.sunset_time:
                self.info_text.setHtml(
                    f"<p><span style='color: {colors['error']};'><b>Error:</b> Could not determine sunset time.</span></p>"
                )
                return

            sunset = sun_info.sunset_time
            if sunset.tzinfo is None:
                sunset = sunset.replace(tzinfo=UTC)

            # Get current time
            now = datetime.now(UTC)
            if sunset.tzinfo and now.tzinfo is None:
                now = now.replace(tzinfo=UTC)

            # Convert to local time for proper hour comparison
            from celestron_nexstar.api.core.utils import get_local_timezone

            local_tz = get_local_timezone(location.latitude, location.longitude)
            if not local_tz:
                # Fallback: use UTC (cast to Any to allow timezone as fallback)
                local_tz = cast(Any, UTC)

            now_local = now.astimezone(local_tz)
            today_date_local = now_local.date()

            # Determine the start time:
            # 1. If current time is past start_hour, start from current hour (rounded up)
            # 2. Otherwise, start from start_hour
            # 3. But never start before sunset

            # Calculate desired start time based on start_hour in local time
            desired_start_local = datetime.combine(today_date_local, datetime.min.time()).replace(
                hour=self.start_hour, minute=0, second=0, microsecond=0, tzinfo=local_tz
            )
            desired_start = desired_start_local.astimezone(UTC).replace(tzinfo=UTC)

            # Compare in local time
            if now_local > desired_start_local:
                # Round current time up to next hour (in local time)
                current_hour = now_local.hour
                if now_local.minute > 0 or now_local.second > 0:
                    current_hour += 1
                if current_hour > 23:
                    # Move to next day at midnight
                    today_date_local += timedelta(days=1)
                    current_hour = 0
                current_local = datetime.combine(today_date_local, datetime.min.time()).replace(
                    hour=current_hour, minute=0, second=0, microsecond=0, tzinfo=local_tz
                )
                current = current_local.astimezone(UTC).replace(tzinfo=UTC)
            else:
                current = desired_start

            # Ensure we don't start before sunset
            # Only adjust if sunset is today (not tomorrow) in local time
            # If sunset is tomorrow, we're already past today's sunset, so no adjustment needed
            sunset_local = sunset.astimezone(local_tz)
            current_local_check = current.astimezone(local_tz)

            # Only adjust if sunset is on the same local date as now, and current is before sunset
            if sunset_local.date() == now_local.date() and current_local_check < sunset_local:
                # Round sunset up to next hour (in local time)
                sunset_hour = sunset_local.hour
                if sunset_local.minute > 0 or sunset_local.second > 0:
                    sunset_hour += 1
                sunset_date_local = sunset_local.date()
                if sunset_hour > 23:
                    # Move to next day at midnight
                    sunset_date_local += timedelta(days=1)
                    sunset_hour = 0
                current_local = datetime.combine(sunset_date_local, datetime.min.time()).replace(
                    hour=min(sunset_hour, 23), minute=0, second=0, microsecond=0, tzinfo=local_tz
                )
                current = current_local.astimezone(UTC).replace(tzinfo=UTC)

            start_date = current.date()
            max_slots = 24  # Safety limit to prevent infinite loops

            time_slots: list[datetime] = []
            while len(time_slots) < max_slots:
                # Stop if we've moved to the next day
                if current.date() > start_date:
                    break
                # Stop if we've gone past end_hour on the same day
                if current.hour > self.end_hour:
                    break
                # Add the time slot
                time_slots.append(current)
                # Move to next interval
                current += timedelta(hours=self.interval)

            # Get recommendations for each time slot
            recommendations = asyncio.run(
                get_time_based_recommendations(time_slots, location.latitude, location.longitude, "telescope")
            )

            # Build HTML content
            html_content = []
            html_content.append(
                f"<p><span style='color: {colors['header']}; font-size: 14pt; font-weight: bold;'>Time-Based Recommendations</span></p>"
            )
            html_content.append("<br>")

            # Add explanatory text
            html_content.append(
                f"<p style='color: {colors['text_dim']}; margin-bottom: 15px; line-height: 1.5;'>"
                "<b>What are time slots?</b><br>"
                "Time slots show recommended objects to observe at different times throughout the night. "
                "Each time slot displays the best objects to view during that hour, helping you plan your "
                "observing session. Objects are selected based on their visibility, altitude, and observing "
                "conditions at each specific time. This helps you maximize your observing time by knowing "
                "what to look for and when."
                "</p>"
            )

            if not time_slots:
                html_content.append(
                    f"<p><span style='color: {colors['text_dim']};'>No time slots available for the specified range.</span></p>"
                )
                self.info_text.setHtml("\n".join(html_content))
                return

            # Display each time slot with recommendations
            for time_slot in time_slots:
                time_str = format_local_time(time_slot, location.latitude, location.longitude)
                html_content.append(
                    f"<p><span style='color: {colors['header']}; font-weight: bold; font-size: 12pt;'>{time_str}</span></p>"
                )

                objects = recommendations.get(time_slot, [])
                if objects:
                    html_content.append("<ul style='margin-left: 20px; margin-top: 5px; margin-bottom: 10px;'>")
                    for obj in objects[:5]:  # Limit to 5 per time slot
                        html_content.append(f"<li style='color: {colors['text']}; margin-bottom: 3px;'>{obj.name}</li>")
                    html_content.append("</ul>")
                else:
                    html_content.append(
                        f"<p style='color: {colors['text_dim']}; margin-left: 20px; margin-top: 5px; margin-bottom: 10px;'>"
                        "No specific recommendations</p>"
                    )

            self.info_text.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading time slots: {e}", exc_info=True)
            self.info_text.setHtml(
                f"<p><span style='color: {colors['error']};'><b>Error:</b> Failed to load time slots: {e}</span></p>"
            )
