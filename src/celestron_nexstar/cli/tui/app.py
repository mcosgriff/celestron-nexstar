"""
TUI Application

Main application class for the full-screen terminal user interface.
"""

from __future__ import annotations

from prompt_toolkit import Application, PromptSession
from prompt_toolkit.layout.layout import Layout
from rich.console import Console

from .bindings import create_key_bindings
from .layout import create_layout


console = Console()


def _change_telescope_interactive() -> None:
    """Interactive telescope selection."""
    try:
        from ...api.optics import (
            TelescopeModel,
            get_current_configuration,
            get_telescope_specs,
            set_current_configuration,
        )

        current_config = get_current_configuration()
        console.print(f"\n[bold]Current Telescope:[/bold] {current_config.telescope.display_name}\n")

        # List available telescopes
        console.print("[bold]Available Telescopes:[/bold]")
        telescope_models = list(TelescopeModel)
        for i, model in enumerate(telescope_models, 1):
            specs = get_telescope_specs(model)
            marker = "←" if model == current_config.telescope.model else " "
            console.print(
                f"  {marker} {i}. {specs.display_name} ({specs.aperture_mm:.0f}mm, f/{specs.focal_ratio:.1f})"
            )

        console.print(f"\n[dim]Enter telescope number (1-{len(telescope_models)}) or name, or 'cancel':[/dim]")
        session = PromptSession()
        choice = session.prompt("> ").strip()

        if choice.lower() in ("cancel", "c", "q"):
            return

        # Parse choice
        selected_model = None
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(telescope_models):
                selected_model = telescope_models[idx]
        else:
            # Try to match by name
            choice_lower = choice.lower()
            for model in telescope_models:
                if choice_lower in model.display_name.lower() or choice_lower in model.value.lower():
                    selected_model = model
                    break

        if selected_model:
            new_telescope = get_telescope_specs(selected_model)
            new_config = type(current_config)(telescope=new_telescope, eyepiece=current_config.eyepiece)
            set_current_configuration(new_config)
            console.print(f"[green]✓[/green] Telescope changed to {new_telescope.display_name}")
            console.print("[dim]Press Enter to return to dashboard...[/dim]")
            session.prompt("")
        else:
            console.print("[red]Invalid selection[/red]")
            console.print("[dim]Press Enter to return...[/dim]")
            session.prompt("")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


def _change_eyepiece_interactive() -> None:
    """Interactive eyepiece selection."""
    try:
        from ...api.optics import (
            COMMON_EYEPIECES,
            get_current_configuration,
            set_current_configuration,
        )

        current_config = get_current_configuration()
        current_ep_name = current_config.eyepiece.name or f"{current_config.eyepiece.focal_length_mm:.0f}mm"
        console.print(f"\n[bold]Current Eyepiece:[/bold] {current_ep_name}\n")

        # List available eyepieces
        console.print("[bold]Available Eyepieces:[/bold]")
        eyepiece_items = list(COMMON_EYEPIECES.items())
        for i, (_key, eyepiece) in enumerate(eyepiece_items, 1):
            ep_name = eyepiece.name or f"{eyepiece.focal_length_mm:.0f}mm"
            marker = "←" if eyepiece.focal_length_mm == current_config.eyepiece.focal_length_mm else " "
            console.print(
                f"  {marker} {i}. {ep_name} ({eyepiece.focal_length_mm:.0f}mm, {eyepiece.apparent_fov_deg:.0f}° FOV)"
            )

        console.print(f"\n[dim]Enter eyepiece number (1-{len(eyepiece_items)}) or name, or 'cancel':[/dim]")
        session = PromptSession()
        choice = session.prompt("> ").strip()

        if choice.lower() in ("cancel", "c", "q"):
            return

        # Parse choice
        selected_eyepiece = None
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(eyepiece_items):
                selected_eyepiece = eyepiece_items[idx][1]
        else:
            # Try to match by name or focal length
            choice_lower = choice.lower()
            for key, eyepiece in eyepiece_items:
                ep_name = (eyepiece.name or "").lower()
                if choice_lower in ep_name or choice_lower in key.lower():
                    selected_eyepiece = eyepiece
                    break
                # Try matching focal length
                try:
                    if float(choice) == eyepiece.focal_length_mm:
                        selected_eyepiece = eyepiece
                        break
                except ValueError:
                    pass

        if selected_eyepiece:
            new_config = type(current_config)(telescope=current_config.telescope, eyepiece=selected_eyepiece)
            set_current_configuration(new_config)
            ep_name = selected_eyepiece.name or f"{selected_eyepiece.focal_length_mm:.0f}mm"
            console.print(f"[green]✓[/green] Eyepiece changed to {ep_name}")
            console.print("[dim]Press Enter to return to dashboard...[/dim]")
            session.prompt("")
        else:
            console.print("[red]Invalid selection[/red]")
            console.print("[dim]Press Enter to return...[/dim]")
            session.prompt("")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


class TUIApplication:
    """Full-screen TUI application for telescope control and observing."""

    def __init__(self) -> None:
        """Initialize the TUI application."""
        # Create layout once and reuse it
        # This ensures the layout structure doesn't get recreated on refresh
        root_container = create_layout()
        layout = Layout(root_container)

        # Create key bindings
        key_bindings = create_key_bindings()

        # Create application
        # The layout is created once and reused, so pane widths should remain stable
        self.app = Application(
            layout=layout,
            key_bindings=key_bindings,
            full_screen=True,
            refresh_interval=2.0,  # Refresh every 2 seconds
            mouse_support=False,  # Disable mouse for now
        )

    def run(self) -> None:
        """Run the TUI application."""
        while True:
            result = self.app.run()
            if result == "change_telescope":
                _change_telescope_interactive()
                # Recreate app to refresh
                self.__init__()
            elif result == "change_eyepiece":
                _change_eyepiece_interactive()
                # Recreate app to refresh
                self.__init__()
            else:
                break
