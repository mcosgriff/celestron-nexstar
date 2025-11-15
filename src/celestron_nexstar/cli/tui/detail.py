"""
Object Detail View

Shows detailed information about a selected celestial object.
"""

from __future__ import annotations

from prompt_toolkit.formatted_text import FormattedText

from celestron_nexstar.api.catalogs.catalogs import CelestialObject
from celestron_nexstar.api.observation.visibility import VisibilityInfo


def get_object_detail_text(obj: CelestialObject, visibility_info: VisibilityInfo) -> FormattedText:
    """
    Generate formatted text for object detail view.

    Args:
        obj: The celestial object
        visibility_info: Visibility information for the object

    Returns:
        Formatted text for inline display
    """
    # Try to get additional details from database
    import asyncio

    from celestron_nexstar.api.database.database import get_database

    db = get_database()
    db_obj = asyncio.run(db.get_by_name(obj.name))

    # Use database object if available (has more fields), otherwise use catalog object
    display_obj = db_obj if db_obj else obj

    lines: list[tuple[str, str]] = []

    # Header
    lines.append(("bold cyan", f"{display_obj.name}"))
    if display_obj.common_name:
        lines.append(("", " - "))
        lines.append(("dim", display_obj.common_name))
    lines.append(("", "\n"))
    # Use a simple separator line that will wrap naturally
    lines.append(("dim", "────────────────────\n"))  # Fixed short separator

    # Position (J2000)
    ra_h = int(display_obj.ra_hours)
    ra_m = int((display_obj.ra_hours - ra_h) * 60)
    ra_s = int(((display_obj.ra_hours - ra_h) * 60 - ra_m) * 60)
    dec_d = int(display_obj.dec_degrees)
    dec_m = int((abs(display_obj.dec_degrees) - abs(dec_d)) * 60)
    dec_s = int(((abs(display_obj.dec_degrees) - abs(dec_d)) * 60 - dec_m) * 60)
    dec_dir = "N" if display_obj.dec_degrees >= 0 else "S"

    # Position on separate lines to avoid long lines
    lines.append(("bold", "Position (J2000):\n"))
    lines.append(("", f"  RA:  {ra_h:02d}h {ra_m:02d}m {ra_s:02d}s\n"))
    lines.append(("", f"  Dec: {abs(dec_d):02d}° {dec_m:02d}' {dec_s:02d}\" {dec_dir}\n"))

    # Current position
    if visibility_info.altitude_deg is not None and visibility_info.azimuth_deg is not None:
        lines.append(("bold", "Current: "))
        lines.append(("cyan", f"Alt:{visibility_info.altitude_deg:5.1f}° "))
        lines.append(("cyan", f"Az:{visibility_info.azimuth_deg:5.1f}°\n"))

    # Properties - each on its own line
    lines.append(("bold", "Type: "))
    lines.append(("", f"{display_obj.object_type.value}\n"))

    lines.append(("bold", "Catalog: "))
    lines.append(("", f"{display_obj.catalog}\n"))

    # Get additional fields from database if available
    if db_obj:
        from celestron_nexstar.api.database.models import CelestialObjectModel

        with db._get_session_sync() as session:
            model = (
                session.query(CelestialObjectModel).filter(CelestialObjectModel.name.ilike(display_obj.name)).first()
            )
            if model:
                if model.constellation:
                    lines.append(("bold", "Const: "))
                    lines.append(("", f"{model.constellation}\n"))
                if model.size_arcmin:
                    lines.append(("bold", "Size: "))
                    lines.append(("", f"{model.size_arcmin:.2f}'\n"))
                if model.catalog_number:
                    lines.append(("bold", "#: "))
                    lines.append(("", f"{model.catalog_number}\n"))

    if display_obj.magnitude is not None:
        lines.append(("bold", "Mag: "))
        lines.append(("cyan", f"{display_obj.magnitude:.2f}\n"))
    if visibility_info.limiting_magnitude:
        lines.append(("bold", "Limit: "))
        lines.append(("yellow", f"{visibility_info.limiting_magnitude:.2f}\n"))

    # Description (truncated for inline view)
    if display_obj.description:
        desc = display_obj.description.split("\n")[0]  # First line only
        if len(desc) > 60:
            desc = desc[:57] + "..."
        lines.append(("dim", f"{desc}\n"))

    # Visibility info
    if visibility_info.reasons:
        lines.append(("bold", "Visibility: "))
        # Show first reason only for compact view
        first_reason = visibility_info.reasons[0] if visibility_info.reasons else ""
        if len(first_reason) > 50:
            first_reason = first_reason[:47] + "..."
        lines.append(("", f"{first_reason} "))
        lines.append(("dim", f"(score: {visibility_info.observability_score:.2f})\n"))

    if display_obj.parent_planet:
        lines.append(("bold", "Parent: "))
        lines.append(("", f"{display_obj.parent_planet}\n"))

    # Use a simple separator line that will wrap naturally
    lines.append(("dim", "────────────────────\n"))  # Fixed short separator
    lines.append(("dim", "Press Esc to close detail view\n"))

    return FormattedText(lines)


def show_object_detail(obj: CelestialObject, visibility_info: VisibilityInfo) -> None:
    """
    Display detailed information about a celestial object (legacy function for dialog mode).

    Args:
        obj: The celestial object
        visibility_info: Visibility information for the object
    """
    from rich.console import Console

    console = Console()

    # Try to get additional details from database
    import asyncio

    from celestron_nexstar.api.database.database import get_database

    db = get_database()
    db_obj = asyncio.run(db.get_by_name(obj.name))

    # Use database object if available (has more fields), otherwise use catalog object
    display_obj = db_obj if db_obj else obj

    console.print("\n" + "=" * 70)
    console.print(f"[bold cyan]{display_obj.name}[/bold cyan]")
    if display_obj.common_name:
        console.print(f"[dim]Common Name:[/dim] {display_obj.common_name}")

    console.print("\n[bold]Position (J2000):[/bold]")
    ra_h = int(display_obj.ra_hours)
    ra_m = int((display_obj.ra_hours - ra_h) * 60)
    ra_s = int(((display_obj.ra_hours - ra_h) * 60 - ra_m) * 60)
    dec_d = int(display_obj.dec_degrees)
    dec_m = int((abs(display_obj.dec_degrees) - abs(dec_d)) * 60)
    dec_s = int(((abs(display_obj.dec_degrees) - abs(dec_d)) * 60 - dec_m) * 60)
    dec_dir = "N" if display_obj.dec_degrees >= 0 else "S"

    console.print(f"  RA:  {ra_h:02d}h {ra_m:02d}m {ra_s:02d}s")
    console.print(f"  Dec: {abs(dec_d):02d}° {dec_m:02d}' {dec_s:02d}\" {dec_dir}")

    # Current position (if different from J2000)
    if visibility_info.altitude_deg is not None and visibility_info.azimuth_deg is not None:
        console.print("\n[bold]Current Position:[/bold]")
        console.print(f"  Altitude: {visibility_info.altitude_deg:.2f}°")
        console.print(f"  Azimuth:  {visibility_info.azimuth_deg:.2f}°")

    console.print("\n[bold]Properties:[/bold]")
    console.print(f"  Type:      {display_obj.object_type.value}")
    console.print(f"  Catalog:   {display_obj.catalog}")

    # Get additional fields from database if available
    if db_obj:
        from celestron_nexstar.api.database.models import CelestialObjectModel

        with db._get_session_sync() as session:
            model = (
                session.query(CelestialObjectModel).filter(CelestialObjectModel.name.ilike(display_obj.name)).first()
            )
            if model:
                if model.constellation:
                    console.print(f"  Constellation: {model.constellation}")
                if model.size_arcmin:
                    console.print(f"  Size: {model.size_arcmin:.2f}'")
                if model.catalog_number:
                    console.print(f"  Catalog Number: {model.catalog_number}")

    if display_obj.magnitude is not None:
        console.print(f"  Magnitude: {display_obj.magnitude:.2f}")
    if visibility_info.limiting_magnitude:
        console.print(f"  Limiting Mag: {visibility_info.limiting_magnitude:.2f}")

    if display_obj.description:
        console.print("\n[bold]Description:[/bold]")
        # Wrap description text
        desc_lines = display_obj.description.split("\n")
        for line in desc_lines:
            console.print(f"  {line}")

    if visibility_info.reasons:
        console.print("\n[bold]Visibility:[/bold]")
        for reason in visibility_info.reasons:
            console.print(f"  • {reason}")
        console.print(f"  Observability Score: {visibility_info.observability_score:.2f}")

    if display_obj.parent_planet:
        console.print(f"\n[bold]Parent Planet:[/bold] {display_obj.parent_planet}")

    console.print("\n" + "=" * 70)
    console.print("[dim]Press Enter to return...[/dim]")
    from prompt_toolkit import PromptSession as _PromptSession

    prompt_session: _PromptSession[str] = _PromptSession()
    prompt_session.prompt("")


def show_object_detail_interactive() -> None:
    """Show detail for the currently selected object (legacy function)."""
    from celestron_nexstar.cli.tui.state import get_state

    state = get_state()
    selected = state.get_selected_object()

    if selected is None:
        from rich.console import Console

        console = Console()
        console.print("\n[red]No object selected[/red]")
        console.print("[dim]Press Enter to return...[/dim]")
        from prompt_toolkit import PromptSession as _PromptSession

        session: _PromptSession[str] = _PromptSession()
        session.prompt("")
        return

    obj, visibility_info = selected
    show_object_detail(obj, visibility_info)
