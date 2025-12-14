"""
Optics Configuration Dialog

Modal dialog to change the active telescope model and eyepiece used for FOV/visibility calculations.
This updates the same persisted configuration used by the CLI (`nexstar optics config`).
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from celestron_nexstar.api.observation.optics import (
    COMMON_EYEPIECES,
    OpticalConfiguration,
    TelescopeModel,
    get_current_configuration,
    get_telescope_specs,
    set_current_configuration,
)


logger = logging.getLogger(__name__)


class OpticsConfigDialog(QDialog):
    """Modal dialog to edit telescope + eyepiece selection."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Optics Configuration")
        self.setMinimumWidth(520)
        self.setMinimumHeight(420)
        self.resize(560, 520)

        self._selected_telescope: TelescopeModel | None = None
        self._selected_eyepiece_key: str | None = None

        layout = QVBoxLayout(self)

        header = QLabel("Configure Telescope and Eyepiece")
        header.setStyleSheet("font-size: 14pt; font-weight: bold;")
        layout.addWidget(header)

        help_text = QLabel(
            "These settings are used for magnification, field-of-view calculations, and visibility filtering."
        )
        help_text.setWordWrap(True)
        layout.addWidget(help_text)

        # Telescope selector
        form = QFormLayout()
        self.telescope_combo = QComboBox()
        for model in TelescopeModel:
            specs = get_telescope_specs(model)
            self.telescope_combo.addItem(
                f"{specs.display_name} ({specs.aperture_mm:.0f}mm, f/{specs.focal_ratio:.1f})",
                model,
            )
        form.addRow("Telescope:", self.telescope_combo)
        layout.addLayout(form)

        # Eyepiece selector (radio list)
        eyepiece_label = QLabel("Eyepiece:")
        eyepiece_label.setStyleSheet("font-weight: bold; margin-top: 8px;")
        layout.addWidget(eyepiece_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(scroll, 1)

        eyepieces_widget = QWidget()
        eyepieces_layout = QVBoxLayout(eyepieces_widget)
        eyepieces_layout.setSpacing(6)
        scroll.setWidget(eyepieces_widget)

        self.eyepiece_radios: dict[str, QRadioButton] = {}

        # Preselect current config
        try:
            current = get_current_configuration()
            self._selected_telescope = current.telescope.model

            match_key: str | None = None
            for key, ep in COMMON_EYEPIECES.items():
                if (
                    abs(ep.focal_length_mm - current.eyepiece.focal_length_mm) < 0.1
                    and abs(ep.apparent_fov_deg - current.eyepiece.apparent_fov_deg) < 0.1
                ):
                    match_key = key
                    break
            self._selected_eyepiece_key = match_key or "25mm_plossl"
        except Exception:
            self._selected_telescope = TelescopeModel.NEXSTAR_6SE
            self._selected_eyepiece_key = "25mm_plossl"

        # Apply telescope selection
        if self._selected_telescope is not None:
            for i in range(self.telescope_combo.count()):
                data = self.telescope_combo.itemData(i)
                if isinstance(data, TelescopeModel) and data == self._selected_telescope:
                    self.telescope_combo.setCurrentIndex(i)
                    break
        self.telescope_combo.currentIndexChanged.connect(self._on_telescope_changed)

        # Eyepieces sorted by focal length (longest first)
        for key, ep in sorted(COMMON_EYEPIECES.items(), key=lambda kv: kv[1].focal_length_mm, reverse=True):
            radio = QRadioButton(ep.name or f"{ep.focal_length_mm:.0f}mm")
            radio.setToolTip(f"Focal Length: {ep.focal_length_mm}mm\nApparent FOV: {ep.apparent_fov_deg}°")
            radio.setChecked(key == self._selected_eyepiece_key)
            radio.toggled.connect(lambda checked, k=key: self._on_eyepiece_selected(k) if checked else None)
            self.eyepiece_radios[key] = radio
            eyepieces_layout.addWidget(radio)
        eyepieces_layout.addStretch()

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self._on_save)
        layout.addWidget(buttons)

    def _on_telescope_changed(self) -> None:
        data = self.telescope_combo.currentData()
        if isinstance(data, TelescopeModel):
            self._selected_telescope = data

    def _on_eyepiece_selected(self, key: str) -> None:
        self._selected_eyepiece_key = key

    def _on_save(self) -> None:
        try:
            telescope_model = self._selected_telescope
            eyepiece_key = self._selected_eyepiece_key
            if telescope_model is None or not eyepiece_key:
                return

            telescope = get_telescope_specs(telescope_model)
            eyepiece = COMMON_EYEPIECES[eyepiece_key]
            config = OpticalConfiguration(telescope=telescope, eyepiece=eyepiece)
            set_current_configuration(config, save=True)
            self.accept()
        except Exception as e:
            logger.error("Failed to save optics configuration", exc_info=True)
            # Keep dialog open; user can retry.
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "Error", f"Failed to save optics configuration:\n{e!s}")
