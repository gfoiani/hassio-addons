"""
Abstract broker interface for crypto trading.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional

import pandas as pd


class BrokerBase(ABC):

    @abstractmethod
    def connect(self) -> bool:
        """Connect to the exchange. Returns True on success."""

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect and clean up."""

    @abstractmethod
    def get_account_value(self) -> float:
        """Return total portfolio value in USDT (balance + open positions)."""

    @abstractmethod
    def get_buying_power(self) -> float:
        """Return available USDT balance."""

    @abstractmethod
    def get_symbol_info(self, symbol: str) -> dict:
        """Return exchange info for a symbol (stepSize, tickSize, minQty, etc.)."""

    @abstractmethod
    def get_bars(self, symbol: str, timeframe_minutes: int, limit: int = 50) -> pd.DataFrame:
        """
        Return OHLCV candlestick data as a DataFrame with columns:
        open_time, open, high, low, close, volume
        """

    @abstractmethod
    def get_quote(self, symbol: str) -> Optional[float]:
        """Return the current market price for a symbol."""

    @abstractmethod
    def place_bracket_order(
        self,
        symbol: str,
        qty: float,
        stop_loss: float,
        take_profit: float,
    ) -> Optional[dict]:
        """
        Place a market BUY order followed by an OCO SELL order (SL + TP).

        Returns a dict with:
          { "order_id": str, "oco_order_list_id": str, "fill_price": float }
        or None on failure.
        """

    @abstractmethod
    def close_position(self, symbol: str, qty: float, oco_order_list_id: Optional[str]) -> bool:
        """
        Cancel pending OCO and place a market SELL to close the position.
        Returns True on success.
        """

    @abstractmethod
    def has_pending_oco(self, symbol: str, oco_order_list_id: str) -> bool:
        """
        Check whether the OCO order is still open (position not yet closed by SL/TP).
        Returns False if the OCO was triggered (position closed server-side).
        """
