# Crypto Trading Bot — Home Assistant Addon

Automated **intraday crypto trading** on [Binance Spot](https://binance.com) running as a background Home Assistant addon.

Uses a **Momentum strategy** (EMA-9/EMA-21 crossover + RSI filter) on 15/30/60-minute candles. Entries are protected with native Binance **OCO orders** (One-Cancels-Other) that set Stop-Loss and Take-Profit simultaneously.

Optional **Telegram notifications** via the existing relay service.

> ⚠️ **Risk disclaimer**: Automated trading involves significant financial risk. Always start in paper trading mode (`paper_trading: true`) and test thoroughly before switching to live funds.

---

## Supported architectures

| Architecture | Hardware |
| --- | --- |
| `aarch64` | Raspberry Pi 4 (64-bit) |
| `armv7` | Raspberry Pi 3/4 (32-bit) |
| `armhf` | Raspberry Pi 2 |
| `amd64` | x86-64 servers and VMs |

---

## Prerequisites

1. A [Binance account](https://binance.com) with API access enabled.
2. **API Key + Secret** — see setup instructions below.
3. *(Optional)* The [Telegram relay service](../telegram_bot/README.md) deployed on Render.

---

## Binance API setup

### Live account (real funds)

> ⚠️ Only do this when you are ready to trade with real money. Always test with Testnet first.

1. Log in to [binance.com](https://binance.com).
2. Click your profile icon (top right) → **Account & Security** → **API Management**.
3. Click **Create API** → choose **System generated** → enter a label (e.g. `hassio-crypto-bot`).
4. Complete identity verification (2FA code required).
5. On the API permissions page, enable **only** these two:
   - ✅ **Enable Reading** (Read Info)
   - ✅ **Enable Spot & Margin Trading**
   - ❌ **Do NOT enable Withdrawals** — not needed and a security risk.
6. Under **IP access restrictions**, consider adding a fixed IP (your Raspberry Pi) for extra safety. Or leave unrestricted if your IP is dynamic.
7. Click **Save** → confirm with 2FA.
8. Copy **API Key** and **Secret Key** immediately — the secret is shown **only once**.

### Testnet account (paper trading — no real money)

The Testnet uses separate credentials, independent from your real Binance account.

1. Go to [testnet.binance.vision](https://testnet.binance.vision/).
2. Click **Log In** → authenticate with your **GitHub** account.
3. Under **API Keys**, click **Generate HMAC_SHA256 Key** → enter a label.
4. Copy **API Key** and **Secret Key** — the secret is shown **only once**.
5. The Testnet provides a pre-loaded paper balance (BTC, ETH, USDT) for testing.

> **Note:** Testnet credentials do **not** work on the live Binance API and vice versa.
> When `paper_trading: true`, the bot connects to `testnet.binance.vision`.
> When `paper_trading: false`, it connects to the real `api.binance.com`.

---

## Installation (Home Assistant)

1. Add this repository to your HA addon store:

   [![Add repository](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fgfoiani%2Fhassio-addons%2F)

2. Find **"Crypto Trading Bot (Binance)"** in the addon store and click **Install**.
3. Configure the addon (see section below).
4. Click **Start** and check the **Log** tab.

---

## Configuration

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `api_key` | string | `""` | Binance API key |
| `api_secret` | string | `""` | Binance API secret |
| `paper_trading` | bool | `true` | Use Binance Testnet (no real money) |
| `symbols` | string | `"BTCUSDT,ETHUSDT"` | Comma-separated trading pairs |
| `timeframe` | select | `15` | Candle size in minutes: `15`, `30`, or `60` |
| `max_position_value_usdt` | string | `"100"` | Maximum USDT to invest per position |
| `stop_loss_pct` | string | `"2.0"` | Stop-loss percentage below entry |
| `take_profit_pct` | string | `"4.0"` | Take-profit percentage above entry |
| `max_daily_loss_pct` | string | `"5.0"` | Halt new entries if daily P&L drops below this |
| `check_interval` | string | `"60"` | Seconds between main loop iterations |
| `cooldown_minutes` | string | `"30"` | Minutes to wait after closing before re-entering same symbol |
| `telegram_relay_url` | string | `""` | URL of the Telegram relay service (optional) |
| `telegram_api_key` | string | `""` | API key for the relay service (optional) |

### Example configuration

```yaml
api_key: "your_binance_api_key"
api_secret: "your_binance_api_secret"
paper_trading: true
symbols: "BTCUSDT,ETHUSDT,SOLUSDT"
timeframe: "15"
max_position_value_usdt: "200"
stop_loss_pct: "2.0"
take_profit_pct: "4.0"
max_daily_loss_pct: "5.0"
check_interval: "60"
cooldown_minutes: "30"
telegram_relay_url: "https://your-relay.onrender.com"
telegram_api_key: "your_relay_api_key"
```

---

## Strategy

### Momentum (EMA + RSI)

Entry conditions (**LONG only** — spot trading, no shorting):

1. **EMA-9 crosses above EMA-21** — bullish momentum signal
2. **RSI between 40 and 70** — not overbought, confirms trend health
3. Minimum 25 candles required before evaluating signals

Once a LONG entry is triggered:

- A **market BUY** order is placed immediately
- A **Binance OCO order** (SELL) is placed with:
  - `LIMIT_MAKER` leg (take-profit) at `entry_price × (1 + take_profit_pct / 100)`
  - `STOP_LOSS_LIMIT` leg (stop-loss) at `entry_price × (1 − stop_loss_pct / 100)`
- If either leg fills, the other is cancelled automatically by Binance

### Cooldown

After a position is closed (by SL, TP, or manual close), the bot waits `cooldown_minutes` before re-evaluating the same symbol. This prevents immediately re-entering on noise after a triggered stop.

### Daily loss limit

If total portfolio value drops by `max_daily_loss_pct` since midnight UTC, the bot halts all new entries for the rest of the day. Resets automatically at midnight UTC. Can also be triggered manually via `/halt`.

---

## Telegram commands

The bot responds to these commands via the Telegram relay:

| Command | Description |
| --- | --- |
| `/status` | Show all open positions with P&L |
| `/positions` | Alias for `/status` |
| `/halt` | Stop opening new positions (existing positions remain) |
| `/resume` | Re-enable new position entries |
| `/close SYMBOL` | Manually close a specific position (e.g. `/close BTCUSDT`) |

---

## Persistent storage

Files written to `/data` (survive restarts):

| File | Description |
| --- | --- |
| `crypto_positions.json` | Current open/closed positions |
| `crypto_trades.log` | Append-only trade history |

Trade log format:

```text
2025-01-15 10:23:00 UTC | ENTER | BTCUSDT      | LONG  | qty=0.002        | entry=42500.00000000 | SL=41650.00000000 | TP=44100.00000000 | cost=85.00 USDT
2025-01-15 11:45:00 UTC | EXIT  | BTCUSDT      | LONG  | qty=0.002        | entry=42500.00000000 | exit=44100.00000000 | P&L=+3.200000 USDT | reason=take-profit
```

---

## Local development

Test the bot locally with Docker without a full HA environment.

### 1. Get Binance Testnet credentials

Go to [testnet.binance.vision](https://testnet.binance.vision/), log in with GitHub, and generate an API key.

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```bash
LOCAL_DEPLOY=true
API_KEY=your_testnet_api_key
API_SECRET=your_testnet_api_secret
PAPER_TRADING=true           # true = testnet, false = real Binance
SYMBOLS=BTCUSDT,ETHUSDT
TIMEFRAME=15
MAX_POSITION_VALUE_USDT=100
STOP_LOSS_PCT=2.0
TAKE_PROFIT_PCT=4.0
MAX_DAILY_LOSS_PCT=5.0
CHECK_INTERVAL=60
COOLDOWN_MINUTES=30
TELEGRAM_RELAY_URL=          # leave empty to disable
TELEGRAM_API_KEY=
```

### 3. Build and run

```bash
./deploy_local.sh
```

### 4. Watch logs

```bash
docker logs -f crypto-trader
```

Expected output:

```text
============================================================
  Crypto Trading Bot – Binance Spot
============================================================
  Mode         : PAPER (Testnet)
  Symbols      : BTCUSDT, ETHUSDT
  Timeframe    : 15m
  Max pos.     : 100 USDT
  Stop loss    : 2.0%
  Take profit  : 4.0%
============================================================
2025-01-15 10:00:00 [INFO] crypto_bot.broker: Connected to Binance (TESTNET)
2025-01-15 10:00:00 [INFO] crypto_bot.bot: Crypto bot started.
2025-01-15 10:15:00 [INFO] crypto_bot.strategy: BTCUSDT LONG signal: EMA9 crossed above EMA21, RSI=52.3
2025-01-15 10:15:01 [INFO] crypto_bot.bot: ENTERED LONG 0.002 BTCUSDT @ 42500.000000 | SL=41650.000000 TP=44100.000000
```

### 5. Stop

```bash
docker stop crypto-trader
```

### 6. Remove

```bash
docker rm -f crypto-trader
docker rmi crypto-trader:latest
docker volume rm crypto-trader-data
```

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md).
