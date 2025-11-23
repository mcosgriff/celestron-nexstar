"""
Main entry point for the GUI application.
"""

import sys

from PySide6.QtWidgets import QApplication

from celestron_nexstar.api.core.utils import configure_astropy_iers
from celestron_nexstar.gui.main_window import MainWindow
from celestron_nexstar.gui.themes import FusionTheme, ThemeMode


def main() -> int:
    """Main entry point for the GUI application."""
    # Configure astropy IERS data handling early to avoid warnings
    configure_astropy_iers()

    app = QApplication(sys.argv)
    app.setApplicationName("Celestron NexStar")
    app.setOrganizationName("Celestron NexStar")

    # Pre-import qtawesome to ensure fonts/resources are loaded
    try:
        import qtawesome as qta  # type: ignore[import-not-found]

        # Test creating an icon to trigger font loading
        _ = qta.icon("fa5s.link")
    except Exception:
        # If qtawesome fails to load, we'll fall back to theme icons
        pass

    # Load JetBrains Mono font
    try:
        from celestron_nexstar.gui.utils.font_loader import load_jetbrains_mono

        font_family = load_jetbrains_mono()
        if font_family:
            # Store font family name for use in widgets
            app.setProperty("monospace_font", font_family)
    except Exception:
        # If font loading fails, widgets will fall back to system monospace fonts
        pass

    # Initialize and apply theme (default to SYSTEM)
    theme = FusionTheme(ThemeMode.SYSTEM)
    theme.apply(app)

    # Create and show main window
    window = MainWindow(theme)
    window.show()

    return int(app.exec())


if __name__ == "__main__":
    sys.exit(main())
