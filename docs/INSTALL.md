# Installation Guide - Celestron NexStar Python API

## Prerequisites

- Python 3.9 or later (tested up to Python 3.14)
- uv (Python package manager)
- USB connection to Celestron NexStar 6SE telescope

## Installing uv

If you don't have uv installed:

```zsh
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or using Homebrew on macOS
brew install uv

# Or using pip
pip install uv
```

## Installation Methods

### Option 1: Install from Source (Development)

```zsh
# Clone or navigate to the project directory
cd celestron-nexstar

# Install dependencies and package in development mode
uv sync --all-extras

# This creates a virtual environment at .venv and installs:
# - celestron-nexstar package (editable)
# - All runtime dependencies
# - All development dependencies (tests, linters, etc.)
```

### Option 2: Install as User (Production)

```zsh
# Install only runtime dependencies
uv sync

# Or build and install the wheel
uv build
pip install dist/celestron_nexstar-0.1.0-py3-none-any.whl
```

## Verifying Installation

```zsh
# Activate the virtual environment
source .venv/bin/activate

# Try importing the package
python -c "from celestron_nexstar import NexStarTelescope; print('Success!')"

# Or run directly with uv
uv run python -c "from celestron_nexstar import NexStarTelescope; print('Success!')"

# Run an example script
uv run python examples/simple_position_tracking.py
```

## Running Tests

```zsh
# Run all tests with coverage
uv run pytest

# Run specific test file
uv run pytest tests/test_nexstar_api.py

# Run with verbose output
uv run pytest -v

# Generate HTML coverage report
uv run pytest --cov-report=html
open htmlcov/index.html
```

## Development Setup

For development work:

```zsh
# Install with all dev dependencies
uv sync --all-extras

# Run linters
uv run black src tests
uv run isort src tests
uv run flake8 src tests
uv run mypy src
```

## Hardware Connection

### Finding Your Serial Port

**macOS:**
```zsh
ls /dev/tty.usbserial*
# Usually: /dev/tty.usbserial-1420 or /dev/tty.usbserial-XXXXX
```

**Linux:**
```zsh
ls /dev/ttyUSB*
# Usually: /dev/ttyUSB0

# Grant permissions
sudo usermod -a -G dialout $USER
# Log out and back in
```

**Windows:**
```
Check Device Manager → Ports (COM & LPT)
Usually: COM3, COM4, etc.
```

### Required Adapters for MacBook

If your MacBook only has USB-C ports:
- **USB-C to USB-A adapter** (~$19, Apple official or third-party)
- Or **USB-C to USB-B cable** (direct connection, $10-15)

## Usage Examples

### Quick Start

```python
from celestron_nexstar import NexStarTelescope, TrackingMode

# Connect
telescope = NexStarTelescope(port='/dev/tty.usbserial-1420')
telescope.connect()

# Get position
ra, dec = telescope.get_position_ra_dec()
print(f"RA: {ra:.4f}h, Dec: {dec:.4f}°")

# Enable tracking
telescope.set_tracking_mode(TrackingMode.ALT_AZ)

# Disconnect
telescope.disconnect()
```

### Using Context Manager

```python
from celestron_nexstar import NexStarTelescope

with NexStarTelescope(port='/dev/tty.usbserial-1420') as telescope:
    ra, dec = telescope.get_position_ra_dec()
    print(f"Position: {ra:.4f}h, {dec:.4f}°")
# Automatically disconnects
```

## Managing Dependencies

```zsh
# Show installed packages
uv pip list

# Add a new dependency
uv add package-name

# Add a development dependency
uv add --dev package-name

# Update dependencies
uv sync --upgrade

# View dependency tree
uv tree
```

## Building Distribution

```zsh
# Build wheel and sdist
uv build

# Outputs created in dist/:
# - celestron_nexstar-0.1.0-py3-none-any.whl
# - celestron_nexstar-0.1.0.tar.gz
```

## Publishing (Future)

```zsh
# Publish to PyPI (requires credentials)
uv publish
```

## Troubleshooting

### uv Not Found

```zsh
# Add uv to PATH (if installed via curl)
echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### Import Errors

```zsh
# Make sure you're in the virtual environment
source .venv/bin/activate

# Or run with uv run
uv run python your_script.py
```

### Serial Port Permission Denied (Linux)

```zsh
sudo usermod -a -G dialout $USER
# Log out and back in for changes to take effect
```

### Tests Failing

```zsh
# Ensure all dev dependencies are installed
uv sync --all-extras

# Check Python version
python --version  # Should be 3.9+

# Run tests with more verbosity
uv run pytest -vv
```

## Uninstallation

```zsh
# Remove the virtual environment
rm -rf .venv

# Remove the lock file
rm uv.lock
```

## Additional Resources

- [uv Documentation](https://docs.astral.sh/uv/)
- [Project README](../README.md)
