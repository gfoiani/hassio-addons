# 1.3.1

- Fix `LOCAL_DEPOLY` typo in `run.sh` — local deploy env-var detection now works correctly
- Fix fasthash Darwin crash: undefined `url` variable caused `NameError` on macOS
- Fix fasthash: save downloaded library using the correct filename instead of hardcoded `.so`
- Fix potential `ZeroDivisionError` in hashrate calculation when hashing completes in under 1ms
- Fix socket not recreated cleanly on reconnect — prevents `connect()` failures after errors
- Improve hash rate: disable Nagle's algorithm (`TCP_NODELAY`) to reduce network round-trip latency
- Improve hash rate: increase socket buffer from 1024 to 4096 bytes to prevent fragmented reads
- Improve hash rate: pre-encode static job request and result suffix outside the mining loop
- Improve startup time: move `pip install requests` to Dockerfile (was running on every container start)
- Remove unnecessary venv creation from `run.sh`
- Add graceful error handling and timeout for fasthash download failures

# 1.3.0

- Add Fashhash algorithm

# 1.2.2

- Add miner identifier

# 1.2.1

- Minor code refactoring

# 1.2.0

- Add multithreading

# 1.1.2

- Container uses tmpfs, a memory file system. (20.11.22)

# 1.1.1

- Update config.yaml (17.11.22)

# 1.1.0

- Added ability to specify username and mining_key from configuration panel (15.11.22)

# 1.0.7

- First commit
