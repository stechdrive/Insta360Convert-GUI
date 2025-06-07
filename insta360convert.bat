@echo off
REM Set the console code page to UTF-8 to prevent issues with non-ASCII characters in paths or output.
chcp 65001 > nul

REM Change the current directory to the location of this batch file.
REM This ensures that the script can correctly find any relative files (e.g., config files, other scripts).
cd /d "%~dp0"

REM --- Auto-detect and execute Python environment ---

REM Priority 1: Try the Python Launcher (py.exe). This is the best method.
where py >nul 2>nul
if %errorlevel% == 0 (
    py -w insta360convert.py
    exit /b
)

REM Priority 2: Try python.exe. This covers the Microsoft Store version.
where python >nul 2>nul
if %errorlevel% == 0 (
    REM Use "start /min" to launch in a new, minimized console, allowing this batch file to exit immediately.
    start "Insta360Convert GUI" /min python insta360convert.py
    exit /b
)

REM Priority 3: Fallback to pyw.exe directly.
where pyw >nul 2>nul
if %errorlevel% == 0 (
    start "" pyw insta360convert.py
    exit /b
)

REM --- Error handling if no Python executable was found ---
echo.
echo =================================================================
echo  Error: Could not find a Python installation.
echo.
echo  This program requires Python to run.
echo  Please install it from the Microsoft Store or python.org.
echo =================================================================
echo.
pause