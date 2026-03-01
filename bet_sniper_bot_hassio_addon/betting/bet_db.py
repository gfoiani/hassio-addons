"""SQLite bet history database for the Bet Sniper Bot.

Every bet is stored in ``/data/bets.db`` as a single row that is first inserted
(when placed) and then updated (when settled).  The schema is created automatically
on first run.

Lifecycle::

    db_id = bet_db.record_bet(...)     # called after placing a bet
    bet_db.settle_bet(db_id, ...)      # called when the bet is settled

Statistics queries (examples)::

    -- win rate
    SELECT AVG(CASE WHEN result = 'WON' THEN 1 ELSE 0 END) FROM bets WHERE result IS NOT NULL;

    -- P&L by competition
    SELECT competition, COUNT(*) AS bets,
           ROUND(SUM(profit_loss), 2) AS total_pnl
    FROM bets WHERE result IS NOT NULL
    GROUP BY competition ORDER BY total_pnl DESC;

    -- Monthly performance
    SELECT strftime('%Y-%m', bet_time) AS month,
           COUNT(*) AS bets,
           ROUND(SUM(profit_loss), 2) AS pnl
    FROM bets WHERE result IS NOT NULL
    GROUP BY month ORDER BY month;
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional

logger = logging.getLogger("bet_sniper.bet_db")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS bets (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id         TEXT    NOT NULL,
    event_name       TEXT    NOT NULL,
    competition      TEXT,
    market_id        TEXT    NOT NULL,
    selection_id     INTEGER NOT NULL,
    selection_name   TEXT    NOT NULL,
    odds             REAL    NOT NULL,
    stake            REAL    NOT NULL,
    bet_time         TEXT    NOT NULL,
    paper_trade      INTEGER NOT NULL DEFAULT 0,
    result           TEXT,
    profit_loss      REAL,
    settled_time     TEXT,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now'))
)
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_bets_event_id ON bets(event_id)",
    "CREATE INDEX IF NOT EXISTS idx_bets_bet_time ON bets(bet_time)",
    "CREATE INDEX IF NOT EXISTS idx_bets_result ON bets(result)",
    "CREATE INDEX IF NOT EXISTS idx_bets_competition ON bets(competition)",
]


class BetDatabase:
    """Thread-safe SQLite persistence for bet history."""

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
            logger.info("Bet database initialised at %s", self._db_path)
        except Exception as exc:
            logger.error("Failed to initialise bet database: %s", exc)

    def record_bet(
        self,
        event_id: str,
        event_name: str,
        competition: Optional[str],
        market_id: str,
        selection_id: int,
        selection_name: str,
        odds: float,
        stake: float,
        paper_trade: bool,
    ) -> Optional[int]:
        """Insert a new bet record and return its auto-increment id.

        Returns ``None`` if the insert fails — the bot continues normally
        as the DB is non-critical.
        """
        bet_time = datetime.now(timezone.utc)
        try:
            with self._lock, self._connect() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO bets (
                        event_id, event_name, competition,
                        market_id, selection_id, selection_name,
                        odds, stake, bet_time, paper_trade
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id, event_name, competition,
                        market_id, selection_id, selection_name,
                        odds, stake, bet_time.isoformat(), int(paper_trade),
                    ),
                )
                conn.commit()
                bet_id = cur.lastrowid
            logger.debug(
                "Bet recorded in DB: id=%d %s %s @ %.2f (stake=%.2f, paper=%s)",
                bet_id, event_name, selection_name, odds, stake, paper_trade,
            )
            return bet_id
        except Exception as exc:
            logger.error("Failed to record bet for %s: %s", event_name, exc)
            return None

    def already_bet(self, event_id: str) -> bool:
        """Return True if a bet (paper or real) already exists for this event."""
        try:
            with self._lock, self._connect() as conn:
                row = conn.execute(
                    "SELECT id FROM bets WHERE event_id = ? LIMIT 1", (event_id,)
                ).fetchone()
            return row is not None
        except Exception as exc:
            logger.error("Failed to check existing bet for event %s: %s", event_id, exc)
            return False

    def get_today_spend(self) -> float:
        """Return the total stake placed today (UTC) for real bets only."""
        try:
            with self._lock, self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT COALESCE(SUM(stake), 0) AS spend
                    FROM bets
                    WHERE date(bet_time) = date('now')
                      AND paper_trade = 0
                    """
                ).fetchone()
            return float(row["spend"])
        except Exception as exc:
            logger.error("Failed to compute today's spend: %s", exc)
            return 0.0

    def settle_bet(
        self,
        bet_id: int,
        result: str,
        profit_loss: float,
    ) -> None:
        """Update a bet row with its settlement result.

        ``result`` is one of: 'WON', 'LOST', 'VOID'.
        ``profit_loss`` is positive for wins, negative for losses (net of stake).
        """
        settled_time = datetime.now(timezone.utc)
        try:
            with self._lock, self._connect() as conn:
                conn.execute(
                    """
                    UPDATE bets SET
                        result       = ?,
                        profit_loss  = ?,
                        settled_time = ?,
                        updated_at   = datetime('now')
                    WHERE id = ?
                    """,
                    (result, profit_loss, settled_time.isoformat(), bet_id),
                )
                conn.commit()
            logger.debug(
                "Bet settled in DB: id=%d result=%s pnl=%.2f",
                bet_id, result, profit_loss,
            )
        except Exception as exc:
            logger.error("Failed to settle bet id=%d: %s", bet_id, exc)

    def get_pending_bets(self) -> list:
        """Return all bets without a result (unsettled)."""
        try:
            with self._lock, self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT id, market_id, selection_id, stake, odds, event_name,
                           selection_name, paper_trade
                    FROM bets WHERE result IS NULL AND paper_trade = 0
                    """
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.error("Failed to fetch pending bets: %s", exc)
            return []

    def get_stats(self) -> dict:
        """Return aggregated statistics from the bet history.

        Returns an empty dict on DB error (non-critical).
        """
        try:
            with self._lock, self._connect() as conn:
                row = conn.execute("""
                    SELECT
                        COUNT(*)                                             AS total,
                        COALESCE(SUM(CASE WHEN result='WON' THEN 1 ELSE 0 END), 0) AS wins,
                        COALESCE(ROUND(
                            SUM(CASE WHEN result='WON' THEN 1.0 ELSE 0 END)
                            / NULLIF(COUNT(*), 0) * 100, 1
                        ), 0)                                               AS win_rate,
                        COALESCE(ROUND(SUM(profit_loss), 2), 0)            AS total_pnl,
                        COALESCE(ROUND(AVG(profit_loss), 2), 0)            AS avg_pnl,
                        COALESCE(ROUND(MAX(profit_loss), 2), 0)            AS best_pnl,
                        COALESCE(ROUND(MIN(profit_loss), 2), 0)            AS worst_pnl
                    FROM bets WHERE result IS NOT NULL AND paper_trade = 0
                """).fetchone()

                open_count = conn.execute(
                    "SELECT COUNT(*) FROM bets WHERE result IS NULL AND paper_trade = 0"
                ).fetchone()[0]

                paper_count = conn.execute(
                    "SELECT COUNT(*) FROM bets WHERE paper_trade = 1"
                ).fetchone()[0]

                yesterday_row = conn.execute("""
                    SELECT
                        COUNT(*) AS bets,
                        COALESCE(ROUND(SUM(profit_loss), 2), 0) AS pnl
                    FROM bets
                    WHERE result IS NOT NULL
                      AND paper_trade = 0
                      AND date(bet_time) = date('now', '-1 day')
                """).fetchone()

                week_row = conn.execute("""
                    SELECT
                        COUNT(*) AS bets,
                        COALESCE(ROUND(SUM(profit_loss), 2), 0) AS pnl
                    FROM bets
                    WHERE result IS NOT NULL
                      AND paper_trade = 0
                      AND bet_time >= datetime('now', '-7 days')
                """).fetchone()

                competition_rows = conn.execute("""
                    SELECT competition,
                           COUNT(*) AS cnt,
                           COALESCE(ROUND(SUM(profit_loss), 2), 0) AS pnl
                    FROM bets
                    WHERE result IS NOT NULL AND paper_trade = 0
                    GROUP BY competition
                """).fetchall()

            return {
                "total_settled": row["total"],
                "wins": row["wins"],
                "win_rate": row["win_rate"],
                "total_pnl": row["total_pnl"],
                "avg_pnl": row["avg_pnl"],
                "best_pnl": row["best_pnl"],
                "worst_pnl": row["worst_pnl"],
                "open_count": open_count,
                "paper_count": paper_count,
                "yesterday_bets": yesterday_row["bets"],
                "yesterday_pnl": yesterday_row["pnl"],
                "week_bets": week_row["bets"],
                "week_pnl": week_row["pnl"],
                "by_competition": {
                    r["competition"]: {"count": r["cnt"], "pnl": r["pnl"]}
                    for r in competition_rows
                },
            }
        except Exception as exc:
            logger.error("Failed to query bet stats: %s", exc)
            return {}
