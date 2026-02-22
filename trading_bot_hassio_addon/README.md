# Day Trading Bot – Home Assistant Addon

Automated day trading bot for the **NYSE** (New York) and **LSE** (London Stock Exchange).

Runs inside Home Assistant as an addon **or** as a standalone Docker container.
Designed to run on **Raspberry Pi** (aarch64 / armv7).

---

## Supported brokers

| Broker | Markets | Demo | Notes |
| ------ | ------- | ---- | ----- |
| **XTB** (default) | NYSE + LSE | ✅ | CFD stocks. Available in Italy. Regime dichiarativo. |
| **Directa** | NYSE + LSE + Borsa Italiana | ❌ | Real stocks. Regime amministrato. Darwin auto-started. |

> **Italian tax note**:
>
> - **XTB** uses *regime dichiarativo* – you declare gains yourself in the annual tax return (Modello 730 / Redditi PF, quadro RT).
> - **Directa SIM** uses *regime amministrato* – taxes are withheld automatically by the broker.

---

## XTB setup

XTB connects directly to XTB's servers via WebSocket — **no local software required**.

1. Open an XTB account at [xtb.com](https://www.xtb.com) (demo account available for free).
2. Enter your credentials in the addon settings:
   - `api_key` → your XTB **userId** (numeric account ID)
   - `api_secret` → your XTB **password**
3. Set `paper_trading: "true"` to use the demo account (recommended to start).

### XTB symbol format

| Asset | XTB symbol |
| ----- | ---------- |
| Apple (NYSE) | `AAPL.US` |
| Microsoft (NYSE) | `MSFT.US` |
| Tesla (NASDAQ) | `TSLA.US` |
| BP (LSE) | `BP.UK` |
| Vodafone (LSE) | `VOD.UK` |
| HSBC (LSE) | `HSBA.UK` |
| Shell (LSE) | `SHEL.UK` |

Find exact symbol names in the XTB xStation platform under **Market Watch**.

### Example `.env` for XTB

```bash
BROKER=xtb
API_KEY=12345678         # your XTB userId
API_SECRET=your_password
PAPER_TRADING=true
EXCHANGES=NYSE,LSE
SYMBOLS_NYSE=AAPL.US,MSFT.US,NVDA.US
SYMBOLS_LSE=BP.UK,VOD.UK
```

---

## Directa SIM setup

Directa SIM is the ideal choice for **Italian retail investors** who want *regime amministrato* (automatic tax withholding). It supports real stocks on NYSE/NASDAQ and LSE in addition to Borsa Italiana.

The bot communicates with the **Darwin API** via TCP sockets. **Darwin CommandLine (DCL.jar) is automatically downloaded and started inside the container** on first run — no manual setup required.

### What you need

1. Open a Directa SIM account at [directa.it](https://www.directa.it).
2. Enter your Directa credentials in the addon settings:
   - `api_key` → your Directa **userId** (account code)
   - `api_secret` → your Directa **password**

The addon will:

- Download `DCL.jar` automatically from Directa's servers on first startup (cached in `/data/` for subsequent restarts).
- Launch Darwin CommandLine as a background process before the bot starts.
- Wait up to 60 seconds for Darwin to be ready (port 10002).
- Stop Darwin cleanly when the bot shuts down.

Darwin logs are written to `/data/darwin.log`.

### Darwin API ports

Darwin CommandLine opens three TCP sockets on localhost (all internal to the container):

| Port | Function |
| ---- | -------- |
| `10001` | DATAFEED – real-time price subscriptions |
| `10002` | TRADING – orders, positions, account info |
| `10003` | HISTORICAL – candle / tick data |

### Paper / demo trading

Directa SIM does **not** provide a separate paper-trading account via the API.
Set `paper_trading: "true"` and Darwin CommandLine is started with the `-test` flag, which routes orders to Directa's test environment (no real trades executed).

### External Darwin (advanced)

If you already have Darwin running on a separate machine, set `directa_host` to that machine's IP address. The addon will then skip the auto-start and connect to Darwin remotely.

```bash
DIRECTA_HOST=192.168.1.100   # skip auto-start, connect to external Darwin
```

### Directa symbol format

US stocks (NYSE/NASDAQ) require a **`.` prefix**. Italian and LSE stocks use plain tickers.

| Asset | Directa symbol | Market |
| ----- | -------------- | ------ |
| Apple (NYSE) | `.AAPL` | NYSE |
| Microsoft | `.MSFT` | NASDAQ |
| Tesla | `.TSLA` | NASDAQ |
| ENI (Borsa Italiana) | `ENI` | MTA |
| Enel | `ENEL` | MTA |
| BP (LSE) | `BP` | LSE |
| Vodafone (LSE) | `VOD` | LSE |

Verify exact symbol names in the Darwin platform under **Market Watch**.

### Bracket order simulation

Directa has no native bracket order type. The broker implementation simulates it by placing three separate orders atomically:

1. **Market entry order** (`ACQMARKET` / `VENMARKET`)
2. **Stop-loss stop order** (`VENSTOP` / `ACQSTOP`)
3. **Take-profit limit order** (`VENAZ` / `ACQAZ`)

The stop/limit orders are cancelled automatically when the position is closed by the bot.

### Example `.env` for Directa

```bash
BROKER=directa
API_KEY=your_directa_userId
API_SECRET=your_directa_password
PAPER_TRADING=true        # starts Darwin in -test mode
EXCHANGES=NYSE,LSE
SYMBOLS_NYSE=.AAPL,.MSFT,.NVDA   # dot prefix for US stocks
SYMBOLS_LSE=BP,VOD                # plain ticker for LSE
DIRECTA_HOST=127.0.0.1            # auto-started inside container
```

---

## Trading strategies

### Opening Range Breakout (ORB) – *recommended*

1. **ORB window** (first `orb_minutes` after market open, default 15 min): the bot records the highest high and lowest low of every 1-minute candle.
2. **Signal detection**: once the ORB window closes, the bot monitors for a price breakout:
   - **LONG** if price > ORB high **and** volume > 1.5× average volume
   - **SHORT** if price < ORB low **and** volume > 1.5× average volume
3. **Risk**: stop loss at the opposite ORB boundary; take profit at the configured percentage.

### Momentum (EMA crossover + RSI)

- **LONG** when EMA-9 crosses above EMA-21 and RSI is 40–65.
- **SHORT** when EMA-9 crosses below EMA-21 and RSI is 35–60.

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
| `broker` | `xtb` | `xtb` or `directa` |
| `api_key` | | XTB: userId · Directa: userId |
| `api_secret` | | XTB: password · Directa: password |
| `paper_trading` | `true` | `true` = demo/paper account |
| `exchanges` | `NYSE,LSE` | Comma-separated list: `NYSE`, `LSE` |
| `symbols_nyse` | | XTB: `AAPL.US` · Directa: `.AAPL` |
| `symbols_lse` | | XTB: `BP.UK` · Directa: `BP` |
| `max_position_value` | `1000` | Max capital per position (account currency) |
| `stop_loss_pct` | `2.0` | Stop loss % |
| `take_profit_pct` | `4.0` | Take profit % |
| `max_daily_loss_pct` | `5.0` | Daily loss limit % |
| `strategy` | `orb` | `orb` (Opening Range Breakout) or `momentum` |
| `orb_minutes` | `15` | Opening range collection window (minutes) |
| `pre_market_minutes` | `30` | Start monitoring N minutes before market open |
| `close_minutes` | `15` | Close all positions N minutes before market close |
| `check_interval` | `30` | Main loop interval (seconds) |
| `directa_host` | `127.0.0.1` | Directa only: `127.0.0.1` = auto-start, remote IP = external Darwin |

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

Open positions and trade logs are written to `/data/`, the standard Home Assistant addon persistent directory:

| File | Description |
| ---- | ----------- |
| `positions.json` | Current open positions (survives restarts and updates) |
| `trades.log` | Append-only trade history: one line per ENTER/EXIT event |

### Viewing the trade log in Home Assistant

The `/data/` directory is accessible via the **File Editor** addon or **Studio Code Server**:

1. Install the **File Editor** addon from the HA addon store.
2. Navigate to the addon data folder: **`/addon_configs/<slug>/data/trades.log`**
   (the slug is `day-trading-bot` unless changed in `config.yaml`).

Each line in `trades.log` looks like:

```text
2024-01-15 09:32:15 UTC | ENTER | NYSE | AAPL.US      | LONG  | qty=5      | entry=185.2300 | SL=181.5254 | TP=192.6392
2024-01-15 09:45:30 UTC | EXIT  | NYSE | AAPL.US      | LONG  | qty=5      | entry=185.2300 | exit=192.6392  | P&L=+36.81 | reason=take-profit
```

### Viewing in local Docker mode

```bash
# Print the full log
docker exec trading-bot cat /data/trades.log

# Follow in real time
docker exec trading-bot tail -f /data/trades.log
```

---

## ⚠️ Risk disclaimer

This software is provided for **educational and research purposes only**.
Automated trading carries significant financial risk. Past performance is not indicative of future results.
Always start with a **demo account** and never risk capital you cannot afford to lose.
