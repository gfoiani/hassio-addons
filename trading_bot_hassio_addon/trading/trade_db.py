"""SQLite trade history database.

Every trade is stored in ``/data/trades.db`` as a single row that is first
inserted (open) and then updated (close).  The schema is created automatically
on first run.

Lifecycle::

    db_id = trade_db.open_trade(...)      # called in _enter_position → returns row id
    pos.db_trade_id = db_id               # stored on Position (persisted to positions.json)
    trade_db.close_trade(db_id, ...)      # called in _exit_position after pos.close()

Statistics queries (examples)::

    -- win rate
    SELECT AVG(win) FROM trades WHERE close_time IS NOT NULL;

    -- P&L by symbol
    SELECT symbol, COUNT(*) AS trades,
           ROUND(SUM(realized_pnl), 2) AS total_pnl,
           ROUND(AVG(realized_pnl_pct), 2) AS avg_pct
    FROM trades WHERE close_time IS NOT NULL
    GROUP BY symbol ORDER BY total_pnl DESC;

    -- P&L by strategy
    SELECT strategy, COUNT(*) AS trades, AVG(win) AS win_rate
    FROM trades WHERE close_time IS NOT NULL GROUP BY strategy;

    -- Monthly performance
    SELECT strftime('%Y-%m', entry_time) AS month,
           COUNT(*) AS trades, ROUND(SUM(realized_pnl), 2) AS pnl
    FROM trades WHERE close_time IS NOT NULL
    GROUP BY month ORDER BY month;
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional

logger = logging.getLogger("trading_bot.trade_db")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS trades (
    id                INTEGER  PRIMARY KEY AUTOINCREMENT,
    symbol            TEXT     NOT NULL,
    exchange          TEXT,
    side              TEXT     NOT NULL,
    broker            TEXT,
    strategy          TEXT,
    entry_time        TEXT     NOT NULL,
    entry_price       REAL     NOT NULL,
    quantity          REAL     NOT NULL,
    cost              REAL     NOT NULL,
    stop_loss         REAL     NOT NULL,
    take_profit       REAL     NOT NULL,
    order_id          TEXT,
    close_time        TEXT,
    close_price       REAL,
    close_reason      TEXT,
    duration_seconds  INTEGER,
    realized_pnl      REAL,
    realized_pnl_pct  REAL,
    win               INTEGER,
    created_at        TEXT     NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT     NOT NULL DEFAULT (datetime('now'))
)
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)",
    "CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades(entry_time)",
    "CREATE INDEX IF NOT EXISTS idx_trades_win ON trades(win)",
    "CREATE INDEX IF NOT EXISTS idx_trades_close_reason ON trades(close_reason)",
]


class TradeDatabase:
    """Thread-safe SQLite persistence for trade history."""

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
        exchange: Optional[str],
        side: str,
        broker: str,
        strategy: str,
        entry_time: datetime,
        entry_price: float,
        quantity: float,
        stop_loss: float,
        take_profit: float,
        order_id: Optional[str] = None,
    ) -> Optional[int]:
        """Insert a new open-trade record and return the auto-increment id.

        Returns ``None`` if the insert fails (DB error); the trade will still
        proceed normally — the DB is non-critical.
        """
        cost = entry_price * quantity
        try:
            with self._lock, self._connect() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO trades (
                        symbol, exchange, side, broker, strategy,
                        entry_time, entry_price, quantity, cost,
                        stop_loss, take_profit, order_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        symbol, exchange, side, broker, strategy,
                        entry_time.isoformat(), entry_price, quantity, cost,
                        stop_loss, take_profit, order_id,
                    ),
                )
                conn.commit()
                trade_id = cur.lastrowid
            logger.debug(
                "Trade opened in DB: id=%d %s %s @ %.4f",
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

        ``realized_pnl`` must already account for position side (positive = profit).
        ``cost`` is ``entry_price * quantity`` and is used to compute the
        percentage gain/loss.
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
                "Trade closed in DB: id=%d reason=%s pnl=%.4f (%.2f%%)",
                trade_id, close_reason, realized_pnl, realized_pnl_pct,
            )
        except Exception as exc:
            logger.error("Failed to record trade close for id=%d: %s", trade_id, exc)

    def get_stats(self) -> dict:
        """Return aggregated statistics from the trade history.

        Returns an empty dict on DB error (non-critical).
        """
        try:
            with self._lock, self._connect() as conn:
                row = conn.execute("""
                    SELECT
                        COUNT(*)                                AS total,
                        COALESCE(SUM(win), 0)                  AS wins,
                        COALESCE(ROUND(AVG(win) * 100, 1), 0)  AS win_rate,
                        COALESCE(ROUND(SUM(realized_pnl), 2), 0) AS total_pnl,
                        COALESCE(ROUND(AVG(realized_pnl), 2), 0) AS avg_pnl,
                        COALESCE(ROUND(AVG(realized_pnl_pct), 2), 0) AS avg_pnl_pct,
                        COALESCE(ROUND(MAX(realized_pnl), 2), 0) AS best_pnl,
                        COALESCE(ROUND(MIN(realized_pnl), 2), 0) AS worst_pnl,
                        COALESCE(ROUND(AVG(duration_seconds) / 60.0, 1), 0) AS avg_duration_min
                    FROM trades WHERE close_time IS NOT NULL
                """).fetchone()

                open_count = conn.execute(
                    "SELECT COUNT(*) FROM trades WHERE close_time IS NULL"
                ).fetchone()[0]

                today_row = conn.execute("""
                    SELECT
                        COUNT(*) AS trades,
                        COALESCE(ROUND(SUM(realized_pnl), 2), 0) AS pnl
                    FROM trades
                    WHERE close_time IS NOT NULL
                      AND date(close_time) = date('now', '-1 day')
                """).fetchone()

                week_row = conn.execute("""
                    SELECT
                        COUNT(*) AS trades,
                        COALESCE(ROUND(SUM(realized_pnl), 2), 0) AS pnl
                    FROM trades
                    WHERE close_time IS NOT NULL
                      AND close_time >= datetime('now', '-7 days')
                """).fetchone()

                reason_rows = conn.execute("""
                    SELECT close_reason,
                           COUNT(*) AS cnt,
                           COALESCE(ROUND(SUM(realized_pnl), 2), 0) AS pnl
                    FROM trades
                    WHERE close_time IS NOT NULL
                    GROUP BY close_reason
                """).fetchall()

            return {
                "total_closed": row["total"],
                "wins": row["wins"],
                "win_rate": row["win_rate"],
                "total_pnl": row["total_pnl"],
                "avg_pnl": row["avg_pnl"],
                "avg_pnl_pct": row["avg_pnl_pct"],
                "best_pnl": row["best_pnl"],
                "worst_pnl": row["worst_pnl"],
                "avg_duration_min": row["avg_duration_min"],
                "open_count": open_count,
                "today_trades": today_row["trades"],
                "today_pnl": today_row["pnl"],
                "week_trades": week_row["trades"],
                "week_pnl": week_row["pnl"],
                "by_reason": {
                    r["close_reason"]: {"count": r["cnt"], "pnl": r["pnl"]}
                    for r in reason_rows
                },
            }
        except Exception as exc:
            logger.error("Failed to query trade stats: %s", exc)
            return {}
