#!/usr/bin/with-contenv bashio

set +u
set +H   # disable history expansion (prevents ! in passwords from being misinterpreted)

echo "=========================================="
echo "  Day Trading Bot - NYSE & LSE"
echo "=========================================="
echo ""


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
# Directa: launch Darwin via DCL.jar
#
# DCL.jar is a launcher: it downloads Engine.jar, spawns it with the -mc
# (machine communication) flag that opens socket ports 10001/10002/10003,
# then exits.  We run DCL.jar synchronously (~5 s), then locate the
# Engine.jar (StartEngine) process it left running in the background.
#
# Darwin is auto-started inside the container when directa_host=127.0.0.1
# (the default). If directa_host points to an external machine, Darwin is
# assumed to be already running there and auto-start is skipped.
# --------------------------------------------------------------------------
ENGINE_PID=""

if [[ "$BROKER" == "directa" && "${DIRECTA_HOST:-127.0.0.1}" == "127.0.0.1" ]]; then
  ENGINE_DIR="/root/.directa/engine"
  DCL_JAR="$ENGINE_DIR/DCL.jar"
  ENGINE_LOG="/data/darwin.log"
  DIRECTA_BASE="https://app1.directatrading.com/dcl/RilascioDCL"

  mkdir -p "$ENGINE_DIR"

  # Always download DCL.jar to ensure the latest version.
  echo "Downloading Directa DCL.jar..."
  if ! curl -fsSL -o "$DCL_JAR" "$DIRECTA_BASE/DCL.jar"; then
    echo "ERROR: Failed to download DCL.jar"
    exit 1
  fi

  # Truncate log so this session's output is isolated from previous runs
  > "$ENGINE_LOG"

  # Stream Darwin log to stdout in real-time for visibility
  tail -f "$ENGINE_LOG" &
  TAIL_PID=$!

  # Run DCL.jar synchronously — it downloads Engine.jar, spawns StartEngine
  # with the -mc socket-server flag, prints "Fine del comando avvio" and exits.
  if [[ "${PAPER_TRADING:-true}" == "true" ]]; then
    echo "Directa Darwin:   starting in TEST environment (no real orders)"
    java -Djava.awt.headless=true -jar "$DCL_JAR" \
      "$API_KEY" "$API_SECRET" -test < /dev/null >> "$ENGINE_LOG" 2>&1
  else
    echo "Directa Darwin:   starting in LIVE environment ⚠️  REAL MONEY"
    java -Djava.awt.headless=true -jar "$DCL_JAR" \
      "$API_KEY" "$API_SECRET" < /dev/null >> "$ENGINE_LOG" 2>&1
  fi

  # DCL.jar has exited — locate the Engine.jar (StartEngine) process it spawned.
  ENGINE_PID=$(pgrep -f "directa.standalone.StartEngine" 2>/dev/null | head -1)
  if [[ -z "$ENGINE_PID" ]]; then
    kill "$TAIL_PID" 2>/dev/null
    echo "ERROR: DCL.jar finished but StartEngine is not running. Full $ENGINE_LOG:"
    cat "$ENGINE_LOG"
    exit 1
  fi
  echo "Darwin (Engine) PID: $ENGINE_PID  (logs → $ENGINE_LOG)"

  # Wait until Darwin's trading socket (port 10002) accepts connections
  echo "Waiting for Darwin to be ready (up to 90s)..."
  DARWIN_READY=false
  for i in $(seq 1 90); do
    if nc -z 127.0.0.1 10002 2>/dev/null; then
      DARWIN_READY=true
      kill "$TAIL_PID" 2>/dev/null
      echo "Darwin is ready (${i}s elapsed)."
      break
    fi
    # Abort early if Engine.jar exited unexpectedly
    if ! kill -0 "$ENGINE_PID" 2>/dev/null; then
      sleep 1  # let tail flush remaining output
      kill "$TAIL_PID" 2>/dev/null
      echo "ERROR: Darwin Engine (StartEngine) exited unexpectedly. Full $ENGINE_LOG:"
      cat "$ENGINE_LOG"
      exit 1
    fi
    sleep 1
  done

  if [[ "$DARWIN_READY" == "false" ]]; then
    kill "$TAIL_PID" 2>/dev/null
    echo "ERROR: Darwin Engine did not become ready within 90 seconds. Full $ENGINE_LOG:"
    cat "$ENGINE_LOG"
    kill "$ENGINE_PID" 2>/dev/null
    exit 1
  fi

elif [[ "$BROKER" == "directa" ]]; then
  echo "Directa Darwin:   using external Darwin at ${DIRECTA_HOST}:10002"
fi

# --------------------------------------------------------------------------
# Cleanup handler: stop Darwin Engine when the bot exits
# --------------------------------------------------------------------------
cleanup() {
  echo "Shutting down..."
  if [[ -n "$ENGINE_PID" ]] && kill -0 "$ENGINE_PID" 2>/dev/null; then
    echo "Stopping Darwin Engine (PID $ENGINE_PID)..."
    kill "$ENGINE_PID"
    wait "$ENGINE_PID" 2>/dev/null
    echo "Darwin stopped."
  fi
}
trap cleanup EXIT INT TERM

echo "Starting Trading Bot..."
python3 -u main.py \
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
