from dataclasses import dataclass, field
from typing import List


@dataclass
class TradingConfig:
    broker: str
    api_key: str
    api_secret: str
    paper_trading: bool

    exchanges: List[str]
    symbols_nyse: List[str]
    symbols_lse: List[str]

    max_position_value: float
    stop_loss_pct: float
    take_profit_pct: float
    max_daily_loss_pct: float

    strategy: str
    orb_minutes: int
    pre_market_minutes: int
    close_minutes: int
    check_interval: int

    # Directa SIM specific (ignored by XTB)
    # Darwin CommandLine (DCL.jar) is auto-started by run.sh on the same host.
    # Set to a remote IP only if running Darwin on a separate machine.
    directa_host: str = "127.0.0.1"

    # Telegram relay service (Render)
    # Leave empty to disable Telegram integration.
    telegram_relay_url: str = ""   # e.g. https://trading-bot-telegram-relay.onrender.com
    telegram_api_key: str = ""     # shared secret (RELAY_API_KEY on the Render service)

    @property
    def all_symbols(self) -> List[str]:
        return self.symbols_nyse + self.symbols_lse

    def symbols_for_exchange(self, exchange_name: str) -> List[str]:
        if exchange_name == "NYSE":
            return self.symbols_nyse
        elif exchange_name == "LSE":
            return self.symbols_lse
        return []
