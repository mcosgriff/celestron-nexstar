"""
SPK Manager Dialog

Dialog for downloading and managing JPL Horizons SPK files for comets.
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
    from celestron_nexstar.gui.workers.download_workers import DownloadCometSPKThread


logger = logging.getLogger(__name__)


# Type alias for comet data dict
CometData = dict[str, Any]


class SPKManagerDialog(QDialog):
    """Dialog for managing comet SPK files from JPL Horizons."""

    _download_thread: DownloadCometSPKThread | None
    _comet_data: list[CometData]
    _pending_downloads: list[CometData]
    _download_count: int
    _download_errors: list[str]

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the SPK manager dialog."""
        super().__init__(parent)
        self.setWindowTitle("Comet SPK Manager")
        self.setMinimumWidth(800)
        self.setMinimumHeight(500)
        self.resize(900, 600)

        self._download_thread = None
        self._comet_data = []
        self._pending_downloads = []
        self._download_count = 0
        self._download_errors = []

        layout = QVBoxLayout(self)

        # Header
        header = QLabel("JPL Horizons SPK Files")
        header.setStyleSheet("font-size: 14pt; font-weight: bold; margin-bottom: 8px;")
        layout.addWidget(header)

        desc = QLabel(
            "SPK (SPICE Kernel) files provide high-accuracy ephemeris data from JPL Horizons. "
            "Download SPK files for specific comets to enable precise offline position calculations. "
            "SPK files are ~10-100 KB each and cover a 3-year window."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Action buttons
        action_row = QHBoxLayout()

        download_selected_btn = QPushButton("Download Selected")
        download_selected_btn.clicked.connect(self._on_download_selected)
        download_selected_btn.setToolTip("Download SPK files for selected comets")
        self.download_selected_btn = download_selected_btn
        action_row.addWidget(download_selected_btn)

        download_bright_btn = QPushButton("Download Bright Comets")
        download_bright_btn.clicked.connect(self._on_download_bright)
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
        self.table = table
        layout.addWidget(table)

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

        # Load data
        self._load_comets()

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

            self.table.setRowCount(len(comets))
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
                self.table.setItem(row, 0, checkbox_item)

                # Name
                name_item = QTableWidgetItem(comet.name)
                self.table.setItem(row, 1, name_item)

                # Designation
                des_item = QTableWidgetItem(comet.designation)
                self.table.setItem(row, 2, des_item)

                # Peak magnitude
                mag_item = QTableWidgetItem(f"{comet.peak_magnitude:.1f}")
                self.table.setItem(row, 3, mag_item)

                # SPK status
                spk = spk_by_designation.get(comet.designation)
                if spk and spk.is_valid:
                    status_item = QTableWidgetItem("✓ Downloaded")
                    status_item.setForeground(Qt.GlobalColor.green)

                    # Size
                    size_kb = spk.size_bytes / 1024
                    size_item = QTableWidgetItem(f"{size_kb:.1f} KB")
                    self.table.setItem(row, 5, size_item)

                    # Downloaded date
                    date_str = spk.downloaded_at.strftime("%Y-%m-%d") if spk.downloaded_at else "-"
                    date_item = QTableWidgetItem(date_str)
                    self.table.setItem(row, 6, date_item)
                else:
                    status_item = QTableWidgetItem("Not downloaded")
                    status_item.setForeground(Qt.GlobalColor.gray)
                    self.table.setItem(row, 5, QTableWidgetItem("-"))
                    self.table.setItem(row, 6, QTableWidgetItem("-"))

                self.table.setItem(row, 4, status_item)

            self.table.resizeColumnsToContents()
            self.status.setText(f"Showing {len(comets)} comets. {len(spk_by_designation)} SPK files cached.")

        except Exception as e:
            logger.error(f"Error loading comets: {e}", exc_info=True)
            self.status.setText(f"Error loading comets: {e}")

    def _get_selected_comets(self) -> list[CometData]:
        """Get list of selected comets."""
        selected = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                selected.append(self._comet_data[row])
        return selected

    def _on_download_selected(self) -> None:
        """Download SPK files for selected comets."""
        selected = self._get_selected_comets()
        if not selected:
            QMessageBox.information(self, "No Selection", "Please select one or more comets to download SPK files for.")
            return

        self._download_spks(selected)

    def _on_download_bright(self) -> None:
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
            self._download_spks(bright)

    def _download_spks(self, comets: list[CometData]) -> None:
        """Download SPK files for given comets."""

        self.progress.setVisible(True)
        self.progress.setRange(0, len(comets))
        self.progress.setValue(0)
        self.download_selected_btn.setEnabled(False)

        self._pending_downloads = list(comets)
        self._download_count = 0
        self._download_errors = []

        self._download_next()

    def _download_next(self) -> None:
        """Download next SPK in queue."""
        from celestron_nexstar.gui.workers.download_workers import DownloadCometSPKThread

        if not self._pending_downloads:
            self._download_complete()
            return

        comet = self._pending_downloads.pop(0)
        self.status.setText(f"Downloading SPK for {comet['name']}...")

        self._download_thread = DownloadCometSPKThread(
            designation=comet["designation"],
            name=comet["name"],
            force=False,
        )
        self._download_thread.progress_updated.connect(self._on_spk_progress)
        self._download_thread.download_complete.connect(self._on_spk_complete)
        self._download_thread.error_occurred.connect(self._on_spk_error)
        self._download_thread.start()

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
        self.download_selected_btn.setEnabled(True)

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

        # Refresh table
        self._load_comets()
