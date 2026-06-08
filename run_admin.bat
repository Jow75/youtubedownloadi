@echo off
REM Double-click this to open the License Admin tool (seller-only).
cd /d "%~dp0"
python license_admin.py
if errorlevel 1 pause
