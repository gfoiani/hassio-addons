"""
Binance Spot broker using the python-binance client.

Supports:
  - Binance Spot (real) and Binance Testnet (paper trading)
  - Market BUY entry
  - OCO SELL order for bracket SL + TP (native Binance feature)
  - Position monitoring: detects when OCO fires (SL or TP hit)
  - Manual close: cancels OCO + market SELL
"""

from __future__ import annotations

import logging
import math
from typing import Dict, Optional

import pandas as pd
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException

from trading.broker.base import BrokerBase

logger = logging.getLogger("crypto_bot.broker")

# Binance kline interval strings mapped from minutes
_INTERVAL_MAP = {
    1:   Client.KLINE_INTERVAL_1MINUTE,
    3:   Client.KLINE_INTERVAL_3MINUTE,
    5:   Client.KLINE_INTERVAL_5MINUTE,
    15:  Client.KLINE_INTERVAL_15MINUTE,
    30:  Client.KLINE_INTERVAL_30MINUTE,
    60:  Client.KLINE_INTERVAL_1HOUR,
    120: Client.KLINE_INTERVAL_2HOUR,
    240: Client.KLINE_INTERVAL_4HOUR,
}


class BinanceBroker(BrokerBase):
    """
    Binance Spot broker.

    OCO orders are used to set both SL and TP at entry:
      - STOP_LOSS_LIMIT leg: triggers if price falls to stop_loss
      - LIMIT_MAKER leg: fills at take_profit
    If either leg fills, the other is cancelled automatically by Binance.
    """

    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        self._api_key = api_key
        self._api_secret = api_secret
        self._testnet = testnet
        self._client: Optional[Client] = None
        # Cache symbol filters to avoid repeated API calls
        self._symbol_filters: Dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        try:
            self._client = Client(
                self._api_key,
                self._api_secret,
                testnet=self._testnet,
            )
            self._client.ping()
            server_time = self._client.get_server_time()
            mode = "TESTNET" if self._testnet else "LIVE ⚠️"
            logger.info(f"Connected to Binance ({mode}) — server time: {server_time['serverTime']}")
            return True
        except Exception as exc:
            logger.error(f"Failed to connect to Binance: {exc}")
            return False

    def disconnect(self) -> None:
        self._client = None
        logger.info("Disconnected from Binance.")

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    # Stablecoins counted at face value (1:1 with USD)
    _STABLECOINS = {"USDT", "USDC", "BUSD", "FDUSD", "TUSD"}

    def get_account_value(self) -> float:
        """Total stable-coin value + crypto holdings converted to USDT."""
        account = self._client.get_account()
        total = 0.0
        for asset in account["balances"]:
            free = float(asset["free"])
            locked = float(asset["locked"])
            amount = free + locked
            if amount == 0:
                continue
            if asset["asset"] in self._STABLECOINS:
                total += amount
            else:
                for quote in ("USDT", "USDC"):
                    try:
                        price = float(self._client.get_symbol_ticker(
                            symbol=asset["asset"] + quote)["price"])
                        total += amount * price
                        break
                    except Exception:
                        continue
        return total

    def get_buying_power(self) -> float:
        """Free stable-coin balance available for new orders."""
        account = self._client.get_account()
        total = 0.0
        for asset in account["balances"]:
            if asset["asset"] in self._STABLECOINS:
                total += float(asset["free"])
        return total

    # ------------------------------------------------------------------
    # Symbol info & filters
    # ------------------------------------------------------------------

    def get_symbol_info(self, symbol: str) -> dict:
        """Return parsed filters (stepSize, tickSize, minQty, minNotional)."""
        if symbol in self._symbol_filters:
            return self._symbol_filters[symbol]

        info = self._client.get_symbol_info(symbol)
        if info is None:
            raise ValueError(f"Symbol {symbol} not found on Binance")

        filters = {f["filterType"]: f for f in info["filters"]}
        parsed = {
            "step_size": float(filters["LOT_SIZE"]["stepSize"]),
            "min_qty": float(filters["LOT_SIZE"]["minQty"]),
            "tick_size": float(filters["PRICE_FILTER"]["tickSize"]),
            "min_notional": float(filters.get("MIN_NOTIONAL", {}).get("minNotional", 10.0)),
        }
        self._symbol_filters[symbol] = parsed
        return parsed

    def _round_qty(self, qty: float, step_size: float) -> float:
        precision = max(0, -int(math.floor(math.log10(step_size))))
        return round(math.floor(qty / step_size) * step_size, precision)

    def _round_price(self, price: float, tick_size: float) -> float:
        precision = max(0, -int(math.floor(math.log10(tick_size))))
        return round(round(price / tick_size) * tick_size, precision)

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    def get_bars(self, symbol: str, timeframe_minutes: int, limit: int = 50) -> pd.DataFrame:
        interval = _INTERVAL_MAP.get(timeframe_minutes)
        if interval is None:
            raise ValueError(f"Unsupported timeframe: {timeframe_minutes}m")

        klines = self._client.get_klines(symbol=symbol, interval=interval, limit=limit)
        if not klines:
            return pd.DataFrame()

        df = pd.DataFrame(klines, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "num_trades",
            "taker_buy_base", "taker_buy_quote", "ignore",
        ])
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = df[col].astype(float)
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        return df[["open_time", "open", "high", "low", "close", "volume"]]

    def get_quote(self, symbol: str) -> Optional[float]:
        try:
            ticker = self._client.get_symbol_ticker(symbol=symbol)
            return float(ticker["price"])
        except Exception as exc:
            logger.warning(f"Could not get quote for {symbol}: {exc}")
            return None

    # ------------------------------------------------------------------
    # Order placement
    # ------------------------------------------------------------------

    def place_bracket_order(
        self,
        symbol: str,
        qty: float,
        stop_loss: float,
        take_profit: float,
    ) -> Optional[dict]:
        """
        1. Market BUY `qty` of `symbol`
        2. OCO SELL: STOP_LOSS_LIMIT at `stop_loss` + LIMIT at `take_profit`

        Returns { "order_id": str, "oco_order_list_id": str, "fill_price": float }
        or None on any failure.
        """
        filters = self.get_symbol_info(symbol)
        tick_size = filters["tick_size"]
        step_size = filters["step_size"]

        qty = self._round_qty(qty, step_size)
        if qty < filters["min_qty"]:
            logger.warning(f"{symbol}: qty {qty} below minQty {filters['min_qty']}")
            return None

        # --- Step 1: Market BUY ---
        try:
            buy_order = self._client.order_market_buy(
                symbol=symbol,
                quantity=qty,
            )
            order_id = str(buy_order["orderId"])
            # Compute actual fill price from fills
            fills = buy_order.get("fills", [])
            if fills:
                total_qty = sum(float(f["qty"]) for f in fills)
                fill_price = sum(float(f["price"]) * float(f["qty"]) for f in fills) / total_qty
            else:
                fill_price = float(buy_order.get("price", 0)) or self.get_quote(symbol) or 0.0
            logger.info(f"{symbol}: market BUY {qty} filled @ {fill_price:.6f}")
        except (BinanceAPIException, BinanceOrderException) as exc:
            logger.error(f"{symbol}: market BUY failed: {exc}")
            return None

        # Re-fetch actual filled quantity (may differ slightly from requested)
        try:
            order_detail = self._client.get_order(symbol=symbol, orderId=buy_order["orderId"])
            executed_qty = float(order_detail.get("executedQty", qty))
            if executed_qty > 0:
                qty = self._round_qty(executed_qty, step_size)
        except Exception:
            pass

        # --- Step 2: OCO SELL (SL + TP) ---
        sl_price = self._round_price(stop_loss, tick_size)
        # For STOP_LOSS_LIMIT, stop_price must be slightly above limit_price
        sl_limit_price = self._round_price(stop_loss * 0.999, tick_size)
        tp_price = self._round_price(take_profit, tick_size)

        try:
            oco = self._client.create_oco_order(
                symbol=symbol,
                side=Client.SIDE_SELL,
                quantity=qty,
                price=str(tp_price),           # LIMIT leg (take profit)
                stopPrice=str(sl_price),       # stop trigger
                stopLimitPrice=str(sl_limit_price),  # limit price after stop triggers
                stopLimitTimeInForce=Client.TIME_IN_FORCE_GTC,
            )
            oco_id = str(oco["orderListId"])
            logger.info(
                f"{symbol}: OCO placed — TP={tp_price} SL={sl_price} "
                f"OCO_ID={oco_id}"
            )
            return {
                "order_id": order_id,
                "oco_order_list_id": oco_id,
                "fill_price": fill_price,
            }
        except (BinanceAPIException, BinanceOrderException) as exc:
            logger.error(f"{symbol}: OCO order failed: {exc}")
            # BUY already executed — attempt emergency close
            logger.warning(f"{symbol}: attempting emergency market sell after OCO failure")
            self._emergency_sell(symbol, qty)
            return None

    def _emergency_sell(self, symbol: str, qty: float):
        try:
            self._client.order_market_sell(symbol=symbol, quantity=qty)
            logger.info(f"{symbol}: emergency market sell executed for {qty}")
        except Exception as exc:
            logger.error(f"{symbol}: emergency sell FAILED: {exc}. Manual intervention needed!")

    # ------------------------------------------------------------------
    # Position management
    # ------------------------------------------------------------------

    def has_pending_oco(self, symbol: str, oco_order_list_id: str) -> bool:
        """
        Returns True if the OCO is still EXECUTING (position still open).
        Returns False if OCO was ALL_DONE or not found (triggered).
        """
        try:
            oco = self._client.get_orderlist(orderListId=int(oco_order_list_id))
            return oco.get("listStatusType") == "EXECUTING"
        except Exception as exc:
            logger.debug(f"has_pending_oco error for {symbol} OCO {oco_order_list_id}: {exc}")
            return False

    def close_position(
        self, symbol: str, qty: float, oco_order_list_id: Optional[str]
    ) -> bool:
        """Cancel OCO (if still open) then market-sell to close position."""
        # Cancel OCO
        if oco_order_list_id:
            try:
                self._client.cancel_orderlist(symbol=symbol, orderListId=int(oco_order_list_id))
                logger.info(f"{symbol}: OCO {oco_order_list_id} cancelled")
            except BinanceAPIException as exc:
                # OCO may have already been triggered — non-fatal
                logger.debug(f"{symbol}: OCO cancel response: {exc}")

        # Market SELL
        try:
            filters = self.get_symbol_info(symbol)
            qty = self._round_qty(qty, filters["step_size"])
            self._client.order_market_sell(symbol=symbol, quantity=qty)
            logger.info(f"{symbol}: market SELL {qty} executed (position closed)")
            return True
        except (BinanceAPIException, BinanceOrderException) as exc:
            logger.error(f"{symbol}: market SELL failed: {exc}")
            return False
