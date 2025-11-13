#!/bin/bash
# Run mypy with the same configuration as pre-commit
# This ensures consistency between manual runs and pre-commit hooks
#
# Pre-commit uses mypy v1.18.2 with these additional dependencies:
# - types-pyserial, returns, deal, pyserial, tqdm, sqlalchemy>=2.0.0

set -e

# Ensure we're in the project root
cd "$(dirname "$0")/.."

# Ensure mypy plugins are installed (matching pre-commit additional_dependencies)
# These are needed for the plugins to work correctly
echo "Installing mypy plugin dependencies (matching pre-commit)..."
uv pip install --quiet types-pyserial returns deal 2>&1 || {
    echo "Warning: Some plugin dependencies may not be installed correctly"
}

# Verify plugins can be imported (mypy will fail silently if plugins can't load)
echo "Verifying mypy plugins are available..."
uv run python -c "
import sys
errors = []
try:
    import returns.contrib.mypy.returns_plugin
except ImportError as e:
    errors.append(f'returns plugin: {e}')
try:
    import deal.mypy
except ImportError as e:
    errors.append(f'deal plugin: {e}')
try:
    import sqlalchemy.ext.mypy.plugin
except ImportError as e:
    errors.append(f'sqlalchemy plugin: {e}')

if errors:
    print('WARNING: Some mypy plugins failed to import:')
    for err in errors:
        print(f'  - {err}')
    print('Mypy may not work correctly without these plugins.')
    sys.exit(1)
else:
    print('✓ All mypy plugins are available')
" || {
    echo "Error: Mypy plugins are not available. Please install dependencies."
    exit 1
}

# Verify mypy version matches pre-commit (v1.18.2)
MYPY_VERSION=$(uv run mypy --version 2>&1 | grep -oE 'mypy [0-9]+\.[0-9]+\.[0-9]+' | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || echo "unknown")
echo "Using mypy version: $MYPY_VERSION"
if [[ "$MYPY_VERSION" != "1.18.2" ]]; then
    echo "Warning: Pre-commit uses mypy v1.18.2, but found $MYPY_VERSION"
    echo "Installing mypy v1.18.2 to match pre-commit..."
    uv pip install --quiet 'mypy==1.18.2' 2>&1 || {
        echo "Error: Failed to install mypy v1.18.2"
        exit 1
    }
fi

# Run mypy with explicit config file (matching pre-commit)
# Pre-commit uses: mypy --config-file=pyproject.toml
# Add --show-error-codes to match pre-commit output format
echo "Running mypy..."
uv run mypy --config-file=pyproject.toml --show-error-codes src/
