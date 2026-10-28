@echo off
cd /d "%~dp0"
py -m pip install --quiet bleak
py find_bike.py
pause
