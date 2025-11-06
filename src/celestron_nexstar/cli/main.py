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

    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import NestedCompleter
    from prompt_toolkit.formatted_text import HTML
    from prompt_toolkit.history import InMemoryHistory
    from prompt_toolkit.styles import Style

    from .tracking import PositionTracker

    # Background position tracking state
    # Instantiate the tracker with a function to get the port
    tracker = PositionTracker(lambda: state.get("port"))

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
