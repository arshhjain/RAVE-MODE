@echo off
:: ============================================================
::  Rave Mode — Build Script
::  Double-click this file from the project root folder.
:: ============================================================

echo.
echo  ===  Rave Mode Builder  ===
echo.

:: ---------- 1. Check Python is available ----------
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Make sure Python is installed and on your PATH.
    pause & exit /b 1
)

:: ---------- 2. Install / upgrade dependencies ----------
echo [1/4] Installing dependencies...
pip install --upgrade pyinstaller >nul 2>&1
pip install -r requirements.txt >nul 2>&1
echo       Done.

:: ---------- 3. Verify the ui folder exists ----------
if not exist "ui\index.html" (
    echo [ERROR] ui\index.html not found.
    echo         Make sure index.html is inside a folder called "ui" next to this script.
    pause & exit /b 1
)

:: ---------- 4. Run PyInstaller ----------
echo [2/4] Running PyInstaller...
pyinstaller rave_mode.spec --noconfirm --clean
if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller failed. Check the output above for details.
    pause & exit /b 1
)
echo       Done.

:: ---------- 5. Verify output ----------
echo [3/4] Checking output...
if not exist "dist\RaveMode\RaveMode.exe" (
    echo [WARNING] dist\RaveMode\RaveMode.exe was not found — check PyInstaller output.
) else (
    echo       dist\RaveMode\RaveMode.exe  —  OK
)

:: ---------- 6. Done ----------
echo [4/4] Build complete!
echo.
echo  Output folder:  dist\RaveMode\
echo  Run the app  :  dist\RaveMode\RaveMode.exe
echo.
echo  To distribute, zip or copy the entire dist\RaveMode\ folder.
echo  The .exe will NOT work if moved out of that folder on its own.
echo.
pause
