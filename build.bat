@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    set "STUDIO_PYTHON=.venv\Scripts\python.exe"
) else (
    set "STUDIO_PYTHON=python"
)
"%STUDIO_PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
"%STUDIO_PYTHON%" -m unittest discover -s tests -v
if errorlevel 1 exit /b 1
"%STUDIO_PYTHON%" tools\build_app.py
if errorlevel 1 exit /b 1
"%STUDIO_PYTHON%" tools\package_source.py
