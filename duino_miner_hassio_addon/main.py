import threading
import subprocess
import signal
import sys

from fasthash import Fasthash
from sys import argv

def signal_handler(sig, frame):
  print('Exiting main script')
  sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

script, username, mining_key, efficiency, threads_count, *_rest = argv
log_level = _rest[0] if _rest else "minimal"

MINER_SCRIPT = "miner.py"

def run_script(script_name, username, mining_key, efficiency, thread_index, log_level):
  subprocess.run(["python3", "-u", script_name, username, mining_key, efficiency, thread_index, log_level])

if __name__ == "__main__":
  # Load fasthash
  Fasthash.load()
  Fasthash.init()

  thread_list = []

  for idx in range(0, int(threads_count)):
    thread = threading.Thread(target=run_script, args=(MINER_SCRIPT, username, mining_key, efficiency, str(idx + 1), log_level))
    thread_list.append(thread)

  for thread in thread_list:
    thread.start()
  for thread in thread_list:
    thread.join()

  print("All scripts have finished executing.")
