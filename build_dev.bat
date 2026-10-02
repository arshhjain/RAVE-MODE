@echo off
:: ============================================================
::  Rave Mode — Build Script
::  Double-click this file from the project root folder.
:: ============================================================

echo.
echo  ===  Rave Mode Dev Tools Builder  ===
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
pyinstaller rave_mode_dev.spec --noconfirm --clean
if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller failed. Check the output above for details.
    pause & exit /b 1
)
echo       Done.

:: ---------- 5. Verify output ----------
echo [3/4] Checking output...
if not exist "dist\RaveModeDev.exe" (
    echo [WARNING] dist\RaveModeDev.exe was not found — check PyInstaller output.
) else (
    echo       dist\RaveModeDev.exe  —  OK
)

:: ---------- 6. Done ----------
echo [4/4] Build complete!
echo.
echo  Output folder:  dist\
echo  Run the app  :  dist\RaveModeDev.exe
echo.
echo  To distribute, you can copy the standalone RaveModeDev.exe file anywhere you like!
echo.
pause
