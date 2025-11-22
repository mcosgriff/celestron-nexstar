#!/bin/bash
# Launcher script for nexstar-gui that runs in background

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Change to project directory
cd "$PROJECT_DIR" || exit 1

# Run the GUI application in background
# On macOS, we can use 'open' or just run with & and disown
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS: Run in background and detach from terminal
    nohup uv run nexstar-gui > /dev/null 2>&1 &
    disown
else
    # Linux: Run in background
    uv run nexstar-gui > /dev/null 2>&1 &
    disown
fi

echo "NexStar GUI started in background"
