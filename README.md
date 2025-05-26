# Roger Trading System

This project is a trading signal generator and management system designed to help automate and analyze trading strategies. It leverages Python scripts and Excel files to generate, process, and manage trading signals.

## Project Structure

- **trading_signal_generator.py**: Main script for generating trading signals based on market data and predefined strategies.
- **update_watchlist.py**: (Currently ignored in version control) Used to update or manage the trading watchlist.
- **trading_synthesis.xlsx**: Excel file used for storing or synthesizing trading signals and results (ignored in version control).
- **requirements.txt**: Lists the Python dependencies required to run the project.
- **tokens.txt**: Stores API tokens or credentials (ensure this file is kept secure).

## Features

- Automated generation of trading signals.
- Integration with Excel for data storage and analysis.
- Modular scripts for signal generation and watchlist management.

## Getting Started

1. **Install dependencies**  
   Run the following command to install required Python packages:
   ```
   pip install -r requirements.txt
   ```

2. **Configure tokens**  
   Add your API tokens or credentials to `tokens.txt`.

3. **Run the signal generator**  
   Execute the main script:
   ```
   python trading_signal_generator.py
   ```

## Notes

- The files `trading_synthesis.xlsx` and `update_watchlist.py` are ignored by version control and will not be pushed to GitHub.
- Ensure you have the necessary market data and API access configured for the scripts to function correctly.

## License

This project is for personal or educational use. Please contact the author for other uses.
