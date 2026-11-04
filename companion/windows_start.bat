@echo off
cd /d "%~dp0"
rem ---- EDIT THESE IF NEEDED ----------------------------------------------
rem Your bike's Bluetooth address (run  py find_bike.py  to find it). Leave blank to find the bike automatically.
set "BIKE_ADDR="
set "PORT=48765"
rem Highest resistance the game may command (hard max 80). Lower = easier.
set "CAP=50"
rem Extra options, e.g.  --units mph --hud-scale 1.5 --grade-scale 0.6 --coast-brake 0.7
set "EXTRA="
rem ------------------------------------------------------------------------
set "ARGS=--port %PORT% --cap %CAP%"
if defined BIKE_ADDR set "ARGS=%ARGS% --addr %BIKE_ADDR%"
py -m pip install --quiet bleak
py start_bikeman.py %ARGS% %EXTRA%
pause
