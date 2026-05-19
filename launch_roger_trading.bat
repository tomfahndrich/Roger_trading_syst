@echo off
REM Sync the entire repo to origin/Roger2 then launch the GUI.
REM
REM Previously this script only checked out trading_gui.py and
REM trading_signal_generator.py — that broke whenever the GUI started
REM importing new symbols from Roger_trading_yfinance_symbol/. Now we sync
REM the whole branch so every tracked file (incl. symbols_finder.py,
REM __init__.py, this .bat itself, ...) stays in lock-step with origin.
REM
REM Gitignored files (trading_synthesis.xlsx, __pycache__, ~$lock files,
REM etc.) are preserved on disk.

set SCRIPT_DIR=%~dp0
cd /D "%SCRIPT_DIR%"

REM Pull latest from the remote and snap local Roger2 to it.
git fetch origin Roger2
git checkout -B Roger2 origin/Roger2

echo Repo synced to origin/Roger2.

echo Attempting to launch Roger Trading System GUI...
echo Please ensure Python 3 is installed and all required packages (pandas, yfinance, ta, openpyxl, etc.) are available.
echo If the app doesn't start, this window might show error messages.

REM Execute the Python GUI script.
python trading_gui.py

echo Roger Trading System script has finished or the window was closed.
