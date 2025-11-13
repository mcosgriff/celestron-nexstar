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
echo "Installing mypy plugin dependencies..."
uv pip install --quiet types-pyserial returns deal 2>&1 || {
    echo "Warning: Some plugin dependencies may not be installed"
}

# Verify plugins can be imported
echo "Verifying mypy plugins..."
uv run python -c "
try:
    import returns.contrib.mypy.returns_plugin
    print('✓ returns plugin available')
except ImportError as e:
    print(f'✗ returns plugin not available: {e}')

try:
    import deal.mypy
    print('✓ deal plugin available')
except ImportError as e:
    print(f'✗ deal plugin not available: {e}')

try:
    import sqlalchemy.ext.mypy.plugin
    print('✓ sqlalchemy plugin available')
except ImportError as e:
    print(f'✗ sqlalchemy plugin not available: {e}')
" 2>&1

# Run mypy with explicit config file (matching pre-commit)
# Pre-commit uses: mypy --config-file=pyproject.toml
echo ""
echo "Running mypy..."
uv run mypy --config-file=pyproject.toml --show-error-codes --show-traceback src/ 2>&1
