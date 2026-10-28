#!/usr/bin/env bash
# Builds dist/FS25_BikeMan.zip (the game mod) with the files at the zip root, as FS25 requires.
set -e
cd "$(dirname "$0")/.."
mkdir -p dist
rm -f dist/FS25_BikeMan.zip
(cd mod && zip -qr ../dist/FS25_BikeMan.zip modDesc.xml BikeMan.lua icon_BikeMan.dds images)
unzip -tq dist/FS25_BikeMan.zip
unzip -l dist/FS25_BikeMan.zip
