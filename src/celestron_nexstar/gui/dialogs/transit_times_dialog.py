"""
Dialog to display transit times for celestial objects.
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


class TransitTimesInfoDialog(QDialog):
    """Dialog to display transit times for celestial objects."""

    def __init__(self, parent: QWidget | None = None, limit: int = 20) -> None:
        """Initialize the transit times dialog."""
        super().__init__(parent)
        self.setWindowTitle("Transit Times")
        self.setMinimumWidth(700)
        self.setMinimumHeight(600)

        self.limit = limit

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
                color: #00bcd4; /* Cyan for headers */
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

        # Load transit times information
        self._load_transit_times()

    def _load_transit_times(self) -> None:
        """Load transit times from the API and format for display."""
        try:
            from celestron_nexstar.api.core.utils import format_local_time
            from celestron_nexstar.api.database.database import get_database
            from celestron_nexstar.api.location.observer import get_observer_location
            from celestron_nexstar.api.observation.planning_utils import get_transit_times

            location = get_observer_location()
            if not location:
                self.info_text.setHtml(
                    "<p><span style='color: #f44336;'><b>Error:</b> No observer location set.</span></p>"
                )
                return

            # Get objects from database
            db = get_database()
            all_objects = asyncio.run(db.filter_objects(limit=self.limit * 2))  # Get more to filter

            # Get transit times
            transit_times = get_transit_times(all_objects[: self.limit], location.latitude, location.longitude)

            # Build HTML content
            html_content = []
            html_content.append(
                "<p><span style='color: #00bcd4; font-size: 14pt; font-weight: bold;'>Transit Times (Objects at Highest Point)</span></p>"
            )
            html_content.append("<br>")

            # Add explanatory text
            html_content.append(
                "<p style='color: #9e9e9e; margin-bottom: 15px; line-height: 1.5;'>"
                "<b>What are transit times?</b><br>"
                "Transit time is when a celestial object reaches its highest point in the sky (meridian crossing). "
                "This is the best time to observe an object because it's at maximum altitude, reducing atmospheric "
                "distortion and light pollution effects. Objects are sorted by transit time, showing when each will "
                "be at its peak visibility tonight."
                "</p>"
            )

            if not transit_times:
                html_content.append("<p><span style='color: #ffc107;'>No objects found with transit times.</span></p>")
                self.info_text.setHtml("\n".join(html_content))
                return

            # Create a table-like display
            html_content.append("<table style='width: 100%; border-collapse: collapse; margin-top: 10px;'>")
            html_content.append(
                "<tr style='border-bottom: 1px solid #444;'>"
                "<th style='text-align: left; padding: 8px; color: #00bcd4; font-weight: bold;'>Object</th>"
                "<th style='text-align: left; padding: 8px; color: #00bcd4; font-weight: bold;'>Transit Time</th>"
                "</tr>"
            )

            # Sort by transit time
            sorted_transits = sorted(transit_times.items(), key=lambda x: x[1])

            for obj_name, transit_time in sorted_transits:
                time_str = format_local_time(transit_time, location.latitude, location.longitude)
                html_content.append(
                    f"<tr style='border-bottom: 1px solid #333;'>"
                    f"<td style='padding: 8px; color: #00bcd4;'>{obj_name}</td>"
                    f"<td style='padding: 8px; color: #4caf50;'>{time_str}</td>"
                    f"</tr>"
                )

            html_content.append("</table>")

            self.info_text.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading transit times: {e}", exc_info=True)
            self.info_text.setHtml(
                f"<p><span style='color: #f44336;'><b>Error:</b> Failed to load transit times: {e}</span></p>"
            )
