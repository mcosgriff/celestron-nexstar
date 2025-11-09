"""
Export utilities for CLI commands.

Supports exporting Rich console output to text files with ASCII tables.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from rich.console import Console


def export_to_text(content: str, file_path: Path) -> None:
    """
    Export content to a text file.

    Args:
        content: Text content to export
        file_path: Path to output file
    """
    with file_path.open("w", encoding="utf-8") as f:
        f.write(content)


def create_file_console(file_path: Path | None = None) -> Console:
    """
    Create a console that writes to a file (for export) or stdout.

    Args:
        file_path: If provided, write to this file. Otherwise write to StringIO.

    Returns:
        Console instance configured for file output
    """
    file_handle = file_path.open("w", encoding="utf-8") if file_path else StringIO()

    return Console(
        file=file_handle,
        force_terminal=False,  # Disable terminal features for clean text
        width=120,  # Fixed width for consistent formatting
        legacy_windows=False,
        _environ={},  # Don't use environment variables
        no_color=True,  # No ANSI color codes in exported files
    )

