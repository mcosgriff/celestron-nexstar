"""
Main entry point for the GUI application.
"""

import sys

from PySide6.QtWidgets import QApplication

from celestron_nexstar.gui.main_window import MainWindow
from celestron_nexstar.gui.themes import ColorStyle, QtMaterialTheme, ThemeMode


def main() -> int:
    """Main entry point for the GUI application."""
    app = QApplication(sys.argv)
    app.setApplicationName("Celestron NexStar")
    app.setOrganizationName("Celestron NexStar")

    # Initialize and apply theme
    theme = QtMaterialTheme(ThemeMode.SYSTEM, ColorStyle.BLUE, dense=True)
    theme.apply(app)

    # Create and show main window
    window = MainWindow(theme)
    window.show()

    return int(app.exec())


if __name__ == "__main__":
    sys.exit(main())
