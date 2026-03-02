"""
Market data providers for the Day Trading Bot.

Primary:   Yahoo Finance v8 HTTP API (no API key required).
Fallback:  TradingView via tradingview-ta (public technical analysis data).

Symbol mapping from Directa format to each provider:
  NYSE  .AAPL  →  Yahoo: AAPL        | TradingView: NASDAQ:AAPL
  LSE   BP     →  Yahoo: BP.L        | TradingView: LSE:BP
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger("trading_bot.data")

# ── Yahoo Finance ─────────────────────────────────────────────────────────────

_YF_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; trading-bot/1.0)"}
_HTTP_TIMEOUT = 10  # seconds

# In-memory TTL caches
_bar_cache: dict[str, tuple[float, pd.DataFrame]] = {}
_quote_cache: dict[str, tuple[float, float]] = {}

_QUOTE_TTL = 20.0  # seconds – well under the default 30 s check interval

# ── TradingView ───────────────────────────────────────────────────────────────

_tv_available = True
try:
    from tradingview_ta import TA_Handler, Interval, Exchange
except ImportError:
    _tv_available = False
    logger.warning(
        "tradingview-ta not installed – TradingView fallback disabled. "
        "Install with: pip install tradingview-ta"
    )

# TradingView quote cache (same TTL as Yahoo)
_tv_quote_cache: dict[str, tuple[float, float]] = {}

# NYSE symbols that are actually listed on NASDAQ
_NASDAQ_SYMBOLS = {"AAPL", "MSFT", "NVDA", "GOOG", "GOOGL", "AMZN", "META", "TSLA", "NFLX"}


# ── Symbol conversion ─────────────────────────────────────────────────────────


def _to_yf_symbol(directa_symbol: str) -> str:
    """Convert a Directa symbol to a Yahoo Finance ticker.

    Directa NYSE: .AAPL, .MSFT  →  Yahoo: AAPL, MSFT  (strip leading dot)
    Directa LSE:  BP, SHEL      →  Yahoo: BP.L, SHEL.L  (append .L)
    """
    if directa_symbol.startswith("."):
        return directa_symbol[1:]
    return directa_symbol + ".L"


def _to_tv_info(directa_symbol: str) -> tuple[str, str, str]:
    """Convert a Directa symbol to TradingView (symbol, exchange, screener).

    Returns (symbol, exchange, screener) tuple for TA_Handler.
    """
    if directa_symbol.startswith("."):
        ticker = directa_symbol[1:]
        if ticker in _NASDAQ_SYMBOLS:
            return ticker, "NASDAQ", "america"
        return ticker, "NYSE", "america"
    # LSE symbols
    return directa_symbol, "LSE", "united_kingdom"


# ── Yahoo Finance bars ────────────────────────────────────────────────────────


def _yf_interval(timeframe_minutes: int) -> str:
    mapping = {1: "1m", 2: "2m", 5: "5m", 15: "15m", 30: "30m", 60: "60m"}
    return mapping.get(timeframe_minutes, "1m")


def _yf_range(timeframe_minutes: int) -> str:
    # Yahoo Finance intraday limits: 1 m → max 7 days, others → max 60 days
    return "5d" if timeframe_minutes <= 1 else "60d"


def get_bars(
    directa_symbol: str,
    timeframe_minutes: int = 5,
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


# ── Quote (price) retrieval ───────────────────────────────────────────────────


def get_quote(directa_symbol: str) -> Optional[float]:
    """Return the latest price for *directa_symbol*.

    Tries Yahoo Finance first, then TradingView as fallback.
    Returns None if the price cannot be determined.
    """
    # 1. Try Yahoo Finance
    price = _yf_get_quote(directa_symbol)
    if price is not None:
        return price

    # 2. Fallback: TradingView
    price = _tv_get_quote(directa_symbol)
    if price is not None:
        return price

    return None


def _yf_get_quote(directa_symbol: str) -> Optional[float]:
    """Yahoo Finance quote (primary)."""
    now = time.monotonic()
    cache_key = f"yf:{directa_symbol}"
    if cache_key in _quote_cache:
        ts, price = _quote_cache[cache_key]
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
        _quote_cache[cache_key] = (now, price)
        logger.debug("Yahoo Finance: quote %s = %.4f", yf_sym, price)
        return price

    except Exception as exc:
        logger.error("Yahoo Finance get_quote failed for %s: %s", yf_sym, exc)
        return None


def _tv_get_quote(directa_symbol: str) -> Optional[float]:
    """TradingView quote (fallback)."""
    if not _tv_available:
        return None

    now = time.monotonic()
    cache_key = f"tv:{directa_symbol}"
    if cache_key in _tv_quote_cache:
        ts, price = _tv_quote_cache[cache_key]
        if now - ts < _QUOTE_TTL:
            return price

    ticker, exchange, screener = _to_tv_info(directa_symbol)
    try:
        handler = TA_Handler(
            symbol=ticker,
            exchange=exchange,
            screener=screener,
            interval=Interval.INTERVAL_5_MINUTES,
        )
        analysis = handler.get_analysis()
        price = analysis.indicators.get("close")

        if price is not None and float(price) > 0:
            price = float(price)
            _tv_quote_cache[cache_key] = (now, price)
            logger.debug("TradingView: quote %s:%s = %.4f", exchange, ticker, price)
            return price

    except Exception as exc:
        logger.warning("TradingView get_quote failed for %s:%s: %s", exchange, ticker, exc)

    return None


# ── Volume retrieval (TradingView) ────────────────────────────────────────────


def get_tv_volume(directa_symbol: str) -> Optional[float]:
    """Return the current trading volume from TradingView.

    TradingView provides more reliable volume data for LSE stocks than Yahoo
    Finance's 1-min bars.  Returns None if unavailable.
    """
    if not _tv_available:
        return None

    ticker, exchange, screener = _to_tv_info(directa_symbol)
    try:
        handler = TA_Handler(
            symbol=ticker,
            exchange=exchange,
            screener=screener,
            interval=Interval.INTERVAL_5_MINUTES,
        )
        analysis = handler.get_analysis()
        volume = analysis.indicators.get("volume")

        if volume is not None and float(volume) >= 0:
            logger.debug("TradingView: volume %s:%s = %.0f", exchange, ticker, float(volume))
            return float(volume)

    except Exception as exc:
        logger.warning("TradingView get_volume failed for %s:%s: %s", exchange, ticker, exc)

    return None
