"""
Layout Construction

Builds the full-screen TUI layout with panes and containers using Textual.
"""

from __future__ import annotations

from typing import Any

from textual.containers import Horizontal  # type: ignore[import-not-found]

from celestron_nexstar.cli.tui.panes import (
    ConditionsPane,
    DatasetPane,
    HeaderBar,
    StatusBar,
    VisibleObjectsPane,
)


def create_layout() -> list[Any]:
    """
    Create the main layout for the TUI application.

    Returns:
        List of widgets for the compose method
    """
    # Header bar
    header = HeaderBar(id="header")

    # Main content area with three panes
    dataset_pane = DatasetPane(id="dataset-pane", classes="pane")
    conditions_pane = ConditionsPane(id="conditions-pane", classes="pane")
    visible_pane = VisibleObjectsPane(id="visible-pane", classes="pane")

    # Status bar
    status_bar = StatusBar(id="status-bar")

    # Return widgets in order
    return [header, Horizontal(dataset_pane, conditions_pane, visible_pane, id="main-content"), status_bar]
