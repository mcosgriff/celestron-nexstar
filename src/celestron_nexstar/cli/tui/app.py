"""
TUI Application

Main application class for the full-screen terminal user interface.
"""

from __future__ import annotations

import asyncio

from prompt_toolkit import Application, PromptSession
from prompt_toolkit.layout.containers import FloatContainer
from prompt_toolkit.layout.layout import Layout
from rich.console import Console

from .bindings import create_key_bindings
from .layout import create_layout


console = Console()


def _change_telescope_interactive() -> None:
    """Interactive telescope selection."""
    try:
        from ...api.optics import (
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
        session: PromptSession[str] = PromptSession()
        choice = session.prompt("> ").strip()

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
            session.prompt("")
        else:
            console.print("[red]Invalid selection[/red]")
            console.print("[dim]Press Enter to return...[/dim]")
            session.prompt("")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


def _change_eyepiece_interactive() -> None:
    """Interactive eyepiece selection."""
    try:
        from ...api.optics import (
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
        session: PromptSession[str] = PromptSession()
        choice = session.prompt("> ").strip()

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
            session.prompt("")
        else:
            console.print("[red]Invalid selection[/red]")
            console.print("[dim]Press Enter to return...[/dim]")
            session.prompt("")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


def _goto_selected_object() -> None:
    """Goto selected object with telescope."""
    try:
        from .state import get_state

        state = get_state()
        selected = state.get_selected_object()

        if not selected:
            console.print("[yellow]No object selected[/yellow]")
            return

        obj, vis_info = selected

        # Check telescope connection
        from ..utils.state import get_telescope

        telescope = get_telescope()
        session: PromptSession[str] = PromptSession()
        if not telescope or not telescope.protocol or not telescope.protocol.is_open():
            console.print("[yellow]Telescope not connected[/yellow]")
            console.print("[dim]Press 'c' to connect[/dim]")
            session.prompt("Press Enter to continue...")
            return

        # Check if object is above horizon
        if vis_info.altitude_deg is None or vis_info.altitude_deg < 0:
            console.print(f"[yellow]Warning: {obj.name} is below the horizon[/yellow]")
            confirm = session.prompt("Slew anyway? (y/N): ").strip().lower()
            if confirm != "y":
                return

        # Perform goto
        display_name = obj.common_name or obj.name
        console.print(f"\n[bold]Slewing to {display_name}[/bold]")
        console.print(f"[dim]RA: {obj.ra_hours:.4f}h, Dec: {obj.dec_degrees:+.4f}°[/dim]\n")

        success = telescope.goto_ra_dec(obj.ra_hours, obj.dec_degrees)
        if success:
            console.print("[green]✓[/green] Slew initiated")
            console.print("[dim]Press Enter to return...[/dim]")
            session.prompt("")
        else:
            console.print("[red]✗[/red] Slew failed")
            console.print("[dim]Press Enter to return...[/dim]")
            session.prompt("")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        error_session: PromptSession[str] = PromptSession()
        error_session.prompt("Press Enter to continue...")


def _connect_telescope_interactive() -> None:
    """Interactive telescope connection."""
    try:
        from ..utils.state import get_telescope

        telescope = get_telescope()
        session: PromptSession[str] = PromptSession()
        if telescope and telescope.protocol and telescope.protocol.is_open():
            console.print("\n[bold]Telescope is already connected[/bold]\n")
            disconnect = session.prompt("Disconnect? (y/N): ").strip().lower()
            if disconnect == "y":
                from ..utils.state import clear_telescope

                telescope.disconnect()
                clear_telescope()
                console.print("[green]✓[/green] Disconnected")
            console.print("[dim]Press Enter to return...[/dim]")
            session.prompt("")
            return

        # Prompt for port
        console.print("\n[bold]Connect Telescope[/bold]\n")
        console.print("[dim]Enter serial port (e.g., /dev/ttyUSB0, COM3) or 'cancel':[/dim]")
        port = session.prompt("Port: ").strip()

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

        from ..utils.state import set_telescope

        set_telescope(telescope)

        console.print("[green]✓[/green] Connected")
        console.print("[dim]Press Enter to return...[/dim]")
        session.prompt("")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        error_session: PromptSession[str] = PromptSession()
        error_session.prompt("Press Enter to continue...")


def _park_telescope_interactive() -> None:
    """Interactive telescope parking."""
    try:
        from ..utils.state import get_telescope

        telescope = get_telescope()
        session: PromptSession[str] = PromptSession()
        if not telescope or not telescope.protocol or not telescope.protocol.is_open():
            console.print("[yellow]Telescope not connected[/yellow]")
            session.prompt("Press Enter to continue...")
            return

        console.print("\n[bold]Park Telescope[/bold]\n")
        console.print("[yellow]Warning: This will move the telescope to park position[/yellow]")
        confirm = session.prompt("Park telescope? (y/N): ").strip().lower()

        if confirm != "y":
            return

        # Park (typically Alt=0, Az=180 or similar - check telescope API)
        console.print("\n[dim]Parking telescope...[/dim]")
        # Note: Actual park command depends on telescope model
        # For now, just move to a safe position
        success = telescope.goto_alt_az(180.0, 0.0)  # South, horizon
        if success:
            console.print("[green]✓[/green] Telescope parked")
        else:
            console.print("[red]✗[/red] Park failed")

        console.print("[dim]Press Enter to return...[/dim]")
        session.prompt("")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        error_session: PromptSession[str] = PromptSession()
        error_session.prompt("Press Enter to continue...")


def _change_tracking_mode_interactive() -> None:
    """Interactive tracking mode selection."""
    try:
        from ..utils.state import get_telescope

        telescope = get_telescope()
        session: PromptSession[str] = PromptSession()
        if not telescope or not telescope.protocol or not telescope.protocol.is_open():
            console.print("[yellow]Telescope not connected[/yellow]")
            session.prompt("Press Enter to continue...")
            return

        from ...api.types import TrackingMode

        console.print("\n[bold]Tracking Mode[/bold]\n")
        console.print("Available modes:")
        console.print("  1. Alt-Az (Alt-Azimuth)")
        console.print("  2. EQ North (Equatorial, Northern Hemisphere)")
        console.print("  3. EQ South (Equatorial, Southern Hemisphere)")
        console.print("  4. Off (No tracking)\n")

        choice = session.prompt("Select mode (1-4) or 'cancel': ").strip()

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
        session.prompt("")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        error_session: PromptSession[str] = PromptSession()
        error_session.prompt("Press Enter to continue...")


def _show_settings_dialog() -> None:
    """Show settings/configuration dialog."""
    try:
        console.print("\n[bold]Settings[/bold]\n")
        console.print("─" * 40 + "\n")

        # Location settings
        from ...api.observer import get_observer_location

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
        from ..utils.state import get_telescope

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

        session: PromptSession[str] = PromptSession()
        session.prompt("Press Enter to return...")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        error_session: PromptSession[str] = PromptSession()
        error_session.prompt("Press Enter to continue...")


def _show_location_input_dialog() -> str | None:
    """Show btop-style input dialog for location entry.

    Note: Due to prompt_toolkit limitations, this temporarily pauses the TUI.
    For better modal support, consider migrating to Textual framework.
    """
    from prompt_toolkit import PromptSession
    from prompt_toolkit.formatted_text import HTML

    session: PromptSession[str] = PromptSession()

    # Show styled prompt with btop-like appearance
    try:
        result = session.prompt(
            HTML(
                '<style fg="#ff6600">[Location]</style> Enter location to geocode:\n'
                'Examples: "New York, NY", "90210", "London, UK"\n'
                '<style fg="#ff6600">></style> '
            ),
            default="",
        )
        return result.strip() if result else None
    except KeyboardInterrupt:
        return None


def _show_location_confirm_dialog(location_name: str, lat: float, lon: float) -> bool:
    """Show confirmation dialog for location update.

    Note: Due to prompt_toolkit limitations, this temporarily pauses the TUI.
    """
    from prompt_toolkit import PromptSession
    from prompt_toolkit.formatted_text import HTML

    # Format coordinates
    lat_dir = "N" if lat >= 0 else "S"
    lon_dir = "E" if lon >= 0 else "W"

    session: PromptSession[str] = PromptSession()
    try:
        result = session.prompt(
            HTML(
                f'<style fg="#ff6600">[Confirm Location]</style>\n'
                f'Location: <style fg="cyan">{location_name}</style>\n'
                f"Coordinates: {abs(lat):.4f}° {lat_dir}, {abs(lon):.4f}° {lon_dir}\n"
                f"Update location? (y/n): "
            ),
            default="n",
        )
        return result.strip().lower() in ("y", "yes")
    except KeyboardInterrupt:
        return False


def _update_location_interactive() -> None:
    """Interactive location update with geocoding using btop-style dialogs."""
    try:
        from ...api.observer import geocode_location, set_observer_location

        # Step 1: Get location input
        query = _show_location_input_dialog()
        if not query:
            return

        # Step 2: Geocode
        try:
            new_location = asyncio.run(geocode_location(query))
        except ValueError as e:
            # Show error dialog
            _show_error_dialog(f"Geocoding failed: {e}")
            return

        # Step 3: Confirm update
        confirmed = _show_location_confirm_dialog(
            new_location.name or "Unknown",
            new_location.latitude,
            new_location.longitude,
        )

        if confirmed:
            set_observer_location(new_location, save=True)
            _show_success_dialog("Location updated successfully!")
        else:
            _show_info_dialog("Location update cancelled")

    except Exception as e:
        _show_error_dialog(f"Error: {e}")


def _show_error_dialog(message: str) -> None:
    """Show error dialog."""
    from prompt_toolkit import PromptSession
    from prompt_toolkit.formatted_text import HTML

    session: PromptSession[str] = PromptSession()
    session.prompt(
        HTML(f'<style fg="#ff0000">✗ Error:</style> {message}\n\nPress Enter to continue...'),
    )


def _show_success_dialog(message: str) -> None:
    """Show success dialog."""
    from prompt_toolkit import PromptSession
    from prompt_toolkit.formatted_text import HTML

    session: PromptSession[str] = PromptSession()
    session.prompt(
        HTML(f'<style fg="#00ff00">✓ Success:</style> {message}\n\nPress Enter to continue...'),
    )


def _show_info_dialog(message: str) -> None:
    """Show info dialog."""
    from prompt_toolkit import PromptSession

    session: PromptSession[str] = PromptSession()
    session.prompt(f"{message}\n\nPress Enter to continue...")


def _show_help_overlay() -> None:
    """Show help overlay with keyboard shortcuts."""
    try:
        console.print("\n[bold]Keyboard Shortcuts[/bold]\n")
        console.print("─" * 50 + "\n")

        shortcuts = [
            (
                "Navigation",
                [
                    ("1", "Focus dataset pane"),
                    ("2", "Focus conditions pane"),
                    ("3", "Focus visible objects pane"),
                    ("↑/↓", "Move selection up/down"),
                    ("Enter", "Toggle detail view"),
                ],
            ),
            (
                "Actions",
                [
                    ("g", "Goto selected object"),
                    ("c", "Connect/disconnect telescope"),
                    ("p", "Park telescope"),
                    ("m", "Change tracking mode"),
                ],
            ),
            (
                "Configuration",
                [
                    ("t", "Change telescope"),
                    ("e", "Change eyepiece"),
                    ("u", "Toggle UTC/Local time"),
                ],
            ),
            (
                "Search & Filter",
                [
                    ("/", "Search objects"),
                    ("f", "Filter by type"),
                    ("s", "Cycle sort options"),
                    ("r", "Toggle sort direction"),
                    ("Esc", "Close search/filter"),
                ],
            ),
            (
                "Other",
                [
                    ("?", "Show this help"),
                    ("q", "Quit application"),
                ],
            ),
        ]

        for category, items in shortcuts:
            console.print(f"[bold cyan]{category}:[/bold cyan]")
            for key, desc in items:
                console.print(f"  [yellow]{key:10s}[/yellow] {desc}")
            console.print("")

        console.print("[dim]Press Enter to return...[/dim]")
        session: PromptSession[str] = PromptSession()
        session.prompt("")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        error_session: PromptSession[str] = PromptSession()
        error_session.prompt("Press Enter to continue...")


# Global reference to current TUI application instance for dialog support
_current_tui_app: TUIApplication | None = None


class TUIApplication:
    """Full-screen TUI application for telescope control and observing."""

    def __init__(self) -> None:
        """Initialize the TUI application."""
        global _current_tui_app
        _current_tui_app = self
        self._float_container: FloatContainer | None = None
        self._initialize_app()

    def _initialize_app(self) -> None:
        """Initialize or reinitialize the application."""
        # Create layout once and reuse it
        # This ensures the layout structure doesn't get recreated on refresh
        root_container = create_layout()
        # Store reference to FloatContainer for dynamic float management
        if isinstance(root_container, FloatContainer):
            self._float_container = root_container
        layout = Layout(root_container)

        # Create key bindings
        key_bindings = create_key_bindings()

        # Create application
        # The layout is created once and reused, so pane widths should remain stable
        self.app: Application[None] = Application(
            layout=layout,
            key_bindings=key_bindings,
            full_screen=True,
            refresh_interval=2.0,  # Refresh every 2 seconds
            mouse_support=False,  # Disable mouse for now
        )

    def run(self) -> None:
        """Run the TUI application."""
        from .state import get_state

        while True:
            result = self.app.run()
            if result == "change_telescope":
                _change_telescope_interactive()
                # Recreate app to refresh
                self._initialize_app()
            elif result == "change_eyepiece":
                _change_eyepiece_interactive()
                # Recreate app to refresh
                self._initialize_app()
            elif result == "search_mode":
                # Handle search input
                state = get_state()
                if state.search_mode:
                    # Show prompt for search text
                    from prompt_toolkit import PromptSession

                    session: PromptSession[str] = PromptSession()
                    try:
                        search_text = session.prompt("Search: ", default=state.search_query)
                        state.search_query = search_text
                        state.search_mode = False
                    except KeyboardInterrupt:
                        state.search_query = ""
                        state.search_mode = False
                    # Recreate app to refresh
                    self._initialize_app()
            elif result == "goto_object":
                _goto_selected_object()
                # Recreate app to refresh
                self._initialize_app()
            elif result == "connect_telescope":
                _connect_telescope_interactive()
                # Recreate app to refresh
                self._initialize_app()
            elif result == "park_telescope":
                _park_telescope_interactive()
                # Recreate app to refresh
                self._initialize_app()
            elif result == "tracking_mode":
                _change_tracking_mode_interactive()
                # Recreate app to refresh
                self._initialize_app()
            elif result == "settings":
                _show_settings_dialog()
                # Recreate app to refresh
                self._initialize_app()
            elif result == "help":
                _show_help_overlay()
                # Recreate app to refresh
                self._initialize_app()
            elif result == "update_location":
                _update_location_interactive()
                # Recreate app to refresh
                self._initialize_app()
            else:
                break
