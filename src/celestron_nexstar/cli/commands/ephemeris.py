"""
Ephemeris Commands

Commands for managing JPL ephemeris files for offline field use.
"""

from typing import Any, Literal, cast

import typer
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from celestron_nexstar.api.ephemeris_manager import (
    EPHEMERIS_FILES,
    EPHEMERIS_SETS,
    delete_file,
    download_file,
    download_set,
    get_ephemeris_directory,
    get_file_size,
    get_installed_files,
    get_set_info,
    is_file_installed,
    verify_file,
)

from ..utils.output import calculate_panel_width, console, print_error, print_info, print_success, print_warning
from ..utils.selection import select_from_list


app = typer.Typer(help="Ephemeris file management")


@app.command("list", rich_help_panel="File Management")
def list_files(
    show_all: bool = typer.Option(False, "--all", "-a", help="Show all available files"),
) -> None:
    """
    List installed ephemeris files.

    Shows which ephemeris files are currently downloaded and available
    for offline use.

    Examples:
        nexstar ephemeris list
        nexstar ephemeris list --all
    """
    try:
        installed = get_installed_files()

        if not show_all:
            # Show only installed files
            if not installed:
                print_info("No ephemeris files installed")
                print_info("Use 'nexstar ephemeris download <file>' to download files")
                print_info("Use 'nexstar ephemeris list --all' to see available files")
                return

            table = Table(
                title="Installed Ephemeris Files",
                show_header=True,
                header_style="bold magenta",
            )
            table.add_column("File", style="cyan", width=35)
            table.add_column("Size", style="green", width=10)
            table.add_column("Coverage", style="yellow", width=15)
            table.add_column("Contents", style="white")

            for _, info, path in installed:
                actual_size_mb = path.stat().st_size / (1024 * 1024)
                coverage = f"{info.coverage_start}-{info.coverage_end}"
                contents = ", ".join(info.contents[:3])
                if len(info.contents) > 3:
                    contents += f", +{len(info.contents) - 3} more"

                table.add_row(
                    info.display_name,
                    f"{actual_size_mb:.1f} MB",
                    coverage,
                    contents,
                )

            console.print(table)
            total_size = sum(p.stat().st_size for _, _, p in installed) / (1024 * 1024)
            print_info(f"Total: {len(installed)} files, {total_size:.1f} MB")

        else:
            # Show all available files
            table = Table(
                title="Available Ephemeris Files",
                show_header=True,
                header_style="bold magenta",
            )
            table.add_column("File", style="cyan", width=35)
            table.add_column("Status", style="green", width=15)
            table.add_column("Size", style="yellow", width=10)
            table.add_column("Coverage", style="blue", width=15)

            for key, info in EPHEMERIS_FILES.items():
                status = "[green]✓ Installed[/green]" if is_file_installed(key) else "[dim]Not installed[/dim]"

                table.add_row(
                    info.display_name,
                    status,
                    f"{info.size_mb:.0f} MB",
                    f"{info.coverage_start}-{info.coverage_end}",
                )

            console.print(table)
            print_info(f"Storage location: {get_ephemeris_directory()}")

    except Exception as e:
        print_error(f"Failed to list files: {e}")
        raise typer.Exit(code=1) from e


@app.command("info", rich_help_panel="File Information")
def show_info(
    file: str | None = typer.Argument(
        None, help="File name (e.g., de440s, jup365). If not provided, will prompt interactively."
    ),
) -> None:
    """
    Show detailed information about an ephemeris file.

    Explains what the file contains, when to use it, and what objects
    it covers.

    If run without arguments, you'll be prompted to select from available
    files interactively.

    Examples:
        # Interactive selection
        nexstar ephemeris info

        # Direct selection
        nexstar ephemeris info de440s
        nexstar ephemeris info jup365
    """
    try:
        # Interactive selection if file not provided
        if file is None:
            file = _select_ephemeris_file_interactive()
            if file is None:
                print_info("Selection cancelled")
                return

        if file not in EPHEMERIS_FILES:
            print_error(f"Unknown ephemeris file: {file}")
            print_info(f"Available files: {', '.join(EPHEMERIS_FILES.keys())}")
            raise typer.Exit(code=1) from None

        info = EPHEMERIS_FILES[file]
        installed = is_file_installed(file)

        # Create info panel
        info_text = Text()

        # Status
        if installed:
            info_text.append("Status: ", style="bold yellow")
            info_text.append("✓ Installed\n", style="bold green")
            actual_size = get_file_size(file)
            if actual_size:
                info_text.append(f"   Size: {actual_size / (1024 * 1024):.1f} MB\n", style="green")
        else:
            info_text.append("Status: ", style="bold yellow")
            info_text.append("Not installed\n", style="dim")
            info_text.append(f"   Est. size: {info.size_mb:.0f} MB\n", style="yellow")

        info_text.append("\n")

        # Coverage
        info_text.append("Time Coverage:\n", style="bold yellow")
        info_text.append(f"   {info.coverage_start} - {info.coverage_end}\n", style="white")
        info_text.append("\n")

        # Description
        info_text.append("Description:\n", style="bold yellow")
        info_text.append(f"   {info.description}\n", style="white")
        info_text.append("\n")

        # Contents
        info_text.append("Contains:\n", style="bold yellow")
        for obj in info.contents:
            info_text.append(f"   • {obj}\n", style="white")
        info_text.append("\n")

        # Use case
        info_text.append("When to use:\n", style="bold yellow")
        info_text.append(f"   {info.use_case}\n", style="white")

        panel = Panel(
            info_text,
            title=f"[bold]{info.display_name}[/bold]",
            border_style="cyan",
            width=calculate_panel_width(info_text, console),
        )
        console.print(panel)

        # Show download command if not installed
        if not installed:
            print_info(f"Download with: nexstar ephemeris download {file}")

    except Exception as e:
        print_error(f"Failed to show info: {e}")
        raise typer.Exit(code=1) from e


@app.command("download", rich_help_panel="File Management")
def download(
    file: str | None = typer.Argument(
        None, help="File name or set name (e.g., de440s, standard). If not provided, will prompt interactively."
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Force re-download"),
) -> None:
    """
    Download an ephemeris file or file set.

    Downloads ephemeris files to ~/.skyfield/ for offline use in the field.
    Files are downloaded from NASA JPL's NAIF servers.

    If run without arguments, you'll be prompted to select from available
    files and sets interactively.

    File sets:
      recommended - Skyfield's default (DE421 + Jupiter moons) (~20 MB) [RECOMMENDED]
      minimal     - Same as recommended (alias) (~20 MB)
      standard    - Planets + Jupiter & Saturn moons (~47 MB)
      complete    - All major moons except Mars (~60 MB)
      full        - Everything including Mars moons (~63 MB)

    Examples:
        # Interactive selection
        nexstar ephemeris download

        # Download specific file
        nexstar ephemeris download de440s
        nexstar ephemeris download jup365

        # Download file set (recommended is Skyfield's default)
        nexstar ephemeris download recommended
        nexstar ephemeris download standard
        nexstar ephemeris download complete

        # Force re-download
        nexstar ephemeris download de440s --force
    """
    try:
        # Interactive selection if file not provided
        if file is None:
            file = _select_ephemeris_download_interactive()
            if file is None:
                print_info("Selection cancelled")
                return
        # Check if it's a file set
        if file in EPHEMERIS_SETS:
            set_info = get_set_info(file)
            print_info(
                f"Downloading {file} set ({set_info['file_count']} files, {set_info['total_size_mb']:.0f} MB)..."
            )

            with console.status(f"[bold green]Downloading {file} set..."):
                downloaded = download_set(
                    cast(Literal["recommended", "minimal", "standard", "complete", "full"], file), force=force
                )

            print_success(f"Downloaded {len(downloaded)} files")
            for path in downloaded:
                size_mb = path.stat().st_size / (1024 * 1024)
                print_success(f"  ✓ {path.name} ({size_mb:.1f} MB)")

        # Check if it's an individual file
        elif file in EPHEMERIS_FILES:
            info = EPHEMERIS_FILES[file]

            # Check if already installed
            if is_file_installed(file) and not force:
                print_warning(f"{info.display_name} is already installed")
                print_info("Use --force to re-download")
                return

            print_info(f"Downloading {info.display_name} ({info.size_mb:.0f} MB)...")

            with console.status(f"[bold green]Downloading {info.filename}..."):
                path = download_file(file, force=force)

            size_mb = path.stat().st_size / (1024 * 1024)
            print_success(f"Downloaded {info.display_name} ({size_mb:.1f} MB)")
            print_info(f"Saved to: {path}")

        else:
            print_error(f"Unknown file or set: {file}")
            print_info(f"Available files: {', '.join(EPHEMERIS_FILES.keys())}")
            print_info(f"Available sets: {', '.join(EPHEMERIS_SETS.keys())}")
            raise typer.Exit(code=1) from None

    except Exception as e:
        print_error(f"Download failed: {e}")
        raise typer.Exit(code=1) from e


@app.command("sets", rich_help_panel="File Information")
def show_sets() -> None:
    """
    Show predefined ephemeris file sets.

    File sets are curated collections designed for different observing needs.

    Example:
        nexstar ephemeris sets
    """
    try:
        table = Table(
            title="Ephemeris File Sets",
            show_header=True,
            header_style="bold magenta",
        )
        table.add_column("Set", style="cyan", width=12)
        table.add_column("Files", style="yellow", width=8)
        table.add_column("Size", style="green", width=10)
        table.add_column("Status", style="blue", width=12)
        table.add_column("Description", style="white")

        set_descriptions = {
            "recommended": "Skyfield's default recommendation (DE421 + Jupiter moons)",
            "minimal": "Same as recommended (alias for backwards compatibility)",
            "standard": "Planets + Jupiter & Saturn moons",
            "complete": "All major planet moons except Mars",
            "full": "Everything including challenging Mars moons",
        }

        for set_name in ["recommended", "minimal", "standard", "complete", "full"]:
            info = get_set_info(set_name)
            installed_count = cast(int, info["installed_count"])
            file_count = cast(int, info["file_count"])
            (installed_count / file_count) * 100

            if installed_count == file_count:
                status = "[green]✓ Complete[/green]"
            elif installed_count > 0:
                status = f"[yellow]{installed_count}/{file_count}[/yellow]"
            else:
                status = "[dim]Not installed[/dim]"

            # Highlight recommended set
            set_name_display = f"[bold green]★ {set_name}[/bold green]" if set_name == "recommended" else set_name
            table.add_row(
                set_name_display,
                str(info["file_count"]),
                f"{info['total_size_mb']:.0f} MB",
                status,
                set_descriptions[set_name],
            )

        console.print(table)
        print_info("Download a set with: nexstar ephemeris download <set_name>")

    except Exception as e:
        print_error(f"Failed to show sets: {e}")
        raise typer.Exit(code=1) from e


@app.command("verify", rich_help_panel="File Management")
def verify(
    file: str = typer.Argument(None, help="File to verify (or all if not specified)"),
) -> None:
    """
    Verify integrity of installed ephemeris files.

    Checks if files can be loaded correctly by Skyfield.

    Examples:
        nexstar ephemeris verify         # Verify all installed files
        nexstar ephemeris verify de440s  # Verify specific file
    """
    try:
        if file:
            # Verify specific file
            if file not in EPHEMERIS_FILES:
                print_error(f"Unknown file: {file}")
                raise typer.Exit(code=1) from None

            if not is_file_installed(file):
                print_error(f"{file} is not installed")
                raise typer.Exit(code=1) from None

            info = EPHEMERIS_FILES[file]
            print_info(f"Verifying {info.display_name}...")

            is_valid, message = verify_file(file)
            if is_valid:
                print_success(f"✓ {info.display_name}: {message}")
            else:
                print_error(f"✗ {info.display_name}: {message}")
                raise typer.Exit(code=1) from None

        else:
            # Verify all installed files
            installed = get_installed_files()

            if not installed:
                print_info("No files to verify")
                return

            print_info(f"Verifying {len(installed)} files...")

            all_valid = True
            for key, info, _ in installed:
                is_valid, message = verify_file(key)
                if is_valid:
                    print_success(f"✓ {info.display_name}")
                else:
                    print_error(f"✗ {info.display_name}: {message}")
                    all_valid = False

            if all_valid:
                print_success("All files verified successfully")
            else:
                print_error("Some files failed verification")
                raise typer.Exit(code=1) from None

    except Exception as e:
        print_error(f"Verification failed: {e}")
        raise typer.Exit(code=1) from e


@app.command("delete", rich_help_panel="File Management")
def delete_file_cmd(
    file: str = typer.Argument(..., help="File to delete"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """
    Delete an installed ephemeris file.

    Removes the file from ~/.skyfield/ to free up disk space.

    Example:
        nexstar ephemeris delete de421
        nexstar ephemeris delete de421 --yes
    """
    try:
        if file not in EPHEMERIS_FILES:
            print_error(f"Unknown file: {file}")
            raise typer.Exit(code=1) from None

        if not is_file_installed(file):
            print_warning(f"{file} is not installed")
            return

        info = EPHEMERIS_FILES[file]
        size = get_file_size(file)
        size_mb = size / (1024 * 1024) if size else 0

        # Confirmation
        if not yes:
            console.print("\n[yellow]About to delete:[/yellow]")
            console.print(f"  File: {info.display_name}")
            console.print(f"  Size: {size_mb:.1f} MB\n")

            confirm = typer.confirm("Are you sure?")
            if not confirm:
                print_info("Cancelled")
                return

        # Delete
        success = delete_file(file)
        if success:
            print_success(f"Deleted {info.display_name} ({size_mb:.1f} MB freed)")
        else:
            print_error(f"Failed to delete {file}")
            raise typer.Exit(code=1) from None

    except Exception as e:
        print_error(f"Delete failed: {e}")
        raise typer.Exit(code=1) from e


def _select_ephemeris_file_interactive() -> str | None:
    """Interactively select an ephemeris file."""
    # Create list of file keys with their info
    file_items = list(EPHEMERIS_FILES.items())

    def display_file(item: tuple[str, Any]) -> tuple[str, ...]:
        key, info = item
        installed = is_file_installed(key)
        status = "[green]✓ Installed[/green]" if installed else "[dim]Not installed[/dim]"
        if installed:
            size = get_file_size(key)
            size_str = f"{size / (1024 * 1024):.1f} MB" if size else f"{info.size_mb:.0f} MB (est.)"
        else:
            size_str = f"{info.size_mb:.0f} MB"
        coverage = f"{info.coverage_start}-{info.coverage_end}"
        return (info.display_name, status, size_str, coverage)

    selected = select_from_list(
        file_items,
        title="Select Ephemeris File",
        display_func=display_file,
        headers=["File", "Status", "Size", "Coverage"],
    )

    return selected[0] if selected else None


def _select_ephemeris_download_interactive() -> str | None:
    """Interactively select an ephemeris file or set to download."""
    # Combine files and sets
    all_items: list[tuple[str, str, Any]] = []  # (key, type, info)

    # Add individual files
    for key, info in EPHEMERIS_FILES.items():
        all_items.append((key, "file", info))

    # Add sets
    for set_name in EPHEMERIS_SETS:
        set_info = get_set_info(set_name)
        all_items.append((set_name, "set", set_info))

    def display_item(item: tuple[str, str, Any]) -> tuple[str, ...]:
        key, item_type, info = item
        if item_type == "file":
            info_obj = info
            name = info_obj.display_name
            size = f"{info_obj.size_mb:.0f} MB"
            description = info_obj.description[:50] + "..." if len(info_obj.description) > 50 else info_obj.description
        else:
            # It's a set
            set_info_dict = info
            # Highlight recommended set
            name = "[bold green]★ Recommended Set[/bold green]" if key == "recommended" else f"{key.title()} Set"
            size = f"{set_info_dict['total_size_mb']:.0f} MB"
            description = (
                "[dim]Skyfield's default[/dim]" if key == "recommended" else f"{set_info_dict['file_count']} files"
            )

        return (name, "[cyan]File[/cyan]" if item_type == "file" else "[yellow]Set[/yellow]", size, description)

    selected = select_from_list(
        all_items,
        title="Select Ephemeris File or Set to Download",
        display_func=display_item,
        headers=["Name", "Type", "Size", "Description"],
    )

    return selected[0] if selected else None
