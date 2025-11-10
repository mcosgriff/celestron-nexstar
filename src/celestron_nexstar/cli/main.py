"""
Celestron NexStar CLI - Main Application

This is the main entry point for the Celestron NexStar command-line interface.
"""

import typer
from dotenv import load_dotenv
from rich.console import Console

# Import and register subcommands
from .commands import (
    align,
    aurora,
    binoculars,
    catalog,
    connect,
    dashboard,
    data,
    eclipse,
    ephemeris,
    goto,
    location,
    move,
    multi_night,
    naked_eye,
    optics,
    planets,
    position,
    time,
    tonight,
    track,
)


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

    load_dotenv()

    if verbose:
        console.print("[dim]Verbose mode enabled[/dim]")
        if port:
            console.print(f"[dim]Using port: {port}[/dim]")
        if profile:
            console.print(f"[dim]Using profile: {profile}[/dim]")


@app.command(rich_help_panel="Utilities")
def version() -> None:
    """Show the CLI version."""
    from celestron_nexstar.cli import __version__

    console.print(f"[bold]Celestron NexStar CLI[/bold] version [cyan]{__version__}[/cyan]")


# Register command groups organized by category

# Telescope Control
app.add_typer(
    connect.app,
    name="connect",
    help="Connection commands",
    rich_help_panel="Telescope Control",
)
app.add_typer(
    position.app,
    name="position",
    help="Position query commands",
    rich_help_panel="Telescope Control",
)
app.add_typer(
    goto.app,
    name="goto",
    help="Slew (goto) commands",
    rich_help_panel="Telescope Control",
)
app.add_typer(
    move.app,
    name="move",
    help="Manual movement commands",
    rich_help_panel="Telescope Control",
)
app.add_typer(
    track.app,
    name="track",
    help="Tracking control commands",
    rich_help_panel="Telescope Control",
)
app.add_typer(
    align.app,
    name="align",
    help="Alignment commands",
    rich_help_panel="Telescope Control",
)

# Planning & Observation
app.add_typer(
    tonight.app,
    name="telescope",
    help="Telescope viewing commands",
    rich_help_panel="Planning & Observation",
)
app.add_typer(
    multi_night.app,
    name="multi-night",
    help="Multi-night planning and comparison (uses telescope configuration)",
    rich_help_panel="Planning & Observation",
)
app.add_typer(
    binoculars.app,
    name="binoculars",
    help="Binocular viewing (ISS, constellations, asterisms)",
    rich_help_panel="Planning & Observation",
)
app.add_typer(
    naked_eye.app,
    name="naked-eye",
    help="Naked-eye stargazing (no equipment needed)",
    rich_help_panel="Planning & Observation",
)
app.add_typer(
    aurora.app,
    name="aurora",
    help="Aurora borealis (Northern Lights) visibility",
    rich_help_panel="Planning & Observation",
)
app.add_typer(
    eclipse.app,
    name="eclipse",
    help="Lunar and solar eclipse predictions",
    rich_help_panel="Planning & Observation",
)
app.add_typer(
    planets.app,
    name="planets",
    help="Planetary events (conjunctions, oppositions)",
    rich_help_panel="Planning & Observation",
)
app.add_typer(
    catalog.app,
    name="catalog",
    help="Celestial object catalogs",
    rich_help_panel="Planning & Observation",
)

# Configuration
app.add_typer(
    location.app,
    name="location",
    help="Observer location commands",
    rich_help_panel="Configuration",
)
app.add_typer(
    time.app,
    name="time",
    help="Time and date commands",
    rich_help_panel="Configuration",
)
app.add_typer(
    optics.app,
    name="optics",
    help="Telescope and eyepiece configuration",
    rich_help_panel="Configuration",
)
app.add_typer(
    ephemeris.app,
    name="ephemeris",
    help="Ephemeris file management",
    rich_help_panel="Configuration",
)

# Data & Management
app.add_typer(
    data.app,
    name="data",
    help="Data import and management",
    rich_help_panel="Data & Management",
)
app.add_typer(
    dashboard.app,
    name="dashboard",
    help="Full-screen dashboard",
    rich_help_panel="Data & Management",
)


# Also add connect commands directly to main app for convenience
@app.command("conn", rich_help_panel="Utilities")
def conn(
    port: str = typer.Argument(..., help="Serial port (e.g., /dev/ttyUSB0, COM3)"),
    baudrate: int = typer.Option(9600, help="Baud rate"),
    timeout: float = typer.Option(2.0, help="Connection timeout in seconds"),
) -> None:
    """Quick connect to telescope (shorthand for 'connect connect')."""
    connect.connect(port, baudrate, timeout)


@app.command("disc", rich_help_panel="Utilities")
def disc() -> None:
    """Quick disconnect from telescope (shorthand for 'connect disconnect')."""
    connect.disconnect()


@app.command(rich_help_panel="Utilities")
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
    from prompt_toolkit.filters import Condition
    from prompt_toolkit.formatted_text import HTML
    from prompt_toolkit.history import InMemoryHistory
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.key_binding.key_processor import KeyPressEvent
    from prompt_toolkit.styles import Style

    from celestron_nexstar.api.movement import MovementController
    from celestron_nexstar.api.tracking import PositionTracker

    from .tutorial import TutorialSystem

    # Helper function to get port with correct type
    def get_port() -> str | None:
        """Get port from state, ensuring correct type."""
        port = state.get("port")
        return port if isinstance(port, str) else None

    # Background position tracking state
    # Instantiate the tracker with a function to get the port
    tracker = PositionTracker(get_port)

    # Interactive movement control state
    # Instantiate the movement controller with a function to get the port
    movement = MovementController(get_port)

    # Tutorial system
    tutorial_system = TutorialSystem(console)

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
        completions["tutorial"] = {
            "all": None,
            "demo": None,
        }
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
        """Generate bottom toolbar with position tracking and movement status."""
        parts = []

        # Position tracking
        status = tracker.get_status_text()
        if status:
            parts.append(f'<b><style bg="ansiblue" fg="ansiwhite"> Position: {status} </style></b>')

        # Movement control status
        if movement.moving:
            direction = movement.active_direction or ""
            arrow = {"up": "↑", "down": "↓", "left": "←", "right": "→"}.get(direction, "?")
            parts.append(
                f'<b><style bg="ansired" fg="ansiwhite"> Moving {arrow} Speed:{movement.slew_rate}/9 </style></b>'
            )
        else:
            parts.append(
                f'<b><style bg="ansigreen" fg="ansiblack"> ▣ Speed:{movement.slew_rate}/9 (arrows=move +/-=speed ESC=stop ^P/^N=history) </style></b>'
            )

        return HTML(" ".join(parts))

    # Key bindings for interactive movement control
    kb = KeyBindings()

    # Define filter: only activate speed/movement keys when input buffer is empty
    @Condition
    def buffer_is_empty() -> bool:
        from prompt_toolkit.application import get_app

        try:
            app = get_app()
            return len(app.current_buffer.text) == 0
        except Exception:
            return False

    # Arrow keys move telescope (only when not typing)
    @kb.add("up", filter=buffer_is_empty)
    def _(event: KeyPressEvent) -> None:
        """Move telescope up when up arrow is pressed (only when not typing)."""
        movement.start_move("up")

    @kb.add("down", filter=buffer_is_empty)
    def _(event: KeyPressEvent) -> None:
        """Move telescope down when down arrow is pressed (only when not typing)."""
        movement.start_move("down")

    @kb.add("left", filter=buffer_is_empty)
    def _(event: KeyPressEvent) -> None:
        """Move telescope left when left arrow is pressed (only when not typing)."""
        movement.start_move("left")

    @kb.add("right", filter=buffer_is_empty)
    def _(event: KeyPressEvent) -> None:
        """Move telescope right when right arrow is pressed (only when not typing)."""
        movement.start_move("right")

    # Speed adjustment (only when not typing to avoid interfering with -- arguments)
    @kb.add("+", filter=buffer_is_empty)
    @kb.add("=", filter=buffer_is_empty)  # Also works without shift
    def _(event: KeyPressEvent) -> None:
        """Increase slew rate (only when not typing)."""
        movement.increase_rate()

    @kb.add("-", filter=buffer_is_empty)
    def _(event: KeyPressEvent) -> None:
        """Decrease slew rate (only when not typing)."""
        movement.decrease_rate()
        movement.decrease_rate()

    # Command history navigation using Ctrl+P (previous) and Ctrl+N (next)
    @kb.add("c-p")
    def _(event: KeyPressEvent) -> None:
        """Navigate to previous command in history (Ctrl+P)."""
        event.current_buffer.history_backward()

    @kb.add("c-n")
    def _(event: KeyPressEvent) -> None:
        """Navigate to next command in history (Ctrl+N)."""
        event.current_buffer.history_forward()

    # ESC always stops movement (works anytime)
    @kb.add("escape")
    def _(event: KeyPressEvent) -> None:
        """Stop telescope movement when ESC is pressed."""
        movement.stop_move()

    # Custom style for prompt
    style = Style.from_dict(
        {
            "prompt": "ansicyan bold",
        }
    )

    # Create session with history and completion
    session: PromptSession[str] = PromptSession(
        history=InMemoryHistory(),
        completer=NestedCompleter.from_nested_dict(build_completions()),
        key_bindings=kb,
        style=style,
        enable_history_search=True,
        bottom_toolbar=bottom_toolbar,
        refresh_interval=0.5,  # Refresh toolbar every 0.5 seconds
    )

    # Welcome message
    console.print("\n[bold green]╔═══════════════════════════════════════════════════╗[/bold green]")
    console.print(
        "[bold green]║[/bold green]   [bold cyan]NexStar Interactive Shell[/bold cyan]                   [bold green]║[/bold green]"
    )
    console.print("[bold green]╚═══════════════════════════════════════════════════╝[/bold green]\n")
    console.print("[bold]Quick Start:[/bold]")
    console.print("  • Type [cyan]'tutorial'[/cyan] for an interactive guided tour")
    console.print("  • Type [cyan]'help'[/cyan] to see all available commands")
    console.print(
        "  • Press [cyan]arrow keys[/cyan] to move telescope | [cyan]+/-[/cyan]: speed | [cyan]ESC[/cyan]: stop"
    )
    console.print("  • Press [cyan]Ctrl+P/Ctrl+N[/cyan] for command history (previous/next)")
    console.print("  • Type [cyan]'exit'[/cyan] to quit\n")

    # Command loop
    while True:
        try:
            # Get input from user
            text = session.prompt([("class:prompt", "nexstar> ")])

            # Skip empty input
            if not text.strip():
                continue

            # Handle shell-specific commands
            cmd_lower = text.strip().lower()

            if cmd_lower in ["exit", "quit"]:
                movement.stop_move()  # Stop any active movement
                tracker.stop()
                console.print("\n[bold]Goodbye![/bold]\n")
                break

            if cmd_lower == "clear":
                console.clear()
                continue

            if cmd_lower == "tutorial" or text.strip().startswith("tutorial "):
                parts = text.strip().split()
                if len(parts) == 1:
                    # Show tutorial menu
                    tutorial_system.start()
                elif parts[1] == "all":
                    # Run all lessons
                    tutorial_system.run_all_lessons()
                elif parts[1] == "demo":
                    # Run only demo lessons
                    tutorial_system.run_all_lessons(demo_only=True)
                elif parts[1].isdigit():
                    # Run specific lesson (1-indexed)
                    lesson_num = int(parts[1])
                    if 1 <= lesson_num <= len(tutorial_system.lessons):
                        tutorial_system.run_lesson(lesson_num - 1)
                    else:
                        console.print(f"[red]Invalid lesson number. Choose 1-{len(tutorial_system.lessons)}[/red]")
                else:
                    console.print("[red]Usage: tutorial [all|demo|<lesson_number>][/red]")
                continue

            if cmd_lower == "help":
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
                console.print("  [cyan]data[/cyan]       - Data import and management")
                console.print("  [cyan]optics[/cyan]     - Telescope and eyepiece configuration")
                console.print("  [cyan]ephemeris[/cyan]  - Ephemeris file management")
                console.print("\n[bold]Shell-specific commands:[/bold]")
                console.print(
                    "  [cyan]tracking start[/cyan]                            - Start background position tracking"
                )
                console.print(
                    "  [cyan]tracking stop[/cyan]                             - Stop background position tracking"
                )
                console.print("  [cyan]tracking status[/cyan]                           - Show tracking status")
                console.print(
                    "  [cyan]tracking interval <sec>[/cyan]                   - Set update interval (0.5-30.0s)"
                )
                console.print("  [cyan]tracking history [--last N][/cyan]              - Show position history")
                console.print("  [cyan]tracking clear[/cyan]                            - Clear position history")
                console.print("  [cyan]tracking stats[/cyan]                            - Show tracking statistics")
                console.print("  [cyan]tracking export <file> [--format][/cyan]    - Export history (csv/json)")
                console.print("  [cyan]tracking alert-threshold <deg/s>[/cyan]     - Set collision alert threshold")
                console.print(
                    "  [cyan]tracking chart on|off[/cyan]                - Toggle ASCII star chart visualization"
                )
                console.print("\n[bold]Interactive Movement Control:[/bold]")
                console.print("  [cyan]Arrow Keys (↑↓←→)[/cyan]   - Move telescope in any direction")
                console.print("  [cyan]+ / -[/cyan]              - Increase/decrease slew speed (0-9)")
                console.print("  [cyan]ESC[/cyan]                - Stop all movement")
                console.print(
                    "  [dim]Current speed displayed in status bar (green when stopped, red when moving)[/dim]"
                )
                console.print("\n[bold]Command History:[/bold]")
                console.print("  [cyan]Ctrl+P[/cyan]             - Previous command in history")
                console.print("  [cyan]Ctrl+N[/cyan]             - Next command in history")
                console.print("\n[bold]Data Import Commands:[/bold]")
                console.print("  [cyan]data sources[/cyan]                    - List available catalog data sources")
                console.print(
                    "  [cyan]data import <source>[/cyan]            - Import catalog data (e.g., data import openngc)"
                )
                console.print("  [cyan]data import <source> -m <mag>[/cyan]   - Import with custom magnitude limit")
                console.print("  [cyan]data stats[/cyan]                      - Show database statistics")
                console.print("\n[bold]Tutorial System:[/bold]")
                console.print("  [cyan]tutorial[/cyan]           - Show interactive tutorial menu")
                console.print("  [cyan]tutorial <number>[/cyan]  - Run specific lesson (e.g., tutorial 1)")
                console.print("  [cyan]tutorial demo[/cyan]      - Run demo lessons (no telescope needed)")
                console.print("  [cyan]tutorial all[/cyan]       - Run all lessons in sequence")
                console.print("\n[dim]Use '<command> --help' for detailed help on each command[/dim]")
                console.print("[dim]New users: Type 'tutorial' to learn the shell interactively![/dim]\n")
                continue

            # Handle tracking commands
            if text.strip().startswith("tracking "):
                parts = text.strip().split()
                subcmd = parts[1] if len(parts) > 1 else ""

                if subcmd == "start":
                    if not state.get("port"):
                        console.print(
                            "[yellow]Warning: No telescope port configured. Use --port or set NEXSTAR_PORT[/yellow]"
                        )
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
                                    f"{az:.1f}°",
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
                            console.print(
                                f"  First recorded: [dim]{stats['first_timestamp'].strftime('%H:%M:%S')}[/dim]"
                            )
                            console.print(f"  Last recorded: [dim]{stats['last_timestamp'].strftime('%H:%M:%S')}[/dim]")
                            console.print(
                                f"  Total RA drift: [yellow]{stats['total_ra_drift_arcsec']:.1f}[/yellow] arcsec"
                            )
                            console.print(
                                f"  Total Dec drift: [yellow]{stats['total_dec_drift_arcsec']:.1f}[/yellow] arcsec"
                            )

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
                    console.print(
                        "[dim]Available: start, stop, status, interval, history, clear, stats, export, alert-threshold, chart[/dim]"
                    )

                continue

            # Parse command with proper shell-like splitting (handles quotes)
            try:
                args = shlex.split(text)
            except ValueError as e:
                console.print(f"[red]Error parsing command: {e}[/red]")
                continue

            if not args:
                continue

            # Check if user typed just a command group name without subcommand
            # Provide helpful guidance
            command_groups_needing_subcommands = {
                "catalog": "Try: catalog list, catalog search, catalog info, catalog catalogs",
                "optics": "Try: optics config, optics show",
                "ephemeris": "Try: ephemeris download, ephemeris list, ephemeris verify, ephemeris sets",
                "position": "Try: position get",
                "goto": "Try: goto object, goto ra-dec, goto alt-az",
                "move": "Try: move fixed, move stop",
                "track": "Try: track get, track set",
                "align": "Try: align sync",
                "location": "Try: location show, location set, location geocode",
                "time": "Try: time get, time set",
                "data": "Try: data sources, data import, data stats",
            }

            if len(args) == 1 and args[0] in command_groups_needing_subcommands:
                console.print(f"[yellow]'{args[0]}' requires a subcommand.[/yellow]")
                console.print(f"[dim]{command_groups_needing_subcommands[args[0]]}[/dim]")
                console.print(f"[dim]Or use: {args[0]} --help[/dim]")
                continue

            # Execute command through typer
            old_argv = sys.argv
            command_success = False
            try:
                # Construct argv as if called from command line
                sys.argv = ["nexstar", *args]

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
