import os
import numpy as np
import pandas as pd
import yfinance as yf
from ta.trend import SMAIndicator, CCIIndicator

# PARAMETERS
TOKENS_FILE = 'tokens.txt'
EXCEL_FILE  = 'trading_synthesis.xlsx'
TIMEFRAMES  = {
    'weekly': {'interval': '1wk',  'period': '3y'},
    'daily' : {'interval': '1d',   'period': '1y'},
    '4h'    : {'interval': '4h',   'period': '90d'},  # ← changed here
}
STOCH_PARAMS = {
    'window':    55,   # %K raw look-back
    'k_smooth':  55,   # smoothing for %K
    'd_smooth':  36,   # smoothing for %D
}
CCI_PERIOD   = 20
SLOPE_PERIOD = 10

# INDICATOR FUNCTIONS
def compute_stoch(df, window, k_smooth, d_smooth):
    low_n  = df['Low'].rolling(window).min()
    high_n = df['High'].rolling(window).max()
    raw_k  = 100 * (df['Close'] - low_n) / (high_n - low_n)
    k_series = SMAIndicator(raw_k, window=k_smooth, fillna=False).sma_indicator()
    d_series = SMAIndicator(k_series, window=d_smooth, fillna=False).sma_indicator()
    return k_series, d_series

def compute_cci(df, period):
    return CCIIndicator(
        high=df['High'], low=df['Low'], close=df['Close'],
        window=period, constant=0.015, fillna=False
    ).cci()

def slope(series):
    y = series.dropna().values[-SLOPE_PERIOD:]
    if len(y) < SLOPE_PERIOD:
        return np.nan
    x = np.arange(len(y))
    return np.polyfit(x, y, 1)[0]

def signal_from_indicators(df):
    # Use only the last bar's K vs D (not a crossover)
    k_now   = df['K'].iloc[-1]
    d_now   = df['D'].iloc[-1]
    cci_now = df['CCI'].iloc[-1]
    slope_k = slope(df['K'])
    slope_d = slope(df['D'])

    buy  = (k_now > d_now) and (cci_now > 100)  # and (slope_k > 0) and (slope_d > 0)
    sell = (k_now < d_now) and (cci_now < -100) # and (slope_k < 0) and (slope_d < 0)

    return 'Buy' if buy else 'Sell' if sell else 'Neutral'

def main():
    # Load tokens
    with open(TOKENS_FILE) as f:
        tokens = [t.strip() for t in f if t.strip()]

    new_signals = {tf: [] for tf in TIMEFRAMES}

    for token in tokens:
        ticker = yf.Ticker(token)
        for sheet, cfg in TIMEFRAMES.items():
            df = ticker.history(period=cfg['period'], interval=cfg['interval'])
            if df.empty:
                print(f"Warning: No data for {token} ({sheet})")
                continue

            # ── DROP TZ INFO ────────────────────────────────────────────
            # if the index is timezone‐aware, remove the tz so Excel will accept it
            if getattr(df.index, 'tz', None) is not None:
                df.index = df.index.tz_localize(None)

            # ── INDICATORS ─────────────────────────────────────────────
            df['K'], df['D'] = compute_stoch(
                df, STOCH_PARAMS['window'],
                STOCH_PARAMS['k_smooth'],
                STOCH_PARAMS['d_smooth']
            )
            df['CCI'] = compute_cci(df, CCI_PERIOD)

            # ── FILTER & SIGNAL ───────────────────────────────────────
            ind = df.dropna(subset=['K','D','CCI'])
            if ind.empty:
                print(f"Warning: No valid indicators for {token} ({sheet})")
                continue

            sig = signal_from_indicators(ind)
            if sig == 'Neutral':
                continue
            else:
                print(f"Signal for {token} ({sheet}): {sig})")
            last = ind.iloc[-1]
            new_signals[sheet].append({
                'datetime'   : last.name,       # now tz‐naive
                'signal'     : sig,
                'token'      : token,
                'close price': last['Close'],
                'CCI'        : last['CCI'],
                'stoch K'    : last['K'],
                'stoch D'    : last['D'],
                'slope K'    : slope(ind['K']),
                'slope D'    : slope(ind['D']),
            })

    # Load or initialize Excel
    if os.path.exists(EXCEL_FILE):
        existing = pd.read_excel(EXCEL_FILE, sheet_name=None)
    else:
        existing = {
            sheet: pd.DataFrame(columns=[
                'datetime','signal','token','close price','CCI',
                'stoch K','stoch D','slope K','slope D'
            ]) for sheet in TIMEFRAMES
        }

    with pd.ExcelWriter(EXCEL_FILE, engine='openpyxl') as writer:
        for sheet in TIMEFRAMES:
            old_df = existing.get(sheet, pd.DataFrame())
            new_df = pd.DataFrame(new_signals[sheet])
            combined = pd.concat([new_df, old_df], ignore_index=True) if not new_df.empty else old_df

            # —— ROUND NUMERIC COLUMNS TO 2 DECIMALS ————————————————
            num_cols = ['close price','CCI','stoch K','stoch D','slope K','slope D']
            combined[num_cols] = combined[num_cols].round(2)

            combined.to_excel(writer, sheet_name=sheet, index=False)

    print(f"Updated '{EXCEL_FILE}' with 2-dec Buy/Sell signals for: {', '.join(tokens)}")

if __name__ == "__main__":
    main()