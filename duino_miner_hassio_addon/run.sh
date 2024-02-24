#!/usr/bin/with-contenv bashio

echo "Hassio Duco-Miner."
echo "Based on MineCryptoOnWifiRouter by BastelPichi  "
echo ""

echo "Creating venv . . ."
python3 -m venv ./venv
echo "Activating venv . . ."
source ./venv/bin/activate
echo "Installing requests . . ."
pip3 install requests

THREADS_COUNT=$(bashio::config 'threads_count')
USERNAME=$(bashio::config 'username')
MINING_KEY=$(bashio::config 'mining_key')

echo "Username is: " $USERNAME
echo "Mining key is: " $MINING_KEY

echo "Run Miner.py . . ."
python3 main.py $THREADS_COUNT $USERNAME $MINING_KEY
