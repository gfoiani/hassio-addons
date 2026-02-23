"""
Momentum strategy for crypto spot trading.

Only LONG signals are generated (spot = buy/sell only, no shorting).

Entry conditions:
  - EMA-9 crosses above EMA-21 (bullish momentum)
  - RSI is between 40 and 70 (not overbought, not oversold)
  - Minimum 25 bars required for reliable EMA calculation

Exit is managed via Binance OCO orders (SL + TP placed at entry time).
"""

from __future__ import annotations

import logging
from enum import Enum

import pandas as pd

logger = logging.getLogger("crypto_bot.strategy")

MIN_BARS = 25


class Signal(str, Enum):
    LONG = "long"
    NONE = "none"


class MomentumStrategy:
    """
    EMA-9 / EMA-21 crossover with RSI filter.

    Generates LONG signals only (crypto spot, no short).
    """

    def check_signal(self, symbol: str, bars: pd.DataFrame) -> Signal:
        if bars is None or len(bars) < MIN_BARS:
            logger.debug(
                f"{symbol}: not enough bars ({len(bars) if bars is not None else 0}/{MIN_BARS})"
            )
            return Signal.NONE

        df = bars.copy()
        df["ema9"] = df["close"].ewm(span=9, adjust=False).mean()
        df["ema21"] = df["close"].ewm(span=21, adjust=False).mean()

        # RSI (Wilder's smoothing via ewm com=13)
        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(com=13, adjust=False).mean()
        avg_loss = loss.ewm(com=13, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, float("nan"))
        df["rsi"] = 100 - (100 / (1 + rs))

        last = df.iloc[-1]
        prev = df.iloc[-2]

        # Bullish EMA crossover + RSI in healthy range
        if (
            prev["ema9"] <= prev["ema21"]
            and last["ema9"] > last["ema21"]
            and 40 < last["rsi"] < 70
        ):
            logger.info(
                f"{symbol} LONG signal: EMA9 ({last['ema9']:.4f}) crossed above "
                f"EMA21 ({last['ema21']:.4f}), RSI={last['rsi']:.1f}"
            )
            return Signal.LONG

        return Signal.NONE
