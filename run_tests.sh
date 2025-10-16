#!/usr/bin/env zsh
# Test runner script for Celestron NexStar API
# Runs all tests with coverage reporting

echo "=== Running Celestron NexStar API Tests ==="
echo ""

# Run tests with coverage
echo "Running tests with coverage..."
python -m pytest test_nexstar_api.py test_nexstar_utils.py -v --cov=nexstar_api --cov=nexstar_utils --cov-report=term-missing --cov-report=html

# Check if tests passed
if [[ $? -eq 0 ]]; then
    echo ""
    echo "=== All Tests Passed! ==="
    echo ""
    echo "Coverage report generated in htmlcov/index.html"
    echo "Open with: open htmlcov/index.html"
else
    echo ""
    echo "=== Some Tests Failed ==="
    exit 1
fi
