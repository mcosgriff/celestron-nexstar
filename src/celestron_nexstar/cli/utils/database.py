"""
Database setup validation utilities.

Provides functions to check if the database is properly initialized
and show helpful error messages instead of stacktraces.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import NoReturn, TypeVar

import typer
from rich.console import Console

from celestron_nexstar.api.database.database import get_database


T = TypeVar("T", bound=Callable[..., object])


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

    # Check if schema exists (check for new type-specific tables)
    try:
        import asyncio

        from sqlalchemy import text

        async def _check_tables() -> set[str]:
            async with db._engine.begin() as conn:
                result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
                return {row[0] for row in result.fetchall()}

        existing_tables = asyncio.run(_check_tables())

        # Check for new type-specific tables (after refactor)
        # At least one of these should exist if schema is set up
        required_tables = ["stars", "planets", "moons", "galaxies", "nebulae", "clusters", "double_stars"]
        has_schema = any(table in existing_tables for table in required_tables)

        # Also check for old objects table (for backward compatibility during migration)
        has_old_schema = "objects" in existing_tables

        if not has_schema and not has_old_schema:
            raise _show_setup_error(
                "Database schema is missing.",
                "The database file exists but the schema has not been created.",
            )

        # Check if there's any catalog data
        from sqlalchemy import func, select

        from celestron_nexstar.api.database.models import (
            ClusterModel,
            DoubleStarModel,
            GalaxyModel,
            MoonModel,
            NebulaModel,
            PlanetModel,
            StarModel,
        )

        # Count objects across all type-specific tables
        total_count = 0
        with db._get_session_sync() as session:
            for model_class in [
                StarModel,
                DoubleStarModel,
                GalaxyModel,
                NebulaModel,
                ClusterModel,
                PlanetModel,
                MoonModel,
            ]:
                try:
                    # Type ignore: model_class is guaranteed to have 'id' attribute from CelestialObjectMixin
                    result = session.scalar(select(func.count(model_class.id))) or 0  # type: ignore[attr-defined]
                    total_count += result
                except Exception:
                    # Table might not exist yet, skip it
                    pass

            # Also check old objects table if it exists (for backward compatibility)
            if has_old_schema:
                try:
                    from celestron_nexstar.api.database.models import CelestialObjectModel

                    result = session.scalar(select(func.count(CelestialObjectModel.id))) or 0
                    total_count += result
                except Exception:
                    pass

        if total_count == 0:
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


def require_database_setup(func: T) -> T:
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
    def wrapper(*args: object, **kwargs: object) -> object:
        check_database_setup()
        return func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]
