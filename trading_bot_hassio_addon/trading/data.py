"""
Yahoo Finance HTTP market data provider.

Replaces the yfinance library with direct HTTP calls to the Yahoo Finance v8
chart API, eliminating C-extension dependencies (lxml, frozendict, peewee)
that cause compilation failures on Alpine ARM containers.  Uses only
`requests`, which is already a direct dependency of the bot.

Used as fallback when Directa Darwin's paid data ports (10001 DATAFEED,
10003 HISTORICAL) are not available or return no data.

Symbol mapping from Directa format to Yahoo Finance tickers:
  NYSE  .AAPL  →  AAPL        (strip leading dot)
  LSE   BP     →  BP.L        (append London suffix)
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger("trading_bot.data")

_YF_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; trading-bot/1.0)"}
_HTTP_TIMEOUT = 10  # seconds

# In-memory TTL caches
_bar_cache: dict[str, tuple[float, pd.DataFrame]] = {}
_quote_cache: dict[str, tuple[float, float]] = {}

_QUOTE_TTL = 20.0  # seconds – well under the default 30 s check interval


def _to_yf_symbol(directa_symbol: str) -> str:
    """Convert a Directa symbol to a Yahoo Finance ticker.

    Directa NYSE: .AAPL, .MSFT  →  Yahoo: AAPL, MSFT  (strip leading dot)
    Directa LSE:  BP, SHEL      →  Yahoo: BP.L, SHEL.L  (append .L)
    """
    if directa_symbol.startswith("."):
        return directa_symbol[1:]
    return directa_symbol + ".L"


def _yf_interval(timeframe_minutes: int) -> str:
    mapping = {1: "1m", 2: "2m", 5: "5m", 15: "15m", 30: "30m", 60: "60m"}
    return mapping.get(timeframe_minutes, "1m")


def _yf_range(timeframe_minutes: int) -> str:
    # Yahoo Finance intraday limits: 1 m → max 7 days, others → max 60 days
    return "5d" if timeframe_minutes <= 1 else "60d"


def get_bars(
    directa_symbol: str,
    timeframe_minutes: int = 1,
    limit: int = 100,
) -> pd.DataFrame:
    """Fetch OHLCV bars from Yahoo Finance v8 API with in-memory caching.

    Returns a DataFrame with columns [open, high, low, close, volume] and a
    UTC DatetimeIndex.  Returns an empty DataFrame on error.
    """
    cache_key = f"{directa_symbol}:{timeframe_minutes}:{limit}"
    now = time.monotonic()

    # TTL: half a bar period, minimum 60 s
    ttl = max(timeframe_minutes * 30, 60)
    if cache_key in _bar_cache:
        ts, df = _bar_cache[cache_key]
        if now - ts < ttl:
            return df

    yf_sym = _to_yf_symbol(directa_symbol)
    interval = _yf_interval(timeframe_minutes)
    try:
        resp = requests.get(
            _YF_URL.format(symbol=yf_sym),
            params={"interval": interval, "range": _yf_range(timeframe_minutes)},
            headers=_HEADERS,
            timeout=_HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        result = data.get("chart", {}).get("result") or []
        if not result:
            logger.warning(
                "Yahoo Finance: no bars returned for %s (interval=%s)", yf_sym, interval
            )
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        chart = result[0]
        timestamps = chart.get("timestamp", [])
        quote = chart.get("indicators", {}).get("quote", [{}])[0]

        df = pd.DataFrame(
            {
                "open":   quote.get("open", []),
                "high":   quote.get("high", []),
                "low":    quote.get("low", []),
                "close":  quote.get("close", []),
                "volume": quote.get("volume", []),
            },
            index=pd.to_datetime(timestamps, unit="s", utc=True),
        ).dropna(subset=["close"]).tail(limit)

        _bar_cache[cache_key] = (now, df)
        logger.debug(
            "Yahoo Finance: fetched %d bars for %s (interval=%s)", len(df), yf_sym, interval
        )
        return df

    except Exception as exc:
        logger.error("get_bars failed for %s: %s", yf_sym, exc)
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])


def get_quote(directa_symbol: str) -> Optional[float]:
    """Return the latest price for *directa_symbol* via Yahoo Finance v8 API.

    Returns None if the price cannot be determined.
    """
    now = time.monotonic()
    if directa_symbol in _quote_cache:
        ts, price = _quote_cache[directa_symbol]
        if now - ts < _QUOTE_TTL:
            return price

    yf_sym = _to_yf_symbol(directa_symbol)
    try:
        resp = requests.get(
            _YF_URL.format(symbol=yf_sym),
            params={"interval": "1m", "range": "1d"},
            headers=_HEADERS,
            timeout=_HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        result = data.get("chart", {}).get("result") or []
        if not result:
            return None

        price = result[0].get("meta", {}).get("regularMarketPrice")
        if not price or float(price) <= 0:
            return None

        price = float(price)
        _quote_cache[directa_symbol] = (now, price)
        logger.debug("Yahoo Finance: quote %s = %.4f", yf_sym, price)
        return price

    except Exception as exc:
        logger.error("get_quote failed for %s: %s", yf_sym, exc)
        return None
