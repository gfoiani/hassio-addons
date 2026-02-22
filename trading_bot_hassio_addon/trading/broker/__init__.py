from trading.broker.base import BrokerBase
from trading.broker.xtb_broker import XTBBroker
from trading.broker.directa_broker import DirectaBroker


def create_broker(config) -> BrokerBase:
    """Factory: instantiate the configured broker."""
    name = config.broker.lower()
    if name == "xtb":
        return XTBBroker(
            user_id=config.api_key,
            password=config.api_secret,
            demo=config.paper_trading,
        )
    if name == "directa":
        return DirectaBroker(
            host=config.directa_host,
        )
    raise ValueError(
        f"Unknown broker: '{config.broker}'. Choose 'xtb' or 'directa'."
    )
