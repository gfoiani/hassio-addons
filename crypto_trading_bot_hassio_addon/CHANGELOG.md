# Changelog

## 1.0.11

- Fix OCO order placement: updated to new Binance API format (`aboveType`/`belowType` parameters required by `POST /api/v3/orderList/oco`)

## 1.0.0

- Initial release
- Binance Spot trading with Momentum EMA+RSI strategy
- Intraday timeframes: 15, 30, 60 minutes
- OCO orders for bracket SL/TP on Binance Spot
- 24/7 operation with cooldown between trades per symbol
- Daily loss limit with automatic trading halt
- Telegram notifications and commands via relay service
- Paper trading mode via Binance Testnet
- Persistent positions and trade log in /data
- Multi-architecture Docker support
