@echo off
rem Checks which shop sites answer the update script (changes no data). Share the saved result when asking for help.
cd /d "%~dp0"
where py >nul 2>nul && (py -3 prices\collect.py --diagnose & pause & exit /b)
where python >nul 2>nul && (python prices\collect.py --diagnose & pause & exit /b)
echo Python 3 is needed: https://www.python.org/downloads/
pause
