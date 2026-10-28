@echo off
cd /d "%~dp0"
rem ---- EDIT THESE IF NEEDED ----------------------------------------------
set "PORT=48765"
rem Extra options, e.g.  --units mph --hud-scale 1.5 --grade-scale 0.6 --coast-brake 0.7
set "EXTRA="
rem Only if the profile folder is not found automatically:
rem set "EXTRA=%EXTRA% --profile ""D:\path\to\My Games\FarmingSimulator2025"""
rem ------------------------------------------------------------------------
echo Start this once FS25 is running and you are on a vehicle.
py fs25_link.py --port %PORT% %EXTRA%
pause
