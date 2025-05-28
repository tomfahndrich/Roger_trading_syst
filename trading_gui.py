import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pandas as pd
from trading_signal_generator import main as generate_signals, TIMEFRAMES, EXCEL_FILE

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
    'notes': 200,
    'token': 80,
    'close price': 100,
    'CCI': 80,
    'stoch K': 80,
    'stoch D': 80,
    'slope K': 80,
    'slope D': 80
}

# Define standard columns for DataFrames to ensure consistency
STANDARD_COLUMNS = ['datetime', 'signal', 'token', 'close price', 'CCI', 'stoch K', 'stoch D', 'slope K', 'slope D', 'notes']

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
        
        # Initialize data dictionary with empty DataFrames structured with STANDARD_COLUMNS
        self.data = {}
        for sheet in TIMEFRAMES:
            df = pd.DataFrame(columns=STANDARD_COLUMNS)
            if 'notes' in df.columns:
                df['notes'] = df['notes'].astype(str)
            else: # Should not happen if STANDARD_COLUMNS includes 'notes'
                df['notes'] = pd.Series(dtype=str)
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
            
            # Configure tree columns - initially empty
            tree["columns"] = STANDARD_COLUMNS
            
            # Configure tags for Buy/Sell colors
            tree.tag_configure('buy', background='#c8e6c9')   # Light green
            tree.tag_configure('sell', background='#ffcdd2')  # Light red
            
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
                df = pd.DataFrame(columns=STANDARD_COLUMNS)
                df['notes'] = df['notes'].astype(str)
                self.data[sheet] = df

            if os.path.exists(EXCEL_FILE):
                self.status_var.set("Loading data from Excel...")
                excel_data_sheets = pd.read_excel(EXCEL_FILE, sheet_name=None)
                
                for sheet in TIMEFRAMES:
                    if sheet in excel_data_sheets:
                        loaded_df = excel_data_sheets[sheet].copy()
                        # Ensure all standard columns exist, add if missing
                        for col in STANDARD_COLUMNS:
                            if col not in loaded_df.columns:
                                loaded_df[col] = "" if col == 'notes' else pd.NA
                        
                        loaded_df['notes'] = loaded_df['notes'].fillna("").astype(str)
                        # Ensure all STANDARD_COLUMNS are present before assignment
                        self.data[sheet] = loaded_df.reindex(columns=STANDARD_COLUMNS, fill_value="") 
                        self.data[sheet]['notes'] = self.data[sheet]['notes'].fillna("").astype(str)
            else:
                messagebox.showwarning("File Not Found", f"Excel file not found at {EXCEL_FILE}. Displaying empty tables.")

            self.display_all_data() # Helper to refresh all tabs
            self.status_var.set("Data loaded successfully from Excel")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error loading data from Excel: {str(e)}")
            self.status_var.set(f"Error loading data: {str(e)}")
            # Fallback: ensure self.data has empty, structured DataFrames
            for sheet in TIMEFRAMES:
                df = pd.DataFrame(columns=STANDARD_COLUMNS)
                df['notes'] = df['notes'].astype(str)
                self.data[sheet] = df
            self.display_all_data()

    def display_all_data(self):
        """Helper function to refresh display for all sheets."""
        for sheet in TIMEFRAMES:
            self.display_data(sheet)

    def display_data(self, sheet):
        """Display data in the treeview for a specific sheet"""
        tree = self.trees[sheet]
        df_display = pd.DataFrame(columns=STANDARD_COLUMNS)
        if sheet in self.data and isinstance(self.data[sheet], pd.DataFrame):
            df_display = self.data[sheet].copy()
        
        for col in STANDARD_COLUMNS: # Ensure all standard columns exist in df_display
            if col not in df_display.columns:
                df_display[col] = "" if col == 'notes' else pd.NA
        df_display['notes'] = df_display['notes'].fillna("").astype(str)

        # Clear previous data
        for item in tree.get_children():
            tree.delete(item)
        
        # Configure columns from STANDARD_COLUMNS for consistency
        tree["columns"] = STANDARD_COLUMNS
        tree.column("#0", width=0, stretch=tk.NO)
        tree.heading("#0", text="")
        
        for col in STANDARD_COLUMNS:
            width = COLUMN_WIDTHS.get(col, 100)
            tree.column(col, width=width, anchor=tk.W if col == 'notes' else tk.CENTER) # Notes left-aligned
            tree.heading(col, text=col.capitalize())
        
        # Add data rows
        if not df_display.empty:
            for idx, row_s in df_display.iterrows(): # row_s is a Series
                values = []
                for col_name in STANDARD_COLUMNS:
                    val = row_s.get(col_name, "") # Get value or default to empty string
                    if pd.api.types.is_datetime64_any_dtype(val) or isinstance(val, pd.Timestamp):
                        values.append(val.strftime('%Y-%m-%d %H:%M:%S'))
                    elif pd.isna(val):
                        values.append("") # Display NA as empty string
                    else:
                        values.append(str(val)) # Ensure all values are strings for treeview
                
                tag = ""
                signal_val_series = row_s.get('signal', pd.Series(dtype=str)) # Get as series
                if not pd.isna(signal_val_series):
                    signal_val = str(signal_val_series).lower()
                    if signal_val == 'buy':
                        tag = "buy"
                    elif signal_val == 'sell':
                        tag = "sell"
                tree.insert("", tk.END, values=tuple(values), tags=(tag,))
    
    def save_data_to_excel(self): # Renamed for clarity, this is the main save mechanism
        """Save all data from self.data to the Excel file, preserving other sheets like 'symbols'."""
        try:
            existing_sheets_data = {}
            if os.path.exists(EXCEL_FILE):
                try:
                    # Read all existing sheets to preserve them
                    xls = pd.ExcelFile(EXCEL_FILE)
                    for sheet_name_in_file in xls.sheet_names:
                        if sheet_name_in_file not in TIMEFRAMES:
                            existing_sheets_data[sheet_name_in_file] = pd.read_excel(xls, sheet_name=sheet_name_in_file)
                except Exception as e:
                    # Handle case where Excel file might be corrupted or unreadable
                    print(f"Warning: Could not read existing sheets from {EXCEL_FILE} for preservation: {str(e)}")
                    # Continue, will effectively overwrite if writer proceeds.

            with pd.ExcelWriter(EXCEL_FILE, engine='openpyxl') as writer:
                # 1. Write application-managed sheets (from self.data)
                for sheet_name_app in TIMEFRAMES: # Iterate using a different variable name
                    df_to_save = self.data.get(sheet_name_app)
                    
                    if df_to_save is None or not isinstance(df_to_save, pd.DataFrame):
                        df_to_save = pd.DataFrame(columns=STANDARD_COLUMNS)
                    else:
                        df_to_save = df_to_save.copy()

                    # Ensure all standard columns exist.
                    for col in STANDARD_COLUMNS:
                        if col not in df_to_save.columns:
                            if col == 'notes':
                                df_to_save[col] = "" 
                            else:
                                df_to_save[col] = pd.NA
                    
                    df_to_save['notes'] = df_to_save['notes'].fillna("").astype(str)
                    
                    df_final = df_to_save.reindex(columns=STANDARD_COLUMNS)
                    
                    for col in df_final.columns:
                        if col != 'notes':
                            df_final[col] = df_final[col].fillna("")
                        elif col == 'notes': 
                            df_final[col] = df_final[col].fillna("").astype(str)
                            
                    df_final.to_excel(writer, sheet_name=sheet_name_app, index=False)

                # 2. Write back other existing sheets (e.g., "symbols")
                for sheet_name_existing, df_existing in existing_sheets_data.items():
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
            column_id = tree.identify_column(event.x)
            item_id = tree.identify_row(event.y)

            if not item_id or not column_id:
                return # Click outside of a cell

            column_idx = int(column_id.replace('#', '')) -1 # Treeview columns are 1-indexed

            # Ensure we are clicking on the 'notes' column
            if column_idx < 0 or column_idx >= len(STANDARD_COLUMNS) or STANDARD_COLUMNS[column_idx] != 'notes':
                return
        except Exception: # Catch any error during identification (e.g. if click is not on a cell)
            return

        current_values = tree.item(item_id, "values")
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
            # We need a reliable way to find the row in the DataFrame.
            # Using the tree item's current values for datetime, token, signal as a key.
            # This assumes these columns are present and their order in STANDARD_COLUMNS.
            
            try:
                dt_idx = STANDARD_COLUMNS.index('datetime')
                tk_idx = STANDARD_COLUMNS.index('token')
                sg_idx = STANDARD_COLUMNS.index('signal')
            except ValueError:
                messagebox.showerror("Error", "Key columns (datetime, token, signal) not found for saving note.")
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
                # Update the 'notes' for the first matched row
                df_sheet.loc[matching_indices[0], 'notes'] = new_note_value
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
            df_to_display = df_full[df_full['signal'].astype(str).str.lower() == signal_type.lower()]
        
        # Create a temporary display DataFrame to pass to display_data
        # This avoids modifying self.data[sheet] directly for filtering purposes
        current_data_for_sheet = self.data[sheet] # Backup
        self.data[sheet] = df_to_display # Temporarily set for display
        self.display_data(sheet) # This will use the filtered df_to_display
        self.data[sheet] = current_data_for_sheet # Restore original

        self.status_var.set(f"Displaying {signal_type.capitalize()} signals for {sheet.capitalize()}")

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
                        
                        # Ensure all standard columns exist and notes are properly formatted
                        for col in STANDARD_COLUMNS:
                            if col not in df_to_export.columns:
                                df_to_export[col] = "" if col == 'notes' else pd.NA
                        
                        df_to_export['notes'] = df_to_export['notes'].fillna("").astype(str)

                        final_export_df = df_to_export.reindex(columns=STANDARD_COLUMNS, fill_value="")
                        final_export_df['notes'] = final_export_df['notes'].fillna("").astype(str)

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
