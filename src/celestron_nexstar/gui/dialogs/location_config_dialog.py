"""
Location Configuration Dialog

Modal dialog that lets the user set the app's observer location via:
- Automatic detection (system services or IP)
- Address/location geocoding
- Manual latitude/longitude entry
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from celestron_nexstar.api.location.observer import (
    ObserverLocation,
    detect_location_automatically,
    enrich_location_with_elevation_feet,
    geocode_location,
    get_observer_location,
    set_observer_location,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _ResolvedLocation:
    location: ObserverLocation


class _DetectLocationThread(QThread):
    location_ready = Signal(object)  # _ResolvedLocation
    error_occurred = Signal(str)

    def run(self) -> None:
        try:
            loc = detect_location_automatically()
            loc = enrich_location_with_elevation_feet(loc)
            self.location_ready.emit(_ResolvedLocation(loc))
        except Exception as e:
            self.error_occurred.emit(str(e))


class _GeocodeLocationThread(QThread):
    location_ready = Signal(object)  # _ResolvedLocation
    error_occurred = Signal(str)

    def __init__(self, query: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._query = query

    def run(self) -> None:
        try:
            loc = geocode_location(self._query)
            loc = enrich_location_with_elevation_feet(loc)
            self.location_ready.emit(_ResolvedLocation(loc))
        except Exception as e:
            self.error_occurred.emit(str(e))


class LocationConfigDialog(QDialog):
    """Modal dialog to configure observer location."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Set Location")
        self.setMinimumWidth(560)
        self.setMinimumHeight(420)
        self.resize(620, 520)

        self._pending_location: ObserverLocation | None = None
        self._detect_thread: _DetectLocationThread | None = None
        self._geocode_thread: _GeocodeLocationThread | None = None

        layout = QVBoxLayout(self)

        header = QLabel("Observer Location")
        header.setStyleSheet("font-size: 14pt; font-weight: bold;")
        layout.addWidget(header)

        desc = QLabel(
            "This location is used for sky calculations (moon/planet positions, rise/set times, weather, etc.)."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        self.tabs.addTab(self._build_auto_tab(), "Auto Detect")
        self.tabs.addTab(self._build_address_tab(), "Address")
        self.tabs.addTab(self._build_coordinates_tab(), "Coordinates")

        # Buttons
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        self.button_box.rejected.connect(self.reject)
        self.button_box.accepted.connect(self._on_save)
        layout.addWidget(self.button_box)

        # Pre-fill manual fields from current location
        try:
            current = get_observer_location()
            self.lat_spin.setValue(current.latitude)
            self.lon_spin.setValue(current.longitude)
            self.elev_spin.setValue(max(0.0, float(current.elevation or 0.0)))
            if current.name:
                self.name_edit.setText(current.name)
        except Exception:
            pass

        self._update_preview(None)

    def _build_auto_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        info = QLabel(
            "Automatically detect your location using system location services (if available) or your IP address."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        row = QHBoxLayout()
        self.detect_btn = QPushButton("Detect Location")
        self.detect_btn.clicked.connect(self._on_detect_clicked)
        row.addWidget(self.detect_btn)
        row.addStretch()
        layout.addLayout(row)

        self.auto_status = QLabel("")
        self.auto_status.setWordWrap(True)
        layout.addWidget(self.auto_status)

        layout.addStretch()
        return w

    def _build_address_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        info = QLabel("Enter a city, address, or ZIP code to geocode.")
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        self.query_edit = QLineEdit()
        self.query_edit.setPlaceholderText('e.g. "Denver, CO" or "90210"')
        form.addRow("Search:", self.query_edit)
        layout.addLayout(form)

        row = QHBoxLayout()
        self.geocode_btn = QPushButton("Geocode")
        self.geocode_btn.clicked.connect(self._on_geocode_clicked)
        row.addWidget(self.geocode_btn)
        row.addStretch()
        layout.addLayout(row)

        self.geocode_status = QLabel("")
        self.geocode_status.setWordWrap(True)
        layout.addWidget(self.geocode_status)

        layout.addStretch()
        return w

    def _build_coordinates_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        info = QLabel("Manually enter coordinates.")
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        self.lat_spin = QDoubleSpinBox()
        self.lat_spin.setRange(-90.0, 90.0)
        self.lat_spin.setDecimals(6)
        self.lat_spin.setSingleStep(0.001)
        self.lat_spin.setSuffix(" °")
        self.lat_spin.valueChanged.connect(self._on_manual_changed)
        form.addRow("Latitude:", self.lat_spin)

        self.lon_spin = QDoubleSpinBox()
        self.lon_spin.setRange(-180.0, 180.0)
        self.lon_spin.setDecimals(6)
        self.lon_spin.setSingleStep(0.001)
        self.lon_spin.setSuffix(" °")
        self.lon_spin.valueChanged.connect(self._on_manual_changed)
        form.addRow("Longitude:", self.lon_spin)

        self.elev_spin = QDoubleSpinBox()
        self.elev_spin.setRange(0.0, 50000.0)
        self.elev_spin.setDecimals(0)
        self.elev_spin.setSingleStep(25.0)
        self.elev_spin.setSuffix(" ft")
        self.elev_spin.valueChanged.connect(self._on_manual_changed)
        form.addRow("Elevation:", self.elev_spin)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Optional name (e.g. Home)")
        self.name_edit.textChanged.connect(self._on_manual_changed)
        form.addRow("Name:", self.name_edit)

        layout.addLayout(form)
        layout.addStretch()
        return w

    def _set_busy(self, busy: bool) -> None:
        self.detect_btn.setEnabled(not busy)
        self.geocode_btn.setEnabled(not busy)
        self.query_edit.setEnabled(not busy)
        self.lat_spin.setEnabled(not busy)
        self.lon_spin.setEnabled(not busy)
        self.elev_spin.setEnabled(not busy)
        self.name_edit.setEnabled(not busy)
        self.button_box.button(QDialogButtonBox.StandardButton.Save).setEnabled(not busy)

    def _update_preview(self, location: ObserverLocation | None) -> None:
        if location is None:
            self.auto_status.setText("")
            self.geocode_status.setText("")
            self._pending_location = None
            return

        lat_dir = "N" if location.latitude >= 0 else "S"
        lon_dir = "E" if location.longitude >= 0 else "W"
        name = location.name or "Unnamed location"
        msg = f"Selected: {name}\nCoordinates: {abs(location.latitude):.4f}°{lat_dir}, {abs(location.longitude):.4f}°{lon_dir}"
        if location.elevation:
            msg += f"\nElevation: {location.elevation:.0f} ft"

        # Update whichever tab is active; also store as pending save value
        self.auto_status.setText(msg)
        self.geocode_status.setText(msg)
        self._pending_location = location

    def _on_detect_clicked(self) -> None:
        if self._detect_thread is not None:
            return
        self._set_busy(True)
        self.auto_status.setText("Detecting location…")
        thread = _DetectLocationThread(self)
        self._detect_thread = thread
        thread.location_ready.connect(self._on_location_resolved)
        thread.error_occurred.connect(self._on_location_error)
        thread.finished.connect(lambda: setattr(self, "_detect_thread", None))
        thread.start()

    def _on_geocode_clicked(self) -> None:
        query = self.query_edit.text().strip()
        if not query:
            QMessageBox.information(self, "Geocode", "Please enter an address, city, or ZIP code.")
            return
        if self._geocode_thread is not None:
            return
        self._set_busy(True)
        self.geocode_status.setText("Geocoding…")
        thread = _GeocodeLocationThread(query=query, parent=self)
        self._geocode_thread = thread
        thread.location_ready.connect(self._on_location_resolved)
        thread.error_occurred.connect(self._on_location_error)
        thread.finished.connect(lambda: setattr(self, "_geocode_thread", None))
        thread.start()

    def _on_manual_changed(self) -> None:
        # Only treat manual inputs as the pending selection when user is on Coordinates tab
        loc = ObserverLocation(
            latitude=float(self.lat_spin.value()),
            longitude=float(self.lon_spin.value()),
            elevation=float(self.elev_spin.value()),
            name=self.name_edit.text().strip() or None,
        )
        self._pending_location = loc

    def _on_location_resolved(self, resolved: object) -> None:
        self._set_busy(False)
        try:
            if isinstance(resolved, _ResolvedLocation):
                self._update_preview(resolved.location)
            else:
                self._update_preview(None)
        except Exception:
            self._update_preview(None)

    def _on_location_error(self, msg: str) -> None:
        self._set_busy(False)
        self.auto_status.setText(f"Failed: {msg}")
        self.geocode_status.setText(f"Failed: {msg}")
        self._pending_location = None

    def _on_save(self) -> None:
        try:
            # If on coordinates tab, use the manual values even if no explicit "change" event fired
            if self.tabs.currentIndex() == 2:
                self._on_manual_changed()

            if self._pending_location is None:
                QMessageBox.information(self, "Set Location", "No location selected yet.")
                return

            set_observer_location(self._pending_location, save=True)
            self.accept()
        except Exception as e:
            logger.error("Failed to save observer location", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to save location:\n{e!s}")
