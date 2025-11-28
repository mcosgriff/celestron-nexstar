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

### ⬜ Goto Queue/Sequence

- Queue multiple objects for automatic slewing
- Auto-advance after a timer
- Sequence planning for efficient observing

### ⬜ Tracking History Graph

- Real-time graph of telescope position (RA/Dec or Alt/Az)
- Visualize tracking accuracy
- Export tracking data

### ⬜ Alignment Assistant

- Step-by-step alignment wizard
- Visual guides for star selection
- Alignment quality indicators

---

## Data and Information

### ⬜ Object Comparison Tool

- Side-by-side comparison of objects
- Compare magnitude, size, difficulty, etc.
- Help choose between similar objects

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

### ⬜ Dark Sky Mode

- Red-light mode for night use
- Minimal UI mode
- Screen dimming controls

### ⬜ Customizable Layouts

- Save/load window layouts
- Dockable panels
- Multiple monitor support

### ✅ Resizable Table Columns

- ✅ All table columns are resizable
- ✅ Minimum column widths based on header text
- ✅ Columns auto-size to content on initial load
- ✅ User can manually resize to preferred widths

### ⬜ Search Improvements

- Recent searches
- Search suggestions
- Advanced filters (magnitude range, object type, etc.)

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

### ⬜ Goto Queue

- Simple object queue
- Manual advance through queue

### ⬜ Dark Sky Mode

- Red-light theme option
- Minimal UI mode

---

## Notes

- Features marked as "TODO" in the code should be prioritized
- Quick wins can provide immediate value with minimal effort
- Consider user feedback when prioritizing features
- Some features may require additional dependencies or libraries

---

## Last Updated

2025-02-01
