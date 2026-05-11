# Roger Trading System — CLAUDE.md

> Comprehensive project guide for AI-assisted development. Read this at session start before touching any file.

---

## Quick Context

**What it is:** A Python desktop app that fetches OHLCV data from Yahoo Finance, computes multi-timeframe technical signals, and presents them in a Tkinter GUI with inline trade-tracking backed by a single Excel file.

**Who runs it:** Personal/small-team trading assistant. No server, no DB, no external API — everything lives in `trading_synthesis.xlsx`.

**Version:** 1.2 (hardcoded in About dialog, `trading_gui.py:1085`)

---

## File Map

```
Roger_trading_syst/
├── trading_signal_generator.py   # Core: yfinance fetch + indicator computation + signal logic + Excel write
├── trading_gui.py                # Tkinter GUI: display, filters, inline editing, save-to-Excel
├── roger_trading_launcher.py     # CLI entry point: --gui (default) or --cli flags
├── launch_roger_trading.bat      # Windows: pulls from remote Roger branch, then runs trading_gui.py
├── trading_synthesis.xlsx        # Runtime data file (gitignored): signals + notes + trades + symbols list
├── requirements.txt              # Python deps
├── README.md                     # User-facing docs
└── Roger_trading_yfinance_symbol/
    ├── __init__.py               # Makes the dir a Python package (importable from trading_gui.py)
    ├── symbols_finder.py         # Two-way lookup (name↔symbol). Both CLI and importable functions.
    ├── extract_symbols_from_txt.py  # CLI: TradingView watchlist .txt → symbols.xlsx
    ├── symbols_to_extract.txt    # Sample TradingView watchlist export (hundreds of symbols)
    ├── symbols.xlsx              # Output of extract_symbols_from_txt.py
    ├── names.xlsx                # Input company names for symbols_finder.py
    ├── names_with_symbols.xlsx   # Output of symbols_finder.py
    └── tests/
        ├── test_symbols_finder.py   # Pytest suite for symbols_finder (lookup + argparse + main routing)
        └── test_add_tokens_tab.py   # Pytest suite for Add Tokens helpers + xlsx merge integration
```

---

## Architecture

### Data Flow

```
trading_synthesis.xlsx["symbols"] sheet
        ↓  (read by generate_signals)
yfinance.Ticker.history()  (monthly/weekly/daily/4h)
        ↓
Indicator computation (Stoch, CCI, DMI/ADX, slope)
        ↓
Signal classification (Buy+/Buy/Buy-/Sell-/Sell/Sell+)
        ↓
Inter-timeframe trend enrichment (K>D → "up"/"down" per other TF)
        ↓
trading_synthesis.xlsx (one sheet per timeframe, merge preserving notes/trades)
        ↓
trading_gui.py reads Excel → displays in Treeview tabs → user edits inline
        ↓  (on edit or close)
trading_synthesis.xlsx (save via temp file + shutil.move for atomicity)
```

### Module Responsibilities

| File | Responsibility |
|------|----------------|
| `trading_signal_generator.py` | Fetch, compute, classify, persist signals |
| `trading_gui.py` | Display, filter, edit, save; hosts the Add Tokens tab |
| `roger_trading_launcher.py` | Entry-point routing only |
| `Roger_trading_yfinance_symbol/symbols_finder.py` | Symbol discovery — used as a CLI **and** imported by `trading_gui.py` (`best_symbol_for_company`, `lookup_info_for_symbol`) for the Add Tokens flow |
| `Roger_trading_yfinance_symbol/extract_symbols_from_txt.py` | Standalone CLI for TradingView watchlist parsing |

---

## Signal Logic (trading_signal_generator.py)

### Timeframes

| Key | Interval | Period |
|-----|----------|--------|
| `monthly` | `1mo` | `13y` |
| `weekly` | `1wk` | `3y` |
| `daily` | `1d` | `1y` |
| `4h` | `4h` | `90d` |

### Indicator Parameters

| Indicator | Parameter | Value |
|-----------|-----------|-------|
| Stochastic %K | window (lookback) | 55 |
| Stochastic %K | k_smooth | 55 |
| Stochastic %D | d_smooth | 36 |
| CCI | period | 20 |
| DMI/ADX | period | 14 |
| Slope | lookback periods | 10 (linear regression) |
| SLOPE_THRESHOLD | min significant magnitude | 0.4 |
| ADX_THRESHOLD | min trend strength | 20 |
| LOOKBACK_CROSSOVER | K/D cross detection window | 5 bars |

### Signal Classification

```
K > D  AND  CCI < -100  →  Buy  family
  + slope_K > 0.4 AND slope_D > 0.4          →  Buy+   (strong aligned)
  + slope_K * slope_D < 0                     →  Buy-   (divergent slopes, grey)
  (otherwise)                                 →  Buy    (standard)

K < D  AND  CCI > 100   →  Sell family
  + slope_K < -0.4 AND slope_D < -0.4        →  Sell+  (strong aligned)
  + slope_K * slope_D < 0                     →  Sell-  (divergent slopes, grey)
  (otherwise)                                 →  Sell   (standard)

Anything else → Neutral → NOT stored (skipped entirely)
```

### Cross Detection (`recent_stoch_crossover`)

Examines the `LOOKBACK_CROSSOVER` bars immediately **before** the last bar (not including it). Returns `True` if K−D changes sign in that window. Direction (bull/bear) is ignored. Cross is stored as a separate boolean `cross` column, displayed in GUI as orange (`#FFD580`). It does NOT change the signal label.

### Monthly Special Rule

For monthly timeframe: `Close` is replaced by `Open` in the working copy (`df_for_calc`) before all indicator computations. The stored "close price" is also the Open value. This avoids using a partial-month Close. **This is a deliberate design decision — do not revert it.**

### Staleness Correction (daily/weekly only)

If the last historical bar is older than the threshold, a synthetic bar is appended in-memory using the most recent intraday data (priority: 5m → 15m → 1h). The synthetic bar is never persisted to the Excel history; it only affects the current signal computation run.

| Timeframe | Stale threshold |
|-----------|-----------------|
| daily | > 24 hours |
| weekly | > 5 days |

### Price Precision Rule (global)

Applied immediately on fetch, after synthetic bar, before signal storage, before Excel write:
- `price < 10` → 4 decimal places
- `price >= 10` → 2 decimal places

Function: `_normalize_price_value()`, applied via `normalize_price_columns()`.

### Excel Merge Strategy

On every `generate_signals()` run, new signal data is merged with old data:
- **Preserve**: `notes`, `Trade Type`, `Entry Price`, `Target Exit Price`, `Exit Price`, `PNL`, `PNL %` (user-entered data never overwritten)
- **Deduplicate**: on `(datetime, token, signal)` triple, keep first
- **Retain historical signals**: rows in old data not in new data are kept (appended)

---

## GUI Architecture (trading_gui.py)

### Class: `TradingApp`

| Method | Purpose |
|--------|---------|
| `__init__` | Init data dict, build menu, build widgets, load data |
| `create_menu` | File/View/Help menubar |
| `create_widgets` | Header, button bar, filter row, notebook tabs, status bar |
| `load_data` | Read Excel → populate `self.data[sheet]` → display |
| `display_data(sheet_key)` | Refresh Treeview for one sheet |
| `display_all_data` | Call `display_data` for all sheets |
| `save_data_to_excel` | Write `self.data` → temp file → atomic move to `EXCEL_FILE` |
| `update_data` | save → generate_signals() → load_data (runs on main thread, blocks UI) |
| `on_double_click` | Inline editing for notes, trade type, prices |
| `commit_update` | Validate + write edit to `self.data[sheet]` + save + refresh |
| `apply_all_filters` | Combined filter: token + slope K + slope D + ADX + trade type |
| `reset_filters` | Clear all filter inputs → apply_all_filters |
| `export_to_excel` | File dialog → save all sheets to chosen path |
| `on_closing` | save_data_to_excel → destroy |
| `_build_add_tokens_tab` | Build the 5th notebook tab (URL / mode / source / tokens / log) |
| `_on_add_tokens` | Validate inputs, disable button, spawn daemon thread |
| `_add_tokens_worker` | Background: per-token yfinance lookup with rate-limit; UI updates via `root.after()` |
| `_merge_into_symbols_sheet` | Atomic xlsx merge: mutates ONLY symbols sheet, preserves all others |
| `_on_add_complete` | Main-thread callback: re-enable UI, refresh tooltip metadata, summary |
| `_reload_symbol_info` | Re-read only the symbols sheet (refresh tooltip without disturbing Treeviews) |
| `_refresh_available_sources` | Read `sources` sheet; bootstrap with `DEFAULT_SOURCES` if absent; filter out sentinel; refresh combobox with sentinel appended |
| `_write_sources_sheet` | First-launch write of the sources sheet, preserving every other sheet |
| `_register_new_source` | Idempotent: append a source to `sources` sheet + refresh combobox. No-op for empty/sentinel/existing names. |
| `_update_token_source` | Tooltip Source-dropdown callback: update in-memory + spawn persist thread |
| `_persist_token_source` | Background-thread: rewrite the row in symbols sheet (Source only, all other metadata preserved from cached `symbol_info`); auto-registers `Investing.com - X` composites after success |

### Column Layout (per tab)

```
Displayed: datetime | signal | token | close price | CCI | stoch K | stoch D | slope K | slope D | ADX | [tf_trend cols...] | notes | Trade Type | Entry Price | Target Exit Price | Exit Price | PNL | PNL %

Hidden (internal, in self.data but not shown): +DI | -DI | cross
```

### Notebook Tabs

| Tab | Source | Purpose |
|-----|--------|---------|
| `Monthly` / `Weekly` / `Daily` / `4h` | `self.data[tf]` (mirrors timeframe sheets) | Display + filter + inline edit signals |
| `Add Tokens` | Form widgets (no DataFrame) | Append/update rows in the `symbols` sheet via yfinance lookup |

### Color Tags (Treeview)

| Tag | Color | Signal |
|-----|-------|--------|
| `buy+` | `#388e3c` (dark green) | Buy+ |
| `buy` | `#e8f5e9` (light green) | Buy |
| `buy-` | `#d3d3d3` (gray) | Buy- |
| `sell-` | `#d3d3d3` (gray) | Sell- |
| `sell` | `#ffebee` (light red) | Sell |
| `sell+` | `#e57373` (red) | Sell+ |
| `cross` | `#FFD580` (orange) | any signal with cross=True (overrides signal color) |

### Inline Editing

Double-click on editable columns: `notes`, `Trade Type`, `Entry Price`, `Target Exit Price`, `Exit Price`.
- `Trade Type`: dropdown OptionMenu (Buy/Sell only)
- `Entry Price`: auto-populated from `close price` when Trade Type is set
- `PNL` / `PNL %`: auto-computed from `Entry Price`, `Exit Price`, `Trade Type` — never manually entered

### Filter System

All filters apply simultaneously via `apply_all_filters()`. Filters operate on the current tab only. They do NOT modify `self.data` — they temporarily swap data for display then restore.

| Filter | Input | Logic |
|--------|-------|-------|
| Token | StringVar (partial match) | `str.lower().contains(tok)` |
| Slope K | StringVar (numeric) | `> thr` if thr≥0, `< thr` if thr<0 |
| Slope D | StringVar (numeric) | `> thr` if thr≥0, `< thr` if thr<0 |
| ADX | StringVar (numeric) | converts stored `+/-XX.X` string to float |
| Trade Type | BooleanVar × 2 | Buy/Sell checkboxes |
| Signal (buttons) | All/Buy/Sell | Buy → [buy, buy+]; Sell → [sell, sell+] |

> **Note:** `filter_by_slope()` at line 993 is a legacy combined method superseded by `apply_all_filters`. It is no longer called from the UI but still exists.

---

## Add Tokens Flow

### `symbols` sheet schema (post-migration)

| Symbols | Company Name | Yahoo Finance URL | Source | Source URL | Watchlist URL | Watchlist Name |
|---|---|---|---|---|---|---|

New columns are auto-created on first write by `_merge_into_symbols_sheet` (the function is column-agnostic — it reindexes against `SYMBOLS_COLS`). Legacy rows are left intact and gain empty values for new columns. **NaN cells from pandas missing values are normalized to `""` via the module-level `_safe_str()` helper** when loading into `self.symbol_info` — without this, the tooltip showed `"nan"` for missing optional fields.

### `sources` sheet (5th sheet of `trading_synthesis.xlsx`)

Single-column sheet (`Source Name`) driving the Add Tokens dropdown and the tooltip Source menu. Bootstrapped on first launch from `DEFAULT_SOURCES`. **Grows organically with usage**: every new source picked via "+ Nouvelle source..." or every new `Investing.com - X` composite is appended via `_register_new_source` (idempotent). Editable directly in Excel.

### Pure helpers (module-level, importable for tests)

| Function | Purpose |
|---|---|
| `parse_tokens(text)` | Multi-line text → deduplicated, stripped list of tokens (case-insensitive dedup, first occurrence wins) |
| `build_source(template, list_name)` | `Investing.com - {NOM DE LA LISTE}` → `Investing.com - <name>` (or just `Investing.com` if name is blank); other templates pass through |
| `merge_symbol_rows(existing_df, new_rows)` | Pure pandas merge: insert new symbols, update metadata of existing symbols (case-insensitive match), preserve existing `Symbols` casing |

### Persistence rules (critical invariants)

1. **`_merge_into_symbols_sheet` mutates ONLY the symbols sheet.** Every other sheet (timeframes, sources, anything else) is read in, then written back verbatim.
2. **No row is ever deleted from the symbols sheet** — duplicates are updated in place.
3. **`Symbols` column casing is preserved on update** (constant `UPDATABLE_SYMBOL_COLS` excludes it). The 4 metadata columns are always overwritten.
4. **All writes go through temp file + `shutil.move`** for atomicity (same pattern as `save_data_to_excel`).
5. **`DATA_LOCK` is held** during the read-modify-write cycle.

### Tooltip layout (post-Watchlist)

```
Symbol:     AAPL
Company:    Apple Inc.
URL:        https://finance.yahoo.com/quote/AAPL/   ← Yahoo Finance, clickable
Source URL: https://www.investing.com/...           ← User-entered "URL" field, clickable
Watchlist:  https://my-list - Tech Stocks          ← Watchlist URL (clickable) + " - " + Name
Source:     Buffet videos  ▾                       ← clickable, opens dropdown menu
```

Watchlist line is rendered by `TokenTooltip._render_watchlist_line` adaptively:
- Both filled → `Watchlist:  <URL clickable> - <name>` (Frame with two Labels)
- URL only   → `Watchlist:  <URL clickable>` (single clickable Label)
- Name only  → `Watchlist:  <name>` (single static Label)
- Both empty → `Watchlist:  -`

### Editable Source via tooltip

Click the `Source: ... ▾` line to open a radio-button menu listing every entry in `self.available_sources` (driven by the `sources` sheet) plus the `+ Nouvelle source...` sentinel. The menu is parented on `self.tree.winfo_toplevel()` (NOT the tooltip Toplevel) so it survives the tooltip's hide cycle. Picking a value:
- **A regular source** → updates `self.symbol_info[token]['source']` synchronously, spawns a daemon thread to `_persist_token_source` → rebuilds a single-row dict from cached `symbol_info` (preserves Company Name, Yahoo Finance URL, Source URL, **Watchlist URL, Watchlist Name**) → `_merge_into_symbols_sheet([row])` updates in place. Status bar: `Source mise à jour : <token> → <new>`. Failed write raises a messagebox.
- **`Investing.com - {NOM DE LA LISTE}`** → simpledialog prompt for list name (pre-filled if existing source already matches), then same persist flow with the composed `Investing.com - <name>` source. **After a successful merge, `_register_new_source(source)` is scheduled on the main thread** so the composite shows directly in future dropdowns.
- **`+ Nouvelle source...`** → simpledialog for new source name → `register_new_source` callback (wired to `TradingApp._register_new_source`) appends to the `sources` sheet → use as the new source for that token. Cancel / empty input is a silent no-op.

The legacy source value (e.g. `TradingView`) is automatically prepended to the menu if it isn't in `available_sources`, so you can read its current value before swapping it out.

### Add Tokens combobox: "+ Nouvelle source..."

The Add Tokens tab combobox is built with `values = available_sources + [NEW_SOURCE_SENTINEL]`. Picking the sentinel triggers `_on_source_changed` → simpledialog → `_register_new_source(name)` → `source_var` set to the new value. Cancel reverts to `available_sources[0]`. The `Investing.com - {NOM DE LA LISTE}` template still triggers the list-name field visibility toggle.

The sentinel is **never** stored in `self.available_sources` and is **filtered defensively** out of any sheet read by `_refresh_available_sources`, so the on-disk schema stays clean even if someone hand-edits the xlsx.

### Threading model

- `_on_add_tokens` validates, disables the Add button, then `threading.Thread(daemon=True).start()` on `_add_tokens_worker`
- `_add_tokens_worker` runs `lookup_info_for_symbol` / `best_symbol_for_company` per token with a 0.25s sleep (yfinance rate limit)
- All UI updates from the worker go through `self.root.after(0, ...)` — never call Tk from the worker thread directly
- On completion: `_on_add_complete` re-enables the button, calls `_reload_symbol_info` to refresh tooltip metadata (does NOT touch Treeviews — preserves filter state), shows messagebox summary
- Failures (unknown ticker, ambiguous name) are collected and reported but never block the rest of the batch

---

## Symbol Tools (Roger_trading_yfinance_symbol/)

These are **standalone CLI utilities** — they are not imported by the main app.

### `extract_symbols_from_txt.py`

Parses TradingView watchlist export format: `EXCHANGE:SYMBOL,EXCHANGE:SYMBOL,...` (with `###CATEGORY` headers).

```bash
python extract_symbols_from_txt.py symbols_to_extract.txt -o symbols.xlsx
```

Outputs a single-column Excel with `Symbol` header.

### `symbols_finder.py`

Maps company names to Yahoo Finance tickers using `yfinance.Search` with a scoring heuristic:
- Prefers EQUITY > ETF > MUTUALFUND > INDEX > CRYPTO
- Bonus for name substring match and token overlap
- Penalty for missing symbol, preference for shorter symbols

```bash
python symbols_finder.py names.xlsx -o names_with_symbols.xlsx
```

If input already looks like a ticker (all-caps, ≤15 chars), it is passed through unchanged.

---

## Known Issues & Technical Debt

### Bugs / Reliability

1. **UI freezes on update**: `update_data()` calls `generate_signals()` on the main thread. For large symbol lists this blocks Tkinter for minutes. Fix: run in a `threading.Thread` with progress feedback.

2. **`generate_signals` defined after `main()`** (`trading_signal_generator.py:321`): Unusual ordering; `main()` at line 201 calls it via a forward reference that happens to work in Python but is confusing. Should be reordered.

3. **`DATA_LOCK` not used in `update_data()`**: The lock exists but `update_data` doesn't hold it while `generate_signals()` writes to Excel. If the user triggers two rapid updates, race condition is possible.

4. **No atomic Excel read**: If Excel is open in another app (e.g., Excel/LibreOffice) during write, `openpyxl` may corrupt the file. The temp-file write (`save_data_to_excel`) mitigates write corruption, but read has no retry logic.

5. **`filter_signals()` doesn't combine with other filters**: The All/Buy/Sell buttons call `filter_signals()` independently, which ignores slope/token/ADX filters set in the filter bar. Only `apply_all_filters()` is correct. The buttons should call `apply_all_filters` instead (or extend it with a signal-type parameter).

### Dependencies

6. **Unused in requirements.txt**: `alpha_vantage`, `scipy`, `tktooltip` — none of these are imported in the current codebase. Remove them.

7. **`tktooltip` vs custom `ToolTip` class**: A custom `ToolTip` class is defined in `trading_gui.py` (line 59) and used everywhere. `tktooltip` (the package) is never used. Remove from requirements.

### Configuration

8. **All parameters hardcoded**: `TIMEFRAMES`, `STOCH_PARAMS`, `CCI_PERIOD`, `SLOPE_PERIOD`, `DMI_PERIOD`, etc. are module-level constants with no config file or CLI override. Adding a `config.yaml` or similar would allow per-user customization without code changes.

9. **`EXCEL_FILE` is a relative path** (`'trading_synthesis.xlsx'`): The app only works if launched from the project root. If run from another directory, it fails silently or creates the file in the wrong location.

### Testing

10. **Signal logic still untested**: The Add Tokens flow now has a 44-test pytest suite (`tests/test_add_tokens_tab.py` — covers Watchlist columns, sentinel flow, Investing auto-persist), and `symbols_finder.py` has its own 34-test suite. But the indicator computations and signal classification in `trading_signal_generator.py` remain untested. Any refactor of signal logic still risks silent breakage.

### Windows-specific

11. **`launch_roger_trading.bat` pulls from `origin/Roger2` and `origin/Roger`**: These remote branches appear to exist but are not visible locally. The batch file is designed for a Windows deployment workflow where code is updated from a specific branch. This branch strategy should be documented.

---

## Development Guidelines

### Adding a New Indicator

1. Add computation function in `trading_signal_generator.py` (alongside `compute_stoch`, `compute_cci`, `compute_dmi`)
2. Add it to `BASE_COLS` (line 211) if it should be stored
3. Compute it inside the `generate_signals` loop after existing indicators
4. Add display column width in `COLUMN_WIDTHS` dict (`trading_gui.py:88`)
5. If it should be hidden from display: add to `HIDDEN_DMI_COLS` (`trading_gui.py:14`)
6. Update `classify_signal_json` if signal classification changes

### Adding a New Timeframe

1. Add entry to `TIMEFRAMES` dict (`trading_signal_generator.py:9`)
2. The rest of the code is data-driven — Excel sheets, GUI tabs, trend columns are all generated dynamically from `TIMEFRAMES`
3. Check yfinance availability: 4h data is only available for ~60 days; shorter intervals have stricter period limits

### Adding a New Filter

1. Add a `tk.StringVar` or `tk.BooleanVar` in `create_widgets`
2. Bind it to `apply_all_filters` via `trace_add("write", ...)` or `command=`
3. Add filter logic inside `apply_all_filters()` — do NOT create a new standalone `filter_by_X()` method

### Modifying Signal Logic

**Critical invariants to preserve:**
- Monthly timeframe must use Open price for both calculation and display (see Monthly Special Rule above)
- `cross` flag must never change the `signal` label — it is a separate boolean attribute
- Neutral signals must not be stored in Excel or shown in GUI
- Price precision rule must be applied at all 4 points (fetch, synthetic bar, signal dict, Excel write)

### Saving to Excel

Always use `save_data_to_excel()` — it:
1. Recomputes PNL before write
2. Uses a temp file + atomic move
3. Preserves non-timeframe sheets (e.g., `symbols`)
4. Reindexes columns to canonical order

Never write directly to `EXCEL_FILE` with `pd.ExcelWriter` from outside this method.

---

## Running the Project

```bash
# Install deps
pip install -r requirements.txt

# GUI mode (default)
python roger_trading_launcher.py
# or
python trading_gui.py

# CLI mode (signal generation only, no GUI)
python roger_trading_launcher.py --cli
# or
python trading_signal_generator.py

# Symbol tools (standalone)
cd Roger_trading_yfinance_symbol/
python extract_symbols_from_txt.py symbols_to_extract.txt -o symbols.xlsx
python symbols_finder.py names.xlsx -o names_with_symbols.xlsx
```

### Prerequisites

- Python 3.9+ (pycache shows both 3.9 and 3.13 compiled files)
- Internet connectivity (yfinance fetches live data)
- `trading_synthesis.xlsx` must exist with a `symbols` sheet containing a `Symbols` column

---

## Priority Improvements (Roadmap)

### Court terme — Features actives (prochaines sessions)
- [ ] **Colonne "Company Name"** : afficher le nom complet de l'entreprise à côté du symbole dans toutes les vues (surtout utile pour les symboles exotiques). Nécessite de stocker le mapping symbol→name (probablement via `yf.Ticker(token).info['longName']` ou depuis le fichier `names_with_symbols.xlsx`).
- [ ] **Nouveaux filtres** : 1-2 critères de filtre supplémentaires dans la barre de la GUI (à préciser — candidates : filtre par CCI, filtre par signal spécifique Buy+/Sell+, filtre cross uniquement).
- [x] **Onglet Add Tokens** *(branche `add_tokens_tab`, mai 2026)*: 5ème onglet de la GUI permettant d'ajouter des symboles (ou des noms d'entreprise) à la feuille `symbols` du xlsx en collant une liste, en choisissant une source dans une liste finie, et optionnellement une URL. Tooltip enrichi avec une ligne "Source URL". Voir section "Add Tokens Flow" plus haut.
- [x] **Watchlist URL + Name** *(branche `add_tokens_tab`, mai 2026)*: deuxième paire de champs optionnels dans Add Tokens (URL + nom de la watchlist), deux nouvelles colonnes dans la feuille `symbols`, ligne tooltip adaptative `Watchlist:  <URL> - <nom>`.
- [x] **Auto-persist sources** *(branche `add_tokens_tab`, mai 2026)*: option `+ Nouvelle source...` en fin de dropdown (Add Tokens + tooltip menu) pour créer une nouvelle source à la volée ; chaque `Investing.com - <liste>` est aussi auto-ajouté à la feuille `sources` après usage.

### Moyen terme — Features futures (non spécifiées)
- [ ] À définir selon les besoins qui émergent

### Technique — Dette identifiée (à traiter quand opportun, pas prioritaire)
- [ ] Move signal generation to background thread — avec 500-1000 symboles l'update prend ~10 min et bloque l'UI. Acceptable pour l'instant (update 1-2×/jour), à considérer si le volume ou la fréquence augmente.
- [ ] Fix `filter_signals()` buttons to go through `apply_all_filters()` (bug: ignores active filters)
- [ ] Remove `filter_by_slope()` dead code (line 993)
- [ ] Clean up `requirements.txt`: remove `alpha_vantage`, `scipy`, `tktooltip`
- [ ] Make `EXCEL_FILE` path absolute (resolve relative to script directory, not CWD)

---

## Git & Branch Notes

- Main branch: `master` (Tom's dev branch)
- `origin/Roger2`: **active deployment branch** — Tom pushes here when ready to deliver to the client
- `origin/Roger`: deprecated, no longer used
- **Deployment workflow**: Tom pushes to `Roger2` → Roger (client, Windows) runs `launch_roger_trading.bat` which pulls the latest files and launches the GUI
- `trading_synthesis.xlsx` is gitignored — do not commit it
- `__pycache__/` is gitignored
- `update_watchlist.py` is gitignored and no longer needed — ignore it

### launch_roger_trading.bat — état actuel (corrigé 2026-04-30)
```bat
git fetch origin Roger2
git checkout origin/Roger2 -- trading_gui.py trading_signal_generator.py
```
Les deux lignes pointent correctement sur `Roger2`. Le commentaire echo ligne 16 dit encore "from branch Roger" mais c'est cosmétique uniquement.

---

## Session Start Checklist

Before any development session:

1. Read this file (done)
2. Check `tasks/todo.md` if it exists for in-progress work
3. Check `tasks/lessons.md` for past corrections
4. Run `git log --oneline -10` to see recent changes
5. Verify `trading_synthesis.xlsx` exists with a `symbols` sheet before testing signal generation
