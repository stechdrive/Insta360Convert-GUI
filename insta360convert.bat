@echo off
REM Set console code page to UTF-8 to handle non-ASCII characters in paths or script output
chcp 65001 > nul

REM Change directory to the location of this batch file
REM This ensures that the script can find any relative files correctly
cd /d "%~dp0"

REM Launch the Python GUI script without a console window
REM "start" with an empty title "" runs the command in a new process and allows the batch file to exit immediately
REM "pyw.exe" is used to run Python scripts without opening a console window, suitable for GUI applications
start "" pyw insta360convert.py