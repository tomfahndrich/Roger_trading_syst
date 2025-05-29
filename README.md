# Roger Trading System

This project is a trading signal generator and management system designed to help automate and analyze trading strategies. It leverages Python scripts and Excel files to generate, process, and manage trading signals with an intuitive graphical user interface.

## Project Structure

- **trading_signal_generator.py**: Main script for generating trading signals based on market data and predefined strategies.
- **trading_gui.py**: Graphical user interface for viewing, filtering, and managing trading signals.
- **roger_trading_launcher.py**: Python launcher script that can start either the GUI or command-line version.
- **launch_roger_trading.bat**: Windows batch file to easily launch the trading system.
- **trading_synthesis.xlsx**: Excel file used for storing or synthesizing trading signals and results (ignored in version control).
- **requirements.txt**: Lists the Python dependencies required to run the project.
- **tokens.txt**: Stores API tokens or credentials (ensure this file is kept secure).

## Features

- Automated generation of trading signals based on technical indicators (Stochastic, CCI).
- Interactive GUI for viewing and analyzing trading signals.
- Filtering capabilities by signal type (Buy/Sell) and token symbols.
- Note-taking functionality for individual signals, automatically saved to Excel.
- Integration with Excel for data storage and analysis.
- Support for multiple timeframes (weekly, daily, 4h).
- Modular architecture for easy extension and customization.

## Getting Started

1. **Install dependencies**  
   Run the following command to install required Python packages:
   ```
   pip install -r requirements.txt
   ```

2. **Configure symbols**  
   Add your trading symbols to the "symbols" sheet in the `trading_synthesis.xlsx` file.

3. **Launch the application**  
   You can launch the application in different ways:
   
   **GUI Mode (recommended):**
   ```
   python roger_trading_launcher.py
   ```
   or simply:
   ```
   python trading_gui.py
   ```
   
   **Command-line Mode (signal generation only):**
   ```
   python roger_trading_launcher.py --cli
   ```
   or:
   ```
   python trading_signal_generator.py
   ```

## Using the GUI

The GUI provides several features to make working with trading signals easier:

1. **Main Dashboard**
   - **Update Data**: Fetches new signals and updates the Excel file
   - **Tabs for Different Timeframes**: Switch between weekly, daily, and 4-hour timeframes

2. **Filtering Options**
   - **All/Buy/Sell Buttons**: Quickly filter signals by type
   - **Token Search**: Type any part of a token symbol to filter results
   - **Clear Filter**: Reset all filters with the "✕" button

3. **Managing Notes**
   - **Double-click** on any note field to add or edit notes
   - Notes are automatically saved to the Excel file

## Notes

- The file `trading_synthesis.xlsx` is ignored by version control and will not be pushed to GitHub.
- The GUI automatically loads and saves data to the Excel file.
- The system uses yfinance to fetch market data - ensure you have internet connectivity.
- Signal colors: Buy signals are highlighted in green, Sell signals in red.

## License

This project is for personal or educational use. Please contact the author for other uses.
