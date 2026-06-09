@echo off
REM Fallback: the original simple Tkinter admin window (no browser, no server).
REM Use this only if the web console (run_admin.bat) won't start.
cd /d "%~dp0"
python license_admin.py
if errorlevel 1 pause
