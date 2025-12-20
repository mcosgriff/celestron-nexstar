"""
Main entry point for the GUI application.
"""

# Set environment variables for Wayland window decorations (needed for COSMIC)
# This MUST be done before any Qt imports
import os  # noqa: I001  # Must import os first to set env vars before Qt

# Force enable window decorations on Wayland (required for window to be movable)
# This is critical for COSMIC desktop environment
os.environ["QT_WAYLAND_DISABLE_WINDOWDECORATION"] = "0"

# Additional Qt Wayland settings that may help
# Force Qt to use client-side decorations if available
if "QT_WAYLAND_SHELL_INTEGRATION" not in os.environ:
    # Try xdg-shell if available (standard Wayland protocol)
    os.environ.setdefault("QT_WAYLAND_SHELL_INTEGRATION", "xdg-shell")

import logging
import sys
from pathlib import Path

# Import duckdb BEFORE any api imports to avoid deal import hook issues
# This must happen before deal.activate() is called (which happens in api/__init__.py)
# duckdb is required by starplot, and importing it early ensures it's cached before deal's hook intercepts imports
import duckdb  # type: ignore[import-untyped]  # noqa: F401

# Import starplot after duckdb to ensure it can import duckdb successfully
import starplot  # type: ignore[import-untyped]  # noqa: F401
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from celestron_nexstar.api.core.utils import configure_astropy_iers
from celestron_nexstar.gui.main_window import MainWindow
from celestron_nexstar.gui.themes import FusionTheme, ThemeMode


def _setup_logging() -> None:
    """Set up logging to file and console."""
    # Create log directory in user's config directory
    config_dir = Path.home() / ".config" / "celestron-nexstar"
    config_dir.mkdir(parents=True, exist_ok=True)
    log_file = config_dir / "nexstar-gui.log"

    # Configure logging format
    log_format = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Set up root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # File handler - write all logs to file
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(log_format, date_format)
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Console handler - only show INFO and above to avoid cluttering console
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter("%(levelname)-8s %(name)s: %(message)s")
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # Log where the log file is located
    logger = logging.getLogger(__name__)
    logger.info(f"Logging to file: {log_file}")


def main() -> int:
    """Main entry point for the GUI application."""
    # Set up logging first
    _setup_logging()
    logger = logging.getLogger(__name__)

    # Verify Wayland environment variable is set (for debugging)
    wayland_decoration = os.environ.get("QT_WAYLAND_DISABLE_WINDOWDECORATION")
    logger.info(f"QT_WAYLAND_DISABLE_WINDOWDECORATION={wayland_decoration}")

    # Configure astropy IERS data handling early to avoid warnings
    configure_astropy_iers()

    app = QApplication(sys.argv)

    # Log platform information for debugging
    try:
        platform_name = app.platformName() if hasattr(app, "platformName") else "unknown"
        logger.info(f"Qt platform: {platform_name}")
    except Exception:
        pass
    app.setApplicationName("Celestron NexStar")
    app.setApplicationDisplayName("Celestron NexStar")
    app.setOrganizationName("Celestron NexStar")

    # Pre-import qtawesome to ensure fonts/resources are loaded
    try:
        import qtawesome as qta  # type: ignore[import-untyped]

        # Test creating an icon to trigger font loading
        _ = qta.icon("fa5s.link")
    except Exception:
        # If qtawesome fails to load, we'll fall back to theme icons
        pass

    # Set application/window icon (shows in macOS Dock, GNOME dock, Windows taskbar)
    icon_path = Path(__file__).parent / "assets" / "icons" / "app.svg"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

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
