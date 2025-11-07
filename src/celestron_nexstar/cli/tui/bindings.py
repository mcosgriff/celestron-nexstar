"""
Key Bindings

Defines keyboard shortcuts for the TUI application.
"""

from __future__ import annotations

from prompt_toolkit.key_binding import KeyBindings


def create_key_bindings() -> KeyBindings:
    """
    Create key bindings for the TUI application.

    Returns:
        KeyBindings instance with all keyboard shortcuts
    """
    kb = KeyBindings()

    @kb.add("q")
    @kb.add("c-q")
    def exit_app(event):
        """Quit application."""
        event.app.exit()

    @kb.add("r")
    def refresh_all(event):
        """Force refresh all panes."""
        event.app.invalidate()

    @kb.add("1")
    def focus_dataset(event):
        """Focus dataset pane."""
        # Will be implemented when we have pane references
        event.app.invalidate()

    @kb.add("2")
    def focus_conditions(event):
        """Focus conditions pane."""
        # Will be implemented when we have pane references
        event.app.invalidate()

    @kb.add("3")
    def focus_visible(event):
        """Focus visible objects pane."""
        # Will be implemented when we have pane references
        event.app.invalidate()

    @kb.add("c-c")
    def interrupt(event):
        """Handle Ctrl+C gracefully."""
        event.app.exit()

    return kb

