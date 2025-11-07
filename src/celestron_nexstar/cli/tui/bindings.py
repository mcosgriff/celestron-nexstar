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
        from .state import get_state

        state = get_state()
        state.focused_pane = "visible"
        event.app.invalidate()

    @kb.add("t")
    def change_telescope(event):
        """Change telescope model."""
        # Exit app with result code to trigger interactive selection
        event.app.exit(result="change_telescope")

    @kb.add("e")
    def change_eyepiece(event):
        """Change eyepiece."""
        # Exit app with result code to trigger interactive selection
        event.app.exit(result="change_eyepiece")

    @kb.add("up")
    def move_up(event):
        """Move selection up in visible objects pane."""
        from .state import get_state

        state = get_state()
        if state.focused_pane == "visible":
            state.move_selection_up()
            event.app.invalidate()

    @kb.add("down")
    def move_down(event):
        """Move selection down in visible objects pane."""
        from .state import get_state

        state = get_state()
        if state.focused_pane == "visible":
            state.move_selection_down()
            event.app.invalidate()

    @kb.add("enter")
    def show_detail(event):
        """Toggle detail view for selected object."""
        from .state import get_state

        state = get_state()
        if state.focused_pane == "visible" and state.get_selected_object():
            state.toggle_detail()
            event.app.invalidate()

    @kb.add("escape")
    def close_detail(event):
        """Close detail view."""
        from .state import get_state

        state = get_state()
        if state.show_detail:
            state.show_detail = False
            event.app.invalidate()

    @kb.add("c-c")
    def interrupt(event):
        """Handle Ctrl+C gracefully."""
        event.app.exit()

    return kb
