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
