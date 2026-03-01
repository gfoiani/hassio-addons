"""SQLite trade history database for the Crypto Bot.

Every trade is stored in ``/data/crypto_trades.db`` as a single row that is
first inserted (open) and then updated (close).  The schema is created
automatically on first run.

Lifecycle::

    db_id = trade_db.open_trade(...)      # called in _enter_position → returns row id
    pos.db_trade_id = db_id               # stored on Position (persisted to crypto_positions.json)
    trade_db.close_trade(db_id, ...)      # called in _record_closed_position after pos.close()

Statistics queries (examples)::

    -- win rate
    SELECT AVG(win) FROM trades WHERE close_time IS NOT NULL;

    -- P&L by symbol (all amounts in USDT)
    SELECT symbol, COUNT(*) AS trades,
           ROUND(SUM(realized_pnl), 4) AS total_pnl_usdt,
           ROUND(AVG(realized_pnl_pct), 2) AS avg_pct
    FROM trades WHERE close_time IS NOT NULL
    GROUP BY symbol ORDER BY total_pnl_usdt DESC;

    -- Monthly performance
    SELECT strftime('%Y-%m', entry_time) AS month,
           COUNT(*) AS trades,
           ROUND(SUM(realized_pnl), 4) AS pnl_usdt
    FROM trades WHERE close_time IS NOT NULL
    GROUP BY month ORDER BY month;

    -- Exit reason breakdown
    SELECT close_reason, COUNT(*) AS cnt, AVG(win) AS win_rate
    FROM trades WHERE close_time IS NOT NULL GROUP BY close_reason;
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional

logger = logging.getLogger("crypto_bot.trade_db")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS trades (
    id                  INTEGER  PRIMARY KEY AUTOINCREMENT,
    symbol              TEXT     NOT NULL,
    side                TEXT     NOT NULL,
    broker              TEXT,
    strategy            TEXT,
    entry_time          TEXT     NOT NULL,
    entry_price         REAL     NOT NULL,
    quantity            REAL     NOT NULL,
    cost                REAL     NOT NULL,
    stop_loss           REAL     NOT NULL,
    take_profit         REAL     NOT NULL,
    order_id            TEXT,
    oco_order_list_id   TEXT,
    close_time          TEXT,
    close_price         REAL,
    close_reason        TEXT,
    duration_seconds    INTEGER,
    realized_pnl        REAL,
    realized_pnl_pct    REAL,
    win                 INTEGER,
    created_at          TEXT     NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT     NOT NULL DEFAULT (datetime('now'))
)
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)",
    "CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades(entry_time)",
    "CREATE INDEX IF NOT EXISTS idx_trades_win ON trades(win)",
    "CREATE INDEX IF NOT EXISTS idx_trades_close_reason ON trades(close_reason)",
]


class TradeDatabase:
    """Thread-safe SQLite persistence for crypto trade history."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = str(db_path)
        self._lock = threading.Lock()
        self._init_db()

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        try:
            with self._lock, self._connect() as conn:
                conn.execute(_CREATE_TABLE)
                for stmt in _CREATE_INDEXES:
                    conn.execute(stmt)
                conn.commit()
            logger.info("Trade database initialised at %s", self._db_path)
        except Exception as exc:
            logger.error("Failed to initialise trade database: %s", exc)

    def open_trade(
        self,
        symbol: str,
        side: str,
        broker: str,
        strategy: str,
        entry_time: datetime,
        entry_price: float,
        quantity: float,
        stop_loss: float,
        take_profit: float,
        order_id: Optional[str] = None,
        oco_order_list_id: Optional[str] = None,
    ) -> Optional[int]:
        """Insert a new open-trade record and return the auto-increment id.

        ``cost`` is stored as ``entry_price * quantity`` (USDT).
        Returns ``None`` if the insert fails; trading continues normally.
        """
        cost = entry_price * quantity
        try:
            with self._lock, self._connect() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO trades (
                        symbol, side, broker, strategy,
                        entry_time, entry_price, quantity, cost,
                        stop_loss, take_profit, order_id, oco_order_list_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        symbol, side, broker, strategy,
                        entry_time.isoformat(), entry_price, quantity, cost,
                        stop_loss, take_profit, order_id, oco_order_list_id,
                    ),
                )
                conn.commit()
                trade_id = cur.lastrowid
            logger.debug(
                "Trade opened in DB: id=%d %s %s @ %.6f",
                trade_id, symbol, side, entry_price,
            )
            return trade_id
        except Exception as exc:
            logger.error("Failed to record trade open for %s: %s", symbol, exc)
            return None

    def close_trade(
        self,
        trade_id: int,
        close_price: float,
        close_time: datetime,
        close_reason: str,
        entry_time: datetime,
        realized_pnl: float,
        cost: float,
    ) -> None:
        """Update the trade record with exit data.

        ``realized_pnl`` is in USDT (positive = profit).
        ``cost`` is ``entry_price * quantity`` in USDT, used to compute
        the percentage gain/loss.
        """
        realized_pnl_pct = (realized_pnl / cost * 100) if cost else 0.0
        duration_seconds = int((close_time - entry_time).total_seconds())
        win = 1 if realized_pnl > 0 else 0
        try:
            with self._lock, self._connect() as conn:
                conn.execute(
                    """
                    UPDATE trades SET
                        close_price      = ?,
                        close_time       = ?,
                        close_reason     = ?,
                        duration_seconds = ?,
                        realized_pnl     = ?,
                        realized_pnl_pct = ?,
                        win              = ?,
                        updated_at       = datetime('now')
                    WHERE id = ?
                    """,
                    (
                        close_price, close_time.isoformat(), close_reason,
                        duration_seconds, realized_pnl, realized_pnl_pct, win,
                        trade_id,
                    ),
                )
                conn.commit()
            logger.debug(
                "Trade closed in DB: id=%d reason=%s pnl=%.6f USDT (%.2f%%)",
                trade_id, close_reason, realized_pnl, realized_pnl_pct,
            )
        except Exception as exc:
            logger.error("Failed to record trade close for id=%d: %s", trade_id, exc)
