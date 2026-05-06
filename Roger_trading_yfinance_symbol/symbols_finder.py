#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Map company names -> most probable Yahoo Finance symbol using yfinance.Search,
reading from an Excel file and writing the symbol into a second column.

Install:
  pip install pandas openpyxl yfinance
"""

from __future__ import annotations

import argparse
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yfinance as yf


TICKER_LIKE_RE = re.compile(r"^[A-Z0-9.\-^=]{1,15}$")  # rough heuristic


def looks_like_ticker(s: str) -> bool:
    s = (s or "").strip()
    return bool(s) and bool(TICKER_LIKE_RE.match(s)) and s.upper() == s


def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def score_quote(company: str, q: Dict[str, Any]) -> float:
    """
    Heuristic scoring of a search quote result.
    Higher = better.
    """
    company_n = normalize_text(company)

    symbol = (q.get("symbol") or "").strip()
    shortname = normalize_text(q.get("shortname") or "")
    longname = normalize_text(q.get("longname") or "")
    qtype = (q.get("quoteType") or "").upper()

    # Base by instrument type preference
    type_weight = {
        "EQUITY": 100.0,
        "ETF": 80.0,
        "MUTUALFUND": 60.0,
        "INDEX": 40.0,
        "CRYPTOCURRENCY": 30.0,
        "CURRENCY": 20.0,
    }.get(qtype, 10.0)

    score = type_weight

    # Name match bonuses
    if company_n and (company_n in longname or company_n in shortname):
        score += 40.0
    # Token overlap bonus
    company_tokens = set(re.findall(r"[a-z0-9]+", company_n))
    name_tokens = set(re.findall(r"[a-z0-9]+", f"{shortname} {longname}"))
    if company_tokens and name_tokens:
        overlap = len(company_tokens & name_tokens) / max(1, len(company_tokens))
        score += 30.0 * overlap

    # Penalty for missing symbol
    if not symbol:
        score -= 1000.0

    # Small preference for shorter, cleaner symbols
    score += max(0.0, 5.0 - (len(symbol) / 5.0))

    return score


def best_symbol_for_company(company: str, max_results: int = 10, timeout: int = 30) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Returns (symbol, company_name, debug_info).
    """
    company = (company or "").strip()
    if not company:
        return None, None, "empty_company"

    # If input already looks like a ticker, keep it
    if looks_like_ticker(company):
        return company, None, "input_looks_like_ticker"

    try:
        res = yf.Search(company, max_results=max_results, timeout=timeout).quotes
    except Exception as e:
        return None, None, f"search_error:{type(e).__name__}"

    if not res:
        return None, None, "no_results"

    # Keep only results with a symbol
    candidates: List[Dict[str, Any]] = [q for q in res if (q.get("symbol") or "").strip()]
    if not candidates:
        return None, None, "no_symbol_in_results"

    ranked = sorted(
        ((score_quote(company, q), q) for q in candidates),
        key=lambda x: x[0],
        reverse=True,
    )
    best_q = ranked[0][1]
    best_sym = (best_q.get("symbol") or "").strip() or None
    best_type = (best_q.get("quoteType") or "").upper() or "UNKNOWN"
    best_name = best_q.get("longname") or best_q.get("shortname") or ""
    return best_sym, best_name or None, f"picked:{best_type}:{best_name}"


def lookup_info_for_symbol(symbol: str) -> Tuple[Optional[str], str]:
    """
    Returns (company_name, debug_info) for a given ticker symbol.
    Uses yf.Ticker(symbol).info to resolve longName / shortName.
    """
    symbol = (symbol or "").strip()
    if not symbol:
        return None, "empty_symbol"

    try:
        info = yf.Ticker(symbol).info
    except Exception as e:
        return None, f"info_error:{type(e).__name__}"

    if not info:
        return None, "no_info"

    name = info.get("longName") or info.get("shortName") or None
    qtype = info.get("quoteType", "UNKNOWN")
    return name, f"info_ok:{qtype}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Add Yahoo Finance symbols to an Excel file based on company names.")
    ap.add_argument("input_xlsx", help="Path to input Excel file (.xlsx)")
    ap.add_argument("--output", "-o", default=None, help="Path to output Excel file (.xlsx). Default: <input>_with_symbols.xlsx")
    ap.add_argument("--sheet", default=None, help="Sheet name (or 0-based index). Default: first sheet")
    ap.add_argument("--name-col", default=0, type=int, help="0-based index of input column (company names in 'name' mode, symbols in 'symbol' mode). Default: 0")
    ap.add_argument("--symbol-col-name", default="Symbol", help="Header name for output symbol column. Default: Symbol")
    ap.add_argument("--sleep", default=0.25, type=float, help="Sleep between requests (seconds). Default: 0.25")
    ap.add_argument("--max-results", default=10, type=int, help="Search max_results. Default: 10")
    ap.add_argument(
        "--mode",
        choices=["name", "symbol"],
        default="name",
        help="Input mode: 'name' (company name → symbol, default) or 'symbol' (symbol → company name).",
    )
    ap.add_argument(
        "--source",
        default="investing.com",
        help="Value written to the Source column. Default: investing.com",
    )
    args = ap.parse_args()

    inp = args.input_xlsx
    out = args.output or re.sub(r"\.xlsx$", "", inp, flags=re.IGNORECASE) + "_with_symbols.xlsx"

    # pandas.read_excel(..., sheet_name=None) returns a dict of {sheet_name: DataFrame}
    # but the rest of the script expects a single DataFrame.
    sheet_arg = args.sheet
    if isinstance(sheet_arg, str) and sheet_arg.strip().isdigit():
        sheet_arg = int(sheet_arg.strip())
    if sheet_arg is None:
        sheet_arg = 0

    df_or_sheets = pd.read_excel(inp, sheet_name=sheet_arg)
    if isinstance(df_or_sheets, dict):
        if not df_or_sheets:
            raise ValueError("No sheets found in Excel workbook")
        first_sheet_name = next(iter(df_or_sheets))
        df = df_or_sheets[first_sheet_name]
        print(f"ℹ️  Using first sheet: {first_sheet_name}")
    else:
        df = df_or_sheets

    if df.shape[1] <= args.name_col:
        raise ValueError(f"name-col={args.name_col} out of range for dataframe with {df.shape[1]} columns")

    name_series = df.iloc[:, args.name_col]

    symbols: List[Optional[str]] = []
    company_names: List[Optional[str]] = []
    yf_urls: List[str] = []

    total = len(name_series)
    for i, val in enumerate(name_series.tolist(), start=1):
        raw = "" if pd.isna(val) else str(val).strip()

        if args.mode == "symbol":
            sym = raw or None
            name, _ = lookup_info_for_symbol(raw)
            print(f"[{i}/{total}] {raw} -> {name or '(no name found)'}")
        else:
            sym, name, _ = best_symbol_for_company(raw, max_results=args.max_results)
            print(f"[{i}/{total}] {raw!r} -> {sym or '(not found)'}")

        symbols.append(sym)
        company_names.append(name)
        yf_urls.append(f"https://finance.yahoo.com/quote/{sym}/" if sym else "")

        time.sleep(max(0.0, args.sleep))

    df[args.symbol_col_name] = symbols
    df["Company Name"] = company_names
    df["Yahoo Finance URL"] = yf_urls
    df["Source"] = args.source

    col_order = [args.symbol_col_name, "Company Name", "Yahoo Finance URL", "Source"]
    out_df = df[col_order]

    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        out_df.to_excel(writer, index=False)

    print(f"✅ Done. Wrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())