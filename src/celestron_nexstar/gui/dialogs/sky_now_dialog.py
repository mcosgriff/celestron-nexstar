"""
Dialog to display objects currently transiting or about to transit.

Shows celestial objects whose transit time falls within a user-adjustable time window,
helping observers quickly identify what's best to view right now.
"""

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from celestron_nexstar.api.catalogs.catalogs import CelestialObject
from celestron_nexstar.api.core.utils import format_local_time
from celestron_nexstar.api.location.observer import get_observer_location
from celestron_nexstar.api.observation.visibility import get_object_altitude_azimuth
from celestron_nexstar.gui.utils.table_utils import autosize_table_columns


if TYPE_CHECKING:
    from celestron_nexstar.gui.main_window import MainWindow

logger = logging.getLogger(__name__)


class SkyNowWorkerThread(QThread):
    """Worker thread to load objects in background."""

    data_ready = Signal(
        list, datetime, datetime, float, float
    )  # (objects_with_transit, start_time, end_time, observer_lat, observer_lon)
    error_occurred = Signal(str, str)  # (error_message, status_message)

    def __init__(
        self,
        parent: QWidget | None = None,
        start_offset_hours: float = 0.0,
        end_offset_hours: float = 1.0,
    ) -> None:
        """
        Initialize the worker thread.

        Args:
            parent: Parent widget
            start_offset_hours: Start offset in hours from now
            end_offset_hours: End offset in hours from now
        """
        super().__init__(parent)
        self.start_offset_hours = start_offset_hours
        self.end_offset_hours = end_offset_hours

    def run(self) -> None:
        """Load objects in background thread."""
        try:
            # Get observer location
            try:
                location = get_observer_location()
                if not location:
                    raise ValueError("No location set")
            except Exception:
                self.error_occurred.emit(
                    "No location set. Configure your observing location in Settings.", "Error: No location set"
                )
                return

            # Get time range (use timezone-aware local time)
            from celestron_nexstar.api.core.utils import get_local_timezone

            local_tz = get_local_timezone(location.latitude, location.longitude)
            now = datetime.now(local_tz)
            start_time = now + timedelta(hours=self.start_offset_hours)
            end_time = now + timedelta(hours=self.end_offset_hours)

            # Query ALL objects from database (with reasonable magnitude limits)
            # Note: We skip the initial visibility filter and only check visibility at transit time
            # This is much faster than checking visibility twice (now + transit time)
            from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed

            from celestron_nexstar.api.database.database import get_database

            try:
                db = get_database()

                # Define all queries to run in parallel
                query_tasks = [
                    ("star", {"object_type": "star", "max_magnitude": 4.5, "limit": 300}),
                    ("double_star", {"object_type": "double_star", "max_magnitude": 7.0, "limit": 100}),
                    ("galaxy", {"object_type": "galaxy", "max_magnitude": 11.0, "limit": 200}),
                    ("nebula", {"object_type": "nebula", "max_magnitude": 11.0, "limit": 200}),
                    ("cluster", {"object_type": "cluster", "max_magnitude": 11.0, "limit": 200}),
                    ("planet", {"object_type": "planet", "limit": 50}),
                    ("moon", {"object_type": "moon", "limit": 100}),
                ]

                # Run all queries in parallel
                all_objects = []
                with ThreadPoolExecutor(max_workers=7) as executor:
                    # Submit all queries
                    future_to_type = {
                        executor.submit(db.filter_objects, **kwargs): obj_type for obj_type, kwargs in query_tasks
                    }

                    # Collect results as they complete
                    for future in as_completed(future_to_type):
                        obj_type = future_to_type[future]
                        try:
                            objects = future.result()
                            all_objects.extend(objects)
                            logger.debug(f"Sky Now: Got {len(objects)} {obj_type}(s)")
                        except Exception as e:
                            logger.warning(f"Failed to query {obj_type}s: {e}")

                logger.debug(f"Sky Now: Got {len(all_objects)} total objects from database")

            except Exception as e:
                logger.error(f"Error querying objects: {e}", exc_info=True)
                self.error_occurred.emit(f"Database error: {e}", "Error loading objects")
                return

            # Pre-filter objects by current altitude to reduce expensive timeline calculations
            visible_now = []
            for obj in all_objects:
                try:
                    altitude_deg, _azimuth_deg = get_object_altitude_azimuth(
                        obj,
                        observer_lat=location.latitude,
                        observer_lon=location.longitude,
                        dt=now,
                    )
                    if altitude_deg > -10.0:
                        visible_now.append(obj)
                except Exception:
                    continue

            logger.debug(f"Sky Now: {len(visible_now)} objects above -10° altitude right now")

            # Get observing conditions for visibility probability calculation
            from celestron_nexstar.api.observation.observation_planner import ObservationPlanner
            from celestron_nexstar.api.observation.planning_utils import get_object_visibility_timeline
            from celestron_nexstar.api.observation.visibility import assess_visibility

            planner = ObservationPlanner()
            weather_executor = ThreadPoolExecutor(max_workers=1)
            try:
                conditions_future = weather_executor.submit(planner.get_tonight_conditions)
                try:
                    conditions = conditions_future.result(timeout=0.1)
                except TimeoutError:
                    conditions = None
                except Exception as e:
                    logger.warning(f"Could not get observing conditions, using defaults: {e}")
                    conditions = None

                # Calculate transit times and check visibility at transit time
                # (We only check visibility once - at the transit time)
                filtered_objects: list[tuple[CelestialObject, datetime]] = []

                def process_object(obj: CelestialObject) -> tuple[CelestialObject, datetime] | None:
                    obj_name = getattr(obj, "common_name", None) or getattr(obj, "name", "Unknown")

                    try:
                        # Calculate transit time using visibility timeline
                        timeline = get_object_visibility_timeline(
                            obj=obj,
                            observer_lat=location.latitude,
                            observer_lon=location.longitude,
                            start_time=now,
                            days=1,  # Look ahead 1 day
                        )

                        transit_time = timeline.transit_time

                        # Debug logging for Rigel specifically
                        if "rigel" in obj_name.lower():
                            logger.info(
                                f"Sky Now: Found Rigel! transit_time={transit_time}, "
                                f"tzinfo={transit_time.tzinfo if transit_time else 'N/A'}"
                            )

                        if transit_time:
                            # Convert transit_time to local timezone for comparison
                            if transit_time.tzinfo is None:
                                # If naive, assume it's UTC
                                transit_time = transit_time.replace(tzinfo=UTC)
                            transit_time_local = transit_time.astimezone(local_tz)

                            # Check if transit time is in our range
                            in_time_range = start_time <= transit_time_local <= end_time

                            # Debug logging for Rigel specifically
                            if "rigel" in obj_name.lower():
                                logger.info(
                                    f"Sky Now: Rigel details: transit_local={transit_time_local.strftime('%Y-%m-%d %H:%M:%S %Z')}, "
                                    f"start_time={start_time.strftime('%Y-%m-%d %H:%M:%S %Z')}, "
                                    f"end_time={end_time.strftime('%Y-%m-%d %H:%M:%S %Z')}, "
                                    f"in_range={in_time_range}"
                                )

                            if in_time_range:
                                # Use the SAME visibility check as main window tables
                                # Assess visibility at transit time
                                visibility_at_transit = assess_visibility(
                                    obj,
                                    min_altitude_deg=20.0,  # Match main window threshold
                                    observer_lat=location.latitude,
                                    observer_lon=location.longitude,
                                    dt=transit_time,  # Check visibility at transit time
                                )

                                # Calculate visibility probability (same as main window)
                                if conditions:
                                    visibility_prob_result = planner._calculate_visibility_probability(
                                        obj, conditions, visibility_at_transit
                                    )
                                    # Handle tuple return (probability, explanations) or just probability
                                    if isinstance(visibility_prob_result, tuple):
                                        visibility_probability = visibility_prob_result[0]
                                    else:
                                        visibility_probability = visibility_prob_result
                                else:
                                    # No conditions available, use observability score as proxy
                                    visibility_probability = visibility_at_transit.observability_score

                                # Use same threshold as main window: visibility_probability > 0
                                # (Main window shows objects with visibility_probability > 0)
                                if visibility_probability > 0:
                                    return (obj, transit_time_local)
                                else:
                                    logger.debug(
                                        f"Sky Now: Excluding {obj_name} - visibility probability too low "
                                        f"(prob={visibility_probability:.3f}, alt={visibility_at_transit.altitude_deg:.1f}°)"
                                    )

                    except Exception as e:
                        # Skip objects that fail transit calculation
                        logger.debug(f"Sky Now: Could not calculate transit for {obj_name}: {e}")
                        return None

                    return None

                max_workers = min(4, os.cpu_count() or 1)
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    for result in executor.map(process_object, visible_now):
                        if result:
                            filtered_objects.append(result)
            finally:
                weather_executor.shutdown(wait=False)

            logger.info(
                f"Sky Now: Filtered to {len(filtered_objects)} objects transiting between {start_time.strftime('%H:%M')} and {end_time.strftime('%H:%M')} local time"
            )

            # Debug: Log object types
            if filtered_objects:
                type_counts = {}
                for obj, _ in filtered_objects:
                    obj_type = str(getattr(obj, "object_type", "Unknown"))
                    type_counts[obj_type] = type_counts.get(obj_type, 0) + 1
                logger.debug(f"Sky Now: Object types: {type_counts}")

            # Sort by transit time
            filtered_objects.sort(key=lambda x: x[1])

            # Emit results
            self.data_ready.emit(filtered_objects, start_time, end_time, location.latitude, location.longitude)

        except Exception as e:
            logger.error(f"Error loading objects: {e}", exc_info=True)
            self.error_occurred.emit(f"Unexpected error: {e}", "Error loading objects")


class SkyNowDialog(QDialog):
    """Dialog showing objects transiting now or soon."""

    def __init__(self, parent: QWidget | None = None, main_window: "MainWindow | None" = None) -> None:
        """
        Initialize the Sky Now dialog.

        Args:
            parent: Parent widget
            main_window: Reference to main window for goto queue access
        """
        super().__init__(parent)
        self.main_window = main_window

        # Worker thread for background loading
        self.worker: SkyNowWorkerThread | None = None

        # Progress dialog for loading
        self.progress_dialog: QProgressDialog | None = None

        # Setup UI
        self.setWindowTitle("Sky Now - Objects Transiting Soon")
        self.setMinimumWidth(900)
        self.setMinimumHeight(700)
        self.resize(1000, 750)

        self._setup_ui()
        self._load_objects()

    def _setup_ui(self) -> None:
        """Setup the user interface."""
        layout = QVBoxLayout(self)

        # Time range controls
        time_range_layout = QHBoxLayout()

        time_range_layout.addWidget(QLabel("Show objects transiting from:"))

        self.start_offset_spinbox = QDoubleSpinBox()
        self.start_offset_spinbox.setRange(-2.0, 6.0)
        self.start_offset_spinbox.setValue(0.0)
        self.start_offset_spinbox.setSingleStep(0.25)
        self.start_offset_spinbox.setSuffix(" hrs from now")
        self.start_offset_spinbox.setMinimumWidth(150)
        time_range_layout.addWidget(self.start_offset_spinbox)

        time_range_layout.addWidget(QLabel("to:"))

        self.end_offset_spinbox = QDoubleSpinBox()
        self.end_offset_spinbox.setRange(-2.0, 6.0)
        self.end_offset_spinbox.setValue(1.0)
        self.end_offset_spinbox.setSingleStep(0.25)
        self.end_offset_spinbox.setSuffix(" hrs from now")
        self.end_offset_spinbox.setMinimumWidth(150)
        time_range_layout.addWidget(self.end_offset_spinbox)

        self.apply_filter_button = QPushButton("Apply Filter")
        self.apply_filter_button.clicked.connect(self._apply_time_filter)
        time_range_layout.addWidget(self.apply_filter_button)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self._refresh_data)
        time_range_layout.addWidget(self.refresh_button)

        time_range_layout.addStretch()

        layout.addLayout(time_range_layout)

        # Status label
        self.status_label = QLabel("Loading objects...")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["Name", "Type", "Magnitude", "Constellation", "Transit Time", "Altitude Now", "Actions"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.itemDoubleClicked.connect(self._on_row_double_clicked)

        layout.addWidget(self.table, 1)  # Stretch factor 1

        # Footer controls
        footer_layout = QHBoxLayout()

        self.add_all_button = QPushButton("Add All to Goto Queue")
        self.add_all_button.clicked.connect(self._on_add_all_to_queue)
        footer_layout.addWidget(self.add_all_button)

        self.auto_refresh_checkbox = QCheckBox("Auto-refresh")
        self.auto_refresh_checkbox.setChecked(False)
        self.auto_refresh_checkbox.toggled.connect(self._on_auto_refresh_toggled)
        footer_layout.addWidget(self.auto_refresh_checkbox)

        self.refresh_interval_spinbox = QSpinBox()
        self.refresh_interval_spinbox.setRange(1, 30)
        self.refresh_interval_spinbox.setValue(15)
        self.refresh_interval_spinbox.setSuffix(" minutes")
        self.refresh_interval_spinbox.valueChanged.connect(self._on_refresh_interval_changed)
        footer_layout.addWidget(self.refresh_interval_spinbox)

        footer_layout.addStretch()

        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        footer_layout.addWidget(self.close_button)

        layout.addLayout(footer_layout)

        # Auto-refresh timer
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_data)

        # Start timer if auto-refresh enabled
        if self.auto_refresh_checkbox.isChecked():
            self.refresh_timer.start(self.refresh_interval_spinbox.value() * 60 * 1000)

    def _load_objects(self) -> None:
        """Load objects in background thread."""
        # Disable controls while loading
        self.apply_filter_button.setEnabled(False)
        self.refresh_button.setEnabled(False)
        self.add_all_button.setEnabled(False)

        # Clear table completely
        self.table.clearContents()
        self.table.setRowCount(0)
        self.table.setSortingEnabled(False)

        # Show progress dialog
        self.progress_dialog = QProgressDialog(
            "Loading objects transiting in selected time range...", "Cancel", 0, 0, self
        )
        self.progress_dialog.setWindowTitle("Sky Now")
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.canceled.connect(self._on_loading_canceled)
        self.progress_dialog.show()

        # Update status
        self.status_label.setText("Loading objects...")

        # Create and start worker thread
        start_offset = self.start_offset_spinbox.value()
        end_offset = self.end_offset_spinbox.value()

        self.worker = SkyNowWorkerThread(parent=self, start_offset_hours=start_offset, end_offset_hours=end_offset)
        self.worker.data_ready.connect(self._on_data_ready)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _on_loading_canceled(self) -> None:
        """Handle loading canceled by user."""
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait(1000)

        self.status_label.setText("Loading canceled")
        logger.info("Sky Now: Loading canceled by user")

    def _on_data_ready(
        self,
        filtered_objects: list[tuple[CelestialObject, datetime]],
        start_time: datetime,
        end_time: datetime,
        observer_lat: float,
        observer_lon: float,
    ) -> None:
        """
        Handle data ready from worker thread.

        Args:
            filtered_objects: List of (object, transit_time) tuples
            start_time: Start of time range
            end_time: End of time range
            observer_lat: Observer latitude
            observer_lon: Observer longitude
        """
        # Close progress dialog (disconnect cancel signal first to avoid false cancel message)
        if self.progress_dialog:
            self.progress_dialog.canceled.disconnect()
            self.progress_dialog.close()
            self.progress_dialog = None

        if filtered_objects:
            self._populate_table(filtered_objects, observer_lat, observer_lon)
            self._update_status_label(len(filtered_objects), start_time, end_time, observer_lat, observer_lon)
        else:
            self._show_no_objects_message(start_time, end_time, observer_lat, observer_lon)

    def _on_error(self, error_message: str, status_message: str) -> None:
        """
        Handle error from worker thread.

        Args:
            error_message: Error message to display in table
            status_message: Status message for status label
        """
        # Close progress dialog (disconnect cancel signal first to avoid false cancel message)
        if self.progress_dialog:
            self.progress_dialog.canceled.disconnect()
            self.progress_dialog.close()
            self.progress_dialog = None

        self._show_error_in_table(error_message)
        self.status_label.setText(status_message)

    def _on_worker_finished(self) -> None:
        """Handle worker thread finished."""
        # Re-enable controls
        self.apply_filter_button.setEnabled(True)
        self.refresh_button.setEnabled(True)
        self.add_all_button.setEnabled(True)

    def _populate_table(
        self, objects: list[tuple[CelestialObject, datetime]], observer_lat: float, observer_lon: float
    ) -> None:
        """
        Populate table with filtered objects.

        Args:
            objects: List of (CelestialObject, transit_time) tuples
            observer_lat: Observer latitude
            observer_lon: Observer longitude
        """
        # Disable sorting while populating
        self.table.setSortingEnabled(False)

        # Clear table and remove any widgets
        self.table.clearContents()
        self.table.setRowCount(len(objects))

        for row, (obj, transit_time) in enumerate(objects):
            # Name column - store CelestialObject in UserRole
            # Safely extract name and common_name from instance dict
            try:
                if hasattr(obj, "__dict__"):
                    name = obj.__dict__.get("name", "Unknown")
                    common_name = obj.__dict__.get("common_name", None)
                else:
                    name = getattr(obj, "name", "Unknown")
                    common_name = getattr(obj, "common_name", None)

                # Ensure they're actual values, not descriptors
                name = str(name) if isinstance(name, (str, int, float)) else "Unknown"

                display_name = str(common_name) if common_name and isinstance(common_name, (str, int, float)) else name
            except Exception:
                display_name = "Unknown"

            name_item = QTableWidgetItem(display_name)
            name_item.setData(Qt.ItemDataRole.UserRole, obj)
            self.table.setItem(row, 0, name_item)

            # Type column
            type_name = self._get_verbose_type_name(obj)
            type_item = QTableWidgetItem(type_name)
            self.table.setItem(row, 1, type_item)

            # Magnitude column
            try:
                if hasattr(obj, "__dict__") and "magnitude" in obj.__dict__:
                    magnitude = obj.__dict__["magnitude"]
                else:
                    magnitude = getattr(obj, "magnitude", None)

                if magnitude is not None and isinstance(magnitude, (int, float)):
                    mag_item = QTableWidgetItem(f"{magnitude:.1f}")
                    mag_item.setData(Qt.ItemDataRole.UserRole, magnitude)
                else:
                    mag_item = QTableWidgetItem("N/A")
                    mag_item.setData(Qt.ItemDataRole.UserRole, 999.0)
            except Exception:
                mag_item = QTableWidgetItem("N/A")
                mag_item.setData(Qt.ItemDataRole.UserRole, 999.0)

            self.table.setItem(row, 2, mag_item)

            # Constellation column - safely get the actual value
            try:
                # Access the attribute value directly from instance __dict__ if available
                if hasattr(obj, "__dict__") and "constellation" in obj.__dict__:
                    constellation = obj.__dict__["constellation"]
                else:
                    constellation = getattr(obj, "constellation", None)

                # Only use it if it's a simple type (str, int, etc.), not a descriptor
                if constellation is not None and isinstance(constellation, (str, int, float)):
                    constellation_str = str(constellation)
                else:
                    constellation_str = "N/A"
            except Exception:
                constellation_str = "N/A"

            const_item = QTableWidgetItem(constellation_str)
            self.table.setItem(row, 3, const_item)

            # Transit time column
            transit_str = format_local_time(transit_time, observer_lat, observer_lon)
            transit_item = QTableWidgetItem(transit_str)
            transit_item.setData(Qt.ItemDataRole.UserRole, transit_time)  # For sorting
            self.table.setItem(row, 4, transit_item)

            # Altitude now column
            try:
                from celestron_nexstar.api.core.utils import get_local_timezone

                local_tz = get_local_timezone(observer_lat, observer_lon) or UTC
                altitude, _ = get_object_altitude_azimuth(obj, observer_lat, observer_lon, datetime.now(local_tz))
                alt_str = f"{altitude:.1f}°" if altitude >= 0 else "Below horizon"
                alt_item = QTableWidgetItem(alt_str)
                alt_item.setData(Qt.ItemDataRole.UserRole, altitude)  # For numeric sorting
            except Exception as e:
                obj_name_debug = getattr(obj, "name", "Unknown")
                logger.debug(f"Failed to get altitude for {obj_name_debug}: {e}")
                alt_item = QTableWidgetItem("N/A")
                alt_item.setData(Qt.ItemDataRole.UserRole, -999.0)
            self.table.setItem(row, 5, alt_item)

            # Actions column - Info button
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(4, 2, 4, 2)
            actions_layout.setSpacing(4)

            info_button = QPushButton("Info")
            # Use the same display_name we already extracted
            info_button.clicked.connect(lambda checked, obj_name=display_name: self._on_info_clicked(obj_name))
            actions_layout.addWidget(info_button)
            actions_layout.addStretch()

            self.table.setCellWidget(row, 6, actions_widget)

        # Auto-resize columns
        autosize_table_columns(self.table, stretch_last=False)

        # Re-enable sorting and sort by transit time (column 4)
        self.table.setSortingEnabled(True)
        self.table.sortItems(4, Qt.SortOrder.AscendingOrder)

    def _get_verbose_type_name(self, obj: CelestialObject) -> str:
        """
        Get verbose type name for object.

        Args:
            obj: Celestial object

        Returns:
            Verbose type name
        """
        type_str = str(obj.object_type.value if hasattr(obj.object_type, "value") else obj.object_type)

        # Capitalize and replace underscores
        type_str = type_str.replace("_", " ").title()

        return type_str

    def _show_error_in_table(self, message: str) -> None:
        """
        Show error message in table.

        Args:
            message: Error message to display
        """
        self.table.setRowCount(1)
        self.table.setSortingEnabled(False)

        error_item = QTableWidgetItem(message)
        error_item.setFlags(Qt.ItemFlag.NoItemFlags)
        error_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(0, 0, error_item)
        self.table.setSpan(0, 0, 1, 7)

    def _show_no_objects_message(
        self, start_time: datetime, end_time: datetime, observer_lat: float, observer_lon: float
    ) -> None:
        """
        Show 'no objects' message in table.

        Args:
            start_time: Start of time range
            end_time: End of time range
            observer_lat: Observer latitude
            observer_lon: Observer longitude
        """
        self.table.setRowCount(1)
        self.table.setSortingEnabled(False)

        start_str = format_local_time(start_time, observer_lat, observer_lon)
        end_str = format_local_time(end_time, observer_lat, observer_lon)

        message = f"No objects transiting between {start_str} and {end_str}. Try adjusting the time range."

        no_objects_item = QTableWidgetItem(message)
        no_objects_item.setFlags(Qt.ItemFlag.NoItemFlags)
        no_objects_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(0, 0, no_objects_item)
        self.table.setSpan(0, 0, 1, 7)

        self.status_label.setText("No objects found in selected time range")

    def _update_status_label(
        self, count: int, start_time: datetime, end_time: datetime, observer_lat: float, observer_lon: float
    ) -> None:
        """
        Update status label.

        Args:
            count: Number of objects
            start_time: Start of time range
            end_time: End of time range
            observer_lat: Observer latitude
            observer_lon: Observer longitude
        """
        start_str = format_local_time(start_time, observer_lat, observer_lon)
        end_str = format_local_time(end_time, observer_lat, observer_lon)
        from celestron_nexstar.api.core.utils import get_local_timezone

        local_tz = get_local_timezone(observer_lat, observer_lon) or UTC
        now_str = format_local_time(datetime.now(local_tz), observer_lat, observer_lon)

        self.status_label.setText(
            f"Showing {count} object{'s' if count != 1 else ''} transiting {start_str} - {end_str} "
            f"(Last updated: {now_str})"
        )

    def _apply_time_filter(self) -> None:
        """Apply time filter when user changes range."""
        start = self.start_offset_spinbox.value()
        end = self.end_offset_spinbox.value()

        if start >= end:
            QMessageBox.warning(self, "Invalid Time Range", "Start time must be before end time.")
            return

        self._load_objects()

    def _refresh_data(self) -> None:
        """Auto-refresh handler."""
        logger.info("Sky Now: Auto-refreshing data")

        # Reload objects
        self._load_objects()

    def _on_info_clicked(self, object_name: str) -> None:
        """
        Show ObjectInfoDialog for object.

        Args:
            object_name: Name of object
        """
        try:
            from celestron_nexstar.gui.dialogs.object_info_dialog import ObjectInfoDialog

            dialog = ObjectInfoDialog(self, object_name)
            dialog.exec()
        except Exception as e:
            logger.error(f"Error showing object info: {e}", exc_info=True)
            QMessageBox.warning(self, "Error", f"Failed to show object info: {e}")

    def _on_row_double_clicked(self, item: QTableWidgetItem) -> None:
        """
        Handle double-click on table row.

        Args:
            item: Clicked item
        """
        # Get object name from first column of clicked row
        row = item.row()
        name_item = self.table.item(row, 0)

        if name_item:
            # Use the display name from the table item text (already safely extracted)
            obj_name = name_item.text()
            if obj_name:
                self._on_info_clicked(obj_name)

    def _on_add_all_to_queue(self) -> None:
        """Add all visible objects to goto queue in transit-time order."""
        # Collect objects from table
        objects_to_add: list[CelestialObject] = []

        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            if name_item and name_item.data(Qt.ItemDataRole.UserRole):
                obj = name_item.data(Qt.ItemDataRole.UserRole)
                if isinstance(obj, CelestialObject):
                    objects_to_add.append(obj)

        if not objects_to_add:
            QMessageBox.information(self, "No Objects", "No objects to add to queue.")
            return

        # Validate main window
        if not self.main_window:
            QMessageBox.warning(self, "Queue Unavailable", "Main window reference not available.")
            return

        # Ensure queue window exists
        if not hasattr(self.main_window, "_goto_queue_window") or self.main_window._goto_queue_window is None:
            self.main_window._on_goto_queue()

        # Add objects to queue
        try:
            if self.main_window._goto_queue_window:
                self.main_window._goto_queue_window.add_objects(objects_to_add, notes="Added from Sky Now")

                # Show confirmation
                reply = QMessageBox.information(
                    self,
                    "Added to Queue",
                    f"Added {len(objects_to_add)} object{'s' if len(objects_to_add) != 1 else ''} to goto queue in transit-time order.\n\n"
                    "Would you like to view the queue?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )

                if reply == QMessageBox.StandardButton.Yes:
                    # Show and raise queue window
                    self.main_window._goto_queue_window.show()
                    self.main_window._goto_queue_window.raise_()
                    self.main_window._goto_queue_window.activateWindow()

        except Exception as e:
            logger.error(f"Error adding objects to queue: {e}", exc_info=True)
            QMessageBox.warning(self, "Error", f"Failed to add objects to queue: {e}")

    def _on_auto_refresh_toggled(self, checked: bool) -> None:
        """
        Handle auto-refresh checkbox toggle.

        Args:
            checked: Whether checkbox is checked
        """
        if checked:
            interval_minutes = self.refresh_interval_spinbox.value()
            self.refresh_timer.start(interval_minutes * 60 * 1000)
            logger.info(f"Sky Now: Auto-refresh enabled ({interval_minutes} minutes)")
        else:
            self.refresh_timer.stop()
            logger.info("Sky Now: Auto-refresh disabled")

    def _on_refresh_interval_changed(self, value: int) -> None:
        """
        Handle refresh interval change.

        Args:
            value: New interval in minutes
        """
        if self.refresh_timer.isActive():
            self.refresh_timer.stop()
            self.refresh_timer.start(value * 60 * 1000)
            logger.info(f"Sky Now: Refresh interval changed to {value} minutes")

    def closeEvent(self, event) -> None:  # noqa: N802
        """Handle dialog close event."""
        # Stop refresh timer
        if self.refresh_timer.isActive():
            self.refresh_timer.stop()

        # Wait for worker thread to finish
        if self.worker and self.worker.isRunning():
            self.worker.wait(1000)  # Wait up to 1 second

        super().closeEvent(event)
