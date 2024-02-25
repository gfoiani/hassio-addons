import threading
import subprocess

from sys import argv

import signal
import sys

def signal_handler(sig, frame):
  print('Exiting main script')
  sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

script, threads_count, username, mining_key = argv

MINER_SCRIPT = "miner.py"

def run_script(script_name, thread_index, username, mining_key):
  subprocess.run(["python3", script_name, thread_index, username, mining_key])

if __name__ == "__main__":
  thread_list = []

  for idx in range(0, int(threads_count)):
    thread = threading.Thread(target=run_script, args=(MINER_SCRIPT, str(idx + 1), username, mining_key))
    thread_list.append(thread)

  for thread in thread_list:
    thread.start()
  for thread in thread_list:
    thread.join()

  print("All scripts have finished executing.")
