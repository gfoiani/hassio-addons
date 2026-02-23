"""
CryptoTradingConfig – configuration dataclass for the Binance Spot crypto bot.
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class CryptoTradingConfig:
    api_key: str
    api_secret: str
    paper_trading: bool
    symbols: List[str]           # e.g. ["BTCUSDT", "ETHUSDT"]
    timeframe: int               # candle size in minutes: 15, 30, or 60
    max_position_value_usdt: float
    stop_loss_pct: float
    take_profit_pct: float
    max_daily_loss_pct: float
    check_interval: int          # seconds between main loop iterations
    cooldown_minutes: int        # minutes to wait after closing before re-entering same symbol
    telegram_relay_url: str = ""
    telegram_api_key: str = ""
