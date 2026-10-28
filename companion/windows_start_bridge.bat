@echo off
cd /d "%~dp0"
rem ---- EDIT THESE IF NEEDED ----------------------------------------------
rem Your bike's Bluetooth address (run  py find_bike.py  to find it). Leave blank to find the bike automatically.
set "BIKE_ADDR="
rem Port used between the two scripts. Change BOTH .bat files if you change it.
set "PORT=48765"
rem Highest resistance the game may command (hard max 80). Lower = easier.
set "CAP=50"
rem ------------------------------------------------------------------------
set "ARGS=--cap %CAP% --port %PORT%"
if defined BIKE_ADDR set "ARGS=%ARGS% --addr %BIKE_ADDR%"
py -m pip install --quiet bleak
echo Starting the bike bridge. Wake the bike by pedalling. Close the Renpho app and Zwift first.
py bridge.py %ARGS%
pause
