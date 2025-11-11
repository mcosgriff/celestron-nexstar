# Full-Screen TUI Application Plan

## Overview

Create a full-screen terminal application using `prompt_toolkit`'s `Application` class to display real-time telescope and observing information in multiple panes.

## Architecture

Based on [prompt_toolkit full-screen applications documentation](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/full_screen_apps.html), we'll use:

- **Application**: Main full-screen app instance
- **Layout**: VSplit/HSplit containers to arrange panes
- **UIControl**: FormattedTextControl for displaying formatted content
- **Window**: Containers that wrap UIControl objects
- **Key Bindings**: Global and pane-specific keyboard shortcuts

## Layout Structure

```text
┌─────────────────────────────────────────────────────────────┐
│  Header Bar (Connection Status, Time, Location)              │
├──────────────┬──────────────┬───────────────────────────────┤
│              │              │                                 │
│  Dataset     │  Conditions  │  Visible Objects              │
│  Information │  Pane        │  Pane                          │
│  Pane        │              │                                 │
│              │              │                                 │
│  (Left)      │  (Middle)    │  (Right - Scrollable)          │
│              │              │                                 │
│              │              │                                 │
├──────────────┴──────────────┴───────────────────────────────┤
│  Status Bar (Position, Tracking, Movement Status)           │
└─────────────────────────────────────────────────────────────┘
```

### Pane 1: Dataset Information (Left, ~30% width)

**Content:**

- Database statistics
  - Total objects in database
  - Objects by catalog (Messier, NGC, IC, etc.)
  - Objects by type (Galaxy, Nebula, Star, etc.)
  - Magnitude range
- Catalog status
  - Last import date
  - Import sources available
  - Data freshness indicators

**Update Frequency:** Every 5 seconds or on demand

**Implementation:**

````python
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.containers import Window

def get_dataset_info() -> FormattedText:
    """Generate formatted text for dataset pane."""
    db = get_database()
    stats = db.get_stats()

    return FormattedText([
        ("bold", "Database Statistics\n"),
        ("", f"Total Objects: {stats.total_objects:,}\n"),
        ("", f"Catalogs: {len(stats.objects_by_catalog)}\n"),
        ("", "\nBy Catalog:\n"),
        # ... format catalog breakdown
    ])

dataset_pane = Window(
    content=FormattedTextControl(get_dataset_info),
    width=Dimension(weight=30),
    wrap_lines=True,
)
```python

### Pane 2: Current Conditions (Middle, ~30% width)

**Content:**

- Weather conditions
  - Cloud cover percentage
  - Temperature
  - Precipitation probability
  - Seeing quality (if available)
- Sky conditions
  - Light pollution (Bortle class, SQM)
  - Moon phase and altitude
  - Limiting magnitude
- Time information
  - Current time (local and UTC)
  - Sunset/sunrise times
  - Night duration remaining

**Update Frequency:** Every 2 seconds (weather), every 1 second (time)

**Implementation:**

```python
def get_conditions_info() -> FormattedText:
    """Generate formatted text for conditions pane."""
    # Get observer location
    location = get_observer_location()

    # Get weather (if available)
    # Get moon phase
    # Get time info

    return FormattedText([
        ("bold", "Observing Conditions\n"),
        ("", f"Location: {location.name if location else 'Not set'}\n"),
        ("", f"Time: {datetime.now().strftime('%H:%M:%S')}\n"),
        # ... format conditions
    ])

conditions_pane = Window(
    content=FormattedTextControl(get_conditions_info),
    width=Dimension(weight=30),
    wrap_lines=True,
)
```python

### Pane 3: Visible Objects (Right, ~40% width, scrollable)

**Content:**

- List of currently visible objects
  - Object name and common name
  - Current altitude/azimuth
  - Magnitude
  - Object type
  - Observability score
- Sortable by:
  - Altitude (highest first)
  - Magnitude (brightest first)
  - Observability score
- Filterable by:
  - Object type
  - Minimum altitude
  - Maximum magnitude

**Update Frequency:** Every 3 seconds

**Implementation:**

```python
from prompt_toolkit.layout.containers import ScrollablePane

def get_visible_objects() -> FormattedText:
    """Generate formatted text for visible objects pane."""
    # Get observer location and time
    location = get_observer_location()
    config = get_current_configuration()

    # Query database for objects
    db = get_database()
    all_objects = db.filter_objects(max_magnitude=config.limiting_magnitude)

    # Filter visible objects
    visible = filter_visible_objects(
        all_objects,
        config=config,
        observer_lat=location.latitude_deg if location else None,
        observer_lon=location.longitude_deg if location else None,
    )

    # Sort by altitude (highest first)
    visible_sorted = sorted(visible, key=lambda v: v.altitude_deg or 0, reverse=True)

    # Format as list
    lines = [("bold", "Currently Visible Objects\n")]
    for obj_info in visible_sorted[:50]:  # Top 50
        lines.append(("", f"{obj_info.object_name:20s} "))
        lines.append(("cyan", f"Alt: {obj_info.altitude_deg:.1f}° "))
        lines.append(("yellow", f"Mag: {obj_info.magnitude or 'N/A'}\n"))

    return FormattedText(lines)

visible_pane = ScrollablePane(
    Window(
        content=FormattedTextControl(get_visible_objects),
        wrap_lines=False,
    )
)
```python

## Layout Implementation

```python
from prompt_toolkit import Application
from prompt_toolkit.layout.containers import (
    HSplit,
    VSplit,
    Window,
    FloatContainer,
)
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.layout.dimension import Dimension

# Create main layout
root_container = HSplit([
    # Header bar
    Window(
        content=FormattedTextControl(get_header_info),
        height=Dimension.exact(1),
        char="─",
    ),

    # Main content area
    VSplit([
        dataset_pane,
        Window(width=1, char="│"),  # Vertical divider
        conditions_pane,
        Window(width=1, char="│"),  # Vertical divider
        visible_pane,
    ]),

    # Status bar
    Window(
        content=FormattedTextControl(get_status_info),
        height=Dimension.exact(1),
        char="─",
    ),
])

layout = Layout(root_container)
```python

## Key Bindings

### Global Key Bindings

```python
from prompt_toolkit.key_binding import KeyBindings

kb = KeyBindings()

@kb.add('q')
@kb.add('c-q')
def exit_app(event):
    """Quit application."""
    event.app.exit()

@kb.add('r')
def refresh_all(event):
    """Force refresh all panes."""
    # Trigger refresh of all content
    pass

@kb.add('tab')
def cycle_focus(event):
    """Cycle focus between panes."""
    # Focus next pane
    pass

@kb.add('1')
def focus_dataset(event):
    """Focus dataset pane."""
    event.app.layout.focus(dataset_pane)

@kb.add('2')
def focus_conditions(event):
    """Focus conditions pane."""
    event.app.layout.focus(conditions_pane)

@kb.add('3')
def focus_visible(event):
    """Focus visible objects pane."""
    event.app.layout.focus(visible_pane)

@kb.add('s')
def toggle_sort(event):
    """Toggle sort order in visible objects pane."""
    # Cycle through: altitude, magnitude, score
    pass

@kb.add('f')
def filter_menu(event):
    """Open filter menu for visible objects."""
    # Show filter dialog
    pass
````

## Update Mechanism

Use `refresh_interval` in Application to auto-refresh content:

````python
app = Application(
    layout=layout,
    key_bindings=kb,
    full_screen=True,
    refresh_interval=1.0,  # Refresh every second
    # Use a custom refresh handler to update specific panes at different rates
)
```python

Or use background threads with `invalidate()`:

```python
import threading
from prompt_toolkit.application import get_app

def background_updater():
    """Background thread to update pane content."""
    while True:
        time.sleep(2)  # Update every 2 seconds
        app = get_app()
        if app:
            # Invalidate specific panes to trigger refresh
            app.invalidate()
```python

## Integration with Existing Code

### Reuse Existing Modules

1. **Database**: Use `get_database()` and `get_stats()` from `database.py`
2. **Visibility**: Use `filter_visible_objects()` from `visibility.py`
3. **Observer**: Use `get_observer_location()` from `observer.py`
4. **Optics**: Use `get_current_configuration()` from `optics.py`
5. **Position Tracking**: Integrate with existing `PositionTracker` class

### New Components Needed

1. **TUI Application Module**: `src/celestron_nexstar/cli/tui.py`
   - Main Application class
   - Layout construction
   - Content generators
   - Update handlers

2. **Weather Integration** (if not already exists):
   - Weather API client
   - Forecast caching
   - See `WHATS_VISIBLE_TONIGHT_PLAN.md` for details

3. **Content Formatters**:
   - Format database stats as formatted text
   - Format conditions as formatted text
   - Format visible objects list as formatted text

## File Structure

```text
src/celestron_nexstar/cli/
├── tui.py              # Main TUI application
├── tui/
│   ├── __init__.py
│   ├── panes.py        # Pane content generators
│   ├── layout.py       # Layout construction
│   ├── bindings.py     # Key bindings
│   └── updates.py       # Update handlers
└── commands/
    └── dashboard.py    # CLI command to launch TUI
````

## Implementation Phases

### Phase 1: Basic Layout (Week 1)

- [ ] Create basic Application with three panes
- [ ] Implement static content in each pane
- [ ] Add basic key bindings (quit, refresh)
- [ ] Test layout and sizing

### Phase 2: Dynamic Content (Week 1-2)

- [ ] Connect dataset pane to database stats
- [ ] Connect conditions pane to observer/time data
- [ ] Connect visible objects pane to visibility calculations
- [ ] Implement auto-refresh mechanism

### Phase 3: Interactivity (Week 2)

- [ ] Add sorting to visible objects pane
- [ ] Add filtering to visible objects pane
- [ ] Add pane focus cycling
- [ ] Add scroll support for visible objects

### Phase 4: Weather Integration (Week 2-3)

- [ ] Integrate weather API (if available)
- [ ] Display weather conditions
- [ ] Add weather-based visibility warnings

### Phase 5: Advanced Features (Week 3)

- [ ] Add object selection and goto functionality
- [ ] Add search dialog
- [ ] Add settings/configuration dialog
- [ ] Add help overlay

## Example Usage

```bash
# Launch full-screen TUI
nexstar dashboard

# Or with options
nexstar dashboard --port /dev/ttyUSB0
```

## Key Features

1. **Real-time Updates**: All panes update automatically
2. **Keyboard Navigation**: Full keyboard control
3. **Scrollable Lists**: Handle large object lists efficiently
4. **Color Coding**: Use colors to indicate status (good/bad conditions, etc.)
5. **Responsive Layout**: Adapts to terminal size
6. **Integration**: Works with existing telescope connection and tracking

## Technical Considerations

1. **Performance**:

   - Cache database queries (update every 5s, not every refresh)
   - Limit visible objects list to top 50-100
   - Use lazy evaluation for expensive calculations

2. **Threading**:

   - Use background threads for slow operations (weather API)
   - Use `invalidate()` to trigger UI updates from threads
   - Be careful with thread safety

3. **Error Handling**:

   - Gracefully handle missing data (no location, no connection, etc.)
   - Show error messages in panes when appropriate
   - Don't crash on API failures

4. **Testing**:
   - Test with different terminal sizes
   - Test with missing data sources
   - Test keyboard navigation
   - Test refresh performance

## References

- [prompt_toolkit Full-Screen Applications](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/full_screen_apps.html)
- [prompt_toolkit Layout Documentation](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/layout.html)
- [prompt_toolkit Key Bindings](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/key_bindings.html)
