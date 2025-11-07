"""
Dashboard Command

Launches the full-screen TUI dashboard.
"""

import typer
from rich.console import Console

from ..tui import TUIApplication


app = typer.Typer(help="Full-screen dashboard commands")
console = Console()


@app.command()
def show() -> None:
    """
    Launch the full-screen telescope dashboard.

    The dashboard displays:
    - Database statistics and catalog information
    - Current observing conditions
    - List of currently visible objects

    Keyboard shortcuts:
    - q or Ctrl+Q: Quit
    - r: Refresh all panes
    - 1/2/3: Focus different panes (coming soon)
    - Ctrl+C: Exit gracefully
    """
    try:
        console.print("[dim]Launching dashboard...[/dim]")
        console.print("[dim]Press 'q' to quit[/dim]\n")

        # Create and run TUI
        tui = TUIApplication()
        tui.run()

        console.print("\n[green]Dashboard closed[/green]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        raise typer.Exit(code=1) from e
