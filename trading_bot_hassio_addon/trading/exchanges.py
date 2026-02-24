"""
Exchange schedule definitions for NYSE (New York) and LSE (London).

NYSE: Monday-Friday 09:30-16:00 America/New_York
LSE:  Monday-Friday 08:00-16:30 Europe/London

Both exchanges observe local public holidays (not modelled here for simplicity;
users should monitor holiday calendars independently).
"""

from __future__ import annotations

import logging
from datetime import datetime, time
from typing import Optional

import pytz

logger = logging.getLogger("trading_bot.exchanges")


class ExchangeSchedule:
    def __init__(
        self,
        name: str,
        timezone: str,
        open_hour: int,
        open_minute: int,
        close_hour: int,
        close_minute: int,
    ):
        self.name = name
        self.timezone = timezone
        self._tz = pytz.timezone(timezone)
        self._open_time = time(open_hour, open_minute)
        self._close_time = time(close_hour, close_minute)

    # ------------------------------------------------------------------
    # Core time helpers
    # ------------------------------------------------------------------

    def local_now(self) -> datetime:
        """Return current datetime in the exchange local timezone."""
        return datetime.now(self._tz)

    def is_market_day(self) -> bool:
        """Return True on weekdays (Mon-Fri). Holidays NOT modelled."""
        return self.local_now().weekday() < 5  # 0=Mon … 4=Fri

    def is_open(self) -> bool:
        """Return True while the exchange is actively trading."""
        if not self.is_market_day():
            return False
        now_t = self.local_now().time()
        return self._open_time <= now_t <= self._close_time

    # ------------------------------------------------------------------
    # Time-until helpers (return None if not applicable today)
    # ------------------------------------------------------------------

    def minutes_until_open(self) -> Optional[float]:
        """Minutes until today's open, or None if market is already open / not a market day."""
        if not self.is_market_day():
            return None
        now = self.local_now()
        open_dt = now.replace(
            hour=self._open_time.hour,
            minute=self._open_time.minute,
            second=0,
            microsecond=0,
        )
        delta = (open_dt - now).total_seconds() / 60
        return delta if delta > 0 else None

    def minutes_until_close(self) -> Optional[float]:
        """Minutes until today's close, or None if the market is closed."""
        if not self.is_open():
            return None
        now = self.local_now()
        close_dt = now.replace(
            hour=self._close_time.hour,
            minute=self._close_time.minute,
            second=0,
            microsecond=0,
        )
        return (close_dt - now).total_seconds() / 60

    def minutes_since_open(self) -> Optional[float]:
        """Minutes elapsed since today's open, or None if the market is closed."""
        if not self.is_open():
            return None
        now = self.local_now()
        open_dt = now.replace(
            hour=self._open_time.hour,
            minute=self._open_time.minute,
            second=0,
            microsecond=0,
        )
        return (now - open_dt).total_seconds() / 60

    # ------------------------------------------------------------------
    # Window helpers used by the bot's main loop
    # ------------------------------------------------------------------

    def is_pre_market_window(self, minutes_before: int) -> bool:
        """True in the N minutes *before* the market opens."""
        mins = self.minutes_until_open()
        return mins is not None and 0 < mins <= minutes_before

    def is_orb_window(self, orb_minutes: int) -> bool:
        """True during the Opening Range Breakout data-collection period."""
        mins = self.minutes_since_open()
        return mins is not None and 0 <= mins <= orb_minutes

    def is_closing_window(self, minutes_before: int) -> bool:
        """True in the last N minutes before market close."""
        mins = self.minutes_until_close()
        return mins is not None and 0 < mins <= minutes_before

    def __repr__(self) -> str:
        return (
            f"ExchangeSchedule({self.name}, tz={self.timezone}, "
            f"open={self._open_time}, close={self._close_time})"
        )


# ---------------------------------------------------------------------------
# Pre-built exchange objects
# ---------------------------------------------------------------------------

NYSE = ExchangeSchedule(
    name="NYSE",
    timezone="America/New_York",
    open_hour=9,
    open_minute=30,
    close_hour=16,
    close_minute=0,
)

LSE = ExchangeSchedule(
    name="LSE",
    timezone="Europe/London",
    open_hour=8,
    open_minute=0,
    close_hour=16,
    close_minute=30,
)

EXCHANGES: dict[str, ExchangeSchedule] = {
    "NYSE": NYSE,
    "LSE": LSE,
}


def get_exchange(name: str) -> ExchangeSchedule:
    """Return an ExchangeSchedule by name (case-insensitive)."""
    key = name.upper()
    if key not in EXCHANGES:
        raise ValueError(f"Unknown exchange '{name}'. Available: {list(EXCHANGES.keys())}")
    return EXCHANGES[key]
