from trading.broker.base import BrokerBase
from trading.broker.directa_broker import DirectaBroker


def create_broker(config) -> BrokerBase:
    """Factory: instantiate the configured broker."""
    if config.broker.lower() == "directa":
        return DirectaBroker(host=config.directa_host)
    raise ValueError(
        f"Unknown broker: '{config.broker}'. Only 'directa' is supported."
    )
