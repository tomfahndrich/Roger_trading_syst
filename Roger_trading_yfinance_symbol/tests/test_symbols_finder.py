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
