#!/usr/bin/env python3
# Duino-Coin HASSIO Miner. Based on MineCryptoOnWifiRouter by BastelPichi

import hashlib
import socket
import sys
import time
import requests
import signal

stop_thread = False  # Flag to signal the thread to stop
script, username, mining_key, efficiency, idx, *_rest = sys.argv
log_level = _rest[0] if _rest else "minimal"

def signal_handler(sig, frame):
  global stop_thread
  stop_thread = True
  print(f"Exiting Thread {idx}")
  sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

DEFAULT_NODE_ADDRESS = "server.duinocoin.com"
DEFAULT_NODE_PORT = 2813
SOFTWARE_NAME = "Raspberry Pi Miner"
BUFFER_SIZE = 4096  # Increased from 1024 to handle larger server responses

def current_time():
  return time.strftime("%H:%M:%S", time.localtime())

def get_efficiency():
  efficiency_mapping = {
      (99, 90): 0.005,
      (90, 70): 0.1,
      (70, 50): 0.8,
      (50, 30): 1.8,
      (30, 1): 3
  }
  eff_value = int(efficiency)
  for (upper, lower), eff_map in efficiency_mapping.items():
    if upper > eff_value >= lower:
      return eff_map
  return 0  # efficiency=100 → no sleep, maximum hash rate

def fetch_pools():
  while True:
    try:
      response = requests.get(f"https://{DEFAULT_NODE_ADDRESS}/getPool").json()
      return response["ip"], response["port"]
    except Exception:
      print(f"{current_time()}: Error retrieving mining node, retrying in 15s")
      time.sleep(15)

def mine(username, mining_key, index, soc):
    try:
        import libducohasher
        fasthash_supported = True
    except ImportError:
        fasthash_supported = False

    identifier = socket.gethostname().split(".")[0]
    eff_sleep = get_efficiency()

    # Pre-encode static parts to avoid repeated allocations in the hot loop
    job_request = f"JOB,{username},LOW,{mining_key}".encode("utf-8")
    result_suffix = f",{SOFTWARE_NAME},{identifier} Thread {index}".encode("utf-8")

    while not stop_thread:
        soc.send(job_request)

        job = soc.recv(BUFFER_SIZE).decode().rstrip("\n").split(",")
        last_h, exp_h, difficulty = job[:3]
        difficulty_int = int(difficulty)  # parse once, reuse for both range and hasher

        if fasthash_supported:
            time_start = time.time()
            hasher = libducohasher.DUCOHasher(last_h.encode('ascii'))
            result = hasher.DUCOS1(bytes.fromhex(exp_h), difficulty_int, int(eff_sleep))
            time_elapsed = time.time() - time_start
            hashrate = result / time_elapsed if time_elapsed > 0 else 0
        else:
            base_hash = hashlib.sha1(last_h.encode("ascii"))
            hashing_start_time = time.time()

            result = 0
            for result in range(100 * difficulty_int + 1):
                temp_hash = base_hash.copy()
                temp_hash.update(str(result).encode("ascii"))
                if exp_h == temp_hash.hexdigest():
                    break

            time_elapsed = time.time() - hashing_start_time
            hashrate = result / time_elapsed if time_elapsed > 0 else 0

            if eff_sleep:
                time.sleep(eff_sleep)

        hashrate_str = (str(int(hashrate / 1000)) + "kH/s").encode("utf-8")
        soc.send(str(result).encode("utf-8") + b"," + hashrate_str + result_suffix)

        feedback_parts = soc.recv(BUFFER_SIZE).decode().rstrip("\n").split(",")
        status = feedback_parts[0]
        reason = feedback_parts[1] if len(feedback_parts) > 1 else ""

        if status == "GOOD":
            if log_level == "verbose":
                print(f"{current_time()}: Thread {index} | Accepted | result={result} | {hashrate_str.decode()} | diff={difficulty}")
        elif status == "BLOCK":
            print(f"{current_time()}: Thread {index} | Block found! | result={result} | {hashrate_str.decode()} | diff={difficulty}")
        elif status == "BAD":
            reason_str = f" | reason={reason}" if reason else ""
            print(f"{current_time()}: Thread {index} | Rejected | result={result} | {hashrate_str.decode()} | diff={difficulty}{reason_str}")

def main():
  while True:
    # Create a fresh socket each iteration so reconnects work cleanly
    soc = socket.socket()
    # Disable Nagle's algorithm: sends each packet immediately, reducing round-trip latency
    soc.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    # Timeout during connect so we don't block forever on unreachable hosts
    soc.settimeout(30)

    try:
      print(f"{current_time()}: Running Thread {idx}")
      print(f"{current_time()}: Searching for fastest connection to the server")

      try:
        NODE_ADDRESS, NODE_PORT = fetch_pools()
      except Exception:
        NODE_ADDRESS = DEFAULT_NODE_ADDRESS
        NODE_PORT = DEFAULT_NODE_PORT
        print(f"{current_time()}: Using default server {DEFAULT_NODE_ADDRESS}:{DEFAULT_NODE_PORT}")

      soc.connect((str(NODE_ADDRESS), int(NODE_PORT)))
      soc.settimeout(None)  # Back to blocking mode after connect
      print(f"{current_time()}: Fastest connection found")
      server_version = soc.recv(100).decode()
      print(f"{current_time()}: Server Version: {server_version}")

      mine(username, mining_key, idx, soc)
    except Exception as e:
        print(f"{current_time()}: Error occurred: {e}, restarting in 5s.")
        time.sleep(5)
    finally:
        soc.close()

if __name__ == "__main__":
  main()
