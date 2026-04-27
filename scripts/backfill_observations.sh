#!/usr/bin/env bash
# Backfill ASOS daily-high/low observations into the settlements table.
# Usage: backfill_observations.sh [days] [station]
set -euo pipefail
cd "$(dirname "$0")/.."
DAYS="${1:-7}"
if [[ $# -ge 2 ]]; then
  exec uv run weather-bot backfill --days "$DAYS" --station "$2"
else
  exec uv run weather-bot backfill --days "$DAYS"
fi
