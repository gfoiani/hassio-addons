"""
Abstract broker interface.

All broker implementations must subclass BrokerBase and implement
every abstract method. This keeps the bot logic broker-agnostic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

import pandas as pd


class BrokerBase(ABC):

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to the broker. Return True on success."""
        ...

    @abstractmethod
    def disconnect(self):
        """Cleanly close the connection."""
        ...

    # ------------------------------------------------------------------
    # Account information
    # ------------------------------------------------------------------

    @abstractmethod
    def get_account_value(self) -> float:
        """Return total account equity in account currency."""
        ...

    @abstractmethod
    def get_buying_power(self) -> float:
        """Return available capital for new positions."""
        ...

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    @abstractmethod
    def get_bars(
        self,
        symbol: str,
        timeframe_minutes: int = 1,
        limit: int = 100,
    ) -> pd.DataFrame:
        """
        Return OHLCV bars as a DataFrame with columns:
            open, high, low, close, volume
        Index should be a DatetimeTZAware index (UTC preferred).
        """
        ...

    @abstractmethod
    def get_quote(self, symbol: str) -> Optional[float]:
        """Return the current mid-price for `symbol`, or None on failure."""
        ...

    # ------------------------------------------------------------------
    # Order execution
    # ------------------------------------------------------------------

    @abstractmethod
    def place_market_order(
        self,
        symbol: str,
        qty: float,
        side: str,                     # "buy" | "sell"
    ) -> Optional[str]:
        """
        Place a market order. Return the broker order ID on success,
        or None on failure.
        """
        ...

    @abstractmethod
    def place_bracket_order(
        self,
        symbol: str,
        qty: float,
        side: str,                     # "buy" | "sell"
        stop_loss: float,
        take_profit: float,
    ) -> Optional[str]:
        """
        Place a market order with attached stop-loss and take-profit levels.
        Return the broker order ID on success, or None on failure.

        NOTE: XTB attaches SL/TP at order creation.
              Alpaca uses bracket orders.
        """
        ...

    @abstractmethod
    def close_position(self, symbol: str) -> bool:
        """Close the open position for `symbol` at market. Return True on success."""
        ...

    @abstractmethod
    def close_all_positions(self) -> bool:
        """Close all open positions at market. Return True on success."""
        ...

    # ------------------------------------------------------------------
    # Broker capabilities
    # ------------------------------------------------------------------

    @property
    def long_only(self) -> bool:
        """Return True if this broker only supports long positions.

        Real-share brokers (e.g. Directa) do not allow naked short selling.
        CFD brokers (e.g. XTB) support both LONG and SHORT.
        Subclasses override this to return True when shorting is unavailable.
        """
        return False

    # ------------------------------------------------------------------
    # Position query
    # ------------------------------------------------------------------

    @abstractmethod
    def get_open_positions(self) -> List[dict]:
        """
        Return a list of open positions. Each dict must contain at minimum:
            symbol, qty, side ("long"|"short"), avg_entry_price,
            current_price, unrealized_pl
        """
        ...
