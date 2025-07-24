import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pandas as pd
from trading_signal_generator import main as generate_signals, TIMEFRAMES, EXCEL_FILE

# BASE_COLS from trading_signal_generator.py: ['datetime', 'signal', 'token', 'close price', 'CCI', 'stoch K', 'stoch D', 'slope K', 'slope D', 'ADX']
BASE_COLS_GUI = ['datetime', 'signal', 'token', 'close price', 'CCI', 'stoch K', 'stoch D', 'slope K', 'slope D', 'ADX']
# Hidden DMI columns for internal use (not displayed)
HIDDEN_DMI_COLS = ['+DI', '-DI']
NOTES_COL_GUI = 'notes'

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
            current_sheet_columns = BASE_COLS_GUI + HIDDEN_DMI_COLS + trend_cols_for_this_sheet + [NOTES_COL_GUI]
            
            df = pd.DataFrame(columns=current_sheet_columns)
            if NOTES_COL_GUI in df.columns:
                df[NOTES_COL_GUI] = df[NOTES_COL_GUI].astype(str)
            else: # Should not happen if current_sheet_columns includes NOTES_COL_GUI
                df[NOTES_COL_GUI] = pd.Series(dtype=str)
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
        self.token_var.trace_add("write", lambda name, index, mode, sv=self.token_var: self.filter_by_token(sv.get()))
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
        self.slope_k_var.trace_add("write", lambda n, i, m, sv=self.slope_k_var: self.filter_by_slope_k(sv.get()))
        slope_k_entry = tk.Entry(slope_k_frame, textvariable=self.slope_k_var, width=5, bg="white", fg="black")
        slope_k_entry.pack(side=tk.LEFT, padx=2)
        ToolTip(slope_k_entry, "Filter by slope K: positive > threshold, negative < threshold")
        
        # Add slope D filter
        slope_d_frame = tk.Frame(filter_frame, bg="#DCDAD5")
        slope_d_frame.pack(side=tk.LEFT, padx=10)
        slope_d_label = tk.Label(slope_d_frame, text="Slope D", bg="#DCDAD5", fg="black", font=("Arial", 11))
        slope_d_label.pack(side=tk.LEFT, padx=2)
        self.slope_d_var = tk.StringVar()
        self.slope_d_var.trace_add("write", lambda n, i, m, sv=self.slope_d_var: self.filter_by_slope_d(sv.get()))
        slope_d_entry = tk.Entry(slope_d_frame, textvariable=self.slope_d_var, width=5, bg="white", fg="black")
        slope_d_entry.pack(side=tk.LEFT, padx=2)
        ToolTip(slope_d_entry, "Filter by slope D: positive > threshold, negative < threshold")
        
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
                current_sheet_columns = BASE_COLS_GUI + HIDDEN_DMI_COLS + trend_cols_for_this_sheet + [NOTES_COL_GUI]
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
                        expected_cols = BASE_COLS_GUI + HIDDEN_DMI_COLS + trend_cols_for_this_sheet + [NOTES_COL_GUI]
                        
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
                current_sheet_columns = BASE_COLS_GUI + trend_cols_for_this_sheet + [NOTES_COL_GUI]
                df = pd.DataFrame(columns=current_sheet_columns)
                df[NOTES_COL_GUI] = df[NOTES_COL_GUI].astype(str)
                self.data[sheet] = df
            self.display_all_data()

    def display_all_data(self):
        """Helper function to refresh display for all sheets."""
        for sheet in TIMEFRAMES:
            self.display_data(sheet) # Pass the sheet name (key)

    def display_data(self, sheet_key):
        """Display data in the treeview for a specific sheet"""
        tree = self.trees[sheet_key]
        
        # Determine all data columns including hidden DMI columns for this specific sheet
        other_timeframes = [tf for tf in TIMEFRAMES if tf != sheet_key]
        trend_cols_for_this_sheet = sorted([f'{tf}_trend' for tf in other_timeframes])
        data_columns = BASE_COLS_GUI + HIDDEN_DMI_COLS + trend_cols_for_this_sheet + [NOTES_COL_GUI]
        # Determine display columns (exclude hidden DMI cols)
        display_columns = [c for c in data_columns if c not in HIDDEN_DMI_COLS]

        df_display = pd.DataFrame(columns=display_columns)
        if sheet_key in self.data and isinstance(self.data[sheet_key], pd.DataFrame):
            df_from_data = self.data[sheet_key].copy()
            for col in data_columns:
                if col not in df_from_data.columns:
                    df_from_data[col] = pd.NA
            df_filled = df_from_data.reindex(columns=data_columns, fill_value=pd.NA)
            # Prepare display DataFrame
            df_display = df_filled[display_columns].fillna("")
        
        if NOTES_COL_GUI in df_display.columns:
            df_display[NOTES_COL_GUI] = df_display[NOTES_COL_GUI].fillna("").astype(str)
        else:
            df_display[NOTES_COL_GUI] = ""          

        # Clear previous data
        for item in tree.get_children():
            tree.delete(item)
        
        # Configure tree columns dynamically
        tree["columns"] = display_columns
        tree["show"] = "headings"  # Show only headings, not the default first column

        for col in display_columns:
            tree.heading(col, text=col.replace('_', ' ').title())
            tree.column(col, width=COLUMN_WIDTHS.get(col, 100), anchor=tk.CENTER)
         
        # Insert data with ADX formatting
        for index, row in df_display.iterrows():
            values_to_insert = []
            for col in display_columns:
                if col == 'ADX':
                    # Ensure '+' sign for positive ADX values if missing
                    raw_val = row['ADX']
                    if pd.isna(raw_val) or raw_val == "":
                        formatted = ""
                    else:
                        s = str(raw_val)
                        if s.startswith('+') or s.startswith('-'):
                            formatted = s
                        else:
                            try:
                                num = float(s)
                                formatted = f"{ '+' if num>=0 else '-' }{abs(num):.1f}"
                            except Exception:
                                formatted = s
                    values_to_insert.append(formatted)
                else:
                    values_to_insert.append(str(row[col]) if pd.notna(row[col]) else "")
             
            # Apply tags for row coloring based on signal
            sig = str(row['signal']).lower()
            tags = ()
            if sig == 'buy+':
                tags = ('buy+',)
            elif sig == 'buy':
                tags = ('buy',)
            elif sig == 'sell':
                tags = ('sell',)
            elif sig == 'sell+':
                tags = ('sell+',)
            
            tree.insert("", "end", values=values_to_insert, tags=tags)

        # Update status bar or other UI elements if needed
        self.status_var.set(f"Displaying data for {sheet_key.capitalize()}")

    def save_data_to_excel(self): # Renamed for clarity, this is the main save mechanism
        """Save all data from self.data to the Excel file, preserving other sheets like 'symbols'."""
        try:
            existing_sheets_data = {}
            if os.path.exists(EXCEL_FILE):
                # ...existing code...
                try:
                    # Load all sheets to preserve those not managed by self.data
                    existing_excel = pd.ExcelFile(EXCEL_FILE)
                    for sheet_name_existing in existing_excel.sheet_names:
                        if sheet_name_existing not in self.data: # Only load if not in current app data
                             existing_sheets_data[sheet_name_existing] = pd.read_excel(existing_excel, sheet_name_existing)
                except Exception as e_read:
                    print(f"Warning: Could not read existing sheets from {EXCEL_FILE} for preservation: {e_read}")
                    # Decide if you want to proceed without preserving or stop. Here, we proceed.

            with pd.ExcelWriter(EXCEL_FILE, engine='openpyxl') as writer:
                # Save data from the application (self.data)
                for sheet_name, df_app in self.data.items():
                    if df_app is not None and isinstance(df_app, pd.DataFrame):
                        df_to_save = df_app.copy()
                        
                        # Define column order for saving: BASE_COLS_GUI + trends + NOTES_COL_GUI
                        # Assuming TIMEFRAMES, BASE_COLS_GUI, NOTES_COL_GUI are accessible class/global constants
                        other_timeframes_save = [tf for tf in TIMEFRAMES if tf != sheet_name] 
                        trend_cols_for_save = sorted([f'{tf}_trend' for tf in other_timeframes_save])
                        save_columns_ordered = BASE_COLS_GUI + trend_cols_for_save + [NOTES_COL_GUI]

                        # Ensure all necessary columns exist in df_to_save, fill with "" if not
                        for col in save_columns_ordered:
                            if col not in df_to_save.columns:
                                df_to_save[col] = ""
                        
                        if NOTES_COL_GUI in df_to_save.columns:
                            df_to_save[NOTES_COL_GUI] = df_to_save[NOTES_COL_GUI].fillna("").astype(str)
                        else: # Should be created by the loop above
                            df_to_save[NOTES_COL_GUI] = ""

                        # Reindex to the desired order for saving
                        final_save_df = df_to_save.reindex(columns=save_columns_ordered, fill_value="")
                        
                        final_save_df.to_excel(writer, sheet_name=sheet_name, index=False)

                # Preserve other sheets from the original Excel file
                for sheet_name_existing, df_existing in existing_sheets_data.items():
                    # This condition was: if sheet_name_existing not in self.data:
                    # It's already handled when populating existing_sheets_data.
                    # Just write all collected existing sheets.
                    df_existing.to_excel(writer, sheet_name=sheet_name_existing, index=False)
            
            self.status_var.set("Data saved to Excel, non-managed sheets preserved.")
        except Exception as e:
            print(f"Error saving data to Excel: {str(e)}")
            messagebox.showerror("Save Error", f"Error saving data to Excel: {str(e)}")
            self.status_var.set(f"Warning: Could not save data to Excel: {str(e)}")

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
        # Identify the widget, tab, tree, item, and column
        try:
            # Determine active sheet and tree
            tab_id = self.notebook.select()
            if not tab_id:
                return # No tab selected
            sheet = self.notebook.tab(tab_id, "text").lower()
            if sheet not in self.trees:
                return # Sheet not found
            tree = self.trees[sheet]

            # Identify column and item
            column_id = tree.identify_column(event.x) # e.g., '#3'
            item_id = tree.identify_row(event.y)

            if not item_id or not column_id:
                return # Click outside of a cell

            column_idx = int(column_id.replace('#', '')) -1 # Treeview columns are 1-indexed
            
            # Get the actual column names from the treeview configuration
            actual_tree_columns = tree["columns"] # This is current_sheet_columns from display_data

            # Ensure we are clicking on the 'notes' column
            # MODIFIED: Check against actual_tree_columns and NOTES_COL_GUI
            if column_idx < 0 or column_idx >= len(actual_tree_columns) or actual_tree_columns[column_idx] != NOTES_COL_GUI:
                return
        except Exception: # Catch any error during identification (e.g. if click is not on a cell)
            return

        current_values = tree.item(item_id, "values")
        # The column_idx now correctly refers to the position of NOTES_COL_GUI in actual_tree_columns
        current_note = current_values[column_idx] if column_idx < len(current_values) else ""
        
        entry = tk.Entry(tree, relief=tk.SOLID) # Use a solid relief for visibility
        entry.insert(0, str(current_note)) # Ensure current note is string
        
        def save_edit_action(event_obj=None):
            new_note_value = entry.get()
            
            # Update treeview
            updated_values = list(current_values) # Make a mutable copy
            if column_idx < len(updated_values):
                 updated_values[column_idx] = new_note_value
            tree.item(item_id, values=updated_values)
            
            # Update DataFrame (self.data)
            try:
                # Get indices of key columns from the actual tree column list
                # This assumes 'datetime', 'token', 'signal' are always present in tree display
                dt_idx = actual_tree_columns.index('datetime')
                tk_idx = actual_tree_columns.index('token')
                sg_idx = actual_tree_columns.index('signal')
            except ValueError: # If any key column is not in actual_tree_columns
                messagebox.showerror("Error", "Key columns (datetime, token, signal) not found in tree display for saving note.")
                entry.destroy()
                return

            key_datetime_str = updated_values[dt_idx]
            key_token = updated_values[tk_idx]
            key_signal = updated_values[sg_idx]

            df_sheet = self.data[sheet]
            
            # Convert DataFrame datetime to string for comparison if necessary
            # This needs to be robust based on how datetimes are stored and displayed
            if pd.api.types.is_datetime64_any_dtype(df_sheet['datetime']):
                # Attempt to match various possible string formats or convert tree string to datetime
                # For simplicity, assume tree string format is 'YYYY-MM-DD HH:MM:S'
                try:
                    # Convert tree string to datetime object to match DataFrame if it contains datetime objects
                    key_dt_obj = pd.to_datetime(key_datetime_str)
                    mask = (df_sheet['datetime'] == key_dt_obj) & \
                           (df_sheet['token'].astype(str) == str(key_token)) & \
                           (df_sheet['signal'].astype(str) == str(key_signal))
                except ValueError: # If key_datetime_str is not a valid datetime string for pd.to_datetime
                     # Fallback to string comparison if DataFrame datetime is also string or if conversion fails
                    mask = (df_sheet['datetime'].astype(str) == str(key_datetime_str)) & \
                           (df_sheet['token'].astype(str) == str(key_token)) & \
                           (df_sheet['signal'].astype(str) == str(key_signal))
            else: # If df_sheet['datetime'] is already string
                mask = (df_sheet['datetime'].astype(str) == str(key_datetime_str)) & \
                       (df_sheet['token'].astype(str) == str(key_token)) & \
                       (df_sheet['signal'].astype(str) == str(key_signal))

            matching_indices = df_sheet.index[mask].tolist()
            
            if matching_indices:
                # Update the 'notes' for the first matched row using NOTES_COL_GUI
                df_sheet.loc[matching_indices[0], NOTES_COL_GUI] = new_note_value
                self.save_data_to_excel() # Persist change to Excel immediately
            else:
                print(f"Warning: Could not find matching row in DataFrame for sheet {sheet} to save note.")
                print(f"Key: dt='{key_datetime_str}', token='{key_token}', signal='{key_signal}'")
                messagebox.showwarning("Save Note", "Could not find the exact row to save the note. It might have been changed or removed.")
            
            entry.destroy()

        entry.bind("<Return>", save_edit_action)
        entry.bind("<FocusOut>", save_edit_action)
        entry.bind("<Escape>", lambda e: entry.destroy())
        
        x, y, width, height = tree.bbox(item_id, column_id)
        # Avoid negative dimension errors
        if width <= 0 or height <= 0:
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
                        export_columns_ordered = BASE_COLS_GUI + trend_cols_for_export + [NOTES_COL_GUI]

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