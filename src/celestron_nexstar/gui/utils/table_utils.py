"""
Table sizing utilities.

We standardize column auto-sizing across the GUI to keep tables readable without manual resizing.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QHeaderView


def autosize_table_columns(widget: Any, *, stretch_last: bool = False) -> None:
    """Auto-size all columns to their contents for QTableWidget/QTreeWidget/QTableView-like widgets.

    This sets the horizontal header resize mode to ResizeToContents, and then forces an initial resize
    pass via the widget's resize-to-contents method if available.
    """

    header = None
    if hasattr(widget, "horizontalHeader"):
        try:
            header = widget.horizontalHeader()
        except Exception:
            header = None
    if header is None and hasattr(widget, "header"):
        try:
            header = widget.header()
        except Exception:
            header = None

    if header is not None and isinstance(header, QHeaderView):
        header.setStretchLastSection(stretch_last)
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

    # Force initial sizing
    if hasattr(widget, "resizeColumnsToContents"):
        try:
            widget.resizeColumnsToContents()
            return
        except Exception:
            pass

    if hasattr(widget, "columnCount") and hasattr(widget, "resizeColumnToContents"):
        try:
            col_count = int(widget.columnCount())
            for col in range(col_count):
                widget.resizeColumnToContents(col)
        except Exception:
            pass
