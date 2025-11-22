# GUI Implementation Plan - PySide6 (Qt6)

## Overview

This document outlines the plan to implement a modern GUI application using PySide6 (Qt6) for the Celestron NexStar telescope control system. The plan includes:

1. **Refactoring Phase**: Moving reusable logic from CLI to API
2. **GUI Architecture**: PySide6 application structure and components
3. **Implementation Roadmap**: Step-by-step development plan

## Phase 1: Refactor CLI Logic to API

### 1.1 Time Formatting Utilities

**Current State**: Time formatting functions are duplicated across multiple CLI command files:

- `_get_local_timezone()` - duplicated in `telescope.py`, `binoculars.py`, `naked_eye.py`, `multi_night.py`, `iss.py`
- `_format_local_time()` - duplicated in same files

**Action**: Create centralized time formatting utilities in API

**Location**: `src/celestron_nexstar/api/core/utils.py` (or new `src/celestron_nexstar/api/core/time_utils.py`)

**Functions to Add**:

```python
def get_local_timezone(lat: float, lon: float) -> ZoneInfo | None:
    """Get timezone for a given latitude and longitude."""

def format_local_time(dt: datetime, lat: float, lon: float) -> str:
    """Format datetime in local timezone, falling back to UTC if timezone unavailable."""
```

**Benefits**:

- Eliminates code duplication
- Reusable by both CLI and GUI
- Easier to test and maintain

### 1.2 Export Filename Generation

**Current State**: Export filename generation is duplicated with variations across many CLI command files:

- `_generate_export_filename()` - duplicated in 15+ command files with slight variations

**Action**: Create centralized export utilities in API

**Location**: `src/celestron_nexstar/api/core/export_utils.py` (new file)

**Functions to Add**:

```python
def generate_export_filename(
    command: str,
    viewing_type: str = "telescope",
    binocular_model: str | None = None,
    location: ObserverLocation | None = None,
    date_suffix: str = "",
    **kwargs
) -> Path:
    """Generate standardized export filename based on command, equipment, location, and date."""
```

**Benefits**:

- Consistent filename generation across CLI and GUI
- Single source of truth for export naming conventions
- Easier to extend with new export formats

### 1.3 Data Formatting Utilities

**Current State**: Some formatting logic is embedded in CLI commands (e.g., coordinate formatting, magnitude formatting)

**Action**: Review and extract reusable formatting functions to API

**Location**: `src/celestron_nexstar/api/core/formatting.py` (new file)

**Functions to Consider**:

- Coordinate formatting (RA/Dec, Alt/Az)
- Magnitude formatting
- Time duration formatting
- Distance formatting

**Benefits**:

- Consistent formatting across CLI and GUI
- Easier to localize in the future
- Better separation of concerns

## Phase 2: PySide6 GUI Architecture

### 2.1 Project Structure

```text
src/celestron_nexstar/
├── api/                    # Existing API (business logic)
├── cli/                    # Existing CLI (keep for backward compatibility)
└── gui/                    # New GUI module
    ├── __init__.py
    ├── main.py             # Application entry point
    ├── main_window.py      # Main application window
    ├── widgets/            # Custom Qt widgets
    │   ├── __init__.py
    │   ├── telescope_control.py
    │   ├── observation_planner.py
    │   ├── catalog_browser.py
    │   ├── sky_chart.py
    │   ├── conditions_panel.py
    │   └── events_calendar.py
    ├── dialogs/            # Dialog windows
    │   ├── __init__.py
    │   ├── connection_dialog.py
    │   ├── location_dialog.py
    │   ├── optics_config_dialog.py
    │   └── object_search_dialog.py
    ├── models/             # Qt data models
    │   ├── __init__.py
    │   ├── catalog_model.py
    │   ├── observation_list_model.py
    │   └── events_model.py
    ├── resources/          # Qt resources (icons, UI files)
    │   ├── icons/
    │   └── styles/
    └── utils/              # GUI-specific utilities
        ├── __init__.py
        ├── async_worker.py
        └── theme.py
```

### 2.2 Core Components

#### 2.2.1 Main Application (`gui/main.py`)

**Responsibilities**:

- Initialize Qt application
- Set up application-wide settings (theme, style, etc.)
- Handle application lifecycle
- Manage global state

**Key Features**:

- Dark theme support (astronomy-friendly)
- Application-wide keyboard shortcuts
- Settings persistence
- Error handling and logging

#### 2.2.2 Main Window (`gui/main_window.py`)

**Layout**: Tabbed interface with dockable panels

**Main Tabs**:

1. **Telescope Control** - Connection, movement, alignment
2. **Observation Planner** - Tonight's viewing, multi-night planning
3. **Catalog Browser** - Search and browse celestial objects
4. **Sky Chart** - Interactive star chart
5. **Events Calendar** - Celestial events, meteor showers, etc.
6. **Settings** - Configuration management

**Dockable Panels**:

- **Conditions Panel** - Weather, seeing conditions, moon phase
- **Position Monitor** - Current telescope position (RA/Dec, Alt/Az)
- **Object Details** - Selected object information

#### 2.2.3 Telescope Control Widget (`gui/widgets/telescope_control.py`)

**Features**:

- Connection status indicator
- Serial port/TCP connection selection
- Position display (RA/Dec, Alt/Az)
- Movement controls (arrow buttons, rate selection)
- Goto controls (object search, coordinate entry)
- Tracking mode selection
- Alignment tools

**API Integration**:

- Uses `celestron_nexstar.api.telescope.*`
- Async operations for non-blocking UI

#### 2.2.4 Observation Planner Widget (`gui/widgets/observation_planner.py`)

**Features**:

- Tonight's conditions summary
- Recommended objects list (filterable, sortable)
- Object details panel
- Multi-night comparison view
- Export functionality

**API Integration**:

- Uses `celestron_nexstar.api.observation.*`
- Real-time updates based on current time

#### 2.2.5 Catalog Browser Widget (`gui/widgets/catalog_browser.py`)

**Features**:

- Search bar with autocomplete
- Catalog selection (Messier, NGC, planets, etc.)
- Filterable table view (type, magnitude, etc.)
- Object details on selection
- Quick "Goto" button integration

**API Integration**:

- Uses `celestron_nexstar.api.catalogs.*`
- Uses `celestron_nexstar.api.database.*`

#### 2.2.6 Sky Chart Widget (`gui/widgets/sky_chart.py`)

**Features**:

- Interactive star chart (using existing skyfield/astropy calculations)
- Current telescope position indicator
- Object selection on click
- Zoom and pan controls
- Time controls (current, specific time, animation)

**Implementation Notes**:

- Consider using `matplotlib` or `PyQtGraph` for rendering
- Or integrate with existing astronomy visualization libraries

#### 2.2.7 Conditions Panel (`gui/widgets/conditions_panel.py`)

**Features**:

- Weather summary (temperature, cloud cover, etc.)
- Seeing conditions score
- Moon phase and position
- Light pollution level
- Best viewing time windows

**API Integration**:

- Uses `celestron_nexstar.api.observation.observation_planner`
- Uses `celestron_nexstar.api.location.weather`

### 2.3 Data Models

#### 2.3.1 Catalog Model (`gui/models/catalog_model.py`)

**Purpose**: Provide Qt model for catalog data in table views

**Features**:

- Filterable and sortable
- Lazy loading for large catalogs
- Search integration

#### 2.3.2 Observation List Model (`gui/models/observation_list_model.py`)

**Purpose**: Manage list of recommended objects for observation

**Features**:

- Dynamic updates based on time
- Sorting by various criteria (altitude, magnitude, etc.)
- Custom roles for display formatting

### 2.4 Dialogs

#### 2.4.1 Connection Dialog (`gui/dialogs/connection_dialog.py`)

**Features**:

- Serial port selection (with auto-detection)
- TCP/IP connection options
- Connection testing
- Connection history

#### 2.4.2 Location Dialog (`gui/dialogs/location_dialog.py`)

**Features**:

- Location search (geocoding)
- Coordinate entry
- Elevation input
- Location presets

#### 2.4.3 Optics Config Dialog (`gui/dialogs/optics_config_dialog.py`)

**Features**:

- Telescope model selection
- Eyepiece configuration
- Performance calculations display

#### 2.4.4 Object Search Dialog (`gui/dialogs/object_search_dialog.py`)

**Features**:

- Quick object search
- Autocomplete suggestions
- Object preview
- Direct goto integration

### 2.5 Async Operations

**Challenge**: Many API operations are blocking (database queries, network requests, telescope communication)

**Solution**: Use Qt's async capabilities with worker threads

**Implementation** (`gui/utils/async_worker.py`):

- `AsyncWorker` class using `QThread` and `QObject` signals
- Progress reporting via signals
- Error handling via signals
- Cancellation support

**Usage Pattern**:

```python
worker = AsyncWorker(api_function, *args, **kwargs)
worker.progress.connect(update_progress_bar)
worker.finished.connect(handle_results)
worker.error.connect(handle_error)
worker.start()
```

## Phase 3: Implementation Roadmap

### 3.1 Phase 1: Foundation (Week 1-2)

**Tasks**:

1. ✅ Move time formatting utilities to API
2. ✅ Move export filename generation to API
3. ✅ Extract reusable formatting functions
4. ✅ Update CLI commands to use new API functions
5. ✅ Add PySide6 to dependencies
6. ✅ Create basic GUI project structure
7. ✅ Implement main application entry point
8. ✅ Create basic main window with tab structure

**Deliverables**:

- Refactored API with new utility functions
- Basic GUI skeleton
- Application launches and displays main window

### 3.2 Phase 2: Core Telescope Control (Week 3-4)

**Tasks**:

1. Implement connection dialog
2. Implement telescope control widget
3. Add position monitoring
4. Implement movement controls
5. Add goto functionality
6. Implement tracking mode controls
7. Add error handling and status indicators

**Deliverables**:

- Functional telescope connection and control
- Real-time position display
- Basic movement and goto operations

### 3.3 Phase 3: Observation Planning (Week 5-6)

**Tasks**:

1. Implement conditions panel
2. Create observation planner widget
3. Add object recommendation list
4. Implement object details view
5. Add filtering and sorting
6. Integrate with telescope control (goto from list)

**Deliverables**:

- Functional observation planning interface
- Integration with telescope control

### 3.4 Phase 4: Catalog Browser (Week 7-8)

**Tasks**:

1. Implement catalog browser widget
2. Create catalog data model
3. Add search functionality
4. Implement filtering
5. Add object details panel
6. Integrate with telescope control

**Deliverables**:

- Functional catalog browser
- Search and filter capabilities
- Object selection and goto

### 3.5 Phase 5: Events and Calendar (Week 9-10)

**Tasks**:

1. Implement events calendar widget
2. Add event types (meteors, eclipses, ISS, etc.)
3. Create event details view
4. Add filtering by event type
5. Integrate with observation planner

**Deliverables**:

- Functional events calendar
- Event details and filtering

### 3.6 Phase 6: Sky Chart (Week 11-12)

**Tasks**:

1. Research and select chart rendering library
2. Implement basic sky chart widget
3. Add star rendering
4. Add object overlay
5. Implement telescope position indicator
6. Add zoom and pan controls
7. Add time controls

**Deliverables**:

- Interactive sky chart
- Telescope position visualization

### 3.7 Phase 7: Polish and Integration (Week 13-14)

**Tasks**:

1. Implement settings dialog
2. Add theme support (dark/light)
3. Add keyboard shortcuts
4. Implement export functionality
5. Add help/documentation
6. Performance optimization
7. Error handling improvements
8. User testing and feedback

**Deliverables**:

- Polished, production-ready GUI
- Complete feature set
- Documentation

## Phase 4: Technical Considerations

### 4.1 Dependencies

**Add to `pyproject.toml`**:

```toml
dependencies = [
    # ... existing dependencies ...
    "PySide6>=6.6.0",  # Qt6 Python bindings
]

[project.optional-dependencies]
gui = [
    "PySide6>=6.6.0",
    "matplotlib>=3.8.0",  # For sky chart (if needed)
]
```

**Note**: Consider making GUI dependencies optional to keep CLI-only installations lightweight.

### 4.2 Application Entry Point

**New script in `pyproject.toml`**:

```toml
[project.scripts]
nexstar = "celestron_nexstar.cli.main:app"
nexstar-gui = "celestron_nexstar.gui.main:main"
```

### 4.3 Threading Model

**Guidelines**:

- All API calls that may block should run in worker threads
- Use Qt signals/slots for thread-safe communication
- Never update UI from worker threads directly
- Use `QMetaObject.invokeMethod` or signals for UI updates

### 4.4 State Management

**Approach**:

- Use Qt's property system for observable state
- Centralized application state in main window or separate state manager
- Persist settings using `QSettings`

### 4.5 Error Handling

**Strategy**:

- Use Qt's message boxes for user-facing errors
- Log all errors to file and console
- Provide helpful error messages with recovery suggestions
- Handle telescope disconnection gracefully

### 4.6 Testing

**Approach**:

- Unit tests for GUI utilities and models
- Integration tests for widget functionality
- Mock API calls for testing without hardware
- UI tests using Qt's test framework (optional)

## Phase 5: Migration Strategy

### 5.1 Backward Compatibility

**Principles**:

- CLI remains fully functional
- No breaking changes to API
- GUI and CLI can coexist
- Shared configuration between CLI and GUI

### 5.2 Configuration Sharing

**Approach**:

- GUI reads from same config files as CLI
- GUI writes to same config files as CLI
- Use existing `ObserverLocation` and `OpticalConfiguration` APIs

### 5.3 Feature Parity

**Initial Goal**: Match core CLI functionality in GUI

- Telescope control
- Observation planning
- Catalog browsing
- Basic events viewing

**Future Enhancements**: GUI-specific features

- Interactive sky chart
- Real-time position tracking
- Visual object selection
- Drag-and-drop planning

## Phase 6: Documentation

### 6.1 User Documentation

**Create**:

- GUI user guide
- Screenshots and walkthroughs
- Keyboard shortcuts reference
- Troubleshooting guide

### 6.2 Developer Documentation

**Create**:

- GUI architecture documentation
- Widget development guide
- API integration examples
- Contributing guidelines for GUI

## Success Criteria

### Phase 1 (Refactoring)

- ✅ All time formatting logic centralized in API
- ✅ All export filename generation centralized in API
- ✅ CLI commands updated to use new API functions
- ✅ All tests passing

### Phase 2-7 (GUI Implementation)

- ✅ GUI application launches successfully
- ✅ Can connect to telescope
- ✅ Can control telescope (move, goto, track)
- ✅ Can view observation recommendations
- ✅ Can browse catalogs
- ✅ Can view celestial events
- ✅ Settings persist between sessions
- ✅ Error handling works correctly
- ✅ Application is responsive (no UI freezing)

## Future Enhancements (Post-MVP)

1. **Advanced Sky Chart**
   - 3D visualization
   - Constellation lines and labels
   - Deep sky object overlays
   - Horizon and coordinate grid

2. **Observation Logging**
   - Session notes
   - Object observation records
   - Photo integration
   - Export to standard formats

3. **Multi-Telescope Support**
   - Manage multiple telescope connections
   - Compare capabilities
   - Coordinate observations

4. **Remote Control**
   - Network telescope control
   - Mobile companion app
   - Web interface

5. **Advanced Planning**
   - Multi-object sequences
   - Automated observation runs
   - Integration with imaging software

## Notes

- This plan assumes a 14-week development timeline, but can be adjusted based on resources
- Some phases can be parallelized (e.g., catalog browser and events calendar)
- Sky chart implementation may require additional research and prototyping
- Consider user feedback early and iterate on design
