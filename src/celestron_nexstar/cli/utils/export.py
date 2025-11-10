"""
Export utilities for CLI commands.

Supports exporting Rich console output to text files with ASCII tables.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from typing import Any


def export_to_text(content: str, file_path: Path) -> None:
    """
    Export content to a text file.

    Args:
        content: Text content to export
        file_path: Path to output file
    """
    with file_path.open("w", encoding="utf-8") as f:
        f.write(content)


class FileConsole:
    """Wrapper for Console with StringIO file handle for export."""

    def __init__(self, console: Console, file_handle: StringIO) -> None:
        self._console = console
        self.file = file_handle

    def __getattr__(self, name: str) -> Any:
        """Delegate all other attributes to the underlying console."""
        return getattr(self._console, name)


def create_file_console(file_path: Path | None = None) -> FileConsole:
    """
    Create a console that writes to a file (for export) or stdout.

    Args:
        file_path: If provided, write to this file. Otherwise write to StringIO.

    Returns:
        FileConsole instance with console and file handle for export
    """
    file_handle: StringIO | Any = file_path.open("w", encoding="utf-8") if file_path else StringIO()

    console = Console(
        file=file_handle,
        force_terminal=False,  # Disable terminal features for clean text
        width=120,  # Fixed width for consistent formatting
        legacy_windows=False,
        _environ={},  # Don't use environment variables
        no_color=True,  # No ANSI color codes in exported files
    )

    return FileConsole(console, file_handle)  # type: ignore[arg-type]
