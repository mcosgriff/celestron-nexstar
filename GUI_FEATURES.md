# GUI Feature Roadmap

This document tracks potential features and enhancements for the Celestron NexStar GUI application.

## Status Legend

- ⬜ Not Started
- 🚧 In Progress
- ✅ Completed
- ❌ Cancelled/Deferred

---

## Observation Planning and Session Management

### ⬜ Observation Session Planner

- Create and save observing sessions
- Add objects to a session with notes
- Track progress (observed, skipped, notes)
- Export session logs

### ⬜ Checklist Window

- Pre-observation checklist (equipment, alignment, conditions)
- Per-object checklist (filters, eyepieces, notes)
- Session completion tracking
- **Note:** Currently marked as TODO in code

### ⬜ Quick Reference Cards

- Printable reference cards for objects
- Difficulty ratings, equipment needed, best viewing times
- One-page summaries
- **Note:** Currently marked as TODO in code

### ✅ Object Favorites/Bookmarks

- ✅ Star/favorite objects list
- ✅ Quick access from toolbar
- ✅ Context menu to add/remove favorites
- ✅ Star indicator (★) in object tables
- ✅ Dedicated database table with fast indexed lookups
- ✅ Favorites dialog for viewing and managing favorites
- ⬜ Organize by category or custom lists (future enhancement)

---

## Visualization and Sky View

### ⬜ Interactive Sky Map

- Real-time sky view showing current telescope position
- Object positions overlaid
- Click to select and goto objects
- Constellation lines and labels
- **Plan**: See `docs/plans/INTERACTIVE_SKY_MAP_PLAN.md` for detailed implementation plan

### ⬜ Star Chart/Planisphere View

- Rotatable star chart for current time/location
- Highlight visible objects
- Show rise/set times on the chart

### ⬜ 3D Solar System Viewer

- Interactive 3D view of planets and moons
- Current positions and orbits
- Zoom and rotate controls

---

## Telescope Control Enhancements

### ✅ Goto Queue/Sequence

- ✅ Queue multiple objects for automatic slewing
- ✅ Auto-advance after a configurable timer (10-3600 seconds, default 60s)
- ✅ Sequence planning for efficient observing (optimizes order by proximity)
- ✅ Queue management window with drag-and-drop reordering
- ✅ Start/Pause/Stop/Skip controls
- ✅ Status indicators (Current, Done, Pending)
- ✅ Save/Load queue to/from JSON files
- ✅ Integration with main window (context menu "Add to Goto Queue")
- ✅ Automatic slew completion detection
- ✅ Greedy nearest-neighbor algorithm for sequence optimization
- ✅ Considers object altitude for optimal starting point

### ✅ Tracking History Graph

- ✅ Real-time graph of telescope position (RA/Dec or Alt/Az)
- ✅ Visualize tracking accuracy (drift calculation and display)
- ✅ Export tracking data (CSV and JSON formats)
- ✅ Dual coordinate system support (switch between Alt/Az and RA/Dec)
- ✅ Real-time updates with configurable refresh rate
- ✅ Clear history functionality
- ✅ Automatic PositionTracker integration
- ✅ Matplotlib-based visualization with dual subplots

### ✅ Alignment Assistant

- ✅ Step-by-step alignment wizard
- ✅ Visual guides for star selection
- ✅ Alignment quality indicators
- ✅ Support for SkyAlign (3 objects), Two-Star, and One-Star alignment
- ✅ Object suggestions with quality scoring
- ✅ Integration with telescope sync/goto commands
- ✅ Progress tracking and step-by-step instructions

---

## Data and Information

### ✅ Object Comparison Tool

- ✅ Side-by-side comparison of objects
- ✅ Compare magnitude, size, difficulty, visibility, observability, etc.
- ✅ Help choose between similar objects
- ✅ Visual indicators (green=best, red=worst) for comparable attributes
- ✅ Search and add objects to comparison
- ✅ Remove individual objects or clear all
- ✅ Real-time visibility and difficulty assessment
- ✅ Integration with main window (menu and context menu)

### ✅ Observation Log/Journal

- ✅ Record observations with photos/notes
- ✅ Searchable history
- ✅ Statistics (objects observed, hours logged)
- ✅ View, edit, and delete observations
- ✅ Context menu integration to log observations
- ✅ Weather conditions and equipment tracking
- ⬜ Export to standard formats (CSV, JSON) (future enhancement)

### ✅ Equipment Manager

- ✅ Catalog eyepieces, filters, cameras
- ✅ Database storage with usage tracking
- ✅ Field of view calculation API
- ✅ Equipment Manager dialog with tabs for each equipment type
- ✅ View, add, edit, and delete equipment
- ⬜ Add/edit dialogs for equipment (future enhancement)
- ⬜ Enhanced FOV calculator UI (future enhancement)

---

## Real-Time Features

### ✅ Live Data Dashboard

- ✅ Real-time weather, seeing conditions, moon phase
- ✅ Space weather alerts
- ✅ Auto-refresh every 60 seconds
- ✅ Manual refresh button
- ✅ Color-coded indicators for conditions

### ⬜ Notifications/Alerts

- ISS passes, meteor showers, eclipses
- Object transit alerts
- Weather condition changes

### ⬜ Multi-Object Visibility Timeline

- Timeline showing when multiple objects are visible
- Overlap visualization
- Optimal viewing windows

---

## Social and Sharing

### ⬜ Observation Sharing

- Export session reports
- Share object lists
- Community object ratings/reviews

### ⬜ Photo Integration

- Attach photos to observations
- Before/after comparison
- Simple image annotation

---

## Advanced Features

### ⬜ Scripting/Macro Support

- Record and replay telescope movements
- Custom automation scripts
- Scheduled observations

### ⬜ Multi-Telescope Support

- Control multiple telescopes
- Sync positions
- Compare views

### ⬜ Remote Control/Web Interface

- Web-based control panel
- Mobile-friendly interface
- Remote monitoring

### ⬜ Integration with Astrophotography Software

- Connect to PHD2, NINA, etc.
- Sync mount positions
- Coordinate imaging sessions

---

## UI/UX Improvements

### ✅ Dark Sky Mode

- ✅ Red-light theme option for preserving night vision
- ✅ Dark red-black background with red/amber text colors
- ✅ Optimized for night vision preservation (red light ~650nm wavelength)
- ✅ Accessible from View → Theme → Dark Sky Mode
- ✅ Minimal UI mode (separate toggle)
- ⬜ Screen dimming controls (future enhancement)

### ⬜ Customizable Layouts

- Save/load window layouts
- Dockable panels
- Multiple monitor support

### ✅ Resizable Table Columns

- ✅ All table columns are resizable
- ✅ Minimum column widths based on header text
- ✅ Columns auto-size to content on initial load
- ✅ User can manually resize to preferred widths

### ✅ Search Improvements

- ✅ Recent searches (stores up to 20 recent queries in database)
- ✅ Search suggestions/autocomplete (real-time suggestions as you type)
- ✅ Advanced filters (magnitude range, object type, catalog selection)
- ✅ Filter dialog with persistent filter state
- ✅ Integration with catalog search window

### ⬜ Tutorial/Help System

- Interactive tutorials
- Context-sensitive help
- Video guides integration

---

## Quick Wins (Easier to Implement)

These features are prioritized for quick implementation:

### ✅ Object Favorites

- ✅ Simple star/favorites list
- ✅ Quick access from toolbar
- ✅ Context menu integration
- ✅ Star indicators in tables
- ✅ Dedicated database table with fast indexed lookups
- ✅ Context menu integration
- ✅ Star indicators in tables

### ✅ Observation Log

- ✅ Basic note-taking per object
- ✅ Detailed observation logging with conditions, equipment, and ratings
- ✅ View and manage observation history
- ✅ Context menu integration

### ✅ Live Dashboard

- ✅ Real-time conditions widget
- ✅ Weather, moon phase, space weather
- ✅ Auto-refresh functionality

### ✅ Goto Queue

- ✅ Queue management window with full controls
- ✅ Automatic slewing with configurable delay
- ✅ Sequence optimization for efficient observing
- ✅ Save/Load queue persistence
- ✅ Context menu integration

### ✅ Dark Sky Mode & Minimal UI

- ✅ Red-light theme option (Dark Sky Mode)
- ✅ Minimal UI mode toggle (Ctrl+M)
- ✅ Hides menus, toolbars, and status bar for clean interface

---

## Notes

- Features marked as "TODO" in the code should be prioritized
- Quick wins can provide immediate value with minimal effort
- Consider user feedback when prioritizing features
- Some features may require additional dependencies or libraries

---

## Last Updated

2025-12-05

### Recent Updates

- **2025-12-05**: ✅ Completed Dark Sky Mode feature
  - Red-light theme with dark red-black background and red/amber text
  - Optimized for night vision preservation (red light ~650nm wavelength)
  - Accessible from View → Theme → Dark Sky Mode
  - Custom QPalette implementation for consistent red-light appearance

- **2025-12-05**: ✅ Completed Minimal UI Mode feature
  - Toggle to hide/show menus, toolbars, and status bar
  - Keyboard shortcut: Ctrl+M
  - Provides clean, distraction-free interface for observing
  - Accessible from View → Minimal UI Mode

- **2025-12-05**: ✅ Completed Search Improvements feature
  - Recent searches stored in database (up to 20 queries)
  - Real-time search suggestions/autocomplete
  - Advanced filters dialog (magnitude range, object type, catalog)
  - Filter state persistence
  - Integrated with catalog search window

- **2025-02-01**: ✅ Completed Object Comparison Tool feature
  - Side-by-side comparison table with key metrics
  - Visual indicators for best/worst values
  - Search and add objects functionality
  - Real-time visibility and difficulty assessment
  - Integration with context menus

- **2025-02-01**: ✅ Completed Tracking History Graph feature
  - Real-time position tracking with matplotlib graphs
  - Dual coordinate system support (Alt/Az and RA/Dec)
  - Tracking accuracy visualization (drift calculation)
  - Export functionality (CSV and JSON)
  - Integration with PositionTracker API
  - Clear history and real-time updates

- **2025-02-01**: ✅ Completed Alignment Assistant feature
  - Step-by-step wizard for SkyAlign, Two-Star, and One-Star alignment
  - Visual guides with object positions and quality indicators
  - Integration with telescope sync/goto commands
  - Object suggestions with quality scoring

- **2025-02-01**: ✅ Completed Calibration Assistant feature
  - Step-by-step backlash calibration wizard
  - Visual guides with color-coded feedback
  - Axis-specific instructions (Azimuth, Altitude, or Both)

- **2025-02-01**: ✅ Completed Goto Queue/Sequence feature
  - Full queue management with drag-and-drop reordering
  - Auto-advance timer with configurable delay
  - Sequence optimization algorithm
  - Save/Load queue persistence
  - Integration with main window context menus
