import sys
import os
import pytest
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

    def test_returns_none_when_no_name_fields(self):
        with patch("symbols_finder.yf.Ticker") as mock_cls:
            mock_cls.return_value.info = {"quoteType": "EQUITY"}
            name, debug = sf.lookup_info_for_symbol("AAPL")
        assert name is None

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
