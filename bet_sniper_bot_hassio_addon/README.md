# Bet Sniper Bot (Betfair)

Automatic football 1X2 BACK betting on Betfair with configurable risk management
and Telegram notifications.

## Features

- **Automatic placement** of BACK bets on football MATCH_ODDS (1X2) markets
- **Supported leagues**: Serie A, Premier League, La Liga, Bundesliga (configurable)
- **Odds filter**: configurable `min_odds` / `max_odds` range
- **Snipe window**: bets placed only in the configurable time window before kick-off
  (e.g. between 30 min and 2 h), so the bot uses final line-ups and mature market odds
- **Risk management**:
  - Fixed stake per bet
  - Daily spend cap (% of balance)
  - Reserve (% of balance never touched)
- **Paper-trading mode**: test the strategy without placing real bets
- **SQLite history**: every bet stored in `/data/bets.db`
- **Telegram commands**: `/status`, `/stats`, `/halt`, `/resume`

## Configuration

| Option | Default | Description |
|---|---|---|
| `username` | | Betfair account username |
| `password` | | Betfair account password |
| `app_key` | | Betfair API App Key |
| `paper_trading` | `true` | Simulate bets without spending money |
| `leagues` | Serie A, PL, La Liga, Bundesliga | Comma-separated league slugs |
| `min_odds` | `1.5` | Minimum back odds to consider |
| `max_odds` | `3.5` | Maximum back odds to consider |
| `stake_per_bet` | `5.0` | Fixed stake per event (in account currency) |
| `max_daily_loss_pct` | `10.0` | Max % of balance to spend per day |
| `reserve_pct` | `20.0` | % of balance always kept reserved |
| `lookahead_hours` | `24` | Hours ahead to look for upcoming matches |
| `check_interval` | `3600` | Seconds between market scans |
| `bet_window_hours` | `2.0` | Only bet if kick-off is within this many hours |
| `min_time_to_ko_minutes` | `30` | Don't bet if kick-off is less than this many minutes away |
| `telegram_relay_url` | | Telegram relay service URL |
| `telegram_api_key` | | Telegram relay API key |

## Supported League Slugs

| Slug | Competition |
|---|---|
| `soccer_italy_serie_a` | Serie A |
| `soccer_epl` | English Premier League |
| `soccer_spain_la_liga` | Spanish La Liga |
| `soccer_germany_bundesliga` | German Bundesliga |
| `soccer_france_ligue_1` | French Ligue 1 |
| `soccer_portugal_primeira_liga` | Primeira Liga |
| `soccer_uefa_champs_league` | UEFA Champions League |
| `soccer_uefa_europa_league` | UEFA Europa League |

## Strategy

The bot scans upcoming events continuously but only places bets inside the **snipe window**
— the period between `min_time_to_ko_minutes` and `bet_window_hours` before kick-off.
This ensures the odds reflect official line-ups (published ~60 min before KO) and the
Betfair market is mature and liquid.

For each match inside the snipe window:
1. Fetches the Betfair MATCH_ODDS market (Home / Draw / Away).
2. Finds the outcome with the **lowest back odds** within `[min_odds, max_odds]`
   (= highest implied probability = most confident pick in range).
3. Places a BACK LIMIT order at those odds with `persistence_type=LAPSE`
   (cancelled at in-play if unmatched).
4. Records the bet in SQLite for history and settlement tracking.

## Risk Management

Before placing each bet the bot verifies:

- `today_spend + stake ≤ balance × (max_daily_loss_pct / 100)`
- `stake ≤ balance - reserved - today_spend`

where `reserved = balance × (reserve_pct / 100)`.

## Local Development

```bash
cp .env.example .env
# Edit .env with your credentials
./deploy_local.sh
```

## Betfair App Key

1. Log in to Betfair.
2. Go to **My Account → Developer Program → Application Keys**.
3. Create a Delayed App Key (free) for testing, or a Live App Key for real bets.
