"""
TUI Application State

Manages state for the TUI application including selected objects and focus.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ...api.catalogs import CelestialObject
    from ...api.visibility import VisibilityInfo


@dataclass
class TUIState:
    """State for the TUI application."""

    # Visible objects list and selection
    visible_objects: list[tuple[CelestialObject, VisibilityInfo]] = field(default_factory=list)
    selected_index: int = 0
    focused_pane: str = "visible"  # "dataset", "conditions", "visible"
    show_detail: bool = False  # Whether to show detail view in pane

    def get_selected_object(self) -> tuple[CelestialObject, VisibilityInfo] | None:
        """Get the currently selected object."""
        if not self.visible_objects or self.selected_index < 0:
            return None
        if self.selected_index >= len(self.visible_objects):
            return None
        return self.visible_objects[self.selected_index]

    def move_selection_up(self) -> None:
        """Move selection up."""
        if self.visible_objects and self.selected_index > 0:
            self.selected_index -= 1

    def move_selection_down(self) -> None:
        """Move selection down."""
        if self.visible_objects and self.selected_index < len(self.visible_objects) - 1:
            self.selected_index += 1

    def set_visible_objects(self, objects: list[tuple[CelestialObject, VisibilityInfo]]) -> None:
        """Set the visible objects list and reset selection."""
        self.visible_objects = objects
        # Reset selection to 0, but keep it within bounds
        if self.selected_index >= len(objects):
            self.selected_index = max(0, len(objects) - 1)
        elif self.selected_index < 0:
            self.selected_index = 0

    def toggle_detail(self) -> None:
        """Toggle detail view."""
        self.show_detail = not self.show_detail


# Global state instance
_state: TUIState | None = None


def get_state() -> TUIState:
    """Get the global TUI state."""
    global _state
    if _state is None:
        _state = TUIState()
    return _state


def reset_state() -> None:
    """Reset the global state."""
    global _state
    _state = TUIState()
