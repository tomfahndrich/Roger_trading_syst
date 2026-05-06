import sys
import os
import argparse
import tempfile
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock, PropertyMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import symbols_finder as sf


# ── lookup_info_for_symbol ────────────────────────────────────────────────────

class TestLookupInfoForSymbol:

    def test_returns_longname_when_available(self):
        mock_info = {"longName": "Apple Inc.", "shortName": "Apple", "quoteType": "EQUITY"}
        with patch("symbols_finder.yf.Ticker") as mock_cls:
            mock_cls.return_value.info = mock_info
            name, debug = sf.lookup_info_for_symbol("AAPL")
        assert name == "Apple Inc."
        assert "info_ok" in debug

    def test_falls_back_to_shortname_when_no_longname(self):
        mock_info = {"shortName": "Apple", "quoteType": "EQUITY"}
        with patch("symbols_finder.yf.Ticker") as mock_cls:
            mock_cls.return_value.info = mock_info
            name, debug = sf.lookup_info_for_symbol("AAPL")
        assert name == "Apple"
        assert "info_ok" in debug

    def test_returns_none_when_no_name_fields(self):
        with patch("symbols_finder.yf.Ticker") as mock_cls:
            mock_cls.return_value.info = {"quoteType": "EQUITY"}
            name, debug = sf.lookup_info_for_symbol("AAPL")
        assert name is None
        assert "info_ok" in debug

    def test_empty_symbol_returns_none_without_network_call(self):
        with patch("symbols_finder.yf.Ticker") as mock_cls:
            name, debug = sf.lookup_info_for_symbol("")
        assert name is None
        assert debug == "empty_symbol"
        mock_cls.assert_not_called()

    def test_whitespace_only_symbol_returns_none(self):
        with patch("symbols_finder.yf.Ticker") as mock_cls:
            name, debug = sf.lookup_info_for_symbol("   ")
        assert name is None
        assert debug == "empty_symbol"
        mock_cls.assert_not_called()

    def test_empty_info_dict_returns_none(self):
        with patch("symbols_finder.yf.Ticker") as mock_cls:
            mock_cls.return_value.info = {}
            name, debug = sf.lookup_info_for_symbol("INVALID")
        assert name is None
        assert debug == "no_info"

    def test_exception_during_info_access_returns_none(self):
        with patch("symbols_finder.yf.Ticker") as mock_cls:
            mock_ticker = MagicMock()
            type(mock_ticker).info = PropertyMock(side_effect=Exception("network error"))
            mock_cls.return_value = mock_ticker
            name, debug = sf.lookup_info_for_symbol("AAPL")
        assert name is None
        assert "info_error" in debug
        assert "Exception" in debug

    def test_symbol_is_stripped(self):
        mock_info = {"longName": "Apple Inc.", "quoteType": "EQUITY"}
        with patch("symbols_finder.yf.Ticker") as mock_cls:
            mock_cls.return_value.info = mock_info
            name, _ = sf.lookup_info_for_symbol("  AAPL  ")
        mock_cls.assert_called_once_with("AAPL")
        assert name == "Apple Inc."


# ── TestArgparse ─────────────────────────────────────────────────────────────

class TestArgparse:

    def _parse(self, args_list):
        ap = argparse.ArgumentParser()
        ap.add_argument("input_xlsx")
        ap.add_argument("--output", "-o", default=None)
        ap.add_argument("--sheet", default=None)
        ap.add_argument("--name-col", default=0, type=int)
        ap.add_argument("--symbol-col-name", default="Symbol")
        ap.add_argument("--sleep", default=0.25, type=float)
        ap.add_argument("--max-results", default=10, type=int)
        ap.add_argument("--mode", choices=["name", "symbol"], default="name")
        ap.add_argument("--source", default="investing.com")
        return ap.parse_args(args_list)

    def test_default_mode_is_name(self):
        args = self._parse(["input.xlsx"])
        assert args.mode == "name"

    def test_mode_symbol_accepted(self):
        args = self._parse(["input.xlsx", "--mode", "symbol"])
        assert args.mode == "symbol"

    def test_mode_invalid_rejected(self):
        with pytest.raises(SystemExit):
            self._parse(["input.xlsx", "--mode", "invalid"])

    def test_default_source_is_investing_com(self):
        args = self._parse(["input.xlsx"])
        assert args.source == "investing.com"

    def test_custom_source_accepted(self):
        args = self._parse(["input.xlsx", "--source", "manual"])
        assert args.source == "manual"


class TestMainModeRouting:

    def _run_main_with_temp_excel(self, input_data: list, extra_args: list) -> pd.DataFrame:
        import os
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            input_path = f.name
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            output_path = f.name

        pd.DataFrame(input_data, columns=["Input"]).to_excel(input_path, index=False)

        import sys
        argv_backup = sys.argv[:]
        sys.argv = ["symbols_finder.py", input_path, "--output", output_path] + extra_args
        try:
            sf.main()
        finally:
            sys.argv = argv_backup
            os.unlink(input_path)

        result = pd.read_excel(output_path)
        os.unlink(output_path)
        return result

    def test_symbol_mode_calls_lookup_not_search(self):
        with patch("symbols_finder.lookup_info_for_symbol", return_value=("Apple Inc.", "info_ok:EQUITY")) as mock_lookup, \
             patch("symbols_finder.best_symbol_for_company") as mock_search:
            self._run_main_with_temp_excel(["AAPL", "MSFT"], ["--mode", "symbol"])

        assert mock_lookup.call_count == 2
        mock_search.assert_not_called()

    def test_symbol_mode_output_has_correct_columns(self):
        with patch("symbols_finder.lookup_info_for_symbol", return_value=("Apple Inc.", "info_ok:EQUITY")):
            df = self._run_main_with_temp_excel(["AAPL"], ["--mode", "symbol"])

        assert list(df.columns) == ["Symbol", "Company Name", "Yahoo Finance URL", "Source"]

    def test_symbol_mode_symbol_preserved_from_input(self):
        with patch("symbols_finder.lookup_info_for_symbol", return_value=("Apple Inc.", "info_ok:EQUITY")):
            df = self._run_main_with_temp_excel(["AAPL"], ["--mode", "symbol"])

        assert df.iloc[0]["Symbol"] == "AAPL"
        assert df.iloc[0]["Company Name"] == "Apple Inc."
        assert df.iloc[0]["Yahoo Finance URL"] == "https://finance.yahoo.com/quote/AAPL/"

    def test_name_mode_still_calls_best_symbol_for_company(self):
        with patch("symbols_finder.best_symbol_for_company", return_value=("AAPL", "Apple Inc.", "picked:EQUITY:Apple Inc.")) as mock_search, \
             patch("symbols_finder.lookup_info_for_symbol") as mock_lookup:
            self._run_main_with_temp_excel(["Apple Inc."], ["--mode", "name"])

        mock_search.assert_called_once()
        mock_lookup.assert_not_called()

    def test_source_arg_written_to_source_column(self):
        with patch("symbols_finder.lookup_info_for_symbol", return_value=("Apple Inc.", "info_ok:EQUITY")):
            df = self._run_main_with_temp_excel(["AAPL"], ["--mode", "symbol", "--source", "manual"])

        assert df.iloc[0]["Source"] == "manual"
