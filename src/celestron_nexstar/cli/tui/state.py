"""
TUI Application State

Manages state for the TUI application including selected objects and focus.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
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
    time_display_mode: str = "local"  # "local" or "utc" for time display

    # Sorting and filtering
    sort_by: str = "altitude"  # "altitude", "magnitude", "name", "type"
    sort_reverse: bool = False  # True for descending order
    filter_type: str | None = None  # Filter by object type
    filter_mag_min: float | None = None  # Minimum magnitude
    filter_mag_max: float | None = None  # Maximum magnitude
    filter_constellation: str | None = None  # Filter by constellation
    search_query: str = ""  # Search query for object names
    search_mode: bool = False  # Whether in search input mode
    filter_menu_active: bool = False  # Whether filter menu is active

    # Session tracking
    session_start_time: datetime | None = None
    observed_objects: list[str] = field(default_factory=list)  # Names of observed objects

    # Quick actions state
    telescope_connected: bool = False

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

    def toggle_time_mode(self) -> None:
        """Toggle between local and UTC time display."""
        self.time_display_mode = "utc" if self.time_display_mode == "local" else "local"

    def cycle_sort_by(self) -> None:
        """Cycle through sort options."""
        sort_options = ["altitude", "magnitude", "name", "type"]
        current_idx = sort_options.index(self.sort_by) if self.sort_by in sort_options else 0
        self.sort_by = sort_options[(current_idx + 1) % len(sort_options)]
        self._apply_sorting()

    def toggle_sort_direction(self) -> None:
        """Toggle sort direction."""
        self.sort_reverse = not self.sort_reverse
        self._apply_sorting()

    def _apply_sorting(self) -> None:
        """Apply current sorting to visible objects."""
        if not self.visible_objects:
            return

        def sort_key(item: tuple[CelestialObject, VisibilityInfo]) -> tuple[float | int | str, ...]:
            obj, vis_info = item
            if self.sort_by == "altitude":
                return (vis_info.altitude_deg or -999,)
            elif self.sort_by == "magnitude":
                mag = obj.magnitude if obj.magnitude is not None else 999
                return (mag,)
            elif self.sort_by == "name":
                return (obj.name.lower(),)
            elif self.sort_by == "type":
                return (obj.object_type.value, obj.name.lower())
            return (0,)

        self.visible_objects.sort(key=sort_key, reverse=self.sort_reverse)
        # Reset selection to stay on same object if possible
        if self.selected_index >= len(self.visible_objects):
            self.selected_index = max(0, len(self.visible_objects) - 1)

    def add_observed_object(self, object_name: str) -> None:
        """Add an object to the observed list."""
        if object_name not in self.observed_objects:
            self.observed_objects.append(object_name)

    def get_session_duration(self) -> float | None:
        """Get session duration in hours."""
        if self.session_start_time is None:
            return None
        from datetime import datetime

        delta = datetime.now() - self.session_start_time
        return delta.total_seconds() / 3600.0


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
