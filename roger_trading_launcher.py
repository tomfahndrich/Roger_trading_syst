#!/usr/bin/env python3
"""
Roger Trading System Launcher
This script provides a simple way to launch either the GUI or command-line version
of the Roger Trading System.
"""

import os
import sys
import argparse

def main():
    parser = argparse.ArgumentParser(description="Roger Trading System Launcher")
    parser.add_argument("--gui", action="store_true", help="Launch the GUI version (default)")
    parser.add_argument("--cli", action="store_true", help="Launch the command-line version")
    
    args = parser.parse_args()
    
    # If no arguments or --gui is specified, launch GUI
    if not args.cli or args.gui:
        print("Launching Roger Trading System GUI...")
        try:
            from trading_gui import TradingApp
            import tkinter as tk
            root = tk.Tk()
            app = TradingApp(root)
            root.protocol("WM_DELETE_WINDOW", app.on_closing)
            root.mainloop()
        except ImportError as e:
            print(f"Error: {e}")
            print("Make sure all dependencies are installed. Try: pip install -r requirements.txt")
            sys.exit(1)
    # If --cli is specified, launch command-line version
    elif args.cli:
        print("Running Roger Trading System in command-line mode...")
        try:
            from trading_signal_generator import main
            main()
        except ImportError as e:
            print(f"Error: {e}")
            print("Make sure all dependencies are installed. Try: pip install -r requirements.txt")
            sys.exit(1)

if __name__ == "__main__":
    main()
