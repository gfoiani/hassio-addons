"""
Trading strategies.

- ORBStrategy   : Opening Range Breakout (primary for day trading)
- MomentumStrategy : EMA crossover + RSI (secondary)
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Optional

import pandas as pd

from trading.position import PositionSide

logger = logging.getLogger("trading_bot.strategy")


class Signal(str, Enum):
    LONG = "long"
    SHORT = "short"
    NONE = "none"


# ---------------------------------------------------------------------------
# Opening Range Breakout
# ---------------------------------------------------------------------------

class ORBStrategy:
    """
    Opening Range Breakout strategy.

    Phase 1 – ORB collection (first `orb_minutes` after open):
        Track the highest high and lowest low of every candle.

    Phase 2 – Signal detection (after ORB window):
        LONG  if price closes above ORB high AND volume > avg_volume * multiplier
        SHORT if price closes below ORB low  AND volume > avg_volume * multiplier

    Stop loss is placed at the opposite ORB boundary (with a small buffer).
    Take profit is delegated to RiskManager (percentage-based).
    """

    def __init__(self, orb_minutes: int = 15, volume_multiplier: float = 1.5):
        self.orb_minutes = orb_minutes
        self.volume_multiplier = volume_multiplier

        self._orb_high: dict[str, float] = {}
        self._orb_low: dict[str, float] = {}
        self._established: set[str] = set()

    # ------------------------------------------------------------------
    # ORB setup
    # ------------------------------------------------------------------

    def update_orb(self, symbol: str, high: float, low: float):
        """
        Feed a single candle's high/low during the ORB window.
        Call this for every candle received while is_orb_window() is True.
        """
        if symbol not in self._orb_high:
            self._orb_high[symbol] = high
            self._orb_low[symbol] = low
        else:
            self._orb_high[symbol] = max(self._orb_high[symbol], high)
            self._orb_low[symbol] = min(self._orb_low[symbol], low)

    def set_orb_from_bars(self, symbol: str, bars: pd.DataFrame):
        """
        Initialise ORB from a DataFrame of OHLCV bars
        (e.g. fetched at the end of the ORB window).
        `bars` must contain 'high' and 'low' columns.
        """
        if bars is None or bars.empty:
            logger.warning(f"{symbol}: no bars to build ORB from")
            return
        self._orb_high[symbol] = float(bars["high"].max())
        self._orb_low[symbol] = float(bars["low"].min())
        self._established.add(symbol)
        logger.info(
            f"{symbol} ORB established → Low={self._orb_low[symbol]:.4f}  "
            f"High={self._orb_high[symbol]:.4f}"
        )

    def finalize_orb(self, symbol: str):
        """Mark ORB as ready for signal detection."""
        if symbol in self._orb_high:
            self._established.add(symbol)
            logger.info(
                f"{symbol} ORB finalised → Low={self._orb_low[symbol]:.4f}  "
                f"High={self._orb_high[symbol]:.4f}"
            )

    def orb_high(self, symbol: str) -> Optional[float]:
        return self._orb_high.get(symbol)

    def orb_low(self, symbol: str) -> Optional[float]:
        return self._orb_low.get(symbol)

    def is_established(self, symbol: str) -> bool:
        return symbol in self._established

    # ------------------------------------------------------------------
    # Signal detection
    # ------------------------------------------------------------------

    def check_signal(
        self,
        symbol: str,
        current_price: float,
        current_volume: float = 0.0,
        avg_volume: float = 0.0,
    ) -> Signal:
        """
        Return a Signal based on whether the price has broken out of the ORB.
        Volume filter is skipped when avg_volume == 0.
        """
        if symbol not in self._established:
            return Signal.NONE

        high = self._orb_high.get(symbol)
        low = self._orb_low.get(symbol)
        if high is None or low is None:
            return Signal.NONE

        volume_ok = avg_volume == 0 or current_volume >= avg_volume * self.volume_multiplier

        if current_price > high and volume_ok:
            logger.info(
                f"{symbol} LONG signal: price {current_price:.4f} > ORB high {high:.4f}"
            )
            return Signal.LONG

        if current_price < low and volume_ok:
            logger.info(
                f"{symbol} SHORT signal: price {current_price:.4f} < ORB low {low:.4f}"
            )
            return Signal.SHORT

        return Signal.NONE

    # ------------------------------------------------------------------
    # Stop loss helper
    # ------------------------------------------------------------------

    def orb_stop_loss(self, symbol: str, side: PositionSide, buffer: float = 0.001) -> Optional[float]:
        """Return stop loss at the opposite ORB boundary + buffer."""
        if side == PositionSide.LONG:
            low = self._orb_low.get(symbol)
            return round(low * (1.0 - buffer), 4) if low else None
        high = self._orb_high.get(symbol)
        return round(high * (1.0 + buffer), 4) if high else None

    # ------------------------------------------------------------------
    # Daily reset
    # ------------------------------------------------------------------

    def reset_symbol(self, symbol: str):
        self._orb_high.pop(symbol, None)
        self._orb_low.pop(symbol, None)
        self._established.discard(symbol)

    def reset_all(self):
        self._orb_high.clear()
        self._orb_low.clear()
        self._established.clear()


# ---------------------------------------------------------------------------
# Momentum (EMA crossover + RSI)
# ---------------------------------------------------------------------------

class MomentumStrategy:
    """
    Simple momentum strategy.

    LONG  when EMA-9 crosses above EMA-21 AND RSI is between 40 and 65.
    SHORT when EMA-9 crosses below EMA-21 AND RSI is between 35 and 60.

    At least 25 bars required.
    """

    def check_signal(self, symbol: str, bars: pd.DataFrame) -> Signal:
        if bars is None or len(bars) < 25:
            logger.debug(f"{symbol}: not enough bars for momentum signal ({len(bars) if bars is not None else 0})")
            return Signal.NONE

        df = bars.copy()
        df["ema9"] = df["close"].ewm(span=9, adjust=False).mean()
        df["ema21"] = df["close"].ewm(span=21, adjust=False).mean()

        # RSI
        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(com=13, adjust=False).mean()
        avg_loss = loss.ewm(com=13, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, float("nan"))
        df["rsi"] = 100 - (100 / (1 + rs))

        last = df.iloc[-1]
        prev = df.iloc[-2]

        if (
            prev["ema9"] <= prev["ema21"]
            and last["ema9"] > last["ema21"]
            and 40 < last["rsi"] < 65
        ):
            logger.info(f"{symbol} Momentum LONG: EMA cross ↑, RSI={last['rsi']:.1f}")
            return Signal.LONG

        if (
            prev["ema9"] >= prev["ema21"]
            and last["ema9"] < last["ema21"]
            and 35 < last["rsi"] < 60
        ):
            logger.info(f"{symbol} Momentum SHORT: EMA cross ↓, RSI={last['rsi']:.1f}")
            return Signal.SHORT

        return Signal.NONE


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_strategy(name: str, **kwargs):
    if name == "orb":
        return ORBStrategy(
            orb_minutes=kwargs.get("orb_minutes", 15),
            volume_multiplier=kwargs.get("volume_multiplier", 1.5),
        )
    if name == "momentum":
        return MomentumStrategy()
    raise ValueError(f"Unknown strategy: '{name}'. Choose 'orb' or 'momentum'.")
