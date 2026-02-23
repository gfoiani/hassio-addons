from trading.broker.binance_broker import BinanceBroker
from trading.config import CryptoTradingConfig


def create_broker(config: CryptoTradingConfig) -> BinanceBroker:
    return BinanceBroker(
        api_key=config.api_key,
        api_secret=config.api_secret,
        testnet=config.paper_trading,
    )
