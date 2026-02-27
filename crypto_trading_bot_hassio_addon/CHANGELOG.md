# Changelog

## 1.0.13

- Fix: OCO close reason detection replaced unreliable current-price heuristic with actual Binance order data. The bot now queries `get_order` on each OCO leg to find the FILLED one and reads its `type` (`STOP_LOSS_LIMIT` → stop-loss, `LIMIT_MAKER` → take-profit) and actual `cummulativeQuoteQty / executedQty` fill price. Previously the bot could report "Take-profit hit" even when the stop-loss fired, because the market price had bounced back before the next tick.
- Fix: exit P&L percentage in Telegram now uses the actual realized P&L divided by position cost, instead of `unrealized_pnl_pct` which depended on the (potentially stale) current price.

## 1.0.12

- IP whitelist alert: on startup failure the bot sends a Telegram notification with the current public IP and a link to Binance API Management
- IP whitelist alert: during the main loop, Binance error -2015 (IP rejected) triggers a throttled Telegram notification (at most once per hour) with the current public IP
- Broker: error code -2015 in `connect()` now produces a specific log message pointing to IP whitelist instead of a generic error

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
