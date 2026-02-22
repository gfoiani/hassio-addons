#!/usr/bin/env python3
"""
Day Trading Bot – Entry Point

Reads configuration from:
  1. Command-line arguments (set by run.sh from bashio::config in HA mode)
  2. Environment variables (for standalone Docker / local testing)
"""

import argparse
import logging
import os
import signal
import sys

from trading.config import TradingConfig
from trading.bot import TradingBot

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("trading_bot")


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Day Trading Bot – NYSE & LSE")

    def env(key: str, default: str = "") -> str:
        return os.getenv(key, default)

    p.add_argument("--broker",              default=env("BROKER", "xtb"))
    p.add_argument("--api-key",             default=env("API_KEY", ""))
    p.add_argument("--api-secret",          default=env("API_SECRET", ""))
    p.add_argument("--paper-trading",       default=env("PAPER_TRADING", "true"))
    p.add_argument("--exchanges",           default=env("EXCHANGES", "NYSE,LSE"))
    p.add_argument("--symbols-nyse",        default=env("SYMBOLS_NYSE", ""))
    p.add_argument("--symbols-lse",         default=env("SYMBOLS_LSE", ""))
    p.add_argument("--max-position-value",  default=env("MAX_POSITION_VALUE", "1000"))
    p.add_argument("--stop-loss-pct",       default=env("STOP_LOSS_PCT", "2.0"))
    p.add_argument("--take-profit-pct",     default=env("TAKE_PROFIT_PCT", "4.0"))
    p.add_argument("--max-daily-loss-pct",  default=env("MAX_DAILY_LOSS_PCT", "5.0"))
    p.add_argument("--strategy",            default=env("STRATEGY", "orb"))
    p.add_argument("--orb-minutes",         default=env("ORB_MINUTES", "15"))
    p.add_argument("--pre-market-minutes",  default=env("PRE_MARKET_MINUTES", "30"))
    p.add_argument("--close-minutes",       default=env("CLOSE_MINUTES", "15"))
    p.add_argument("--check-interval",      default=env("CHECK_INTERVAL", "30"))

    # Directa SIM specific (ignored for XTB)
    p.add_argument("--directa-host",    default=env("DIRECTA_HOST", "127.0.0.1"))

    # Telegram relay service (optional)
    p.add_argument("--telegram-relay-url", default=env("TELEGRAM_RELAY_URL", ""))
    p.add_argument("--telegram-api-key",   default=env("TELEGRAM_API_KEY", ""))

    return p.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = _parse_args()

    def _parse_symbols(raw: str):
        return [s.strip() for s in raw.split(",") if s.strip()]

    config = TradingConfig(
        broker=args.broker,
        api_key=args.api_key,
        api_secret=args.api_secret,
        paper_trading=args.paper_trading.lower() in ("true", "1", "yes"),
        exchanges=_parse_symbols(args.exchanges),
        symbols_nyse=_parse_symbols(args.symbols_nyse),
        symbols_lse=_parse_symbols(args.symbols_lse),
        max_position_value=float(args.max_position_value),
        stop_loss_pct=float(args.stop_loss_pct),
        take_profit_pct=float(args.take_profit_pct),
        max_daily_loss_pct=float(args.max_daily_loss_pct),
        strategy=args.strategy,
        orb_minutes=int(args.orb_minutes),
        pre_market_minutes=int(args.pre_market_minutes),
        close_minutes=int(args.close_minutes),
        check_interval=int(args.check_interval),
        directa_host=args.directa_host,
        telegram_relay_url=args.telegram_relay_url,
        telegram_api_key=args.telegram_api_key,
    )

    logger.info("=" * 60)
    logger.info("  Day Trading Bot")
    logger.info("=" * 60)
    logger.info(f"  Broker       : {config.broker} ({'PAPER' if config.paper_trading else 'LIVE ⚠️'})")
    if config.broker.lower() == "directa":
        logger.info(f"  Directa Darwin: {config.directa_host}:10002")
    logger.info(f"  Exchanges    : {', '.join(config.exchanges)}")
    logger.info(f"  Strategy     : {config.strategy}")
    logger.info(f"  NYSE symbols : {', '.join(config.symbols_nyse) or '(none)'}")
    logger.info(f"  LSE symbols  : {', '.join(config.symbols_lse) or '(none)'}")
    logger.info(f"  Stop loss    : {config.stop_loss_pct}%")
    logger.info(f"  Take profit  : {config.take_profit_pct}%")
    logger.info(f"  Max pos.     : {config.max_position_value}")
    logger.info(f"  Max daily Δ  : {config.max_daily_loss_pct}%")
    if config.telegram_relay_url:
        logger.info(f"  Telegram     : {config.telegram_relay_url}")
    else:
        logger.info("  Telegram     : disabled")
    logger.info("=" * 60)

    if not config.all_symbols:
        logger.error("No symbols configured. Add NYSE and/or LSE symbols in the addon options.")
        sys.exit(1)

    bot = TradingBot(config)

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
