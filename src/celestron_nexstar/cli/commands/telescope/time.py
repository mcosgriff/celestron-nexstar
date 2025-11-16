"""
Time Commands

Commands for managing telescope date and time.
"""

from datetime import datetime

import typer
from click import Context
from rich.table import Table
from typer.core import TyperGroup

from celestron_nexstar.cli.utils.output import console, print_error, print_info, print_json, print_success
from celestron_nexstar.cli.utils.state import ensure_connected


class SortedCommandsGroup(TyperGroup):
    """Custom Typer group that sorts commands alphabetically within each help panel."""

    def list_commands(self, ctx: Context) -> list[str]:
        """Return commands sorted alphabetically."""
        commands = super().list_commands(ctx)
        return sorted(commands)


app = typer.Typer(help="Time and date commands", cls=SortedCommandsGroup)


@app.command("get", rich_help_panel="Query")
def get_time(
    port: str | None = typer.Option(None, "--port", "-p", help="Serial port"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """
    Get current date and time from telescope.

    Example:
        nexstar time get
        nexstar time get --json
    """
    try:
        telescope = ensure_connected()

        time_info = telescope.get_time()

        if json_output:
            print_json(
                {
                    "year": time_info.year,
                    "month": time_info.month,
                    "day": time_info.day,
                    "hour": time_info.hour,
                    "minute": time_info.minute,
                    "second": time_info.second,
                    "timezone": time_info.timezone,
                    "daylight_savings": time_info.daylight_savings,
                    "formatted": f"{time_info.year}-{time_info.month:02d}-{time_info.day:02d} "
                    f"{time_info.hour:02d}:{time_info.minute:02d}:{time_info.second:02d}",
                }
            )
        else:
            # Create a nice table
            table = Table(title="Telescope Time", show_header=True, header_style="bold magenta")
            table.add_column("Parameter", style="cyan")
            table.add_column("Value", style="green")

            table.add_row("Date", f"{time_info.year}-{time_info.month:02d}-{time_info.day:02d}")
            table.add_row("Time", f"{time_info.hour:02d}:{time_info.minute:02d}:{time_info.second:02d}")
            table.add_row("Timezone Offset", f"{time_info.timezone:+d} hours from GMT")
            table.add_row("Daylight Savings", "Yes" if time_info.daylight_savings else "No")

            console.print(table)

    except Exception as e:
        print_error(f"Failed to get time: {e}")
        raise typer.Exit(code=1) from e


@app.command("set", rich_help_panel="Configuration")
def set_time(
    port: str | None = typer.Option(None, "--port", "-p", help="Serial port"),
    hour: int = typer.Option(..., help="Hour (0-23)"),
    minute: int = typer.Option(..., help="Minute (0-59)"),
    second: int = typer.Option(..., help="Second (0-59)"),
    month: int = typer.Option(..., help="Month (1-12)"),
    day: int = typer.Option(..., help="Day (1-31)"),
    year: int = typer.Option(..., help="Year (e.g., 2024)"),
    timezone: int = typer.Option(0, help="Timezone offset from GMT in hours"),
    daylight_savings: int = typer.Option(0, help="Daylight savings (0 or 1)"),
) -> None:
    """
    Set date and time on telescope.

    Example:
        nexstar time set --hour 14 --minute 30 --second 0 --month 10 --day 31 --year 2024
        nexstar time set --hour 12 --minute 0 --second 0 --month 6 --day 15 --year 2024 --timezone -5
    """
    # Validate inputs
    if not 0 <= hour <= 23:
        print_error("Hour must be between 0 and 23")
        raise typer.Exit(code=1) from None
    if not 0 <= minute <= 59:
        print_error("Minute must be between 0 and 59")
        raise typer.Exit(code=1) from None
    if not 0 <= second <= 59:
        print_error("Second must be between 0 and 59")
        raise typer.Exit(code=1) from None
    if not 1 <= month <= 12:
        print_error("Month must be between 1 and 12")
        raise typer.Exit(code=1) from None
    if not 1 <= day <= 31:
        print_error("Day must be between 1 and 31")
        raise typer.Exit(code=1) from None
    if year < 2000:
        print_error("Year must be 2000 or later")
        raise typer.Exit(code=1) from None
    if daylight_savings not in [0, 1]:
        print_error("Daylight savings must be 0 or 1")
        raise typer.Exit(code=1) from None

    try:
        telescope = ensure_connected()

        print_info(f"Setting time to {year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}")

        success = telescope.set_time(hour, minute, second, month, day, year, timezone, daylight_savings)
        if success:
            print_success(
                f"Time set to {year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d} (GMT{timezone:+d})"
            )
        else:
            print_error("Failed to set time")
            raise typer.Exit(code=1) from None

    except Exception as e:
        print_error(f"Failed to set time: {e}")
        raise typer.Exit(code=1) from e


@app.command("sync", rich_help_panel="Configuration")
def sync_time(
    port: str | None = typer.Option(None, "--port", "-p", help="Serial port"),
    timezone: int | None = typer.Option(None, help="Timezone offset from GMT (auto-detect if not specified)"),
) -> None:
    """
    Sync telescope time with system time.

    This is a convenience command that sets the telescope time to match
    your computer's current time.

    Example:
        nexstar time sync
        nexstar time sync --timezone -5
    """
    try:
        telescope = ensure_connected()

        # Get current system time
        now = datetime.now()

        # Auto-detect timezone if not specified
        if timezone is None:
            # Get UTC offset in hours
            utc_offset = datetime.now().astimezone().utcoffset()
            timezone = int(utc_offset.total_seconds() / 3600) if utc_offset is not None else 0

        # Determine if DST is in effect (simple heuristic)
        dst = 1 if now.dst() else 0

        print_info(
            f"Syncing to system time: {now.year}-{now.month:02d}-{now.day:02d} "
            f"{now.hour:02d}:{now.minute:02d}:{now.second:02d} (GMT{timezone:+d})"
        )

        success = telescope.set_time(now.hour, now.minute, now.second, now.month, now.day, now.year, timezone, dst)

        if success:
            print_success("Telescope time synced with system time")
        else:
            print_error("Failed to sync time")
            raise typer.Exit(code=1) from None

    except Exception as e:
        print_error(f"Failed to sync time: {e}")
        raise typer.Exit(code=1) from e
