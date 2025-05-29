@echo off
REM This script launches the Roger Trading System GUI.

REM Get the directory of this batch file.
set SCRIPT_DIR=%~dp0

REM Change to the script's directory. This ensures that trading_gui.py
REM and trading_synthesis.xlsx are found correctly, assuming they are
REM in the same directory as this launch script.
cd /D "%SCRIPT_DIR%"

echo Attempting to launch Roger Trading System GUI...
echo Please ensure Python 3 is installed and all required packages (pandas, yfinance, ta, openpyxl, etc.) are available.
echo If the app doesn't start, this window might show error messages.

REM Execute the Python GUI script.
REM This assumes 'python.exe' is in the system PATH.
REM If you want to avoid a console window appearing *at all* (even briefly),
REM you can try using 'pythonw.exe' instead of 'python.exe'.
REM However, using 'pythonw.exe' will hide any error messages if the script fails to start.
python trading_gui.py

echo Roger Trading System script has finished or the window was closed.
REM You can add 'pause' on the line below if you want this window to stay open
REM after the GUI closes, to read any messages.
REM pause
