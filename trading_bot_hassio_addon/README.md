# Day Trading Bot – Home Assistant Addon

Automated day trading bot for the **NYSE** (New York) and **LSE** (London Stock Exchange).

Runs inside Home Assistant as an addon **or** as a standalone Docker container.
Designed to run on **Raspberry Pi** (aarch64 / armv7).

---

## Broker: Directa SIM

The only supported broker is **Directa SIM** — the ideal choice for Italian retail
investors who want *regime amministrato* (automatic tax withholding on gains).
It supports real stocks on NYSE/NASDAQ, LSE and Borsa Italiana.

The bot communicates with the **Darwin API** via TCP sockets.
**Darwin CommandLine (DCL.jar) is automatically downloaded and started inside the
container** on first run — no manual setup required.

### What you need

1. Open a Directa SIM account at [directa.it](https://www.directa.it).
2. Enter your credentials in the addon settings:
   - `api_key` → your Directa **userId** (account code, e.g. `D12345`)
   - `api_secret` → your Directa **password**

The addon will:

- Download `Engine.jar` and `gson.jar` automatically from Directa's servers on
  **every startup** to ensure the latest version is always used.
- Launch Darwin as a background process before the bot starts.
- Stream Darwin output to the addon logs in real-time.
- Wait up to 300 seconds for Darwin to be ready (port 10002).
- Stop Darwin cleanly when the bot shuts down.

Darwin logs are written to `/data/darwin.log` (truncated at each startup to keep
sessions isolated).

### Darwin API ports

Darwin CommandLine opens three TCP sockets on localhost (all internal to the container):

| Port | Function |
| ---- | -------- |
| `10001` | DATAFEED – real-time price subscriptions |
| `10002` | TRADING – orders, positions, account info |
| `10003` | HISTORICAL – candle / tick data |

### Paper / demo trading

Directa SIM does **not** provide a separate paper-trading account via the API.
Set `paper_trading: true` and Darwin CommandLine is started with the `-test` flag,
which routes orders to Directa's test environment (no real trades executed).

### External Darwin (advanced)

If you already have Darwin running on a separate machine, set `directa_host` to that
machine's IP address. The addon will then skip the auto-start and connect remotely.

```bash
DIRECTA_HOST=192.168.1.100   # skip auto-start, connect to external Darwin
```

### Symbol format

US stocks (NYSE/NASDAQ) require a **`.` prefix**. LSE and Italian stocks use plain tickers.

| Asset | Symbol | Market |
| ----- | ------ | ------ |
| Apple | `.AAPL` | NYSE |
| Microsoft | `.MSFT` | NASDAQ |
| Tesla | `.TSLA` | NASDAQ |
| NVIDIA | `.NVDA` | NASDAQ |
| ENI | `ENI` | Borsa Italiana |
| BP | `BP` | LSE |
| Vodafone | `VOD` | LSE |
| HSBC | `HSBA` | LSE |

Verify exact symbol names in the Darwin platform under **Market Watch**.

### Bracket order simulation

Directa has no native bracket order type. The broker implementation simulates it by
placing three separate orders atomically:

1. **Market entry order** (`ACQMARKET` / `VENMARKET`)
2. **Stop-loss stop order** (`VENSTOP` / `ACQSTOP`)
3. **Take-profit limit order** (`VENAZ` / `ACQAZ`)

The stop/limit orders are cancelled automatically when the position is closed by the bot.

### Example `.env`

```bash
BROKER=directa
API_KEY=D12345              # your Directa userId
API_SECRET=your_password
PAPER_TRADING=true          # starts Darwin in -test mode
EXCHANGES=NYSE,LSE
SYMBOLS_NYSE=.AAPL,.MSFT,.NVDA   # dot prefix for US stocks
SYMBOLS_LSE=BP,VOD,HSBA          # plain ticker for LSE
DIRECTA_HOST=127.0.0.1           # auto-started inside container
```

---

## Trading strategies

### Opening Range Breakout (ORB) – *recommended*

1. **ORB window** (first `orb_minutes` after market open, default 15 min): the bot
   records the highest high and lowest low of every 5-minute candle.
2. **Signal detection**: once the ORB window closes, the bot monitors for a price breakout:
   - **LONG** if price > ORB high **and** volume > 1.5× average volume
   - **SHORT** if price < ORB low **and** volume > 1.5× average volume
   (Directa is long-only — SHORT signals are silently ignored.)
3. **Risk**: stop loss at the opposite ORB boundary; take profit at the configured percentage.

### Momentum (EMA crossover + RSI)

- **LONG** when EMA-9 crosses above EMA-21 and RSI is 40–65.

---

## Exchange schedules

| Exchange | Local time | Timezone |
| -------- | ---------- | -------- |
| NYSE | 09:30 – 16:00 | America/New_York (ET) |
| LSE | 08:00 – 16:30 | Europe/London (GMT/BST) |

The bot automatically:

- Starts monitoring **`pre_market_minutes`** before each exchange opens.
- Collects ORB data during the first **`orb_minutes`** after open.
- Closes **all** positions **`close_minutes`** before market close.
- Halts new entries if the daily portfolio loss exceeds **`max_daily_loss_pct`**.

---

## Configuration (Home Assistant)

| Option | Default | Description |
| ------ | ------- | ----------- |
| `broker` | `directa` | Only `directa` is supported |
| `api_key` | | Directa userId (e.g. `D12345`) |
| `api_secret` | | Directa account password |
| `paper_trading` | `true` | `true` = starts Darwin in `-test` mode (no real orders) |
| `exchanges` | `NYSE,LSE` | Comma-separated: `NYSE`, `LSE` |
| `symbols_nyse` | | Dot-prefix format: `.AAPL`, `.MSFT`, `.NVDA` |
| `symbols_lse` | | Plain ticker: `BP`, `VOD`, `HSBA` |
| `max_position_value` | `200` | Max capital per position (account currency, EUR) |
| `stop_loss_pct` | `1.5` | Stop loss % below entry |
| `take_profit_pct` | `3.0` | Take profit % above entry |
| `max_daily_loss_pct` | `3.0` | Halt new entries if daily drawdown reaches this % |
| `strategy` | `momentum` | `orb` (Opening Range Breakout) or `momentum` |
| `orb_minutes` | `15` | Opening range collection window (minutes, ORB only) |
| `pre_market_minutes` | `30` | Start monitoring N minutes before market open |
| `close_minutes` | `30` | Close all positions N minutes before market close |
| `check_interval` | `60` | Main loop interval (seconds) |
| `directa_host` | `127.0.0.1` | `127.0.0.1` = auto-start Darwin; remote IP = external Darwin |
| `telegram_relay_url` | | URL of the Render relay service (leave empty to disable) |
| `telegram_api_key` | | Shared secret for the Telegram relay (`X-API-Key` header) |

---

## Local Docker testing

```bash
# 1. Copy and configure the environment file
cp .env.example .env
nano .env   # fill in your credentials and symbols

# 2. Build and run
chmod +x deploy_local.sh
./deploy_local.sh

# 3. Follow logs
docker logs -f trading-bot
```

---

## Persistent storage

Open positions and trade logs are written to `/data/`, the standard Home Assistant
addon persistent directory:

| File | Description |
| ---- | ----------- |
| `positions.json` | Current open positions (survives restarts and updates) |
| `trades.log` | Append-only trade history: one line per ENTER/EXIT event |
| `trades.db` | SQLite database with full trade history (queryable via `/stats`) |
| `trading_bot.log` | Full bot log (mirrors stdout) |
| `darwin.log` | Darwin CommandLine output (truncated each startup) |

### Viewing the trade log in Home Assistant

The `/data/` directory is accessible via the **File Editor** addon or **Studio Code Server**:

1. Install the **File Editor** addon from the HA addon store.
2. Navigate to: **`/addon_configs/day-trading-bot/data/trades.log`**

Each line in `trades.log` looks like:

```text
2024-01-15 09:32:15 UTC | ENTER | NYSE | .AAPL  | LONG  | qty=5  | entry=185.23 | SL=181.53 | TP=192.64
2024-01-15 09:45:30 UTC | EXIT  | NYSE | .AAPL  | LONG  | qty=5  | entry=185.23 | exit=192.64 | P&L=+36.81 | reason=take-profit
```

### Viewing in local Docker mode

```bash
# Print the full log
docker exec trading-bot cat /data/trades.log

# Follow in real time
docker exec trading-bot tail -f /data/trades.log
```

---

## Telegram integration (optional)

Deploy the companion relay service on Render (see `telegram_bot/` folder), then set
`telegram_relay_url` and `telegram_api_key` in the addon options.

Available Telegram commands:

| Command | Description |
| ------- | ----------- |
| `/status` | Current positions and bot state |
| `/stats` | All-time trading statistics |
| `/halt` | Stop opening new positions |
| `/resume` | Resume after manual halt |
| `/close` | Close all open positions immediately |

---

## ⚠️ Risk disclaimer

This software is provided for **educational and research purposes only**.
Automated trading carries significant financial risk. Past performance is not
indicative of future results.
Always start with a **demo account** (`paper_trading: true`) and never risk capital
you cannot afford to lose.
