"""
Location Commands

Commands for managing observer location.
"""

import asyncio

import typer
from click import Context
from rich.table import Table
from typer.core import TyperGroup

from celestron_nexstar.api.core.exceptions import (
    GeocodingError,
    LocationNotFoundError,
    LocationNotSetError,
)
from celestron_nexstar.api.location.observer import (
    ObserverLocation,
    detect_location_automatically,
    geocode_location,
    get_observer_location,
    set_observer_location,
)
from celestron_nexstar.cli.utils.output import console, print_error, print_info, print_json, print_success
from celestron_nexstar.cli.utils.state import ensure_connected


class SortedCommandsGroup(TyperGroup):
    """Custom Typer group that sorts commands alphabetically within each help panel."""

    def list_commands(self, ctx: Context) -> list[str]:
        """Return commands sorted alphabetically."""
        commands = super().list_commands(ctx)
        return sorted(commands)


app = typer.Typer(help="Observer location commands", cls=SortedCommandsGroup)


@app.command("set", rich_help_panel="Telescope Location")
def set_location(
    port: str | None = typer.Option(None, "--port", "-p", help="Serial port"),
    latitude: float = typer.Option(..., "--lat", help="Latitude in degrees (-90 to +90, North is positive)"),
    longitude: float = typer.Option(..., "--lon", help="Longitude in degrees (-180 to +180, East is positive)"),
) -> None:
    """
    Set observer location (latitude and longitude).

    The telescope uses this information for accurate tracking and coordinate
    conversions between horizontal and equatorial systems.

    Example:
        # New York City
        nexstar location set --lat 40.7128 --lon -74.0060

        # London
        nexstar location set --lat 51.5074 --lon -0.1278

        # Tokyo
        nexstar location set --lat 35.6762 --lon 139.6503
    """
    # Validate coordinates
    if not -90 <= latitude <= 90:
        print_error("Latitude must be between -90 and +90 degrees")
        raise typer.Exit(code=1) from None
    if not -180 <= longitude <= 180:
        print_error("Longitude must be between -180 and +180 degrees")
        raise typer.Exit(code=1) from None

    try:
        telescope = ensure_connected()

        print_info(f"Setting location to {latitude:.4f}°, {longitude:.4f}°")

        success = telescope.set_location(latitude, longitude)
        if success:
            # Format location nicely
            lat_dir = "N" if latitude >= 0 else "S"
            lon_dir = "E" if longitude >= 0 else "W"
            print_success(f"Location set to {abs(latitude):.4f}°{lat_dir}, {abs(longitude):.4f}°{lon_dir}")
        else:
            print_error("Failed to set location")
            raise typer.Exit(code=1) from None

    except Exception as e:
        print_error(f"Failed to set location: {e}")
        raise typer.Exit(code=1) from e


@app.command("get", rich_help_panel="Telescope Location")
def get_location(
    port: str | None = typer.Option(None, "--port", "-p", help="Serial port"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """
    Get current observer location from telescope.

    Example:
        nexstar location get
        nexstar location get --json
    """
    try:
        telescope = ensure_connected()

        location = telescope.get_location()

        if json_output:
            lat_dir = "N" if location.latitude >= 0 else "S"
            lon_dir = "E" if location.longitude >= 0 else "W"
            print_json(
                {
                    "latitude": location.latitude,
                    "longitude": location.longitude,
                    "latitude_formatted": f"{abs(location.latitude):.4f}°{lat_dir}",
                    "longitude_formatted": f"{abs(location.longitude):.4f}°{lon_dir}",
                }
            )
        else:
            # Create a nice table
            table = Table(title="Observer Location", show_header=True, header_style="bold magenta")
            table.add_column("Parameter", style="cyan")
            table.add_column("Value", style="green")

            lat_dir = "N" if location.latitude >= 0 else "S"
            lon_dir = "E" if location.longitude >= 0 else "W"

            table.add_row("Latitude", f"{abs(location.latitude):.4f}°{lat_dir} ({location.latitude:+.4f}°)")
            table.add_row("Longitude", f"{abs(location.longitude):.4f}°{lon_dir} ({location.longitude:+.4f}°)")

            console.print(table)

    except Exception as e:
        print_error(f"Failed to get location: {e}")
        raise typer.Exit(code=1) from e


@app.command("set-observer", rich_help_panel="Observer Location")
def set_observer(
    location: str | None = typer.Argument(None, help="City, address, or ZIP code (e.g., 'New York, NY', '90210')"),
    latitude: float | None = typer.Option(None, "--lat", help="Latitude in degrees (-90 to +90)"),
    longitude: float | None = typer.Option(None, "--lon", help="Longitude in degrees (-180 to +180)"),
    elevation: float = typer.Option(0.0, "--elev", help="Elevation in meters above sea level"),
    name: str | None = typer.Option(None, "--name", help="Optional location name"),
) -> None:
    """
    Set CLI observer location for planetary position calculations.

    You can specify location by:
    1. City/address/ZIP code (geocoded automatically)
    2. Explicit lat/lon coordinates

    This location is used for calculating accurate positions of planets and moons.
    It's separate from the telescope's location setting.

    Examples:
        # By city name
        nexstar location set-observer "New York, NY"
        nexstar location set-observer "London, UK"

        # By ZIP code
        nexstar location set-observer 90210

        # By coordinates
        nexstar location set-observer --lat 40.7128 --lon -74.0060 --name "New York"
    """
    try:
        # Option 1: Geocode from city/address/ZIP
        if location:
            print_info(f"Geocoding location: {location}")
            observer_loc = asyncio.run(geocode_location(location))
            print_success(f"Found: {observer_loc.name}")

        # Option 2: Use explicit coordinates
        elif latitude is not None and longitude is not None:
            if not -90 <= latitude <= 90:
                print_error("Latitude must be between -90 and +90 degrees")
                raise typer.Exit(code=1) from None
            if not -180 <= longitude <= 180:
                print_error("Longitude must be between -180 and +180 degrees")
                raise typer.Exit(code=1) from None

            observer_loc = ObserverLocation(latitude=latitude, longitude=longitude, elevation=elevation, name=name)
        else:
            print_error("Must provide either a location query or --lat and --lon")
            print_info("Examples:")
            print_info('  nexstar location set-observer "New York, NY"')
            print_info("  nexstar location set-observer --lat 40.7128 --lon -74.0060")
            raise typer.Exit(code=1) from None

        # Save the location
        set_observer_location(observer_loc, save=True)

        # Display confirmation
        lat_dir = "N" if observer_loc.latitude >= 0 else "S"
        lon_dir = "E" if observer_loc.longitude >= 0 else "W"

        print_success("Observer location set!")
        table = Table(show_header=False)
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="green")

        if observer_loc.name:
            table.add_row("Location", observer_loc.name)
        table.add_row("Latitude", f"{abs(observer_loc.latitude):.4f}°{lat_dir}")
        table.add_row("Longitude", f"{abs(observer_loc.longitude):.4f}°{lon_dir}")
        if observer_loc.elevation:
            table.add_row("Elevation", f"{observer_loc.elevation:.0f} m")

        console.print(table)
        print_info("This location will be used for planetary position calculations")

    except (GeocodingError, LocationNotFoundError) as e:
        print_error(str(e))
        raise typer.Exit(code=1) from e
    except Exception as e:
        print_error(f"Failed to set observer location: {e}")
        raise typer.Exit(code=1) from e


@app.command("get-observer", rich_help_panel="Observer Location")
def get_observer(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """
    Get current CLI observer location for ephemeris calculations.

    This is the location used for calculating planetary positions, separate
    from the telescope's internal location setting.

    Example:
        nexstar location get-observer
        nexstar location get-observer --json
    """
    try:
        observer_loc = get_observer_location()

        if json_output:
            lat_dir = "N" if observer_loc.latitude >= 0 else "S"
            lon_dir = "E" if observer_loc.longitude >= 0 else "W"
            print_json(
                {
                    "latitude": observer_loc.latitude,
                    "longitude": observer_loc.longitude,
                    "elevation": observer_loc.elevation,
                    "name": observer_loc.name,
                    "latitude_formatted": f"{abs(observer_loc.latitude):.4f}°{lat_dir}",
                    "longitude_formatted": f"{abs(observer_loc.longitude):.4f}°{lon_dir}",
                }
            )
        else:
            # Create a nice table
            table = Table(title="CLI Observer Location", show_header=True, header_style="bold magenta")
            table.add_column("Parameter", style="cyan")
            table.add_column("Value", style="green")

            if observer_loc.name:
                table.add_row("Location", observer_loc.name)

            lat_dir = "N" if observer_loc.latitude >= 0 else "S"
            lon_dir = "E" if observer_loc.longitude >= 0 else "W"

            table.add_row("Latitude", f"{abs(observer_loc.latitude):.4f}°{lat_dir}")
            table.add_row("Longitude", f"{abs(observer_loc.longitude):.4f}°{lon_dir}")

            if observer_loc.elevation:
                table.add_row("Elevation", f"{observer_loc.elevation:.0f} m above sea level")

            console.print(table)
            print_info("Used for planetary position calculations")

    except Exception as e:
        print_error(f"Failed to get observer location: {e}")
        raise typer.Exit(code=1) from e


@app.command("detect", rich_help_panel="Observer Location")
def detect_location(
    save: bool = typer.Option(True, "--save/--no-save", help="Save detected location to config"),
) -> None:
    """
    Automatically detect your location.

    Tries multiple methods:
    1. System location services (GPS, if available and permitted)
    2. IP-based geolocation (fallback, less accurate)

    This will prompt you for permission before accessing location services.

    Examples:
        nexstar location detect
        nexstar location detect --no-save  # Detect but don't save
    """
    try:
        console.print("\n[cyan]Detecting your location...[/cyan]\n")
        console.print(
            "[dim]This may use your IP address or system location services (if available and permitted).[/dim]\n"
        )

        detected = asyncio.run(detect_location_automatically())

        # Display results
        lat_dir = "N" if detected.latitude >= 0 else "S"
        lon_dir = "E" if detected.longitude >= 0 else "W"

        print_success("Location detected!")
        table = Table(show_header=False)
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="green")

        if detected.name:
            table.add_row("Location", detected.name)
        table.add_row("Latitude", f"{abs(detected.latitude):.4f}°{lat_dir}")
        table.add_row("Longitude", f"{abs(detected.longitude):.4f}°{lon_dir}")
        if detected.elevation:
            table.add_row("Elevation", f"{detected.elevation:.0f} m")

        console.print(table)

        if save:
            set_observer_location(detected, save=True)
            print_success("\nLocation saved to config!")
        else:
            print_info("\nLocation not saved. Use --save to save it.")

    except LocationNotSetError as e:
        print_error(str(e))
        print_info("\nYou can set your location manually:")
        print_info('  nexstar location set-observer "City, State"')
        print_info("  nexstar location set-observer --lat 40.7128 --lon -74.0060")
        raise typer.Exit(code=1) from e
    except Exception as e:
        print_error(f"Failed to detect location: {e}")
        raise typer.Exit(code=1) from e
