#!/usr/bin/env python3
"""
Bet Sniper Bot – Entry Point

Reads configuration from:
  1. Command-line arguments (set by run.sh from bashio::config in HA mode)
  2. Environment variables (for standalone Docker / local testing)

Start in paper-trading mode first (default) to verify integration before
enabling live betting.
"""

import argparse
import logging
import os
import signal
import sys
from pathlib import Path

from betting.config import BetSniperConfig
from betting.bot import BetSniperBot

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/data/bet_sniper.log", mode="a", encoding="utf-8"),
    ],
)
logger = logging.getLogger("bet_sniper")


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Bet Sniper Bot – Betfair football betting")

    def env(key: str, default: str = "") -> str:
        return os.getenv(key, default)

    p.add_argument("--username",            default=env("BETFAIR_USERNAME", ""))
    p.add_argument("--password",            default=env("BETFAIR_PASSWORD", ""))
    p.add_argument("--app-key",             default=env("BETFAIR_APP_KEY", ""))
    p.add_argument("--paper-trading",       default=env("PAPER_TRADING", "true"))
    p.add_argument("--leagues",             default=env("LEAGUES",
                   "soccer_italy_serie_a,soccer_epl,soccer_spain_la_liga,soccer_germany_bundesliga"))
    p.add_argument("--min-odds",            default=env("MIN_ODDS", "1.5"))
    p.add_argument("--max-odds",            default=env("MAX_ODDS", "3.5"))
    p.add_argument("--stake-per-bet",       default=env("STAKE_PER_BET", "5.0"))
    p.add_argument("--max-daily-loss-pct",  default=env("MAX_DAILY_LOSS_PCT", "10.0"))
    p.add_argument("--reserve-pct",         default=env("RESERVE_PCT", "20.0"))
    p.add_argument("--lookahead-hours",          default=env("LOOKAHEAD_HOURS", "24"))
    p.add_argument("--check-interval",           default=env("CHECK_INTERVAL", "3600"))
    p.add_argument("--bet-window-hours",         default=env("BET_WINDOW_HOURS", "2.0"))
    p.add_argument("--min-time-to-ko-minutes",   default=env("MIN_TIME_TO_KO_MINUTES", "30"))
    p.add_argument("--telegram-relay-url",       default=env("TELEGRAM_RELAY_URL", ""))
    p.add_argument("--telegram-api-key",         default=env("TELEGRAM_API_KEY", ""))

    return p.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = _parse_args()

    def _bool(v: str) -> bool:
        return v.lower() in ("true", "1", "yes")

    def _list(v: str):
        return [s.strip() for s in v.split(",") if s.strip()]

    config = BetSniperConfig(
        username=args.username,
        password=args.password,
        app_key=args.app_key,
        paper_trading=_bool(args.paper_trading),
        leagues=_list(args.leagues),
        min_odds=float(args.min_odds),
        max_odds=float(args.max_odds),
        stake_per_bet=float(args.stake_per_bet),
        max_daily_loss_pct=float(args.max_daily_loss_pct),
        reserve_pct=float(args.reserve_pct),
        lookahead_hours=int(args.lookahead_hours),
        check_interval=int(args.check_interval),
        bet_window_hours=float(args.bet_window_hours),
        min_time_to_ko_minutes=int(args.min_time_to_ko_minutes),
        telegram_relay_url=args.telegram_relay_url,
        telegram_api_key=args.telegram_api_key,
    )

    logger.info("=" * 60)
    logger.info("  Bet Sniper Bot")
    logger.info("  Mode:         %s", "PAPER" if config.paper_trading else "LIVE")
    logger.info("  Leagues:      %s", ", ".join(config.leagues))
    logger.info("  Odds range:   %.2f – %.2f", config.min_odds, config.max_odds)
    logger.info("  Stake/bet:    %.2f", config.stake_per_bet)
    logger.info("  Daily cap:    %.0f%%", config.max_daily_loss_pct)
    logger.info("  Reserve:      %.0f%%", config.reserve_pct)
    logger.info("  Lookahead:    %dh", config.lookahead_hours)
    logger.info("  Interval:     %ds", config.check_interval)
    logger.info("  Bet window:   %.1fh before KO (min %dmin)", config.bet_window_hours, config.min_time_to_ko_minutes)
    logger.info("=" * 60)

    # Validate
    if not config.paper_trading and (not config.username or not config.password or not config.app_key):
        logger.error("LIVE mode requires username, password, and app_key.")
        sys.exit(1)

    if not config.leagues:
        logger.error("No leagues configured.")
        sys.exit(1)

    if config.min_odds >= config.max_odds:
        logger.error("min_odds (%.2f) must be less than max_odds (%.2f).", config.min_odds, config.max_odds)
        sys.exit(1)

    bot = BetSniperBot(config)

    def _handle_shutdown(sig, frame):
        logger.info("Signal %s received – shutting down …", sig)
        bot.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    try:
        bot.run()
    except Exception as exc:
        logger.critical("Fatal error: %s", exc, exc_info=True)
        bot.shutdown()
        sys.exit(1)


if __name__ == "__main__":
    main()
