"""
SPK Manager Dialog

Dialog for downloading and managing JPL Horizons SPK files for asteroids.

Note: SPK files are only available for asteroids from JPL Horizons.
Comet positions are calculated from orbital elements instead.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


if TYPE_CHECKING:
    from celestron_nexstar.gui.workers.download_workers import DownloadAsteroidSPKThread, DownloadCometSPKThread


logger = logging.getLogger(__name__)


# Type aliases
CometData = dict[str, Any]
AsteroidData = dict[str, Any]


class SPKManagerDialog(QDialog):
    """Dialog for managing asteroid SPK files from JPL Horizons.

    Note: SPK files are only available for asteroids. Comets use orbital elements.
    """

    _comet_download_thread: DownloadCometSPKThread | None
    _asteroid_download_thread: DownloadAsteroidSPKThread | None
    _comet_data: list[CometData]
    _asteroid_data: list[AsteroidData]
    _pending_downloads: list[CometData | AsteroidData]
    _download_count: int
    _download_errors: list[str]
    _download_type: str  # "comet" or "asteroid"

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the SPK manager dialog."""
        super().__init__(parent)
        self.setWindowTitle("Asteroid SPK Manager")
        self.setMinimumWidth(800)
        self.setMinimumHeight(500)
        self.resize(900, 600)

        self._comet_download_thread = None
        self._asteroid_download_thread = None
        self._comet_data = []
        self._asteroid_data = []
        _pending_downloads = []
        self._download_count = 0
        self._download_errors = []
        self._download_type = "asteroid"

        layout = QVBoxLayout(self)

        # Header
        header = QLabel("JPL Horizons SPK Files - Asteroids")
        header.setStyleSheet("font-size: 14pt; font-weight: bold; margin-bottom: 8px;")
        layout.addWidget(header)

        desc = QLabel(
            "SPK (SPICE Kernel) files provide high-accuracy ephemeris data from JPL Horizons. "
            "Download SPK files for asteroids to enable precise offline position calculations. "
            "SPK files are ~10-100 KB each and cover a 3-year window.\n\n"
            "Note: SPK files are only available for asteroids from JPL Horizons. "
            "Comet positions are calculated from orbital elements (no download needed)."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Create asteroid tab (no tabs needed since we only show asteroids)
        asteroid_tab = self._create_asteroid_tab()
        layout.addWidget(asteroid_tab)

        # Progress
        progress = QProgressBar()
        progress.setVisible(False)
        progress.setRange(0, 100)
        self.progress = progress
        layout.addWidget(progress)

        # Status
        status = QLabel()
        status.setWordWrap(True)
        self.status = status
        layout.addWidget(status)

        # Button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Load asteroid data
        self._load_asteroids()

    def _create_comet_tab(self) -> QWidget:
        """Create the comets tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Action buttons
        action_row = QHBoxLayout()

        download_selected_btn = QPushButton("Download Selected")
        download_selected_btn.clicked.connect(self._on_download_selected_comets)
        download_selected_btn.setToolTip("Download SPK files for selected comets")
        self.comet_download_selected_btn = download_selected_btn
        action_row.addWidget(download_selected_btn)

        download_bright_btn = QPushButton("Download Bright Comets")
        download_bright_btn.clicked.connect(self._on_download_bright_comets)
        download_bright_btn.setToolTip("Download SPK for comets brighter than magnitude 8")
        action_row.addWidget(download_bright_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._load_comets)
        action_row.addWidget(refresh_btn)

        action_row.addStretch()
        layout.addLayout(action_row)

        # Table
        table = QTableWidget()
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels(
            ["Select", "Comet", "Designation", "Peak Mag", "SPK Status", "SPK Size", "Downloaded"]
        )
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header_view = table.horizontalHeader()
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.comet_table = table
        layout.addWidget(table)

        return tab

    def _create_asteroid_tab(self) -> QWidget:
        """Create the asteroids tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Action buttons
        action_row = QHBoxLayout()

        download_selected_btn = QPushButton("Download Selected")
        download_selected_btn.clicked.connect(self._on_download_selected_asteroids)
        download_selected_btn.setToolTip("Download SPK files for selected asteroids")
        self.asteroid_download_selected_btn = download_selected_btn
        action_row.addWidget(download_selected_btn)

        download_bright_btn = QPushButton("Download Bright Asteroids")
        download_bright_btn.clicked.connect(self._on_download_bright_asteroids)
        download_bright_btn.setToolTip("Download SPK for asteroids brighter than magnitude 12")
        action_row.addWidget(download_bright_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._load_asteroids)
        action_row.addWidget(refresh_btn)

        action_row.addStretch()
        layout.addLayout(action_row)

        # Table
        table = QTableWidget()
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels(
            ["Select", "Asteroid", "Designation", "H Mag", "SPK Status", "SPK Size", "Downloaded"]
        )
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header_view = table.horizontalHeader()
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.asteroid_table = table
        layout.addWidget(table)

        return tab

    def _load_comets(self) -> None:
        """Load comets from database and show SPK status."""
        try:
            from sqlalchemy import select

            from celestron_nexstar.api.database.models import CometModel, CometSPKModel, get_db_session

            with get_db_session() as session:
                # Get all comets
                comets = session.execute(select(CometModel).order_by(CometModel.peak_magnitude)).scalars().all()

                # Get SPK records
                spk_records = session.execute(select(CometSPKModel)).scalars().all()
                spk_by_designation = {spk.comet_designation: spk for spk in spk_records}

            self.comet_table.setRowCount(len(comets))
            self._comet_data = []

            for row, comet in enumerate(comets):
                # Store comet data for later
                self._comet_data.append(
                    {
                        "designation": comet.designation,
                        "name": comet.name,
                        "peak_magnitude": comet.peak_magnitude,
                    }
                )

                # Checkbox column
                checkbox_item = QTableWidgetItem()
                checkbox_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                checkbox_item.setCheckState(Qt.CheckState.Unchecked)
                self.comet_table.setItem(row, 0, checkbox_item)

                # Name
                name_item = QTableWidgetItem(comet.name)
                self.comet_table.setItem(row, 1, name_item)

                # Designation
                des_item = QTableWidgetItem(comet.designation)
                self.comet_table.setItem(row, 2, des_item)

                # Peak magnitude
                mag_item = QTableWidgetItem(f"{comet.peak_magnitude:.1f}")
                self.comet_table.setItem(row, 3, mag_item)

                # SPK status
                spk = spk_by_designation.get(comet.designation)
                if spk and spk.is_valid:
                    status_item = QTableWidgetItem("✓ Downloaded")
                    status_item.setForeground(Qt.GlobalColor.green)

                    # Size
                    size_kb = spk.size_bytes / 1024
                    size_item = QTableWidgetItem(f"{size_kb:.1f} KB")
                    self.comet_table.setItem(row, 5, size_item)

                    # Downloaded date
                    date_str = spk.downloaded_at.strftime("%Y-%m-%d") if spk.downloaded_at else "-"
                    date_item = QTableWidgetItem(date_str)
                    self.comet_table.setItem(row, 6, date_item)
                else:
                    status_item = QTableWidgetItem("Not downloaded")
                    status_item.setForeground(Qt.GlobalColor.gray)
                    self.comet_table.setItem(row, 5, QTableWidgetItem("-"))
                    self.comet_table.setItem(row, 6, QTableWidgetItem("-"))

                self.comet_table.setItem(row, 4, status_item)

            self.comet_table.resizeColumnsToContents()
            # Comet tab removed - SPK files not available for comets

        except Exception as e:
            logger.error(f"Error loading comets: {e}", exc_info=True)

    def _load_asteroids(self) -> None:
        """Load asteroids from database and show SPK status.

        Note: Only shows asteroids that likely have SPK files available from JPL Horizons.
        Excludes dwarf planets, TNOs, centaurs, and distant objects.
        """
        try:
            from sqlalchemy import select

            from celestron_nexstar.api.database.models import AsteroidModel, AsteroidSPKModel, get_db_session

            with get_db_session() as session:
                # Get all asteroids
                all_asteroids = (
                    session.execute(select(AsteroidModel).order_by(AsteroidModel.absolute_magnitude_h)).scalars().all()
                )

                # Filter to only asteroids that likely have SPK files available from JPL Horizons
                # NOTE: In practice, JPL Horizons does NOT provide downloadable SPK files for most asteroids.
                # This filtering reduces the list to potentially available objects, but downloads may still fail.
                # SPK files are theoretically available for:
                # - Main belt asteroids (semi_major_axis ~2-4 AU)
                # - Near-Earth objects (NEOs, semi_major_axis < 2 AU)
                # NOT available for:
                # - Major asteroids already in planetary ephemeris (Ceres, Pallas, Vesta, etc.)
                # - Dwarf planets (Eris, Haumea, Makemake, etc.)
                # - Trans-Neptunian objects (TNOs) like Sedna
                # - Centaurs (Chiron, Chariklo)
                # - Jupiter Trojans and more distant objects
                # - Asteroids with unusual orbits (highly eccentric, highly inclined)

                # Major asteroids included in JPL planetary ephemeris files (de421.bsp, de440s.bsp)
                MAJOR_BODY_ASTEROIDS = {"1", "2", "3", "4", "10"}  # Ceres, Pallas, Juno, Vesta, Hygiea

                asteroids = [
                    a
                    for a in all_asteroids
                    if a.designation not in MAJOR_BODY_ASTEROIDS  # Already in ephemeris
                    and a.asteroid_type not in ("dwarf_planet", "tno", "centaur", "trojan")  # Exclude distant types
                    and a.semi_major_axis_au < 4.5  # Main belt + NEOs only, exclude Jupiter trojans
                ]

                # Get SPK records
                spk_records = session.execute(select(AsteroidSPKModel)).scalars().all()
                spk_by_designation = {spk.asteroid_designation: spk for spk in spk_records}

            self.asteroid_table.setRowCount(len(asteroids))
            self._asteroid_data = []

            for row, asteroid in enumerate(asteroids):
                # Store asteroid data for later
                self._asteroid_data.append(
                    {
                        "designation": asteroid.designation,
                        "name": asteroid.name,
                        "absolute_magnitude_h": asteroid.absolute_magnitude_h,
                    }
                )

                # Checkbox column
                checkbox_item = QTableWidgetItem()
                checkbox_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                checkbox_item.setCheckState(Qt.CheckState.Unchecked)
                self.asteroid_table.setItem(row, 0, checkbox_item)

                # Name
                name = asteroid.name or f"Asteroid {asteroid.designation}"
                name_item = QTableWidgetItem(name)
                self.asteroid_table.setItem(row, 1, name_item)

                # Designation
                des_item = QTableWidgetItem(asteroid.designation)
                self.asteroid_table.setItem(row, 2, des_item)

                # H magnitude
                mag_item = QTableWidgetItem(f"{asteroid.absolute_magnitude_h:.1f}")
                self.asteroid_table.setItem(row, 3, mag_item)

                # SPK status
                spk = spk_by_designation.get(asteroid.designation)
                if spk and spk.is_valid:
                    status_item = QTableWidgetItem("✓ Downloaded")
                    status_item.setForeground(Qt.GlobalColor.green)

                    # Size
                    size_kb = spk.size_bytes / 1024
                    size_item = QTableWidgetItem(f"{size_kb:.1f} KB")
                    self.asteroid_table.setItem(row, 5, size_item)

                    # Downloaded date
                    date_str = spk.downloaded_at.strftime("%Y-%m-%d") if spk.downloaded_at else "-"
                    date_item = QTableWidgetItem(date_str)
                    self.asteroid_table.setItem(row, 6, date_item)
                else:
                    status_item = QTableWidgetItem("Not downloaded")
                    status_item.setForeground(Qt.GlobalColor.gray)
                    self.asteroid_table.setItem(row, 5, QTableWidgetItem("-"))
                    self.asteroid_table.setItem(row, 6, QTableWidgetItem("-"))

                self.asteroid_table.setItem(row, 4, status_item)

            self.asteroid_table.resizeColumnsToContents()
            self.status.setText(f"Showing {len(asteroids)} asteroids. {len(spk_by_designation)} SPK files cached.")

        except Exception as e:
            logger.error(f"Error loading asteroids: {e}", exc_info=True)
            self.status.setText(f"Error loading asteroids: {e}")

    def _get_selected_comets(self) -> list[CometData]:
        """Get list of selected comets."""
        selected = []
        for row in range(self.comet_table.rowCount()):
            item = self.comet_table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                selected.append(self._comet_data[row])
        return selected

    def _get_selected_asteroids(self) -> list[AsteroidData]:
        """Get list of selected asteroids."""
        selected = []
        for row in range(self.asteroid_table.rowCount()):
            item = self.asteroid_table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                selected.append(self._asteroid_data[row])
        return selected

    def _on_download_selected_comets(self) -> None:
        """Download SPK files for selected comets."""
        selected = self._get_selected_comets()
        if not selected:
            QMessageBox.information(self, "No Selection", "Please select one or more comets to download SPK files for.")
            return

        self._download_type = "comet"
        self._download_spks(selected)

    def _on_download_selected_asteroids(self) -> None:
        """Download SPK files for selected asteroids."""
        selected = self._get_selected_asteroids()
        if not selected:
            QMessageBox.information(
                self, "No Selection", "Please select one or more asteroids to download SPK files for."
            )
            return

        self._download_type = "asteroid"
        self._download_spks(selected)

    def _on_download_bright_comets(self) -> None:
        """Download SPK files for bright comets (mag < 8)."""
        bright = [c for c in self._comet_data if float(c["peak_magnitude"]) < 8.0]
        if not bright:
            QMessageBox.information(
                self, "No Bright Comets", "No comets brighter than magnitude 8 found in the database."
            )
            return

        reply = QMessageBox.question(
            self,
            "Download Bright Comets",
            f"Download SPK files for {len(bright)} comets brighter than magnitude 8?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._download_type = "comet"
            self._download_spks(bright)

    def _on_download_bright_asteroids(self) -> None:
        """Download SPK files for bright asteroids (H < 12)."""
        bright = [a for a in self._asteroid_data if float(a["absolute_magnitude_h"]) < 12.0]
        if not bright:
            QMessageBox.information(
                self, "No Bright Asteroids", "No asteroids brighter than H magnitude 12 found in the database."
            )
            return

        reply = QMessageBox.question(
            self,
            "Download Bright Asteroids",
            f"Download SPK files for {len(bright)} asteroids brighter than H magnitude 12?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._download_type = "asteroid"
            self._download_spks(bright)

    def _download_spks(self, items: list[CometData | AsteroidData]) -> None:
        """Download SPK files for given comets or asteroids."""
        self.progress.setVisible(True)
        self.progress.setRange(0, len(items))
        self.progress.setValue(0)

        if self._download_type == "comet":
            self.comet_download_selected_btn.setEnabled(False)
        else:
            self.asteroid_download_selected_btn.setEnabled(False)

        self._pending_downloads = list(items)
        self._download_count = 0
        self._download_errors = []

        self._download_next()

    def _download_next(self) -> None:
        """Download next SPK in queue."""
        if not self._pending_downloads:
            self._download_complete()
            return

        item = self._pending_downloads.pop(0)

        if self._download_type == "comet":
            from celestron_nexstar.gui.workers.download_workers import DownloadCometSPKThread

            self.status.setText(f"Downloading SPK for {item['name']}...")

            self._comet_download_thread = DownloadCometSPKThread(
                designation=item["designation"],
                name=item["name"],
                force=False,
            )
            self._comet_download_thread.progress_updated.connect(self._on_spk_progress)
            self._comet_download_thread.download_complete.connect(self._on_spk_complete)
            self._comet_download_thread.error_occurred.connect(self._on_spk_error)
            self._comet_download_thread.start()
        else:
            from celestron_nexstar.gui.workers.download_workers import DownloadAsteroidSPKThread

            name = item.get("name") or f"Asteroid {item['designation']}"
            self.status.setText(f"Downloading SPK for {name}...")

            self._asteroid_download_thread = DownloadAsteroidSPKThread(
                designation=item["designation"],
                name=name,
                force=False,
            )
            self._asteroid_download_thread.progress_updated.connect(self._on_spk_progress)
            self._asteroid_download_thread.download_complete.connect(self._on_spk_complete)
            self._asteroid_download_thread.error_occurred.connect(self._on_spk_error)
            self._asteroid_download_thread.start()

    def _on_spk_progress(self, msg: str, current: int, total: int) -> None:
        """Handle SPK download progress."""
        self.status.setText(msg)

    def _on_spk_complete(self, designation: str, success: bool, message: str) -> None:
        """Handle SPK download complete."""
        self._download_count += 1
        self.progress.setValue(self._download_count)

        if not success:
            self._download_errors.append(f"{designation}: {message}")

        # Continue with next
        self._download_next()

    def _on_spk_error(self, designation: str, error: str) -> None:
        """Handle SPK download error."""
        self._download_errors.append(f"{designation}: {error}")

    def _download_complete(self) -> None:
        """All downloads complete."""
        self.progress.setVisible(False)
        self.asteroid_download_selected_btn.setEnabled(True)

        if self._download_errors:
            self.status.setText(f"Downloaded {self._download_count} SPKs. Errors: {len(self._download_errors)}")
            error_text = "\n".join(self._download_errors[:5])
            if len(self._download_errors) > 5:
                error_text += f"\n... and {len(self._download_errors) - 5} more"
            QMessageBox.warning(
                self,
                "Download Errors",
                f"Some SPK downloads failed:\n\n{error_text}",
            )
        else:
            self.status.setText(f"Successfully downloaded {self._download_count} SPK files.")

        # Refresh asteroid table
        self._load_asteroids()
