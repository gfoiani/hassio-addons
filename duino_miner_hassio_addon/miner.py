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
script, idx, username, mining_key = sys.argv

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
    identifier = socket.gethostname().split(".")[0]
    while not stop_thread:
      soc.send(bytes(f"JOB,{str(username)},LOW,{mining_key}", encoding="utf8"))

      job = soc.recv(1024).decode().rstrip("\n")
      job = job.split(",")
      difficulty = job[2]

      hashingStartTime = time.time()
      base_hash = hashlib.sha1(str(job[0]).encode("ascii"))

      for result in range(100 * int(difficulty) + 1):
        temp_hash = base_hash.copy()
        temp_hash.update(str(result).encode("ascii"))
        ducos1 = temp_hash.hexdigest()

        if job[1] == ducos1:
          hashingStopTime = time.time()
          timeDifference = hashingStopTime - hashingStartTime
          hashrate = result / timeDifference

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
            break
          elif feedback == Feedback.BAD.value:
            print(f"{current_time()}: Rejected share",
                  result,
                  "Hashrate",
                  int(hashrate/1000),
                  "kH/s",
                  "Difficulty",
                  difficulty)
            break

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
