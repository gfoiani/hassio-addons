# Changelog

## v1.0.26

- Fix: "market closed (weekend/holiday)" was logged at DEBUG level (invisible in normal output). Changed to INFO so the bot immediately shows a visible status message on startup when the market is closed.

## v1.0.25

- Fix: `#!/usr/bin/with-contenv bashio` enables bash `errexit` (`set -e`) by default. When Darwin exits with a non-zero code (market closed), `wait $ENGINE_PID` returned non-zero and `set -e` killed the script immediately — before the retry/sleep logic ever ran. This is why the container kept stopping despite the retry loop added in v1.0.23/v1.0.24. Added `set +e` at the top of `run.sh` (alongside the existing `set +u` and `set +H`) to disable errexit. All critical commands already have explicit error checking via `if !` guards, so disabling errexit has no negative side effects.

## v1.0.24

- Fix: Darwin exits with a **non-zero exit code** when the market is closed (e.g. weekend), not exit 0 as previously assumed. The script was treating any non-zero exit as a fatal crash and stopping the container. Now any Darwin exit (0 or non-zero) is treated as "session ended — retry later". The actual exit code and last 10 lines of darwin.log are printed for visibility, but the bot stays alive and sleeps until the next session.

## v1.0.23

- Feature: Darwin startup is now wrapped in a persistent retry loop so the add-on stays running on Home Assistant even when the market is closed.
  - **Weekend (Saturday / Sunday)**: bot calculates the exact sleep duration until Monday 07:30 UTC and waits. No manual restart needed.
  - **Weekday, outside session hours**: bot retries every 30 minutes until Darwin opens port 10002.
  - On retry, Engine.jar / gson.jar are not re-downloaded if already present on disk.
  - On retry, Engine.jar / gson.jar are not re-downloaded if already present on disk.

## v1.0.22

- Fix: Darwin clean exit (exit 0) is no longer treated as an error. When Darwin shuts down with exit code 0 after `TRADING_END_ORDINI` the bot now prints an informational message (market likely closed / no active session) and exits cleanly (exit 0). A non-zero exit code still triggers the full error dump. This prevents the container from logging a false "ERROR: Darwin Engine exited unexpectedly" every weekend or outside market hours.

## v1.0.21

- Fix: Darwin readiness check now waits only for port 10002 (TRADING), which is available on the free MC API tier. Ports 10001 (DATAFEED) and 10003 (HISTORICAL) require a paid Directa data subscription and may never open; market data will be sourced separately. The 30-second diagnostic still reports the state of all three ports for visibility.

## v1.0.20

- Diagnostic: port readiness check now probes all three Darwin MC ports — 10001 (DATAFEED), 10002 (TRADING), 10003 (HISTORICAL) — and waits for all three to be open before proceeding. Each 30-second progress message now reports the individual open/closed state of all three ports, making it clear which ports Darwin has opened and which are still missing. The `logDCL/` tail is also expanded from 20 to 30 lines.

## v1.0.19

- Fix (LIVE mode): for live trading, Engine.jar and gson.jar are now downloaded directly and StartEngine is launched as a managed background process (controlled stdin/stdout). DCL.jar spawned StartEngine as a fully detached process (closed I/O, different session), which prevented JVM initialisation inside a container — confirmed by `/proc/net/tcp` being completely empty after 300 s (no network activity at all).
- TEST mode is unchanged: DCL.jar is still used (handles the `-test` simulation-server flag internally).
- Diagnostic: `logDCL/` directory contents and `/proc/net/tcp6` (IPv6) now included in 30-second progress messages.

## v1.0.18

- Diagnostic: added `/proc/net/tcp` dump, `darwin.log` tail, and engine directory listing to the 30-second progress messages. This reveals what TCP connections StartEngine is attempting (state `02` = `SYN_SENT` = blocked connect) and the remote IP/port it is trying to reach.

## v1.0.17

- Diagnostic: every 30 seconds while waiting for port 10002, the last 30 lines of `StartEngine.log` are now printed inline (not just at timeout). This surfaces StartEngine authentication or network errors in real-time so the root cause of port 10002 never opening is visible in the HA log.

## v1.0.16

- Fix: Darwin Engine readiness timeout increased from 90 s to 300 s. Live connections to Directa require authentication against external servers before port 10002 opens, which can take well over 90 seconds.
- Improvement: Engine.jar's own log file (`StartEngine.log`) is now streamed to stdout in real-time alongside the DCL.jar log, and printed in full on timeout or unexpected exit for easier debugging.
- Improvement: a progress message is printed every 30 seconds while waiting for port 10002 to become available.

## v1.0.15

- Fix: armv7/armhf Docker build now uses `ARG TARGETARCH` (a Docker BuildKit compile-time variable) instead of `uname -m` at runtime to select the Java package. `openjdk8-jre-headless` is not available in Alpine 3.18 for 32-bit ARM; Java is skipped on those platforms with an informational message. Directa broker requires Java and is therefore not supported on armv7/armhf; XTB broker is unaffected.

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
