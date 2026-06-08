@echo off
REM ============================================================
REM  Universal Media Downloader - local launcher
REM  Double-click this file to start the app in your browser.
REM ============================================================
cd /d "%~dp0"

echo Starting Universal Media Downloader...
echo A browser tab will open at http://localhost:8501
echo Keep this window open while you use the app. Close it to stop.
echo.

python -m streamlit run app.py

echo.
echo The app has stopped. Press any key to close this window.
pause >nul
