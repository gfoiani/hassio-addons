"""Configuration dataclass for the Bet Sniper Bot."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class BetSniperConfig:
    """All runtime configuration for the bot.

    Populated by main.py from CLI args / environment variables.
    """

    # Betfair credentials
    username: str
    password: str
    app_key: str

    # Trading mode
    paper_trading: bool

    # Market configuration
    leagues: List[str]          # e.g. ["soccer_italy_serie_a", "soccer_epl"]
    min_odds: float             # Minimum back odds to consider
    max_odds: float             # Maximum back odds to consider

    # Stake / risk management
    stake_per_bet: float        # Fixed stake per event (e.g. 5.0 EUR)
    max_daily_loss_pct: float   # Max % of balance to spend in one day (e.g. 10.0)
    reserve_pct: float          # % of balance to always keep reserved (e.g. 20.0)

    # Scheduling
    lookahead_hours: int        # How many hours ahead to look for matches
    check_interval: int         # Seconds between market scans

    # Snipe window – only place bets when kick-off is "close enough"
    bet_window_hours: float     # Bet only if KO is within this many hours (e.g. 2.0)
    min_time_to_ko_minutes: int # Don't bet if KO is less than this many minutes away (e.g. 30)

    # Telegram relay
    telegram_relay_url: str
    telegram_api_key: str
