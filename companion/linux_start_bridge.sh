#!/usr/bin/env bash
cd "$(dirname "$0")"
# ---- EDIT THESE IF NEEDED ------------------------------------------------
BIKE_ADDR=""      # your bike's Bluetooth address (run ./find_bike.sh); blank = find it automatically
PORT=48765
CAP=50            # highest resistance the game may command (hard max 80)
# --------------------------------------------------------------------------
ARGS=(--cap "$CAP" --port "$PORT")
[ -n "$BIKE_ADDR" ] && ARGS+=(--addr "$BIKE_ADDR")
if [ ! -x .venv/bin/python ] || ! .venv/bin/python -c "import bleak" 2>/dev/null; then
  rm -rf .venv
  python3 -m venv .venv && .venv/bin/pip install --quiet bleak || { rm -rf .venv; echo "Could not set up the Python environment (see README, Linux troubleshooting). If you are inside a container, run this in your normal terminal on the host instead."; exit 1; }
fi
echo "Starting the bike bridge. Wake the bike by pedalling. Close the Renpho app first."
exec .venv/bin/python bridge.py "${ARGS[@]}"
