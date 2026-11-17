@echo off
rem Windows: double-click to start Transcibio. The window stays open; Ctrl+C stops the app.
rem "start" opens PowerShell in its own window, so Ctrl+C there skips cmd's "Terminate batch job?".
set TRANSCIBIO_FROM_DESKTOP=1
start "Transcibio" powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\transcibio.ps1" start
