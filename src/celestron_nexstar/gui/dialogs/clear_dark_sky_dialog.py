"""Dialog to display Clear Dark Sky chart."""

import logging

from PySide6.QtCore import Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


logger = logging.getLogger(__name__)


class ChartFetchWorkerThread(QThread):
    """Worker thread to fetch Clear Dark Sky chart in background."""

    chart_ready = Signal(str, bytes)  # (chart_key, image_data)
    error_occurred = Signal(str)  # Error message

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the worker thread."""
        super().__init__(parent)

    def run(self) -> None:
        """Fetch chart in background thread."""
        try:
            from celestron_nexstar.api.location.clear_dark_sky import (
                fetch_chart_image,
                find_nearest_chart,
            )
            from celestron_nexstar.api.location.observer import get_observer_location

            # Get observer location
            location = get_observer_location()

            # Find nearest chart
            chart_key = find_nearest_chart(location)
            if not chart_key:
                self.error_occurred.emit(
                    "No Clear Dark Sky chart found for your location. "
                    "Charts are primarily available for North American locations."
                )
                return

            # Fetch chart image
            image_data = fetch_chart_image(chart_key)
            if not image_data:
                self.error_occurred.emit("Failed to download Clear Dark Sky chart image.")
                return

            self.chart_ready.emit(chart_key, image_data)

        except Exception as e:
            logger.exception("Error fetching Clear Dark Sky chart")
            self.error_occurred.emit(f"Error: {e}")


class ClearDarkSkyDialog(QDialog):
    """Dialog to display Clear Dark Sky chart."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the dialog."""
        super().__init__(parent)
        self.setWindowTitle("Clear Dark Sky Chart")
        self.setMinimumWidth(800)
        self.setMinimumHeight(600)
        self.resize(900, 700)

        # Store chart key, worker, and original pixmap for resizing
        self.chart_key: str | None = None
        self.worker: ChartFetchWorkerThread | None = None
        self.original_pixmap: QPixmap | None = None

        # Create main layout
        layout = QVBoxLayout(self)

        # Check if location is set
        try:
            from celestron_nexstar.api.location.observer import get_observer_location

            location = get_observer_location()
        except Exception:
            QMessageBox.warning(
                self,
                "Location Required",
                "Please configure your observer location in Settings before viewing Clear Dark Sky charts.",
            )
            self.reject()
            return

        # Show warning if outside North America
        from celestron_nexstar.api.location.clear_dark_sky import is_north_america

        if not is_north_america(location):
            warning_label = QLabel(
                "⚠ Clear Dark Sky charts are primarily available for North American locations. "
                "A chart may not be available for your location."
            )
            warning_label.setStyleSheet("background-color: #ffc107; color: #000000; padding: 8px;")
            warning_label.setWordWrap(True)
            layout.addWidget(warning_label)

        # Info label
        location_name = location.name or f"{location.latitude:.4f}°, {location.longitude:.4f}°"
        self.info_label = QLabel(
            f"Clear Dark Sky chart for: {location_name}\n\nLoading chart... This may take a few seconds."
        )
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        # Image label (will show chart once loaded)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setScaledContents(False)
        self.image_label.setMinimumHeight(400)
        layout.addWidget(self.image_label, 1)  # Stretch factor 1

        # Button layout
        button_layout = QHBoxLayout()

        # Link button (will be enabled once chart loads)
        self.link_button = QPushButton("Open Full Chart in Browser")
        self.link_button.setEnabled(False)
        self.link_button.clicked.connect(self._on_open_link)
        button_layout.addWidget(self.link_button)

        # Refresh button
        self.refresh_button = QPushButton("Refresh Chart")
        self.refresh_button.clicked.connect(self._on_refresh)
        button_layout.addWidget(self.refresh_button)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Dialog button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Create auto-refresh timer (60 minutes)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._on_auto_refresh)
        self.refresh_timer.setInterval(3600000)  # 60 minutes in milliseconds

        # Start loading chart
        self._load_chart()

    def _load_chart(self) -> None:
        """Load chart in background thread."""
        # Disable refresh button while loading
        self.refresh_button.setEnabled(False)

        # Create and start worker
        self.worker = ChartFetchWorkerThread(self)
        self.worker.chart_ready.connect(self._on_chart_ready)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.finished.connect(lambda: self.refresh_button.setEnabled(True))
        self.worker.start()

    def _on_chart_ready(self, chart_key: str, image_data: bytes) -> None:
        """Handle chart loaded successfully."""
        self.chart_key = chart_key

        # Load image into QPixmap
        pixmap = QPixmap()
        if pixmap.loadFromData(image_data):
            # Store original pixmap for resizing
            self.original_pixmap = pixmap

            # Scale to fit window while maintaining aspect ratio
            scaled_pixmap = pixmap.scaled(
                self.image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.image_label.setPixmap(scaled_pixmap)
            self.link_button.setEnabled(True)

            # Update info label
            from celestron_nexstar.api.location.observer import get_observer_location

            location = get_observer_location()
            location_name = location.name or f"{location.latitude:.4f}°, {location.longitude:.4f}°"
            self.info_label.setText(
                f"Clear Dark Sky chart for: {location_name}\nChart ID: {chart_key}\n\nCharts update hourly."
            )

            # Start auto-refresh timer
            if not self.refresh_timer.isActive():
                self.refresh_timer.start()

        else:
            self._on_error("Failed to load chart image")

    def _on_error(self, error_msg: str) -> None:
        """Handle error loading chart."""
        logger.warning(f"Clear Dark Sky chart error: {error_msg}")
        self.image_label.setText(f"Error: {error_msg}")
        self.info_label.setText(
            "Failed to load Clear Dark Sky chart.\n\nPlease check your internet connection and try again."
        )

        # Don't start refresh timer on error
        self.refresh_timer.stop()

    def _on_open_link(self) -> None:
        """Open full chart page in browser."""
        if self.chart_key:
            from celestron_nexstar.api.location.clear_dark_sky import get_chart_page_url

            url = get_chart_page_url(self.chart_key)
            QDesktopServices.openUrl(QUrl(url))

    def _on_refresh(self) -> None:
        """Manually refresh the chart."""
        self.info_label.setText("Refreshing chart...")
        self.image_label.clear()
        self.original_pixmap = None  # Clear cached pixmap
        self.link_button.setEnabled(False)
        self._load_chart()

    def _on_auto_refresh(self) -> None:
        """Auto-refresh triggered by timer."""
        logger.info("Auto-refreshing Clear Dark Sky chart")
        self._on_refresh()

    def closeEvent(self, event):  # noqa: N802
        """Handle dialog close event."""
        # Stop refresh timer
        self.refresh_timer.stop()

        # Wait for worker thread to finish
        if self.worker and self.worker.isRunning():
            self.worker.wait(1000)  # Wait up to 1 second

        super().closeEvent(event)

    def resizeEvent(self, event):  # noqa: N802
        """Handle resize event to re-scale image."""
        super().resizeEvent(event)

        # Re-scale image from original if we have one
        if self.original_pixmap and not self.original_pixmap.isNull():
            # Scale original pixmap to new size while maintaining aspect ratio
            scaled_pixmap = self.original_pixmap.scaled(
                self.image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.image_label.setPixmap(scaled_pixmap)
