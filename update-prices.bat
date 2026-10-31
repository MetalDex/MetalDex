@echo off
rem Update the price data: collects listings, rebuilds the tracker, commits. See prices/update.py.
rem For Task Scheduler add --auto so it does not wait for Enter at the end.
cd /d "%~dp0"
where py >nul 2>nul && (py -3 prices\update.py %* & exit /b)
where python >nul 2>nul && (python prices\update.py %* & exit /b)
echo Python 3 is needed to update prices. Install it from https://www.python.org/downloads/
echo (tick "Add python.exe to PATH" during setup), then double-click this file again.
pause
