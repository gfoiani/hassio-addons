#!/usr/bin/with-contenv bashio

set +u

echo "Hassio Duco-Miner."
echo "Based on MineCryptoOnWifiRouter by BastelPichi"
echo ""

echo "Creating venv . . ."
python3 -m venv ./venv
echo "Activating venv . . ."
source ./venv/bin/activate
echo "Installing requests . . ."
pip3 install requests

if [[ $LOCAL_DEPLOY != "true" ]]; then
  USERNAME=$(bashio::config 'username')
  MINING_KEY=$(bashio::config 'mining_key')
  EFFICIENCY=$(bashio::config 'efficiency')
  THREADS_COUNT=$(bashio::config 'threads_count')
  LOG_LEVEL=$(bashio::config 'log_level')
  MINER_NAME=$(bashio::config 'miner_name')
fi

echo "Username is: " $USERNAME
echo "Mining key is: " $MINING_KEY
echo "Efficiency is: " $EFFICIENCY
echo "Threads count is: " $THREADS_COUNT
echo "Log level is: " $LOG_LEVEL
echo "Miner name is: " $MINER_NAME

echo "Run Miner.py . . ."
python3 main.py "$USERNAME" "$MINING_KEY" "$EFFICIENCY" "$THREADS_COUNT" "$LOG_LEVEL" "$MINER_NAME"
