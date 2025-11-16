"""
TUI Application

Main application class for the full-screen terminal user interface using Textual.
"""

from __future__ import annotations

from typing import ClassVar

from rich.console import Console
from textual.app import App, ComposeResult  # type: ignore[import-not-found]
from textual.binding import Binding  # type: ignore[import-not-found]
from textual.containers import Container, Horizontal  # type: ignore[import-not-found]
from textual.screen import ModalScreen  # type: ignore[import-not-found]
from textual.widgets import Button, Input, Static  # type: ignore[import-not-found]

from celestron_nexstar.cli.tui.layout import create_layout
from celestron_nexstar.cli.tui.state import get_state


console = Console()


class LocationInputScreen(ModalScreen[str | None]):
    """Modal screen for location input."""

    CSS = """
    LocationInputScreen {
        align: center middle;
    }

    .dialog {
        width: 60;
        height: auto;
        background: $surface;
        border: solid $primary;
        padding: 1;
    }

    .title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    #location_input {
        margin: 1 0;
    }
    """

    def compose(self) -> ComposeResult:
        """Create the location input dialog."""
        with Container(classes="dialog"):
            yield Static("[Location] Enter location to geocode:", classes="title")
            yield Static('Examples: "New York, NY", "90210", "London, UK"')
            yield Input(placeholder="Enter location...", id="location_input")
            with Horizontal():
                yield Button("OK", variant="primary", id="ok")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        """Focus the input when mounted."""
        self.query_one("#location_input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "ok":
            location = self.query_one("#location_input", Input).value
            self.dismiss(location.strip() if location else None)
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in input."""
        location = event.value.strip()
        self.dismiss(location if location else None)


class LocationConfirmScreen(ModalScreen[bool]):
    """Modal screen for location confirmation."""

    CSS = """
    LocationConfirmScreen {
        align: center middle;
    }

    .dialog {
        width: 60;
        height: auto;
        background: $surface;
        border: solid $primary;
        padding: 1;
    }

    .title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    """

    def __init__(self, location_name: str, lat: float, lon: float) -> None:
        """Initialize with location data."""
        super().__init__()
        self.location_name = location_name
        self.lat = lat
        self.lon = lon

    def compose(self) -> ComposeResult:
        """Create the confirmation dialog."""
        lat_dir = "N" if self.lat >= 0 else "S"
        lon_dir = "E" if self.lon >= 0 else "W"

        with Container(classes="dialog"):
            yield Static("[Confirm Location]", classes="title")
            yield Static(f"Location: [cyan]{self.location_name}[/cyan]")
            yield Static(f"Coordinates: {abs(self.lat):.4f}° {lat_dir}, {abs(self.lon):.4f}° {lon_dir}")
            yield Static("Update location?")
            with Horizontal():
                yield Button("Yes", variant="primary", id="yes")
                yield Button("No", id="no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        self.dismiss(event.button.id == "yes")


class MessageScreen(ModalScreen[None]):
    """Modal screen for displaying messages."""

    CSS = """
    MessageScreen {
        align: center middle;
    }

    .dialog {
        width: 60;
        height: auto;
        background: $surface;
        border: solid $primary;
        padding: 1;
    }

    .title {
        text-style: bold;
        margin-bottom: 1;
    }

    .error .title {
        color: $error;
    }

    .success .title {
        color: $success;
    }
    """

    def __init__(self, message: str, message_type: str = "info") -> None:
        """Initialize with message and type."""
        super().__init__()
        self.message = message
        self.message_type = message_type

    def compose(self) -> ComposeResult:
        """Create the message dialog."""
        title_map = {
            "error": "✗ Error:",
            "success": "✓ Success:",
            "info": "Info:",
        }
        title = title_map.get(self.message_type, "Info:")

        with Container(classes=f"dialog {self.message_type}"):
            yield Static(title, classes="title")
            yield Static(self.message)
            yield Button("OK", variant="primary", id="ok")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        self.dismiss(None)


class SearchInputScreen(ModalScreen[str | None]):
    """Modal screen for search input."""

    CSS = """
    SearchInputScreen {
        align: center middle;
    }

    .dialog {
        width: 60;
        height: auto;
        background: $surface;
        border: solid $primary;
        padding: 1;
    }

    .title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    """

    def __init__(self, current_query: str = "") -> None:
        """Initialize with current search query."""
        super().__init__()
        self.current_query = current_query

    def compose(self) -> ComposeResult:
        """Create the search input dialog."""
        with Container(classes="dialog"):
            yield Static("Search Objects", classes="title")
            yield Input(
                placeholder="Enter search query...",
                id="search_input",
                value=self.current_query,
            )
            with Horizontal():
                yield Button("Search", variant="primary", id="search")
                yield Button("Clear", id="clear")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        """Focus the input when mounted."""
        self.query_one("#search_input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "search":
            query = self.query_one("#search_input", Input).value
            self.dismiss(query.strip() if query else "")
        elif event.button.id == "clear":
            self.dismiss("")
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in input."""
        query = event.value.strip()
        self.dismiss(query if query else "")


class TUIApplication(App):
    """Full-screen TUI application for telescope control and observing using Textual."""

    CSS = """
    Screen {
        background: #000000;
    }

    #header {
        background: #333333;
        height: 1;
        border-bottom: solid #666666;
    }

    #main-content {
        height: 1fr;
    }

    #status-bar {
        background: #333333;
        height: 1;
        border-top: solid #666666;
    }

    .pane {
        background: #1e1e1e;
        border: solid #333333;
        padding: 1;
    }

    .pane-focused {
        border: solid $primary;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+q", "quit", "Quit", show=False),
        Binding("r", "refresh", "Refresh"),
        Binding("1", "focus_dataset", "Focus Dataset"),
        Binding("2", "focus_conditions", "Focus Conditions"),
        Binding("3", "focus_visible", "Focus Visible"),
        Binding("t", "change_telescope", "Change Telescope"),
        Binding("e", "change_eyepiece", "Change Eyepiece"),
        Binding("up", "move_up", "Move Up", show=False),
        Binding("down", "move_down", "Move Down", show=False),
        Binding("enter", "show_detail", "Show Detail", show=False),
        Binding("u", "toggle_time_mode", "Toggle UTC/Local"),
        Binding("s", "cycle_sort", "Cycle Sort"),
        Binding("f", "filter_menu", "Filter"),
        Binding("/", "search_mode", "Search"),
        Binding("escape", "close_search", "Close Search", show=False),
        Binding("c", "connect_telescope", "Connect"),
        Binding("g", "goto_object", "Goto"),
        Binding("p", "park_telescope", "Park"),
        Binding("m", "tracking_mode", "Tracking Mode"),
        Binding("?", "show_help", "Help"),
        Binding("h", "show_help", "Help", show=False),
        Binding("ctrl+o", "show_settings", "Settings", show=False),
        Binding("l", "update_location", "Location"),
    ]

    def __init__(self) -> None:
        """Initialize the TUI application."""
        super().__init__()

    def compose(self) -> ComposeResult:
        """Create the application layout."""
        yield from create_layout()

    def on_mount(self) -> None:
        """Initialize the application."""
        get_state().focused_pane = "visible"  # Default focus
        self.set_interval(2.0, self.refresh_all)  # Auto-refresh every 2 seconds

    def action_quit(self) -> None:
        """Quit the application."""
        self.exit()

    def action_refresh(self) -> None:
        """Force refresh all panes."""
        self.refresh_all()

    def refresh_all(self) -> None:
        """Refresh all panes."""
        # Trigger refresh by updating state
        get_state()
        # Force a refresh by calling refresh on all panes
        for widget in self.query(".pane"):
            widget.refresh()

    def action_focus_dataset(self) -> None:
        """Focus dataset pane."""
        state = get_state()
        state.focused_pane = "dataset"
        self.refresh_all()

    def action_focus_conditions(self) -> None:
        """Focus conditions pane."""
        state = get_state()
        state.focused_pane = "conditions"
        self.refresh_all()

    def action_focus_visible(self) -> None:
        """Focus visible objects pane."""
        state = get_state()
        state.focused_pane = "visible"
        self.refresh_all()

    def action_change_telescope(self) -> None:
        """Change telescope model."""
        self._change_telescope_interactive()

    def action_change_eyepiece(self) -> None:
        """Change eyepiece."""
        self._change_eyepiece_interactive()

    def action_move_up(self) -> None:
        """Move selection up in visible objects pane."""
        state = get_state()
        if state.focused_pane == "visible":
            state.move_selection_up()
            self.refresh_all()

    def action_move_down(self) -> None:
        """Move selection down in visible objects pane."""
        state = get_state()
        if state.focused_pane == "visible":
            state.move_selection_down()
            self.refresh_all()

    def action_show_detail(self) -> None:
        """Toggle detail view for selected object."""
        state = get_state()
        if state.focused_pane == "visible" and state.get_selected_object():
            state.toggle_detail()
            self.refresh_all()

    def action_toggle_time_mode(self) -> None:
        """Toggle between local and UTC time display."""
        state = get_state()
        state.toggle_time_mode()
        self.refresh_all()

    def action_cycle_sort(self) -> None:
        """Cycle through sort options."""
        state = get_state()
        if state.focused_pane == "visible":
            state.cycle_sort_by()
            self.refresh_all()
        else:
            # Start/stop session
            if state.session_start_time is None:
                from datetime import datetime

                state.session_start_time = datetime.now()
            else:
                state.session_start_time = None
            self.refresh_all()

    def action_filter_menu(self) -> None:
        """Toggle filter menu or cycle type filter."""
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
            self.refresh_all()

    async def action_search_mode(self) -> None:
        """Enter search mode."""
        state = get_state()
        if state.focused_pane == "visible":
            result = await self.push_screen(SearchInputScreen(state.search_query))
            if result is not None:
                state.search_query = result
                state.search_mode = False
                self.refresh_all()

    def action_close_search(self) -> None:
        """Close search mode or filter menu."""
        state = get_state()
        if state.search_mode:
            state.search_mode = False
            state.search_query = ""
            self.refresh_all()
        elif state.filter_menu_active:
            state.filter_menu_active = False
            state.filter_type = None
            self.refresh_all()
        elif state.show_detail:
            state.show_detail = False
            self.refresh_all()

    def action_connect_telescope(self) -> None:
        """Connect/disconnect telescope."""
        self._connect_telescope_interactive()

    def action_goto_object(self) -> None:
        """Goto selected object."""
        state = get_state()
        if state.focused_pane == "visible" and state.get_selected_object():
            self._goto_selected_object()

    def action_park_telescope(self) -> None:
        """Park telescope."""
        self._park_telescope_interactive()

    def action_tracking_mode(self) -> None:
        """Change tracking mode."""
        self._change_tracking_mode_interactive()

    async def action_show_help(self) -> None:
        """Show help overlay."""
        await self._show_help_overlay()

    def action_show_settings(self) -> None:
        """Show settings/configuration dialog."""
        self._show_settings_dialog()

    async def action_update_location(self) -> None:
        """Update observer location (geocode address)."""
        state = get_state()
        if state.focused_pane == "conditions":
            await self._update_location_interactive()

    def _change_telescope_interactive(self) -> None:
        """Interactive telescope selection."""
        try:
            from celestron_nexstar.api.observation.optics import (
                TelescopeModel,
                get_current_configuration,
                get_telescope_specs,
                set_current_configuration,
            )

            current_config = get_current_configuration()
            console.print(f"\n[bold]Current Telescope:[/bold] {current_config.telescope.display_name}\n")

            # List available telescopes
            console.print("[bold]Available Telescopes:[/bold]")
            telescope_models = list(TelescopeModel)
            for i, model in enumerate(telescope_models, 1):
                specs = get_telescope_specs(model)
                marker = "←" if model == current_config.telescope.model else " "
                console.print(
                    f"  {marker} {i}. {specs.display_name} ({specs.aperture_mm:.0f}mm, f/{specs.focal_ratio:.1f})"
                )

            console.print(f"\n[dim]Enter telescope number (1-{len(telescope_models)}) or name, or 'cancel':[/dim]")
            choice = input("> ").strip()

            if choice.lower() in ("cancel", "c", "q"):
                return

            # Parse choice
            selected_model = None
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(telescope_models):
                    selected_model = telescope_models[idx]
            else:
                # Try to match by name
                choice_lower = choice.lower()
                for model in telescope_models:
                    if choice_lower in model.display_name.lower() or choice_lower in model.value.lower():
                        selected_model = model
                        break

            if selected_model:
                new_telescope = get_telescope_specs(selected_model)
                new_config = type(current_config)(telescope=new_telescope, eyepiece=current_config.eyepiece)
                set_current_configuration(new_config)
                console.print(f"[green]✓[/green] Telescope changed to {new_telescope.display_name}")
                console.print("[dim]Press Enter to return to dashboard...[/dim]")
                input("")
                self.refresh_all()
            else:
                console.print("[red]Invalid selection[/red]")
                console.print("[dim]Press Enter to return...[/dim]")
                input("")

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

    def _change_eyepiece_interactive(self) -> None:
        """Interactive eyepiece selection."""
        try:
            from celestron_nexstar.api.observation.optics import (
                COMMON_EYEPIECES,
                get_current_configuration,
                set_current_configuration,
            )

            current_config = get_current_configuration()
            current_ep_name = current_config.eyepiece.name or f"{current_config.eyepiece.focal_length_mm:.0f}mm"
            console.print(f"\n[bold]Current Eyepiece:[/bold] {current_ep_name}\n")

            # List available eyepieces, sorted by focal length
            console.print("[bold]Available Eyepieces:[/bold]")
            eyepiece_items = sorted(COMMON_EYEPIECES.items(), key=lambda x: x[1].focal_length_mm, reverse=True)

            # Group by type for better organization
            plossl_items = [(k, v) for k, v in eyepiece_items if "plossl" in k]
            ultrawide_items = [(k, v) for k, v in eyepiece_items if "ultrawide" in k]
            wide_items = [(k, v) for k, v in eyepiece_items if "wide" in k and "ultrawide" not in k]

            item_num = 1
            if plossl_items:
                console.print("\n[dim]Plössl Eyepieces (50° FOV):[/dim]")
                for _key, eyepiece in plossl_items:
                    ep_name = eyepiece.name or f"{eyepiece.focal_length_mm:.0f}mm"
                    marker = "←" if eyepiece.focal_length_mm == current_config.eyepiece.focal_length_mm else " "
                    console.print(f"  {marker} {item_num:2d}. {ep_name:30s} ({eyepiece.focal_length_mm:.0f}mm)")
                    item_num += 1

            if ultrawide_items:
                console.print("\n[dim]Ultra-Wide Eyepieces (82° FOV):[/dim]")
                for _key, eyepiece in ultrawide_items:
                    ep_name = eyepiece.name or f"{eyepiece.focal_length_mm:.0f}mm"
                    marker = "←" if eyepiece.focal_length_mm == current_config.eyepiece.focal_length_mm else " "
                    console.print(f"  {marker} {item_num:2d}. {ep_name:30s} ({eyepiece.focal_length_mm:.0f}mm)")
                    item_num += 1

            if wide_items:
                console.print("\n[dim]Wide-Angle Eyepieces (68° FOV):[/dim]")
                for _key, eyepiece in wide_items:
                    ep_name = eyepiece.name or f"{eyepiece.focal_length_mm:.0f}mm"
                    marker = "←" if eyepiece.focal_length_mm == current_config.eyepiece.focal_length_mm else " "
                    console.print(f"  {marker} {item_num:2d}. {ep_name:30s} ({eyepiece.focal_length_mm:.0f}mm)")
                    item_num += 1

            total_items = len(eyepiece_items)

            console.print(f"\n[dim]Enter eyepiece number (1-{total_items}) or name/focal length, or 'cancel':[/dim]")
            choice = input("> ").strip()

            if choice.lower() in ("cancel", "c", "q"):
                return

            # Rebuild flat list for selection
            all_items = plossl_items + ultrawide_items + wide_items

            # Parse choice
            selected_eyepiece = None
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(all_items):
                    selected_eyepiece = all_items[idx][1]
            else:
                # Try to match by name or focal length
                choice_lower = choice.lower()
                for key, eyepiece in all_items:
                    ep_name = (eyepiece.name or "").lower()
                    if choice_lower in ep_name or choice_lower in key.lower():
                        selected_eyepiece = eyepiece
                        break
                    # Try matching focal length
                    try:
                        if float(choice) == eyepiece.focal_length_mm:
                            selected_eyepiece = eyepiece
                            break
                    except ValueError:
                        pass

            if selected_eyepiece:
                new_config = type(current_config)(telescope=current_config.telescope, eyepiece=selected_eyepiece)
                set_current_configuration(new_config)
                ep_name = selected_eyepiece.name or f"{selected_eyepiece.focal_length_mm:.0f}mm"
                console.print(f"[green]✓[/green] Eyepiece changed to {ep_name}")
                console.print("[dim]Press Enter to return to dashboard...[/dim]")
                input("")
                self.refresh_all()
            else:
                console.print("[red]Invalid selection[/red]")
                console.print("[dim]Press Enter to return...[/dim]")
                input("")

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

    def _goto_selected_object(self) -> None:
        """Goto selected object with telescope."""

        async def _do_goto() -> None:
            try:
                state = get_state()
                selected = state.get_selected_object()

                if not selected:
                    await self.push_screen(MessageScreen("No object selected", "error"))
                    return

                obj, vis_info = selected

                # Check telescope connection
                from celestron_nexstar.cli.utils.state import get_telescope

                telescope = get_telescope()
                if not telescope or not telescope.protocol or not telescope.protocol.is_open():
                    await self.push_screen(MessageScreen("Telescope not connected. Press 'c' to connect.", "error"))
                    return

                # Check if object is above horizon
                if vis_info.altitude_deg is None or vis_info.altitude_deg < 0:
                    # For now, just proceed - could add confirmation dialog later
                    pass

                # Perform goto
                display_name = obj.common_name or obj.name
                success = telescope.goto_ra_dec(obj.ra_hours, obj.dec_degrees)
                if success:
                    await self.push_screen(MessageScreen(f"Slew initiated to {display_name}", "success"))
                else:
                    await self.push_screen(MessageScreen("Slew failed", "error"))
                self.refresh_all()

            except Exception as e:
                await self.push_screen(MessageScreen(f"Error: {e}", "error"))

        self.run_worker(_do_goto())

    def _connect_telescope_interactive(self) -> None:
        """Interactive telescope connection."""
        try:
            from celestron_nexstar.cli.utils.state import get_telescope

            telescope = get_telescope()
            if telescope and telescope.protocol and telescope.protocol.is_open():
                console.print("\n[bold]Telescope is already connected[/bold]\n")
                disconnect = input("Disconnect? (y/N): ").strip().lower()
                if disconnect == "y":
                    from celestron_nexstar.cli.utils.state import clear_telescope

                    telescope.disconnect()
                    clear_telescope()
                    console.print("[green]✓[/green] Disconnected")
                self.refresh_all()
                return

            # Prompt for port
            console.print("\n[bold]Connect Telescope[/bold]\n")
            console.print("[dim]Enter serial port (e.g., /dev/ttyUSB0, COM3) or 'cancel':[/dim]")
            port = input("Port: ").strip()

            if port.lower() in ("cancel", "c", "q"):
                return

            if not port:
                console.print("[yellow]No port specified[/yellow]")
                return

            # Connect
            from celestron_nexstar import NexStarTelescope, TelescopeConfig

            console.print(f"\n[dim]Connecting to {port}...[/dim]")
            config = TelescopeConfig(port=port)
            telescope = NexStarTelescope(config)
            telescope.connect()

            from celestron_nexstar.cli.utils.state import set_telescope

            set_telescope(telescope)

            console.print("[green]✓[/green] Connected")
            console.print("[dim]Press Enter to return...[/dim]")
            input("")
            self.refresh_all()

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            input("Press Enter to continue...")

    def _park_telescope_interactive(self) -> None:
        """Interactive telescope parking."""

        async def _do_park() -> None:
            try:
                from celestron_nexstar.cli.utils.state import get_telescope

                telescope = get_telescope()
                if not telescope or not telescope.protocol or not telescope.protocol.is_open():
                    await self.push_screen(MessageScreen("Telescope not connected", "error"))
                    return

                console.print("\n[bold]Park Telescope[/bold]\n")
                console.print("[yellow]Warning: This will move the telescope to park position[/yellow]")
                confirm = input("Park telescope? (y/N): ").strip().lower()

                if confirm != "y":
                    return

                # Park (typically Alt=0, Az=180 or similar - check telescope API)
                console.print("\n[dim]Parking telescope...[/dim]")
                # Note: Actual park command depends on telescope model
                # For now, just move to a safe position
                success = telescope.goto_alt_az(180.0, 0.0)  # South, horizon
                if success:
                    await self.push_screen(MessageScreen("Telescope parked", "success"))
                else:
                    await self.push_screen(MessageScreen("Park failed", "error"))
                self.refresh_all()

            except Exception as e:
                await self.push_screen(MessageScreen(f"Error: {e}", "error"))

        self.run_worker(_do_park())

    def _change_tracking_mode_interactive(self) -> None:
        """Interactive tracking mode selection."""

        async def _do_tracking() -> None:
            try:
                from celestron_nexstar.cli.utils.state import get_telescope

                telescope = get_telescope()
                if not telescope or not telescope.protocol or not telescope.protocol.is_open():
                    await self.push_screen(MessageScreen("Telescope not connected", "error"))
                    return

                from celestron_nexstar.api.core.types import TrackingMode

                console.print("\n[bold]Tracking Mode[/bold]\n")
                console.print("Available modes:")
                console.print("  1. Alt-Az (Alt-Azimuth)")
                console.print("  2. EQ North (Equatorial, Northern Hemisphere)")
                console.print("  3. EQ South (Equatorial, Southern Hemisphere)")
                console.print("  4. Off (No tracking)\n")

                choice = input("Select mode (1-4) or 'cancel': ").strip()

                if choice.lower() in ("cancel", "c", "q"):
                    return

                mode_map = {
                    "1": TrackingMode.ALT_AZ,
                    "2": TrackingMode.EQ_NORTH,
                    "3": TrackingMode.EQ_SOUTH,
                    "4": TrackingMode.OFF,
                }

                if choice not in mode_map:
                    console.print("[yellow]Invalid selection[/yellow]")
                    return

                mode = mode_map[choice]
                telescope.set_tracking_mode(mode)
                console.print(f"[green]✓[/green] Tracking mode set to {mode.value}")
                console.print("[dim]Press Enter to return...[/dim]")
                input("")
                self.refresh_all()

            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                input("Press Enter to continue...")

        self.run_worker(_do_tracking())

    def _show_settings_dialog(self) -> None:
        """Show settings/configuration dialog."""
        try:
            console.print("\n[bold]Settings[/bold]\n")
            console.print("─" * 40 + "\n")

            # Location settings
            from celestron_nexstar.api.location.observer import get_observer_location

            location = get_observer_location()
            console.print("[bold]Location:[/bold]")
            if location.name:
                console.print(f"  Name: {location.name}")
            console.print(f"  Latitude: {location.latitude:.4f}°")
            console.print(f"  Longitude: {location.longitude:.4f}°")
            console.print(f"  Elevation: {location.elevation:.0f}m\n")

            # Weather API status
            console.print("[bold]Weather API:[/bold]")
            console.print("  [green]✓[/green] Using Open-Meteo (free, no API key required)")
            console.print("")

            # Telescope connection status
            from celestron_nexstar.cli.utils.state import get_telescope

            telescope = get_telescope()
            console.print("[bold]Telescope:[/bold]")
            if telescope and telescope.protocol and telescope.protocol.is_open():
                console.print("  [green]✓[/green] Connected")
                try:
                    info = telescope.get_info()
                    console.print(f"  Model: {info.model}")
                    console.print(f"  Firmware: {info.firmware_major}.{info.firmware_minor}")
                except Exception:
                    pass
            else:
                console.print("  [yellow]✗[/yellow] Not connected")
            console.print("")

            input("Press Enter to return...")
            self.refresh_all()

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            input("Press Enter to continue...")

    async def _update_location_interactive(self) -> None:
        """Interactive location update with geocoding using Textual dialogs."""
        try:
            from celestron_nexstar.api.location.observer import geocode_location, set_observer_location

            # Step 1: Get location input
            query = await self.push_screen(LocationInputScreen())
            if not query:
                return

            # Step 2: Geocode
            try:
                new_location = await geocode_location(query)
            except ValueError as e:
                await self.push_screen(MessageScreen(f"Geocoding failed: {e}", "error"))
                return

            # Step 3: Confirm update
            confirmed = await self.push_screen(
                LocationConfirmScreen(
                    new_location.name or "Unknown",
                    new_location.latitude,
                    new_location.longitude,
                )
            )

            if confirmed:
                set_observer_location(new_location, save=True)
                await self.push_screen(MessageScreen("Location updated successfully!", "success"))
            else:
                await self.push_screen(MessageScreen("Location update cancelled", "info"))
            self.refresh_all()

        except Exception as e:
            await self.push_screen(MessageScreen(f"Error: {e}", "error"))

    async def _show_help_overlay(self) -> None:
        """Show help overlay with keyboard shortcuts."""
        try:
            help_text = """
[bold]Keyboard Shortcuts[/bold]

[bold cyan]Navigation:[/bold cyan]
  1                    Focus dataset pane
  2                    Focus conditions pane
  3                    Focus visible objects pane
  ↑/↓                  Move selection up/down
  Enter                Toggle detail view

[bold cyan]Actions:[/bold cyan]
  g                    Goto selected object
  c                    Connect/disconnect telescope
  p                    Park telescope
  m                    Change tracking mode

[bold cyan]Configuration:[/bold cyan]
  t                    Change telescope
  e                    Change eyepiece
  u                    Toggle UTC/Local time

[bold cyan]Search & Filter:[/bold cyan]
  /                    Search objects
  f                    Filter by type
  s                    Cycle sort options
  r                    Toggle sort direction
  Esc                  Close search/filter

[bold cyan]Other:[/bold cyan]
  ?                    Show this help
  q                    Quit application
"""
            await self.push_screen(MessageScreen(help_text, "info"))

        except Exception as e:
            await self.push_screen(MessageScreen(f"Error: {e}", "error"))
