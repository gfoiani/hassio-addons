#!/usr/bin/with-contenv bashio

echo "=========================================="
echo "  Day Trading Bot - NYSE & LSE"
echo "=========================================="
echo ""

echo "Creating Python virtual environment..."
python3 -m venv ./venv
echo "Activating virtual environment..."
source ./venv/bin/activate

echo "Installing dependencies..."
pip3 install --upgrade pip --quiet
pip3 install -r requirements.txt --quiet

if [[ $LOCAL_DEPLOY != "true" ]]; then
  BROKER=$(bashio::config 'broker')
  API_KEY=$(bashio::config 'api_key')
  API_SECRET=$(bashio::config 'api_secret')
  PAPER_TRADING=$(bashio::config 'paper_trading')
  EXCHANGES=$(bashio::config 'exchanges')
  SYMBOLS_NYSE=$(bashio::config 'symbols_nyse')
  SYMBOLS_LSE=$(bashio::config 'symbols_lse')
  MAX_POSITION_VALUE=$(bashio::config 'max_position_value')
  STOP_LOSS_PCT=$(bashio::config 'stop_loss_pct')
  TAKE_PROFIT_PCT=$(bashio::config 'take_profit_pct')
  MAX_DAILY_LOSS_PCT=$(bashio::config 'max_daily_loss_pct')
  STRATEGY=$(bashio::config 'strategy')
  ORB_MINUTES=$(bashio::config 'orb_minutes')
  PRE_MARKET_MINUTES=$(bashio::config 'pre_market_minutes')
  CLOSE_MINUTES=$(bashio::config 'close_minutes')
  CHECK_INTERVAL=$(bashio::config 'check_interval')
  DIRECTA_HOST=$(bashio::config 'directa_host')
  TELEGRAM_RELAY_URL=$(bashio::config 'telegram_relay_url')
  TELEGRAM_API_KEY=$(bashio::config 'telegram_api_key')
fi

echo "Broker:           $BROKER"
echo "Paper trading:    $PAPER_TRADING"
echo "Exchanges:        $EXCHANGES"
echo "NYSE symbols:     $SYMBOLS_NYSE"
echo "LSE symbols:      $SYMBOLS_LSE"
echo "Strategy:         $STRATEGY"
echo "Stop loss:        ${STOP_LOSS_PCT}%"
echo "Take profit:      ${TAKE_PROFIT_PCT}%"
echo "Max daily loss:   ${MAX_DAILY_LOSS_PCT}%"
echo ""

# --------------------------------------------------------------------------
# Directa: start Darwin CommandLine (DCL.jar) as a subprocess
#
# Darwin is auto-started inside the container when directa_host=127.0.0.1
# (the default). If directa_host points to an external machine, Darwin is
# assumed to be already running there and auto-start is skipped.
# --------------------------------------------------------------------------
DCL_PID=""

if [[ "$BROKER" == "directa" && "${DIRECTA_HOST:-127.0.0.1}" == "127.0.0.1" ]]; then
  DCL_JAR="/data/DCL.jar"
  DCL_LOG="/data/darwin.log"
  DCL_URL="https://app1.directatrading.com/dcl/RilascioDCL/DCL.jar"

  # Download DCL.jar on first run; cached in /data for subsequent restarts
  if [ ! -f "$DCL_JAR" ]; then
    echo "Downloading Darwin CommandLine (DCL.jar)..."
    if ! curl -fsSL -o "$DCL_JAR" "$DCL_URL"; then
      echo "ERROR: Failed to download DCL.jar from $DCL_URL"
      echo "       Check your internet connection or copy DCL.jar manually to /data/DCL.jar"
      exit 1
    fi
    echo "DCL.jar downloaded and saved to $DCL_JAR"
  else
    echo "Using cached Darwin CommandLine from $DCL_JAR"
  fi

  # Build DCL arguments: userId password [-test]
  if [[ "${PAPER_TRADING:-true}" == "true" ]]; then
    echo "Directa Darwin:   starting in TEST environment (no real orders)"
    java -jar "$DCL_JAR" "$API_KEY" "$API_SECRET" -test >> "$DCL_LOG" 2>&1 &
  else
    echo "Directa Darwin:   starting in LIVE environment ⚠️  REAL MONEY"
    java -jar "$DCL_JAR" "$API_KEY" "$API_SECRET" >> "$DCL_LOG" 2>&1 &
  fi
  DCL_PID=$!
  echo "Darwin PID: $DCL_PID  (logs → $DCL_LOG)"

  # Wait until Darwin's trading socket (port 10002) accepts connections
  echo "Waiting for Darwin to be ready (up to 60s)..."
  DARWIN_READY=false
  for i in $(seq 1 60); do
    if nc -z 127.0.0.1 10002 2>/dev/null; then
      DARWIN_READY=true
      echo "Darwin is ready (${i}s elapsed)."
      break
    fi
    # Abort early if Darwin exited unexpectedly
    if ! kill -0 "$DCL_PID" 2>/dev/null; then
      echo "ERROR: Darwin exited unexpectedly. Last 20 lines of $DCL_LOG:"
      tail -20 "$DCL_LOG"
      exit 1
    fi
    sleep 1
  done

  if [[ "$DARWIN_READY" == "false" ]]; then
    echo "ERROR: Darwin did not become ready within 60 seconds."
    echo "Last 20 lines of $DCL_LOG:"
    tail -20 "$DCL_LOG"
    kill "$DCL_PID" 2>/dev/null
    exit 1
  fi

elif [[ "$BROKER" == "directa" ]]; then
  echo "Directa Darwin:   using external Darwin at ${DIRECTA_HOST}:10002"
fi

# --------------------------------------------------------------------------
# Cleanup handler: stop Darwin when the bot exits
# --------------------------------------------------------------------------
cleanup() {
  echo "Shutting down..."
  if [[ -n "$DCL_PID" ]] && kill -0 "$DCL_PID" 2>/dev/null; then
    echo "Stopping Darwin CommandLine (PID $DCL_PID)..."
    kill "$DCL_PID"
    wait "$DCL_PID" 2>/dev/null
    echo "Darwin stopped."
  fi
}
trap cleanup EXIT INT TERM

echo "Starting Trading Bot..."
python3 main.py \
  --broker "$BROKER" \
  --api-key "$API_KEY" \
  --api-secret "$API_SECRET" \
  --paper-trading "$PAPER_TRADING" \
  --exchanges "$EXCHANGES" \
  --symbols-nyse "$SYMBOLS_NYSE" \
  --symbols-lse "$SYMBOLS_LSE" \
  --max-position-value "$MAX_POSITION_VALUE" \
  --stop-loss-pct "$STOP_LOSS_PCT" \
  --take-profit-pct "$TAKE_PROFIT_PCT" \
  --max-daily-loss-pct "$MAX_DAILY_LOSS_PCT" \
  --strategy "$STRATEGY" \
  --orb-minutes "$ORB_MINUTES" \
  --pre-market-minutes "$PRE_MARKET_MINUTES" \
  --close-minutes "$CLOSE_MINUTES" \
  --check-interval "$CHECK_INTERVAL" \
  --directa-host "${DIRECTA_HOST:-127.0.0.1}" \
  --telegram-relay-url "${TELEGRAM_RELAY_URL:-}" \
  --telegram-api-key "${TELEGRAM_API_KEY:-}"
