"""
TUI Application

Main application class for the full-screen terminal user interface.
"""

from __future__ import annotations

from prompt_toolkit import Application
from prompt_toolkit.layout.layout import Layout

from .bindings import create_key_bindings
from .layout import create_layout


class TUIApplication:
    """Full-screen TUI application for telescope control and observing."""

    def __init__(self) -> None:
        """Initialize the TUI application."""
        # Create layout
        root_container = create_layout()
        layout = Layout(root_container)

        # Create key bindings
        key_bindings = create_key_bindings()

        # Create application
        self.app = Application(
            layout=layout,
            key_bindings=key_bindings,
            full_screen=True,
            refresh_interval=2.0,  # Refresh every 2 seconds
            mouse_support=False,  # Disable mouse for now
        )

    def run(self) -> None:
        """Run the TUI application."""
        self.app.run()

