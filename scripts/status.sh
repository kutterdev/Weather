#!/usr/bin/env bash
# Print learning state from the database.
set -euo pipefail
cd "$(dirname "$0")/.."
exec uv run weather-bot status
