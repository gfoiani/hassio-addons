#!/usr/bin/with-contenv bashio

set +u
set +H
set +e

echo "=========================================="
echo "  Bet Sniper Bot (Betfair)"
echo "=========================================="
echo ""

if [[ $LOCAL_DEPLOY != "true" ]]; then
  USERNAME=$(bashio::config 'username')
  PASSWORD=$(bashio::config 'password')
  APP_KEY=$(bashio::config 'app_key')
  PAPER_TRADING=$(bashio::config 'paper_trading')
  LEAGUES=$(bashio::config 'leagues')
  MIN_ODDS=$(bashio::config 'min_odds')
  MAX_ODDS=$(bashio::config 'max_odds')
  STAKE_PER_BET=$(bashio::config 'stake_per_bet')
  MAX_DAILY_LOSS_PCT=$(bashio::config 'max_daily_loss_pct')
  RESERVE_PCT=$(bashio::config 'reserve_pct')
  LOOKAHEAD_HOURS=$(bashio::config 'lookahead_hours')
  CHECK_INTERVAL=$(bashio::config 'check_interval')
  BET_WINDOW_HOURS=$(bashio::config 'bet_window_hours')
  MIN_TIME_TO_KO_MINUTES=$(bashio::config 'min_time_to_ko_minutes')
  TELEGRAM_RELAY_URL=$(bashio::config 'telegram_relay_url')
  TELEGRAM_API_KEY=$(bashio::config 'telegram_api_key')
fi

echo "Paper trading:      $PAPER_TRADING"
echo "Leagues:            $LEAGUES"
echo "Odds range:         $MIN_ODDS – $MAX_ODDS"
echo "Stake per bet:      $STAKE_PER_BET"
echo "Max daily loss:     ${MAX_DAILY_LOSS_PCT}%"
echo "Reserve:            ${RESERVE_PCT}%"
echo "Lookahead:          ${LOOKAHEAD_HOURS}h"
echo "Check interval:     ${CHECK_INTERVAL}s"
echo "Bet window:         ${BET_WINDOW_HOURS}h before KO"
echo "Min time to KO:     ${MIN_TIME_TO_KO_MINUTES}min"
echo ""

exec python3 -u main.py \
  --username "${USERNAME:-}" \
  --password "${PASSWORD:-}" \
  --app-key "${APP_KEY:-}" \
  --paper-trading "${PAPER_TRADING:-true}" \
  --leagues "${LEAGUES:-soccer_italy_serie_a,soccer_epl,soccer_spain_la_liga,soccer_germany_bundesliga}" \
  --min-odds "${MIN_ODDS:-1.5}" \
  --max-odds "${MAX_ODDS:-2.2}" \
  --stake-per-bet "${STAKE_PER_BET:-5.0}" \
  --max-daily-loss-pct "${MAX_DAILY_LOSS_PCT:-5.0}" \
  --reserve-pct "${RESERVE_PCT:-30.0}" \
  --lookahead-hours "${LOOKAHEAD_HOURS:-24}" \
  --check-interval "${CHECK_INTERVAL:-1800}" \
  --bet-window-hours "${BET_WINDOW_HOURS:-2.0}" \
  --min-time-to-ko-minutes "${MIN_TIME_TO_KO_MINUTES:-45}" \
  --telegram-relay-url "${TELEGRAM_RELAY_URL:-}" \
  --telegram-api-key "${TELEGRAM_API_KEY:-}"
