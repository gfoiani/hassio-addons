"""
XTB broker implementation using the xAPI WebSocket protocol.

Documentation: http://developers.xstore.pro/documentation/

Credentials:
    user_id  : XTB account number (numeric string)
    password : XTB account password

Account types:
    demo=True  → wss://ws.xtb.com/demo
    demo=False → wss://ws.xtb.com/real   (LIVE – real money)

Symbol naming in XTB:
    NYSE / NASDAQ stocks : AAPL.US, MSFT.US, TSLA.US, GOOGL.US …
    LSE stocks           : BP.UK,   VOD.UK,  HSBA.UK, RIO.UK …

Chart period codes (in minutes):
    1 = M1, 5 = M5, 15 = M15, 30 = M30,
    60 = H1, 240 = H4, 1440 = D1

Trade command codes:
    0 = BUY,  1 = SELL
Trade type codes:
    0 = OPEN, 2 = CLOSE
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import pandas as pd
import websocket  # websocket-client

from trading.broker.base import BrokerBase

logger = logging.getLogger("trading_bot.broker.xtb")

_DEMO_URL = "wss://ws.xtb.com/demo"
_REAL_URL = "wss://ws.xtb.com/real"

_PERIOD_MAP = {1: 1, 5: 5, 15: 15, 30: 30, 60: 60, 240: 240, 1440: 1440}

_CMD_BUY = 0
_CMD_SELL = 1
_TYPE_OPEN = 0
_TYPE_CLOSE = 2


class XTBBroker(BrokerBase):
    def __init__(self, user_id: str, password: str, demo: bool = True):
        self._user_id = user_id
        self._password = password
        self._url = _DEMO_URL if demo else _REAL_URL
        self._ws: Optional[websocket.WebSocket] = None
        self._stream_session_id: Optional[str] = None
        self._connected = False

    # ------------------------------------------------------------------
    # Low-level WebSocket helpers
    # ------------------------------------------------------------------

    def _send(self, command: str, arguments: Optional[dict] = None) -> dict:
        """Send a synchronous command and return the parsed response."""
        payload: dict = {"command": command}
        if arguments:
            payload["arguments"] = arguments

        raw = json.dumps(payload)
        logger.debug(f"→ XTB: {raw[:200]}")
        self._ws.send(raw)

        # XTB may send multiple JSON objects; read until we get the response
        response_str = self._ws.recv()
        logger.debug(f"← XTB: {response_str[:200]}")
        return json.loads(response_str)

    def _reconnect(self):
        """Re-establish connection and re-login after a disconnect."""
        logger.warning("XTB: reconnecting …")
        try:
            if self._ws:
                self._ws.close()
        except Exception:
            pass
        self._ws = None
        self._connected = False
        time.sleep(3)
        self.connect()

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        try:
            self._ws = websocket.WebSocket()
            self._ws.connect(self._url, timeout=10)

            resp = self._send(
                "login",
                {"userId": self._user_id, "password": self._password},
            )
            if not resp.get("status"):
                logger.error(f"XTB login failed: {resp.get('errorDescr', resp)}")
                return False

            self._stream_session_id = resp.get("streamSessionId")
            self._connected = True
            logger.info(f"XTB connected ({'DEMO' if self._url == _DEMO_URL else 'REAL'})")
            return True

        except Exception as exc:
            logger.error(f"XTB connection error: {exc}")
            return False

    def disconnect(self):
        try:
            if self._ws:
                self._send("logout")
                self._ws.close()
        except Exception:
            pass
        self._ws = None
        self._connected = False
        logger.info("XTB disconnected.")

    # ------------------------------------------------------------------
    # Account information
    # ------------------------------------------------------------------

    def get_account_value(self) -> float:
        resp = self._safe_send("getMarginLevel")
        data = resp.get("returnData", {})
        # equity = balance + unrealized P&L
        return float(data.get("equity", data.get("balance", 0.0)))

    def get_buying_power(self) -> float:
        resp = self._safe_send("getMarginLevel")
        data = resp.get("returnData", {})
        return float(data.get("freeMargin", 0.0))

    def _safe_send(self, command: str, arguments: Optional[dict] = None) -> dict:
        """Send with automatic reconnect on failure."""
        try:
            return self._send(command, arguments)
        except Exception as exc:
            logger.warning(f"XTB send error ({exc}), reconnecting …")
            self._reconnect()
            return self._send(command, arguments)

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    def get_bars(
        self,
        symbol: str,
        timeframe_minutes: int = 1,
        limit: int = 100,
    ) -> pd.DataFrame:
        """
        Fetch OHLCV bars from XTB using getChartLastRequest.
        Returns a DataFrame with columns: open, high, low, close, volume.
        """
        period = _PERIOD_MAP.get(timeframe_minutes, timeframe_minutes)
        # XTB expects a Unix timestamp in milliseconds
        start_ms = int(
            (datetime.now(timezone.utc) - timedelta(minutes=timeframe_minutes * limit * 2)).timestamp()
            * 1000
        )

        resp = self._safe_send(
            "getChartLastRequest",
            {
                "info": {
                    "period": period,
                    "start": start_ms,
                    "symbol": symbol,
                }
            },
        )

        if not resp.get("status"):
            logger.error(f"get_bars failed for {symbol}: {resp.get('errorDescr')}")
            return pd.DataFrame()

        candles = resp.get("returnData", {}).get("rateInfos", [])
        if not candles:
            return pd.DataFrame()

        digits = resp.get("returnData", {}).get("digits", 5)
        factor = 10 ** digits

        rows = []
        for c in candles[-limit:]:
            open_ = c["open"] / factor
            rows.append(
                {
                    "timestamp": pd.Timestamp(c["ctm"], unit="ms", tz="UTC"),
                    "open": open_,
                    "high": open_ + c["high"] / factor,
                    "low": open_ + c["low"] / factor,
                    "close": open_ + c["close"] / factor,
                    "volume": c.get("vol", 0.0),
                }
            )

        df = pd.DataFrame(rows).set_index("timestamp")
        return df

    def get_quote(self, symbol: str) -> Optional[float]:
        """Return mid-price from the latest tick."""
        resp = self._safe_send(
            "getTickPrices",
            {
                "level": 0,
                "symbols": [symbol],
                "timestamp": int(time.time() * 1000) - 5000,
            },
        )
        if not resp.get("status"):
            logger.error(f"get_quote failed for {symbol}: {resp.get('errorDescr')}")
            return None

        ticks = resp.get("returnData", {}).get("quotations", [])
        if not ticks:
            return None

        tick = ticks[0]
        ask = tick.get("ask", 0.0)
        bid = tick.get("bid", 0.0)
        return (ask + bid) / 2.0 if ask and bid else ask or bid

    # ------------------------------------------------------------------
    # Order execution
    # ------------------------------------------------------------------

    def _trade_transaction(
        self,
        symbol: str,
        cmd: int,
        volume: float,
        price: float,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        order: int = 0,
        trade_type: int = _TYPE_OPEN,
        custom_comment: str = "trading-bot",
    ) -> Optional[str]:
        """
        Send a tradeTransaction command.
        Returns the order number as a string, or None on failure.
        """
        resp = self._safe_send(
            "tradeTransaction",
            {
                "tradeTransInfo": {
                    "cmd": cmd,
                    "customComment": custom_comment,
                    "expiration": 0,
                    "offset": 0,
                    "order": order,
                    "price": price,
                    "sl": round(stop_loss, 5),
                    "symbol": symbol,
                    "tp": round(take_profit, 5),
                    "type": trade_type,
                    "volume": volume,
                }
            },
        )

        if not resp.get("status"):
            logger.error(
                f"tradeTransaction failed for {symbol}: {resp.get('errorDescr', resp)}"
            )
            return None

        order_id = str(resp.get("returnData", {}).get("order", ""))
        logger.info(
            f"XTB order placed: {'BUY' if cmd == _CMD_BUY else 'SELL'} {volume} {symbol} "
            f"price={price} SL={stop_loss} TP={take_profit} → order_id={order_id}"
        )
        return order_id

    def place_market_order(
        self, symbol: str, qty: float, side: str
    ) -> Optional[str]:
        cmd = _CMD_BUY if side == "buy" else _CMD_SELL
        price = self.get_quote(symbol) or 0.0
        return self._trade_transaction(symbol, cmd, qty, price)

    def place_bracket_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        stop_loss: float,
        take_profit: float,
    ) -> Optional[str]:
        cmd = _CMD_BUY if side == "buy" else _CMD_SELL
        price = self.get_quote(symbol) or 0.0
        return self._trade_transaction(
            symbol, cmd, qty, price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

    def close_position(self, symbol: str) -> bool:
        """Close the first open trade found for `symbol`."""
        trades = self._get_raw_trades()
        for t in trades:
            if t.get("symbol") == symbol:
                order_no = t.get("order")
                # Opposite command to close
                cmd = _CMD_SELL if t.get("cmd") == _CMD_BUY else _CMD_BUY
                price = self.get_quote(symbol) or 0.0
                result = self._trade_transaction(
                    symbol, cmd, t.get("volume", 0.0), price,
                    order=order_no, trade_type=_TYPE_CLOSE
                )
                return result is not None
        logger.warning(f"close_position: no open trade found for {symbol}")
        return False

    def close_all_positions(self) -> bool:
        trades = self._get_raw_trades()
        success = True
        for t in trades:
            sym = t.get("symbol", "")
            order_no = t.get("order")
            cmd = _CMD_SELL if t.get("cmd") == _CMD_BUY else _CMD_BUY
            price = self.get_quote(sym) or 0.0
            result = self._trade_transaction(
                sym, cmd, t.get("volume", 0.0), price,
                order=order_no, trade_type=_TYPE_CLOSE
            )
            if result is None:
                success = False
        return success

    # ------------------------------------------------------------------
    # Position query
    # ------------------------------------------------------------------

    def _get_raw_trades(self) -> List[dict]:
        """Return list of raw open trade dicts from XTB."""
        resp = self._safe_send("getTrades", {"openedOnly": True})
        if not resp.get("status"):
            logger.error(f"getTrades failed: {resp.get('errorDescr')}")
            return []
        return resp.get("returnData", [])

    def get_open_positions(self) -> List[dict]:
        trades = self._get_raw_trades()
        result = []
        for t in trades:
            side = "long" if t.get("cmd") == _CMD_BUY else "short"
            entry = t.get("open_price", 0.0)
            current = self.get_quote(t.get("symbol", "")) or entry
            qty = t.get("volume", 0.0)
            pnl = (current - entry) * qty if side == "long" else (entry - current) * qty
            result.append(
                {
                    "symbol": t.get("symbol", ""),
                    "qty": qty,
                    "side": side,
                    "avg_entry_price": entry,
                    "current_price": current,
                    "unrealized_pl": pnl,
                    "order_id": str(t.get("order", "")),
                    "stop_loss": t.get("sl", 0.0),
                    "take_profit": t.get("tp", 0.0),
                }
            )
        return result
