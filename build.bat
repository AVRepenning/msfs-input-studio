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
"%STUDIO_PYTHON%" -m PyInstaller --noconfirm --clean --workpath "%LOCALAPPDATA%\MSFSInputStudio\build" --onefile --windowed --name MSFSInputStudio --add-data "data;data" --add-data "README.md;." --add-data "FEATURE_MATRIX.md;." --add-data "LICENSE;." --add-data "THIRD_PARTY_NOTICES.md;." msfs_input_studio.py
if errorlevel 1 exit /b 1
echo Built dist\MSFSInputStudio.exe
