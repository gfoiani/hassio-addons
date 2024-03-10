#!/usr/bin/env python3
# Duino-Coin HASSIO Miner. Based on MineCryptoOnWifiRouter by BastelPichi

import hashlib
import os
import socket
import sys
import time
import requests
from enum import Enum
import signal
import sys

stop_thread = False  # Flag to signal the thread to stop
script, username, mining_key, efficiency, idx = sys.argv

def signal_handler(sig, frame):
  global stop_thread
  stop_thread = True
  print(f"Exiting Thread {idx}")
  sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

class Feedback(Enum):
  GOOD = "GOOD"
  BAD = "BAD"

DEFAULT_NODE_ADDRESS = "server.duinocoin.com"
DEFAULT_NODE_PORT = 2813
SOFTWARE_NAME = "HASSIO Miner"

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

  eff = 0
  for (upper, lower), eff_map in efficiency_mapping.items():
    if upper > eff_value >= lower:
      eff = eff_map
      break
  return eff

def fetch_pools():
  while True:
    try:
      response = requests.get(f"https://{DEFAULT_NODE_ADDRESS}/getPool").json()
      NODE_ADDRESS = response["ip"]
      NODE_PORT = response["port"]
      return NODE_ADDRESS, NODE_PORT
    except Exception as e:
      print(f"{current_time()}: Error retrieving mining node, retrying in 15s")
      time.sleep(15)

def mine(username, mining_key, index, soc):
    try:
      import libducohasher
      fasthash_supported = True
    except Exception as e:
      fasthash_supported = False

    identifier = socket.gethostname().split(".")[0]
    efficiency = get_efficiency()
    while not stop_thread:
      soc.send(bytes(f"JOB,{str(username)},LOW,{mining_key}", encoding="utf8"))

      job = soc.recv(1024).decode().rstrip("\n")
      job = job.split(",")
      last_h = job[0]
      exp_h = job[1]
      difficulty = job[2]
      if fasthash_supported:
        time_start = time.time()

        hasher = libducohasher.DUCOHasher(bytes(last_h, encoding='ascii'))
        result = hasher.DUCOS1(
            bytes(bytearray.fromhex(exp_h)), int(difficulty), efficiency)

        time_elapsed = time.time() - time_start
        hashrate = result / time_elapsed
      else:
        hashingStartTime = time.time()
        base_hash = hashlib.sha1(str(last_h).encode("ascii"))

        for result in range(100 * int(difficulty) + 1):
          temp_hash = base_hash.copy()
          temp_hash.update(str(result).encode("ascii"))
          ducos1 = temp_hash.hexdigest()

          if exp_h == ducos1:
            hashingStopTime = time.time()
            timeDifference = hashingStopTime - hashingStartTime
            hashrate = result / timeDifference
            break

      # Send feedback
      soc.send(bytes(f"{str(result)},{str(hashrate)},{SOFTWARE_NAME},{identifier}-{idx}", encoding="utf8"))
      feedback = soc.recv(1024).decode().rstrip("\n")

      if feedback == Feedback.GOOD.value:
        print(f"{current_time()}: Accepted share",
              result,
              "Hashrate",
              int(hashrate/1000),
              "kH/s",
              "Difficulty",
              difficulty)
      elif feedback == Feedback.BAD.value:
        print(f"{current_time()}: Rejected share",
              result,
              "Hashrate",
              int(hashrate/1000),
              "kH/s",
              "Difficulty",
              difficulty)

def main():
  soc = socket.socket()

  while True:
    try:
      print(f"{current_time()}: Running Thread {idx}")
      print(f"{current_time()}: Searching for fastest connection to the server")

      try:
        NODE_ADDRESS, NODE_PORT = fetch_pools()
      except Exception as e:
        NODE_ADDRESS = DEFAULT_NODE_ADDRESS
        NODE_PORT = DEFAULT_NODE_PORT
        print(f"{current_time()}: Using default server port: {DEFAULT_NODE_PORT} and address: {DEFAULT_NODE_ADDRESS}")

      soc.connect((str(NODE_ADDRESS), int(NODE_PORT)))
      print(f"{current_time()}: Fastest connection found")
      server_version = soc.recv(100).decode()
      print(f"{current_time()}: Server Version: {server_version}")

      mine(username, mining_key, idx, soc)
    except Exception as e:
        print(f"{current_time()}: Error occurred: {e}, restarting in 5s.")
        time.sleep(5)
        soc.close()
        soc = socket.socket()

if __name__ == "__main__":
  main()
