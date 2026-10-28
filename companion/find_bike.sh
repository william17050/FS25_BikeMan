#!/usr/bin/env bash
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ] || ! .venv/bin/python -c "import bleak" 2>/dev/null; then
  rm -rf .venv
  python3 -m venv .venv && .venv/bin/pip install --quiet bleak || { rm -rf .venv; echo "Could not set up the Python environment (see README, Linux troubleshooting). If you are inside a container, run this in your normal terminal on the host instead."; exit 1; }
fi
exec .venv/bin/python find_bike.py
