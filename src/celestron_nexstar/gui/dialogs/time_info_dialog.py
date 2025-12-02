"""
Time, Sun, and Moon Information Dialog

Shows current time, UTC time, moon rise/set, and sun rise/set times.
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from celestron_nexstar.api.astronomy.solar_system import get_moon_info, get_sun_info
from celestron_nexstar.api.core import format_local_time
from celestron_nexstar.api.location.observer import get_observer_location


if TYPE_CHECKING:
    from celestron_nexstar import NexStarTelescope


class TimeInfoDialog(QDialog):
    """Dialog showing time, sun, and moon information."""

    def __init__(
        self,
        parent: QWidget | None = None,
        telescope: "NexStarTelescope | None" = None,
    ) -> None:
        """Initialize time info dialog."""
        super().__init__(parent)
        self.setWindowTitle("Time, Sun & Moon Information")
        self.setMinimumWidth(350)
        self.resize(350, 300)  # Set initial size smaller

        self.telescope = telescope

        layout = QVBoxLayout(self)

        # Time information (at top, not in groupbox)
        time_form = QFormLayout()
        self.local_time_label = QLabel()
        time_form.addRow("Local Time:", self.local_time_label)

        self.utc_time_label = QLabel()
        time_form.addRow("UTC Time:", self.utc_time_label)

        layout.addLayout(time_form)

        # Sun information in groupbox
        sun_group = QGroupBox("Sun")
        sun_layout = QFormLayout()
        self.sunrise_label = QLabel()
        sun_layout.addRow("Sunrise:", self.sunrise_label)

        self.sunset_label = QLabel()
        sun_layout.addRow("Sunset:", self.sunset_label)

        sun_group.setLayout(sun_layout)
        layout.addWidget(sun_group)

        # Moon information in groupbox
        moon_group = QGroupBox("Moon")
        moon_layout = QFormLayout()
        self.moonrise_label = QLabel()
        moon_layout.addRow("Moonrise:", self.moonrise_label)

        self.moonset_label = QLabel()
        moon_layout.addRow("Moonset:", self.moonset_label)

        self.moon_phase_label = QLabel()
        moon_layout.addRow("Phase:", self.moon_phase_label)

        self.moon_illumination_label = QLabel()
        moon_layout.addRow("Illumination:", self.moon_illumination_label)

        moon_group.setLayout(moon_layout)
        layout.addWidget(moon_group)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        # Load information
        self._load_time_info()

    def _load_time_info(self) -> None:
        """Load time, sun, and moon information."""
        try:
            location = get_observer_location()
            now = datetime.now(UTC)

            # Local time
            local_time_str = format_local_time(now, location.latitude, location.longitude)
            self.local_time_label.setText(local_time_str)

            # UTC time
            utc_time_str = now.strftime("%Y-%m-%d %H:%M:%S UTC")
            self.utc_time_label.setText(utc_time_str)

            # Sun information
            sun_info = get_sun_info(location.latitude, location.longitude, now)
            if sun_info:
                if sun_info.sunrise_time:
                    sunrise_str = format_local_time(sun_info.sunrise_time, location.latitude, location.longitude)
                    self.sunrise_label.setText(sunrise_str)
                else:
                    self.sunrise_label.setText("Not available")

                if sun_info.sunset_time:
                    sunset_str = format_local_time(sun_info.sunset_time, location.latitude, location.longitude)
                    self.sunset_label.setText(sunset_str)
                else:
                    self.sunset_label.setText("Not available")
            else:
                self.sunrise_label.setText("Error calculating")
                self.sunset_label.setText("Error calculating")

            # Moon information
            moon_info = get_moon_info(location.latitude, location.longitude, now)
            if moon_info:
                if moon_info.moonrise_time:
                    moonrise_str = format_local_time(moon_info.moonrise_time, location.latitude, location.longitude)
                    self.moonrise_label.setText(moonrise_str)
                else:
                    self.moonrise_label.setText("Not available")

                if moon_info.moonset_time:
                    moonset_str = format_local_time(moon_info.moonset_time, location.latitude, location.longitude)
                    self.moonset_label.setText(moonset_str)
                else:
                    self.moonset_label.setText("Not available")

                # Moon phase
                phase_name = moon_info.phase_name.value
                self.moon_phase_label.setText(phase_name)

                # Moon illumination
                illumination_pct = moon_info.illumination * 100
                self.moon_illumination_label.setText(f"{illumination_pct:.1f}%")
            else:
                self.moonrise_label.setText("Error calculating")
                self.moonset_label.setText("Error calculating")
                self.moon_phase_label.setText("Error")
                self.moon_illumination_label.setText("Error")

        except Exception:
            # Set error messages
            self.local_time_label.setText("Error")
            self.utc_time_label.setText("Error")
            self.sunrise_label.setText("Error")
            self.sunset_label.setText("Error")
            self.moonrise_label.setText("Error")
            self.moonset_label.setText("Error")
            self.moon_phase_label.setText("Error")
            self.moon_illumination_label.setText("Error")
