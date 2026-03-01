"""
Directa SIM broker implementation.

Uses the Darwin TCP socket API (Darwin CommandLine / Darwin trading platform).
Darwin CommandLine (DCL.jar) must be running on the host machine before the
bot starts.

Download DCL:  https://app1.directatrading.com/dcl/RilascioDCL/DCL.jar
Launch:        java -jar DCL.jar <userId> <password>
Test environ:  java -jar DCL.jar <userId> <password> -test

Protocol  – three TCP sockets on localhost (or configurable host):
  Port 10002  TRADING   – orders, positions, account information
  Port 10003  HISTORICAL – candle / tick-by-tick data
  Port 10001  DATAFEED  – real-time price subscriptions

Commands are UTF-8 strings terminated with '\\n'.
Responses are semicolon-delimited strings, one per line.
The server emits a standalone 'H\\n' heartbeat every 10 seconds (ignored here).

Notes:
  - US stocks (NYSE/NASDAQ) use '.' prefix: .AAPL, .MSFT, .TSLA
  - Italian stocks use plain ticker: ENI, FCA, ENEL
  - LSE stocks use plain ticker: BP, VOD (verify exact name in Darwin)
  - When directa_host=127.0.0.1 (default), run.sh auto-starts DCL.jar inside
    the container using api_key (userId) and api_secret (password).
  - No native bracket orders; SL/TP are placed as separate stop/limit orders.
  - paper_trading=True maps to Darwin -test mode (started by run.sh).
"""

from __future__ import annotations

import logging
import math
import socket
import threading
import time
from datetime import datetime, timezone
from typing import List, Optional

import pandas as pd

from trading.broker.base import BrokerBase
from trading import data as market_data

logger = logging.getLogger("trading_bot.broker.directa")

# Default Darwin CommandLine TCP ports
_TRADING_PORT    = 10002
_DATAFEED_PORT   = 10001
_HISTORICAL_PORT = 10003

_CONNECT_TIMEOUT = 10.0   # seconds – socket connect
_CMD_TIMEOUT     = 5.0    # seconds – single-line response
_SILENCE_TIMEOUT = 1.0    # seconds – silence = end of multi-line response
_HIST_TIMEOUT    = 30.0   # seconds – historical data (may be slow for many bars)


class DirectaBroker(BrokerBase):
    """
    Directa SIM broker via Darwin TCP socket API.

    Darwin CommandLine (DCL.jar) must be running on `directa_host`
    before calling `connect()`.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        trading_port: int = _TRADING_PORT,
        datafeed_port: int = _DATAFEED_PORT,
        historical_port: int = _HISTORICAL_PORT,
    ):
        self._host            = host
        self._trading_port    = trading_port
        self._datafeed_port   = datafeed_port
        self._historical_port = historical_port

        self._trading_sock:    Optional[socket.socket] = None
        self._datafeed_sock:   Optional[socket.socket] = None
        self._historical_sock: Optional[socket.socket] = None

        self._trading_lock    = threading.Lock()
        self._datafeed_lock   = threading.Lock()
        self._historical_lock = threading.Lock()

        # True while the Darwin port is still worth trying; set to False on
        # first data failure so subsequent calls skip Darwin and go straight to
        # Yahoo Finance HTTP (avoids repeated multi-second timeouts per tick).
        self._darwin_quote_works = True
        self._darwin_bars_works  = True

        # symbol -> (sl_order_id, tp_order_id) – cancelled when closing
        self._bracket_orders: dict[str, tuple[Optional[str], Optional[str]]] = {}

    # ------------------------------------------------------------------
    # Broker capabilities
    # ------------------------------------------------------------------

    @property
    def long_only(self) -> bool:
        """Directa deals in real shares; naked short selling is not allowed."""
        return True

    # ------------------------------------------------------------------
    # Low-level socket helpers
    # ------------------------------------------------------------------

    def _make_socket(self, port: int) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(_CONNECT_TIMEOUT)
        sock.connect((self._host, port))
        return sock

    def _send(self, sock: socket.socket, cmd: str) -> None:
        sock.sendall((cmd + "\n").encode("utf-8"))

    def _readline(self, sock: socket.socket, timeout: float = _CMD_TIMEOUT) -> str:
        """
        Read one newline-terminated line from *sock*.
        Heartbeat-only lines ('H') are silently skipped.
        Returns '' on timeout or closed socket.
        """
        while True:
            buf = b""
            sock.settimeout(timeout)
            try:
                while True:
                    ch = sock.recv(1)
                    if not ch:
                        raise ConnectionError("Darwin socket closed")
                    if ch == b"\n":
                        line = buf.decode("utf-8").strip("\r ")
                        break
                    buf += ch
            except socket.timeout:
                return buf.decode("utf-8", errors="replace").strip()
            if line != "H":
                return line

    def _drain(self, sock: socket.socket, wait: float = 0.3) -> None:
        """Discard any pending data on *sock* for *wait* seconds."""
        sock.settimeout(wait)
        try:
            while True:
                if not sock.recv(4096):
                    break
        except socket.timeout:
            pass

    # ------------------------------------------------------------------
    # Trading-socket helpers (all require _trading_lock)
    # ------------------------------------------------------------------

    def _t_send(self, cmd: str) -> None:
        """Send command on trading socket (caller must hold _trading_lock)."""
        self._send(self._trading_sock, cmd)

    def _t_readline(self, timeout: float = _CMD_TIMEOUT) -> str:
        return self._readline(self._trading_sock, timeout=timeout)

    def _t_cmd_single(self, cmd: str, timeout: float = _CMD_TIMEOUT) -> str:
        """Send command, return one non-empty response line."""
        with self._trading_lock:
            self._t_send(cmd)
            return self._t_readline(timeout=timeout)

    def _t_cmd_collect(
        self,
        cmd: str,
        silence: float = _SILENCE_TIMEOUT,
    ) -> list[str]:
        """
        Send command and collect response lines until *silence* seconds pass
        with no new data. Returns all collected (non-empty) lines.
        """
        with self._trading_lock:
            self._t_send(cmd)
            lines: list[str] = []
            while True:
                line = self._t_readline(timeout=silence)
                if not line:
                    break
                lines.append(line)
        return lines

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        # TRADING port (10002) is required — free-tier MC API.
        try:
            self._trading_sock = self._make_socket(self._trading_port)
        except Exception as exc:
            logger.error(f"Directa connection failed (trading port {self._trading_port}): {exc}")
            return False

        # DATAFEED port (10001) — optional, requires paid subscription.
        # If unavailable, quotes fall back to yfinance automatically.
        try:
            self._datafeed_sock = self._make_socket(self._datafeed_port)
        except Exception as exc:
            logger.info(
                f"Directa: DATAFEED port {self._datafeed_port} not available "
                f"({exc}) – will use Yahoo Finance HTTP for real-time quotes."
            )
            self._datafeed_sock = None

        # HISTORICAL port (10003) — optional, requires paid subscription.
        # If unavailable, bar data falls back to yfinance automatically.
        try:
            self._historical_sock = self._make_socket(self._historical_port)
        except Exception as exc:
            logger.info(
                f"Directa: HISTORICAL port {self._historical_port} not available "
                f"({exc}) – will use Yahoo Finance HTTP for historical bars."
            )
            self._historical_sock = None

        # Enable BEGIN/END markers for multi-line responses (INFOSTOCKS / ORDERLIST)
        try:
            with self._trading_lock:
                self._t_send("FLOWPOINT TRUE")
                # Drain any banner or acknowledgement from Darwin
                self._drain(self._trading_sock, wait=0.5)
        except Exception as exc:
            logger.error(f"Directa FLOWPOINT setup failed: {exc}")
            self.disconnect()
            return False

        datafeed_src  = str(self._datafeed_port)   if self._datafeed_sock   else "Yahoo Finance"
        historical_src = str(self._historical_port) if self._historical_sock else "Yahoo Finance"
        logger.info(
            f"Directa connected to Darwin at {self._host} "
            f"(trading:{self._trading_port}, "
            f"datafeed:{datafeed_src}, "
            f"historical:{historical_src})"
        )
        return True

    def disconnect(self) -> None:
        for sock in (self._trading_sock, self._datafeed_sock, self._historical_sock):
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass
        self._trading_sock    = None
        self._datafeed_sock   = None
        self._historical_sock = None
        logger.info("Directa disconnected.")

    # ------------------------------------------------------------------
    # Account information
    # ------------------------------------------------------------------

    def get_account_value(self) -> float:
        """
        INFOACCOUNT response:
        INFOACCOUNT;HH:MM:SS;ACCOUNT_CODE;LIQUIDITY;GAIN_EUR;OPEN_PROFIT_LOSS
        Total equity = LIQUIDITY + OPEN_PROFIT_LOSS
        """
        line = self._t_cmd_single("INFOACCOUNT")
        try:
            parts = line.split(";")
            if parts[0] == "INFOACCOUNT" and len(parts) >= 6:
                return float(parts[3]) + float(parts[5])
        except Exception as exc:
            logger.error(f"get_account_value parse error: {exc} – raw: {line!r}")
        return 0.0

    def get_buying_power(self) -> float:
        """
        INFOAVAILABILITY response:
        AVAILABILITY;HH:MM:SS;STOCKS_AVAIL;STOCKS_AVAIL_LEVERAGE;...
        Returns STOCKS_AVAIL (cash available for stock purchases without leverage).
        """
        line = self._t_cmd_single("INFOAVAILABILITY")
        try:
            parts = line.split(";")
            if parts[0] == "AVAILABILITY" and len(parts) >= 3:
                return float(parts[2])
        except Exception as exc:
            logger.error(f"get_buying_power parse error: {exc} – raw: {line!r}")
        return 0.0

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    def get_bars(
        self,
        symbol: str,
        timeframe_minutes: int = 1,
        limit: int = 100,
    ) -> pd.DataFrame:
        """Return OHLCV bars for *symbol*.

        Tries the Darwin HISTORICAL socket (port 10003) first.  On the first
        failure (socket unavailable or no data returned) it permanently switches
        to yfinance for the lifetime of this connection, avoiding repeated
        multi-second timeouts on every subsequent tick.
        """
        if self._historical_sock is not None and self._darwin_bars_works:
            df = self._darwin_get_bars(symbol, timeframe_minutes, limit)
            if not df.empty:
                return df
            logger.info(
                "Directa HISTORICAL returned no data for %s "
                "– switching to Yahoo Finance HTTP for all bar requests.", symbol
            )
            self._darwin_bars_works = False

        return market_data.get_bars(symbol, timeframe_minutes, limit)

    def _darwin_get_bars(
        self,
        symbol: str,
        timeframe_minutes: int = 1,
        limit: int = 100,
    ) -> pd.DataFrame:
        """
        CANDLE <ticker> <num_days> <seconds>  →  HISTORICAL socket (10003)

        Response format (each line):
            CANDLE;TICKER;YYYYMMDD;HH:MM:SS;OPEN;LOW;HIGH;CLOSE;VOLUME
        Delimited by BEGIN CANDLES / END CANDLES.
        """
        seconds = timeframe_minutes * 60
        # Estimate calendar days needed (assume ~390 trading min/day for NYSE)
        num_days = max(3, math.ceil(limit * timeframe_minutes / 390) + 2)

        with self._historical_lock:
            self._send(self._historical_sock, f"CANDLE {symbol} {num_days} {seconds}")

            records: list[dict] = []
            deadline = time.monotonic() + _HIST_TIMEOUT
            self._historical_sock.settimeout(_HIST_TIMEOUT)

            while time.monotonic() < deadline:
                line = self._readline(
                    self._historical_sock,
                    timeout=max(1.0, deadline - time.monotonic()),
                )
                if not line:
                    break
                if line == "END CANDLES":
                    break
                if not line.startswith("CANDLE;"):
                    continue

                # CANDLE;TICKER;YYYYMMDD;HH:MM:SS;OPEN;LOW;HIGH;CLOSE;VOLUME
                parts = line.split(";")
                if len(parts) < 9:
                    continue
                try:
                    dt = datetime.strptime(
                        f"{parts[2]} {parts[3]}", "%Y%m%d %H:%M:%S"
                    ).replace(tzinfo=timezone.utc)
                    records.append(
                        {
                            "timestamp": dt,
                            "open":   float(parts[4]),
                            "low":    float(parts[5]),
                            "high":   float(parts[6]),
                            "close":  float(parts[7]),
                            "volume": float(parts[8]),
                        }
                    )
                except Exception:
                    continue

        if not records:
            logger.warning(f"_darwin_get_bars: no candles received for {symbol}")
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        df = (
            pd.DataFrame(records)
            .set_index("timestamp")
            .sort_index()
        )
        return df[["open", "high", "low", "close", "volume"]].tail(limit)

    def get_quote(self, symbol: str) -> Optional[float]:
        """Return the current price for *symbol*.

        Tries the Darwin DATAFEED socket (port 10001) first.  On the first
        failure (socket unavailable or no price tick received) it permanently
        switches to yfinance, avoiding repeated 5-second timeouts per tick.
        """
        if self._datafeed_sock is not None and self._darwin_quote_works:
            price = self._darwin_get_quote(symbol)
            if price is not None:
                return price
            logger.info(
                "Directa DATAFEED returned no price for %s "
                "– switching to Yahoo Finance HTTP for all quote requests.", symbol
            )
            self._darwin_quote_works = False

        return market_data.get_quote(symbol)

    def _darwin_get_quote(self, symbol: str) -> Optional[float]:
        """
        Subscribe to DATAFEED (port 10001) for one price tick, then unsubscribe.
        SUBPRZ response: PRICE;TICKER;HH:MM:SS;PRICE;QTY;...
        """
        with self._datafeed_lock:
            try:
                self._send(self._datafeed_sock, f"SUBPRZ {symbol}")
                deadline = time.monotonic() + _CMD_TIMEOUT
                while time.monotonic() < deadline:
                    line = self._readline(
                        self._datafeed_sock,
                        timeout=max(0.5, deadline - time.monotonic()),
                    )
                    if not line:
                        break
                    if line.startswith(f"PRICE;{symbol};"):
                        parts = line.split(";")
                        if len(parts) >= 4:
                            price = float(parts[3])
                            self._send(self._datafeed_sock, f"UNS {symbol}")
                            return price
                self._send(self._datafeed_sock, f"UNS {symbol}")
            except Exception as exc:
                logger.error(f"_darwin_get_quote failed for {symbol}: {exc}")
        return None

    # ------------------------------------------------------------------
    # Order execution helpers
    # ------------------------------------------------------------------

    def _parse_tradok(self, line: str) -> Optional[str]:
        """
        Parse TRADOK / TRADCONFIRM response and return order_id, or None on error.

        TRADOK;TICKER;ORDER_ID;CODE;COMMAND;QTY;PRICE;ERROR_DESC
        TRADCONFIRM;TICKER;ORDER_ID;3003;COMMAND;QTY;PRICE;MESSAGE
        TRADERR;TICKER;ORDER_ID;ERROR_CODE;...
        """
        parts = line.split(";")
        if not parts:
            return None

        tag = parts[0]
        if tag == "TRADOK" and len(parts) >= 3:
            return parts[2]

        if tag == "TRADCONFIRM" and len(parts) >= 3:
            order_id = parts[2]
            logger.info(f"Directa: order {order_id} requires confirmation – auto-confirming")
            # Auto-confirm; must hold _trading_lock when called from place_* methods
            self._t_send(f"CONFORD {order_id}")
            ack = self._t_readline()
            return self._parse_tradok(ack)

        if tag == "TRADERR":
            logger.error(f"Directa order error: {line}")
        return None

    # ------------------------------------------------------------------
    # Order placement
    # ------------------------------------------------------------------

    def place_market_order(
        self, symbol: str, qty: float, side: str
    ) -> Optional[str]:
        cmd = (
            f"ACQMARKET {symbol},{int(qty)}"
            if side == "buy"
            else f"VENMARKET {symbol},{int(qty)}"
        )
        try:
            with self._trading_lock:
                self._t_send(cmd)
                line = self._t_readline()
                order_id = self._parse_tradok(line)
            if order_id:
                logger.info(f"Directa market order: {side} {qty} {symbol} → {order_id}")
            return order_id
        except Exception as exc:
            logger.error(f"place_market_order failed for {symbol}: {exc}")
            return None

    def place_bracket_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        stop_loss: float,
        take_profit: float,
    ) -> Optional[str]:
        """
        Directa has no native bracket order type.
        Simulated with three separate orders:
          1. Market entry order
          2. Stop-loss stop order (opposite side)
          3. Take-profit limit order (opposite side)
        The SL/TP order IDs are stored and cancelled when the position is closed.
        """
        try:
            iq = int(qty)
            sl_str = f"{stop_loss:.4f}"
            tp_str = f"{take_profit:.4f}"

            if side == "buy":
                entry_cmd = f"ACQMARKET {symbol},{iq}"
                sl_cmd    = f"VENSTOP {symbol},{iq},{sl_str}"
                tp_cmd    = f"VENAZ {symbol},{iq},{tp_str}"
            else:
                entry_cmd = f"VENMARKET {symbol},{iq}"
                sl_cmd    = f"ACQSTOP {symbol},{iq},{sl_str}"
                tp_cmd    = f"ACQAZ {symbol},{iq},{tp_str}"

            with self._trading_lock:
                # 1. Market entry
                self._t_send(entry_cmd)
                entry_id = self._parse_tradok(self._t_readline())
                if not entry_id:
                    return None

                # 2. Stop-loss
                self._t_send(sl_cmd)
                sl_id = self._parse_tradok(self._t_readline())

                # 3. Take-profit limit
                self._t_send(tp_cmd)
                tp_id = self._parse_tradok(self._t_readline())

            self._bracket_orders[symbol] = (sl_id, tp_id)
            logger.info(
                f"Directa bracket: {side} {qty} {symbol} "
                f"SL={stop_loss:.4f}(id={sl_id}) TP={take_profit:.4f}(id={tp_id}) "
                f"entry→{entry_id}"
            )
            return entry_id
        except Exception as exc:
            logger.error(f"place_bracket_order failed for {symbol}: {exc}")
            return None

    def _cancel_bracket_orders(self, symbol: str) -> None:
        """Cancel any pending SL/TP orders associated with *symbol*."""
        ids = self._bracket_orders.pop(symbol, (None, None))
        for order_id in ids:
            if order_id:
                try:
                    with self._trading_lock:
                        self._t_send(f"REVORD {order_id}")
                        self._t_readline(timeout=2.0)  # consume response
                except Exception as exc:
                    logger.warning(f"Failed to cancel order {order_id}: {exc}")

    def close_position(self, symbol: str) -> bool:
        try:
            # Cancel pending SL/TP orders first
            self._cancel_bracket_orders(symbol)

            # Determine position side and quantity
            raw_positions = self._get_positions_raw()
            pos = next((p for p in raw_positions if p["symbol"] == symbol), None)
            if not pos:
                # Position not found on Darwin: it was already closed by a
                # server-side SL/TP order (VENSTOP/VENAZ executed while bot
                # was using delayed yfinance data).  Bracket orders have
                # already been cancelled above — return True so the caller
                # marks the position as closed in the bot's internal state.
                logger.info(
                    f"close_position: {symbol} not found on Darwin – "
                    "already closed by server-side SL/TP order"
                )
                return True

            trading_qty = pos["trading_qty"]
            qty = int(abs(trading_qty))
            cmd = (
                f"VENMARKET {symbol},{qty}"
                if trading_qty > 0
                else f"ACQMARKET {symbol},{qty}"
            )

            with self._trading_lock:
                self._t_send(cmd)
                order_id = self._parse_tradok(self._t_readline())

            ok = order_id is not None
            if ok:
                logger.info(f"Directa: closed position {symbol} (qty={qty})")
            return ok
        except Exception as exc:
            logger.error(f"close_position failed for {symbol}: {exc}")
            return False

    def close_all_positions(self) -> bool:
        raw_positions = self._get_positions_raw()
        success = True
        for pos in raw_positions:
            ok = self.close_position(pos["symbol"])
            success = success and ok
        return success

    # ------------------------------------------------------------------
    # Position query
    # ------------------------------------------------------------------

    def _get_positions_raw(self) -> list[dict]:
        """
        INFOSTOCKS response (one line per held security):
            STOCK;TICKER;HH:MM:SS;PORTFOLIO_QTY;DIRECTA_QTY;TRADING_QTY;AVG_PRICE;GAIN
        Only returns positions where TRADING_QTY != 0.
        """
        lines = self._t_cmd_collect("INFOSTOCKS")
        positions: list[dict] = []
        for line in lines:
            if not line.startswith("STOCK;"):
                continue
            parts = line.split(";")
            if len(parts) < 8:
                continue
            try:
                trading_qty = float(parts[5])
                if trading_qty == 0:
                    continue
                positions.append(
                    {
                        "symbol":      parts[1],
                        "trading_qty": trading_qty,
                        "avg_price":   float(parts[6]),
                        "gain":        float(parts[7]),
                    }
                )
            except ValueError:
                continue
        return positions

    def get_open_positions(self) -> List[dict]:
        positions: list[dict] = []
        for raw in self._get_positions_raw():
            symbol    = raw["symbol"]
            qty       = abs(raw["trading_qty"])
            side      = "long" if raw["trading_qty"] > 0 else "short"
            avg_price = raw["avg_price"]
            current   = self.get_quote(symbol) or avg_price
            positions.append(
                {
                    "symbol":          symbol,
                    "qty":             qty,
                    "side":            side,
                    "avg_entry_price": avg_price,
                    "current_price":   current,
                    "unrealized_pl":   raw["gain"],
                }
            )
        return positions
