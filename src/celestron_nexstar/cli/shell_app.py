"""
Textual-based Interactive Shell Application

Provides an interactive shell interface with autocomplete, status bar,
and command execution using Textual framework.
"""

from __future__ import annotations

import asyncio
import shlex
import sys
import threading
from datetime import datetime
from typing import Any, ClassVar

import typer
from rich.console import Console
from textual.app import App, ComposeResult  # type: ignore[import-not-found]
from textual.binding import Binding  # type: ignore[import-not-found]
from textual.containers import Container  # type: ignore[import-not-found]
from textual.widgets import Input, Static  # type: ignore[import-not-found]

from celestron_nexstar.cli.tutorial import TutorialSystem


console = Console()


class StatusBar(Static):
    """Status bar widget showing time, weather, GPS, and telescope position."""

    def __init__(self, status_cache: dict[str, Any], *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("markup", True)
        super().__init__(*args, **kwargs)
        self.status_cache = status_cache

    def compose(self) -> ComposeResult:
        """Create status bar content."""
        yield Static(id="status-content")

    def on_mount(self) -> None:
        """Start updating status bar."""
        self.set_interval(1.0, self.update_status)

    def update_status(self) -> None:
        """Update status bar content."""
        parts = []

        # Current time
        time_val = self.status_cache.get("time")
        time_str = time_val.strftime("%H:%M:%S") if time_val else datetime.now().strftime("%H:%M:%S")
        parts.append(f"[dim red]Time: {time_str}[/]")

        # Weather
        weather = self.status_cache.get("weather")
        if weather:
            if weather.temperature_c is not None:
                temp_str = f"{weather.temperature_c:.1f}°F"
                parts.append(f"[dim yellow]Temp: {temp_str}[/]")

            if weather.cloud_cover_percent is not None:
                cloud_str = f"{weather.cloud_cover_percent:.0f}%"
                parts.append(f"[dim yellow]Clouds: {cloud_str}[/]")

        # GPS coordinates
        location = self.status_cache.get("location")
        if location:
            gps_str = f"{location.latitude:.4f}, {location.longitude:.4f}"
            parts.append(f"[dim red]GPS: {gps_str}[/]")

        # Telescope status
        telescope_pos = self.status_cache.get("telescope_position")
        if telescope_pos:
            connected = telescope_pos.get("connected", False)
            aligned = telescope_pos.get("aligned", False)

            if not connected:
                parts.append("[red]Scope: Not Connected[/]")
            elif not aligned:
                parts.append("[yellow]Scope: Connected (Not Aligned)[/]")
            elif "ra_dec" in telescope_pos and "alt_az" in telescope_pos:
                ra_dec = telescope_pos["ra_dec"]
                alt_az = telescope_pos["alt_az"]
                pos_str = f"RA:{ra_dec.ra_hours:.2f}h Dec:{ra_dec.dec_degrees:+.2f}° Alt:{alt_az.altitude:.1f}° Az:{alt_az.azimuth:.1f}°"
                parts.append(f"[green]Scope: {pos_str}[/]")
            else:
                parts.append("[yellow]Scope: Connected[/]")

        content = " | ".join(parts)
        self.query_one("#status-content", Static).update(content)


class ShellApp(App):
    """Interactive shell application using Textual."""

    CSS = """
    Screen {
        background: #000000;
    }

    #status-bar {
        background: #000000;
        border-top: solid #333333;
        height: 1;
    }

    #status-content {
        background: #000000;
        color: #cc6666;
    }

    #input-container {
        background: #000000;
    }

    Input {
        background: #000000;
        color: #cccccc;
        border: solid #333333;
    }

    #output {
        background: #000000;
        color: #cccccc;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("ctrl+c", "cancel", "Cancel", show=False),
        Binding("ctrl+d", "exit", "Exit", show=False),
    ]

    def __init__(self, typer_app: typer.Typer, status_cache: dict[str, Any]) -> None:
        super().__init__()
        self.typer_app = typer_app
        self.status_cache = status_cache
        self.tutorial_system = TutorialSystem(console)

    def compose(self) -> ComposeResult:
        """Create the application layout."""
        yield Container(
            Static(id="output", markup=True),
            id="output-container",
        )
        yield Container(
            Input(placeholder="nexstar> ", id="command-input"),
            id="input-container",
        )
        yield StatusBar(self.status_cache, id="status-bar")

    def on_mount(self) -> None:
        """Initialize the application."""
        self.query_one("#command-input", Input).focus()
        self.output_widget = self.query_one("#output", Static)
        self.input_widget = self.query_one("#command-input", Input)

        # Welcome message
        welcome = """[bold green]╔═══════════════════════════════════════════════════╗[/bold green]
[bold green]║[/bold green]   [bold cyan]NexStar Interactive Shell[/bold cyan]                   [bold green]║[/bold green]
[bold green]╚═══════════════════════════════════════════════════╝[/bold green]

[bold]Quick Start:[/bold]
  • Type [cyan]'tutorial'[/cyan] for an interactive guided tour
  • Type [cyan]'help'[/cyan] to see all available commands
  • Type [cyan]'exit'[/cyan] to quit

"""
        self.output_widget.update(welcome)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle command input."""
        command = event.value.strip()
        if not command:
            return

        # Clear input
        self.input_widget.value = ""

        # Handle special commands
        if command.lower() in ("exit", "quit"):
            self.exit()
            return

        if command.lower() == "clear":
            self.output_widget.update("")
            return

        if command.lower() == "help":
            self._show_help()
            return

        if command.lower().startswith("tutorial"):
            self._handle_tutorial(command)
            return

        # Execute command through typer
        self._execute_command(command)

    def _execute_command(self, command: str) -> None:
        """Execute a command through typer."""
        try:
            args = shlex.split(command)
        except ValueError as e:
            self._append_output(f"[red]Error parsing command: {e}[/red]")
            return

        if not args:
            return

        # Temporarily modify sys.argv
        old_argv = sys.argv
        try:
            sys.argv = ["nexstar", *args]
            self.typer_app(standalone_mode=False)
        except SystemExit as e:
            if e.code not in (0, None):
                self._append_output(f"[yellow]Command exited with code: {e.code}[/yellow]")
        except typer.Exit as e:
            if e.exit_code not in (0, None):
                self._append_output(f"[yellow]Command exited with code: {e.exit_code}[/yellow]")
        except typer.Abort:
            self._append_output("[yellow]Command aborted[/yellow]")
        except Exception as e:
            self._append_output(f"[red]Error: {e}[/red]")
        finally:
            sys.argv = old_argv

    def _append_output(self, text: str) -> None:
        """Append text to output area."""
        current = self.output_widget.renderable
        new_text = f"{current}\n{text}" if isinstance(current, str) else text
        self.output_widget.update(new_text)

    def _show_help(self) -> None:
        """Show help information."""
        help_text = """[bold]Available Commands:[/bold]

[bold]Telescope Control:[/bold]
  [cyan]connect[/cyan]        - Connect to telescope
  [cyan]disconnect[/cyan]     - Disconnect from telescope
  [cyan]position[/cyan]       - Get telescope position
  [cyan]goto[/cyan]           - GoTo commands
  [cyan]move[/cyan]           - Manual movement commands
  [cyan]align[/cyan]          - Alignment commands
  [cyan]track[/cyan]          - Tracking mode commands

[bold]Data & Catalogs:[/bold]
  [cyan]catalog[/cyan]        - Celestial object catalogs
  [cyan]data[/cyan]           - Data import and management
  [cyan]ephemeris[/cyan]      - Ephemeris file management

[bold]Observation:[/bold]
  [cyan]observation[/cyan]    - Observation planning
  [cyan]location[/cyan]       - Location management
  [cyan]weather[/cyan]        - Weather information

[bold]Shell Commands:[/bold]
  [cyan]help[/cyan]           - Show this help
  [cyan]clear[/cyan]          - Clear screen
  [cyan]tutorial[/cyan]       - Interactive tutorial
  [cyan]exit[/cyan] / [cyan]quit[/cyan] - Exit shell

[dim]Use '<command> --help' for detailed help on each command[/dim]
"""
        self._append_output(help_text)

    def _handle_tutorial(self, command: str) -> None:
        """Handle tutorial commands."""
        parts = command.split()
        if len(parts) > 1:
            if parts[1] == "all":
                self._append_output("[yellow]Running all tutorials...[/yellow]")
                # TODO: Implement tutorial system
            elif parts[1] == "demo":
                self._append_output("[yellow]Running demo tutorials...[/yellow]")
                # TODO: Implement tutorial system
            else:
                try:
                    lesson_num = int(parts[1])
                    self._append_output(f"[yellow]Running tutorial lesson {lesson_num}...[/yellow]")
                    # TODO: Implement tutorial system
                except ValueError:
                    self._append_output(f"[red]Invalid tutorial number: {parts[1]}[/red]")
        else:
            self._append_output("[yellow]Tutorial system - use 'tutorial <number>' or 'tutorial all'[/yellow]")

    def action_cancel(self) -> None:
        """Handle Ctrl+C."""
        self.input_widget.value = ""

    def action_exit(self) -> None:
        """Handle Ctrl+D or exit."""
        self.exit()


def create_status_cache() -> dict[str, Any]:
    """Create and start status cache updater."""
    status_cache: dict[str, Any] = {
        "time": None,
        "weather": None,
        "location": None,
        "telescope_position": None,
    }

    def update_status_cache() -> None:
        """Update status bar cache in background thread."""

        def _update() -> None:
            while True:
                try:
                    # Update time
                    status_cache["time"] = datetime.now()

                    # Update weather
                    try:
                        from celestron_nexstar.api.location.observer import get_observer_location
                        from celestron_nexstar.api.location.weather import fetch_weather

                        location = get_observer_location()
                        weather = asyncio.run(fetch_weather(location))
                        status_cache["weather"] = weather
                        status_cache["location"] = location
                    except Exception:
                        pass  # Keep old cache on error

                    # Update telescope position and status
                    try:
                        from celestron_nexstar.cli.utils.state import get_telescope

                        telescope = get_telescope()
                        if telescope and telescope.protocol and telescope.protocol.is_open():
                            try:
                                ra_dec = telescope.get_position_ra_dec()
                                alt_az = telescope.get_position_alt_az()
                                is_aligned = not (
                                    ra_dec.ra_hours == 0.0
                                    and ra_dec.dec_degrees == 0.0
                                    and alt_az.altitude == 0.0
                                    and alt_az.azimuth == 0.0
                                )
                                status_cache["telescope_position"] = {
                                    "ra_dec": ra_dec,
                                    "alt_az": alt_az,
                                    "connected": True,
                                    "aligned": is_aligned,
                                }
                            except Exception:
                                status_cache["telescope_position"] = {"connected": True, "aligned": False}
                        else:
                            status_cache["telescope_position"] = {"connected": False, "aligned": False}
                    except Exception:
                        status_cache["telescope_position"] = {"connected": False, "aligned": False}

                    # Sleep for 1 second before next update
                    import time

                    time.sleep(1.0)
                except Exception:
                    import time

                    time.sleep(1.0)

        # Start background thread
        thread = threading.Thread(target=_update, daemon=True)
        thread.start()

    # Start background status updates
    update_status_cache()
    return status_cache
