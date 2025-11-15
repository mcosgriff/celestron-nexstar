"""
Optics Commands

Commands for managing telescope and eyepiece optical configuration.
"""

import typer
from click import Context
from rich.prompt import Prompt
from rich.table import Table
from typer.core import TyperGroup

from celestron_nexstar.api.core.enums import SkyBrightness
from celestron_nexstar.api.observation.optics import (
    COMMON_EYEPIECES,
    EyepieceSpecs,
    OpticalConfiguration,
    TelescopeModel,
    TelescopeSpecs,
    calculate_dawes_limit_arcsec,
    calculate_limiting_magnitude,
    calculate_rayleigh_criterion_arcsec,
    get_current_configuration,
    get_telescope_specs,
    set_current_configuration,
)
from celestron_nexstar.cli.utils.output import console, print_error, print_info, print_json, print_success


class SortedCommandsGroup(TyperGroup):
    """Custom Typer group that sorts commands alphabetically within each help panel."""

    def list_commands(self, ctx: Context) -> list[str]:
        """Return commands sorted alphabetically."""
        commands = super().list_commands(ctx)
        return sorted(commands)


app = typer.Typer(help="Optical configuration commands", cls=SortedCommandsGroup)


@app.command("config", rich_help_panel="Configuration")
def configure(
    telescope: TelescopeModel | None = typer.Option(
        None,
        "--telescope",
        "-t",
        help="Telescope model (if not provided, will prompt interactively)",
    ),
    eyepiece_mm: float | None = typer.Option(
        None,
        "--eyepiece",
        "-e",
        help="Eyepiece focal length in mm (if not provided, will prompt interactively)",
    ),
    eyepiece_fov: float | None = typer.Option(
        None,
        "--fov",
        help="Eyepiece apparent field of view in degrees (auto-filled from common eyepieces if not provided)",
    ),
    eyepiece_name: str | None = typer.Option(
        None,
        "--name",
        help="Optional eyepiece name",
    ),
) -> None:
    """
    Configure telescope and eyepiece setup interactively.

    This configuration is used for calculating limiting magnitudes and
    filtering visible objects based on your actual equipment.

    If run without options, you'll be prompted to select from available
    telescopes and eyepieces interactively.

    Examples:
        # Interactive configuration
        nexstar optics config

        # Non-interactive with flags
        nexstar optics config --telescope nexstar_6se --eyepiece 25

        # Configure NexStar 8SE with 10mm ultra-wide
        nexstar optics config -t nexstar_8se -e 10 --fov 82 --name "10mm UW"
    """
    try:
        # Interactive telescope selection if not provided
        if telescope is None:
            telescope = _select_telescope_interactive()
            if telescope is None:
                print_info("Configuration cancelled")
                return

        # Get telescope specs
        telescope_specs = get_telescope_specs(telescope)

        # Interactive eyepiece selection if not provided
        if eyepiece_mm is None:
            eyepiece_specs = _select_eyepiece_interactive(telescope_specs)
            if eyepiece_specs is None:
                print_info("Configuration cancelled")
                return
        else:
            # Use provided eyepiece focal length
            # If FOV not provided, try to find it in COMMON_EYEPIECES
            if eyepiece_fov is None:
                # Look for matching eyepiece in COMMON_EYEPIECES
                matching_eyepiece = None
                for ep in COMMON_EYEPIECES.values():
                    if abs(ep.focal_length_mm - eyepiece_mm) < 0.1:
                        matching_eyepiece = ep
                        break

                if matching_eyepiece:
                    eyepiece_fov = matching_eyepiece.apparent_fov_deg
                    if not eyepiece_name:
                        eyepiece_name = matching_eyepiece.name
                else:
                    # Default to standard Plössl FOV
                    eyepiece_fov = 50.0

            # Create eyepiece specs
            eyepiece_specs = EyepieceSpecs(
                focal_length_mm=eyepiece_mm,
                apparent_fov_deg=eyepiece_fov,
                name=eyepiece_name or f"{eyepiece_mm}mm eyepiece",
            )

        # Create and save configuration
        config = OpticalConfiguration(
            telescope=telescope_specs,
            eyepiece=eyepiece_specs,
        )
        set_current_configuration(config, save=True)

        print_success("Optical configuration saved!")
        _display_configuration(config)

    except KeyboardInterrupt:
        print_info("\nConfiguration cancelled")
        raise typer.Exit(code=0) from None
    except Exception as e:
        print_error(f"Failed to configure optics: {e}")
        raise typer.Exit(code=1) from e


@app.command("show", rich_help_panel="Configuration")
def show_config(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """
    Show current optical configuration and calculated parameters.

    Displays telescope specs, eyepiece specs, magnification, field of view,
    exit pupil, and limiting magnitude estimates.

    Example:
        nexstar optics show
        nexstar optics show --json
    """
    try:
        config = get_current_configuration()

        if json_output:
            # Calculate limiting magnitude for different conditions
            conditions = [
                SkyBrightness.EXCELLENT,
                SkyBrightness.GOOD,
                SkyBrightness.FAIR,
                SkyBrightness.POOR,
                SkyBrightness.URBAN,
            ]
            limiting_mags = {
                condition.value: calculate_limiting_magnitude(
                    config.telescope.effective_aperture_mm,
                    sky_brightness=condition,
                    exit_pupil_mm=config.exit_pupil_mm,
                )
                for condition in conditions
            }

            print_json(
                {
                    "telescope": {
                        "model": config.telescope.model.value,
                        "display_name": config.telescope.display_name,
                        "aperture_mm": config.telescope.aperture_mm,
                        "aperture_inches": round(config.telescope.aperture_inches, 1),
                        "focal_length_mm": config.telescope.focal_length_mm,
                        "focal_ratio": config.telescope.focal_ratio,
                        "effective_aperture_mm": round(config.telescope.effective_aperture_mm, 1),
                        "light_gathering_power": round(config.telescope.light_gathering_power, 1),
                    },
                    "eyepiece": {
                        "name": config.eyepiece.name,
                        "focal_length_mm": config.eyepiece.focal_length_mm,
                        "apparent_fov_deg": config.eyepiece.apparent_fov_deg,
                    },
                    "performance": {
                        "magnification": round(config.magnification, 1),
                        "exit_pupil_mm": round(config.exit_pupil_mm, 2),
                        "true_fov_deg": round(config.true_fov_deg, 2),
                        "true_fov_arcmin": round(config.true_fov_arcmin, 1),
                        "dawes_limit_arcsec": round(calculate_dawes_limit_arcsec(config.telescope.aperture_mm), 2),
                        "rayleigh_criterion_arcsec": calculate_rayleigh_criterion_arcsec(config.telescope.aperture_mm),
                        "limiting_magnitude": limiting_mags,
                    },
                }
            )
        else:
            _display_configuration(config)

    except Exception as e:
        print_error(f"Failed to show configuration: {e}")
        raise typer.Exit(code=1) from e


@app.command("set-eyepiece", rich_help_panel="Configuration")
def set_eyepiece(
    focal_length_mm: float = typer.Argument(..., help="Eyepiece focal length in mm"),
    fov: float = typer.Option(50.0, "--fov", help="Apparent field of view in degrees"),
    name: str | None = typer.Option(None, "--name", help="Optional eyepiece name"),
) -> None:
    """
    Change the current eyepiece while keeping telescope configuration.

    Useful for quickly switching between eyepieces during an observing session.

    Examples:
        # Switch to 10mm eyepiece
        nexstar optics set-eyepiece 10

        # Switch to 9mm ultra-wide
        nexstar optics set-eyepiece 9 --fov 82 --name "9mm UW"
    """
    try:
        # Get current config
        current_config = get_current_configuration()

        # Create new eyepiece
        eyepiece = EyepieceSpecs(
            focal_length_mm=focal_length_mm,
            apparent_fov_deg=fov,
            name=name or f"{focal_length_mm}mm eyepiece",
        )

        # Create new config with same telescope
        new_config = OpticalConfiguration(
            telescope=current_config.telescope,
            eyepiece=eyepiece,
        )

        set_current_configuration(new_config, save=True)

        print_success(f"Eyepiece changed to {eyepiece.name}")
        _display_configuration(new_config)

    except Exception as e:
        print_error(f"Failed to set eyepiece: {e}")
        raise typer.Exit(code=1) from e


@app.command("telescopes", rich_help_panel="Reference Data")
def list_telescopes() -> None:
    """
    List all supported telescope models and their specifications.

    Example:
        nexstar optics telescopes
    """
    try:
        # Get current configuration to mark configured telescope
        current_config = get_current_configuration()
        current_model = current_config.telescope.model

        table = Table(
            title="Supported Telescope Models",
            show_header=True,
            header_style="bold magenta",
        )
        table.add_column("Model", style="cyan")
        table.add_column("Aperture", style="green")
        table.add_column("Focal Length", style="green")
        table.add_column("f-ratio", style="yellow")
        table.add_column("Resolution", style="blue")

        for model in TelescopeModel:
            specs = get_telescope_specs(model)
            dawes = calculate_dawes_limit_arcsec(specs.aperture_mm)

            # Add star indicator if this is the configured telescope
            model_name = specs.display_name
            if model == current_model:
                model_name = f"⭐ {model_name}"

            table.add_row(
                model_name,
                f'{specs.aperture_mm}mm ({specs.aperture_inches:.1f}")',
                f"{specs.focal_length_mm}mm",
                f"f/{specs.focal_ratio}",
                f"{dawes:.2f} arcsec",
            )

        console.print(table)
        print_info("Use 'nexstar optics config --telescope <model>' to select a telescope")

    except Exception as e:
        print_error(f"Failed to list telescopes: {e}")
        raise typer.Exit(code=1) from e


@app.command("eyepieces", rich_help_panel="Reference Data")
def list_eyepieces() -> None:
    """
    List common eyepiece configurations.

    Example:
        nexstar optics eyepieces
    """
    try:
        config = get_current_configuration()
        current_eyepiece = config.eyepiece

        table = Table(
            title=f"Common Eyepieces for {config.telescope.display_name}",
            show_header=True,
            header_style="bold magenta",
            expand=False,
        )
        table.add_column("Name", style="cyan", no_wrap=True, min_width=24)
        table.add_column("Focal Length", style="green", min_width=12)
        table.add_column("AFOV", style="yellow", min_width=6)
        table.add_column("Magnification", style="blue", min_width=14, no_wrap=True)
        table.add_column("Exit Pupil", style="blue", min_width=10)
        table.add_column("True FOV", style="green", min_width=9)

        for eyepiece in COMMON_EYEPIECES.values():
            mag = eyepiece.magnification(config.telescope)
            exit_pupil = eyepiece.exit_pupil_mm(config.telescope)
            tfov = eyepiece.true_fov_arcmin(config.telescope)

            # Check if this eyepiece matches the current configuration
            # Match by focal length and apparent FOV (within small tolerance)
            is_current = (
                abs(eyepiece.focal_length_mm - current_eyepiece.focal_length_mm) < 0.1
                and abs(eyepiece.apparent_fov_deg - current_eyepiece.apparent_fov_deg) < 0.1
            )

            eyepiece_name = eyepiece.name or f"{eyepiece.focal_length_mm}mm"
            if is_current:
                eyepiece_name = f"⭐ {eyepiece_name}"

            table.add_row(
                eyepiece_name,
                f"{eyepiece.focal_length_mm}mm",
                f"{eyepiece.apparent_fov_deg}°",
                f"{mag:.0f}x",
                f"{exit_pupil:.1f}mm",
                f"{tfov:.1f}'",
            )

        console.print(table)
        print_info("Use 'nexstar optics set-eyepiece <focal_length>' to select an eyepiece")

    except Exception as e:
        print_error(f"Failed to list eyepieces: {e}")
        raise typer.Exit(code=1) from e


@app.command("limiting-mag", rich_help_panel="Calculations")
def show_limiting_magnitude(
    sky_quality: str = typer.Option(
        "good",
        "--sky",
        "-s",
        show_choices=False,
        help="Sky quality: excellent, good, fair, poor, urban",
    ),
) -> None:
    """
    Calculate limiting magnitude for current configuration and sky conditions.

    The limiting magnitude is the faintest object you can theoretically see
    with your telescope under given conditions.

    Examples:
        nexstar optics limiting-mag
        nexstar optics limiting-mag --sky excellent
        nexstar optics limiting-mag --sky urban
    """
    try:
        config = get_current_configuration()

        # Validate sky quality and convert to enum
        try:
            sky_enum = SkyBrightness(sky_quality)
        except ValueError:
            valid_values = [e.value for e in SkyBrightness]
            print_error(f"Invalid sky quality. Must be one of: {', '.join(valid_values)}")
            raise typer.Exit(code=1) from None

        # Calculate for all conditions
        table = Table(
            title=f"Limiting Magnitude - {config.telescope.display_name} + {config.eyepiece.name}",
            show_header=True,
            header_style="bold magenta",
        )
        table.add_column("Sky Condition", style="cyan")
        table.add_column("Bortle Scale", style="yellow")
        table.add_column("Limiting Mag", style="green")

        conditions_info = {
            SkyBrightness.EXCELLENT: ("1-2", "Dark sky site"),
            SkyBrightness.GOOD: ("3-4", "Rural sky"),
            SkyBrightness.FAIR: ("5-6", "Suburban"),
            SkyBrightness.POOR: ("7-8", "Urban"),
            SkyBrightness.URBAN: ("9", "City center"),
        }

        for condition in SkyBrightness:
            limiting_mag = calculate_limiting_magnitude(
                config.telescope.effective_aperture_mm,
                sky_brightness=condition,
                exit_pupil_mm=config.exit_pupil_mm,
            )

            bortle, desc = conditions_info[condition]
            condition_display = f"{condition.value.title()} ({desc})"
            if condition == sky_enum:
                condition_display = f"[bold]{condition_display}[/bold]"
                mag_display = f"[bold green]{limiting_mag:.2f}[/bold green]"
            else:
                mag_display = f"{limiting_mag:.2f}"

            table.add_row(condition_display, bortle, mag_display)

        console.print(table)

        # Show comparison
        selected_mag = calculate_limiting_magnitude(
            config.telescope.effective_aperture_mm,
            sky_brightness=sky_enum,
            exit_pupil_mm=config.exit_pupil_mm,
        )

        print_info(f"With {sky_enum.value} sky conditions, you can see objects down to magnitude {selected_mag:.2f}")
        print_info(f"Current magnification: {config.magnification:.0f}x, Exit pupil: {config.exit_pupil_mm:.1f}mm")

    except Exception as e:
        print_error(f"Failed to calculate limiting magnitude: {e}")
        raise typer.Exit(code=1) from e


def _display_configuration(config: OpticalConfiguration) -> None:
    """Display optical configuration in a nice table format."""
    # Telescope info
    telescope_table = Table(
        title=f"[bold cyan]{config.telescope.display_name}[/bold cyan]",
        show_header=True,
        header_style="bold magenta",
    )
    telescope_table.add_column("Parameter", style="cyan")
    telescope_table.add_column("Value", style="green")

    telescope_table.add_row("Aperture", f'{config.telescope.aperture_mm}mm ({config.telescope.aperture_inches:.1f}")')
    telescope_table.add_row("Focal Length", f"{config.telescope.focal_length_mm}mm")
    telescope_table.add_row("Focal Ratio", f"f/{config.telescope.focal_ratio}")
    telescope_table.add_row(
        "Effective Aperture",
        f"{config.telescope.effective_aperture_mm:.1f}mm (with obstruction)",
    )
    telescope_table.add_row(
        "Light Gathering",
        f"{config.telescope.light_gathering_power:.0f}x naked eye",
    )
    telescope_table.add_row(
        "Resolution (Dawes)",
        f"{calculate_dawes_limit_arcsec(config.telescope.aperture_mm):.2f} arcsec",
    )

    console.print(telescope_table)
    console.print()

    # Eyepiece and performance
    performance_table = Table(
        title=f"[bold cyan]{config.eyepiece.name}[/bold cyan]",
        show_header=True,
        header_style="bold magenta",
    )
    performance_table.add_column("Parameter", style="cyan")
    performance_table.add_column("Value", style="green")

    performance_table.add_row("Focal Length", f"{config.eyepiece.focal_length_mm}mm")
    performance_table.add_row("Apparent FOV", f"{config.eyepiece.apparent_fov_deg}°")
    performance_table.add_row("Magnification", f"{config.magnification:.0f}x")
    performance_table.add_row("Exit Pupil", f"{config.exit_pupil_mm:.1f}mm")
    performance_table.add_row("True FOV", f"{config.true_fov_deg:.2f}° ({config.true_fov_arcmin:.1f}')")

    # Add limiting magnitude for typical conditions
    good_sky_mag = calculate_limiting_magnitude(
        config.telescope.effective_aperture_mm,
        sky_brightness=SkyBrightness.GOOD,
        exit_pupil_mm=config.exit_pupil_mm,
    )
    performance_table.add_row("Limiting Mag (good sky)", f"{good_sky_mag:.2f}")

    console.print(performance_table)


def _select_telescope_interactive() -> TelescopeModel | None:
    """Interactively select a telescope model."""
    try:
        current_config = get_current_configuration()
        current_model = current_config.telescope.model
    except Exception:
        current_model = None

    console.print("\n[bold cyan]Select Telescope Model:[/bold cyan]\n")

    # Create table of available telescopes
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", style="cyan", justify="right")
    table.add_column("Model", style="cyan")
    table.add_column("Aperture", style="green")
    table.add_column("Focal Length", style="green")
    table.add_column("f-ratio", style="yellow")

    telescope_models = list(TelescopeModel)
    for i, model in enumerate(telescope_models, 1):
        specs = get_telescope_specs(model)
        # Use fixed-width format: always reserve 2 chars for indicator (asterisk + space, or 2 spaces)
        marker = "* " if model == current_model else "  "
        if model == current_model:
            model_name = f"[bold]{marker}{specs.display_name}[/bold]"
        else:
            model_name = f"{marker}{specs.display_name}"

        table.add_row(
            str(i),
            model_name,
            f'{specs.aperture_mm}mm ({specs.aperture_inches:.1f}")',
            f"{specs.focal_length_mm}mm",
            f"f/{specs.focal_ratio}",
        )

    console.print(table)
    console.print()

    # Prompt for selection
    while True:
        try:
            choice = Prompt.ask(
                "[cyan]Select telescope number (or 'q' to cancel)[/cyan]",
                default="1" if current_model else None,
            )

            if choice is None:
                return None

            if choice.lower() in ["q", "quit", "cancel", "exit"]:
                return None

            idx = int(choice) - 1
            if 0 <= idx < len(telescope_models):
                selected = telescope_models[idx]
                console.print(f"[green]Selected:[/green] {get_telescope_specs(selected).display_name}")
                return selected
            else:
                console.print(f"[red]Invalid selection. Please enter 1-{len(telescope_models)}[/red]")

        except ValueError:
            console.print("[red]Invalid input. Please enter a number or 'q' to cancel[/red]")
        except KeyboardInterrupt:
            return None


def _select_eyepiece_interactive(telescope_specs: TelescopeSpecs) -> EyepieceSpecs | None:
    """Interactively select an eyepiece."""
    try:
        current_config = get_current_configuration()
        current_eyepiece = current_config.eyepiece
    except Exception:
        current_eyepiece = None

    console.print("\n[bold cyan]Select Eyepiece:[/bold cyan]\n")

    # Show common eyepieces in a table
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", style="cyan", justify="right")
    table.add_column("Name", style="cyan")
    table.add_column("Focal Length", style="green")
    table.add_column("FOV", style="yellow")
    table.add_column("Magnification", style="blue")
    table.add_column("True FOV", style="green")

    eyepiece_list = list(COMMON_EYEPIECES.values())
    for i, eyepiece in enumerate(eyepiece_list, 1):
        mag = eyepiece.magnification(telescope_specs)
        tfov = eyepiece.true_fov_arcmin(telescope_specs)

        # Check if this matches current eyepiece
        is_current = False
        if current_eyepiece:
            is_current = (
                abs(eyepiece.focal_length_mm - current_eyepiece.focal_length_mm) < 0.1
                and abs(eyepiece.apparent_fov_deg - current_eyepiece.apparent_fov_deg) < 0.1
            )

        # Use fixed-width format: always reserve 2 chars for indicator (asterisk + space, or 2 spaces)
        marker = "* " if is_current else "  "
        name = f"[bold]{marker}{eyepiece.name}[/bold]" if is_current else f"{marker}{eyepiece.name}"

        table.add_row(
            str(i),
            name,
            f"{eyepiece.focal_length_mm}mm",
            f"{eyepiece.apparent_fov_deg}°",
            f"{mag:.0f}x",
            f"{tfov:.1f}'",
        )

    console.print(table)
    console.print()

    # Prompt for selection
    while True:
        try:
            choice = Prompt.ask(
                "[cyan]Select eyepiece number, 'c' for custom, or 'q' to cancel[/cyan]",
                default=None,
            )

            if choice is None:
                return None

            if choice.lower() in ["q", "quit", "cancel", "exit"]:
                return None

            if choice.lower() in ["c", "custom"]:
                return _create_custom_eyepiece()

            idx = int(choice) - 1
            if 0 <= idx < len(eyepiece_list):
                selected = eyepiece_list[idx]
                console.print(f"[green]Selected:[/green] {selected.name}")
                return selected
            else:
                console.print(f"[red]Invalid selection. Please enter 1-{len(eyepiece_list)}, 'c', or 'q'[/red]")

        except ValueError:
            console.print("[red]Invalid input. Please enter a number, 'c' for custom, or 'q' to cancel[/red]")
        except KeyboardInterrupt:
            return None


def _create_custom_eyepiece() -> EyepieceSpecs | None:
    """Prompt user to create a custom eyepiece."""
    console.print("\n[bold cyan]Custom Eyepiece Configuration:[/bold cyan]\n")

    try:
        # Get focal length
        while True:
            focal_length_str = Prompt.ask("[cyan]Focal length (mm)[/cyan]")
            try:
                focal_length = float(focal_length_str)
                if focal_length > 0:
                    break
                console.print("[red]Focal length must be positive[/red]")
            except ValueError:
                console.print("[red]Invalid number. Please enter a valid focal length in mm[/red]")

        # Get FOV
        while True:
            fov_str = Prompt.ask(
                "[cyan]Apparent field of view (degrees)[/cyan]",
                default="50.0",
            )
            try:
                fov = float(fov_str)
                if 0 < fov <= 120:
                    break
                console.print("[red]FOV must be between 0 and 120 degrees[/red]")
            except ValueError:
                console.print("[red]Invalid number. Please enter a valid FOV in degrees[/red]")

        # Get optional name
        name = Prompt.ask(
            "[cyan]Eyepiece name (optional)[/cyan]",
            default=f"{focal_length}mm eyepiece",
        )

        eyepiece = EyepieceSpecs(
            focal_length_mm=focal_length,
            apparent_fov_deg=fov,
            name=name,
        )

        console.print(f"[green]Created custom eyepiece:[/green] {eyepiece.name}")
        return eyepiece

    except KeyboardInterrupt:
        return None
