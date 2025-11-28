"""
Observation Edit Dialog

Dialog to create or edit an observation log entry.
"""

import asyncio
import logging
from datetime import UTC
from typing import TYPE_CHECKING

from PySide6.QtCore import QDateTime
from PySide6.QtWidgets import (
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from celestron_nexstar.api.location.observer import get_observer_location
from celestron_nexstar.api.observations import (
    add_observation,
    get_observation,
    update_observation,
)


if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


class ObservationEditDialog(QDialog):
    """Dialog to create or edit an observation log entry."""

    def __init__(
        self,
        parent: QWidget | None = None,
        object_name: str | None = None,
        observation_id: int | None = None,
    ) -> None:
        """
        Initialize the observation edit dialog.

        Args:
            parent: Parent widget
            object_name: Object name for new observation (optional)
            observation_id: Observation ID for editing (optional)
        """
        super().__init__(parent)
        self.observation_id = observation_id
        self.object_name = object_name

        if observation_id:
            self.setWindowTitle("Edit Observation")
        else:
            self.setWindowTitle("New Observation")

        self.setMinimumWidth(600)
        self.setMinimumHeight(500)

        # Create layout
        layout = QVBoxLayout(self)

        # Form layout
        form_layout = QFormLayout()

        # Object name (only for new observations)
        if not observation_id:
            self.object_name_edit = QLineEdit()
            self.object_name_edit.setPlaceholderText("Enter object name (e.g., M31, Vega)")
            if object_name:
                self.object_name_edit.setText(object_name)
            form_layout.addRow("Object Name:", self.object_name_edit)

        # Date/Time
        self.date_time_edit = QDateTimeEdit()
        self.date_time_edit.setCalendarPopup(True)
        self.date_time_edit.setDateTime(QDateTime.currentDateTime())
        self.date_time_edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        form_layout.addRow("Date/Time:", self.date_time_edit)

        # Location
        location_widget = QWidget()
        location_layout = QVBoxLayout(location_widget)
        location_layout.setSpacing(8)

        self.location_name_edit = QLineEdit()
        self.location_name_edit.setPlaceholderText("Location name (optional)")
        location_layout.addWidget(self.location_name_edit)

        location_coords_layout = QHBoxLayout()
        location_coords_layout.setSpacing(10)

        lat_layout = QVBoxLayout()
        lat_layout.setSpacing(2)
        lat_layout.addWidget(QLabel("Latitude:"))
        self.location_lat_edit = QDoubleSpinBox()
        self.location_lat_edit.setRange(-90.0, 90.0)
        self.location_lat_edit.setDecimals(6)
        self.location_lat_edit.setSuffix("°")
        self.location_lat_edit.setSpecialValueText("Auto")
        self.location_lat_edit.setValue(-999)  # Special value for "not set"
        lat_layout.addWidget(self.location_lat_edit)
        location_coords_layout.addLayout(lat_layout)

        lon_layout = QVBoxLayout()
        lon_layout.setSpacing(2)
        lon_layout.addWidget(QLabel("Longitude:"))
        self.location_lon_edit = QDoubleSpinBox()
        self.location_lon_edit.setRange(-180.0, 180.0)
        self.location_lon_edit.setDecimals(6)
        self.location_lon_edit.setSuffix("°")
        self.location_lon_edit.setSpecialValueText("Auto")
        self.location_lon_edit.setValue(-999)  # Special value for "not set"
        lon_layout.addWidget(self.location_lon_edit)
        location_coords_layout.addLayout(lon_layout)

        location_button = QPushButton("Use Current\nLocation")
        location_button.clicked.connect(self._on_use_current_location)
        location_coords_layout.addWidget(location_button)
        location_coords_layout.addStretch()

        location_layout.addLayout(location_coords_layout)
        form_layout.addRow("Location:", location_widget)

        # Viewing conditions
        conditions_label = QLabel("Viewing Conditions")
        conditions_label.setStyleSheet("font-weight: bold;")
        form_layout.addRow(conditions_label)

        self.seeing_quality_spin = QSpinBox()
        self.seeing_quality_spin.setRange(1, 5)
        self.seeing_quality_spin.setSpecialValueText("Not set")
        self.seeing_quality_spin.setValue(0)  # 0 = not set
        form_layout.addRow("Seeing Quality (1-5):", self.seeing_quality_spin)

        self.transparency_spin = QSpinBox()
        self.transparency_spin.setRange(1, 5)
        self.transparency_spin.setSpecialValueText("Not set")
        self.transparency_spin.setValue(0)  # 0 = not set
        form_layout.addRow("Transparency (1-5):", self.transparency_spin)

        self.sky_brightness_spin = QDoubleSpinBox()
        self.sky_brightness_spin.setRange(10.0, 25.0)
        self.sky_brightness_spin.setDecimals(2)
        self.sky_brightness_spin.setSuffix(" mag/arcsec²")
        self.sky_brightness_spin.setSpecialValueText("Not set")
        self.sky_brightness_spin.setValue(0)  # 0 = not set
        form_layout.addRow("Sky Brightness (SQM):", self.sky_brightness_spin)

        # Current weather conditions display
        weather_widget = QWidget()
        weather_layout = QVBoxLayout(weather_widget)
        weather_layout.setSpacing(5)

        self.weather_display = QTextEdit()
        self.weather_display.setReadOnly(True)
        self.weather_display.setMaximumHeight(100)
        self.weather_display.setPlaceholderText("Loading current weather conditions...")
        weather_layout.addWidget(self.weather_display)

        self.weather_notes_edit = QPlainTextEdit()
        self.weather_notes_edit.setPlaceholderText("Additional weather notes (optional)")
        self.weather_notes_edit.setMaximumHeight(60)
        weather_layout.addWidget(self.weather_notes_edit)

        form_layout.addRow("Weather Conditions:", weather_widget)

        # Load current weather in background
        self._load_current_weather()

        # Equipment
        equipment_label = QLabel("Equipment")
        equipment_label.setStyleSheet("font-weight: bold;")
        form_layout.addRow(equipment_label)

        self.telescope_edit = QLineEdit()
        self.telescope_edit.setPlaceholderText("Telescope used (optional)")
        form_layout.addRow("Telescope:", self.telescope_edit)

        self.eyepiece_edit = QLineEdit()
        self.eyepiece_edit.setPlaceholderText("Eyepiece used (optional)")
        form_layout.addRow("Eyepiece:", self.eyepiece_edit)

        # Prepopulate with configured telescope (only for new observations)
        if not observation_id:
            self._prepopulate_equipment()

        self.filters_edit = QLineEdit()
        self.filters_edit.setPlaceholderText("Filters used (optional)")
        form_layout.addRow("Filters:", self.filters_edit)

        # Observation details
        details_label = QLabel("Observation Details")
        details_label.setStyleSheet("font-weight: bold;")
        form_layout.addRow(details_label)

        self.rating_spin = QSpinBox()
        self.rating_spin.setRange(1, 5)
        self.rating_spin.setSpecialValueText("Not set")
        self.rating_spin.setValue(0)  # 0 = not set
        form_layout.addRow("Rating (1-5 stars):", self.rating_spin)

        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setPlaceholderText("Observation notes (optional)")
        form_layout.addRow("Notes:", self.notes_edit)

        layout.addLayout(form_layout)

        # Button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self._on_save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Load existing observation if editing
        if observation_id:
            self._load_observation()
        else:
            # For new observations, try to use current location
            self._on_use_current_location()

    def _load_observation(self) -> None:
        """Load existing observation data."""
        if self.observation_id is None:
            return
        try:
            obs = asyncio.run(get_observation(self.observation_id))
            if not obs:
                QMessageBox.warning(self, "Error", "Observation not found.")
                self.reject()
                return

            # Date/Time
            obs_time = obs.observed_at
            local_time = obs_time.astimezone() if obs_time.tzinfo else obs_time
            qdt = QDateTime.fromSecsSinceEpoch(int(local_time.timestamp()))
            self.date_time_edit.setDateTime(qdt)

            # Location
            if obs.location_name:
                self.location_name_edit.setText(obs.location_name)
            if obs.location_lat is not None:
                self.location_lat_edit.setValue(obs.location_lat)
            if obs.location_lon is not None:
                self.location_lon_edit.setValue(obs.location_lon)

            # Viewing conditions
            if obs.seeing_quality is not None:
                self.seeing_quality_spin.setValue(obs.seeing_quality)
            if obs.transparency is not None:
                self.transparency_spin.setValue(obs.transparency)
            if obs.sky_brightness is not None:
                self.sky_brightness_spin.setValue(obs.sky_brightness)
            if obs.weather_notes:
                self.weather_notes_edit.setPlainText(obs.weather_notes)

            # Equipment
            if obs.telescope:
                self.telescope_edit.setText(obs.telescope)
            if obs.eyepiece:
                self.eyepiece_edit.setText(obs.eyepiece)
            if obs.filters:
                self.filters_edit.setText(obs.filters)

            # Details
            if obs.rating is not None:
                self.rating_spin.setValue(obs.rating)
            if obs.notes:
                self.notes_edit.setPlainText(obs.notes)
        except Exception as e:
            logger.error(f"Error loading observation: {e}", exc_info=True)
            QMessageBox.warning(self, "Error", f"Failed to load observation: {e}")

    def _prepopulate_equipment(self) -> None:
        """Prepopulate telescope and eyepiece from configured hardware."""
        try:
            from celestron_nexstar.api.observation.optics import get_current_configuration

            config = get_current_configuration()
            if config:
                if not self.telescope_edit.text().strip():
                    self.telescope_edit.setText(config.telescope.display_name)
                if not self.eyepiece_edit.text().strip():
                    eyepiece_name = config.eyepiece.name or f"{config.eyepiece.focal_length_mm}mm"
                    self.eyepiece_edit.setText(eyepiece_name)
        except Exception as e:
            logger.debug(f"Could not prepopulate equipment: {e}")

    def _load_current_weather(self) -> None:
        """Load current weather conditions asynchronously."""
        try:
            from celestron_nexstar.api.location.observer import get_observer_location
            from celestron_nexstar.api.location.weather import fetch_weather

            location = get_observer_location()
            if not location:
                self.weather_display.setPlainText("Location not configured")
                return

            # Fetch weather asynchronously
            async def _fetch() -> None:
                try:
                    weather = await fetch_weather(location)
                    if weather.error:
                        self.weather_display.setPlainText(f"Weather data unavailable: {weather.error}")
                        return

                    # Format weather information
                    weather_text = []
                    if weather.temperature_c is not None:
                        weather_text.append(f"Temperature: {weather.temperature_c:.1f}°F")
                    if weather.humidity_percent is not None:
                        weather_text.append(f"Humidity: {weather.humidity_percent:.0f}%")
                    if weather.cloud_cover_percent is not None:
                        weather_text.append(f"Cloud Cover: {weather.cloud_cover_percent:.0f}%")
                    if weather.wind_speed_ms is not None:
                        weather_text.append(f"Wind Speed: {weather.wind_speed_ms:.1f} mph")
                    if weather.visibility_km is not None:
                        weather_text.append(f"Visibility: {weather.visibility_km:.1f} km")
                    if weather.condition:
                        weather_text.append(f"Condition: {weather.condition}")

                    # Add seeing assessment
                    from celestron_nexstar.api.location.weather import (
                        assess_observing_conditions,
                        calculate_seeing_conditions,
                    )

                    seeing_score = calculate_seeing_conditions(weather)
                    status, warning = assess_observing_conditions(weather)
                    weather_text.append(f"\nSeeing Score: {seeing_score:.1f}/100")
                    weather_text.append(f"Observing Status: {status.title()}")
                    if warning:
                        weather_text.append(f"Note: {warning}")

                    self.weather_display.setPlainText("\n".join(weather_text))
                except Exception as e:
                    logger.error(f"Error loading weather: {e}", exc_info=True)
                    self.weather_display.setPlainText(f"Error loading weather: {e}")

            # Run async function
            asyncio.run(_fetch())
        except Exception as e:
            logger.warning(f"Could not load current weather: {e}")
            self.weather_display.setPlainText("Weather data unavailable")

    def _on_use_current_location(self) -> None:
        """Use current observer location."""
        try:
            location = get_observer_location()
            if location:
                self.location_lat_edit.setValue(location.latitude)
                self.location_lon_edit.setValue(location.longitude)
                if location.name:
                    self.location_name_edit.setText(location.name)
        except Exception as e:
            logger.warning(f"Could not get current location: {e}")

    def _on_save(self) -> None:
        """Save observation."""
        try:
            # Get date/time
            from datetime import datetime
            from typing import cast

            qdt = self.date_time_edit.dateTime()
            dt = cast(datetime, qdt.toPython())
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)

            # Get location (use None if special value)
            location_lat = None
            if self.location_lat_edit.value() != -999:
                location_lat = self.location_lat_edit.value()
            location_lon = None
            if self.location_lon_edit.value() != -999:
                location_lon = self.location_lon_edit.value()
            location_name = self.location_name_edit.text().strip() or None

            # Get viewing conditions (use None if 0/special value)
            seeing_quality = None
            if self.seeing_quality_spin.value() > 0:
                seeing_quality = self.seeing_quality_spin.value()
            transparency = None
            if self.transparency_spin.value() > 0:
                transparency = self.transparency_spin.value()
            sky_brightness = None
            if self.sky_brightness_spin.value() > 0:
                sky_brightness = self.sky_brightness_spin.value()
            weather_notes = self.weather_notes_edit.toPlainText().strip() or None

            # Get equipment
            telescope = self.telescope_edit.text().strip() or None
            eyepiece = self.eyepiece_edit.text().strip() or None
            filters = self.filters_edit.text().strip() or None

            # Get details
            rating = None
            if self.rating_spin.value() > 0:
                rating = self.rating_spin.value()
            notes = self.notes_edit.toPlainText().strip() or None

            if self.observation_id:
                # Update existing observation
                success = asyncio.run(
                    update_observation(
                        self.observation_id,
                        observed_at=dt,
                        location_lat=location_lat,
                        location_lon=location_lon,
                        location_name=location_name,
                        seeing_quality=seeing_quality,
                        transparency=transparency,
                        sky_brightness=sky_brightness,
                        weather_notes=weather_notes,
                        telescope=telescope,
                        eyepiece=eyepiece,
                        filters=filters,
                        notes=notes,
                        rating=rating,
                    )
                )
                if not success:
                    QMessageBox.warning(self, "Error", "Failed to update observation.")
                    return
            else:
                # Create new observation
                object_name = (
                    self.object_name_edit.text().strip() if hasattr(self, "object_name_edit") else self.object_name
                )
                if not object_name:
                    QMessageBox.warning(self, "Error", "Object name is required.")
                    return

                obs_id = asyncio.run(
                    add_observation(
                        object_name=object_name,
                        observed_at=dt,
                        location_lat=location_lat,
                        location_lon=location_lon,
                        location_name=location_name,
                        seeing_quality=seeing_quality,
                        transparency=transparency,
                        sky_brightness=sky_brightness,
                        weather_notes=weather_notes,
                        telescope=telescope,
                        eyepiece=eyepiece,
                        filters=filters,
                        notes=notes,
                        rating=rating,
                    )
                )
                if not obs_id:
                    QMessageBox.warning(self, "Error", "Failed to create observation.")
                    return

            self.accept()
        except Exception as e:
            logger.error(f"Error saving observation: {e}", exc_info=True)
            QMessageBox.warning(self, "Error", f"Failed to save observation: {e}")
