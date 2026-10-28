#!/usr/bin/env bash
cd "$(dirname "$0")"
# ---- EDIT THESE IF NEEDED ------------------------------------------------
PORT=48765
EXTRA=()          # e.g. EXTRA=(--units mph --hud-scale 1.5)   or   EXTRA=(--profile "/path/to/FarmingSimulator2025")
# --------------------------------------------------------------------------
echo "Start this once FS25 is running and you are on a vehicle."
exec python3 fs25_link.py --port "$PORT" "${EXTRA[@]}"
