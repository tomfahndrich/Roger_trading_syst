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

- Automated generation of trading signals based on technical indicators:
  - Stochastic Oscillator (%K, %D)
  - Commodity Channel Index (CCI)
  - Directional Movement Index (DMI): +DI, -DI, and Average Directional Index (ADX)
- Four signal types:
  - Buy+: Strong bullish signal when %K > %D, CCI < -100, +DI ≥ -DI, ADX > 20, and significant slopes
  - Buy: Bullish signal when %K > %D and CCI < -100
  - Sell: Bearish signal when %K < %D and CCI > 100
  - Sell+: Strong bearish signal when %K < %D, CCI > 100, -DI > +DI, ADX > 20, and significant slopes
- Interactive GUI with color-coded rows:
  - Buy+ in green, Buy in light green
  - Sell in light red, Sell+ in red
- ADX column displays the ADX value (rounded to one decimal) with a “+” or “-” prefix indicating trend direction
- Slope threshold filter to show only signals where |slope K| and |slope D| exceed a user-defined value
- Advanced filtering:
  - All shows every signal
  - Buy shows both Buy and Buy+
  - Sell shows both Sell and Sell+
  - Token search and clear filter

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
   - **Tabs for Different Timeframes**: Switch between Monthly, Weekly, Daily, and 4-hour views

2. **Filtering Options**
   - **All/Buy/Sell Buttons**: "Buy" shows Buy & Buy+; "Sell" shows Sell & Sell+
   - **Token Search**: Type any part of a token symbol to filter
   - **Slope >**: Enter a decimal (e.g., 0.6) to filter on slope magnitude
   - **Clear Filter**: Reset all filters with the "✕" button

3. **ADX Column**
   - Shows the ADX value with one decimal and a prefix (+/-) to indicate trend

4. **Managing Notes**
   - **Double-click** any note field to add or edit notes
   - Notes auto-save to Excel

## Notes

- The file `trading_synthesis.xlsx` is ignored by version control and will not be pushed to GitHub.
- The GUI automatically loads and saves data to the Excel file.
- The system uses yfinance to fetch market data - ensure you have internet connectivity.
- Signal colors: Buy signals are highlighted in green, Sell signals in red.

## License

This project is for personal or educational use. Please contact the author for other uses.
