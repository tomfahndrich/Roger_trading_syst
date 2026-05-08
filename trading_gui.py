import os
import sys
import time
import webbrowser
import numpy as np
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import pandas as pd
from trading_signal_generator import main as generate_signals, TIMEFRAMES, EXCEL_FILE, TRADE_COLS
import threading
import tempfile
import shutil

# Make the symbols_finder helpers importable regardless of cwd. trading_gui.py
# may be launched directly from any directory; we anchor the package path on
# this file's location.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from Roger_trading_yfinance_symbol.symbols_finder import (
    best_symbol_for_company,
    lookup_info_for_symbol,
    to_yf_symbol,
)

# BASE_COLS from trading_signal_generator.py: ['datetime', 'signal', 'token', 'close price', 'CCI', 'stoch K', 'stoch D', 'slope K', 'slope D', 'ADX']
BASE_COLS_GUI = ['datetime', 'signal', 'token', 'close price', 'CCI', 'stoch K', 'stoch D', 'slope K', 'slope D', 'ADX']
# Hidden internal columns (DMI + crossover flag) for internal use (not displayed)
HIDDEN_DMI_COLS = ['+DI', '-DI', 'cross']
NOTES_COL_GUI = 'notes'
TRADE_COLS_GUI = TRADE_COLS  # Reuse ordering from generator
ALL_NEW_ORDER_APPEND = TRADE_COLS_GUI

# Symbols sheet schema (constants — single source of truth)
SYMBOLS_SHEET = 'symbols'
SOURCES_SHEET = 'sources'
SYMBOLS_COLS = ['Symbols', 'Company Name', 'Yahoo Finance URL', 'Source', 'Source URL']
# Columns updated on duplicate match. 'Symbols' is the row's identity and its
# original casing is preserved across updates.
UPDATABLE_SYMBOL_COLS = ['Company Name', 'Yahoo Finance URL', 'Source', 'Source URL']

# Default source list for the Add Tokens dropdown. Written to the `sources` sheet
# on first launch if absent; thereafter the xlsx is the source of truth so the
# user can edit sources without touching code.
DEFAULT_SOURCES = [
    "Buffet videos",
    "Diallo videos",
    "Raoul Pal",
    "Quentin Chapeau",
    "Investing.com Actu",
    "Investing.com - {NOM DE LA LISTE}",
]
INVESTING_LIST_TEMPLATE = "Investing.com - {NOM DE LA LISTE}"
INVESTING_PREFIX = "Investing.com"

DATA_LOCK = threading.Lock()


def parse_tokens(text):
    """Parse a multi-line text into a deduplicated, stripped list of non-empty tokens.
    Deduplication is case-insensitive; the first occurrence's casing is preserved."""
    seen = set()
    result = []
    for line in (text or "").splitlines():
        token = line.strip()
        if not token:
            continue
        key = token.upper()
        if key in seen:
            continue
        seen.add(key)
        result.append(token)
    return result


def build_source(template, list_name):
    """Resolve the final Source string written to the symbols sheet.
    Special case: the Investing.com template gets concatenated with list_name,
    or strips the suffix entirely when list_name is empty."""
    template = (template or "").strip()
    list_name = (list_name or "").strip()
    if template == INVESTING_LIST_TEMPLATE:
        return f"{INVESTING_PREFIX} - {list_name}" if list_name else INVESTING_PREFIX
    return template


def merge_symbol_rows(existing_df, new_rows):
    """Merge new_rows into existing_df, returning (merged_df, added, updated).

    - Matches existing rows on Symbols column case-insensitively (strip + upper)
    - Existing matches: every column in SYMBOLS_COLS is overwritten with the new value
    - Non-matches: appended at the end
    - Within-batch duplicates: first appended, later occurrences update the queued row
    - Rows with empty Symbols are silently skipped
    """
    df = existing_df.copy() if existing_df is not None else pd.DataFrame(columns=SYMBOLS_COLS)
    for col in SYMBOLS_COLS:
        if col not in df.columns:
            df[col] = ""
    df = df.reindex(columns=SYMBOLS_COLS)

    sym_lower = df['Symbols'].astype(str).str.strip().str.upper()
    by_symbol = {}
    for idx, sym in sym_lower.items():
        if sym and sym not in by_symbol:
            by_symbol[sym] = idx

    added = 0
    updated = 0
    appended = []  # ordered list of dict rows pending append
    appended_keys = {}  # sym_key -> index into appended

    for row in new_rows or []:
        sym_key = str(row.get('Symbols', '')).strip().upper()
        if not sym_key:
            continue
        if sym_key in by_symbol:
            idx = by_symbol[sym_key]
            # Preserve the existing Symbols casing — only metadata cols are overwritten
            for col in UPDATABLE_SYMBOL_COLS:
                df.at[idx, col] = row.get(col, df.at[idx, col])
            updated += 1
        elif sym_key in appended_keys:
            # Same rule for within-batch duplicates: first occurrence sets the casing
            entry = appended[appended_keys[sym_key]]
            for col in UPDATABLE_SYMBOL_COLS:
                entry[col] = row.get(col, entry[col])
        else:
            appended.append({col: row.get(col, '') for col in SYMBOLS_COLS})
            appended_keys[sym_key] = len(appended) - 1
            added += 1

    if appended:
        df = pd.concat(
            [df, pd.DataFrame(appended, columns=SYMBOLS_COLS)],
            ignore_index=True,
        )
    return df, added, updated


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


class TokenTooltip:
    """Tooltip enrichi affiché au survol de la colonne 'token' d'un Treeview.

    on_source_change(token, new_source) is invoked when the user clicks the
    Source line and picks a value from the dropdown. get_sources() must return
    the current list of available sources (typically backed by the xlsx).
    Both callbacks are optional — if omitted, the Source line stays read-only.
    """

    def __init__(self, tree: ttk.Treeview, symbol_info: dict,
                 on_source_change=None, get_sources=None):
        self.tree = tree
        self.symbol_info = symbol_info
        self.on_source_change = on_source_change
        self.get_sources = get_sources
        self.tooltip_window = None
        self.last_item = None
        self._hide_id = None
        self._current_token = None  # token shown in the active tooltip
        self._source_menu_var = None  # holds StringVar bound to the menu
        tree.bind("<Motion>", self.on_motion)
        tree.bind("<Leave>", self._schedule_hide)

    def on_motion(self, event):
        cols = list(self.tree["columns"])
        try:
            token_col_id = f"#{cols.index('token') + 1}"
        except ValueError:
            return
        col = self.tree.identify_column(event.x)
        item = self.tree.identify_row(event.y)
        if col != token_col_id or not item:
            self._schedule_hide()
            return
        if item == self.last_item:
            return
        self._cancel_hide()
        self.last_item = item
        values = self.tree.item(item, "values")
        try:
            token = values[cols.index("token")]
        except (IndexError, ValueError):
            return
        info = self.symbol_info.get(token, {})
        self._show(token,
                   info.get("company_name") or "-",
                   info.get("yf_url") or "",
                   info.get("source_url") or "",
                   info.get("source") or "-",
                   event.x_root + 15, event.y_root + 15)

    def _mouse_over_tooltip(self):
        """Return True if the mouse pointer is currently inside the tooltip window."""
        if not self.tooltip_window:
            return False
        try:
            mx = self.tree.winfo_pointerx()
            my = self.tree.winfo_pointery()
            wx = self.tooltip_window.winfo_rootx()
            wy = self.tooltip_window.winfo_rooty()
            ww = self.tooltip_window.winfo_width()
            wh = self.tooltip_window.winfo_height()
            return wx <= mx <= wx + ww and wy <= my <= wy + wh
        except Exception:
            return False

    def _schedule_hide(self, event=None):
        self._cancel_hide()
        self._hide_id = self.tree.after(400, self._do_hide)

    def _cancel_hide(self):
        if self._hide_id:
            self.tree.after_cancel(self._hide_id)
            self._hide_id = None

    def _do_hide(self):
        self._hide_id = None
        if self._mouse_over_tooltip():
            # Mouse is still over the tooltip — keep checking
            self._hide_id = self.tree.after(100, self._do_hide)
            return
        self.last_item = None
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

    def _show(self, token, company, yf_url, source_url, source, x, y):
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None
        self._current_token = token
        win = tk.Toplevel(self.tree)
        win.wm_overrideredirect(True)
        win.wm_geometry(f"+{x}+{y}")
        win.configure(background="#FFFFDD")
        pad = {"padx": 8, "pady": 2, "anchor": "w", "fg": "black"}
        tk.Label(win, text=f"Symbol:     {token}",  bg="#FFFFDD", font=("Arial", 10, "bold"), **pad).pack(fill="x")
        tk.Label(win, text=f"Company:    {company}", bg="#FFFFDD", font=("Arial", 10), **pad).pack(fill="x")
        if yf_url:
            lnk = tk.Label(win, text=f"URL:        {yf_url}", bg="#FFFFDD",
                           font=("Arial", 10), fg="blue", cursor="hand2", padx=8, pady=2, anchor="w")
            lnk.pack(fill="x")
            lnk.bind("<Button-1>", lambda e, u=yf_url: webbrowser.open(u))
        else:
            tk.Label(win, text="URL:        -", bg="#FFFFDD", font=("Arial", 10), **pad).pack(fill="x")
        if source_url:
            src_lnk = tk.Label(win, text=f"Source URL: {source_url}", bg="#FFFFDD",
                               font=("Arial", 10), fg="blue", cursor="hand2", padx=8, pady=2, anchor="w")
            src_lnk.pack(fill="x")
            src_lnk.bind("<Button-1>", lambda e, u=source_url: webbrowser.open(u))
        else:
            tk.Label(win, text="Source URL: -", bg="#FFFFDD", font=("Arial", 10), **pad).pack(fill="x")

        # Source line — clickable if callbacks are wired (opens a popup menu)
        editable = self.on_source_change is not None and self.get_sources is not None
        src_label = tk.Label(
            win,
            text=f"Source:     {source}  ▾" if editable else f"Source:     {source}",
            bg="#FFFFDD", font=("Arial", 10),
            fg="black", cursor="hand2" if editable else "",
            padx=8, pady=2, anchor="w",
        )
        src_label.pack(fill="x", pady=(0, 4))
        if editable:
            src_label.bind("<Button-1>", self._open_source_menu)

        win.update_idletasks()
        self.tooltip_window = win

    def _open_source_menu(self, event):
        """Pop a radio-button menu under the Source line, current value pre-selected.

        The menu is parented on the tree's toplevel — NOT on self.tooltip_window —
        so it survives the tooltip's hide cycle. Without this, moving the mouse
        from the tooltip to the menu would trigger _schedule_hide → _do_hide →
        tooltip Toplevel destruction → child Menu destruction (Tk parent rule),
        making lower menu items unreachable.
        """
        if not self.on_source_change or not self.get_sources:
            return
        sources = list(self.get_sources() or [])
        if not sources:
            return
        token = self._current_token
        if not token:
            return

        current = (self.symbol_info.get(token, {}) or {}).get("source", "") or ""
        # Ensure the current source appears in the menu even if it's not in the
        # canonical list anymore (legacy sources like 'TradingView')
        menu_sources = list(sources)
        if current and current not in menu_sources:
            menu_sources.insert(0, current)

        menu = tk.Menu(self.tree.winfo_toplevel(), tearoff=0)
        self._source_menu_var = tk.StringVar(value=current)
        for src in menu_sources:
            menu.add_radiobutton(
                label=src,
                value=src,
                variable=self._source_menu_var,
                command=lambda s=src, t=token: self._on_source_picked(t, s),
            )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _on_source_picked(self, token, new_source):
        """Forward the user's pick to the app, prompting for a list name when
        the Investing.com template is chosen."""
        if not self.on_source_change:
            return
        old = (self.symbol_info.get(token, {}) or {}).get("source", "")

        # Investing.com - {NOM DE LA LISTE} → ask the user for the actual name.
        # Pre-fill with the current list name if the existing source already
        # matches the 'Investing.com - <name>' shape, so editing is a one-liner.
        if new_source == INVESTING_LIST_TEMPLATE:
            prefix = f"{INVESTING_PREFIX} - "
            initial = old[len(prefix):] if old.startswith(prefix) else ""
            list_name = simpledialog.askstring(
                "Nom de la liste",
                "Nom de la liste Investing.com\n(vide → 'Investing.com' tout court)",
                initialvalue=initial,
                parent=self.tree.winfo_toplevel(),
            )
            if list_name is None:
                return  # cancelled — keep current source
            new_source = build_source(INVESTING_LIST_TEMPLATE, list_name)

        if new_source == old:
            return
        self.on_source_change(token, new_source)

    def hide(self, event=None):
        self._schedule_hide(event)


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
            
        # symbol_info: {token: {company_name, yf_url, source, source_url}} — populated in load_data()
        self.symbol_info = {}

        # Source list driving the Add Tokens dropdown — refreshed from xlsx in load_data().
        # Initialized to defaults so create_widgets() can build the combobox before xlsx is read.
        self.available_sources = list(DEFAULT_SOURCES)

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
        
        # Add filter buttons — two rows for readability
        filter_frame = tk.Frame(button_frame, bg="#DCDAD5")
        filter_frame.pack(side=tk.LEFT, padx=20)

        # Row 1: signal-category quick-filter buttons
        row1_frame = tk.Frame(filter_frame, bg="#DCDAD5")
        row1_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 5))

        filter_label = tk.Label(row1_frame, text="Quick Filters:", bg="#DCDAD5", fg="black", font=("Arial", 11))
        filter_label.pack(side=tk.LEFT, padx=5)

        all_btn = tk.Button(row1_frame, text="All", command=self._show_all,
                           bg="#DCDAD5", width=6, cursor="hand2",
                           relief=tk.FLAT, borderwidth=0, highlightthickness=0, highlightbackground="gray")
        all_btn.pack(side=tk.LEFT, padx=2)
        ToolTip(all_btn, "Show all trading signals")

        buy_btn = tk.Button(row1_frame, text="Buy", command=lambda: self.filter_signals("buy"),
                           bg="#C8E6C9", width=6, cursor="hand2",
                           relief=tk.FLAT, borderwidth=0, highlightthickness=0, highlightbackground="gray")
        buy_btn.pack(side=tk.LEFT, padx=2)
        ToolTip(buy_btn, "Show only Buy signals")

        sell_btn = tk.Button(row1_frame, text="Sell", command=lambda: self.filter_signals("sell"),
                            bg="#FFCDD2", width=6, cursor="hand2",
                            relief=tk.FLAT, borderwidth=0, highlightthickness=0, highlightbackground="gray")
        sell_btn.pack(side=tk.LEFT, padx=2)
        ToolTip(sell_btn, "Show only Sell signals")

        self.cross_only_var = tk.BooleanVar(value=False)
        self.cross_btn = tk.Button(row1_frame, text="Cross", command=self.toggle_cross_filter,
                                   bg="#FFD580", width=6, cursor="hand2",
                                   relief=tk.FLAT, borderwidth=0, highlightthickness=0, highlightbackground="gray")
        self.cross_btn.pack(side=tk.LEFT, padx=2)
        ToolTip(self.cross_btn, "Show only signals with a recent K/D crossover (orange rows)")

        # Row 2: text/numeric filters
        row2_frame = tk.Frame(filter_frame, bg="#DCDAD5")
        row2_frame.pack(side=tk.TOP, fill=tk.X)

        # Token search
        token_search_frame = tk.Frame(row2_frame, bg="#DCDAD5")
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

        # Slope K filter
        slope_k_frame = tk.Frame(row2_frame, bg="#DCDAD5")
        slope_k_frame.pack(side=tk.LEFT, padx=10)
        slope_k_label = tk.Label(slope_k_frame, text="Slope K", bg="#DCDAD5", fg="black", font=("Arial", 11))
        slope_k_label.pack(side=tk.LEFT, padx=2)
        self.slope_k_var = tk.StringVar()
        self.slope_k_var.trace_add("write", lambda *args: self.apply_all_filters())
        slope_k_entry = tk.Entry(slope_k_frame, textvariable=self.slope_k_var, width=5, bg="white", fg="black")
        slope_k_entry.pack(side=tk.LEFT, padx=2)
        ToolTip(slope_k_entry, "Filter by slope K: positive > threshold, negative < threshold")

        # Slope D filter
        slope_d_frame = tk.Frame(row2_frame, bg="#DCDAD5")
        slope_d_frame.pack(side=tk.LEFT, padx=10)
        slope_d_label = tk.Label(slope_d_frame, text="Slope D", bg="#DCDAD5", fg="black", font=("Arial", 11))
        slope_d_label.pack(side=tk.LEFT, padx=2)
        self.slope_d_var = tk.StringVar()
        self.slope_d_var.trace_add("write", lambda *args: self.apply_all_filters())
        slope_d_entry = tk.Entry(slope_d_frame, textvariable=self.slope_d_var, width=5, bg="white", fg="black")
        slope_d_entry.pack(side=tk.LEFT, padx=2)
        ToolTip(slope_d_entry, "Filter by slope D: positive > threshold, negative < threshold")

        # ADX filter
        adx_frame = tk.Frame(row2_frame, bg="#DCDAD5")
        adx_frame.pack(side=tk.LEFT, padx=10)
        adx_label = tk.Label(adx_frame, text="ADX", bg="#DCDAD5", fg="black", font=("Arial", 11))
        adx_label.pack(side=tk.LEFT, padx=2)
        self.adx_var = tk.StringVar()
        self.adx_var.trace_add("write", lambda *args: self.apply_all_filters())
        adx_entry = tk.Entry(adx_frame, textvariable=self.adx_var, width=5, bg="white", fg="black")
        adx_entry.pack(side=tk.LEFT, padx=2)
        ToolTip(adx_entry, "Filter by ADX: positive > threshold, negative < threshold")

        # Trade Type checkboxes
        trade_type_frame = tk.Frame(row2_frame, bg="#DCDAD5")
        trade_type_frame.pack(side=tk.LEFT, padx=10)
        trade_type_label = tk.Label(trade_type_frame, text="Trades:", bg="#DCDAD5", fg="black", font=("Arial", 11))
        trade_type_label.pack(side=tk.LEFT, padx=(0,4))
        self.trade_buy_var = tk.BooleanVar(value=False)
        self.trade_sell_var = tk.BooleanVar(value=False)
        buy_cb = tk.Checkbutton(trade_type_frame, text="Buy", variable=self.trade_buy_var, bg="#DCDAD5", command=self.apply_all_filters)
        sell_cb = tk.Checkbutton(trade_type_frame, text="Sell", variable=self.trade_sell_var, bg="#DCDAD5", command=self.apply_all_filters)
        buy_cb.pack(side=tk.LEFT)
        sell_cb.pack(side=tk.LEFT)
        ToolTip(buy_cb, "Show only rows where Trade Type is Buy (or with Sell if both checked)")
        ToolTip(sell_cb, "Show only rows where Trade Type is Sell (or with Buy if both checked)")

        # Reset button
        reset_btn = tk.Button(row2_frame, text="🔄 Reset Filters", command=self.reset_filters, bg="#DCDAD5", cursor="hand2")
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
            tree.tag_configure('cross', background='#FFD580')  # Light orange for CROSS
            # Enable editing the notes column
            tree.bind("<Double-1>", self.on_double_click)
            TokenTooltip(
                tree,
                self.symbol_info,
                on_source_change=self._update_token_source,
                get_sources=lambda: self.available_sources,
            )

        # Build Add Tokens tab (after timeframe tabs)
        self._build_add_tokens_tab()

        # Add status bar
        self.status_var = tk.StringVar()
        status_bar = tk.Label(self.root, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor=tk.W, pady=3)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_var.set("Ready")

    def _build_add_tokens_tab(self):
        """Build the Add Tokens tab inside self.notebook (always last after timeframes).
        UI only — handlers are stubbed and wired in Phase 4."""
        frame = tk.Frame(self.notebook)
        self.notebook.add(frame, text="Add Tokens")
        self.tabs['add_tokens'] = frame

        container = tk.Frame(frame, padx=20, pady=15)
        container.pack(fill=tk.BOTH, expand=True)

        # --- URL field (optional)
        url_frame = tk.LabelFrame(container, text=" URL (optionnel) ",
                                  font=("Arial", 10, "bold"), padx=10, pady=8)
        url_frame.pack(fill=tk.X, pady=(0, 8))
        self.url_var = tk.StringVar()
        url_entry = tk.Entry(url_frame, textvariable=self.url_var, width=80)
        url_entry.pack(fill=tk.X)
        ToolTip(url_entry, "URL de la page d'origine — apparaît dans le tooltip des tokens. Vide = trait dans le tooltip.")

        # --- Mode selector (radio: symbol vs name)
        mode_frame = tk.LabelFrame(container, text=" Mode d'entrée ",
                                   font=("Arial", 10, "bold"), padx=10, pady=8)
        mode_frame.pack(fill=tk.X, pady=(0, 8))
        self.mode_var = tk.StringVar(value="symbol")
        tk.Radiobutton(mode_frame, text="Symboles (ex: AAPL, MSFT)",
                       variable=self.mode_var, value="symbol").pack(side=tk.LEFT, padx=10)
        tk.Radiobutton(mode_frame, text="Noms d'entreprises (ex: Apple Inc.)",
                       variable=self.mode_var, value="name").pack(side=tk.LEFT, padx=10)

        # --- Source dropdown (+ conditional list-name entry)
        source_frame = tk.LabelFrame(container, text=" Source ",
                                     font=("Arial", 10, "bold"), padx=10, pady=8)
        source_frame.pack(fill=tk.X, pady=(0, 8))

        src_row = tk.Frame(source_frame)
        src_row.pack(fill=tk.X)
        tk.Label(src_row, text="Choisir :").pack(side=tk.LEFT, padx=(0, 6))
        initial = self.available_sources[0] if self.available_sources else ""
        self.source_var = tk.StringVar(value=initial)
        self.source_combobox = ttk.Combobox(src_row, textvariable=self.source_var,
                                            values=self.available_sources,
                                            state="readonly", width=40)
        self.source_combobox.pack(side=tk.LEFT, padx=4)
        self.source_combobox.bind("<<ComboboxSelected>>", self._on_source_changed)

        # Conditional list-name field — only for the Investing.com template
        self.list_name_frame = tk.Frame(source_frame)
        self.list_name_var = tk.StringVar()
        tk.Label(self.list_name_frame, text="Nom de la liste (optionnel) :").pack(side=tk.LEFT, padx=(0, 6))
        list_name_entry = tk.Entry(self.list_name_frame, textvariable=self.list_name_var, width=35)
        list_name_entry.pack(side=tk.LEFT)
        ToolTip(list_name_entry,
                "Concaténé à 'Investing.com - '. Vide = stocke 'Investing.com' tout court.")
        self._on_source_changed()  # set initial visibility

        # --- Tokens text area
        tokens_frame = tk.LabelFrame(container, text=" Tokens (un par ligne) ",
                                     font=("Arial", 10, "bold"), padx=10, pady=8)
        tokens_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        tokens_inner = tk.Frame(tokens_frame)
        tokens_inner.pack(fill=tk.BOTH, expand=True)
        self.tokens_text = tk.Text(tokens_inner, height=8, font=("Courier", 10), wrap=tk.NONE)
        tokens_scroll = ttk.Scrollbar(tokens_inner, orient=tk.VERTICAL, command=self.tokens_text.yview)
        self.tokens_text.configure(yscrollcommand=tokens_scroll.set)
        tokens_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tokens_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # --- Action buttons
        btn_frame = tk.Frame(container)
        btn_frame.pack(fill=tk.X, pady=(0, 8))
        self.add_btn = tk.Button(btn_frame, text="➕ Add Tokens", command=self._on_add_tokens,
                                 bg="#1565C0", fg="white", font=("Arial", 12, "bold"),
                                 padx=20, pady=6, cursor="hand2", relief=tk.RAISED)
        self.add_btn.pack(side=tk.LEFT, padx=(0, 8))
        ToolTip(self.add_btn,
                "Lookup chaque token via yfinance puis ajoute / met à jour la feuille symbols. Bloqué pendant le traitement.")

        clear_btn = tk.Button(btn_frame, text="Clear", command=self._on_add_clear,
                              bg="#DCDAD5", padx=15, pady=6, cursor="hand2")
        clear_btn.pack(side=tk.LEFT)
        ToolTip(clear_btn, "Vider la zone de tokens et les logs.")

        # --- Status / Log area (read-only)
        log_frame = tk.LabelFrame(container, text=" Status / Log ",
                                  font=("Arial", 10, "bold"), padx=10, pady=8)
        log_frame.pack(fill=tk.BOTH, expand=True)
        log_inner = tk.Frame(log_frame)
        log_inner.pack(fill=tk.BOTH, expand=True)
        self.add_log = tk.Text(log_inner, height=6, font=("Courier", 9), wrap=tk.WORD,
                               state=tk.DISABLED, bg="#F5F5F5")
        log_scroll = ttk.Scrollbar(log_inner, orient=tk.VERTICAL, command=self.add_log.yview)
        self.add_log.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.add_log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def _on_source_changed(self, event=None):
        """Toggle the optional list-name field for the Investing.com template."""
        if self.source_var.get() == INVESTING_LIST_TEMPLATE:
            self.list_name_frame.pack(fill=tk.X, pady=(8, 0))
        else:
            self.list_name_frame.pack_forget()
            self.list_name_var.set("")

    def _on_add_clear(self):
        """Clear the tokens text area and the log widget."""
        self.tokens_text.delete("1.0", tk.END)
        self._log_clear()

    def _log_clear(self):
        self.add_log.config(state=tk.NORMAL)
        self.add_log.delete("1.0", tk.END)
        self.add_log.config(state=tk.DISABLED)

    def _log_append(self, msg):
        """Append a line to the log widget (must be called on the main thread)."""
        self.add_log.config(state=tk.NORMAL)
        self.add_log.insert(tk.END, msg + "\n")
        self.add_log.see(tk.END)
        self.add_log.config(state=tk.DISABLED)

    def _on_add_tokens(self):
        """Validate inputs, then dispatch lookup + persistence to a daemon thread."""
        raw_text = self.tokens_text.get("1.0", tk.END)
        tokens = parse_tokens(raw_text)
        if not tokens:
            messagebox.showwarning("Add Tokens", "Aucun token à ajouter — la zone est vide.")
            self.tokens_text.focus_set()
            return

        mode = self.mode_var.get()
        source = build_source(self.source_var.get(), self.list_name_var.get())
        url = self.url_var.get().strip()
        if not source:
            messagebox.showwarning("Add Tokens", "Sélectionne une source dans le menu déroulant.")
            return

        self.add_btn.config(state=tk.DISABLED)
        self._log_clear()
        self._log_append(
            f"Lookup {len(tokens)} entrée(s) — mode={mode!r}, source={source!r}"
        )

        threading.Thread(
            target=self._add_tokens_worker,
            args=(tokens, mode, source, url),
            daemon=True,
        ).start()

    def _add_tokens_worker(self, tokens, mode, source, url):
        """Background: resolve each entry via yfinance, then atomically merge into xlsx.
        UI updates are dispatched back to the main thread via root.after()."""
        success_rows = []
        failures = []
        total = len(tokens)
        for i, raw in enumerate(tokens, start=1):
            symbol = None
            company_name = None
            try:
                if mode == "symbol":
                    # Normalise EXCHANGE:SYMBOL (e.g. XTRA:MUV2 → MUV2.DE) so the
                    # value stored in the symbols sheet is what trading_signal_generator
                    # can fetch from yfinance downstream.
                    symbol = to_yf_symbol(raw)
                    company_name, _dbg = lookup_info_for_symbol(symbol)
                else:
                    symbol, company_name, _dbg = best_symbol_for_company(raw)
            except Exception as e:
                self.root.after(0, self._log_append,
                                f"[{i}/{total}] {raw!r} → erreur: {type(e).__name__}: {e}")
                failures.append(raw)
                time.sleep(0.25)
                continue

            if symbol and company_name:
                yf_url = f"https://finance.yahoo.com/quote/{symbol}/"
                success_rows.append({
                    "Symbols": symbol,
                    "Company Name": company_name,
                    "Yahoo Finance URL": yf_url,
                    "Source": source,
                    "Source URL": url,
                })
                self.root.after(0, self._log_append,
                                f"[{i}/{total}] {raw!r} → {symbol}  ({company_name})")
            else:
                failures.append(raw)
                self.root.after(0, self._log_append,
                                f"[{i}/{total}] {raw!r} → ÉCHEC (pas de résultat)")
            time.sleep(0.25)

        added = 0
        updated = 0
        persist_error = None
        if success_rows:
            try:
                added, updated = self._merge_into_symbols_sheet(success_rows)
            except Exception as e:
                persist_error = e

        self.root.after(0, self._on_add_complete, added, updated, failures, persist_error)

    def _merge_into_symbols_sheet(self, new_rows):
        """Atomic merge of new_rows into the symbols sheet of EXCEL_FILE.
        Reads ALL sheets, mutates ONLY the symbols sheet, writes back via temp+move.
        Every other sheet (timeframes, sources, anything else) is preserved verbatim.
        Returns (added, updated)."""
        with DATA_LOCK:
            existing = {}
            if os.path.exists(EXCEL_FILE):
                try:
                    xl = pd.ExcelFile(EXCEL_FILE)
                    for sn in xl.sheet_names:
                        existing[sn] = pd.read_excel(xl, sn)
                except Exception as e:
                    print(f"[merge] preserve read warning: {e}")

            symbols_df = existing.get(SYMBOLS_SHEET, pd.DataFrame(columns=SYMBOLS_COLS))
            merged, added, updated = merge_symbol_rows(symbols_df, new_rows)
            existing[SYMBOLS_SHEET] = merged

            temp_fd, temp_path = tempfile.mkstemp(suffix='.xlsx', prefix='tmp_addtokens_')
            os.close(temp_fd)
            try:
                with pd.ExcelWriter(temp_path, engine='openpyxl') as writer:
                    for sn, df in existing.items():
                        df.to_excel(writer, sheet_name=sn, index=False)
                shutil.move(temp_path, EXCEL_FILE)
            finally:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except OSError:
                        pass
            return added, updated

    def _on_add_complete(self, added, updated, failures, persist_error):
        """Main-thread callback: re-enable UI, refresh tooltip data, show summary."""
        self.add_btn.config(state=tk.NORMAL)

        if persist_error:
            msg = f"Erreur lors de l'écriture xlsx: {persist_error}"
            self._log_append(msg)
            messagebox.showerror("Add Tokens", msg)
            return

        try:
            self._reload_symbol_info()
        except Exception as e:
            print(f"[reload symbol_info] {e}")

        summary_lines = [f"{added} ajouté(s), {updated} mis à jour, {len(failures)} échec(s)."]
        if failures:
            preview = failures[:20]
            summary_lines.append("Échecs : " + ", ".join(preview))
            if len(failures) > 20:
                summary_lines.append(f"(+ {len(failures) - 20} autres)")

        self._log_append("--- Terminé ---")
        for line in summary_lines:
            self._log_append(line)

        if added or updated:
            self.tokens_text.delete("1.0", tk.END)
        messagebox.showinfo("Add Tokens", "\n".join(summary_lines))

    def _update_token_source(self, token, new_source):
        """Tooltip callback — user picked a new source from the dropdown.
        Updates symbol_info immediately so the next hover reflects the change,
        then persists in a background thread (file I/O can be slow if Excel
        is open in another app)."""
        token = (token or "").strip()
        new_source = (new_source or "").strip()
        if not token or token not in self.symbol_info:
            return
        self.symbol_info[token]["source"] = new_source
        self.status_var.set(f"Source mise à jour : {token} → {new_source}")
        threading.Thread(
            target=self._persist_token_source,
            args=(token, new_source),
            daemon=True,
        ).start()

    def _persist_token_source(self, token, new_source):
        """Background-thread: rewrite the row in the symbols sheet, preserving
        all other metadata columns by reading them from self.symbol_info first."""
        info = self.symbol_info.get(token, {}) or {}
        row = {
            "Symbols": token,
            "Company Name": info.get("company_name", "") or "",
            "Yahoo Finance URL": info.get("yf_url", "") or "",
            "Source": new_source,
            "Source URL": info.get("source_url", "") or "",
        }
        try:
            self._merge_into_symbols_sheet([row])
        except Exception as e:
            self.root.after(
                0,
                lambda err=e: messagebox.showerror(
                    "Update Source",
                    f"Erreur lors de la mise à jour de la source pour {token} : {err}",
                ),
            )

    def _reload_symbol_info(self):
        """Re-read the symbols sheet to refresh tooltip metadata without disturbing
        timeframe Treeviews or any active filter."""
        self.symbol_info.clear()
        if not os.path.exists(EXCEL_FILE):
            return
        try:
            sym_df = pd.read_excel(EXCEL_FILE, sheet_name=SYMBOLS_SHEET)
        except Exception:
            return
        for _, row in sym_df.iterrows():
            token = str(row.get("Symbols", "") or "").strip()
            if token:
                self.symbol_info[token] = {
                    "company_name": str(row.get("Company Name", "") or "").strip(),
                    "yf_url": str(row.get("Yahoo Finance URL", "") or "").strip(),
                    "source": str(row.get("Source", "") or "").strip(),
                    "source_url": str(row.get("Source URL", "") or "").strip(),
                }

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

            # Load symbol metadata for tooltips (incl. new Source URL column)
            self.symbol_info.clear()
            try:
                sym_df = pd.read_excel(EXCEL_FILE, sheet_name=SYMBOLS_SHEET)
                for _, row in sym_df.iterrows():
                    token = str(row.get("Symbols", "") or "").strip()
                    if token:
                        self.symbol_info[token] = {
                            "company_name": str(row.get("Company Name", "") or "").strip(),
                            "yf_url": str(row.get("Yahoo Finance URL", "") or "").strip(),
                            "source": str(row.get("Source", "") or "").strip(),
                            "source_url": str(row.get("Source URL", "") or "").strip(),
                        }
            except Exception:
                pass

            # Load (or create) the sources sheet driving the Add Tokens dropdown
            self._refresh_available_sources()

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
        """Display data in the treeview for a specific sheet with crossover highlighting."""
        tree = self.trees[sheet_key]
        other_timeframes = [tf for tf in TIMEFRAMES if tf != sheet_key]
        trend_cols = sorted([f'{tf}_trend' for tf in other_timeframes])
        data_columns = BASE_COLS_GUI + HIDDEN_DMI_COLS + trend_cols + [NOTES_COL_GUI] + ALL_NEW_ORDER_APPEND
        display_columns = [c for c in data_columns if c not in HIDDEN_DMI_COLS]

        df_from_data = self.data.get(sheet_key, pd.DataFrame(columns=data_columns)).copy()
        for col in data_columns:
            if col not in df_from_data.columns:
                df_from_data[col] = pd.NA
        df_filled = df_from_data.reindex(columns=data_columns, fill_value=pd.NA)
        df_display = df_filled[display_columns].copy().fillna("")
        if NOTES_COL_GUI in df_display.columns:
            df_display[NOTES_COL_GUI] = df_display[NOTES_COL_GUI].fillna("").astype(str)

        # Clear rows
        for item in tree.get_children():
            tree.delete(item)

        tree['columns'] = display_columns
        tree['show'] = 'headings'
        for col in display_columns:
            tree.heading(col, text=col.replace('_',' ').title())
            tree.column(col, width=COLUMN_WIDTHS.get(col, 100), anchor=tk.CENTER)

        for _, row in df_display.iterrows():
            row_vals = []
            for c in display_columns:
                if c == 'ADX':
                    raw_val = row[c]
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
                elif c in ['Entry Price','Target Exit Price','Exit Price','PNL','PNL %']:
                    v = row[c]
                    if v is None or v == "" or pd.isna(v):
                        row_vals.append("")
                    else:
                        row_vals.append(format_decimal(v))
                else:
                    row_vals.append("" if pd.isna(row[c]) else str(row[c]))

            sig = str(row.get('signal','')).lower()
            base_tag = sig if sig in ['buy+','buy','buy-','sell-','sell','sell+'] else None
            cross_raw = None
            if 'cross' in df_filled.columns:
                try:
                    cross_raw = df_filled.loc[row.name, 'cross']
                except Exception:
                    cross_raw = row.get('cross', '')
            cross_flag = False
            if isinstance(cross_raw, (bool, np.bool_)):
                cross_flag = bool(cross_raw)
            elif isinstance(cross_raw, (int, float)) and not pd.isna(cross_raw):
                cross_flag = int(cross_raw) == 1
            else:
                cross_flag = str(cross_raw).strip().lower() in ('1','true','yes','y')
            if cross_flag:
                tree.insert('', 'end', values=row_vals, tags=('cross',))
            else:
                if base_tag:
                    tree.insert('', 'end', values=row_vals, tags=(base_tag,))
                else:
                    tree.insert('', 'end', values=row_vals)

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
                                ordered = BASE_COLS_GUI + HIDDEN_DMI_COLS + trends + [NOTES_COL_GUI] + ALL_NEW_ORDER_APPEND
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
                            if sn == SYMBOLS_SHEET:
                                for col in ["Company Name", "Yahoo Finance URL", "Source", "Source URL"]:
                                    if col not in df_pres.columns:
                                        df_pres[col] = ""
                                # Reorder to canonical column order
                                df_pres = df_pres.reindex(columns=SYMBOLS_COLS)
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

    def _refresh_available_sources(self):
        """Read the `sources` sheet from xlsx; bootstrap it with DEFAULT_SOURCES if absent.
        Updates self.available_sources and refreshes the Add Tokens combobox values if built."""
        sources = None
        if os.path.exists(EXCEL_FILE):
            try:
                xl = pd.ExcelFile(EXCEL_FILE)
                if SOURCES_SHEET in xl.sheet_names:
                    src_df = pd.read_excel(xl, SOURCES_SHEET)
                    if not src_df.empty:
                        sources = [
                            str(s).strip()
                            for s in src_df.iloc[:, 0].dropna().tolist()
                            if str(s).strip()
                        ]
            except Exception as e:
                print(f"[sources] read warning: {e}")

        if not sources:
            sources = list(DEFAULT_SOURCES)
            if os.path.exists(EXCEL_FILE):
                try:
                    self._write_sources_sheet(sources)
                except Exception as e:
                    print(f"[sources] could not initialize sources sheet: {e}")

        self.available_sources = sources
        cb = getattr(self, 'source_combobox', None)
        if cb is not None:
            cb['values'] = sources

    def _write_sources_sheet(self, sources):
        """Persist a `sources` sheet to xlsx, preserving every other sheet verbatim.
        Used on first launch when the sheet does not yet exist."""
        with DATA_LOCK:
            existing = {}
            try:
                xl = pd.ExcelFile(EXCEL_FILE)
                for sn in xl.sheet_names:
                    existing[sn] = pd.read_excel(xl, sn)
            except Exception as e:
                print(f"[sources] preserve read warning: {e}")
            existing[SOURCES_SHEET] = pd.DataFrame({"Source Name": sources})
            temp_fd, temp_path = tempfile.mkstemp(suffix='.xlsx', prefix='tmp_sources_')
            os.close(temp_fd)
            try:
                with pd.ExcelWriter(temp_path, engine='openpyxl') as writer:
                    for sn, df in existing.items():
                        df.to_excel(writer, sheet_name=sn, index=False)
                shutil.move(temp_path, EXCEL_FILE)
            finally:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except OSError:
                        pass

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
        # Trade Type checkbox filters
        if hasattr(self, 'trade_buy_var') and hasattr(self, 'trade_sell_var') and 'Trade Type' in df_full.columns:
            buy_checked = self.trade_buy_var.get()
            sell_checked = self.trade_sell_var.get()
            if buy_checked and not sell_checked:
                df_full = df_full[df_full['Trade Type'].astype(str) == 'Buy']
            elif sell_checked and not buy_checked:
                df_full = df_full[df_full['Trade Type'].astype(str) == 'Sell']
            elif buy_checked and sell_checked:
                df_full = df_full[df_full['Trade Type'].astype(str).isin(['Buy','Sell'])]
        # Cross filter — show only rows where a recent K/D crossover was detected
        if self.cross_only_var.get() and 'cross' in df_full.columns:
            def _is_cross(v):
                if isinstance(v, (bool, np.bool_)):
                    return bool(v)
                if isinstance(v, (int, float)) and not pd.isna(v):
                    return int(v) == 1
                return str(v).strip().lower() in ('1', 'true', 'yes', 'y')
            df_full = df_full[df_full['cross'].apply(_is_cross)]
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
        if hasattr(self, 'trade_buy_var'):
            self.trade_buy_var.set(False)
        if hasattr(self, 'trade_sell_var'):
            self.trade_sell_var.set(False)
        self.cross_only_var.set(False)
        self.cross_btn.configure(bg="#FFD580", relief=tk.FLAT)
        self.apply_all_filters()

    def toggle_cross_filter(self):
        """Toggle cross-only filter on/off and update button appearance."""
        new_val = not self.cross_only_var.get()
        self.cross_only_var.set(new_val)
        if new_val:
            self.cross_btn.configure(bg="#FFA500", relief=tk.SUNKEN)
        else:
            self.cross_btn.configure(bg="#FFD580", relief=tk.FLAT)
        self.apply_all_filters()

    def _show_all(self):
        """Reset cross filter then show all signals."""
        self.cross_only_var.set(False)
        self.cross_btn.configure(bg="#FFD580", relief=tk.FLAT)
        self.filter_signals("all")
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
                        export_columns_ordered = BASE_COLS_GUI + HIDDEN_DMI_COLS + trend_cols_for_export + [NOTES_COL_GUI] + ALL_NEW_ORDER_APPEND

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