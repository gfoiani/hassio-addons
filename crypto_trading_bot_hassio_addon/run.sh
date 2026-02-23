#!/usr/bin/with-contenv bashio

echo "=========================================="
echo "  Crypto Trading Bot - Binance Spot"
echo "=========================================="
echo ""

if [[ $LOCAL_DEPLOY != "true" ]]; then
  API_KEY=$(bashio::config 'api_key')
  API_SECRET=$(bashio::config 'api_secret')
  PAPER_TRADING=$(bashio::config 'paper_trading')
  SYMBOLS=$(bashio::config 'symbols')
  TIMEFRAME=$(bashio::config 'timeframe')
  MAX_POSITION_VALUE_USDT=$(bashio::config 'max_position_value_usdt')
  STOP_LOSS_PCT=$(bashio::config 'stop_loss_pct')
  TAKE_PROFIT_PCT=$(bashio::config 'take_profit_pct')
  MAX_DAILY_LOSS_PCT=$(bashio::config 'max_daily_loss_pct')
  CHECK_INTERVAL=$(bashio::config 'check_interval')
  COOLDOWN_MINUTES=$(bashio::config 'cooldown_minutes')
  TELEGRAM_RELAY_URL=$(bashio::config 'telegram_relay_url')
  TELEGRAM_API_KEY=$(bashio::config 'telegram_api_key')
fi

echo "Paper trading:      $PAPER_TRADING"
echo "Symbols:            $SYMBOLS"
echo "Timeframe:          ${TIMEFRAME}m"
echo "Max position USDT:  $MAX_POSITION_VALUE_USDT"
echo "Stop loss:          ${STOP_LOSS_PCT}%"
echo "Take profit:        ${TAKE_PROFIT_PCT}%"
echo "Max daily loss:     ${MAX_DAILY_LOSS_PCT}%"
echo "Check interval:     ${CHECK_INTERVAL}s"
echo "Cooldown:           ${COOLDOWN_MINUTES}m"
echo ""

exec python3 main.py \
  --api-key "${API_KEY:-}" \
  --api-secret "${API_SECRET:-}" \
  --paper-trading "${PAPER_TRADING:-true}" \
  --symbols "${SYMBOLS:-BTCUSDT,ETHUSDT}" \
  --timeframe "${TIMEFRAME:-15}" \
  --max-position-value-usdt "${MAX_POSITION_VALUE_USDT:-100}" \
  --stop-loss-pct "${STOP_LOSS_PCT:-2.0}" \
  --take-profit-pct "${TAKE_PROFIT_PCT:-4.0}" \
  --max-daily-loss-pct "${MAX_DAILY_LOSS_PCT:-5.0}" \
  --check-interval "${CHECK_INTERVAL:-60}" \
  --cooldown-minutes "${COOLDOWN_MINUTES:-30}" \
  --telegram-relay-url "${TELEGRAM_RELAY_URL:-}" \
  --telegram-api-key "${TELEGRAM_API_KEY:-}"
