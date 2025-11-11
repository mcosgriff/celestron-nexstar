"""
Database setup validation utilities.

Provides functions to check if the database is properly initialized
and show helpful error messages instead of stacktraces.
"""

from __future__ import annotations

from typing import NoReturn

import typer
from rich.console import Console

from ...api.database import get_database


console = Console()


def check_database_setup() -> None:
    """
    Check if database is properly set up.

    Raises:
        typer.Exit: If database is not set up, with a helpful error message
    """
    db = get_database()

    # Check if database file exists
    if not db.db_path.exists():
        raise _show_setup_error(
            "Database file does not exist.",
            "The database needs to be initialized before use.",
        )

    # Check if schema exists (objects table)
    try:
        from sqlalchemy import inspect, text

        inspector = inspect(db._engine)
        existing_tables = set(inspector.get_table_names())

        if "objects" not in existing_tables:
            raise _show_setup_error(
                "Database schema is missing.",
                "The database file exists but the schema has not been created.",
            )

        # Check if there's any catalog data
        with db._get_session() as session:
            result = session.execute(text("SELECT COUNT(*) FROM objects")).scalar() or 0
            if result == 0:
                raise _show_setup_error(
                    "Database is empty.",
                    "The database schema exists but no catalog data has been imported.",
                )

    except typer.Exit:
        # Re-raise typer.Exit from _show_setup_error
        raise
    except Exception as e:
        # If we can't check, assume it's a schema issue
        error_msg = str(e)
        if "no such table" in error_msg.lower() or "operationalerror" in error_msg.lower():
            raise _show_setup_error(
                "Database schema is missing or incomplete.",
                f"Error checking database: {error_msg}",
            ) from e
        # For other errors, let them propagate (might be a real issue)
        raise


def _show_setup_error(issue: str, details: str) -> NoReturn:
    """
    Show a helpful error message and exit.

    Args:
        issue: Brief description of the issue
        details: Additional details about the problem
    """
    console.print("\n[bold red]✗ Database Setup Required[/bold red]\n")
    console.print(f"[yellow]Issue:[/yellow] {issue}")
    console.print(f"[dim]{details}[/dim]\n")
    console.print("[bold cyan]To fix this, run:[/bold cyan]")
    console.print("  [green]nexstar data setup[/green]\n")
    console.print("[dim]This will create the database schema and import default catalog data.[/dim]\n")
    raise typer.Exit(code=1)


def require_database_setup(func):
    """
    Decorator to check database setup before running a command.

    Usage:
        @app.command()
        @require_database_setup
        def my_command():
            # Database is guaranteed to be set up here
            ...
    """
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        check_database_setup()
        return func(*args, **kwargs)

    return wrapper
