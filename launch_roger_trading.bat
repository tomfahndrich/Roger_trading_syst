@echo off
REM This script updates two specific .py files from the Roger branch and launches the GUI.

REM Get the directory of this batch file.
set SCRIPT_DIR=%~dp0

REM Change to the script's directory.
cd /D "%SCRIPT_DIR%"

REM Update the remote tracking information
git fetch origin Roger2

REM Checkout only specific files from the Roger branch
git checkout origin/Roger2 -- trading_gui.py trading_signal_generator.py

echo Updated trading_gui.py and signal_generator.py from branch Roger.

echo Attempting to launch Roger Trading System GUI...
echo Please ensure Python 3 is installed and all required packages (pandas, yfinance, ta, openpyxl, etc.) are available.
echo If the app doesn't start, this window might show error messages.

REM Execute the Python GUI script.
python trading_gui.py

echo Roger Trading System script has finished or the window was closed.
