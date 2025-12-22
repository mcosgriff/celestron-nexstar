"""
Telescope Connection Dialog

Modal dialog for selecting and configuring telescope connection (Serial or TCP/IP).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from celestron_nexstar.api.core.types import TelescopeConfig


if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class TelescopeConnectionDialog(QDialog):
    """
    Modal dialog to configure and establish telescope connection.

    Supports two connection types:
    - Serial: Direct USB/serial connection
    - TCP/IP: Network connection via WiFi adapter
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the connection dialog."""
        super().__init__(parent)

        self.setWindowTitle("Connect to Telescope")
        self.setMinimumWidth(500)
        self.setMinimumHeight(350)

        # Connection type
        self._connection_type = "serial"

        # Serial widgets
        self.port_combo: QComboBox | None = None
        self.baudrate_combo: QComboBox | None = None
        self.refresh_button: QPushButton | None = None

        # TCP/IP widgets
        self.host_input: QLineEdit | None = None
        self.tcp_port_spinbox: QSpinBox | None = None

        # Status label
        self.status_label: QLabel | None = None

        self._setup_ui()
        self._populate_serial_ports()

    def _setup_ui(self) -> None:
        """Set up the UI layout."""
        layout = QVBoxLayout(self)

        # Header
        header_label = QLabel("Select Connection Type:")
        header_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(header_label)

        # Connection type radio buttons
        radio_layout = QHBoxLayout()

        self.serial_radio = QRadioButton("Serial Connection")
        self.serial_radio.setChecked(True)
        self.serial_radio.toggled.connect(self._on_connection_type_changed)
        radio_layout.addWidget(self.serial_radio)

        self.tcp_radio = QRadioButton("TCP/IP Connection")
        self.tcp_radio.toggled.connect(self._on_connection_type_changed)
        radio_layout.addWidget(self.tcp_radio)

        radio_layout.addStretch()
        layout.addLayout(radio_layout)

        # Stacked widget for different connection types
        self.stacked_widget = QStackedWidget()

        # Serial page
        serial_page = self._create_serial_page()
        self.stacked_widget.addWidget(serial_page)

        # TCP/IP page
        tcp_page = self._create_tcp_page()
        self.stacked_widget.addWidget(tcp_page)

        layout.addWidget(self.stacked_widget)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #E74C3C; font-style: italic;")
        layout.addWidget(self.status_label)

        layout.addStretch()

        # Button box
        button_box = QDialogButtonBox()

        # Connect button
        self.connect_button = button_box.addButton("Connect", QDialogButtonBox.ButtonRole.AcceptRole)
        self.connect_button.setDefault(True)

        # Cancel button
        button_box.addButton(QDialogButtonBox.StandardButton.Cancel)

        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout.addWidget(button_box)

        self.setLayout(layout)

    def _create_serial_page(self) -> QWidget:
        """Create the serial connection configuration page."""
        page = QWidget()
        layout = QFormLayout(page)

        # Info label
        info_label = QLabel("Connect via USB cable")
        info_label.setStyleSheet("color: #666666; font-style: italic;")
        layout.addRow("", info_label)

        # Port selection with refresh button
        port_layout = QHBoxLayout()
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(200)
        port_layout.addWidget(self.port_combo)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self._populate_serial_ports)
        port_layout.addWidget(self.refresh_button)

        layout.addRow("Port:", port_layout)

        # Baudrate selection
        self.baudrate_combo = QComboBox()
        self.baudrate_combo.addItems(["9600", "19200", "38400", "57600", "115200"])
        self.baudrate_combo.setCurrentText("9600")
        layout.addRow("Baud Rate:", self.baudrate_combo)

        return page

    def _create_tcp_page(self) -> QWidget:
        """Create the TCP/IP connection configuration page."""
        page = QWidget()
        layout = QFormLayout(page)

        # Info label
        info_label = QLabel("Connect via WiFi adapter (e.g., SkyPortal)")
        info_label.setStyleSheet("color: #666666; font-style: italic;")
        layout.addRow("", info_label)

        # Host/IP input
        self.host_input = QLineEdit()
        self.host_input.setText("192.168.1.1")
        self.host_input.setPlaceholderText("192.168.1.1 or hostname")
        layout.addRow("Host/IP:", self.host_input)

        # Port input
        self.tcp_port_spinbox = QSpinBox()
        self.tcp_port_spinbox.setMinimum(1)
        self.tcp_port_spinbox.setMaximum(65535)
        self.tcp_port_spinbox.setValue(4030)
        layout.addRow("Port:", self.tcp_port_spinbox)

        return page

    def _on_connection_type_changed(self) -> None:
        """Handle connection type radio button change."""
        if self.serial_radio.isChecked():
            self._connection_type = "serial"
            self.stacked_widget.setCurrentIndex(0)
        else:
            self._connection_type = "tcp"
            self.stacked_widget.setCurrentIndex(1)

        # Clear status
        if self.status_label:
            self.status_label.setText("")

    def _populate_serial_ports(self) -> None:
        """Populate the serial port combo box with available ports."""
        if not self.port_combo:
            return

        # Clear existing items
        self.port_combo.clear()

        # Try to import pyserial for port detection
        try:
            from serial.tools import list_ports

            ports = list_ports.comports()

            if ports:
                for port in ports:
                    # Show port name with description
                    display_name = f"{port.device}"
                    if port.description and port.description != "n/a":
                        display_name += f" - {port.description}"
                    self.port_combo.addItem(display_name, port.device)
            else:
                # No ports found
                self.port_combo.addItem("No serial ports detected", "")
                if self.status_label:
                    self.status_label.setText("No serial ports found. Check USB connection.")

        except ImportError:
            # pyserial not installed, add common port names
            logger.warning("pyserial not installed, using default port names")

            # Common port names for different platforms
            import platform

            system = platform.system()

            if system == "Windows":
                # Windows COM ports
                for i in range(1, 11):
                    self.port_combo.addItem(f"COM{i}", f"COM{i}")
            elif system == "Darwin":
                # macOS ports
                self.port_combo.addItem("/dev/cu.usbserial", "/dev/cu.usbserial")
                self.port_combo.addItem("/dev/cu.usbmodem", "/dev/cu.usbmodem")
            else:
                # Linux ports
                self.port_combo.addItem("/dev/ttyUSB0", "/dev/ttyUSB0")
                self.port_combo.addItem("/dev/ttyUSB1", "/dev/ttyUSB1")
                self.port_combo.addItem("/dev/ttyACM0", "/dev/ttyACM0")

    def get_telescope_config(self) -> TelescopeConfig | None:
        """
        Return TelescopeConfig based on user selection.

        Returns:
            TelescopeConfig if valid configuration, None otherwise
        """
        if self._connection_type == "serial":
            if not self.port_combo or not self.baudrate_combo:
                return None

            # Get port from combo box data (actual device path)
            port = self.port_combo.currentData()
            if not port:
                # Fallback to displayed text
                port = self.port_combo.currentText().split(" - ")[0]

            if not port or port == "No serial ports detected":
                if self.status_label:
                    self.status_label.setText("Please select a valid serial port.")
                return None

            baudrate = int(self.baudrate_combo.currentText())

            return TelescopeConfig(connection_type="serial", port=port, baudrate=baudrate, timeout=2.0)

        else:  # TCP/IP
            if not self.host_input or not self.tcp_port_spinbox:
                return None

            host = self.host_input.text().strip()
            if not host:
                if self.status_label:
                    self.status_label.setText("Please enter a host/IP address.")
                return None

            tcp_port = self.tcp_port_spinbox.value()

            return TelescopeConfig(connection_type="tcp", host=host, tcp_port=tcp_port, timeout=2.0)

    def accept(self) -> None:
        """Override accept to validate configuration first."""
        config = self.get_telescope_config()
        if config is None:
            return  # Don't close dialog if config is invalid

        super().accept()
