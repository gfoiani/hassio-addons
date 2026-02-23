#!/usr/bin/env python3
"""
Crypto Trading Bot (Binance Spot) – Entry Point

Reads configuration from:
  1. Command-line arguments (set by run.sh from bashio::config in HA mode)
  2. Environment variables (for standalone Docker / local testing)
"""

import argparse
import logging
import os
import signal
import sys

from trading.config import CryptoTradingConfig
from trading.bot import CryptoBot

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("crypto_bot")


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Crypto Trading Bot – Binance Spot")

    def env(key: str, default: str = "") -> str:
        return os.getenv(key, default)

    p.add_argument("--api-key",                  default=env("API_KEY", ""))
    p.add_argument("--api-secret",               default=env("API_SECRET", ""))
    p.add_argument("--paper-trading",            default=env("PAPER_TRADING", "true"))
    p.add_argument("--symbols",                  default=env("SYMBOLS", "BTCUSDT,ETHUSDT"))
    p.add_argument("--timeframe",                default=env("TIMEFRAME", "15"))
    p.add_argument("--max-position-value-usdt",  default=env("MAX_POSITION_VALUE_USDT", "100"))
    p.add_argument("--stop-loss-pct",            default=env("STOP_LOSS_PCT", "2.0"))
    p.add_argument("--take-profit-pct",          default=env("TAKE_PROFIT_PCT", "4.0"))
    p.add_argument("--max-daily-loss-pct",       default=env("MAX_DAILY_LOSS_PCT", "5.0"))
    p.add_argument("--check-interval",           default=env("CHECK_INTERVAL", "60"))
    p.add_argument("--cooldown-minutes",         default=env("COOLDOWN_MINUTES", "30"))
    p.add_argument("--telegram-relay-url",       default=env("TELEGRAM_RELAY_URL", ""))
    p.add_argument("--telegram-api-key",         default=env("TELEGRAM_API_KEY", ""))

    return p.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = _parse_args()

    def _parse_list(raw: str):
        return [s.strip() for s in raw.split(",") if s.strip()]

    config = CryptoTradingConfig(
        api_key=args.api_key,
        api_secret=args.api_secret,
        paper_trading=args.paper_trading.lower() in ("true", "1", "yes"),
        symbols=_parse_list(args.symbols),
        timeframe=int(args.timeframe),
        max_position_value_usdt=float(args.max_position_value_usdt),
        stop_loss_pct=float(args.stop_loss_pct),
        take_profit_pct=float(args.take_profit_pct),
        max_daily_loss_pct=float(args.max_daily_loss_pct),
        check_interval=int(args.check_interval),
        cooldown_minutes=int(args.cooldown_minutes),
        telegram_relay_url=args.telegram_relay_url,
        telegram_api_key=args.telegram_api_key,
    )

    logger.info("=" * 60)
    logger.info("  Crypto Trading Bot – Binance Spot")
    logger.info("=" * 60)
    logger.info(f"  Mode         : {'PAPER (Testnet)' if config.paper_trading else 'LIVE ⚠️  REAL MONEY'}")
    logger.info(f"  Symbols      : {', '.join(config.symbols)}")
    logger.info(f"  Timeframe    : {config.timeframe}m")
    logger.info(f"  Max pos.     : {config.max_position_value_usdt} USDT")
    logger.info(f"  Stop loss    : {config.stop_loss_pct}%")
    logger.info(f"  Take profit  : {config.take_profit_pct}%")
    logger.info(f"  Max daily Δ  : {config.max_daily_loss_pct}%")
    logger.info(f"  Cooldown     : {config.cooldown_minutes}m")
    logger.info(f"  Check every  : {config.check_interval}s")
    if config.telegram_relay_url:
        logger.info(f"  Telegram     : {config.telegram_relay_url}")
    else:
        logger.info("  Telegram     : disabled")
    logger.info("=" * 60)

    if not config.symbols:
        logger.error("No symbols configured.")
        sys.exit(1)

    bot = CryptoBot(config)

    def _handle_shutdown(sig, frame):
        logger.info(f"Signal {sig} received – shutting down …")
        bot.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    try:
        bot.run()
    except Exception as exc:
        logger.critical(f"Fatal error: {exc}", exc_info=True)
        bot.shutdown()
        sys.exit(1)


if __name__ == "__main__":
    main()
