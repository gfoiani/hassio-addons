import threading
import subprocess

from sys import argv

script, threads_count, username, mining_key = argv

def run_script(script_name, thread_index, username, mining_key):
    subprocess.run(["python3", script_name, thread_index, username, mining_key])

if __name__ == "__main__":
    thread_list = []

    for idx in range(0, int(threads_count)):
      thread = threading.Thread(target=run_script, args=("miner.py", str(idx + 1), username, mining_key))
      thread_list.append(thread)

    for thread in thread_list:
      thread.start()
    for thread in thread_list:
      thread.join()

    print("All scripts have finished executing.")