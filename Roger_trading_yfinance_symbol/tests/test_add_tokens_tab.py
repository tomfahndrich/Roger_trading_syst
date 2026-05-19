"""Unit tests for the Add Tokens tab pure helpers and the xlsx merge integration.

Targets:
    - parse_tokens
    - build_source
    - merge_symbol_rows
    - _merge_into_symbols_sheet (file I/O round-trip via TradingApp on a fixture xlsx)

Pure helpers run without any GUI; the integration test creates a withdrawn Tk root
which works on macOS / Windows where the project runs.
"""

import os
import sys
import shutil
import tempfile
from pathlib import Path

import pandas as pd
import pytest

# Project root is two levels up from this test file.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading_gui import (
    parse_tokens,
    build_source,
    merge_symbol_rows,
    SYMBOLS_COLS,
    SYMBOLS_SHEET,
    SOURCES_SHEET,
    INVESTING_LIST_TEMPLATE,
    INVESTING_PREFIX,
    NEW_SOURCE_SENTINEL,
)


# ---------------------------------------------------------------------------
# parse_tokens
# ---------------------------------------------------------------------------

class TestParseTokens:
    def test_basic_split_on_newlines(self):
        assert parse_tokens("AAPL\nMSFT\nGOOGL") == ["AAPL", "MSFT", "GOOGL"]

    def test_strips_and_drops_empty(self):
        assert parse_tokens("  AAPL  \n\n   \nMSFT\n") == ["AAPL", "MSFT"]

    def test_case_insensitive_dedup_first_wins(self):
        assert parse_tokens("aapl\nAAPL\nApple\napple") == ["aapl", "Apple"]

    def test_empty_and_none(self):
        assert parse_tokens("") == []
        assert parse_tokens(None) == []


# ---------------------------------------------------------------------------
# build_source
# ---------------------------------------------------------------------------

class TestBuildSource:
    def test_non_template_passes_through(self):
        assert build_source("Buffet videos", "") == "Buffet videos"
        assert build_source("Buffet videos", "ignored") == "Buffet videos"
        assert build_source("Raoul Pal", "") == "Raoul Pal"

    def test_template_with_list_name_concatenates(self):
        assert build_source(INVESTING_LIST_TEMPLATE, "Tech Stocks") == "Investing.com - Tech Stocks"

    def test_template_with_list_name_strips_whitespace(self):
        assert build_source(INVESTING_LIST_TEMPLATE, "  Crypto  ") == "Investing.com - Crypto"

    def test_template_without_list_name_strips_suffix(self):
        assert build_source(INVESTING_LIST_TEMPLATE, "") == INVESTING_PREFIX
        assert build_source(INVESTING_LIST_TEMPLATE, "   ") == INVESTING_PREFIX

    def test_empty_template_returns_empty(self):
        assert build_source("", "anything") == ""
        assert build_source(None, None) == ""


# ---------------------------------------------------------------------------
# merge_symbol_rows
# ---------------------------------------------------------------------------

def _row(sym, name="X", yf="https://yf/X/", source="S", source_url="https://s/X"):
    return {
        "Symbols": sym,
        "Company Name": name,
        "Yahoo Finance URL": yf,
        "Source": source,
        "Source URL": source_url,
    }


class TestMergeSymbolRows:
    def test_inserts_new_rows_into_empty_df(self):
        df = pd.DataFrame(columns=SYMBOLS_COLS)
        merged, added, updated = merge_symbol_rows(df, [_row("AAPL", "Apple"), _row("MSFT", "Microsoft")])
        assert (added, updated) == (2, 0)
        assert list(merged["Symbols"]) == ["AAPL", "MSFT"]
        assert merged.loc[0, "Company Name"] == "Apple"

    def test_updates_existing_row_case_insensitive(self):
        df = pd.DataFrame([_row("AAPL", "Old", source="OldSource")], columns=SYMBOLS_COLS)
        merged, added, updated = merge_symbol_rows(df, [_row("aapl", "New", source="NewSource")])
        assert (added, updated) == (0, 1)
        assert len(merged) == 1
        assert merged.loc[0, "Company Name"] == "New"
        assert merged.loc[0, "Source"] == "NewSource"

    def test_mixed_insert_and_update(self):
        df = pd.DataFrame([_row("AAPL", "Apple")], columns=SYMBOLS_COLS)
        new_rows = [_row("AAPL", "Apple v2"), _row("MSFT", "Microsoft")]
        merged, added, updated = merge_symbol_rows(df, new_rows)
        assert (added, updated) == (1, 1)
        assert set(merged["Symbols"]) == {"AAPL", "MSFT"}

    def test_within_batch_duplicate_last_wins_on_metadata(self):
        df = pd.DataFrame(columns=SYMBOLS_COLS)
        new_rows = [_row("TSLA", "Tesla v1", source="X"), _row("tsla", "Tesla v2", source="Y")]
        merged, added, updated = merge_symbol_rows(df, new_rows)
        assert (added, updated) == (1, 0)
        row = merged.iloc[0]
        assert row["Company Name"] == "Tesla v2"
        assert row["Source"] == "Y"

    def test_empty_symbols_skipped(self):
        df = pd.DataFrame(columns=SYMBOLS_COLS)
        merged, added, updated = merge_symbol_rows(df, [_row("", "empty"), _row("VALID", "v")])
        assert (added, updated) == (1, 0)
        assert list(merged["Symbols"]) == ["VALID"]

    def test_creates_missing_source_url_column_on_legacy_df(self):
        legacy = pd.DataFrame(
            [{"Symbols": "AAPL", "Company Name": "Apple",
              "Yahoo Finance URL": "https://x", "Source": "S"}]
        )
        merged, added, updated = merge_symbol_rows(legacy, [_row("aapl", "Apple v2", source_url="https://new")])
        assert (added, updated) == (0, 1)
        assert "Source URL" in merged.columns
        assert merged.loc[0, "Source URL"] == "https://new"

    def test_none_or_empty_new_rows(self):
        df = pd.DataFrame([_row("AAPL", "Apple")], columns=SYMBOLS_COLS)
        merged, added, updated = merge_symbol_rows(df, None)
        assert (added, updated) == (0, 0)
        assert len(merged) == 1
        merged2, added2, updated2 = merge_symbol_rows(df, [])
        assert (added2, updated2) == (0, 0)


# ---------------------------------------------------------------------------
# Integration: _merge_into_symbols_sheet preserves all sheets
# ---------------------------------------------------------------------------

@pytest.fixture
def fixture_xlsx(tmp_path):
    """Build a minimal multi-sheet xlsx fixture and return its path."""
    path = tmp_path / "fixture.xlsx"
    sheets = {
        "monthly": pd.DataFrame([{"datetime": "2025-01-01", "token": "MOCK", "signal": "Buy"}]),
        "weekly": pd.DataFrame([{"datetime": "2025-01-01", "token": "MOCK", "signal": "Sell"}]),
        SYMBOLS_SHEET: pd.DataFrame(
            [{"Symbols": "AAPL", "Company Name": "Apple Inc.",
              "Yahoo Finance URL": "https://finance.yahoo.com/quote/AAPL/", "Source": "Original"}]
        ),
        SOURCES_SHEET: pd.DataFrame({"Source Name": ["Buffet videos", "Raoul Pal"]}),
    }
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        for sn, df in sheets.items():
            df.to_excel(w, sheet_name=sn, index=False)
    return path


@pytest.fixture
def app(monkeypatch, fixture_xlsx):
    """Spin up TradingApp wired to the fixture xlsx; tear down the Tk root after each test."""
    tk = pytest.importorskip("tkinter", reason="Tkinter not available in this environment")
    import trading_gui
    import trading_signal_generator
    monkeypatch.setattr(trading_gui, "EXCEL_FILE", str(fixture_xlsx))
    monkeypatch.setattr(trading_signal_generator, "EXCEL_FILE", str(fixture_xlsx))

    root = tk.Tk()
    root.withdraw()
    app_instance = trading_gui.TradingApp(root)
    yield app_instance
    root.destroy()


class TestMergeIntoSymbolsSheet:
    def test_preserves_all_other_sheets_and_appends_new_token(self, app, fixture_xlsx):
        rows = [_row("ZZZ", "Zed Inc.", source="Buffet videos", source_url="https://test/zzz")]
        added, updated = app._merge_into_symbols_sheet(rows)
        assert (added, updated) == (1, 0)

        xl = pd.ExcelFile(fixture_xlsx)
        assert set(xl.sheet_names) == {"monthly", "weekly", SYMBOLS_SHEET, SOURCES_SHEET}

        sym = pd.read_excel(xl, SYMBOLS_SHEET)
        assert set(sym["Symbols"]) == {"AAPL", "ZZZ"}
        assert "Source URL" in sym.columns

        # Untouched sheets
        monthly = pd.read_excel(xl, "monthly")
        assert list(monthly.columns) == ["datetime", "token", "signal"]
        assert monthly.iloc[0]["token"] == "MOCK"

        sources = pd.read_excel(xl, SOURCES_SHEET)
        assert list(sources["Source Name"]) == ["Buffet videos", "Raoul Pal"]

    def test_updates_existing_row_in_place(self, app, fixture_xlsx):
        rows = [_row("aapl", "Apple New", source="Raoul Pal", source_url="https://test/aapl")]
        added, updated = app._merge_into_symbols_sheet(rows)
        assert (added, updated) == (0, 1)

        sym = pd.read_excel(fixture_xlsx, sheet_name=SYMBOLS_SHEET)
        assert len(sym) == 1
        row = sym.iloc[0]
        assert row["Symbols"] == "AAPL"  # original casing preserved
        assert row["Company Name"] == "Apple New"
        assert row["Source"] == "Raoul Pal"
        assert row["Source URL"] == "https://test/aapl"


# ---------------------------------------------------------------------------
# Integration: _persist_token_source (tooltip Source dropdown writeback)
# ---------------------------------------------------------------------------

class TestPersistTokenSource:
    def test_updates_source_only_preserves_other_metadata(self, app, fixture_xlsx):
        """Picking a new source from the tooltip must update Source in xlsx
        without touching Company Name, Yahoo Finance URL, or Source URL."""
        # Seed in-memory symbol_info so _persist_token_source has full context
        # (the real flow loads this from xlsx in load_data).
        app.symbol_info["AAPL"] = {
            "company_name": "Apple Inc.",
            "yf_url": "https://finance.yahoo.com/quote/AAPL/",
            "source": "Original",
            "source_url": "https://test/source-page",
        }

        # Direct synchronous call (matches what the daemon thread executes)
        app._persist_token_source("AAPL", "Buffet videos")

        sym = pd.read_excel(fixture_xlsx, sheet_name=SYMBOLS_SHEET)
        row = sym[sym["Symbols"] == "AAPL"].iloc[0]
        assert row["Source"] == "Buffet videos"
        assert row["Company Name"] == "Apple Inc."
        assert row["Yahoo Finance URL"] == "https://finance.yahoo.com/quote/AAPL/"
        assert row["Source URL"] == "https://test/source-page"

    def test_update_token_source_updates_in_memory_immediately(self, app, monkeypatch):
        """The user-facing entry point must reflect the change in symbol_info
        before the background thread completes (so the next hover is accurate).

        We MUST stub _persist_token_source: the daemon thread it spawns can
        outlive both this test and the monkeypatch teardown that restores
        EXCEL_FILE — if it writes via the unpatched path, it overwrites the
        user's real xlsx. Stubbing keeps the thread effectively a no-op.
        """
        persist_calls = []
        monkeypatch.setattr(
            app, "_persist_token_source",
            lambda token, src: persist_calls.append((token, src)),
        )

        app.symbol_info["AAPL"] = {
            "company_name": "Apple Inc.",
            "yf_url": "https://finance.yahoo.com/quote/AAPL/",
            "source": "Original",
            "source_url": "",
        }
        app._update_token_source("AAPL", "Diallo videos")

        # Synchronous in-memory update must be visible immediately
        assert app.symbol_info["AAPL"]["source"] == "Diallo videos"

        # Persist was scheduled with the correct args (the thread may or may not
        # have run yet, so wait briefly for it to invoke our stub).
        import time
        for _ in range(20):
            if persist_calls:
                break
            time.sleep(0.05)
        assert persist_calls == [("AAPL", "Diallo videos")]

    def test_unknown_token_is_silently_ignored(self, app):
        """Defensive: a token not in symbol_info should not crash or persist."""
        before = dict(app.symbol_info)
        app._update_token_source("NONEXISTENT_TOKEN_XYZ", "Buffet videos")
        # No new entry created, no exception
        assert "NONEXISTENT_TOKEN_XYZ" not in app.symbol_info
        assert app.symbol_info == before


# ---------------------------------------------------------------------------
# TokenTooltip._on_source_picked: Investing.com template prompts for list name
# ---------------------------------------------------------------------------

@pytest.fixture
def token_tooltip(monkeypatch):
    """A real TokenTooltip instance attached to a withdrawn Tk root + Treeview.
    Yields (tooltip, symbol_info, changes) where `changes` accumulates every
    on_source_change(token, new_source) call."""
    tk = pytest.importorskip("tkinter")
    from tkinter import ttk
    import trading_gui

    root = tk.Tk()
    root.withdraw()
    tree = ttk.Treeview(root)

    changes = []
    sym_info = {}
    tt = trading_gui.TokenTooltip(
        tree, sym_info,
        on_source_change=lambda token, src: changes.append((token, src)),
        get_sources=lambda: ["Buffet videos", trading_gui.INVESTING_LIST_TEMPLATE],
    )
    yield tt, sym_info, changes
    root.destroy()


class TestSourcePickedInvestingTemplate:
    def test_template_pick_prompts_and_concatenates_list_name(self, token_tooltip, monkeypatch):
        tt, sym_info, changes = token_tooltip
        sym_info["AAPL"] = {"source": "Original"}
        monkeypatch.setattr(
            "trading_gui.simpledialog.askstring",
            lambda *a, **kw: "Tech Watchlist",
        )
        from trading_gui import INVESTING_LIST_TEMPLATE
        tt._on_source_picked("AAPL", INVESTING_LIST_TEMPLATE)
        assert changes == [("AAPL", "Investing.com - Tech Watchlist")]

    def test_template_pick_with_empty_input_strips_suffix(self, token_tooltip, monkeypatch):
        tt, sym_info, changes = token_tooltip
        sym_info["AAPL"] = {"source": "Original"}
        monkeypatch.setattr("trading_gui.simpledialog.askstring", lambda *a, **kw: "")
        from trading_gui import INVESTING_LIST_TEMPLATE, INVESTING_PREFIX
        tt._on_source_picked("AAPL", INVESTING_LIST_TEMPLATE)
        assert changes == [("AAPL", INVESTING_PREFIX)]

    def test_template_pick_cancelled_makes_no_change(self, token_tooltip, monkeypatch):
        tt, sym_info, changes = token_tooltip
        sym_info["AAPL"] = {"source": "Original"}
        monkeypatch.setattr("trading_gui.simpledialog.askstring", lambda *a, **kw: None)
        from trading_gui import INVESTING_LIST_TEMPLATE
        tt._on_source_picked("AAPL", INVESTING_LIST_TEMPLATE)
        assert changes == []

    def test_template_pick_prefills_existing_list_name(self, token_tooltip, monkeypatch):
        tt, sym_info, changes = token_tooltip
        sym_info["AAPL"] = {"source": "Investing.com - Old List"}
        captured = {}
        def fake_askstring(*args, **kwargs):
            captured["initialvalue"] = kwargs.get("initialvalue")
            return "New List"
        monkeypatch.setattr("trading_gui.simpledialog.askstring", fake_askstring)
        from trading_gui import INVESTING_LIST_TEMPLATE
        tt._on_source_picked("AAPL", INVESTING_LIST_TEMPLATE)
        assert captured["initialvalue"] == "Old List"
        assert changes == [("AAPL", "Investing.com - New List")]

    def test_non_template_pick_skips_dialog(self, token_tooltip, monkeypatch):
        """Picking a regular source must NOT call simpledialog at all."""
        tt, sym_info, changes = token_tooltip
        sym_info["AAPL"] = {"source": "Old"}
        called = []
        monkeypatch.setattr(
            "trading_gui.simpledialog.askstring",
            lambda *a, **kw: called.append(True) or "should-not-appear",
        )
        tt._on_source_picked("AAPL", "Buffet videos")
        assert called == []
        assert changes == [("AAPL", "Buffet videos")]

    def test_picking_same_source_is_noop(self, token_tooltip):
        tt, sym_info, changes = token_tooltip
        sym_info["AAPL"] = {"source": "Buffet videos"}
        tt._on_source_picked("AAPL", "Buffet videos")
        assert changes == []


# ---------------------------------------------------------------------------
# Mod 1 — Watchlist URL/Name: schema + tooltip rendering
# ---------------------------------------------------------------------------

class TestWatchlistColumns:
    def test_merge_persists_watchlist_url_and_name(self, app, fixture_xlsx):
        rows = [{
            "Symbols": "WLTOKEN", "Company Name": "Watchlist Co.",
            "Yahoo Finance URL": "https://yf/WLTOKEN/",
            "Source": "Buffet videos", "Source URL": "",
            "Watchlist URL": "https://invest.com/list/42",
            "Watchlist Name": "Tech Stocks",
        }]
        added, updated = app._merge_into_symbols_sheet(rows)
        assert (added, updated) == (1, 0)

        sym = pd.read_excel(fixture_xlsx, sheet_name=SYMBOLS_SHEET)
        assert "Watchlist URL" in sym.columns
        assert "Watchlist Name" in sym.columns
        new = sym[sym["Symbols"] == "WLTOKEN"].iloc[0]
        assert new["Watchlist URL"] == "https://invest.com/list/42"
        assert new["Watchlist Name"] == "Tech Stocks"

    def test_merge_preserves_watchlist_on_source_only_update(self, app, fixture_xlsx):
        """Updating just the Source from the tooltip MUST NOT wipe Watchlist
        data. _persist_token_source rebuilds the row from cached symbol_info."""
        # Seed full row
        app.symbol_info["AAPL"] = {
            "company_name": "Apple Inc.",
            "yf_url": "https://finance.yahoo.com/quote/AAPL/",
            "source": "Original",
            "source_url": "https://x",
            "watchlist_url": "https://my-list",
            "watchlist_name": "Big Tech",
        }
        app._persist_token_source("AAPL", "New Source")
        sym = pd.read_excel(fixture_xlsx, sheet_name=SYMBOLS_SHEET)
        row = sym[sym["Symbols"] == "AAPL"].iloc[0]
        assert row["Source"] == "New Source"
        assert row["Watchlist URL"] == "https://my-list"
        assert row["Watchlist Name"] == "Big Tech"


class TestWatchlistTooltipRendering:
    """Inspect the widgets _render_watchlist_line packs for the 4 cases."""

    @pytest.fixture
    def render_target(self, token_tooltip):
        tt, _, _ = token_tooltip
        import tkinter as tk
        win = tk.Toplevel(tt.tree)
        pad = {"padx": 8, "pady": 2, "anchor": "w", "fg": "black"}
        yield tt, win, pad
        win.destroy()

    def _label_texts(self, container):
        """Recursively gather texts of all Label children."""
        import tkinter as tk
        out = []
        for child in container.winfo_children():
            if isinstance(child, tk.Label):
                out.append(child.cget("text"))
            else:
                out.extend(self._label_texts(child))
        return out

    def test_both_empty_renders_dash(self, render_target):
        tt, win, pad = render_target
        tt._render_watchlist_line(win, "", "", pad)
        assert self._label_texts(win) == ["Watchlist:  -"]

    def test_url_only(self, render_target):
        tt, win, pad = render_target
        tt._render_watchlist_line(win, "https://x", "", pad)
        assert self._label_texts(win) == ["Watchlist:  https://x"]

    def test_name_only(self, render_target):
        tt, win, pad = render_target
        tt._render_watchlist_line(win, "", "Tech", pad)
        assert self._label_texts(win) == ["Watchlist:  Tech"]

    def test_both_filled_renders_url_dash_name(self, render_target):
        tt, win, pad = render_target
        tt._render_watchlist_line(win, "https://x", "Tech", pad)
        # Frame with two labels: URL clickable + " - Tech"
        assert self._label_texts(win) == ["Watchlist:  https://x", " - Tech"]


# ---------------------------------------------------------------------------
# Mod 2a — _register_new_source + sentinel pick flow
# ---------------------------------------------------------------------------

class TestRegisterNewSource:
    def test_appends_to_sources_sheet_and_in_memory_list(self, app, fixture_xlsx):
        before = list(app.available_sources)
        app._register_new_source("My YouTube Channel")
        assert "My YouTube Channel" in app.available_sources
        assert app.available_sources == before + ["My YouTube Channel"]

        src = pd.read_excel(fixture_xlsx, sheet_name=SOURCES_SHEET)
        assert "My YouTube Channel" in src.iloc[:, 0].tolist()

    def test_idempotent_on_existing_name(self, app):
        app._register_new_source("Buffet videos")  # already in defaults
        # Count occurrences in the list
        assert app.available_sources.count("Buffet videos") == 1

    def test_empty_name_is_noop(self, app):
        before = list(app.available_sources)
        app._register_new_source("")
        app._register_new_source("   ")
        app._register_new_source(None)
        assert app.available_sources == before

    def test_sentinel_is_silently_rejected(self, app):
        """Defensive: if the sentinel ever gets passed in, never persist it."""
        before = list(app.available_sources)
        app._register_new_source(NEW_SOURCE_SENTINEL)
        assert app.available_sources == before

    def test_combobox_values_refreshed_with_sentinel_at_end(self, app):
        app._register_new_source("Brand New Source")
        values = list(app.source_combobox["values"])
        assert "Brand New Source" in values
        assert values[-1] == NEW_SOURCE_SENTINEL


@pytest.fixture
def token_tooltip_with_register(monkeypatch):
    """Like token_tooltip but also wires register_new_source. Yields 4-tuple."""
    tk = pytest.importorskip("tkinter")
    from tkinter import ttk
    import trading_gui
    root = tk.Tk()
    root.withdraw()
    tree = ttk.Treeview(root)
    changes = []
    registered = []
    sym_info = {}
    tt = trading_gui.TokenTooltip(
        tree, sym_info,
        on_source_change=lambda token, src: changes.append((token, src)),
        get_sources=lambda: ["Buffet videos", trading_gui.INVESTING_LIST_TEMPLATE],
        register_new_source=lambda name: registered.append(name),
    )
    yield tt, sym_info, changes, registered
    root.destroy()


class TestTooltipNewSourceSentinel:
    def test_pick_sentinel_prompts_registers_and_uses_new_name(
        self, token_tooltip_with_register, monkeypatch
    ):
        tt, sym_info, changes, registered = token_tooltip_with_register
        sym_info["AAPL"] = {"source": "Original"}
        monkeypatch.setattr(
            "trading_gui.simpledialog.askstring",
            lambda *a, **kw: "Cathie Wood",
        )
        tt._on_source_picked("AAPL", NEW_SOURCE_SENTINEL)
        assert registered == ["Cathie Wood"]
        assert changes == [("AAPL", "Cathie Wood")]

    def test_pick_sentinel_cancelled_does_nothing(
        self, token_tooltip_with_register, monkeypatch
    ):
        tt, sym_info, changes, registered = token_tooltip_with_register
        sym_info["AAPL"] = {"source": "Original"}
        monkeypatch.setattr("trading_gui.simpledialog.askstring", lambda *a, **kw: None)
        tt._on_source_picked("AAPL", NEW_SOURCE_SENTINEL)
        assert registered == []
        assert changes == []

    def test_pick_sentinel_empty_string_does_nothing(
        self, token_tooltip_with_register, monkeypatch
    ):
        tt, sym_info, changes, registered = token_tooltip_with_register
        sym_info["AAPL"] = {"source": "Original"}
        monkeypatch.setattr("trading_gui.simpledialog.askstring", lambda *a, **kw: "   ")
        tt._on_source_picked("AAPL", NEW_SOURCE_SENTINEL)
        assert registered == []
        assert changes == []

    def test_open_source_menu_appends_sentinel_when_register_wired(
        self, token_tooltip_with_register
    ):
        """The sentinel must be the LAST item of the menu when register is wired."""
        tt, sym_info, _, _ = token_tooltip_with_register
        sym_info["AAPL"] = {"source": "Buffet videos"}
        tt._current_token = "AAPL"

        # Stub tk_popup so it doesn't actually display; capture the menu
        import tkinter as tk
        captured = {}
        original_init = tk.Menu.__init__
        def patched_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            captured["menu"] = self
        tk.Menu.__init__ = patched_init
        try:
            class FakeEvent:
                x_root = 0
                y_root = 0
            try:
                tt._open_source_menu(FakeEvent())
            except Exception:
                pass  # tk_popup may fail in headless contexts
        finally:
            tk.Menu.__init__ = original_init

        menu = captured.get("menu")
        assert menu is not None
        # Walk menu items
        last_idx = menu.index("end")
        labels = [menu.entrycget(i, "label") for i in range(last_idx + 1)]
        assert labels[-1] == NEW_SOURCE_SENTINEL


# ---------------------------------------------------------------------------
# Mod 2b — Investing.com composite auto-registers after persist
# ---------------------------------------------------------------------------

class TestInvestingCompositeAutoPersist:
    def test_persist_token_source_with_investing_composite_calls_register(
        self, app, fixture_xlsx, monkeypatch
    ):
        """When _persist_token_source writes a Source like 'Investing.com - Tech',
        it must schedule _register_new_source on the main thread."""
        app.symbol_info["AAPL"] = {
            "company_name": "Apple Inc.",
            "yf_url": "https://yf/AAPL/",
            "source": "Original",
            "source_url": "",
            "watchlist_url": "",
            "watchlist_name": "",
        }

        # Capture root.after scheduled callbacks (run them synchronously)
        scheduled = []
        def fake_after(delay, fn, *args):
            scheduled.append((fn, args))
            fn(*args)
        monkeypatch.setattr(app.root, "after", fake_after)

        app._persist_token_source("AAPL", "Investing.com - Tech Stocks")

        # _register_new_source should have been called with the composite
        register_calls = [args for fn, args in scheduled if fn == app._register_new_source]
        assert register_calls == [("Investing.com - Tech Stocks",)]
        assert "Investing.com - Tech Stocks" in app.available_sources

    def test_persist_token_source_with_non_investing_skips_register(
        self, app, fixture_xlsx, monkeypatch
    ):
        app.symbol_info["AAPL"] = {
            "company_name": "Apple Inc.", "yf_url": "https://yf/AAPL/",
            "source": "Original", "source_url": "",
            "watchlist_url": "", "watchlist_name": "",
        }
        scheduled = []
        def fake_after(delay, fn, *args):
            scheduled.append((fn, args))
            fn(*args)
        monkeypatch.setattr(app.root, "after", fake_after)

        before = list(app.available_sources)
        app._persist_token_source("AAPL", "Buffet videos")
        # Buffet videos already in defaults → register would no-op anyway,
        # but more importantly it should NOT be scheduled at all
        register_calls = [args for fn, args in scheduled if fn == app._register_new_source]
        assert register_calls == []
        assert app.available_sources == before
