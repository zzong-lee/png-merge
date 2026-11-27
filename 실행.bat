@echo off
cd /d "%~dp0"
py -3 -c "import PIL" 1>nul 2>nul
if errorlevel 1 (
  py -3 -m pip install -r "%~dp0requirements.txt"
  if errorlevel 1 (
    echo Failed to install Pillow.
    pause
    exit /b 1
  )
)
py -3 "%~dp0main.py" %*
if errorlevel 1 pause
