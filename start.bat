@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo First run: installing. This takes a few minutes.
  py -3 -m venv .venv 2>nul || python -m venv .venv
  if not exist .venv\Scripts\python.exe (
    echo Python was not found. Install it from https://www.python.org/downloads/ and run this again.
    pause
    exit /b 1
  )
)
.venv\Scripts\python -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo Installing failed. Check your internet connection and run this again.
  pause
  exit /b 1
)
if not exist .env (
  copy .env.example .env >nul
  echo.
  echo A file called .env was created. Add your keys to it, save it, then run start.bat again.
  echo The README explains where to get them.
  notepad .env
  pause
  exit /b 0
)
start "" http://localhost:8765
.venv\Scripts\python -m pipeline web
pause
