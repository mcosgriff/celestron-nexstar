# Interactive Sky Map Implementation Plan

## Overview

The Interactive Sky Map is a real-time visualization of the night sky showing the current telescope position, celestial objects, and constellation lines. Users can click on objects to select and goto them, making it an intuitive way to explore and navigate the sky.

## Status

- ⬜ Not Started
- 🚧 In Progress
- ✅ Completed

---

## Goals

1. **Real-time Sky View**: Display current sky view based on observer location and time
2. **Telescope Position Indicator**: Show current telescope pointing direction
3. **Object Overlay**: Display celestial objects (stars, planets, deep-sky objects) on the map
4. **Interactive Selection**: Click on objects to select and goto them
5. **Constellation Visualization**: Draw constellation lines and labels
6. **Coordinate System Support**: Support both Alt/Az (horizontal) and RA/Dec (equatorial) views

---

## Technical Architecture

### Technology Stack

#### Option 1: Matplotlib (Recommended for MVP)
**Pros:**
- Already used in codebase (tracking history graph)
- Excellent for 2D plotting and coordinate transformations
- Good documentation and community support
- Can be embedded in Qt widgets via `FigureCanvasQTAgg`
- Supports polar projections (useful for sky maps)

**Cons:**
- Less interactive than native Qt widgets
- Performance may be slower for frequent updates
- Click detection requires coordinate transformation

**Implementation:**
- Use `matplotlib.figure.Figure` with polar projection
- Embed via `matplotlib.backends.backend_qtagg.FigureCanvasQTAgg`
- Use `matplotlib.patches` for constellation lines
- Use `matplotlib.scatter` for stars/objects
- Handle mouse events via `mpl_connect`

#### Option 2: PyQtGraph
**Pros:**
- Built for Qt, native integration
- Excellent performance for real-time updates
- Built-in interactive features
- Good for scatter plots and line drawing

**Cons:**
- New dependency (not currently in project)
- Less astronomy-specific features
- Requires manual coordinate transformations

#### Option 3: Custom Qt Graphics
**Pros:**
- Full control over rendering
- Native Qt performance
- No additional dependencies

**Cons:**
- More development time
- Manual implementation of all features
- Complex coordinate transformations

**Recommendation**: Start with **Matplotlib** for MVP, consider PyQtGraph for performance optimization later.

### Coordinate Systems

The sky map needs to support two coordinate systems:

1. **Horizontal (Alt/Az)**: 
   - Natural for observers (altitude/azimuth)
   - Changes with time and location
   - Use polar projection (azimuth = angle, altitude = radius)

2. **Equatorial (RA/Dec)**:
   - Fixed relative to stars
   - Standard for astronomy
   - Use rectangular or polar projection

**Implementation:**
- Toggle between coordinate systems via UI button
- Use existing `ra_dec_to_alt_az()` and `alt_az_to_ra_dec()` utilities
- Store current coordinate system preference

### Data Sources

1. **Telescope Position**:
   - `telescope.get_position_ra_dec()` - Current RA/Dec
   - `telescope.get_position_alt_az()` - Current Alt/Az (if available)
   - Convert between systems as needed

2. **Celestial Objects**:
   - Stars: Query database for stars within visible FOV
   - Planets: Use `get_planetary_position()` from ephemeris API
   - Deep-sky objects: Query catalog database (Messier, NGC, etc.)
   - Filter by magnitude based on current viewing conditions

3. **Constellation Data**:
   - `ConstellationModel` from database (already has boundaries)
   - Constellation lines: Need star-to-star connections data
   - Labels: Use constellation names/abbreviations

4. **Constellation Lines**:
   - **Challenge**: Need star-to-star connection data
   - **Options**:
     a. Use existing constellation boundary data (approximate)
     b. Import constellation line data (e.g., from HYG database)
     c. Use star catalog with constellation membership
   - **Recommendation**: Start with boundary visualization, add proper lines later

---

## UI/UX Design

### Window Layout

```
┌─────────────────────────────────────────────────────────┐
│  [Alt/Az] [RA/Dec]  [Zoom In] [Zoom Out] [Reset] [Now] │
├─────────────────────────────────────────────────────────┤
│                                                         │
│                    Sky Map Canvas                       │
│                                                         │
│              (Interactive clickable area)               │
│                                                         │
│                                                         │
├─────────────────────────────────────────────────────────┤
│  Selected: M42 (Orion Nebula)  [Goto] [Info]          │
└─────────────────────────────────────────────────────────┘
```

### Controls

1. **Coordinate System Toggle**: Switch between Alt/Az and RA/Dec views
2. **Zoom Controls**: Zoom in/out, reset to default view
3. **Time Controls**: 
   - "Now" button to jump to current time
   - Time slider to view past/future positions
   - Animation toggle for time progression
4. **View Options**:
   - Toggle constellation lines
   - Toggle constellation labels
   - Toggle object labels
   - Magnitude limit slider
   - Show/hide object types (stars, planets, deep-sky)

### Interaction

1. **Click to Select**: Click on any object to select it
2. **Right-click Menu**: Context menu with options:
   - Goto object
   - Show object info
   - Add to favorites
   - Add to goto queue
3. **Drag to Pan**: Click and drag to pan the view
4. **Scroll to Zoom**: Mouse wheel to zoom in/out
5. **Hover Tooltips**: Show object name and basic info on hover

### Visual Elements

1. **Stars**: 
   - Size based on magnitude (brighter = larger)
   - Color based on spectral type (optional)
   - Minimum size for visibility

2. **Planets**:
   - Distinct markers (circles with symbols)
   - Labels always visible
   - Current position highlighted

3. **Deep-sky Objects**:
   - Different markers by type (galaxy, nebula, cluster)
   - Size based on apparent size (if available)
   - Labels on hover or when selected

4. **Constellation Lines**:
   - Thin lines connecting major stars
   - Color: Light gray (dark theme) / Dark gray (light theme)
   - Optional: Fade lines for less prominent constellations

5. **Constellation Labels**:
   - Constellation name or abbreviation
   - Positioned at constellation center
   - Font size based on zoom level

6. **Telescope Position**:
   - Crosshair or arrow indicator
   - Distinct color (e.g., red or green)
   - Label: "Telescope" or "Scope"
   - Optional: FOV circle showing field of view

7. **Horizon**:
   - For Alt/Az view: Show horizon line (altitude = 0°)
   - Gray out area below horizon
   - Optional: Show cardinal directions (N, S, E, W)

---

## Implementation Phases

### Phase 1: Basic Sky Map Widget (Week 1-2)

**Goals:**
- Create basic matplotlib-based sky map widget
- Display stars in Alt/Az coordinate system
- Basic zoom and pan functionality

**Tasks:**
1. Create `SkyMapWidget` class extending `QWidget`
2. Embed matplotlib figure with polar projection
3. Query and display stars from database
4. Implement coordinate conversion (RA/Dec → Alt/Az)
5. Add zoom controls (mouse wheel, buttons)
6. Add pan controls (click and drag)

**Deliverables:**
- Basic sky map showing stars
- Zoom and pan working
- Stars positioned correctly in Alt/Az coordinates

### Phase 2: Telescope Position and Object Overlay (Week 2-3)

**Goals:**
- Show current telescope position
- Overlay planets and deep-sky objects
- Click detection for object selection

**Tasks:**
1. Integrate telescope position updates
2. Add planets to display (use ephemeris API)
3. Add deep-sky objects (Messier, NGC, etc.)
4. Implement click detection (pixel → sky coordinates)
5. Object selection highlighting
6. Object info display panel

**Deliverables:**
- Telescope position indicator
- Planets and deep-sky objects visible
- Click to select objects working

### Phase 3: Constellation Visualization (Week 3-4)

**Goals:**
- Draw constellation lines
- Add constellation labels
- Toggle visibility options

**Tasks:**
1. Import or generate constellation line data
2. Draw lines connecting stars
3. Add constellation labels
4. Implement toggle controls
5. Style lines based on theme

**Deliverables:**
- Constellation lines and labels visible
- Toggle controls working
- Proper styling for light/dark themes

### Phase 4: Interactive Features (Week 4-5)

**Goals:**
- Goto functionality
- Context menus
- Time controls
- RA/Dec coordinate system support

**Tasks:**
1. Implement "Goto" button integration
2. Add right-click context menu
3. Add time controls (now, slider, animation)
4. Implement RA/Dec coordinate system view
5. Coordinate system toggle
6. Time-based position updates

**Deliverables:**
- Full interactive functionality
- Goto integration working
- Time controls functional
- Both coordinate systems supported

### Phase 5: Polish and Optimization (Week 5-6)

**Goals:**
- Performance optimization
- UI polish
- Additional features
- Integration with main window

**Tasks:**
1. Optimize rendering performance
2. Add FOV circle for telescope
3. Add magnitude limit controls
4. Add object type filters
5. Integrate with main window (menu/toolbar)
6. Add keyboard shortcuts
7. Theme support (light/dark/dark sky)
8. Save/load view preferences

**Deliverables:**
- Polished, performant sky map
- Full integration with application
- All planned features complete

---

## Technical Challenges

### 1. Constellation Line Data

**Problem**: Need star-to-star connection data for drawing constellation lines.

**Solutions**:
- **Option A**: Use HYG (Harvard-Yale-Globe) database which includes constellation line data
- **Option B**: Use simplified boundary-based visualization initially
- **Option C**: Manually define major constellation lines (88 constellations × ~5-10 lines each)

**Recommendation**: Start with Option B (boundaries), add proper lines in Phase 3 using HYG data.

### 2. Performance with Many Objects

**Problem**: Rendering thousands of stars and objects may be slow.

**Solutions**:
- Limit objects by magnitude (only show stars brighter than limit)
- Limit objects by FOV (only render visible area)
- Use level-of-detail (LOD) - fewer objects when zoomed out
- Cache rendered objects
- Use efficient data structures (spatial indexing)

**Implementation**:
- Query database with magnitude and position filters
- Use matplotlib's efficient scatter plotting
- Implement viewport culling

### 3. Coordinate Transformations

**Problem**: Converting between pixel coordinates, sky coordinates, and display coordinates.

**Solutions**:
- Use matplotlib's built-in coordinate transformations
- Create helper functions for coordinate conversion
- Cache transformation matrices when possible

**Implementation**:
- Use `ax.transData` for data-to-pixel conversion
- Use `ax.transAxes` for axes-to-pixel conversion
- Handle polar projection special cases

### 4. Real-time Updates

**Problem**: Telescope position and planet positions change over time.

**Solutions**:
- Use QTimer for periodic updates (e.g., every 1-5 seconds)
- Only update when window is visible
- Debounce rapid position changes
- Use async/await for non-blocking updates

**Implementation**:
- Connect to telescope position tracker
- Update display on position change signals
- Use `_run_async_safe()` helper for async operations

### 5. Click Detection Accuracy

**Problem**: Accurately detecting which object was clicked, especially when objects overlap.

**Solutions**:
- Use distance-based selection (closest object to click)
- Prioritize brighter/larger objects
- Show selection radius
- Allow zooming in for precise selection

**Implementation**:
- Convert click pixel to sky coordinates
- Calculate distances to all nearby objects
- Select closest object within threshold

---

## File Structure

```
src/celestron_nexstar/gui/
├── widgets/
│   └── sky_map_widget.py          # Main sky map widget
├── windows/
│   └── sky_map_window.py          # Sky map window (optional, or embed in main window)
└── dialogs/
    └── sky_map_settings_dialog.py # Settings for sky map (optional)
```

### Key Classes

1. **`SkyMapWidget(QWidget)`**:
   - Main widget containing the sky map
   - Manages matplotlib figure and canvas
   - Handles user interactions
   - Updates display based on telescope position

2. **`SkyMapRenderer`** (optional helper class):
   - Handles rendering logic
   - Manages object data
   - Performs coordinate transformations

3. **`SkyMapSettings`** (dataclass):
   - Stores view preferences
   - Coordinate system
   - Zoom level
   - Visibility toggles
   - Magnitude limits

---

## Dependencies

### Required (Already in Project)
- `matplotlib>=3.8.0` (for plotting)
- `PySide6` (Qt bindings)
- `astropy` (coordinate transformations)
- `numpy` (numerical operations)

### Optional (May Need to Add)
- `pyqtgraph` (if switching from matplotlib for performance)
- Constellation line data source (HYG database or similar)

---

## Integration Points

### Main Window
- Add "Sky Map" menu item in View menu or toolbar
- Open sky map as dockable window or separate window
- Sync selection with main object table

### Telescope Control
- Connect to telescope position updates
- Send goto commands when user clicks "Goto"
- Display current telescope position

### Catalog/Objects
- Use same object data sources
- Share object selection state
- Integrate with favorites system

### Theme System
- Support light/dark/dark sky themes
- Adjust colors for night vision (red theme)
- Theme-aware constellation lines and labels

---

## Future Enhancements

1. **3D View**: Optional 3D perspective view
2. **Animation**: Time-lapse animation of sky movement
3. **FOV Overlay**: Show eyepiece/camera field of view
4. **Search Integration**: Search for objects and highlight on map
5. **Print/Export**: Export sky map as image
6. **Mobile View**: Optimized view for tablet/mobile devices
7. **AR Overlay**: Augmented reality overlay (future)
8. **Multi-object Selection**: Select multiple objects for planning
9. **Trails**: Show object movement trails over time
10. **Satellite Overlay**: Show ISS and other satellites

---

## Success Criteria

1. ✅ Sky map displays stars correctly in Alt/Az coordinates
2. ✅ Telescope position is visible and updates in real-time
3. ✅ Users can click on objects to select them
4. ✅ Goto functionality works from sky map
5. ✅ Constellation lines and labels are visible
6. ✅ Performance is acceptable (< 100ms update time)
7. ✅ Works with light/dark/dark sky themes
8. ✅ Integrates seamlessly with main application

---

## References

- [Matplotlib Polar Projection](https://matplotlib.org/stable/gallery/pie_and_polar_charts/polar_demo.html)
- [HYG Database](https://github.com/astronexus/HYG-Database) - Star catalog with constellation data
- [IAU Constellation Boundaries](https://www.iau.org/public/themes/constellations/)
- [Astropy Coordinates](https://docs.astropy.org/en/stable/coordinates/)

---

## Last Updated

2025-12-05


