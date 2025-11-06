"""
Celestron NexStar CLI - Main Application

This is the main entry point for the Celestron NexStar command-line interface.
"""

import typer
from rich.console import Console

# Import and register subcommands
from .commands import align, catalog, connect, ephemeris, goto, location, move, optics, position, time, track


# Create main app
app = typer.Typer(
    name="nexstar",
    help="Celestron NexStar Telescope Control CLI",
    add_completion=True,
    rich_markup_mode="rich",
)

# Console for rich output
console = Console()

# Global state for CLI
state: dict[str, str | None | bool] = {
    "port": None,
    "profile": None,
    "verbose": False,
}


@app.callback()
def main(
    port: str | None = typer.Option(
        None,
        "--port",
        "-p",
        help="Serial port for telescope connection",
        envvar="NEXSTAR_PORT",
    ),
    profile: str | None = typer.Option(
        None,
        "--profile",
        help="Configuration profile to use",
        envvar="NEXSTAR_PROFILE",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose output",
    ),
) -> None:
    """
    Celestron NexStar Telescope Control CLI

    Control your Celestron NexStar telescope from the command line.

    [bold green]Examples:[/bold green]

        nexstar connect /dev/ttyUSB0
        nexstar position
        nexstar goto --ra 12.5 --dec 45.0

    [bold blue]Environment Variables:[/bold blue]

        NEXSTAR_PORT    - Default serial port
        NEXSTAR_PROFILE - Default configuration profile
    """
    state["port"] = port
    state["profile"] = profile
    state["verbose"] = verbose

    if verbose:
        console.print("[dim]Verbose mode enabled[/dim]")
        if port:
            console.print(f"[dim]Using port: {port}[/dim]")
        if profile:
            console.print(f"[dim]Using profile: {profile}[/dim]")


@app.command()
def version() -> None:
    """Show the CLI version."""
    from celestron_nexstar.cli import __version__

    console.print(f"[bold]Celestron NexStar CLI[/bold] version [cyan]{__version__}[/cyan]")


# Register command groups - Phase 2 (Core)
app.add_typer(connect.app, name="connect", help="Connection commands (deprecated - use subcommands)")
app.add_typer(position.app, name="position", help="Position query commands")
app.add_typer(goto.app, name="goto", help="Slew (goto) commands")
app.add_typer(move.app, name="move", help="Manual movement commands")
app.add_typer(track.app, name="track", help="Tracking control commands")
app.add_typer(align.app, name="align", help="Alignment commands")

# Register command groups - Phase 3 (Advanced)
app.add_typer(location.app, name="location", help="Observer location commands")
app.add_typer(time.app, name="time", help="Time and date commands")
app.add_typer(catalog.app, name="catalog", help="Celestial object catalogs")
app.add_typer(optics.app, name="optics", help="Telescope and eyepiece configuration")
app.add_typer(ephemeris.app, name="ephemeris", help="Ephemeris file management")


# Also add connect commands directly to main app for convenience
@app.command("conn")
def conn(
    port: str = typer.Argument(..., help="Serial port (e.g., /dev/ttyUSB0, COM3)"),
    baudrate: int = typer.Option(9600, help="Baud rate"),
    timeout: float = typer.Option(2.0, help="Connection timeout in seconds"),
) -> None:
    """Quick connect to telescope (shorthand for 'connect connect')."""
    connect.connect(port, baudrate, timeout)


@app.command("disc")
def disc() -> None:
    """Quick disconnect from telescope (shorthand for 'connect disconnect')."""
    connect.disconnect()


@app.command()
def shell() -> None:
    """
    Enter interactive shell mode with autocomplete and command history.

    In interactive mode, you can run commands without the 'nexstar' prefix.

    [bold green]Examples:[/bold green]

        nexstar> position get
        nexstar> goto radec --ra 5.5 --dec 22.5
        nexstar> catalog search "andromeda"
        nexstar> exit

    [bold blue]Features:[/bold blue]

        - Tab completion for commands and subcommands
        - Command history (use up/down arrows)
        - Background position tracking (starts after alignment)
        - Live position updates in status bar
        - Ctrl+C to cancel current input
        - Type 'exit' or 'quit' to leave shell
        - Type 'help' to see available commands
    """
    import shlex
    import sys
    import threading
    import time
    from datetime import datetime
    from typing import Any

    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import NestedCompleter
    from prompt_toolkit.formatted_text import HTML
    from prompt_toolkit.history import InMemoryHistory
    from prompt_toolkit.styles import Style

    # Background position tracking state
    class PositionTracker:
        """Background thread for tracking telescope position."""

        def __init__(self) -> None:
            self.enabled = False
            self.running = False
            self.thread: threading.Thread | None = None
            self.lock = threading.Lock()
            self.update_interval = 2.0  # seconds
            self.last_position: dict[str, Any] = {}
            self.last_update: datetime | None = None
            self.error_count = 0
            # Position history using circular buffer
            from collections import deque
            self.history: deque[dict[str, Any]] = deque(maxlen=1000)
            self.history_enabled = True
            # Slew speed tracking
            self.last_velocity: dict[str, float] = {}  # degrees/sec for alt, az; hours/sec for RA
            self.is_slewing = False
            # Collision detection
            self.alert_threshold = 5.0  # degrees/sec - unexpected movement threshold
            self.expected_slew = False  # Flag to indicate an expected slew is in progress
            self.last_alert: datetime | None = None  # Prevent alert spam
            # ASCII chart visualization
            self.show_chart = False  # Toggle for ASCII star chart in status bar

        def start(self) -> None:
            """Start background position tracking."""
            with self.lock:
                if self.running:
                    return

                self.enabled = True
                self.running = True
                self.error_count = 0
                self.thread = threading.Thread(target=self._track_loop, daemon=True)
                self.thread.start()

        def set_interval(self, seconds: float) -> bool:
            """Set the tracking update interval.

            Args:
                seconds: Update interval in seconds (0.5 to 30.0)

            Returns:
                True if interval was set, False if invalid
            """
            if not (0.5 <= seconds <= 30.0):
                return False

            with self.lock:
                self.update_interval = seconds
            return True

        def get_interval(self) -> float:
            """Get the current update interval."""
            with self.lock:
                return self.update_interval

        def get_history(self, last: int | None = None, since: datetime | None = None) -> list[dict[str, Any]]:
            """Get position history with optional filtering.

            Args:
                last: Return only the last N entries
                since: Return only entries since this timestamp

            Returns:
                List of position history entries
            """
            with self.lock:
                history_list = list(self.history)

            # Filter by timestamp if requested
            if since:
                history_list = [entry for entry in history_list if entry["timestamp"] >= since]

            # Limit to last N if requested
            if last:
                history_list = history_list[-last:]

            return history_list

        def clear_history(self) -> None:
            """Clear all position history."""
            with self.lock:
                self.history.clear()

        def get_history_stats(self) -> dict[str, Any]:
            """Get statistics about the position history.

            Returns:
                Dictionary with stats: count, duration, drift, etc.
            """
            with self.lock:
                history_list = list(self.history)

            if len(history_list) < 2:
                return {
                    "count": len(history_list),
                    "duration_seconds": 0,
                    "total_ra_drift_arcsec": 0,
                    "total_dec_drift_arcsec": 0,
                }

            first = history_list[0]
            last = history_list[-1]
            duration = (last["timestamp"] - first["timestamp"]).total_seconds()

            # Calculate drift in arcseconds
            ra_drift = abs(last["ra_hours"] - first["ra_hours"]) * 15 * 3600  # hours to arcsec
            dec_drift = abs(last["dec_degrees"] - first["dec_degrees"]) * 3600  # degrees to arcsec

            return {
                "count": len(history_list),
                "duration_seconds": duration,
                "first_timestamp": first["timestamp"],
                "last_timestamp": last["timestamp"],
                "total_ra_drift_arcsec": ra_drift,
                "total_dec_drift_arcsec": dec_drift,
            }

        def _calculate_velocity(self, prev_pos: dict[str, Any], curr_pos: dict[str, Any], time_delta: float) -> dict[str, float]:
            """Calculate velocity between two positions.

            Args:
                prev_pos: Previous position dict
                curr_pos: Current position dict
                time_delta: Time elapsed in seconds

            Returns:
                Dictionary with velocity components in degrees/sec
            """
            if time_delta <= 0:
                return {"ra": 0.0, "dec": 0.0, "alt": 0.0, "az": 0.0, "total": 0.0}

            # Calculate rate of change
            ra_rate = (curr_pos["ra_hours"] - prev_pos["ra_hours"]) / time_delta  # hours/sec
            dec_rate = (curr_pos["dec_degrees"] - prev_pos["dec_degrees"]) / time_delta  # deg/sec
            alt_rate = (curr_pos["alt_degrees"] - prev_pos["alt_degrees"]) / time_delta  # deg/sec
            az_rate = (curr_pos["az_degrees"] - prev_pos["az_degrees"]) / time_delta  # deg/sec

            # Calculate total angular velocity using spherical geometry (approximate)
            # Convert RA to degrees for this calculation
            ra_deg_rate = ra_rate * 15  # Convert hours/sec to deg/sec
            total_rate = (ra_deg_rate**2 + dec_rate**2)**0.5  # degrees/sec

            return {
                "ra": ra_rate,  # hours/sec
                "dec": dec_rate,  # deg/sec
                "alt": alt_rate,  # deg/sec
                "az": az_rate,  # deg/sec
                "total": total_rate,  # deg/sec
            }

        def get_velocity(self) -> dict[str, float]:
            """Get current velocity (slew speed).

            Returns:
                Dictionary with velocity components
            """
            with self.lock:
                return self.last_velocity.copy() if self.last_velocity else {}

        def set_alert_threshold(self, threshold: float) -> bool:
            """Set the collision alert threshold.

            Args:
                threshold: Velocity threshold in degrees/sec (0.1 to 20.0)

            Returns:
                True if threshold was set, False if invalid
            """
            if not (0.1 <= threshold <= 20.0):
                return False

            with self.lock:
                self.alert_threshold = threshold
            return True

        def get_alert_threshold(self) -> float:
            """Get the current alert threshold."""
            with self.lock:
                return self.alert_threshold

        def set_expected_slew(self, expected: bool) -> None:
            """Set whether a slew is expected (to suppress collision alerts)."""
            with self.lock:
                self.expected_slew = expected

        def set_chart_enabled(self, enabled: bool) -> None:
            """Enable or disable ASCII star chart visualization."""
            with self.lock:
                self.show_chart = enabled

        def _get_compass_indicator(self, azimuth: float) -> str:
            """Get compass rose indicator for azimuth.

            Args:
                azimuth: Azimuth in degrees (0-360)

            Returns:
                Compass indicator string
            """
            # 16-point compass rose
            directions = [
                "N", "NNE", "NE", "ENE",
                "E", "ESE", "SE", "SSE",
                "S", "SSW", "SW", "WSW",
                "W", "WNW", "NW", "NNW"
            ]

            # Calculate index (0-15)
            index = int((azimuth + 11.25) / 22.5) % 16
            return directions[index]

        def _get_altitude_bar(self, altitude: float) -> str:
            """Get altitude bar graph.

            Args:
                altitude: Altitude in degrees (0-90)

            Returns:
                Bar graph string using block characters
            """
            # Clamp altitude to 0-90
            alt = max(0, min(90, altitude))

            # Use 8 levels of blocks
            blocks = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
            level = int((alt / 90) * 7)  # 0-7
            return blocks[level] * 3

        def export_history(self, filename: str, format: str = "csv") -> tuple[bool, str]:
            """Export position history to a file.

            Args:
                filename: Output file path
                format: Export format ('csv' or 'json')

            Returns:
                Tuple of (success, message)
            """
            with self.lock:
                history_list = list(self.history)

            if not history_list:
                return False, "No history to export"

            try:
                if format.lower() == "csv":
                    import csv
                    with open(filename, 'w', newline='') as f:
                        writer = csv.writer(f)
                        writer.writerow(['timestamp', 'ra_hours', 'dec_degrees', 'alt_degrees', 'az_degrees'])
                        for entry in history_list:
                            writer.writerow([
                                entry['timestamp'].isoformat(),
                                entry['ra_hours'],
                                entry['dec_degrees'],
                                entry['alt_degrees'],
                                entry['az_degrees']
                            ])
                    return True, f"Exported {len(history_list)} entries to {filename}"

                elif format.lower() == "json":
                    import json
                    # Convert datetime objects to ISO format for JSON
                    json_data = []
                    for entry in history_list:
                        json_entry = entry.copy()
                        json_entry['timestamp'] = entry['timestamp'].isoformat()
                        json_data.append(json_entry)

                    with open(filename, 'w') as f:
                        json.dump({
                            'export_time': datetime.now().isoformat(),
                            'count': len(json_data),
                            'positions': json_data
                        }, f, indent=2)
                    return True, f"Exported {len(history_list)} entries to {filename}"

                else:
                    return False, f"Unknown format: {format}. Use 'csv' or 'json'"

            except Exception as e:
                return False, f"Export failed: {e}"

        def stop(self) -> None:
            """Stop background position tracking."""
            with self.lock:
                self.enabled = False
                if self.thread:
                    # Thread will exit on next iteration
                    self.running = False

        def _track_loop(self) -> None:
            """Background tracking loop."""
            while self.enabled:
                try:
                    # Import here to avoid circular dependencies
                    from celestron_nexstar import NexStarTelescope

                    # Check if we have a connection
                    port = state.get("port")
                    if not port:
                        time.sleep(self.update_interval)
                        continue

                    # Get current position
                    try:
                        with NexStarTelescope(str(port)) as telescope:
                            ra_hours, dec_degrees = telescope.get_position_ra_dec()
                            alt_degrees, az_degrees = telescope.get_position_alt_az()

                            with self.lock:
                                now = datetime.now()
                                prev_position = self.last_position.copy()
                                prev_time = self.last_update

                                curr_position = {
                                    "ra_hours": ra_hours,
                                    "dec_degrees": dec_degrees,
                                    "alt_degrees": alt_degrees,
                                    "az_degrees": az_degrees,
                                }

                                self.last_position = curr_position
                                self.last_update = now
                                self.error_count = 0

                                # Calculate velocity if we have a previous position
                                if prev_position and prev_time:
                                    time_delta = (now - prev_time).total_seconds()
                                    self.last_velocity = self._calculate_velocity(prev_position, curr_position, time_delta)

                                    # Detect if slewing (velocity > 0.1 deg/sec)
                                    self.is_slewing = self.last_velocity.get("total", 0) > 0.1

                                    # Check for unexpected movement (collision detection)
                                    total_speed = self.last_velocity.get("total", 0)
                                    if (not self.expected_slew and
                                        total_speed > self.alert_threshold):
                                        # Alert only once every 5 seconds to prevent spam
                                        should_alert = True
                                        if self.last_alert:
                                            seconds_since_alert = (now - self.last_alert).total_seconds()
                                            should_alert = seconds_since_alert >= 5

                                        if should_alert:
                                            self.last_alert = now
                                            # Log alert in history with special marker
                                            if self.history_enabled:
                                                self.history.append({
                                                    "timestamp": now,
                                                    "ra_hours": ra_hours,
                                                    "dec_degrees": dec_degrees,
                                                    "alt_degrees": alt_degrees,
                                                    "az_degrees": az_degrees,
                                                    "alert": "UNEXPECTED_MOVEMENT",
                                                    "speed": total_speed,
                                                })

                                # Add to history if enabled
                                if self.history_enabled:
                                    self.history.append({
                                        "timestamp": now,
                                        "ra_hours": ra_hours,
                                        "dec_degrees": dec_degrees,
                                        "alt_degrees": alt_degrees,
                                        "az_degrees": az_degrees,
                                    })

                    except Exception:
                        with self.lock:
                            self.error_count += 1
                            # Stop tracking after 3 consecutive errors
                            if self.error_count >= 3:
                                self.enabled = False
                                self.running = False

                    time.sleep(self.update_interval)

                except Exception:
                    # Fatal error in tracking loop
                    with self.lock:
                        self.enabled = False
                        self.running = False
                    break

        def get_status_text(self) -> str:
            """Get formatted status text for display."""
            with self.lock:
                if not self.enabled or not self.last_position:
                    return ""

                ra = self.last_position.get("ra_hours", 0)
                dec = self.last_position.get("dec_degrees", 0)
                alt = self.last_position.get("alt_degrees", 0)
                az = self.last_position.get("az_degrees", 0)

                # Format RA as hours:minutes:seconds
                ra_h = int(ra)
                ra_m = int((ra - ra_h) * 60)
                ra_s = int(((ra - ra_h) * 60 - ra_m) * 60)

                # Format Dec as degrees:arcminutes:arcseconds
                dec_sign = "+" if dec >= 0 else "-"
                dec_abs = abs(dec)
                dec_d = int(dec_abs)
                dec_m = int((dec_abs - dec_d) * 60)
                dec_s = int(((dec_abs - dec_d) * 60 - dec_m) * 60)

                age = ""
                if self.last_update:
                    seconds_ago = (datetime.now() - self.last_update).total_seconds()
                    age = " [live]" if seconds_ago < 5 else f" [{int(seconds_ago)}s ago]"

                # Add slew speed indicator if moving
                slew_info = ""
                if self.is_slewing and self.last_velocity:
                    speed = self.last_velocity.get("total", 0)

                    # Check if this is unexpected movement
                    if not self.expected_slew and speed > self.alert_threshold:
                        slew_info = f"  [⚠ ALERT: {speed:.2f}°/s]"
                    else:
                        slew_info = f"  [Slewing: {speed:.2f}°/s]"

                # Add ASCII chart visualization if enabled
                chart_info = ""
                if self.show_chart:
                    compass = self._get_compass_indicator(az)
                    alt_bar = self._get_altitude_bar(alt)
                    chart_info = f"  [{compass} {alt_bar}]"

                return (
                    f"RA: {ra_h:02d}h{ra_m:02d}m{ra_s:02d}s  "
                    f"Dec: {dec_sign}{dec_d:02d}°{dec_m:02d}'{dec_s:02d}\"  "
                    f"Alt: {alt:.1f}°  Az: {az:.1f}°{age}{chart_info}{slew_info}"
                )

    tracker = PositionTracker()

    # Build nested completer from typer app structure
    def build_completions() -> dict[str, dict[str, None] | None]:
        """Build nested completion dictionary from registered commands."""
        completions: dict[str, dict[str, None] | None] = {}

        # Add top-level commands
        for cmd in app.registered_commands:
            if cmd.name:
                completions[cmd.name] = None

        # Add command groups with their subcommands
        for group in app.registered_groups:
            if group.typer_instance and group.name:
                subcommands: dict[str, None] = {}
                for subcmd in group.typer_instance.registered_commands:
                    # Get command name: use explicit name or derive from callback function
                    cmd_name = subcmd.name
                    if not cmd_name and subcmd.callback:
                        # Derive name from function name (like Typer does)
                        cmd_name = subcmd.callback.__name__.replace("_", "-")

                    if cmd_name:
                        subcommands[cmd_name] = None

                if subcommands:
                    completions[group.name] = subcommands

        # Add shell-specific commands
        completions["exit"] = None
        completions["quit"] = None
        completions["help"] = None
        completions["clear"] = None
        completions["tracking"] = {
            "start": None,
            "stop": None,
            "status": None,
            "interval": None,
            "history": None,
            "clear": None,
            "stats": None,
            "export": None,
            "alert-threshold": None,
            "chart": None,
        }

        return completions

    def bottom_toolbar() -> HTML:
        """Generate bottom toolbar with position tracking."""
        status = tracker.get_status_text()
        if status:
            return HTML(f'<b><style bg="ansiblue" fg="ansiwhite"> Position: {status} </style></b>')
        return HTML('')

    # Custom style for prompt
    style = Style.from_dict({
        'prompt': 'ansicyan bold',
    })

    # Create session with history and completion
    session = PromptSession(
        history=InMemoryHistory(),
        completer=NestedCompleter.from_nested_dict(build_completions()),
        style=style,
        enable_history_search=True,
        bottom_toolbar=bottom_toolbar,
        refresh_interval=0.5,  # Refresh toolbar every 0.5 seconds
    )

    # Welcome message
    console.print("\n[bold green]╔═══════════════════════════════════════════════════╗[/bold green]")
    console.print("[bold green]║[/bold green]   [bold cyan]NexStar Interactive Shell[/bold cyan]                   [bold green]║[/bold green]")
    console.print("[bold green]╚═══════════════════════════════════════════════════╝[/bold green]\n")
    console.print("[dim]Type 'help' for available commands, 'exit' to quit[/dim]\n")

    # Command loop
    while True:
        try:
            # Get input from user
            text = session.prompt([('class:prompt', 'nexstar> ')])

            # Skip empty input
            if not text.strip():
                continue

            # Handle shell-specific commands
            cmd_lower = text.strip().lower()

            if cmd_lower in ['exit', 'quit']:
                tracker.stop()
                console.print("\n[bold]Goodbye![/bold]\n")
                break

            if cmd_lower == 'clear':
                console.clear()
                continue

            if cmd_lower == 'help':
                console.print("\n[bold]Available command groups:[/bold]")
                console.print("  [cyan]connect[/cyan]    - Connection commands")
                console.print("  [cyan]position[/cyan]   - Position query commands")
                console.print("  [cyan]goto[/cyan]       - Slew (goto) commands")
                console.print("  [cyan]move[/cyan]       - Manual movement commands")
                console.print("  [cyan]track[/cyan]      - Tracking control commands")
                console.print("  [cyan]align[/cyan]      - Alignment commands")
                console.print("  [cyan]location[/cyan]   - Observer location commands")
                console.print("  [cyan]time[/cyan]       - Time and date commands")
                console.print("  [cyan]catalog[/cyan]    - Celestial object catalogs")
                console.print("  [cyan]optics[/cyan]     - Telescope and eyepiece configuration")
                console.print("  [cyan]ephemeris[/cyan]  - Ephemeris file management")
                console.print("\n[bold]Shell-specific commands:[/bold]")
                console.print("  [cyan]tracking start[/cyan]                            - Start background position tracking")
                console.print("  [cyan]tracking stop[/cyan]                             - Stop background position tracking")
                console.print("  [cyan]tracking status[/cyan]                           - Show tracking status")
                console.print("  [cyan]tracking interval <sec>[/cyan]                   - Set update interval (0.5-30.0s)")
                console.print("  [cyan]tracking history [--last N][/cyan]              - Show position history")
                console.print("  [cyan]tracking clear[/cyan]                            - Clear position history")
                console.print("  [cyan]tracking stats[/cyan]                            - Show tracking statistics")
                console.print("  [cyan]tracking export <file> [--format][/cyan]    - Export history (csv/json)")
                console.print("  [cyan]tracking alert-threshold <deg/s>[/cyan]     - Set collision alert threshold")
                console.print("  [cyan]tracking chart on|off[/cyan]                - Toggle ASCII star chart visualization")
                console.print("\n[dim]Use '<command> --help' for detailed help on each command[/dim]\n")
                continue

            # Handle tracking commands
            if text.strip().startswith("tracking "):
                parts = text.strip().split()
                subcmd = parts[1] if len(parts) > 1 else ""

                if subcmd == "start":
                    if not state.get("port"):
                        console.print("[yellow]Warning: No telescope port configured. Use --port or set NEXSTAR_PORT[/yellow]")
                        console.print("[dim]Tracking will start once a connection is available[/dim]")
                    tracker.start()
                    console.print("[green]✓[/green] Background position tracking started")
                    console.print("[dim]Position updates will appear in the status bar at the bottom[/dim]")

                elif subcmd == "stop":
                    tracker.stop()
                    console.print("[green]✓[/green] Background position tracking stopped")

                elif subcmd == "status":
                    if tracker.enabled:
                        status = tracker.get_status_text()
                        if status:
                            console.print(f"[green]●[/green] Tracking active: {status}")
                        else:
                            console.print("[yellow]○[/yellow] Tracking enabled but no data yet")
                    else:
                        console.print("[dim]○[/dim] Tracking disabled")
                    console.print(f"[dim]Update interval: {tracker.get_interval()}s[/dim]")

                elif subcmd == "interval":
                    if len(parts) < 3:
                        console.print(f"[yellow]Current update interval: {tracker.get_interval()}s[/yellow]")
                        console.print("[dim]Usage: tracking interval <seconds>[/dim]")
                        console.print("[dim]Valid range: 0.5 to 30.0 seconds[/dim]")
                    else:
                        try:
                            interval = float(parts[2])
                            if tracker.set_interval(interval):
                                console.print(f"[green]✓[/green] Update interval set to {interval}s")
                            else:
                                console.print("[red]Invalid interval. Must be between 0.5 and 30.0 seconds[/red]")
                        except ValueError:
                            console.print(f"[red]Invalid number: {parts[2]}[/red]")

                elif subcmd == "history":
                    # Parse optional arguments
                    last_n = None
                    for i, part in enumerate(parts):
                        if part == "--last" and i + 1 < len(parts):
                            try:
                                last_n = int(parts[i + 1])
                            except ValueError:
                                console.print(f"[red]Invalid number for --last: {parts[i + 1]}[/red]")
                                break
                    else:
                        # Get history
                        history = tracker.get_history(last=last_n)
                        if not history:
                            console.print("[dim]No position history available yet[/dim]")
                        else:
                            from rich.table import Table
                            table = Table(title=f"Position History ({len(history)} entries)")
                            table.add_column("Time", style="cyan")
                            table.add_column("RA", justify="right")
                            table.add_column("Dec", justify="right")
                            table.add_column("Alt", justify="right")
                            table.add_column("Az", justify="right")

                            for entry in history:
                                timestamp = entry["timestamp"].strftime("%H:%M:%S")
                                ra = entry["ra_hours"]
                                dec = entry["dec_degrees"]
                                alt = entry["alt_degrees"]
                                az = entry["az_degrees"]

                                # Format RA as hours:minutes:seconds
                                ra_h = int(ra)
                                ra_m = int((ra - ra_h) * 60)
                                ra_s = int(((ra - ra_h) * 60 - ra_m) * 60)

                                # Format Dec as degrees:arcminutes:arcseconds
                                dec_sign = "+" if dec >= 0 else "-"
                                dec_abs = abs(dec)
                                dec_d = int(dec_abs)
                                dec_m = int((dec_abs - dec_d) * 60)
                                dec_s = int(((dec_abs - dec_d) * 60 - dec_m) * 60)

                                table.add_row(
                                    timestamp,
                                    f"{ra_h:02d}h{ra_m:02d}m{ra_s:02d}s",
                                    f"{dec_sign}{dec_d:02d}°{dec_m:02d}'{dec_s:02d}\"",
                                    f"{alt:.1f}°",
                                    f"{az:.1f}°"
                                )

                            console.print(table)

                elif subcmd == "clear":
                    tracker.clear_history()
                    console.print("[green]✓[/green] Position history cleared")

                elif subcmd == "stats":
                    stats = tracker.get_history_stats()
                    velocity = tracker.get_velocity()

                    if stats["count"] == 0:
                        console.print("[dim]No position history available yet[/dim]")
                    else:
                        console.print("\n[bold]Position Tracking Statistics:[/bold]")
                        console.print(f"  Total entries: [cyan]{stats['count']}[/cyan]")
                        if stats["count"] >= 2:
                            duration_min = stats["duration_seconds"] / 60
                            console.print(f"  Duration: [cyan]{duration_min:.1f}[/cyan] minutes")
                            console.print(f"  First recorded: [dim]{stats['first_timestamp'].strftime('%H:%M:%S')}[/dim]")
                            console.print(f"  Last recorded: [dim]{stats['last_timestamp'].strftime('%H:%M:%S')}[/dim]")
                            console.print(f"  Total RA drift: [yellow]{stats['total_ra_drift_arcsec']:.1f}[/yellow] arcsec")
                            console.print(f"  Total Dec drift: [yellow]{stats['total_dec_drift_arcsec']:.1f}[/yellow] arcsec")

                        if velocity:
                            console.print("\n[bold]Current Velocity:[/bold]")
                            console.print(f"  Total: [cyan]{velocity.get('total', 0):.3f}[/cyan] °/s")
                            console.print(f"  RA: [dim]{velocity.get('ra', 0):.3f} hours/s[/dim]")
                            console.print(f"  Dec: [dim]{velocity.get('dec', 0):.3f} °/s[/dim]")
                            console.print(f"  Alt: [dim]{velocity.get('alt', 0):.3f} °/s[/dim]")
                            console.print(f"  Az: [dim]{velocity.get('az', 0):.3f} °/s[/dim]")
                            if tracker.is_slewing:
                                console.print("  Status: [yellow]Slewing[/yellow]")
                            else:
                                console.print("  Status: [green]Tracking[/green]")

                        console.print()

                elif subcmd == "export":
                    if len(parts) < 3:
                        console.print("[yellow]Usage: tracking export <filename> [--format csv|json][/yellow]")
                        console.print("[dim]Default format is CSV[/dim]")
                    else:
                        filename = parts[2]
                        export_format = "csv"

                        # Parse optional format argument
                        for i, part in enumerate(parts):
                            if part == "--format" and i + 1 < len(parts):
                                export_format = parts[i + 1]

                        success, message = tracker.export_history(filename, export_format)
                        if success:
                            console.print(f"[green]✓[/green] {message}")
                        else:
                            console.print(f"[red]✗[/red] {message}")

                elif subcmd == "alert-threshold":
                    if len(parts) < 3:
                        console.print(f"[yellow]Current alert threshold: {tracker.get_alert_threshold()}°/s[/yellow]")
                        console.print("[dim]Usage: tracking alert-threshold <degrees_per_sec>[/dim]")
                        console.print("[dim]Valid range: 0.1 to 20.0 degrees/sec[/dim]")
                        console.print("[dim]Alerts trigger when unexpected movement exceeds this speed[/dim]")
                    else:
                        try:
                            threshold = float(parts[2])
                            if tracker.set_alert_threshold(threshold):
                                console.print(f"[green]✓[/green] Alert threshold set to {threshold}°/s")
                            else:
                                console.print("[red]Invalid threshold. Must be between 0.1 and 20.0 degrees/sec[/red]")
                        except ValueError:
                            console.print(f"[red]Invalid number: {parts[2]}[/red]")

                elif subcmd == "chart":
                    if len(parts) < 3:
                        console.print("[yellow]Usage: tracking chart on|off[/yellow]")
                        console.print("[dim]Toggle ASCII star chart visualization in status bar[/dim]")
                    else:
                        mode = parts[2].lower()
                        if mode == "on":
                            tracker.set_chart_enabled(True)
                            console.print("[green]✓[/green] ASCII star chart enabled")
                            console.print("[dim]Compass direction and altitude bar will appear in status bar[/dim]")
                        elif mode == "off":
                            tracker.set_chart_enabled(False)
                            console.print("[green]✓[/green] ASCII star chart disabled")
                        else:
                            console.print(f"[red]Invalid option: {mode}. Use 'on' or 'off'[/red]")

                else:
                    console.print(f"[red]Unknown tracking command: {subcmd}[/red]")
                    console.print("[dim]Available: start, stop, status, interval, history, clear, stats, export, alert-threshold, chart[/dim]")

                continue

            # Parse command with proper shell-like splitting (handles quotes)
            try:
                args = shlex.split(text)
            except ValueError as e:
                console.print(f"[red]Error parsing command: {e}[/red]")
                continue

            if not args:
                continue

            # Execute command through typer
            old_argv = sys.argv
            command_success = False
            try:
                # Construct argv as if called from command line
                sys.argv = ['nexstar', *args]

                # Call the app without exiting on error
                app(standalone_mode=False)
                command_success = True

            except SystemExit as e:
                # Typer may raise SystemExit on success (exit code 0) or errors
                if e.code in (0, None):
                    command_success = True
                else:
                    console.print(f"[yellow]Command exited with code: {e.code}[/yellow]")

            except typer.Exit as e:
                # Typer's Exit exception
                if e.exit_code in (0, None):
                    command_success = True
                else:
                    console.print(f"[yellow]Command exited with code: {e.exit_code}[/yellow]")

            except typer.Abort:
                console.print("[yellow]Command aborted[/yellow]")

            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                if state.get("verbose"):
                    import traceback
                    console.print(f"[dim]{traceback.format_exc()}[/dim]")

            finally:
                # Restore original argv
                sys.argv = old_argv

                # Auto-start tracking after successful align command
                if command_success and len(args) > 0 and args[0] == "align" and not tracker.enabled:
                    tracker.start()
                    console.print("\n[dim]→ Background position tracking started automatically[/dim]")
                    console.print("[dim]  Position updates will appear in the status bar[/dim]")
                    console.print("[dim]  Use 'tracking stop' to disable[/dim]\n")

        except KeyboardInterrupt:
            # Ctrl+C pressed - just show new prompt
            console.print()
            continue

        except EOFError:
            # Ctrl+D pressed - exit gracefully
            console.print("\n[bold]Goodbye![/bold]\n")
            break

    # Clean up: stop tracking thread
    tracker.stop()


if __name__ == "__main__":
    app()
