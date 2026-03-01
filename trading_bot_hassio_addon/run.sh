#!/usr/bin/with-contenv bashio

set +u
set +H   # disable history expansion (prevents ! in passwords from being misinterpreted)
set +e   # bashio enables errexit; disable it so non-zero exit codes don't kill the script

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

  DARWIN_READY=false
  DARWIN_ATTEMPT=0

  # Retry loop: Darwin exits cleanly when the market is closed (weekend/holiday/
  # outside session hours).  We sleep until the next likely opening and try again.
  while [[ "$DARWIN_READY" == "false" ]]; do
    DARWIN_ATTEMPT=$(( DARWIN_ATTEMPT + 1 ))
    ENGINE_PID=""
    TAIL_PID=""
    TAIL2_PID=""

    mkdir -p "$ENGINE_DIR"
    # Truncate log to isolate this attempt's output from previous ones
    > "$ENGINE_LOG"

    if (( DARWIN_ATTEMPT > 1 )); then
      echo ""
      echo "--- Darwin startup attempt #${DARWIN_ATTEMPT} ---"
    fi

    # Stream Darwin log to stdout in real-time for visibility
    tail -f "$ENGINE_LOG" &
    TAIL_PID=$!

    # Track whether ENGINE_PID is a direct child of this shell (needed for wait).
    # LIVE mode spawns with & (direct child); TEST mode finds pid via pgrep (not a child).
    DARWIN_DIRECT_CHILD=false

    if [[ "${PAPER_TRADING:-true}" == "true" ]]; then
      # ------------------------------------------------------------------------
      # TEST mode: use DCL.jar launcher — it handles the -test flag internally
      # (connects to Directa's simulation servers and sets up the test environment).
      # ------------------------------------------------------------------------
      echo "Downloading Directa DCL.jar..."
      if ! curl -fsSL -o "$DCL_JAR" "$DIRECTA_BASE/DCL.jar"; then
        kill "$TAIL_PID" 2>/dev/null
        echo "ERROR: Failed to download DCL.jar"
        exit 1
      fi
      echo "Directa Darwin:   starting in TEST environment (no real orders)"
      java -Djava.awt.headless=true -jar "$DCL_JAR" \
        "$API_KEY" "$API_SECRET" -test < /dev/null >> "$ENGINE_LOG" 2>&1

      # DCL.jar has exited — locate the StartEngine process it spawned.
      ENGINE_PID=$(pgrep -f "directa.standalone.StartEngine" 2>/dev/null | head -1)
      if [[ -z "$ENGINE_PID" ]]; then
        kill "$TAIL_PID" 2>/dev/null
        echo "ERROR: DCL.jar finished but StartEngine is not running. Full $ENGINE_LOG:"
        cat "$ENGINE_LOG"
        exit 1
      fi
    else
      # ------------------------------------------------------------------------
      # LIVE mode: download Engine.jar and gson.jar directly and launch
      # StartEngine ourselves as a managed background process.
      #
      # DCL.jar spawns StartEngine as a fully detached process (closed I/O,
      # different session), which prevents it from initialising correctly inside
      # a container.  Running StartEngine directly with controlled stdin/stdout
      # avoids this problem.
      # ------------------------------------------------------------------------
      # Skip download if jars are already present (subsequent retry attempts)
      if [[ ! -f "$ENGINE_DIR/Engine.jar" ]]; then
        echo "Downloading Directa Engine.jar..."
        if ! curl -fsSL -o "$ENGINE_DIR/Engine.jar" "$DIRECTA_BASE/Engine.jar"; then
          kill "$TAIL_PID" 2>/dev/null
          echo "ERROR: Failed to download Engine.jar"
          exit 1
        fi
      fi
      if [[ ! -f "$ENGINE_DIR/gson.jar" ]]; then
        echo "Downloading Directa gson.jar..."
        if ! curl -fsSL -o "$ENGINE_DIR/gson.jar" "$DIRECTA_BASE/gson.jar"; then
          kill "$TAIL_PID" 2>/dev/null
          echo "ERROR: Failed to download gson.jar"
          exit 1
        fi
      fi
      echo "Directa Darwin:   starting in LIVE environment ⚠️  REAL MONEY"
      java -Djava.awt.headless=true \
        -classpath "$ENGINE_DIR/Engine.jar:$ENGINE_DIR/gson.jar" \
        directa.standalone.StartEngine "$API_KEY" "$API_SECRET" -log -mc \
        < /dev/null >> "$ENGINE_LOG" 2>&1 &
      ENGINE_PID=$!
      DARWIN_DIRECT_CHILD=true
      if [[ -z "$ENGINE_PID" ]]; then
        kill "$TAIL_PID" 2>/dev/null
        echo "ERROR: Failed to start StartEngine. Full $ENGINE_LOG:"
        cat "$ENGINE_LOG"
        exit 1
      fi
    fi

    echo "Darwin (Engine) PID: $ENGINE_PID  (logs → $ENGINE_LOG)"

    # Also stream Engine.jar's own log file (written by the -log flag) if it exists.
    ENGINE_LOG2="$ENGINE_DIR/StartEngine.log"
    if [[ -f "$ENGINE_LOG2" ]]; then
      tail -f "$ENGINE_LOG2" &
      TAIL2_PID=$!
    else
      TAIL2_PID=""
      # Wait briefly then start tailing if the file appears
      (sleep 3; if [[ -f "$ENGINE_LOG2" ]]; then tail -f "$ENGINE_LOG2"; fi) &
      TAIL2_PID=$!
    fi

    echo "Waiting for Darwin to be ready (up to 300s)..."
    DARWIN_EXITED_CLEANLY=false

    for i in $(seq 1 300); do
      P10001=false; P10002=false; P10003=false
      nc -z 127.0.0.1 10001 2>/dev/null && P10001=true
      nc -z 127.0.0.1 10002 2>/dev/null && P10002=true
      nc -z 127.0.0.1 10003 2>/dev/null && P10003=true
      # Wait for port 10002 (TRADING) only — the free-tier MC API.
      # Ports 10001 (DATAFEED) and 10003 (HISTORICAL) require a paid data subscription
      # and may never open; market data will be fetched from an alternative source.
      if [[ "$P10002" == "true" ]]; then
        DARWIN_READY=true
        kill "$TAIL_PID" 2>/dev/null
        kill "$TAIL2_PID" 2>/dev/null
        echo "Darwin is ready (${i}s elapsed). Trading port 10002 open. (10001=$P10001 10003=$P10003)"
        break
      fi
      # Detect early Darwin exit
      if ! kill -0 "$ENGINE_PID" 2>/dev/null; then
        sleep 1  # let tail flush remaining output
        kill "$TAIL_PID" 2>/dev/null
        kill "$TAIL2_PID" 2>/dev/null
        # Capture exit code only for direct children (LIVE mode).
        # pgrep'd pids (TEST mode) are not children of this shell.
        if [[ "$DARWIN_DIRECT_CHILD" == "true" ]]; then
          wait "$ENGINE_PID" 2>/dev/null; DARWIN_EXIT=$?
        else
          DARWIN_EXIT=0  # TEST mode: assume clean exit
        fi
        # Any Darwin exit (0 or non-zero) is treated as "session ended — retry".
        # Darwin exits with non-zero on some versions/configurations when the
        # market is closed; this is NOT a fatal error.
        if [[ "$DARWIN_EXIT" -eq 0 ]]; then
          echo "INFO: Darwin exited cleanly (exit 0)."
        else
          echo "INFO: Darwin exited with code $DARWIN_EXIT."
          echo "      Non-zero exits occur when the market is closed on some Darwin versions."
          echo "--- Last 10 lines of darwin.log ---"
          tail -10 "$ENGINE_LOG"
          echo "--- end ---"
        fi
        DARWIN_EXITED_CLEANLY=true
        break
      fi
      # Print progress every 30 seconds, including diagnostics
      if (( i % 30 == 0 )); then
        echo "Still waiting for Darwin... (${i}s elapsed)"
        echo "--- Darwin MC port status ---"
        echo "  Port 10001 (DATAFEED):   $( [[ "$P10001" == "true" ]] && echo OPEN || echo closed )"
        echo "  Port 10002 (TRADING):    $( [[ "$P10002" == "true" ]] && echo OPEN || echo closed )"
        echo "  Port 10003 (HISTORICAL): $( [[ "$P10003" == "true" ]] && echo OPEN || echo closed )"
        echo "--- end port status ---"
        if [[ -d "$ENGINE_DIR/logDCL" ]]; then
          echo "--- logDCL/ contents ---"
          ls -la "$ENGINE_DIR/logDCL/" 2>/dev/null
          for f in "$ENGINE_DIR/logDCL/"*; do
            [[ -f "$f" ]] && echo "=== $f ===" && tail -30 "$f"
          done
          echo "--- end logDCL ---"
        fi
        echo "--- Last 5 lines of darwin.log ---"
        tail -5 "$ENGINE_LOG"
        echo "--- end darwin.log ---"
        echo "--- Files in $ENGINE_DIR ---"
        ls -la "$ENGINE_DIR/" 2>/dev/null
        echo "--- end engine dir ---"
        echo "--- /proc/net/tcp ---"
        cat /proc/net/tcp 2>/dev/null || echo "(not available)"
        echo "--- /proc/net/tcp6 ---"
        cat /proc/net/tcp6 2>/dev/null || echo "(not available)"
        echo "--- end TCP ---"
      fi
      sleep 1
    done

    # Port 10002 opened — proceed to the trading bot
    if [[ "$DARWIN_READY" == "true" ]]; then
      break
    fi

    # 300-second timeout: Darwin still running but port 10002 never opened
    if [[ "$DARWIN_EXITED_CLEANLY" == "false" ]]; then
      kill "$TAIL_PID" 2>/dev/null
      kill "$TAIL2_PID" 2>/dev/null
      echo "ERROR: Darwin Engine did not become ready within 300 seconds (port 10002 never opened). Full $ENGINE_LOG:"
      cat "$ENGINE_LOG"
      if [[ -f "$ENGINE_LOG2" ]]; then
        echo "Full $ENGINE_LOG2:"
        cat "$ENGINE_LOG2"
      fi
      kill "$ENGINE_PID" 2>/dev/null
      exit 1
    fi

    # --------------------------------------------------------------------------
    # Darwin exited cleanly (exit 0): the market session is not active.
    # Compute how long to sleep before the next attempt:
    #   Weekend (Sat=6, Sun=7) → sleep until Monday 07:30 UTC
    #   Weekday                → retry in 30 minutes
    # --------------------------------------------------------------------------
    DOW=$(date -u +%u)  # 1=Mon … 7=Sun
    H=$(date -u +%H); M=$(date -u +%M); S=$(date -u +%S)
    SECS_NOW=$(( 10#$H * 3600 + 10#$M * 60 + 10#$S ))
    TARGET_UTC=27000   # 07:30 UTC = 7*3600 + 30*60 (30 min before LSE open)

    if [[ "$DOW" -ge 6 ]]; then
      # Weekend: (days to next Monday) * 86400 - seconds elapsed today + 07:30
      # Sat(6) → 2 days to Monday;  Sun(7) → 1 day to Monday
      SLEEP_SECS=$(( (8 - DOW) * 86400 - SECS_NOW + TARGET_UTC ))
      SLEEP_H=$(( SLEEP_SECS / 3600 ))
      SLEEP_M=$(( (SLEEP_SECS % 3600) / 60 ))
      echo ""
      echo "INFO: Darwin exited cleanly — market closed (weekend)."
      echo "Sleeping ${SLEEP_H}h ${SLEEP_M}m until Monday 07:30 UTC."
      echo "The bot will automatically reconnect when the market opens."
    else
      SLEEP_SECS=1800
      echo ""
      echo "INFO: Darwin exited cleanly — no active trading session right now."
      echo "Retrying in 30 minutes..."
    fi

    sleep "$SLEEP_SECS"

  done  # while DARWIN_READY == false

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
