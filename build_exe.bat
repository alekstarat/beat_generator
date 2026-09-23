@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================
echo        Beat Generator - EXE Builder
echo ============================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [1/5] Creating virtual environment...
    py -3.13 -m venv .venv
    if errorlevel 1 (
        echo ERROR: Python 3.13 was not found.
        echo Install Python 3.13 and enable the "py" launcher.
        pause
        exit /b 1
    )
) else (
    echo [1/5] Virtual environment already exists.
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
    echo ERROR: Could not activate virtual environment.
    pause
    exit /b 1
)

echo [2/5] Updating pip...
python -m pip install --upgrade pip
if errorlevel 1 goto :error

echo [3/5] Installing project dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo [4/5] Installing PyInstaller...
python -m pip install --upgrade pyinstaller
if errorlevel 1 goto :error

echo [5/5] Building BeatGenerator.exe...
if exist "build" rmdir /s /q "build"
if exist "dist\BeatGenerator" rmdir /s /q "dist\BeatGenerator"
if exist "dist\BeatGenerator.exe" del /q "dist\BeatGenerator.exe"

python -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --windowed ^
    --name "BeatGenerator" ^
    --icon "icon.ico" ^
    --add-data "icon.ico;." ^
    --collect-all "PySide6" ^
    --collect-all "numpy" ^
    --collect-all "soundfile" ^
    --collect-all "mido" ^
    --collect-all "rtmidi" ^
    "main.py"

if errorlevel 1 goto :error

echo.
echo ============================================
echo BUILD SUCCESSFUL
echo ============================================
echo EXE:
echo %CD%\dist\BeatGenerator\BeatGenerator.exe
echo.
echo The entire "dist\BeatGenerator" folder is the portable build.
echo You can copy that folder to another Windows PC.
echo.
pause
exit /b 0

:error
echo.
echo ============================================
echo BUILD FAILED
echo ============================================
echo Check the error messages above.
pause
exit /b 1
