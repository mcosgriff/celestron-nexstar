"""
Key Bindings

Defines keyboard shortcuts for the TUI application.
"""

from __future__ import annotations

from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent


def create_key_bindings() -> KeyBindings:
    """
    Create key bindings for the TUI application.

    Returns:
        KeyBindings instance with all keyboard shortcuts
    """
    kb = KeyBindings()

    @kb.add("q")
    @kb.add("c-q")
    def exit_app(event: KeyPressEvent) -> None:
        """Quit application."""
        event.app.exit()

    @kb.add("r")
    def refresh_all(event: KeyPressEvent) -> None:
        """Force refresh all panes."""
        event.app.invalidate()

    @kb.add("1")
    def focus_dataset(event: KeyPressEvent) -> None:
        """Focus dataset pane."""
        from .state import get_state

        state = get_state()
        state.focused_pane = "dataset"
        event.app.invalidate()

    @kb.add("2")
    def focus_conditions(event: KeyPressEvent) -> None:
        """Focus conditions pane."""
        from .state import get_state

        state = get_state()
        state.focused_pane = "conditions"
        event.app.invalidate()

    @kb.add("3")
    def focus_visible(event: KeyPressEvent) -> None:
        """Focus visible objects pane."""
        from .state import get_state

        state = get_state()
        state.focused_pane = "visible"
        event.app.invalidate()

    @kb.add("t")
    def change_telescope(event: KeyPressEvent) -> None:
        """Change telescope model."""
        # Exit app with result code to trigger interactive selection
        event.app.exit(result="change_telescope")

    @kb.add("e")
    def change_eyepiece(event: KeyPressEvent) -> None:
        """Change eyepiece."""
        # Exit app with result code to trigger interactive selection
        event.app.exit(result="change_eyepiece")

    @kb.add("up")
    def move_up(event: KeyPressEvent) -> None:
        """Move selection up in visible objects pane."""
        from .state import get_state

        state = get_state()
        if state.focused_pane == "visible":
            state.move_selection_up()
            event.app.invalidate()

    @kb.add("down")
    def move_down(event: KeyPressEvent) -> None:
        """Move selection down in visible objects pane."""
        from .state import get_state

        state = get_state()
        if state.focused_pane == "visible":
            state.move_selection_down()
            event.app.invalidate()

    @kb.add("enter")
    def show_detail(event: KeyPressEvent) -> None:
        """Toggle detail view for selected object."""
        from .state import get_state

        state = get_state()
        if state.focused_pane == "visible" and state.get_selected_object():
            state.toggle_detail()
            event.app.invalidate()

    @kb.add("u")
    def toggle_time_mode(event: KeyPressEvent) -> None:
        """Toggle between local and UTC time display."""
        from .state import get_state

        state = get_state()
        state.toggle_time_mode()
        event.app.invalidate()

    @kb.add("c-c")
    def interrupt(event: KeyPressEvent) -> None:
        """Handle Ctrl+C gracefully."""
        event.app.exit()

    @kb.add("s")
    def cycle_sort(event: KeyPressEvent) -> None:
        """Cycle through sort options."""
        from .state import get_state

        state = get_state()
        if state.focused_pane == "visible":
            state.cycle_sort_by()
            event.app.invalidate()
        else:
            # Start/stop session
            if state.session_start_time is None:
                from datetime import datetime

                state.session_start_time = datetime.now()
            else:
                state.session_start_time = None
            event.app.invalidate()

    @kb.add("r")
    def toggle_reverse(event: KeyPressEvent) -> None:
        """Toggle sort direction."""
        from .state import get_state

        state = get_state()
        if state.focused_pane == "visible":
            state.toggle_sort_direction()
            event.app.invalidate()
        else:
            # Refresh
            event.app.invalidate()

    @kb.add("f")
    def filter_menu(event: KeyPressEvent) -> None:
        """Toggle filter menu or cycle type filter."""
        from .state import get_state

        state = get_state()
        if state.focused_pane == "visible":
            # Cycle through common object types for filtering
            object_types = [None, "galaxy", "star", "nebula", "cluster", "planet"]
            try:
                current_idx = object_types.index(state.filter_type)
                next_idx = (current_idx + 1) % len(object_types)
            except ValueError:
                next_idx = 0
            state.filter_type = object_types[next_idx]
            state.filter_menu_active = state.filter_type is not None
            event.app.invalidate()
        else:
            event.app.invalidate()

    @kb.add("/")
    def search_mode(event: KeyPressEvent) -> None:
        """Enter search mode (will prompt for text)."""
        from .state import get_state

        state = get_state()
        if state.focused_pane == "visible":
            # Exit to show search prompt
            state.search_mode = True
            event.app.exit(result="search_mode")
        else:
            event.app.invalidate()

    @kb.add("escape")
    def close_search_or_filter(event: KeyPressEvent) -> None:
        """Close search mode or filter menu."""
        from .state import get_state

        state = get_state()
        if state.search_mode:
            state.search_mode = False
            state.search_query = ""
            event.app.invalidate()
        elif state.filter_menu_active:
            state.filter_menu_active = False
            state.filter_type = None
            event.app.invalidate()
        elif state.show_detail:
            state.show_detail = False
            event.app.invalidate()

    @kb.add("c")
    def connect_telescope(event: KeyPressEvent) -> None:
        """Connect/disconnect telescope."""
        event.app.exit(result="connect_telescope")

    @kb.add("g")
    def goto_object(event: KeyPressEvent) -> None:
        """Goto selected object."""
        from .state import get_state

        state = get_state()
        if state.focused_pane == "visible" and state.get_selected_object():
            event.app.exit(result="goto_object")
        else:
            event.app.invalidate()

    @kb.add("p")
    def park_telescope(event: KeyPressEvent) -> None:
        """Park telescope."""
        event.app.exit(result="park_telescope")

    @kb.add("m")
    def tracking_mode(event: KeyPressEvent) -> None:
        """Change tracking mode."""
        event.app.exit(result="tracking_mode")

    @kb.add("?")
    def show_help(event: KeyPressEvent) -> None:
        """Show help overlay."""
        event.app.exit(result="help")

    @kb.add("h")
    def show_help_alt(event: KeyPressEvent) -> None:
        """Show help overlay (alternative key)."""
        event.app.exit(result="help")

    @kb.add(",")
    def show_settings(event: KeyPressEvent) -> None:
        """Show settings dialog."""
        event.app.exit(result="settings")

    # Note: Full text input for search requires a modal dialog
    # For now, search mode is toggled with '/' and can be cleared with Esc
    # To actually enter search text, the app would need to show a prompt dialog

    return kb
