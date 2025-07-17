import os
import numpy as np
import pandas as pd
import yfinance as yf
from ta.trend import SMAIndicator, CCIIndicator, ADXIndicator

# PARAMETERS
EXCEL_FILE  = 'trading_synthesis.xlsx'
TIMEFRAMES  = {
    'monthly': {'interval': '1mo', 'period': '13y'},
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
DMI_PERIOD   = 14     # Classic 14-period for DMI/ADX
SLOPE_PERIOD = 10
ADX_THRESHOLD = 20  # ADX threshold for trend strength
SLOPE_THRESHOLD = 0.5  # Slope threshold for trend strength

# INDICATOR FUNCTIONS
def compute_stoch(df, window, k_smooth, d_smooth):
    try:
        # Check if we have enough data
        if len(df) < window:
            print(f"Warning: Not enough data for stochastic calculation. Need {window}, have {len(df)}")
            # Return empty series with proper index
            empty_series = pd.Series(np.nan, index=df.index)
            return empty_series, empty_series
            
        # Safely compute components with error handling
        low_n = df['Low'].rolling(window).min()
        high_n = df['High'].rolling(window).max()
        
        # Handle potential division by zero
        denominator = (high_n - low_n)
        raw_k = pd.Series(np.nan, index=df.index)  # Initialize with NaNs
        
        # Only calculate for non-zero denominators
        valid_idx = denominator != 0
        if valid_idx.any():
            raw_k[valid_idx] = 100 * (df['Close'][valid_idx] - low_n[valid_idx]) / denominator[valid_idx]
        
        # Use fillna=True for better robustness
        k_series = SMAIndicator(raw_k, window=k_smooth, fillna=True).sma_indicator()
        d_series = SMAIndicator(k_series, window=d_smooth, fillna=True).sma_indicator()
        
        return k_series, d_series
        
    except Exception as e:
        print(f"Error calculating stochastic oscillator: {e}")
        # Return empty series with proper index
        empty_series = pd.Series(np.nan, index=df.index)
        return empty_series, empty_series

def compute_cci(df, period):
    try:
        # Check if we have enough data
        if len(df) < period:
            print(f"Warning: Not enough data for CCI calculation. Need {period}, have {len(df)}")
            return pd.Series(np.nan, index=df.index)
        
        # Use fillna=True for better robustness
        return CCIIndicator(
            high=df['High'], low=df['Low'], close=df['Close'],
            window=period, constant=0.015, fillna=True
        ).cci()
    except Exception as e:
        print(f"Error calculating CCI: {e}")
        return pd.Series(np.nan, index=df.index)

def compute_dmi(df, period):
    try:
        # Check if we have enough data points for ADX calculation
        if len(df) < period + 1:  # ADX requires at least period+1 data points
            print(f"Warning: Not enough data points for ADX calculation. Need {period+1}, have {len(df)}")
            return {
                'adx': pd.Series(np.nan, index=df.index),
                'plus_di': pd.Series(np.nan, index=df.index),
                'minus_di': pd.Series(np.nan, index=df.index)
            }
        
        # Create ADX indicator with fillna=True to avoid NaN propagation
        adx_indicator = ADXIndicator(
            high=df['High'], low=df['Low'], close=df['Close'],
            window=period, fillna=True
        )
        
        return {
            'adx': adx_indicator.adx(),
            'plus_di': adx_indicator.adx_pos(),
            'minus_di': adx_indicator.adx_neg()
        }
    except Exception as e:
        print(f"Error computing DMI: {e}")
        # Return empty series with the same index as df
        return {
            'adx': pd.Series(np.nan, index=df.index),
            'plus_di': pd.Series(np.nan, index=df.index),
            'minus_di': pd.Series(np.nan, index=df.index)
        }

def slope(series):
    if series is None or len(series) == 0:
        return np.nan
        
    # First ensure we have enough non-NaN values
    clean_series = series.dropna()
    if len(clean_series) < SLOPE_PERIOD:
        return np.nan
    
    # Get the last SLOPE_PERIOD non-NaN values
    y = clean_series.values[-SLOPE_PERIOD:]
    x = np.arange(len(y))
    
    # Use try/except to catch any numerical errors
    try:
        return np.polyfit(x, y, 1)[0]
    except Exception as e:
        print(f"Error calculating slope: {e}")
        return np.nan

def signal_from_indicators(df):
    # Use only the last bar's K vs D (not a crossover)
    try:
        # First check if DataFrame has enough data
        if df is None or df.empty or len(df) < 1:
            print("Warning: Empty DataFrame provided to signal_from_indicators")
            return 'Neutral'
            
        # Check for required columns
        required_cols = ['K', 'D', 'CCI', 'ADX', 'plus_di', 'minus_di']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            print(f"Warning: Missing required columns in DataFrame: {missing_cols}")
            return 'Neutral'
        
        # Extract values safely
        k_now   = df['K'].iloc[-1]
        d_now   = df['D'].iloc[-1]
        cci_now = df['CCI'].iloc[-1]
        adx_now = df['ADX'].iloc[-1]
        plus_di_now = df['plus_di'].iloc[-1]
        minus_di_now = df['minus_di'].iloc[-1]
        
        # Check for NaN values in critical indicators
        if pd.isna(k_now) or pd.isna(d_now) or pd.isna(cci_now) or pd.isna(adx_now) or pd.isna(plus_di_now) or pd.isna(minus_di_now):
            print("Warning: NaN values found in required indicators")
            return 'Neutral'
        
        # Calculate or retrieve slopes
        slope_k = df['slope_K'].iloc[-1] if 'slope_K' in df.columns else slope(df['K'])
        slope_d = df['slope_D'].iloc[-1] if 'slope_D' in df.columns else slope(df['D'])
    except (KeyError, IndexError, ValueError) as e:
        # Handle missing columns or empty DataFrame
        print(f"Warning: Error extracting indicators from DataFrame: {e}")
        return 'Neutral'
    
    # Basic conditions
    k_above_d = (k_now > d_now)
    k_below_d = (k_now < d_now)
    cci_bearish = (cci_now > 100)
    cci_bullish = (cci_now < -100)
    dmi_bullish = (plus_di_now > minus_di_now and adx_now > ADX_THRESHOLD)
    dmi_bearish = (minus_di_now > plus_di_now and adx_now > ADX_THRESHOLD)
    strong_slopes = (abs(slope_k) > SLOPE_THRESHOLD and abs(slope_d) > SLOPE_THRESHOLD)
    
    # Signal logic based on the four conditions
    if k_above_d and cci_bullish:
        if dmi_bullish and strong_slopes:
            return 'Buy+'
        elif not dmi_bearish:
            return 'Buy'
    elif k_below_d and cci_bearish:
        if dmi_bearish and strong_slopes:
            return 'Sell+'
        elif not dmi_bullish:
            return 'Sell'
    
    return 'Neutral'

def main():
    # Load tokens from "symbols" sheet in Excel
    symbols_df = pd.read_excel(EXCEL_FILE, sheet_name="symbols")
    # Extract the 'Symbols' column, dropna to ignore empty cells, and convert to string
    tokens = symbols_df["Symbols"].dropna().astype(str).tolist()

    new_signals = {tf: [] for tf in TIMEFRAMES} # Holds list of dicts for each timeframe
    all_latest_k_d_values_for_tokens = {} # Stores latest K/D for all token/timeframe pairs

    # Phase 1: Calculate basic signals and store latest K/D for all token/timeframes
    for token in tokens:
        if token not in all_latest_k_d_values_for_tokens:
            all_latest_k_d_values_for_tokens[token] = {}
        ticker = yf.Ticker(token)
        for sheet, cfg in TIMEFRAMES.items(): # sheet is the timeframe key e.g. 'daily'
            try:
                df = ticker.history(period=cfg['period'], interval=cfg['interval'])
            except Exception as e:
                print(f"Error fetching data for {token} ({sheet}): {e}")
                continue
                
            # Verify we have enough data for calculations
            if df.empty or len(df) < SLOPE_PERIOD:
                print(f"Warning: Insufficient data for {token} ({sheet}): {len(df) if not df.empty else 0} rows, need at least {SLOPE_PERIOD}")
                continue

            if getattr(df.index, 'tz', None) is not None:
                df.index = df.index.tz_localize(None)

            try:
                # Compute Stochastic indicators
                df['K'], df['D'] = compute_stoch(
                    df, STOCH_PARAMS['window'],
                    STOCH_PARAMS['k_smooth'],
                    STOCH_PARAMS['d_smooth']
                )
                
                # Compute CCI indicator
                df['CCI'] = compute_cci(df, CCI_PERIOD)
                
                # Compute DMI components
                dmi_components = compute_dmi(df, DMI_PERIOD)
                df['ADX'] = dmi_components['adx']
                df['plus_di'] = dmi_components['plus_di']
                df['minus_di'] = dmi_components['minus_di']
                
                # Drop rows with NaN values in critical columns
                ind = df.dropna(subset=['K','D','CCI','ADX','plus_di','minus_di'])
                
                if ind.empty:
                    print(f"Warning: No valid indicators for {token} ({sheet}) after dropna")
                    continue
                
                # Sanity check: ensure we have enough data for slope calculations
                if len(ind) < SLOPE_PERIOD:
                    print(f"Warning: Insufficient data for {token} ({sheet}) after filtering: {len(ind)} rows, need at least {SLOPE_PERIOD}")
                    continue
                    
            except Exception as e:
                print(f"Error computing indicators for {token} ({sheet}): {e}")
                continue

            # Store latest K/D for this token/timeframe
            latest_k = ind['K'].iloc[-1]
            latest_d = ind['D'].iloc[-1]
            if pd.notna(latest_k) and pd.notna(latest_d):
                all_latest_k_d_values_for_tokens[token][sheet] = {
                    'K': latest_k,
                    'D': latest_d
                }

            sig = signal_from_indicators(ind)
            if sig == 'Neutral':
                continue
            else:
                print(f"Signal for {token} ({sheet}): {sig}")
            
            last_row_data = ind.iloc[-1]            
            signal_entry = {
                'datetime'   : last_row_data.name,
                'signal'     : sig,
                'token'      : token,
                'close price': last_row_data['Close'],
                'CCI'        : last_row_data['CCI'],
                'stoch K'    : last_row_data['K'], # This is the K for the signal's specific datetime
                'stoch D'    : last_row_data['D'], # This is the D for the signal's specific datetime
                'slope K'    : slope(ind['K']), 
                'slope D'    : slope(ind['D']), 
                'ADX'        : last_row_data['ADX'],
                'plus_di'    : last_row_data['plus_di'],
                'minus_di'   : last_row_data['minus_di'],
            }
            new_signals[sheet].append(signal_entry)

    # Phase 2: Enrich signals with inter-timeframe trends using all_latest_k_d_values_for_tokens
    for tf_key_enrich, signals_list_enrich in new_signals.items(): # Iterate Buy/Sell signals
        for signal_data_enrich in signals_list_enrich: 
            current_token = signal_data_enrich['token']
            for other_tf in TIMEFRAMES.keys():
                if other_tf == tf_key_enrich: # Don't compare a timeframe with itself
                    continue 
                
                trend_col_name = f'{other_tf}_trend'
                trend_val = "" 

                # Use the comprehensive all_latest_k_d_values_for_tokens
                if current_token in all_latest_k_d_values_for_tokens and \
                   other_tf in all_latest_k_d_values_for_tokens[current_token]:
                    
                    other_k_val = all_latest_k_d_values_for_tokens[current_token][other_tf]['K']
                    other_d_val = all_latest_k_d_values_for_tokens[current_token][other_tf]['D']
                    
                    if pd.notna(other_k_val) and pd.notna(other_d_val):
                        if other_k_val > other_d_val:
                            trend_val = "up"
                        elif other_k_val < other_d_val:
                            trend_val = "down"
                signal_data_enrich[trend_col_name] = trend_val

    # Phase 3: Excel Processing (largely same as before, uses enriched new_signals)
    NOTES_COL = 'notes'
    BASE_COLS = ['datetime', 'signal', 'token', 'close price', 'CCI', 'stoch K', 'stoch D', 'slope K', 'slope D', 'ADX']

    try:
        existing_excel_content = pd.read_excel(EXCEL_FILE, sheet_name=None) if os.path.exists(EXCEL_FILE) else {}
    except Exception as e:
        print(f"Error reading Excel {EXCEL_FILE}: {e}. Treating as empty.")
        existing_excel_content = {}

    output_excel_content = existing_excel_content.copy()

    for sheet_name, current_signals_list in new_signals.items():
        other_timeframes = [tf for tf in TIMEFRAMES if tf != sheet_name]
        trend_cols_for_this_sheet = sorted([f'{tf}_trend' for tf in other_timeframes])
        
        desired_cols_ordered = ['datetime', 'signal', NOTES_COL] + \
                               [bc for bc in BASE_COLS if bc not in ['datetime', 'signal']] + \
                               trend_cols_for_this_sheet

        new_df = pd.DataFrame(current_signals_list)

        for col in desired_cols_ordered:
            if col not in new_df.columns:
                new_df[col] = ""
        new_df = new_df.reindex(columns=desired_cols_ordered)

        old_df = existing_excel_content.get(sheet_name, pd.DataFrame())

        for col in desired_cols_ordered:
            if col not in old_df.columns:
                old_df[col] = ""
        old_df = old_df.reindex(columns=desired_cols_ordered)
        if NOTES_COL in old_df.columns:
            old_df[NOTES_COL] = old_df[NOTES_COL].fillna("").astype(str)

        merge_keys = ['datetime', 'token', 'signal']
        combined_df = pd.DataFrame()

        if not new_df.empty:
            if not old_df.empty and NOTES_COL in old_df.columns and all(k in old_df.columns for k in merge_keys):
                new_df_for_merge = new_df.drop(columns=[NOTES_COL], errors='ignore')
                merged_with_old_notes = pd.merge(
                    new_df_for_merge,
                    old_df[merge_keys + [NOTES_COL]],
                    on=merge_keys,
                    how='left',
                    suffixes=('', '_old_note')
                )
                if NOTES_COL + '_old_note' in merged_with_old_notes.columns:
                    merged_with_old_notes[NOTES_COL] = merged_with_old_notes[NOTES_COL + '_old_note']
                    merged_with_old_notes.drop(columns=[NOTES_COL + '_old_note'], inplace=True)
                else:
                     merged_with_old_notes[NOTES_COL] = merged_with_old_notes.get(NOTES_COL, "")
                merged_with_old_notes[NOTES_COL] = merged_with_old_notes[NOTES_COL].fillna("")
                
                for col_from_new in new_df.columns: # Ensure all columns from new_df are present
                    if col_from_new not in merged_with_old_notes.columns:
                        merged_with_old_notes[col_from_new] = new_df[col_from_new]
                combined_df = merged_with_old_notes
            else:
                combined_df = new_df.copy()

            if not old_df.empty and all(k in new_df.columns for k in merge_keys) and all(k in old_df.columns for k in merge_keys):
                # Ensure indices are unique before trying to identify non-overlapping rows
                new_df_temp_indexed = new_df.drop_duplicates(subset=merge_keys).set_index(merge_keys)
                old_df_temp_indexed = old_df.drop_duplicates(subset=merge_keys).set_index(merge_keys)
                
                old_rows_not_in_new = old_df[~old_df_temp_indexed.index.isin(new_df_temp_indexed.index)]
                if not old_rows_not_in_new.empty:
                    combined_df = pd.concat([combined_df, old_rows_not_in_new], ignore_index=True)
            elif not old_df.empty and combined_df.empty: 
                 combined_df = old_df.copy()
        elif not old_df.empty:
            combined_df = old_df.copy()
        else:
            combined_df = pd.DataFrame(columns=desired_cols_ordered)

        combined_df = combined_df.reindex(columns=desired_cols_ordered)
        for col in desired_cols_ordered:
            if col not in combined_df.columns:
                combined_df[col] = ""
        
        if NOTES_COL in combined_df.columns:
            combined_df[NOTES_COL] = combined_df[NOTES_COL].fillna("").astype(str)

        if all(k in combined_df.columns for k in merge_keys) and not combined_df.empty:
            combined_df.drop_duplicates(subset=merge_keys, keep='first', inplace=True)

        num_cols_to_round = ['close price','CCI','stoch K','stoch D','slope K','slope D','ADX']
        for col in num_cols_to_round:
            if col in combined_df.columns:
                combined_df[col] = pd.to_numeric(combined_df[col], errors='coerce').round(2)
        
        output_excel_content[sheet_name] = combined_df

    with pd.ExcelWriter(EXCEL_FILE, engine='openpyxl') as writer:
        for sheet_name_to_write, df_to_write in output_excel_content.items():
            if df_to_write is not None:
                if sheet_name_to_write in TIMEFRAMES:
                    s_other_timeframes = [tf for tf in TIMEFRAMES if tf != sheet_name_to_write]
                    s_trend_cols = sorted([f'{tf}_trend' for tf in s_other_timeframes])
                    s_final_ordered_cols = ['datetime', 'signal', NOTES_COL] + \
                                           [bc for bc in BASE_COLS if bc not in ['datetime', 'signal']] + \
                                           s_trend_cols + ['plus_di', 'minus_di']
                    for col_ensure in s_final_ordered_cols: # Ensure all columns exist before reindex
                        if col_ensure not in df_to_write.columns:
                            df_to_write[col_ensure] = ""
                    df_to_write = df_to_write.reindex(columns=s_final_ordered_cols) # Enforce order for data sheets
                
                df_to_write.to_excel(writer, sheet_name=sheet_name_to_write, index=False)

    print(f"Updated '{EXCEL_FILE}' with signals and inter-timeframe trends for: {', '.join(tokens) if tokens else 'no tokens'}")

if __name__ == "__main__":
    main()