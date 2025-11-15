"""
Mount Settings Commands

Commands for configuring mount settings including backlash control and GoTo approach.
"""

import logging
from typing import Literal

import typer
from click import Context
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from typer.core import TyperGroup

from celestron_nexstar.cli.utils.output import print_error, print_success
from celestron_nexstar.cli.utils.state import ensure_connected


logger = logging.getLogger(__name__)


class SortedCommandsGroup(TyperGroup):
    """Custom Typer group that sorts commands alphabetically within each help panel."""

    def list_commands(self, ctx: Context) -> list[str]:
        """Return commands sorted alphabetically."""
        commands = super().list_commands(ctx)
        return sorted(commands)


console = Console()
app = typer.Typer(help="Mount settings and backlash control", cls=SortedCommandsGroup)


@app.command("backlash-info", rich_help_panel="Backlash Control")
def backlash_info() -> None:
    """
    Display information about backlash and how to control it.

    Backlash is the mechanical play in the gear train that causes a delay
    when the mount changes direction. Proper backlash control improves
    tracking accuracy and GoTo precision.

    Reference: https://www.celestron.com/blogs/knowledgebase/controlling-backlash-in-your-mount
    """
    console.print("\n[bold cyan]Understanding Backlash[/bold cyan]\n")

    info_text = """
[bold]What is Backlash?[/bold]

Backlash is the mechanical play or "slop" in the gear train that occurs when
the mount changes direction. This causes a delay before the telescope actually
starts moving, which can affect:

  • Tracking accuracy (stars drift during tracking)
  • GoTo precision (objects not centered after slewing)
  • Alignment accuracy (difficulty centering alignment stars)

[bold]How to Control Backlash[/bold]

1. [bold]Anti-Backlash Settings[/bold] (0-99)
   Adjust these values in the hand control:
   Menu > Scope Setup > Anti-Backlash

   For AltAz mounts (NexStar 6SE/8SE):
   • Azimuth Positive/Negative: Controls backlash when moving east/west
   • Altitude Positive/Negative: Controls backlash when moving up/down

   Start with value 50 and adjust based on testing:
   • Too high: Field of view jumps past target (overshoot)
   • Too low: Not all backlash corrected, drift occurs
   • Correct: Smooth tracking with no overshoot or drift

2. [bold]GoTo Approach Settings[/bold]
   Adjust the direction the telescope approaches targets:
   Menu > Scope Setup > GoTo Approach

   For AltAz mounts:
   • Altitude: Positive = up, Negative = down
   • Azimuth: Positive = right, Negative = left

   [yellow]Default settings:[/yellow] Altitude negative, Azimuth positive

   The approach direction should be OPPOSITE to the load direction:
   • If tube is heavy (accessories pull down): Use negative altitude
   • If tracking west: Use positive azimuth (same as tracking direction)

3. [bold]Calibration Procedure[/bold]
   Use the backlash calibration command to find optimal settings:

   nexstar mount backlash-calibrate
"""
    console.print(Panel(info_text.strip(), border_style="cyan"))
    console.print()

    console.print("[bold yellow]Tips:[/bold yellow]")
    console.print("  • Always use the same approach directions when aligning")
    console.print("  • Re-calibrate after changing accessories (cameras, eyepieces)")
    console.print("  • For astrophotography, backlash control is critical")
    console.print("  • Balance your scope to minimize load on the mount")
    console.print()


@app.command("backlash-calibrate", rich_help_panel="Backlash Control")
def backlash_calibrate(
    port: str | None = typer.Option(None, "--port", "-p", help="Serial port"),
    axis: Literal["azimuth", "altitude", "both"] = typer.Option(
        "both", help="Axis to calibrate (azimuth, altitude, or both)"
    ),
) -> None:
    """
    Guide you through calibrating anti-backlash settings.

    This interactive procedure helps you find the optimal anti-backlash values
    for your mount by testing different settings and observing the results.

    Reference: https://www.celestron.com/blogs/knowledgebase/controlling-backlash-in-your-mount

    Example:
        nexstar mount backlash-calibrate
        nexstar mount backlash-calibrate --axis azimuth
    """
    try:
        ensure_connected(port)

        console.print("\n[bold cyan]Backlash Calibration Guide[/bold cyan]\n")

        instructions = """
This procedure will help you find optimal anti-backlash settings.

[bold]Procedure:[/bold]

1. Set initial anti-backlash value to 99 in hand control:
   Menu > Scope Setup > Anti-Backlash > [Axis] Positive/Negative

2. Slew the mount eastward (azimuth) or upward (altitude) at rate 3 or higher
   for at least 10 arc-minutes

3. Release the button and observe:
   • If field jumps west/down: Value too high (overshoot)
   • If field drifts east/up: Value too low (not enough correction)
   • If field stays steady: Value is correct!

4. Adjust value and repeat until no overshoot occurs

5. Set the opposite direction (Negative) to the same value

[bold]Note:[/bold] You must adjust these settings in the hand control menu.
This command provides guidance only.
"""
        console.print(Panel(instructions.strip(), border_style="yellow"))
        console.print()

        if axis in ["azimuth", "both"]:
            console.print("[bold]Azimuth (East/West) Calibration:[/bold]")
            console.print("  1. Set Azimuth Positive anti-backlash to 99 in hand control")
            console.print("  2. Use arrow buttons to slew eastward at rate 3+ for 10+ arc-minutes")
            console.print("  3. Release and observe field movement")
            console.print("  4. Adjust value down if overshoot, up if drift")
            console.print("  5. When correct, set Azimuth Negative to same value")
            console.print()

        if axis in ["altitude", "both"]:
            console.print("[bold]Altitude (Up/Down) Calibration:[/bold]")
            console.print("  1. Set Altitude Positive anti-backlash to 99 in hand control")
            console.print("  2. Use arrow buttons to slew upward at rate 3+ for 10+ arc-minutes")
            console.print("  3. Release and observe field movement")
            console.print("  4. Adjust value down if overshoot, up if drift")
            console.print("  5. When correct, set Altitude Negative to same value")
            console.print()

        console.print("[yellow]Press ENTER when you've completed the calibration...[/yellow]")
        try:
            Prompt.ask("", default="")
        except KeyboardInterrupt:
            console.print("\n[yellow]Calibration cancelled[/yellow]")
            return

        print_success("Backlash calibration complete!")
        console.print("\n[bold]Next Steps:[/bold]")
        console.print("  • Test GoTo accuracy with: nexstar goto radec --ra 12 --dec 45")
        console.print("  • Monitor tracking with: nexstar tracking start")
        console.print("  • Re-calibrate if you add/remove accessories")
        console.print()

    except Exception as e:
        print_error(f"Calibration guide failed: {e}")
        raise typer.Exit(code=1) from None


@app.command("goto-approach-info", rich_help_panel="GoTo Approach")
def goto_approach_info() -> None:
    """
    Display information about GoTo Approach settings.

    GoTo Approach controls the direction the telescope uses when approaching
    targets during GoTo operations. Setting this correctly minimizes backlash
    effects and improves centering accuracy.

    Reference: https://www.celestron.com/blogs/knowledgebase/controlling-backlash-in-your-mount
    """
    console.print("\n[bold cyan]GoTo Approach Settings[/bold cyan]\n")

    info_text = """
[bold]What is GoTo Approach?[/bold]

GoTo Approach determines the direction the telescope uses when making final
adjustments to center a target during GoTo operations. Setting this correctly
ensures the mount approaches targets from a direction that has already taken
up the backlash slack, resulting in better centering accuracy.

[bold]Setting Directions[/bold]

For AltAz mounts (NexStar 6SE/8SE), directions are defined from the back of
the scope in the north position:

[bold]Altitude (Up/Down):[/bold]
  • Positive: Moves tube up
  • Negative: Moves tube down

[bold]Azimuth (Left/Right):[/bold]
  • Positive: Moves tube right (east)
  • Negative: Moves tube left (west)

[bold]How to Set[/bold]

1. Access menu: Menu > Scope Setup > GoTo Approach

2. Set approach direction OPPOSITE to load direction:

   [bold]Altitude:[/bold]
   • If tube is heavy (accessories pull down): Use NEGATIVE
   • If tube is front-heavy: Use POSITIVE
   • [yellow]Default: Negative[/yellow] (for typical Schmidt-Cassegrain with accessories)

   [bold]Azimuth:[/bold]
   • When tracking west (normal): Use POSITIVE (same as tracking)
   • [yellow]Default: Positive[/yellow]

3. [bold]Important:[/bold] Use the SAME approach directions when aligning!
   Center alignment stars with the same final movements as GoTo approach.

[bold]For Equatorial Mounts:[/bold]

When using an equatorial wedge, you must change the GoTo Direction in
declination when you flip the scope to the opposite side of the mount
(meridian flip).

[bold]Southern Hemisphere:[/bold]

West is to the left, so reverse the azimuth settings.
"""
    console.print(Panel(info_text.strip(), border_style="cyan"))
    console.print()

    console.print("[bold yellow]Recommended Settings for NexStar 6SE/8SE:[/bold yellow]")
    console.print("  • Altitude: [bold]Negative[/bold] (tube heavy with accessories)")
    console.print("  • Azimuth: [bold]Positive[/bold] (tracking west)")
    console.print()
    console.print("[bold yellow]To Change Settings:[/bold yellow]")
    console.print("  Use hand control: Menu > Scope Setup > GoTo Approach")
    console.print()


@app.command("backlash-recommendations", rich_help_panel="Backlash Control")
def backlash_recommendations(
    mount_type: Literal["altaz", "eq"] = typer.Option("altaz", help="Mount type: altaz (AltAz) or eq (Equatorial)"),
    hemisphere: Literal["north", "south"] = typer.Option("north", help="Hemisphere: north or south"),
) -> None:
    """
    Get recommended backlash and GoTo approach settings for your setup.

    Provides recommendations based on mount type, hemisphere, and typical
    telescope configurations.

    Example:
        nexstar mount backlash-recommendations
        nexstar mount backlash-recommendations --mount-type eq --hemisphere north
    """
    console.print("\n[bold cyan]Recommended Backlash Settings[/bold cyan]\n")

    # Create recommendations table
    table = Table(title="Recommended Settings", show_header=True, header_style="bold magenta")
    table.add_column("Setting", style="bold")
    table.add_column("Value", justify="center")
    table.add_column("Notes", style="dim")

    if mount_type == "altaz":
        console.print("[bold]Mount Type:[/bold] Altitude-Azimuth (NexStar 6SE/8SE)")
        console.print(f"[bold]Hemisphere:[/bold] {hemisphere.capitalize()}\n")

        # AltAz recommendations
        table.add_row("Azimuth Positive", "50", "Start here, adjust based on testing")
        table.add_row("Azimuth Negative", "50", "Set same as Positive after calibration")
        table.add_row("Altitude Positive", "50", "Start here, adjust based on testing")
        table.add_row("Altitude Negative", "50", "Set same as Positive after calibration")

        console.print(table)
        console.print()

        # GoTo Approach recommendations
        console.print("[bold]GoTo Approach Settings:[/bold]")
        approach_table = Table(show_header=True, header_style="bold magenta")
        approach_table.add_column("Axis", style="bold")
        approach_table.add_column("Direction", justify="center")
        approach_table.add_column("Reason", style="dim")

        approach_table.add_row(
            "Altitude",
            "[bold]Negative[/bold]",
            "Tube heavy with accessories (diagonal, eyepiece, camera)",
        )
        if hemisphere == "north":
            approach_table.add_row("Azimuth", "[bold]Positive[/bold]", "Tracking west (normal direction)")
        else:
            approach_table.add_row("Azimuth", "[bold]Negative[/bold]", "Southern hemisphere (west is left)")

        console.print(approach_table)
        console.print()

    else:  # Equatorial
        console.print("[bold]Mount Type:[/bold] Equatorial (with wedge)")
        console.print(f"[bold]Hemisphere:[/bold] {hemisphere.capitalize()}\n")

        # EQ recommendations
        table.add_row("RA Positive", "50", "Start here, adjust based on testing")
        table.add_row("RA Negative", "50", "Set same as Positive after calibration")
        table.add_row("Dec Positive", "30-40", "Lower than RA (avoid overcorrection)")
        table.add_row("Dec Negative", "30-40", "Set same as Positive after calibration")

        console.print(table)
        console.print()

        # GoTo Approach recommendations for EQ
        console.print("[bold]GoTo Approach Settings:[/bold]")
        approach_table = Table(show_header=True, header_style="bold magenta")
        approach_table.add_column("Axis", style="bold")
        approach_table.add_column("Direction", justify="center")
        approach_table.add_column("Notes", style="dim")

        approach_table.add_row("RA", "[bold]Positive[/bold]", "Same as tracking direction")
        approach_table.add_row(
            "Dec",
            "[bold]Varies[/bold]",
            "Change when flipping across meridian (meridian flip)",
        )

        console.print(approach_table)
        console.print()

    console.print("[bold yellow]Calibration Tips:[/bold yellow]")
    console.print("  1. Start with recommended values (50 for AltAz, 30-40 for Dec)")
    console.print("  2. Test by slewing at rate 3+ for 10+ arc-minutes")
    console.print("  3. Observe field movement when releasing button")
    console.print("  4. Adjust down if overshoot, up if drift")
    console.print("  5. Set both Positive and Negative to same value when correct")
    console.print()

    console.print("[bold yellow]Important Notes:[/bold yellow]")
    console.print("  • These are starting values - fine-tune for your specific mount")
    console.print("  • Re-calibrate after adding/removing accessories")
    console.print("  • For astrophotography, backlash control is critical")
    console.print("  • Use same GoTo approach directions during alignment")
    console.print()


@app.command("backlash-test", rich_help_panel="Backlash Control")
def backlash_test(
    port: str | None = typer.Option(None, "--port", "-p", help="Serial port"),
    axis: Literal["azimuth", "altitude"] = typer.Option(..., help="Axis to test"),
    direction: Literal["positive", "negative"] = typer.Option(..., help="Direction to test"),
    rate: int = typer.Option(3, min=1, max=9, help="Slew rate (1-9, default 3)"),
    duration: float = typer.Option(10.0, help="Slew duration in seconds (default 10)"),
) -> None:
    """
    Test backlash by slewing in a direction and observing the result.

    This command helps you test your anti-backlash settings by automatically
    slewing the telescope and then stopping, allowing you to observe whether
    there's overshoot or drift.

    Example:
        nexstar mount backlash-test --axis azimuth --direction positive --rate 3 --duration 10
        nexstar mount backlash-test --axis altitude --direction negative --rate 5 --duration 15
    """
    try:
        telescope = ensure_connected(port)

        console.print("\n[bold cyan]Backlash Test[/bold cyan]\n")

        # Map axis and direction to movement commands
        axis_map = {
            ("azimuth", "positive"): ("right", "eastward"),
            ("azimuth", "negative"): ("left", "westward"),
            ("altitude", "positive"): ("up", "upward"),
            ("altitude", "negative"): ("down", "downward"),
        }

        move_dir, direction_name = axis_map.get((axis, direction), ("", ""))
        if not move_dir:
            print_error(f"Invalid axis/direction combination: {axis}/{direction}")
            raise typer.Exit(code=1) from None

        console.print(f"[bold]Testing:[/bold] {axis.capitalize()} {direction.capitalize()}")
        console.print(f"[bold]Direction:[/bold] {direction_name}")
        console.print(f"[bold]Rate:[/bold] {rate}")
        console.print(f"[bold]Duration:[/bold] {duration:.1f} seconds")
        console.print()

        console.print("[yellow]Instructions:[/yellow]")
        console.print("  1. Watch the field of view carefully")
        console.print("  2. When movement stops, observe what happens:")
        console.print("     • [red]Overshoot:[/red] Field jumps past target (anti-backlash too high)")
        console.print("     • [yellow]Drift:[/yellow] Field continues drifting (anti-backlash too low)")
        console.print("     • [green]Steady:[/green] Field stays put (anti-backlash correct!)")
        console.print()

        console.print("[bold]Starting test in 3 seconds...[/bold]")
        import time

        for i in range(3, 0, -1):
            console.print(f"  {i}...")
            time.sleep(1)

        # Start movement
        console.print(f"\n[bold green]Moving {direction_name} at rate {rate}...[/bold green]")
        success = telescope.move_fixed(move_dir, rate)
        if not success:
            print_error("Failed to start movement")
            raise typer.Exit(code=1) from None

        # Wait for duration
        time.sleep(duration)

        # Stop movement
        axis_code = "az" if axis == "azimuth" else "alt"
        telescope.stop_motion(axis_code)

        console.print("[bold]Movement stopped. Observe the field of view now.[/bold]")
        console.print()

        console.print("[bold]What to look for:[/bold]")
        console.print("  • [red]Overshoot:[/red] Reduce anti-backlash value by 10-20")
        console.print("  • [yellow]Drift:[/yellow] Increase anti-backlash value by 10-20")
        console.print("  • [green]Steady:[/green] Value is correct! Set opposite direction to same value")
        console.print()

        console.print("[yellow]Adjust settings in hand control:[/yellow]")
        console.print("  Menu > Scope Setup > Anti-Backlash")
        console.print()

    except Exception as e:
        print_error(f"Backlash test failed: {e}")
        raise typer.Exit(code=1) from None
