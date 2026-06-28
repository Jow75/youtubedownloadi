@echo off
REM Double-click this to open the License Console (seller-only, premium UI).
REM Opens in its OWN native window (Windows WebView2). If WebView2 isn't
REM available it automatically falls back to opening in your browser.
cd /d "%~dp0"
python admin_app.py
if errorlevel 1 pause
