#!/usr/bin/env bash
# Builds dist/BikeMan_Companion.zip (bridge, link, start scripts) for Windows and Linux.
set -e
cd "$(dirname "$0")/.."
mkdir -p dist
rm -f dist/BikeMan_Companion.zip
zip -qr dist/BikeMan_Companion.zip companion -x 'companion/__pycache__/*' 'companion/.venv/*' 'companion/rides/*'
unzip -tq dist/BikeMan_Companion.zip
