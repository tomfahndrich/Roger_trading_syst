@echo off
REM This script updates the local repository and launches the Roger Trading System GUI.

REM Get the directory of this batch file.
set SCRIPT_DIR=%~dp0

REM Change to the script's directory.
cd /D "%SCRIPT_DIR%"

echo Updating the local repository...
REM Pull the latest changes from the remote repository.
git pull

echo Attempting to launch Roger Trading System GUI...
echo Please ensure Python 3 is installed and all required packages (pandas, yfinance, ta, openpyxl, etc.) are available.
echo If the app doesn't start, this window might show error messages.

REM Execute the Python GUI script.
python trading_gui.py

echo Roger Trading System script has finished or the window was closed.
REM You can add 'pause' on the line below if you want this window to stay open
REM after the GUI closes, to read any messages.
REM pause
