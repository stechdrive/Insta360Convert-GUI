@echo off
REM Set the console code page to UTF-8 to prevent issues with non-ASCII characters in paths or output.
chcp 65001 > nul

REM Change the current directory to the location of this batch file.
cd /d "%~dp0"

REM --- Auto-detect and execute Python environment (most robust method) ---

REM Attempt 1: Try the official Python Launcher with the -w flag.
REM This is the most ideal method. We directly attempt execution and check the result.
REM Error output is redirected to nul to hide "Unknown option: -w" on misconfigured systems.
(py -w insta360convert.py) >nul 2>nul
if %errorlevel% == 0 (
    exit /b
)

REM Attempt 2: If the launcher fails, try pyw.exe directly.
REM This is specific to full installations from python.org and is very reliable for GUIs.
where pyw >nul 2>nul
if %errorlevel% == 0 (
    start "" pyw insta360convert.py
    exit /b
)

REM Attempt 3: If both fail, try python.exe.
REM This covers the Microsoft Store version and basic PATH setups.
REM "start /min" launches it in a new, minimized console window.
where python >nul 2>nul
if %errorlevel% == 0 (
    start "Insta360Convert GUI" /min python insta360convert.py
    exit /b
)

REM --- Error handling if no Python executable was found ---
echo.
echo =================================================================
echo  Error: Could not find a working Python installation.
echo.
echo  This program requires Python to run.
echo  Please install it from the Microsoft Store or python.org.
echo =================================================================
echo.
pause