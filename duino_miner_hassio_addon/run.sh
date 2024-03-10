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

# echo "Downloading Rust . . ."
# curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs/ | sh -s -- -y
# source $HOME/.cargo/env
# echo "Download duino fasthash:"
# wget https://server.duinocoin.com/fasthash/libducohash.tar.gz

# echo "Unpack it:"
# tar -xvf libducohash.tar.gz
# echo "Go to the dir:"
# cd libducohash
# echo "Compile it:"
# rustup target add x86_64-unknown-linux-musl
# cargo build --target x86_64-unknown-linux-musl --release
# echo("Extract the module:")
# mv target/release/libducohasher.so ..
# cd ..

if [[ $LOCAL_DEPOLY != "true" ]]; then
  USERNAME=$(bashio::config 'username')
  MINING_KEY=$(bashio::config 'mining_key')
  EFFICIENCY=$(bashio::config 'efficiency')
  THREADS_COUNT=$(bashio::config 'threads_count')
fi

echo "Username is: " $USERNAME
echo "Mining key is: " $MINING_KEY
echo "Efficiency is: " $EFFICIENCY
echo "Threads count is: " $THREADS_COUNT

echo "Run Miner.py . . ."
python3 main.py $USERNAME $MINING_KEY $EFFICIENCY $THREADS_COUNT
