"""
Layout Construction

Builds the full-screen TUI layout with panes and containers.
"""

from __future__ import annotations

from prompt_toolkit.layout.containers import (
    HSplit,
    VSplit,
    Window,
)
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension

from .panes import (
    get_conditions_info,
    get_dataset_info,
    get_header_info,
    get_status_info,
    get_visible_objects_info,
)


def create_layout() -> HSplit:
    """
    Create the main layout for the TUI application.

    Returns:
        Root container with header, panes, and status bar
    """
    # Header bar
    header = Window(
        content=FormattedTextControl(get_header_info),
        height=Dimension.exact(1),
        char="─",
        style="bg:#333333",
    )

    # Dataset information pane (left)
    dataset_pane = Window(
        content=FormattedTextControl(get_dataset_info),
        width=Dimension(weight=30),
        wrap_lines=True,
        style="bg:#1e1e1e",
    )

    # Conditions pane (middle)
    conditions_pane = Window(
        content=FormattedTextControl(get_conditions_info),
        width=Dimension(weight=30),
        wrap_lines=True,
        style="bg:#1e1e1e",
    )

    # Visible objects pane (right, scrollable)
    visible_pane = Window(
        content=FormattedTextControl(get_visible_objects_info),
        width=Dimension(weight=40),
        wrap_lines=False,
        style="bg:#1e1e1e",
    )

    # Main content area with three panes
    main_content = VSplit([
        dataset_pane,
        Window(width=1, char="│", style="fg:#666666"),  # Vertical divider
        conditions_pane,
        Window(width=1, char="│", style="fg:#666666"),  # Vertical divider
        visible_pane,
    ])

    # Status bar
    status_bar = Window(
        content=FormattedTextControl(get_status_info),
        height=Dimension.exact(1),
        char="─",
        style="bg:#333333",
    )

    # Root container
    root_container = HSplit([
        header,
        main_content,
        status_bar,
    ])

    return root_container

