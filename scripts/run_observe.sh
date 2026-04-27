#!/usr/bin/env bash
# Start the long-running scheduler. Ctrl-C to stop.
set -euo pipefail
cd "$(dirname "$0")/.."
exec uv run weather-bot observe
