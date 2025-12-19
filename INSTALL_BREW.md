# Homebrew Installation Guide for macOS

## Required Packages

### 1. Install Homebrew (if not already installed)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 2. Install uv (Python package manager)

```bash
brew install uv
```

**Note:** `uv` will automatically handle Python 3.11+ installation, so you don't need to install Python separately.

### 3. Install SpatiaLite (required for spatial database features)

```bash
brew install spatialite-tools
```

**Note:** This installs the SpatiaLite extension library (`mod_spatialite.dylib`) that the project needs for spatial queries. The project will automatically find it at `/opt/homebrew/lib/mod_spatialite.dylib` (Apple Silicon) or `/usr/local/lib/mod_spatialite.dylib` (Intel).

**About SQLite:** 
- macOS comes with SQLite built-in, but it may be an older version
- Installing `spatialite-tools` will automatically install a newer SQLite via Homebrew as a dependency
- Python's `sqlite3` module (used by `aiosqlite`) will typically use the system SQLite that came with Python
- For most use cases, the system SQLite is sufficient. If you need newer SQLite features (like DROP COLUMN support, which requires SQLite 3.35.0+), you can explicitly install SQLite via Homebrew, but this is usually not necessary

## Optional Packages (Recommended)

### 4. Install Qt6 (for GUI functionality)

```bash
brew install qt@6
```

**Note:** PySide6 bundles Qt libraries, so this is **optional**. The GUI will work without it. However, installing system Qt via Homebrew provides better system integration, may improve GUI performance, and ensures you have the latest Qt libraries.

If you install Qt6, you can optionally add it to your PATH:

```bash
# For Apple Silicon Macs (M1/M2/M3)
echo 'export PATH="/opt/homebrew/opt/qt@6/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc

# For Intel Macs
echo 'export PATH="/usr/local/opt/qt@6/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

## Installation Summary

**Minimum required (core functionality):**
```bash
brew install uv spatialite-tools
```

**Recommended (with GUI support):**
```bash
brew install uv spatialite-tools qt@6
```

**What each package does:**
- `uv`: Python package manager (handles Python 3.11+ and all Python dependencies)
- `spatialite-tools`: Provides SpatiaLite extension for spatial database queries (constellation boundaries, light pollution data, etc.). This will also install SQLite as a dependency.
- `qt@6`: System Qt libraries for GUI (optional - PySide6 bundles Qt but system Qt provides better integration)

## After Installation

Once you have `uv` installed, you can set up the project:

```bash
# Navigate to the project directory
cd celestron-nexstar

# Install all dependencies (creates .venv automatically)
uv sync --all-extras

# Verify installation
uv run nexstar --help
```

## Troubleshooting

### If geopandas/shapely fail to install

The Python wheels for macOS typically include all necessary libraries. However, if you encounter issues with geospatial packages, you can install system libraries:

```bash
# Install GDAL, GEOS, and PROJ (usually not needed)
brew install gdal geos proj
```

**Note:** This is rarely necessary as the Python wheels include these libraries.

### Verify uv installation

```bash
uv --version
```

### Verify SpatiaLite installation

```bash
# Check if mod_spatialite.dylib exists
ls /opt/homebrew/lib/mod_spatialite.dylib  # Apple Silicon
# OR
ls /usr/local/lib/mod_spatialite.dylib      # Intel
```

### Verify Qt installation (if installed)

```bash
brew list qt@6
```

### SpatiaLite not loading

If you get errors about SpatiaLite not being available:

1. Verify it's installed: `brew list spatialite-tools`
2. Check the library exists at the expected path (see above)
3. The project will automatically try to load it from the standard Homebrew locations
4. You can also set `SPATIALITE_LIBRARY_PATH` environment variable to point to the library if it's in a non-standard location

### SQLite version issues

If you need a newer SQLite version (e.g., for DROP COLUMN support which requires SQLite 3.35.0+):

```bash
# Install SQLite explicitly (spatialite-tools already installs it, but this ensures latest version)
brew install sqlite

# Check SQLite version
sqlite3 --version
```

**Note:** Python's `sqlite3` module uses the SQLite that was compiled with Python. Installing SQLite via Homebrew makes it available for command-line use, but Python will still use its bundled SQLite unless you recompile Python. For most use cases, the system SQLite is sufficient.

## Next Steps

After installing the Homebrew packages, follow the main installation guide in `docs/INSTALL.md` or the README.md for project setup instructions.

