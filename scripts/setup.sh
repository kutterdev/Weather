#!/usr/bin/env bash
# Install deps and initialize the SQLite database.
set -euo pipefail
cd "$(dirname "$0")/.."
uv sync
uv run weather-bot init
echo "Setup complete. Try: scripts/run_observe.sh"
