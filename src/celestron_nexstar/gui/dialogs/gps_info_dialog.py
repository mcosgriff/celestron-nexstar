"""
GPS Information Dialog

Shows GPS information from telescope or user-set location.
"""

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from celestron_nexstar.api.location.observer import get_observer_location


if TYPE_CHECKING:
    from celestron_nexstar import NexStarTelescope


class GPSInfoDialog(QDialog):
    """Dialog showing GPS information from telescope or user location."""

    def __init__(
        self,
        parent: QWidget | None = None,
        telescope: "NexStarTelescope | None" = None,
    ) -> None:
        """Initialize GPS info dialog."""
        super().__init__(parent)
        self.setWindowTitle("GPS Information")
        self.setMinimumWidth(400)

        self.telescope = telescope

        layout = QVBoxLayout(self)

        # Create form layout for GPS information
        form_layout = QFormLayout()

        # Source
        source_label = QLabel()
        form_layout.addRow("Source:", source_label)

        # Latitude
        self.lat_label = QLabel()
        form_layout.addRow("Latitude:", self.lat_label)

        # Longitude
        self.lon_label = QLabel()
        form_layout.addRow("Longitude:", self.lon_label)

        # Elevation (if available)
        self.elevation_label = QLabel()
        form_layout.addRow("Elevation:", self.elevation_label)

        # Location name (from reverse geocoding)
        self.location_name_label = QLabel()
        form_layout.addRow("Location:", self.location_name_label)

        # Status
        self.status_label = QLabel()
        form_layout.addRow("Status:", self.status_label)

        layout.addLayout(form_layout)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        # Load GPS information
        self._load_gps_info(source_label)

    def _load_gps_info(self, source_label: QLabel) -> None:
        """Load GPS information from telescope or user location."""
        gps_lat: float | None = None
        gps_lon: float | None = None
        source = "User Configuration"
        status = "Using configured location"
        status_color = "blue"

        # Try to get GPS from telescope
        if self.telescope and self.telescope.protocol.is_open():
            try:
                location_result = self.telescope.get_location()
                if location_result:
                    lat = location_result.latitude
                    lon = location_result.longitude
                    # Check if GPS coordinates are valid (not 0,0)
                    if lat != 0.0 and lon != 0.0:
                        gps_lat = lat
                        gps_lon = lon
                        source = "Telescope GPS"
                        status = "GPS Active"
                        status_color = "green"
                    else:
                        source = "Telescope GPS (No Fix)"
                        status = "GPS searching or no signal"
                        status_color = "yellow"
            except Exception:
                source = "Telescope GPS (Error)"
                status = "Could not read GPS from telescope"
                status_color = "red"

        # Fallback to user location
        if gps_lat is None or gps_lon is None:
            try:
                location = get_observer_location()
                gps_lat = location.latitude
                gps_lon = location.longitude
                if source == "User Configuration":
                    status = "Using configured location"
                    status_color = "blue"
            except Exception:
                self.lat_label.setText("--")
                self.lon_label.setText("--")
                self.elevation_label.setText("--")
                self.location_name_label.setText("--")
                self.status_label.setText("No location available")
                self.status_label.setStyleSheet("color: red;")
                source_label.setText("None")
                return

        # Display coordinates
        self.lat_label.setText(f"{gps_lat:.6f}°")
        self.lon_label.setText(f"{gps_lon:.6f}°")

        # Get elevation if available
        elevation_text = "Not available"
        try:
            location = get_observer_location()
            if location.elevation is not None:
                elevation_text = f"{location.elevation:.0f} m"
        except Exception:
            pass  # Keep default "Not available"
        self.elevation_label.setText(elevation_text)

        # Reverse geocoding
        location_name = self._reverse_geocode(gps_lat, gps_lon)
        self.location_name_label.setText(location_name or "Unknown location")

        # Display source and status
        source_label.setText(source)
        self.status_label.setText(status)
        self.status_label.setStyleSheet(f"color: {status_color};")

    def _reverse_geocode(self, lat: float, lon: float) -> str | None:
        """Reverse geocode coordinates to get location name."""
        try:
            from geopy.geocoders import Nominatim

            geolocator = Nominatim(user_agent="celestron-nexstar")
            location = geolocator.reverse((lat, lon), timeout=5)
            if location:
                # Try to get a readable address
                address = location.raw.get("address", {})
                # Build location string from address components
                parts = []
                if "city" in address:
                    parts.append(address["city"])
                elif "town" in address:
                    parts.append(address["town"])
                elif "village" in address:
                    parts.append(address["village"])

                if "state" in address:
                    parts.append(address["state"])
                elif "region" in address:
                    parts.append(address["region"])

                if "country" in address:
                    parts.append(address["country"])

                if parts:
                    return ", ".join(parts)

                # Fallback to display_name
                display_name = location.raw.get("display_name")
                return str(display_name) if display_name else None
        except Exception:
            # Silently fail - reverse geocoding is optional
            pass
        return None
