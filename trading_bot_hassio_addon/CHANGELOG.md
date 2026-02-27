# Changelog

## v1.0.14

- Fix: DCL.jar is a launcher that spawns `directa.standalone.StartEngine` (with the `-mc` socket-server flag) as a detached background process and then exits. The previous script treated DCL.jar's intentional exit as a crash and aborted. DCL.jar is now run synchronously; after it exits, `pgrep` locates the Engine.jar process it spawned and monitors that instead.

## v1.0.13

- Fix: switched Directa startup from `Engine.jar` (standalone engine, no local socket API) back to `DCL.jar` (Darwin CommandLine), which is the component that opens the local socket API ports 10001/10002/10003 that the Python broker connects to. Using `Engine.jar` alone caused the bot to restart immediately because port 10002 never opened within the 60-second timeout.
- Directa: readiness timeout extended from 60 s to 90 s to give DCL.jar more time on slower hardware

## v1.0.12

- Telegram: bot now sends a startup notification with broker, mode, strategy and symbols
- Telegram: bot now sends a shutdown notification before closing all positions
- Logging: all log output is now written to `/data/trading_bot.log` in addition to stdout
- Logging: periodic heartbeat logged every 30 minutes showing open positions, exchange phases and halt state
- Logging: decision logs in active trading window show each symbol being scanned, its current price, ORB range, volume ratio and whether the volume threshold is met
- Logging: ORB collection window logs each candle's high/low and the evolving range per symbol
- Fix: `_load_positions()` was never called on startup – open positions from a previous session are now correctly restored on bot restart

## v1.0.11

- Directa: `Engine.jar` and `gson.jar` are now always re-downloaded on startup to ensure the latest version is used
- Directa: Darwin log is truncated at each startup so sessions are isolated
- Directa: Darwin output is streamed to addon logs in real-time via `tail -f` (no more waiting for failure to see output)
- Directa: on startup failure the full Darwin log is printed instead of only the last 20 lines
- Fix: added `set +H` to `run.sh` to prevent bash history expansion from mangling passwords containing `!`

## v1.0.0

- Initial release
- XTB xAPI WebSocket broker integration (NYSE + LSE)
- Alpaca Markets broker integration (NYSE paper trading)
- Opening Range Breakout (ORB) strategy
- Momentum strategy (EMA crossover + RSI)
- Automatic stop loss, take profit and end-of-day position closure
- NYSE (America/New_York 09:30–16:00) and LSE (Europe/London 08:00–16:30) schedules
- Daily loss limit enforcement
- Position persistence to disk (storage/positions.json)
- Home Assistant addon config panel integration
- Multi-architecture Docker support (amd64, aarch64, armv7, armhf)
