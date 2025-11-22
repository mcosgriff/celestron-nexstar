"""
Main entry point for the GUI application.
"""

import sys

from PySide6.QtWidgets import QApplication

from celestron_nexstar.gui.main_window import MainWindow


def main() -> int:
    """Main entry point for the GUI application."""
    app = QApplication(sys.argv)
    app.setApplicationName("Celestron NexStar")
    app.setOrganizationName("Celestron NexStar")

    # Create and show main window
    window = MainWindow()
    window.show()

    return int(app.exec())


if __name__ == "__main__":
    sys.exit(main())
