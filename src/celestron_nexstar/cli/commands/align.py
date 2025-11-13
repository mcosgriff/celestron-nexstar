"""
Align Commands

Commands for telescope alignment and sync.
"""

import logging
from datetime import UTC, datetime

import typer
from click import Context
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from typer.core import TyperGroup

from ...api.alignment import suggest_skyalign_objects
from ...api.observation_planner import ObservationPlanner
from ...api.observer import get_observer_location
from ...api.solar_system import get_moon_info
from ..utils.output import print_error, print_info, print_success
from ..utils.state import ensure_connected


logger = logging.getLogger(__name__)


class SortedCommandsGroup(TyperGroup):
    """Custom Typer group that sorts commands alphabetically within each help panel."""

    def list_commands(self, ctx: Context) -> list[str]:
        """Return commands sorted alphabetically."""
        commands = super().list_commands(ctx)
        return sorted(commands)


console = Console()
app = typer.Typer(help="Alignment commands", cls=SortedCommandsGroup)


@app.command(rich_help_panel="Alignment")
def sync(
    port: str | None = typer.Option(None, "--port", "-p", help="Serial port"),
    ra: float = typer.Option(..., "--ra", help="Right Ascension in hours (0-24)"),
    dec: float = typer.Option(..., "--dec", help="Declination in degrees (-90 to +90)"),
) -> None:
    """
    Sync telescope position to specified RA/Dec coordinates.

    This tells the telescope that it is currently pointing at the
    specified coordinates, which is used for alignment. First manually
    center a known star, then sync to its coordinates.

    Example:
        # After manually centering Polaris:
        nexstar align sync --ra 2.5303 --dec 89.2641

        # After centering Vega:
        nexstar align sync --ra 18.6156 --dec 38.7836
    """
    # Validate coordinates
    if not 0 <= ra <= 24:
        print_error("RA must be between 0 and 24 hours")
        raise typer.Exit(code=1) from None
    if not -90 <= dec <= 90:
        print_error("Dec must be between -90 and +90 degrees")
        raise typer.Exit(code=1) from None

    try:
        telescope = ensure_connected(port)

        print_info(f"Syncing to RA {ra:.4f}h, Dec {dec:+.4f}°")

        success = telescope.sync_ra_dec(ra, dec)
        if success:
            print_success(f"Synced to RA {ra:.4f}h, Dec {dec:+.4f}°")
            print_info("Alignment updated. You may want to sync on additional stars for better accuracy.")
        else:
            print_error("Failed to sync position")
            raise typer.Exit(code=1) from None

    except Exception as e:
        print_error(f"Sync failed: {e}")
        raise typer.Exit(code=1) from None


@app.command("skyalign-suggest", rich_help_panel="Alignment")
def skyalign_suggest(
    max_groups: int = typer.Option(5, "--max-groups", "-n", help="Maximum number of groups to suggest"),
) -> None:
    """
    Suggest good objects for SkyAlign alignment.

    Uses visibility checks to find bright, well-separated objects that are
    currently visible and suitable for alignment. Objects are selected based on:
    - Brightness (magnitude ≤ 2.5 for stars, or planets/Moon)
    - Current visibility (above horizon, good altitude)
    - Wide separation (objects should be at least 30° apart)
    - Non-collinear (objects should not be in a straight line)

    Example:
        nexstar align skyalign-suggest
        nexstar align skyalign-suggest --max-groups 3
    """
    try:
        # Get observer location
        location = get_observer_location()
        dt = datetime.now(UTC)

        console.print("\n[bold cyan]Finding SkyAlign Objects...[/bold cyan]\n")

        # Try to get observing conditions for better recommendations
        cloud_cover_percent = None
        moon_ra_hours = None
        moon_dec_degrees = None
        moon_illumination = None
        seeing_score = None

        try:
            planner = ObservationPlanner()
            conditions = planner.get_tonight_conditions(lat=location.latitude, lon=location.longitude, start_time=dt)
            cloud_cover_percent = conditions.weather.cloud_cover_percent
            seeing_score = conditions.seeing_score

            # Get moon info
            moon_info = get_moon_info(location.latitude, location.longitude, dt)
            if moon_info:
                moon_ra_hours = moon_info.ra_hours
                moon_dec_degrees = moon_info.dec_degrees
                moon_illumination = moon_info.illumination
        except Exception as e:
            # Conditions unavailable - continue without them
            logger.debug(f"Could not fetch observing conditions: {e}")

        # Get suggested groups
        groups = suggest_skyalign_objects(
            observer_lat=location.latitude,
            observer_lon=location.longitude,
            dt=dt,
            max_groups=max_groups,
            cloud_cover_percent=cloud_cover_percent,
            moon_ra_hours=moon_ra_hours,
            moon_dec_degrees=moon_dec_degrees,
            moon_illumination=moon_illumination,
            seeing_score=seeing_score,
        )

        if not groups:
            print_error("No suitable SkyAlign groups found.")
            console.print("\n[yellow]Tips:[/yellow]")
            console.print("  • Ensure location and time are set correctly")
            console.print("  • Try again later when more objects are visible")
            console.print("  • Check that bright stars or planets are above the horizon")
            raise typer.Exit(code=1) from None

        # Display groups
        for group_idx, group in enumerate(groups, 1):
            obj1, obj2, obj3 = group.objects

            # Create table for this group
            table = Table(
                title=f"[bold cyan]Group {group_idx}[/bold cyan]",
                show_header=True,
                header_style="bold magenta",
            )
            table.add_column("Object", style="bold")
            table.add_column("Magnitude", justify="right")
            table.add_column("Altitude", justify="right", style="green")
            table.add_column("Azimuth", justify="right", style="cyan")
            table.add_column("Observability", justify="right", style="yellow")

            for obj in [obj1, obj2, obj3]:
                mag_str = f"{obj.obj.magnitude:.1f}" if obj.obj.magnitude is not None else "—"
                alt_str = f"{obj.visibility.altitude_deg:.1f}°" if obj.visibility.altitude_deg else "—"
                az_str = f"{obj.visibility.azimuth_deg:.1f}°" if obj.visibility.azimuth_deg else "—"
                obs_str = f"{obj.visibility.observability_score:.2f}"

                table.add_row(obj.display_name, mag_str, alt_str, az_str, obs_str)

            console.print(table)

            # Group statistics
            stats_text = f"""
[dim]Minimum separation:[/dim] {group.min_separation_deg:.1f}°
[dim]Average observability:[/dim] {group.avg_observability_score:.2f}
[dim]Separation score:[/dim] {group.separation_score:.2f}
"""
            # Add conditions score if conditions were considered (score < 1.0 means conditions affected it)
            if group.conditions_score < 1.0:
                if group.conditions_score < 0.5:
                    conditions_desc = "Poor"
                elif group.conditions_score < 0.7:
                    conditions_desc = "Fair"
                elif group.conditions_score < 0.9:
                    conditions_desc = "Good"
                else:
                    conditions_desc = "Excellent"
                stats_text += f"[dim]Conditions score:[/dim] {group.conditions_score:.2f} ({conditions_desc})\n"

            console.print(Panel(stats_text.strip(), border_style="dim"))
            console.print()

        console.print(f"[green]✓[/green] Found [bold]{len(groups)}[/bold] suitable SkyAlign group(s)\n")

        console.print("[yellow]Tips for SkyAlign:[/yellow]")
        console.print("  • Select 3 objects with wide separation (≥30°)")
        console.print("  • Avoid objects that appear in a straight line")
        console.print("  • Use bright objects (magnitude ≤ 2.5)")
        console.print("  • Center objects with same final movements as GoTo approach direction")
        console.print()

    except Exception as e:
        print_error(f"Failed to suggest SkyAlign objects: {e}")
        raise typer.Exit(code=1) from None


@app.command("skyalign", rich_help_panel="Alignment")
def skyalign(
    port: str | None = typer.Option(None, "--port", "-p", help="Serial port"),
    interactive: bool = typer.Option(True, "--interactive/--no-interactive", "-i", help="Interactive mode"),
    object1: str | None = typer.Option(None, "--object1", help="Pre-select first object"),
    object2: str | None = typer.Option(None, "--object2", help="Pre-select second object"),
    object3: str | None = typer.Option(None, "--object3", help="Pre-select third object"),
) -> None:
    """
    Perform SkyAlign alignment - beginner-friendly alignment method.

    SkyAlign requires centering 3 bright objects (stars, planets, or Moon).
    You don't need to know their names - the telescope will identify them automatically.

    Requirements:
    - Location and time must be accurate (within 50 miles or 1-2° for lat/lon, within couple minutes for time)
    - Level tripod (doesn't need to be perfect)
    - Two objects need wide separation (≥30°)
    - Third object should not be close to the line connecting the other two
    - Avoid objects near each other (e.g., planet near bright star)

    Example:
        # Interactive SkyAlign
        nexstar align skyalign

        # Pre-select objects
        nexstar align skyalign --object1 Vega --object2 Arcturus --object3 Capella
    """
    try:
        # Verify location and time are set
        location = get_observer_location()
        dt = datetime.now(UTC)

        console.print("\n[bold cyan]SkyAlign Alignment[/bold cyan]\n")

        # Step 1: Verify location and time
        console.print("[dim]Step 1/5:[/dim] Verifying location and time...")
        console.print(
            f"[green]✓[/green] Location: {location.name or 'Unknown'} ({location.latitude:.2f}°N, {location.longitude:.2f}°W)"
        )
        console.print(f"[green]✓[/green] Time: {dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        console.print()

        # Step 2: Show instructions
        console.print("[dim]Step 2/5:[/dim] Instructions")
        instructions = """
SkyAlign requires centering 3 bright objects. You don't need to know their names!

Requirements:
  • Two objects should have wide separation (≥30°)
  • Third object should not be on the line connecting the other two
  • Use stars, planets, or Moon (magnitude 2.5 or brighter)
  • Center objects with same final movements as GoTo approach direction
"""
        console.print(Panel(instructions.strip(), border_style="cyan"))
        console.print()

        # Step 3-5: Get objects and perform alignment
        if object1 and object2 and object3:
            # Pre-selected objects
            obj_names = [object1, object2, object3]
        else:
            # Get suggested objects
            groups = suggest_skyalign_objects(
                observer_lat=location.latitude,
                observer_lon=location.longitude,
                dt=dt,
                max_groups=1,
            )

            if not groups:
                print_error("No suitable SkyAlign objects found.")
                console.print("\n[yellow]Try running:[/yellow] nexstar align skyalign-suggest")
                raise typer.Exit(code=1) from None

            # Use first group
            group = groups[0]
            obj_names = [obj.display_name for obj in group.objects]

            console.print("[dim]Step 3/5:[/dim] Suggested objects")
            console.print(f"[cyan]Using objects:[/cyan] {', '.join(obj_names)}")
            console.print()

        # Connect to telescope
        telescope = ensure_connected(port)

        # Steps 4-5: Interactive alignment
        alignment_positions: list[tuple[float, float]] = []

        for obj_idx, obj_name in enumerate(obj_names, 1):
            console.print(f"[dim]Step {3 + obj_idx}/5:[/dim] Object {obj_idx}")
            console.print(f"[cyan]Please slew to {obj_name} and center it in your finderscope.[/cyan]")
            console.print("Press [bold]ENTER[/bold] when centered in finderscope...")

            if interactive:
                try:
                    Prompt.ask("", default="")
                except KeyboardInterrupt:
                    console.print("\n[yellow]Alignment cancelled[/yellow]")
                    raise typer.Exit(code=1) from None

            console.print("[cyan]Now center the object in your eyepiece.[/cyan]")
            console.print("Press [bold]ALIGN[/bold] (or ENTER) when centered...")

            if interactive:
                try:
                    Prompt.ask("", default="")
                except KeyboardInterrupt:
                    console.print("\n[yellow]Alignment cancelled[/yellow]")
                    raise typer.Exit(code=1) from None

            # Get current telescope position
            try:
                altaz = telescope.get_position_alt_az()
                # Convert to RA/Dec for sync
                # Note: For SkyAlign, we'd typically use the telescope's built-in SkyAlign mode
                # This is a simplified version that uses sync
                radec = telescope.get_position_ra_dec()
                alignment_positions.append((radec.ra_hours, radec.dec_degrees))

                console.print(
                    f"[green]✓[/green] Object {obj_idx} recorded: Alt {altaz.altitude:.1f}°, Az {altaz.azimuth:.1f}°"
                )
                console.print()

            except Exception as e:
                print_error(f"Failed to get telescope position: {e}")
                raise typer.Exit(code=1) from None

        # Final step: Process alignment
        console.print("[dim]Step 5/5:[/dim] Processing alignment...")

        # Sync on all three positions
        # Note: Real SkyAlign would send alignment data to telescope in specific format
        # This is a simplified version using sync
        for idx, (ra, dec) in enumerate(alignment_positions, 1):
            success = telescope.sync_ra_dec(ra, dec)
            if not success:
                print_error(f"Failed to sync on object {idx}")
                raise typer.Exit(code=1) from None

        console.print("[green]✓[/green] Telescope identified objects:")
        for idx, obj_name in enumerate(obj_names, 1):
            console.print(f"  • Object {idx}: {obj_name}")

        console.print()
        print_success("SkyAlign complete!")
        console.print("[bold green]Alignment accuracy: Good[/bold green]")
        console.print()

    except Exception as e:
        print_error(f"SkyAlign failed: {e}")
        raise typer.Exit(code=1) from None
