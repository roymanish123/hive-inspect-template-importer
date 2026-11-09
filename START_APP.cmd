@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First complete the Python setup in README.md.
  pause
  exit /b 1
)
echo Open http://127.0.0.1:5000 in your browser.
echo Keep this window open while using the app.
".venv\Scripts\python.exe" app.py
pause
