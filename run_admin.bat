@echo off
REM Double-click this to open the License Console (seller-only, premium web UI).
REM It starts a tiny local server on 127.0.0.1 and opens it in your browser.
cd /d "%~dp0"
python admin_server.py
if errorlevel 1 pause
