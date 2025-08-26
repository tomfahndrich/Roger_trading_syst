import os
import numpy as np
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pandas as pd
from trading_signal_generator import main as generate_signals, TIMEFRAMES, EXCEL_FILE, TRADE_COLS
import threading
import tempfile
import shutil

# BASE_COLS from trading_signal_generator.py: ['datetime', 'signal', 'token', 'close price', 'CCI', 'stoch K', 'stoch D', 'slope K', 'slope D', 'ADX']
BASE_COLS_GUI = ['datetime', 'signal', 'token', 'close price', 'CCI', 'stoch K', 'stoch D', 'slope K', 'slope D', 'ADX']
# Hidden DMI columns for internal use (not displayed)
HIDDEN_DMI_COLS = ['+DI', '-DI']
NOTES_COL_GUI = 'notes'
TRADE_COLS_GUI = TRADE_COLS  # Reuse ordering from generator
ALL_NEW_ORDER_APPEND = TRADE_COLS_GUI

DATA_LOCK = threading.Lock()

def format_decimal(val):
    if val is None or val == "" or (isinstance(val, float) and pd.isna(val)):
        return ""
    try:
        return f"{float(val):.2f}"
    except Exception:
        return ""

def compute_pnl(entry, exit_price, trade_type):
    """Compute absolute and percent PNL based on trade type.

    Buy:  PNL = Exit - Entry
          PNL% = (Exit - Entry) / Entry * 100
    Sell: PNL = Entry - Exit
          PNL% = (Entry - Exit) / Entry * 100
    Returns (pnl, pnl_pct) or (None, None) if insufficient data.
    """
    try:
        if trade_type not in ("Buy", "Sell"):
            return None, None
        if entry in (None, "") or exit_price in (None, ""):
            return None, None
        if pd.isna(entry) or pd.isna(exit_price):
            return None, None
        e = float(entry)
        x = float(exit_price)
        if trade_type == 'Buy':
            pnl = x - e
        else:  # Sell
            pnl = e - x
        if e == 0:
            return pnl, None
        pnl_pct = (pnl / e) * 100.0
        return pnl, pnl_pct
    except Exception:
        return None, None

# Create a tooltip class for better UI
class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.widget.bind("<Enter>", self.show_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)
    
    def show_tooltip(self, event=None):
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        
        # Create a toplevel window
        self.tooltip_window = tk.Toplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x}+{y}")
        
        label = tk.Label(self.tooltip_window, text=self.text, 
                         background="#FFFFDD", relief="solid", borderwidth=1,
                         font=("Arial", 10), padx=5, pady=2)
        label.pack(ipadx=2)
    
    def hide_tooltip(self, event=None):
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

# Define constants
COLUMN_WIDTHS = {
    'datetime': 150,
    'signal': 60,
    NOTES_COL_GUI: 200, # Use constant
    'token': 80,
    'close price': 100,
    'CCI': 80,
    'stoch K': 80,
    'stoch D': 80,
    'slope K': 80,
    'slope D': 80,
    'Trade Type': 90,
    'Entry Price': 100,
    'Target Exit Price': 120,
    'Exit Price': 100,
    'PNL': 80,
    'PNL %': 80,
    # Trend columns will be added dynamically, default width can be set or handled in display_data
}

class TradingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Roger Trading System")
        self.root.geometry("1200x700")
        
        style = ttk.Style()
        if 'vista' in style.theme_names():
            style.theme_use('vista')
        elif 'clam' in style.theme_names():
            style.theme_use('clam')
        
        style.configure("Treeview", font=('Arial', 10))
        style.configure("Treeview.Heading", font=('Arial', 11, 'bold'))
        
        # Initialize data dictionary with empty DataFrames structured dynamically, including hidden DMI cols
        self.data = {}
        for sheet in TIMEFRAMES:
            other_timeframes = [tf for tf in TIMEFRAMES if tf != sheet]
            trend_cols_for_this_sheet = sorted([f'{tf}_trend' for tf in other_timeframes])
            current_sheet_columns = BASE_COLS_GUI + HIDDEN_DMI_COLS + trend_cols_for_this_sheet + [NOTES_COL_GUI] + ALL_NEW_ORDER_APPEND
            df = pd.DataFrame(columns=current_sheet_columns)
            df[NOTES_COL_GUI] = df[NOTES_COL_GUI].astype(str)
            for tc in ALL_NEW_ORDER_APPEND:
                if tc not in df.columns:
                    df[tc] = ""
            self.data[sheet] = df
            
        # Create menu
        self.create_menu()
        
        # Create main layout
        self.create_widgets()
        
        # Load data
        self.load_data()
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing) # Ensure on_closing is called

    def create_menu(self):
        """Create application menu"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Update Data", command=self.update_data)
        file_menu.add_command(label="Export to Excel", command=self.export_to_excel)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_closing)
        
        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Show All Signals", command=lambda: self.filter_signals("all"))
        view_menu.add_command(label="Show Buy Signals", command=lambda: self.filter_signals("buy"))
        view_menu.add_command(label="Show Sell Signals", command=lambda: self.filter_signals("sell"))
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about)

    def create_widgets(self):
        # Create a header frame with blue color that matches the update button
        header_frame = tk.Frame(self.root, bg="#1565C0")
        header_frame.pack(fill=tk.X)
        
        # Add title
        title_label = tk.Label(header_frame, text="Roger Trading System", 
                              bg="#1565C0", fg="white", font=("Arial", 16, "bold"), pady=10)
        title_label.pack(fill=tk.X)
        
        # Create a button frame with subtle gradient
        button_frame = tk.Frame(self.root, bg="#DCDAD5", relief=tk.GROOVE, bd=0)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Add a container for the update button with padding
        update_container = tk.Frame(button_frame, bg="#DCDAD5", padx=5, pady=5)
        update_container.pack(side=tk.LEFT)
        
        # Add update button with improved visibility
        update_btn = tk.Button(update_container, text="📊 Update Data", command=self.update_data, 
                              bg="#DCDAD5", fg="black", font=("Arial", 14, "bold"), 
                              padx=30, pady=12, relief=tk.RAISED,
                              borderwidth=3, cursor="hand2")
        
        #shadow_frame = tk.Frame(update_container, bg="#0D47A1", bd=0)
        # Defer placement of shadow until button is packed and has size
        update_btn.pack(padx=10, pady=5)
        self.root.update_idletasks() # Ensure button has dimensions
        #shadow_frame.place(x=update_btn.winfo_x() + 3, y=update_btn.winfo_y() + 3, 
         #                  width=update_btn.winfo_width(), height=update_btn.winfo_height())
        update_btn.lift()
        
        # Add tooltip to update button
        ToolTip(update_btn, "Fetch the latest trading signals and update the data tables")
        
        # Add filter buttons
        filter_frame = tk.Frame(button_frame, bg="#DCDAD5")
        filter_frame.pack(side=tk.LEFT, padx=20)
        
        filter_label = tk.Label(filter_frame, text="Quick Filters:", bg="#DCDAD5", fg="black", font=("Arial", 11)) # Changed bg to #DCDAD5
        filter_label.pack(side=tk.LEFT, padx=5)
        
        all_btn = tk.Button(filter_frame, text="All", command=lambda: self.filter_signals("all"), 
                           bg="#DCDAD5", width=6, cursor="hand2",
                           relief=tk.FLAT, borderwidth=0, highlightthickness=0, highlightbackground="gray")
        all_btn.pack(side=tk.LEFT, padx=2)
        ToolTip(all_btn, "Show all trading signals")
        
        buy_btn = tk.Button(filter_frame, text="Buy", command=lambda: self.filter_signals("buy"), 
                           bg="#C8E6C9", width=6, cursor="hand2",
                           relief=tk.FLAT, borderwidth=0, highlightthickness=0, highlightbackground="gray")
        buy_btn.pack(side=tk.LEFT, padx=2)
        ToolTip(buy_btn, "Show only Buy signals")
        
        sell_btn = tk.Button(filter_frame, text="Sell", command=lambda: self.filter_signals("sell"), 
                            bg="#FFCDD2", width=6, cursor="hand2",
                            relief=tk.FLAT, borderwidth=0, highlightthickness=0, highlightbackground="gray")
        sell_btn.pack(side=tk.LEFT, padx=2)
        ToolTip(sell_btn, "Show only Sell signals")
        
        # Add token search field
        token_search_frame = tk.Frame(filter_frame, bg="#DCDAD5")
        token_search_frame.pack(side=tk.LEFT, padx=10)
        
        token_label = tk.Label(token_search_frame, text="Token:", bg="#DCDAD5", fg="black", font=("Arial", 11))
        token_label.pack(side=tk.LEFT, padx=2)
        
        self.token_var = tk.StringVar()
        self.token_var.trace_add("write", lambda *args: self.apply_all_filters())
        token_entry = tk.Entry(token_search_frame, textvariable=self.token_var, width=10, 
                              bg="white", fg="black")
        token_entry.pack(side=tk.LEFT, padx=2)
        
        clear_btn = tk.Button(token_search_frame, text="✕", command=lambda: self.clear_token_filter(), 
                             bg="#DCDAD5", width=2, cursor="hand2",
                             relief=tk.FLAT, borderwidth=0, highlightthickness=0)
        clear_btn.pack(side=tk.LEFT, padx=1)
        ToolTip(clear_btn, "Clear token filter")
        
        # Add slope K filter
        slope_k_frame = tk.Frame(filter_frame, bg="#DCDAD5")
        slope_k_frame.pack(side=tk.LEFT, padx=10)
        slope_k_label = tk.Label(slope_k_frame, text="Slope K", bg="#DCDAD5", fg="black", font=("Arial", 11))
        slope_k_label.pack(side=tk.LEFT, padx=2)
        self.slope_k_var = tk.StringVar()
        self.slope_k_var.trace_add("write", lambda *args: self.apply_all_filters())
        slope_k_entry = tk.Entry(slope_k_frame, textvariable=self.slope_k_var, width=5, bg="white", fg="black")
        slope_k_entry.pack(side=tk.LEFT, padx=2)
        ToolTip(slope_k_entry, "Filter by slope K: positive > threshold, negative < threshold")
        
        # Add slope D filter
        slope_d_frame = tk.Frame(filter_frame, bg="#DCDAD5")
        slope_d_frame.pack(side=tk.LEFT, padx=10)
        slope_d_label = tk.Label(slope_d_frame, text="Slope D", bg="#DCDAD5", fg="black", font=("Arial", 11))
        slope_d_label.pack(side=tk.LEFT, padx=2)
        self.slope_d_var = tk.StringVar()
        self.slope_d_var.trace_add("write", lambda *args: self.apply_all_filters())
        slope_d_entry = tk.Entry(slope_d_frame, textvariable=self.slope_d_var, width=5, bg="white", fg="black")
        slope_d_entry.pack(side=tk.LEFT, padx=2)
        ToolTip(slope_d_entry, "Filter by slope D: positive > threshold, negative < threshold")
        # Add ADX filter
        adx_frame = tk.Frame(filter_frame, bg="#DCDAD5")
        adx_frame.pack(side=tk.LEFT, padx=10)
        adx_label = tk.Label(adx_frame, text="ADX", bg="#DCDAD5", fg="black", font=("Arial", 11))
        adx_label.pack(side=tk.LEFT, padx=2)
        self.adx_var = tk.StringVar()
        self.adx_var.trace_add("write", lambda *args: self.apply_all_filters())
        adx_entry = tk.Entry(adx_frame, textvariable=self.adx_var, width=5, bg="white", fg="black")
        adx_entry.pack(side=tk.LEFT, padx=2)
        ToolTip(adx_entry, "Filter by ADX: positive > threshold, negative < threshold")
        
        # Add reset filters button
        reset_btn = tk.Button(filter_frame, text="🔄 Reset Filters", command=self.reset_filters, bg="#DCDAD5", cursor="hand2")
        reset_btn.pack(side=tk.LEFT, padx=10)
        ToolTip(reset_btn, "Clear all filters and show all signals")
        # Add info label with icon
        info_frame = tk.Frame(button_frame, bg="#f0f0f0")
        info_frame.pack(side=tk.RIGHT, padx=10)
        
        info_icon = tk.Label(info_frame, text="ℹ️", font=("Arial", 14), bg="#f0f0f0")
        info_icon.pack(side=tk.LEFT)
        
        info_label = tk.Label(info_frame, text="Double-click on notes field to edit", fg="#666", bg="#f0f0f0")
        info_label.pack(side=tk.LEFT, padx=5)
        ToolTip(info_label, "Click on any note field to add or edit notes. Notes are saved automatically to Excel.")
        
        # Create notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Create tabs and frames
        self.tabs = {}
        self.trees = {}
        
        for sheet in TIMEFRAMES:
            # Create frame for tab
            frame = tk.Frame(self.notebook)
            self.tabs[sheet] = frame
            self.notebook.add(frame, text=sheet.capitalize())
            
            # Create treeview for data
            tree = ttk.Treeview(frame)
            self.trees[sheet] = tree
            
            # Configure scrollbars - use ttk scrollbars for better look
            vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
            hsb = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
            tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
            
            # Pack scrollbars and tree
            vsb.pack(side=tk.RIGHT, fill=tk.Y)
            hsb.pack(side=tk.BOTTOM, fill=tk.X)
            tree.pack(fill=tk.BOTH, expand=True)
            
            # Configure tags for Buy+/Buy/Sell/Sell+ colors
            tree.tag_configure('buy+', background='#388e3c')     # Green
            tree.tag_configure('buy', background='#e8f5e9')      # Very light green
            tree.tag_configure('sell', background='#ffebee')     # Very light red
            tree.tag_configure('sell+', background='#e57373')    # Red
            tree.tag_configure('buy-', background='#d3d3d3')  # Light grey for divergent slopes
            tree.tag_configure('sell-', background='#d3d3d3')  # Light grey for divergent slopes
            # Enable editing the notes column
            tree.bind("<Double-1>", self.on_double_click)

        # Add status bar
        self.status_var = tk.StringVar()
        status_bar = tk.Label(self.root, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor=tk.W, pady=3)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_var.set("Ready")

    def load_data(self):
        """Load data exclusively from Excel file."""
        try:
            # Initialize self.data with empty, correctly structured DataFrames first
            for sheet in TIMEFRAMES:
                other_timeframes = [tf for tf in TIMEFRAMES if tf != sheet]
                trend_cols_for_this_sheet = sorted([f'{tf}_trend' for tf in other_timeframes])
                current_sheet_columns = BASE_COLS_GUI + HIDDEN_DMI_COLS + trend_cols_for_this_sheet + [NOTES_COL_GUI] + ALL_NEW_ORDER_APPEND
                df = pd.DataFrame(columns=current_sheet_columns)
                df[NOTES_COL_GUI] = df[NOTES_COL_GUI].astype(str) # Ensure notes column is string
                self.data[sheet] = df

            if os.path.exists(EXCEL_FILE):
                self.status_var.set("Loading data from Excel...")
                excel_data_sheets = pd.read_excel(EXCEL_FILE, sheet_name=None)
                
                for sheet_name_from_excel, df_from_excel in excel_data_sheets.items():
                    if sheet_name_from_excel in TIMEFRAMES: # Process only sheets defined in TIMEFRAMES
                        # Determine expected columns for this sheet
                        other_timeframes = [tf for tf in TIMEFRAMES if tf != sheet_name_from_excel]
                        trend_cols_for_this_sheet = sorted([f'{tf}_trend' for tf in other_timeframes])
                        # Include hidden DMI columns in loaded data
                        expected_cols = BASE_COLS_GUI + HIDDEN_DMI_COLS + trend_cols_for_this_sheet + [NOTES_COL_GUI] + ALL_NEW_ORDER_APPEND
                        
                        # Create a new DataFrame with expected columns
                        df_structured = pd.DataFrame(columns=expected_cols)
                        
                        # Fill with data from Excel, aligning columns
                        for col in expected_cols:
                            if col in df_from_excel.columns:
                                df_structured[col] = df_from_excel[col]
                            else:
                                df_structured[col] = pd.NA # Or some default like "" or np.nan
                        
                        if NOTES_COL_GUI in df_structured.columns:
                            df_structured[NOTES_COL_GUI] = df_structured[NOTES_COL_GUI].fillna("").astype(str)
                        else:
                            df_structured[NOTES_COL_GUI] = ""
                        # Ensure ADX column values include sign
                        def _add_sign_to_adx(v):
                            if pd.isna(v) or v == "":
                                return ""
                            s = str(v)
                            if s.startswith('+') or s.startswith('-'):
                                return s
                            try:
                                num = float(v)
                            except Exception:
                                return s
                            sign = '+' if num >= 0 else '-'
                            return f"{sign}{abs(num):.1f}"
                        df_structured['ADX'] = df_structured['ADX'].apply(_add_sign_to_adx)
                        # Ensure trade cols exist
                        for tc in ALL_NEW_ORDER_APPEND:
                            if tc not in df_structured.columns:
                                df_structured[tc] = ""
                        # Re-order columns to expected
                        df_structured = df_structured.reindex(columns=expected_cols)
                        self.data[sheet_name_from_excel] = df_structured
            else:
                messagebox.showinfo("Info", f"{EXCEL_FILE} not found. Displaying empty tables.")
                self.status_var.set(f"{EXCEL_FILE} not found.")
                # self.data is already initialized with empty structured DataFrames

            self.display_all_data() # Helper to refresh all tabs
            self.status_var.set("Data loaded successfully")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error loading data: {str(e)}")
            self.status_var.set(f"Error loading data: {str(e)}")
            # Fallback: ensure self.data has empty, structured DataFrames
            for sheet in TIMEFRAMES:
                other_timeframes = [tf for tf in TIMEFRAMES if tf != sheet]
                trend_cols_for_this_sheet = sorted([f'{tf}_trend' for tf in other_timeframes])
                current_sheet_columns = BASE_COLS_GUI + trend_cols_for_this_sheet + [NOTES_COL_GUI] + ALL_NEW_ORDER_APPEND
                df = pd.DataFrame(columns=current_sheet_columns)
                df[NOTES_COL_GUI] = df[NOTES_COL_GUI].astype(str)
                self.data[sheet] = df
            self.display_all_data()

    def display_all_data(self):
        """Helper function to refresh display for all sheets."""
        for sheet in TIMEFRAMES:
            self.display_data(sheet) # Pass the sheet name (key)

    def display_data(self, sheet_key):
        """Display data in the treeview for a specific sheet."""
        tree = self.trees[sheet_key]
        other_timeframes = [tf for tf in TIMEFRAMES if tf != sheet_key]
        trend_cols = sorted([f'{tf}_trend' for tf in other_timeframes])
        data_columns = BASE_COLS_GUI + HIDDEN_DMI_COLS + trend_cols + [NOTES_COL_GUI] + ALL_NEW_ORDER_APPEND
        display_columns = [c for c in data_columns if c not in HIDDEN_DMI_COLS]

        if sheet_key in self.data and isinstance(self.data[sheet_key], pd.DataFrame):
            df_from_data = self.data[sheet_key].copy()
        else:
            df_from_data = pd.DataFrame(columns=data_columns)

        for col in data_columns:
            if col not in df_from_data.columns:
                df_from_data[col] = pd.NA
        df_filled = df_from_data.reindex(columns=data_columns, fill_value=pd.NA)
        df_display = df_filled[display_columns].copy().fillna("")
        if NOTES_COL_GUI in df_display.columns:
            df_display[NOTES_COL_GUI] = df_display[NOTES_COL_GUI].fillna("").astype(str)

        # Clear existing rows
        for item in tree.get_children():
            tree.delete(item)

        tree['columns'] = display_columns
        tree['show'] = 'headings'
        for col in display_columns:
            tree.heading(col, text=col.replace('_',' ').title())
            tree.column(col, width=COLUMN_WIDTHS.get(col, 100), anchor=tk.CENTER)

        for _, row in df_display.iterrows():
            row_vals = []
            for col in display_columns:
                if col == 'ADX':
                    raw_val = row[col]
                    if raw_val in [None, ""]:
                        row_vals.append("")
                    else:
                        s = str(raw_val)
                        if s.startswith('+') or s.startswith('-'):
                            row_vals.append(s)
                        else:
                            try:
                                num = float(s)
                                row_vals.append(f"{'+' if num>=0 else '-'}{abs(num):.1f}")
                            except Exception:
                                row_vals.append(s)
                elif col in ['Entry Price','Target Exit Price','Exit Price','PNL','PNL %']:
                    v = row[col]
                    if v is None or v == "" or pd.isna(v):
                        row_vals.append("")
                    else:
                        row_vals.append(format_decimal(v))
                else:
                    row_vals.append("" if pd.isna(row[col]) else str(row[col]))

            sig = str(row.get('signal','')).lower()
            tag = ()
            if sig in ['buy+','buy','sell','sell+','sell-','buy-']:
                tag = (sig,)
            tree.insert('', 'end', values=row_vals, tags=tag)

        self.status_var.set(f"Displaying data for {sheet_key.capitalize()}")

    def save_data_to_excel(self): # Renamed for clarity, this is the main save mechanism
        """Save all data from self.data to the Excel file, preserving other sheets like 'symbols'."""
        try:
            with DATA_LOCK:
                preserve = {}
                if os.path.exists(EXCEL_FILE):
                    try:
                        xl = pd.ExcelFile(EXCEL_FILE)
                        for sn in xl.sheet_names:
                            if sn not in self.data:
                                preserve[sn] = pd.read_excel(xl, sn)
                    except Exception as er:
                        print("Preserve read warning:", er)

                # Recompute PNL columns before saving
                for sheet_name, df_app in self.data.items():
                    if isinstance(df_app, pd.DataFrame) and not df_app.empty:
                        if 'Entry Price' in df_app.columns and 'Exit Price' in df_app.columns:
                            pnl_vals = []
                            pnl_pct_vals = []
                            for _, r in df_app.iterrows():
                                pnl, pct = compute_pnl(r.get('Entry Price'), r.get('Exit Price'), r.get('Trade Type'))
                                pnl_vals.append(pnl)
                                pnl_pct_vals.append(pct)
                            df_app['PNL'] = pnl_vals
                            df_app['PNL %'] = pnl_pct_vals

                temp_fd, temp_path = tempfile.mkstemp(suffix='.xlsx', prefix='tmp_trading_')
                os.close(temp_fd)
                try:
                    with pd.ExcelWriter(temp_path, engine='openpyxl') as writer:
                        for sheet_name, df_app in self.data.items():
                            if df_app is not None and isinstance(df_app, pd.DataFrame):
                                other_tfs = [tf for tf in TIMEFRAMES if tf != sheet_name]
                                trends = sorted([f'{tf}_trend' for tf in other_tfs])
                                ordered = BASE_COLS_GUI + trends + [NOTES_COL_GUI] + ALL_NEW_ORDER_APPEND
                                for col in ordered:
                                    if col not in df_app.columns:
                                        df_app[col] = ""
                                df_save = df_app.reindex(columns=ordered)
                                if NOTES_COL_GUI in df_save.columns:
                                    df_save[NOTES_COL_GUI] = df_save[NOTES_COL_GUI].fillna("").astype(str)
                                # Format numeric columns to two decimals where applicable
                                for c in ['Entry Price','Target Exit Price','Exit Price','PNL','PNL %']:
                                    if c in df_save.columns:
                                        df_save[c] = pd.to_numeric(df_save[c], errors='coerce')
                                df_save.to_excel(writer, sheet_name=sheet_name, index=False)
                        for sn, df_pres in preserve.items():
                            df_pres.to_excel(writer, sheet_name=sn, index=False)
                    shutil.move(temp_path, EXCEL_FILE)
                finally:
                    if os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except OSError:
                            pass
            self.status_var.set("Saved")
        except Exception as e:
            messagebox.showerror("Save Error", f"Error: {e}")
            self.status_var.set("Save failed")

    def update_data(self):
        """Update data by running the trading signal generator and reloading from Excel."""
        try:
            self.status_var.set("Updating data...")
            self.root.update_idletasks()
            
            # 1. Save current notes from GUI (self.data) to Excel file
            self.save_data_to_excel() 

            # 2. Run signal generator (assumed to read from and write to EXCEL_FILE)
            generate_signals()
            
            # 3. Reload data from Excel to reflect all changes
            self.load_data() # This will also refresh the display
            
            self.status_var.set("Data updated successfully")
            messagebox.showinfo("Success", "Trading data updated successfully")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error updating data: {str(e)}")
            self.status_var.set(f"Error updating data: {str(e)}")

    def on_double_click(self, event):
        """Handle double-click on treeview to edit notes."""
        try:
            tab_id = self.notebook.select()
            if not tab_id:
                return
            sheet = self.notebook.tab(tab_id, "text").lower()
            if sheet not in self.trees:
                return
            tree = self.trees[sheet]
            column_id = tree.identify_column(event.x)
            item_id = tree.identify_row(event.y)
            if not item_id or not column_id:
                return
            column_idx = int(column_id.replace('#','')) - 1
            actual_tree_columns = tree["columns"]
            if column_idx < 0 or column_idx >= len(actual_tree_columns):
                return
            target_col = actual_tree_columns[column_idx]
            editable_cols = [NOTES_COL_GUI, 'Trade Type','Entry Price','Target Exit Price','Exit Price']
            if target_col not in editable_cols:
                return
        except Exception:
            return

        current_values = tree.item(item_id, "values")
        current_val = current_values[column_idx] if column_idx < len(current_values) else ""

        def locate_df_row(updated_values):
            try:
                dt_idx = actual_tree_columns.index('datetime')
                tk_idx = actual_tree_columns.index('token')
                sg_idx = actual_tree_columns.index('signal')
            except ValueError:
                return None
            key_dt = updated_values[dt_idx]
            key_token = updated_values[tk_idx]
            key_signal = updated_values[sg_idx]
            ds = self.data[sheet]
            if 'datetime' not in ds.columns:
                return None
            if pd.api.types.is_datetime64_any_dtype(ds['datetime']):
                try:
                    key_dt_obj = pd.to_datetime(key_dt)
                    mask = (ds['datetime'] == key_dt_obj) & (ds['token'].astype(str)==str(key_token)) & (ds['signal'].astype(str)==str(key_signal))
                except Exception:
                    mask = (ds['datetime'].astype(str)==str(key_dt)) & (ds['token'].astype(str)==str(key_token)) & (ds['signal'].astype(str)==str(key_signal))
            else:
                mask = (ds['datetime'].astype(str)==str(key_dt)) & (ds['token'].astype(str)==str(key_token)) & (ds['signal'].astype(str)==str(key_signal))
            idxs = ds.index[mask].tolist()
            return idxs[0] if idxs else None

        def commit_update(updated_values, field_name, new_value):
            row_idx = locate_df_row(updated_values)
            if row_idx is None:
                messagebox.showwarning("Update","Row not found for update")
                return
            df_sheet = self.data[sheet]
            if field_name == 'Trade Type':
                if new_value not in ['Buy','Sell']:
                    messagebox.showwarning('Validation','Trade Type must be Buy or Sell')
                    return
                df_sheet.at[row_idx,'Trade Type'] = new_value
                close_val = df_sheet.at[row_idx,'close price'] if 'close price' in df_sheet.columns else None
                try:
                    if close_val not in [None,""]:
                        df_sheet.at[row_idx,'Entry Price'] = float(close_val)
                except Exception:
                    df_sheet.at[row_idx,'Entry Price'] = ""
            elif field_name == NOTES_COL_GUI:
                # Always store notes as string
                df_sheet.at[row_idx, NOTES_COL_GUI] = str(new_value)
            elif field_name in ['Entry Price','Target Exit Price','Exit Price']:
                if new_value == "":
                    # Use np.nan to keep numeric dtype
                    df_sheet.at[row_idx, field_name] = np.nan
                else:
                    try:
                        val = float(new_value)
                        if field_name=='Entry Price' and val < 0:
                            raise ValueError
                        df_sheet.at[row_idx, field_name] = val
                    except Exception:
                        messagebox.showwarning('Validation', f'Invalid number for {field_name}')
                        return
            entry_v = df_sheet.at[row_idx,'Entry Price'] if 'Entry Price' in df_sheet.columns else None
            exit_v = df_sheet.at[row_idx,'Exit Price'] if 'Exit Price' in df_sheet.columns else None
            trade_type_v = df_sheet.at[row_idx,'Trade Type'] if 'Trade Type' in df_sheet.columns else None
            pnl, pct = compute_pnl(entry_v, exit_v, trade_type_v)
            df_sheet.at[row_idx,'PNL'] = pnl if pnl is not None else np.nan
            df_sheet.at[row_idx,'PNL %'] = pct if pct is not None else np.nan
            self.save_data_to_excel()
            self.display_data(sheet)

        if target_col == 'Trade Type':
            menu_var = tk.StringVar(value=current_val if current_val in ['Buy','Sell'] else 'Buy')
            option = tk.OptionMenu(tree, menu_var, 'Buy','Sell', command=lambda sel: (commit_update(list(current_values),'Trade Type', sel), opt.destroy()))
            opt = option
            x, y, width, height = tree.bbox(item_id, column_id)
            if width <=0 or height <=0:
                return
            opt.place(x=x, y=y, width=width, height=height)
            return

        entry = tk.Entry(tree, relief=tk.SOLID)
        entry.insert(0, str(current_val))

        def save_edit_action(_ev=None):
            new_val = entry.get().strip()
            updated_values = list(current_values)
            if column_idx < len(updated_values):
                updated_values[column_idx] = new_val
            commit_update(updated_values, target_col, new_val)
            entry.destroy()

        entry.bind("<Return>", save_edit_action)
        entry.bind("<FocusOut>", save_edit_action)
        entry.bind("<Escape>", lambda e: entry.destroy())
        x, y, width, height = tree.bbox(item_id, column_id)
        if width <=0 or height <=0:
            return
        entry.place(x=x, y=y, width=width, height=height)
        entry.focus_set()
        entry.selection_range(0, tk.END)

    def filter_signals(self, signal_type):
        """Filter data based on signal type (buy, sell, all)"""
        current_tab_id = self.notebook.select()
        if not current_tab_id:
            return
        sheet = self.notebook.tab(current_tab_id, "text").lower()
        
        # Use a temporary DataFrame for display to keep self.data intact
        if sheet not in self.data or not isinstance(self.data[sheet], pd.DataFrame):
            return # Should not happen
        
        df_full = self.data[sheet].copy()
        df_to_display = df_full
        
        if signal_type != "all" and 'signal' in df_full.columns:
            sig_series = df_full['signal'].astype(str).str.lower()
            if signal_type.lower() == 'buy':
                df_to_display = df_full[sig_series.isin(['buy', 'buy+'])]
            elif signal_type.lower() == 'sell':
                df_to_display = df_full[sig_series.isin(['sell', 'sell+'])]
            else:
                df_to_display = df_full[sig_series == signal_type.lower()]
        
        # Create a temporary display DataFrame to pass to display_data
        # This avoids modifying self.data[sheet] directly for filtering purposes
        current_data_for_sheet = self.data[sheet] # Backup
        self.data[sheet] = df_to_display # Temporarily set for display
        self.display_data(sheet) # This will use the filtered df_to_display
        self.data[sheet] = current_data_for_sheet # Restore original

        self.status_var.set(f"Displaying {signal_type.capitalize()} signals for {sheet.capitalize()}")
    
    def filter_by_token(self, token_text):
        """Filter data based on token name (case-insensitive partial match)"""
        if not token_text:
            # If token filter is empty, show all data
            self.filter_signals("all")
            return
            
        current_tab_id = self.notebook.select()
        if not current_tab_id:
            return
        sheet = self.notebook.tab(current_tab_id, "text").lower()
        
        # Use a temporary DataFrame for display to keep self.data intact
        if sheet not in self.data or not isinstance(self.data[sheet], pd.DataFrame):
            return # Should not happen
        
        df_full = self.data[sheet].copy()
        
        # Filter by token name (case-insensitive partial match)
        df_to_display = df_full[df_full['token'].astype(str).str.lower().str.contains(token_text.lower())]
        
        # Create a temporary display DataFrame to pass to display_data
        current_data_for_sheet = self.data[sheet] # Backup
        self.data[sheet] = df_to_display # Temporarily set for display
        self.display_data(sheet) # This will use the filtered df_to_display
        self.data[sheet] = current_data_for_sheet # Restore original

        self.status_var.set(f"Displaying tokens matching '{token_text}' for {sheet.capitalize()}")
    def filter_by_slope_k(self, slope_threshold):
        """Filter data based on slope K: positive values > threshold, negative values < threshold"""
        # Empty input shows all
        if slope_threshold == "":
            self.filter_signals("all")
            return
        try:
            thr = float(slope_threshold)
        except ValueError:
            return
        tab = self.notebook.select()
        if not tab:
            return
        sheet = self.notebook.tab(tab, "text").lower()
        if sheet not in self.data or not isinstance(self.data[sheet], pd.DataFrame):
            return
        df_full = self.data[sheet].copy()
        if thr >= 0:
            df_to_display = df_full[df_full['slope K'] > thr]
        else:
            df_to_display = df_full[df_full['slope K'] < thr]
        # Also apply slope D filter if set
        d_val = self.slope_d_var.get()
        if d_val != "":
            try:
                thr_d = float(d_val)
                if thr_d >= 0:
                    df_to_display = df_to_display[df_to_display['slope D'] > thr_d]
                else:
                    df_to_display = df_to_display[df_to_display['slope D'] < thr_d]
            except ValueError:
                pass
        # Temporarily display filtered data
        backup = self.data[sheet]
        self.data[sheet] = df_to_display
        self.display_data(sheet)
        self.data[sheet] = backup
        self.status_var.set(f"Filtering slope K {'>' if thr>=0 else '<'} {thr} for {sheet.capitalize()}")
    def filter_by_slope_d(self, slope_threshold):
        """Filter data based on slope D: positive values > threshold, negative values < threshold"""
        # Empty input shows all
        if slope_threshold == "":
            self.filter_signals("all")
            return
        try:
            thr = float(slope_threshold)
        except ValueError:
            return
        tab = self.notebook.select()
        if not tab:
            return
        sheet = self.notebook.tab(tab, "text").lower()
        if sheet not in self.data or not isinstance(self.data[sheet], pd.DataFrame):
            return
        df_full = self.data[sheet].copy()
        if thr >= 0:
            df_to_display = df_full[df_full['slope D'] > thr]
        else:
            df_to_display = df_full[df_full['slope D'] < thr]
        # Also apply slope K filter if set
        k_val = self.slope_k_var.get()
        if k_val != "":
            try:
                thr_k = float(k_val)
                if thr_k >= 0:
                    df_to_display = df_to_display[df_to_display['slope K'] > thr_k]
                else:
                    df_to_display = df_to_display[df_to_display['slope K'] < thr_k]
            except ValueError:
                pass
        # Temporarily display filtered data
        backup = self.data[sheet]
        self.data[sheet] = df_to_display
        self.display_data(sheet)
        self.data[sheet] = backup
        self.status_var.set(f"Filtering slope D {'>' if thr>=0 else '<'} {thr} for {sheet.capitalize()}")
    
    def filter_by_adx(self, adx_threshold):
        """Filter data based on ADX: positive values > threshold, negative values < threshold"""
        # Empty input shows all
        if adx_threshold == "":
            self.filter_signals("all")
            return
        try:
            thr = float(adx_threshold)
        except ValueError:
            return
        tab = self.notebook.select()
        if not tab:
            return
        sheet = self.notebook.tab(tab, "text").lower()
        if sheet not in self.data or not isinstance(self.data[sheet], pd.DataFrame):
            return
        df_full = self.data[sheet].copy()
        # Convert ADX strings to numeric
        adx_vals = pd.to_numeric(df_full['ADX'], errors='coerce')
        if thr >= 0:
            df_filtered = df_full[adx_vals > thr]
        else:
            df_filtered = df_full[adx_vals < thr]
        # Also apply slope K filter if set
        k_val = self.slope_k_var.get()
        if k_val != "":
            try:
                thr_k = float(k_val)
                slope_k_vals = pd.to_numeric(df_filtered['slope K'], errors='coerce')
                if thr_k >= 0:
                    df_filtered = df_filtered[slope_k_vals > thr_k]
                else:
                    df_filtered = df_filtered[slope_k_vals < thr_k]
            except ValueError:
                pass
        # Also apply slope D filter if set
        d_val = self.slope_d_var.get()
        if d_val != "":
            try:
                thr_d = float(d_val)
                slope_d_vals = pd.to_numeric(df_filtered['slope D'], errors='coerce')
                if thr_d >= 0:
                    df_filtered = df_filtered[slope_d_vals > thr_d]
                else:
                    df_filtered = df_filtered[slope_d_vals < thr_d]
            except ValueError:
                pass
        # Display filtered result
        backup = self.data[sheet]
        self.data[sheet] = df_filtered
        self.display_data(sheet)
        self.data[sheet] = backup
        self.status_var.set(f"Filtering ADX {'>' if thr>=0 else '<'} {thr} for {sheet.capitalize()}")
    def apply_all_filters(self):
        """Apply token, slope K, slope D and ADX filters together."""
        tab = self.notebook.select()
        if not tab:
            return
        sheet = self.notebook.tab(tab, "text").lower()
        if sheet not in self.data or not isinstance(self.data[sheet], pd.DataFrame):
            return
        df_full = self.data[sheet].copy()
        # Token filter
        tok = self.token_var.get().strip().lower()
        if tok:
            df_full = df_full[df_full['token'].astype(str).str.lower().str.contains(tok)]
        # Slope K filter
        k_val = self.slope_k_var.get().strip()
        if k_val:
            try:
                thr_k = float(k_val)
                if thr_k >= 0:
                    df_full = df_full[df_full['slope K'] > thr_k]
                else:
                    df_full = df_full[df_full['slope K'] < thr_k]
            except ValueError:
                pass
        # Slope D filter
        d_val = self.slope_d_var.get().strip()
        if d_val:
            try:
                thr_d = float(d_val)
                if thr_d >= 0:
                    df_full = df_full[df_full['slope D'] > thr_d]
                else:
                    df_full = df_full[df_full['slope D'] < thr_d]
            except ValueError:
                pass
        # ADX filter
        adx_val = self.adx_var.get().strip()
        if adx_val:
            try:
                thr_adx = float(adx_val)
                adx_num = pd.to_numeric(df_full['ADX'], errors='coerce')
                if thr_adx >= 0:
                    df_full = df_full[adx_num > thr_adx]
                else:
                    df_full = df_full[adx_num < thr_adx]
            except ValueError:
                pass
        # Display combined filters
        backup = self.data[sheet]
        self.data[sheet] = df_full
        self.display_data(sheet)
        self.data[sheet] = backup
        self.status_var.set(f"Applied all filters for {sheet.capitalize()}")
    def reset_filters(self):
        """Reset all filter inputs and display full data."""
        self.token_var.set("")
        self.slope_k_var.set("")
        self.slope_d_var.set("")
        self.adx_var.set("")
        self.apply_all_filters()
    def filter_by_slope(self, slope_threshold):
        """Filter data based on slope K and D thresholds"""
        if not slope_threshold:
            self.filter_signals("all")
            return
        try:
            threshold = float(slope_threshold)
        except ValueError:
            return
        current_tab_id = self.notebook.select()
        if not current_tab_id:
            return
        sheet = self.notebook.tab(current_tab_id, "text").lower()
        if sheet not in self.data or not isinstance(self.data[sheet], pd.DataFrame):
            return
        df_full = self.data[sheet].copy()
        df_to_display = df_full[(df_full['slope K'].abs() > threshold) & (df_full['slope D'].abs() > threshold)]
        # Temporarily set and display
        backup = self.data[sheet]
        self.data[sheet] = df_to_display
        self.display_data(sheet)
        self.data[sheet] = backup
        self.status_var.set(f"Displaying rows with slope > {slope_threshold} for {sheet.capitalize()}")
    
    def clear_token_filter(self):
        """Clear token filter and show all data"""
        self.token_var.set("")
        self.filter_signals("all")
        
    def export_to_excel(self):
        """Export current data (all sheets from self.data) to a new Excel file."""
        try:
            file_path = filedialog.asksaveasfilename(
                defaultextension=".xlsx",
                filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
                title="Export Data to Excel"
            )
            if not file_path:
                return
            
            with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                for sheet_name, df_app in self.data.items():
                    if df_app is not None and isinstance(df_app, pd.DataFrame):
                        df_to_export = df_app.copy()
                        
                        # Determine trend columns for this specific sheet for export
                        other_timeframes_export = [tf for tf in TIMEFRAMES if tf != sheet_name]
                        trend_cols_for_export = sorted([f'{tf}_trend' for tf in other_timeframes_export])
                        
                        # Define the desired column order for export, with NOTES_COL_GUI at the end
                        export_columns_ordered = BASE_COLS_GUI + trend_cols_for_export + [NOTES_COL_GUI] + ALL_NEW_ORDER_APPEND

                        # Ensure all necessary columns exist in df_to_export, fill with "" if not
                        for col in export_columns_ordered:
                            if col not in df_to_export.columns:
                                df_to_export[col] = ""
                        
                        # Ensure notes column is string and filled
                        if NOTES_COL_GUI in df_to_export.columns:
                            df_to_export[NOTES_COL_GUI] = df_to_export[NOTES_COL_GUI].fillna("").astype(str)
                        else: # Should be created by the loop above if NOTES_COL_GUI is in export_columns_ordered
                            df_to_export[NOTES_COL_GUI] = ""


                        # Reindex to the desired order
                        final_export_df = df_to_export.reindex(columns=export_columns_ordered, fill_value="")
                        
                        # Ensure notes is string after reindex, if it exists in final_export_df
                        if NOTES_COL_GUI in final_export_df.columns:
                           final_export_df[NOTES_COL_GUI] = final_export_df[NOTES_COL_GUI].fillna("").astype(str)

                        final_export_df.to_excel(writer, sheet_name=sheet_name, index=False)
            
            self.status_var.set(f"Data exported to {file_path}")
            messagebox.showinfo("Export Successful", f"Data exported to {file_path}")
            
        except Exception as e:
            messagebox.showerror("Export Error", f"Error exporting data: {str(e)}")
            self.status_var.set(f"Error exporting data: {str(e)}")

    def on_closing(self):
        """Handle application closing: save data to Excel and close."""
        try:
            self.save_data_to_excel()
        except Exception as e:
            print(f"Error saving data to Excel on closing: {str(e)}")
        finally:
            self.root.destroy()

    def show_about(self):
        """Show about dialog"""
        messagebox.showinfo("About Roger Trading System", 
                            "Version 1.2\\n\\n"
                            "This application displays trading signals and allows note-taking.\\n"
                            "Data is stored in an Excel file (trading_synthesis.xlsx).")

if __name__ == '__main__':
    root = tk.Tk()
    app = TradingApp(root)
    root.mainloop()