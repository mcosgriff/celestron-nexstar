# Installation Guide - Celestron NexStar Python API

## Prerequisites

- Python 3.8 or later
- Poetry (Python dependency manager)
- USB connection to Celestron NexStar 6SE telescope

## Installing Poetry

If you don't have Poetry installed:

```zsh
# Install Poetry
curl -sSL https://install.python-poetry.org | python3 -

# Or using Homebrew on macOS
brew install poetry
```

## Installation Methods

### Option 1: Install from Source (Development)

```zsh
# Clone or navigate to the project directory
cd Celestron/python

# Install dependencies and package in development mode
poetry install

# This creates a virtual environment and installs:
# - celestron-nexstar package (editable)
# - All runtime dependencies
# - All development dependencies (tests, linters, etc.)
```

### Option 2: Install as User (Production)

```zsh
# Install only runtime dependencies
poetry install --only main

# Or build and install the wheel
poetry build
pip install dist/celestron_nexstar-0.1.0-py3-none-any.whl
```

## Verifying Installation

```zsh
# Activate the Poetry virtual environment
poetry shell

# Try importing the package
python -c "from celestron_nexstar import NexStarTelescope; print('Success!')"

# Run the demo script
poetry run nexstar-demo

# Or
python -m celestron_nexstar.examples.basic_demo
```

## Running Tests

```zsh
# Run all tests with coverage
poetry run pytest

# Run specific test file
poetry run pytest tests/test_nexstar_api.py

# Run with verbose output
poetry run pytest -v

# Generate HTML coverage report
poetry run pytest --cov-report=html
open htmlcov/index.html
```

## Development Setup

For development work:

```zsh
# Install with all dev dependencies
poetry install

# Install pre-commit hooks (if configured)
poetry run pre-commit install

# Run linters
poetry run black src tests
poetry run isort src tests
poetry run flake8 src tests
poetry run mypy src
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
poetry show

# Add a new dependency
poetry add package-name

# Add a development dependency
poetry add --group dev package-name

# Update dependencies
poetry update

# Export requirements.txt (for compatibility)
poetry export -f requirements.txt --output requirements.txt
```

## Building Distribution

```zsh
# Build wheel and sdist
poetry build

# Outputs created in dist/:
# - celestron_nexstar-0.1.0-py3-none-any.whl
# - celestron_nexstar-0.1.0.tar.gz
```

## Publishing (Future)

```zsh
# Configure PyPI credentials
poetry config pypi-token.pypi <your-token>

# Publish to PyPI
poetry publish --build
```

## Troubleshooting

### Poetry Not Found

```zsh
# Add Poetry to PATH
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### Import Errors

```zsh
# Make sure you're in the Poetry environment
poetry shell

# Or run with poetry run
poetry run python your_script.py
```

### Serial Port Permission Denied (Linux)

```zsh
sudo usermod -a -G dialout $USER
# Log out and back in for changes to take effect
```

### Tests Failing

```zsh
# Ensure all dev dependencies are installed
poetry install

# Check Python version
python --version  # Should be 3.8+

# Run tests with more verbosity
poetry run pytest -vv
```

## Uninstallation

```zsh
# Remove the Poetry environment
poetry env remove python

# Or remove the entire virtual environment directory
rm -rf $(poetry env info --path)
```

## Additional Resources

- [Poetry Documentation](https://python-poetry.org/docs/)
- [Project README](README.md)
- [API Documentation](https://your-docs-site.com)
