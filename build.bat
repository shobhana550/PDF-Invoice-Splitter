@echo off
REM PDF Invoice Splitter - Build Script
REM Creates a standalone executable

echo ===============================================
echo PDF Invoice Splitter - PyInstaller Build
echo ===============================================
echo.

REM Check if PyInstaller is installed
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    pip install pyinstaller
)

echo.
echo Building standalone executable...
echo This may take a few minutes...
echo.

REM Create the executable
pyinstaller --onefile --windowed --name "PDF_Invoice_Splitter" --icon=icon.ico splitter.py

echo.
echo ===============================================
echo Build Complete!
echo ===============================================
echo.
echo Your executable is located at:
echo   dist\PDF_Invoice_Splitter.exe
echo.
echo You can now copy this .exe file to any Windows computer
echo and run it directly without needing Python installed.
echo.
pause
