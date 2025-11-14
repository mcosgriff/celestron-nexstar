"""
Layout Construction

Builds the full-screen TUI layout with panes and containers.
"""

from __future__ import annotations

from prompt_toolkit.layout.containers import (
    FloatContainer,
    HSplit,
    VSplit,
    Window,
)
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension

from celestron_nexstar.cli.tui.panes import (
    get_conditions_info,
    get_dataset_info,
    get_header_info,
    get_status_info,
    get_visible_objects_info,
)


def create_layout() -> FloatContainer:
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

    # Use fixed weight-based sizing to maintain stable proportions
    # Weights: 3:3:4 = 30%:30%:40% split
    # ignore_content_width=True prevents content from affecting width calculation
    # Dataset information pane (left) - 30%
    dataset_pane = Window(
        content=FormattedTextControl(get_dataset_info),
        width=Dimension(weight=3),
        wrap_lines=True,
        ignore_content_width=True,  # Ignore content width to maintain stable pane widths
        style="bg:#1e1e1e",
    )

    # Conditions pane (middle) - 30%
    conditions_pane = Window(
        content=FormattedTextControl(get_conditions_info),
        width=Dimension(weight=3),
        wrap_lines=True,
        ignore_content_width=True,  # Ignore content width to maintain stable pane widths
        style="bg:#1e1e1e",
    )

    # Visible objects pane (right) - 40%
    visible_pane = Window(
        content=FormattedTextControl(get_visible_objects_info),
        width=Dimension(weight=4),
        wrap_lines=True,  # Enable wrapping to prevent text cutoff
        ignore_content_width=True,  # Ignore content width to maintain stable pane widths
        style="bg:#1e1e1e",
    )

    # Main content area with three panes
    main_content = VSplit(
        [
            dataset_pane,
            Window(width=1, char="│", style="fg:#666666"),  # Vertical divider
            conditions_pane,
            Window(width=1, char="│", style="fg:#666666"),  # Vertical divider
            visible_pane,
        ]
    )

    # Status bar - single line
    status_bar = Window(
        content=FormattedTextControl(get_status_info),
        height=Dimension.exact(1),
        char="─",
        style="bg:#333333",
    )

    # Root container
    root_container = HSplit(
        [
            header,
            main_content,
            status_bar,
        ]
    )

    # Wrap in FloatContainer to support modal dialogs
    return FloatContainer(content=root_container, floats=[])
