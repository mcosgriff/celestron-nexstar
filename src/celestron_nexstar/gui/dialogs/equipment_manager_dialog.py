"""
Equipment Manager Dialog

Dialog to manage astronomical equipment (eyepieces, filters, cameras)
with field of view calculations and usage tracking.
"""

import asyncio
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from celestron_nexstar.api.equipment import (
    calculate_fov,
    delete_camera,
    delete_filter,
    get_cameras,
    get_filters,
)
from celestron_nexstar.api.observation.optics import (
    COMMON_EYEPIECES,
    OpticalConfiguration,
    TelescopeModel,
    get_current_configuration,
    get_telescope_specs,
    set_current_configuration,
)


if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


class EquipmentManagerDialog(QDialog):
    """Dialog to manage astronomical equipment."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the equipment manager dialog."""
        super().__init__(parent)
        self.setWindowTitle("Equipment Manager")
        self.setMinimumWidth(700)
        self.setMinimumHeight(500)
        self.resize(700, 500)

        # Create layout
        layout = QVBoxLayout(self)

        # Header
        header_label = QLabel("Equipment Manager")
        header_label.setStyleSheet("font-size: 16pt; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header_label)

        # Create tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self._create_telescopes_tab(), "Telescopes")
        self.tab_widget.addTab(self._create_eyepieces_tab(), "Eyepieces")
        self.tab_widget.addTab(self._create_filters_tab(), "Filters")
        self.tab_widget.addTab(self._create_cameras_tab(), "Cameras")
        self.tab_widget.addTab(self._create_fov_calculator_tab(), "FOV Calculator")
        layout.addWidget(self.tab_widget)

        # Add button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Load data
        self._load_all_data()

    def _is_dark_theme(self) -> bool:
        """Detect if the current theme is dark mode."""
        from PySide6.QtGui import QGuiApplication, QPalette

        app = QGuiApplication.instance()
        if app and isinstance(app, QGuiApplication):
            palette = app.palette()
            window_color = palette.color(QPalette.ColorRole.Window)
            brightness = window_color.lightness()
            return bool(brightness < 128)
        return False

    def _update_fov_results_style(self) -> None:
        """Update FOV results label styling based on theme."""
        is_dark = self._is_dark_theme()
        if is_dark:
            # Dark theme: light text on dark background
            bg_color = "#2d2d2d"
            text_color = "#ffffff"
        else:
            # Light theme: dark text on light background
            bg_color = "#f5f5f5"
            text_color = "#000000"

        self.fov_results_label.setStyleSheet(
            f"padding: 10px; background-color: {bg_color}; color: {text_color}; border-radius: 5px;"
        )

    def _create_telescopes_tab(self) -> QWidget:
        """Create the telescopes tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Header
        header_label = QLabel("Telescopes")
        header_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        layout.addWidget(header_label)

        info_label = QLabel("Select your current telescope model. This will be used for field of view calculations.")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Current telescope selection
        form_layout = QFormLayout()

        self.telescope_combo = QComboBox()
        for model in TelescopeModel:
            specs = get_telescope_specs(model)
            display_text = f"{specs.display_name} ({specs.aperture_mm:.0f}mm, f/{specs.focal_ratio:.1f})"
            self.telescope_combo.addItem(display_text, model)

        # Set current telescope if configured
        try:
            current_config = get_current_configuration()
            current_model = current_config.telescope.model
            for i in range(self.telescope_combo.count()):
                item_data = self.telescope_combo.itemData(i)
                # Compare enum values, handling both enum and string cases
                if isinstance(item_data, TelescopeModel):
                    if item_data == current_model:
                        self.telescope_combo.setCurrentIndex(i)
                        break
                elif str(item_data) == current_model.value:
                    self.telescope_combo.setCurrentIndex(i)
                    break
        except Exception:
            pass

        self.telescope_combo.currentIndexChanged.connect(self._on_telescope_changed)
        form_layout.addRow("Current Telescope:", self.telescope_combo)

        layout.addLayout(form_layout)
        layout.addStretch()

        return widget

    def _create_eyepieces_tab(self) -> QWidget:
        """Create the eyepieces tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Header
        header_label = QLabel("Celestron NexStar SE Eyepieces")
        header_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        layout.addWidget(header_label)

        info_label = QLabel("Select your current eyepiece. Only one eyepiece can be active at a time.")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Scroll area for eyepiece list
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        eyepieces_widget = QWidget()
        eyepieces_layout = QVBoxLayout(eyepieces_widget)
        eyepieces_layout.setSpacing(5)

        # Store radio buttons for reference
        self.eyepiece_radios: dict[str, QRadioButton] = {}

        # Get current eyepiece configuration
        try:
            current_config = get_current_configuration()
            current_eyepiece = current_config.eyepiece
            # Match by focal length and apparent FOV (with small tolerance)
            current_key = None
            for key, ep in COMMON_EYEPIECES.items():
                if (
                    abs(ep.focal_length_mm - current_eyepiece.focal_length_mm) < 0.1
                    and abs(ep.apparent_fov_deg - current_eyepiece.apparent_fov_deg) < 0.1
                ):
                    current_key = key
                    break
        except Exception:
            current_key = "25mm_plossl"  # Default

        # Sort eyepieces by focal length (longest first)
        sorted_eyepieces = sorted(COMMON_EYEPIECES.items(), key=lambda x: x[1].focal_length_mm, reverse=True)

        # Create radio buttons for each eyepiece
        for key, eyepiece in sorted_eyepieces:
            radio = QRadioButton(eyepiece.name or f"{eyepiece.focal_length_mm}mm")
            radio.setChecked(key == current_key)

            # Add details as tooltip
            tooltip = f"Focal Length: {eyepiece.focal_length_mm}mm\nApparent FOV: {eyepiece.apparent_fov_deg}°"
            radio.setToolTip(tooltip)

            # Connect to handler
            radio.toggled.connect(lambda checked, k=key: self._on_eyepiece_selected(k) if checked else None)

            self.eyepiece_radios[key] = radio
            eyepieces_layout.addWidget(radio)

        eyepieces_layout.addStretch()
        scroll_area.setWidget(eyepieces_widget)
        layout.addWidget(scroll_area)

        return widget

    def _create_filters_tab(self) -> QWidget:
        """Create the filters tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Header with add button
        header_layout = QHBoxLayout()
        header_label = QLabel("Filters")
        header_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        header_layout.addWidget(header_label)
        header_layout.addStretch()

        add_button = QPushButton("Add Filter")
        add_button.clicked.connect(self._on_add_filter)
        header_layout.addWidget(add_button)
        layout.addLayout(header_layout)

        # Create table
        self.filters_table = QTableWidget()
        self.filters_table.setColumnCount(6)
        header_labels = ["Name", "Type", "Barrel Size", "Transmission (%)", "Usage", "Actions"]
        self.filters_table.setHorizontalHeaderLabels(header_labels)
        self._setup_table(self.filters_table, header_labels)
        layout.addWidget(self.filters_table)

        return widget

    def _create_cameras_tab(self) -> QWidget:
        """Create the cameras tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Header with add button
        header_layout = QHBoxLayout()
        header_label = QLabel("Cameras")
        header_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        header_layout.addWidget(header_label)
        header_layout.addStretch()

        add_button = QPushButton("Add Camera")
        add_button.clicked.connect(self._on_add_camera)
        header_layout.addWidget(add_button)
        layout.addLayout(header_layout)

        # Create table
        self.cameras_table = QTableWidget()
        self.cameras_table.setColumnCount(6)
        header_labels = ["Name", "Type", "Sensor Size (mm)", "Resolution", "Usage", "Actions"]
        self.cameras_table.setHorizontalHeaderLabels(header_labels)
        self._setup_table(self.cameras_table, header_labels)
        layout.addWidget(self.cameras_table)

        return widget

    def _create_fov_calculator_tab(self) -> QWidget:
        """Create the field of view calculator tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Header
        header_label = QLabel("Field of View Calculator")
        header_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        layout.addWidget(header_label)

        # Form layout for inputs
        form_layout = QFormLayout()

        # Telescope selection
        self.fov_telescope_combo = QComboBox()
        for model in TelescopeModel:
            specs = get_telescope_specs(model)
            display_text = f"{specs.display_name} ({specs.aperture_mm:.0f}mm, f/{specs.focal_ratio:.1f})"
            self.fov_telescope_combo.addItem(display_text, model)
        self.fov_telescope_combo.currentIndexChanged.connect(self._on_fov_calculate)
        form_layout.addRow("Telescope:", self.fov_telescope_combo)

        # Eyepiece focal length
        self.fov_eyepiece_focal = QDoubleSpinBox()
        self.fov_eyepiece_focal.setRange(1.0, 100.0)
        self.fov_eyepiece_focal.setSuffix(" mm")
        self.fov_eyepiece_focal.setDecimals(1)
        self.fov_eyepiece_focal.setSingleStep(1.0)
        self.fov_eyepiece_focal.valueChanged.connect(self._on_fov_calculate)
        form_layout.addRow("Eyepiece Focal Length:", self.fov_eyepiece_focal)

        # Eyepiece apparent FOV
        self.fov_eyepiece_afov = QDoubleSpinBox()
        self.fov_eyepiece_afov.setRange(30.0, 120.0)
        self.fov_eyepiece_afov.setSuffix(" °")
        self.fov_eyepiece_afov.setDecimals(1)
        self.fov_eyepiece_afov.setSingleStep(5.0)
        self.fov_eyepiece_afov.setValue(50.0)  # Default Plössl FOV
        self.fov_eyepiece_afov.valueChanged.connect(self._on_fov_calculate)
        form_layout.addRow("Apparent FOV:", self.fov_eyepiece_afov)

        layout.addLayout(form_layout)

        # Results section
        results_label = QLabel("Results:")
        results_label.setStyleSheet("font-size: 12pt; font-weight: bold; margin-top: 10px;")
        layout.addWidget(results_label)

        self.fov_results_label = QLabel()
        self.fov_results_label.setWordWrap(True)
        # Set theme-aware styling
        self._update_fov_results_style()
        layout.addWidget(self.fov_results_label)

        layout.addStretch()

        # Pre-fill with current configuration
        self._prefill_fov_calculator()

        return widget

    def _prefill_fov_calculator(self) -> None:
        """Pre-fill FOV calculator with current telescope and eyepiece configuration."""
        try:
            current_config = get_current_configuration()

            # Set telescope
            current_model = current_config.telescope.model
            for i in range(self.fov_telescope_combo.count()):
                item_data = self.fov_telescope_combo.itemData(i)
                # Compare enum values, handling both enum and string cases
                if isinstance(item_data, TelescopeModel):
                    if item_data == current_model:
                        self.fov_telescope_combo.setCurrentIndex(i)
                        break
                elif str(item_data) == current_model.value:
                    self.fov_telescope_combo.setCurrentIndex(i)
                    break

            # Set eyepiece
            self.fov_eyepiece_focal.setValue(current_config.eyepiece.focal_length_mm)
            self.fov_eyepiece_afov.setValue(current_config.eyepiece.apparent_fov_deg)

            # Calculate initial FOV
            self._on_fov_calculate()
        except Exception:
            # If no config, just use defaults
            pass

    def _on_fov_calculate(self) -> None:
        """Calculate and display field of view."""
        try:
            telescope_model_data = self.fov_telescope_combo.currentData()
            eyepiece_focal = self.fov_eyepiece_focal.value()
            eyepiece_afov = self.fov_eyepiece_afov.value()

            if not telescope_model_data or not eyepiece_focal:
                self.fov_results_label.setText("Please select a telescope and enter eyepiece focal length.")
                return

            # Handle both enum and string (currentData might return the enum directly)
            if isinstance(telescope_model_data, TelescopeModel):
                telescope_model_str = telescope_model_data.value
            else:
                telescope_model_str = str(telescope_model_data)

            result = calculate_fov(
                telescope_model=telescope_model_str,
                eyepiece_focal_length_mm=eyepiece_focal,
                eyepiece_apparent_fov_deg=eyepiece_afov,
            )

            if result["magnification"] is None:
                self.fov_results_label.setText("Error calculating field of view.")
                return

            results_text = f"""
            <b>Magnification:</b> {result["magnification"]:.1f}x<br>
            <b>Exit Pupil:</b> {result["exit_pupil_mm"]:.2f} mm<br>
            <b>True Field of View:</b> {result["true_fov_deg"]:.3f}° ({result["true_fov_arcmin"]:.1f} arcmin)
            """
            self.fov_results_label.setText(results_text)
        except Exception as e:
            logger.error(f"Error calculating FOV: {e}", exc_info=True)
            self.fov_results_label.setText("Error calculating field of view.")

    def _on_telescope_changed(self) -> None:
        """Handle telescope selection change."""
        try:
            selected_model_data = self.telescope_combo.currentData()
            if selected_model_data:
                # Convert to TelescopeModel enum if needed
                if isinstance(selected_model_data, TelescopeModel):
                    selected_model = selected_model_data
                else:
                    # Try to convert string to enum
                    selected_model = TelescopeModel(str(selected_model_data))

                # Get current eyepiece config
                current_config = get_current_configuration()
                telescope = get_telescope_specs(selected_model)

                # Update configuration
                new_config = OpticalConfiguration(
                    telescope=telescope,
                    eyepiece=current_config.eyepiece,
                )
                set_current_configuration(new_config)
                logger.info(f"Telescope changed to {telescope.display_name}")
        except Exception as e:
            logger.error(f"Error changing telescope: {e}", exc_info=True)

    def _setup_table(self, table: QTableWidget, header_labels: list[str]) -> None:
        """Set up table with proper column sizing."""
        header = table.horizontalHeader()
        header.setStretchLastSection(False)

        # Calculate minimum widths based on header text
        font_metrics = QFontMetrics(header.font())
        min_widths = [font_metrics.horizontalAdvance(label) + 20 for label in header_labels]

        # Set all columns to Interactive mode (resizable) and set minimum widths
        for col in range(table.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            header.setMinimumSectionSize(min_widths[col])

        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(True)

    def _load_all_data(self) -> None:
        """Load all equipment data."""
        # Eyepieces are now loaded from COMMON_EYEPIECES, no database needed
        self._load_filters()
        self._load_cameras()

    def _on_eyepiece_selected(self, eyepiece_key: str) -> None:
        """Handle eyepiece selection."""
        try:
            eyepiece = COMMON_EYEPIECES[eyepiece_key]
            current_config = get_current_configuration()

            # Update configuration with new eyepiece
            new_config = OpticalConfiguration(
                telescope=current_config.telescope,
                eyepiece=eyepiece,
            )
            set_current_configuration(new_config)
            logger.info(f"Eyepiece changed to {eyepiece.name or f'{eyepiece.focal_length_mm}mm'}")

            # Update FOV calculator if it's visible
            if hasattr(self, "fov_eyepiece_focal"):
                self.fov_eyepiece_focal.setValue(eyepiece.focal_length_mm)
                self.fov_eyepiece_afov.setValue(eyepiece.apparent_fov_deg)
                self._on_fov_calculate()
        except Exception as e:
            logger.error(f"Error changing eyepiece: {e}", exc_info=True)

    def _load_filters(self) -> None:
        """Load filters from database and populate table."""
        try:
            filters = asyncio.run(get_filters())
            self.filters_table.setRowCount(len(filters))

            for row, f in enumerate(filters):
                # Name
                self.filters_table.setItem(row, 0, QTableWidgetItem(f["name"]))
                # Type
                self.filters_table.setItem(row, 1, QTableWidgetItem(f["filter_type"]))
                # Barrel Size
                barrel_text = f"{f['barrel_size_mm']:.1f}mm" if f["barrel_size_mm"] else "-"
                self.filters_table.setItem(row, 2, QTableWidgetItem(barrel_text))
                # Transmission
                trans_text = f"{f['transmission_percent']:.1f}%" if f["transmission_percent"] else "-"
                self.filters_table.setItem(row, 3, QTableWidgetItem(trans_text))
                # Usage
                self.filters_table.setItem(row, 4, QTableWidgetItem(str(f["usage_count"])))
                # Actions
                actions_widget = QWidget()
                actions_layout = QHBoxLayout(actions_widget)
                actions_layout.setContentsMargins(2, 2, 2, 2)

                edit_button = QPushButton("Edit")
                edit_button.clicked.connect(lambda checked, fid=f["id"]: self._on_edit_filter(fid))
                actions_layout.addWidget(edit_button)

                delete_button = QPushButton("Delete")
                delete_button.clicked.connect(lambda checked, fid=f["id"]: self._on_delete_filter(fid))
                actions_layout.addWidget(delete_button)

                self.filters_table.setCellWidget(row, 5, actions_widget)

            # Resize columns to contents
            self.filters_table.resizeColumnsToContents()
            # Switch back to Interactive mode
            header = self.filters_table.horizontalHeader()
            for col in range(self.filters_table.columnCount()):
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        except Exception as e:
            logger.error(f"Error loading filters: {e}", exc_info=True)

    def _load_cameras(self) -> None:
        """Load cameras from database and populate table."""
        try:
            cameras = asyncio.run(get_cameras())
            self.cameras_table.setRowCount(len(cameras))

            for row, cam in enumerate(cameras):
                # Name
                self.cameras_table.setItem(row, 0, QTableWidgetItem(cam["name"]))
                # Type
                self.cameras_table.setItem(row, 1, QTableWidgetItem(cam["camera_type"]))
                # Sensor Size
                sensor_text = f"{cam['sensor_width_mm']:.1f} * {cam['sensor_height_mm']:.1f}mm"
                self.cameras_table.setItem(row, 2, QTableWidgetItem(sensor_text))
                # Resolution
                if cam["resolution_width"] and cam["resolution_height"]:
                    res_text = f"{cam['resolution_width']} * {cam['resolution_height']}"
                else:
                    res_text = "-"
                self.cameras_table.setItem(row, 3, QTableWidgetItem(res_text))
                # Usage
                self.cameras_table.setItem(row, 4, QTableWidgetItem(str(cam["usage_count"])))
                # Actions
                actions_widget = QWidget()
                actions_layout = QHBoxLayout(actions_widget)
                actions_layout.setContentsMargins(2, 2, 2, 2)

                edit_button = QPushButton("Edit")
                edit_button.clicked.connect(lambda checked, cid=cam["id"]: self._on_edit_camera(cid))
                actions_layout.addWidget(edit_button)

                delete_button = QPushButton("Delete")
                delete_button.clicked.connect(lambda checked, cid=cam["id"]: self._on_delete_camera(cid))
                actions_layout.addWidget(delete_button)

                self.cameras_table.setCellWidget(row, 5, actions_widget)

            # Resize columns to contents
            self.cameras_table.resizeColumnsToContents()
            # Switch back to Interactive mode
            header = self.cameras_table.horizontalHeader()
            for col in range(self.cameras_table.columnCount()):
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        except Exception as e:
            logger.error(f"Error loading cameras: {e}", exc_info=True)

    def _on_add_filter(self) -> None:
        """Handle add filter button click."""
        # TODO: Implement add/edit dialog
        logger.info("Add filter clicked - dialog to be implemented")

    def _on_edit_filter(self, filter_id: int) -> None:
        """Handle edit filter button click."""
        # TODO: Implement add/edit dialog
        logger.info(f"Edit filter {filter_id} clicked - dialog to be implemented")

    def _on_delete_filter(self, filter_id: int) -> None:
        """Handle delete filter button click."""
        try:
            success = asyncio.run(delete_filter(filter_id))
            if success:
                self._load_filters()
        except Exception as e:
            logger.error(f"Error deleting filter: {e}", exc_info=True)

    def _on_add_camera(self) -> None:
        """Handle add camera button click."""
        # TODO: Implement add/edit dialog
        logger.info("Add camera clicked - dialog to be implemented")

    def _on_edit_camera(self, camera_id: int) -> None:
        """Handle edit camera button click."""
        # TODO: Implement add/edit dialog
        logger.info(f"Edit camera {camera_id} clicked - dialog to be implemented")

    def _on_delete_camera(self, camera_id: int) -> None:
        """Handle delete camera button click."""
        try:
            success = asyncio.run(delete_camera(camera_id))
            if success:
                self._load_cameras()
        except Exception as e:
            logger.error(f"Error deleting camera: {e}", exc_info=True)
