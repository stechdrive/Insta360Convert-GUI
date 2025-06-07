@echo off
REM Set the console code page to UTF-8 to prevent issues with non-ASCII characters in paths or output.
chcp 65001 > nul

REM Change the current directory to the location of this batch file.
REM This ensures that the script can correctly find any relative files (e.g., config files, other scripts).
cd /d "%~dp0"

REM --- Auto-detect and execute Python environment ---

REM Priority 1: Try the Python Launcher (py.exe).
REM This is the standard way to run Python on Windows when installed from python.org,
REM and it works even if Python is not in the system's PATH.
where py >nul 2>nul
if %errorlevel% == 0 (
    echo Launching with Python Launcher (py.exe)...
    py -w insta360convert.py
    exit /b
)

REM Priority 2: Try python.exe.
REM This covers installations from the Windows Store or official installers where python.exe was added to the PATH.
REM The "start /b" command runs the script without creating a new console window.
where python >nul 2>nul
if %errorlevel% == 0 (
    echo Launching with python.exe...
    start /b python insta360convert.py
    exit /b
)

REM Priority 3: Fallback to pyw.exe directly.
REM This handles rare cases where only pyw.exe is in the PATH.
REM The "start """ runs the command in a new process, allowing the batch file to exit immediately.
where pyw >nul 2>nul
if %errorlevel% == 0 (
    echo Launching with pyw.exe...
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