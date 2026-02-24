"""
CryptoBot – main orchestrator for Binance Spot intraday trading.

Runs 24/7 (crypto never closes). Loop:
  1. Poll Telegram commands
  2. For each symbol:
     a. If position open → check if OCO fired (SL/TP hit server-side)
     b. If no position → evaluate momentum signal → enter if triggered
  3. Daily reset at UTC midnight
  4. Sleep check_interval seconds
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from trading.config import CryptoTradingConfig
from trading.position import Position, PositionSide, PositionStatus
from trading.risk import RiskManager
from trading.strategy import MomentumStrategy, Signal
from trading.broker import create_broker
from trading.broker.binance_broker import BinanceBroker
from trading.telegram_notifier import TelegramNotifier

logger = logging.getLogger("crypto_bot.bot")

STORAGE_DIR = Path("/data")
POSITIONS_FILE = STORAGE_DIR / "crypto_positions.json"
TRADES_LOG_FILE = STORAGE_DIR / "crypto_trades.log"


class CryptoBot:
    def __init__(self, config: CryptoTradingConfig):
        self._config = config
        self._broker: BinanceBroker = create_broker(config)
        self._strategy = MomentumStrategy()
        self._risk = RiskManager(config)
        self._running = False

        # Active positions: symbol → Position
        self._positions: Dict[str, Position] = {}

        # Cooldown tracking: symbol → UTC datetime when position was closed
        self._cooldowns: Dict[str, datetime] = {}

        # Telegram relay
        self._telegram = TelegramNotifier(
            relay_url=config.telegram_relay_url,
            api_key=config.telegram_api_key,
        )

        # Manual halt flag (set by /halt command)
        self._manual_halt: bool = False

        # Track UTC day for daily reset
        self._current_day: Optional[int] = None

        STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self):
        logger.info("Connecting to Binance …")
        if not self._broker.connect():
            raise RuntimeError("Failed to connect to Binance. Check API credentials.")

        # Pre-load symbol filters
        for symbol in self._config.symbols:
            try:
                self._broker.get_symbol_info(symbol)
                logger.info(f"Symbol info loaded: {symbol}")
            except Exception as exc:
                logger.warning(f"Could not load symbol info for {symbol}: {exc}")

        self._load_positions()
        self._running = True
        self._telegram.start_keepalive()

        logger.info(
            f"Crypto bot started. Symbols: {self._config.symbols} | "
            f"Timeframe: {self._config.timeframe}m | "
            f"Paper: {self._config.paper_trading}"
        )
        self._telegram.notify(
            f"🚀 <b>Crypto Trading Bot started</b>\n"
            f"Symbols: {', '.join(self._config.symbols)}\n"
            f"Timeframe: {self._config.timeframe}m | "
            f"Mode: {'📝 Paper' if self._config.paper_trading else '💰 Live'}"
        )

        while self._running:
            try:
                self._tick()
            except Exception as exc:
                logger.error(f"Unhandled error in main loop: {exc}", exc_info=True)
            time.sleep(self._config.check_interval)

    def shutdown(self):
        logger.info("Shutdown requested …")
        self._running = False
        self._save_positions()
        try:
            self._broker.disconnect()
        except Exception:
            pass
        logger.info("Shutdown complete.")

    # ------------------------------------------------------------------
    # Main tick
    # ------------------------------------------------------------------

    def _tick(self):
        now_utc = datetime.now(timezone.utc)

        # Daily reset at UTC midnight
        today = now_utc.date().toordinal()
        if self._current_day is None:
            self._current_day = today
            self._daily_init()
        elif today != self._current_day:
            self._current_day = today
            self._daily_reset()

        # Process Telegram commands
        self._process_telegram_commands()

        # Process each symbol
        for symbol in self._config.symbols:
            try:
                self._process_symbol(symbol, now_utc)
            except Exception as exc:
                logger.error(f"Error processing {symbol}: {exc}", exc_info=True)

    def _daily_init(self):
        try:
            value = self._broker.get_account_value()
            self._risk.set_initial_portfolio_value(value)
        except Exception as exc:
            logger.warning(f"Could not fetch account value for daily init: {exc}")

    def _daily_reset(self):
        logger.info("UTC midnight — daily reset")
        self._risk.reset_daily()
        self._daily_init()

    # ------------------------------------------------------------------
    # Symbol processing
    # ------------------------------------------------------------------

    def _process_symbol(self, symbol: str, now_utc: datetime):
        pos = self._positions.get(symbol)

        # ── Open position: check if OCO triggered ─────────────────────
        if pos and pos.status == PositionStatus.OPEN:
            current_price = self._broker.get_quote(symbol)
            if current_price:
                pos.current_price = current_price

            # Check if OCO was triggered server-side (SL or TP hit)
            if pos.oco_order_list_id:
                oco_active = self._broker.has_pending_oco(symbol, pos.oco_order_list_id)
                if not oco_active:
                    # OCO fired — determine if it was SL or TP
                    price = current_price or pos.current_price
                    if price <= pos.stop_loss:
                        reason = "stop_loss"
                    elif price >= pos.take_profit:
                        reason = "take_profit"
                    else:
                        reason = "take_profit"  # default: assume TP if unclear
                    self._record_closed_position(pos, price, reason)
                    return

            # Fallback local SL/TP check (e.g. if OCO status unavailable)
            if pos.is_stop_loss_hit():
                logger.info(f"{symbol}: local SL check hit at {pos.current_price:.6f}")
                self._exit_position(symbol, pos.current_price, "stop_loss")
            elif pos.is_take_profit_hit():
                logger.info(f"{symbol}: local TP check hit at {pos.current_price:.6f}")
                self._exit_position(symbol, pos.current_price, "take_profit")
            else:
                logger.debug(
                    f"{symbol} LONG @ {pos.current_price:.6f} "
                    f"P&L={pos.unrealized_pnl:+.4f} USDT ({pos.unrealized_pnl_pct:+.2f}%)"
                )
            return

        # ── No position: check cooldown then evaluate signal ──────────
        if self._manual_halt:
            return

        # Check daily loss limit
        try:
            equity = self._broker.get_account_value()
            if self._risk.should_halt_trading(equity):
                logger.warning("Daily loss limit reached — no new entries.")
                self._telegram.notify(
                    "⛔ <b>Daily loss limit reached.</b> No new positions will be opened today."
                )
                self._manual_halt = True
                return
        except Exception:
            pass

        # Cooldown check
        if symbol in self._cooldowns:
            elapsed_minutes = (now_utc - self._cooldowns[symbol]).total_seconds() / 60
            if elapsed_minutes < self._config.cooldown_minutes:
                remaining = int(self._config.cooldown_minutes - elapsed_minutes)
                logger.debug(f"{symbol}: cooldown active ({remaining}m remaining)")
                return

        # Check signal
        self._check_and_enter(symbol)

    def _check_and_enter(self, symbol: str):
        try:
            bars = self._broker.get_bars(
                symbol, self._config.timeframe, limit=50
            )
            if bars.empty:
                return

            signal = self._strategy.check_signal(symbol, bars)
            if signal != Signal.LONG:
                return

            self._enter_position(symbol)

        except Exception as exc:
            logger.error(f"Signal check error for {symbol}: {exc}", exc_info=True)

    # ------------------------------------------------------------------
    # Position entry
    # ------------------------------------------------------------------

    def _enter_position(self, symbol: str):
        price = self._broker.get_quote(symbol)
        if not price or price <= 0:
            logger.warning(f"{symbol}: cannot enter — no price available")
            return

        filters = self._broker.get_symbol_info(symbol)
        qty = self._risk.calculate_quantity(price, filters["step_size"])
        if qty <= 0 or qty < filters["min_qty"]:
            logger.warning(
                f"{symbol}: cannot enter — qty {qty} too small "
                f"(min={filters['min_qty']}, max_usdt={self._config.max_position_value_usdt})"
            )
            return

        # Check buying power
        buying_power = self._broker.get_buying_power()
        if buying_power < qty * price:
            logger.warning(
                f"{symbol}: insufficient buying power {buying_power:.2f} USDT "
                f"(need {qty * price:.2f} USDT)"
            )
            return

        stop_loss = self._risk.stop_loss_price(price)
        take_profit = self._risk.take_profit_price(price)

        self._telegram.notify(
            f"🔔 <b>Signal detected</b> – LONG <code>{symbol}</code>\n"
            f"Price: <b>{price:.6f}</b> | Qty: {qty}\n"
            f"SL: {stop_loss:.6f} | TP: {take_profit:.6f}\n"
            f"Placing order…"
        )

        result = self._broker.place_bracket_order(
            symbol=symbol,
            qty=qty,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

        if result is None:
            logger.error(f"{symbol}: bracket order failed")
            self._telegram.notify(f"❌ <b>Order failed</b> for <code>{symbol}</code>")
            return

        fill_price = result.get("fill_price", price)
        position = Position(
            symbol=symbol,
            side=PositionSide.LONG,
            entry_price=fill_price,
            quantity=qty,
            stop_loss=stop_loss,
            take_profit=take_profit,
            order_id=result.get("order_id"),
            oco_order_list_id=result.get("oco_order_list_id"),
            current_price=fill_price,
        )
        self._positions[symbol] = position
        self._save_positions()
        self._log_trade("ENTER", position)

        logger.info(
            f"ENTERED LONG {qty} {symbol} @ {fill_price:.6f} | "
            f"SL={stop_loss:.6f} TP={take_profit:.6f}"
        )
        self._telegram.notify(
            f"✅ <b>Position opened</b> – LONG <code>{symbol}</code>\n"
            f"Entry: <b>{fill_price:.6f}</b> | Qty: {qty}\n"
            f"SL: {stop_loss:.6f} | TP: {take_profit:.6f}\n"
            f"Cost: {fill_price * qty:.2f} USDT"
        )

    # ------------------------------------------------------------------
    # Position exit
    # ------------------------------------------------------------------

    def _record_closed_position(self, pos: Position, price: float, reason: str):
        """Record a position that was closed server-side by the OCO order."""
        pos.close(price, reason)
        self._cooldowns[pos.symbol] = datetime.now(timezone.utc)
        pnl = pos.realized_pnl or 0.0
        self._risk.record_realized_pnl(pnl)
        self._save_positions()
        self._log_trade("EXIT", pos)
        self._notify_exit(pos, price, reason, pnl)

    def _exit_position(self, symbol: str, price: float, reason: str):
        """Manually close a position via market sell + cancel OCO."""
        pos = self._positions.get(symbol)
        if pos is None or pos.status != PositionStatus.OPEN:
            return

        success = self._broker.close_position(
            symbol=symbol,
            qty=pos.quantity,
            oco_order_list_id=pos.oco_order_list_id,
        )
        if success:
            self._record_closed_position(pos, price, reason)
        else:
            logger.error(f"{symbol}: failed to close position — will retry next tick")

    def _notify_exit(self, pos: Position, price: float, reason: str, pnl: float):
        emoji = "🟢" if pnl >= 0 else "🔴"
        reason_labels = {
            "stop_loss": "Stop-loss hit 🔴",
            "take_profit": "Take-profit hit 🟢",
            "manual": "Manual close",
        }
        label = reason_labels.get(reason, reason)
        self._telegram.notify(
            f"{emoji} <b>Position closed</b> – <code>{pos.symbol}</code>\n"
            f"Reason: {label}\n"
            f"Exit: <b>{price:.6f}</b> | P&amp;L: <b>{pnl:+.4f} USDT</b> "
            f"({pos.unrealized_pnl_pct:+.2f}%)"
        )

    # ------------------------------------------------------------------
    # Telegram commands
    # ------------------------------------------------------------------

    def _process_telegram_commands(self):
        try:
            commands = self._telegram.poll_commands()
        except Exception as exc:
            logger.warning(f"Failed to poll Telegram: {exc}")
            return

        for cmd in commands:
            command = cmd.get("command", "")
            args = cmd.get("args", "").strip()
            chat_id = cmd.get("chat_id")
            logger.info(f"Telegram /{command} {args}")

            try:
                if command in ("status", "positions"):
                    self._cmd_status(chat_id)
                elif command == "halt":
                    self._manual_halt = True
                    self._telegram.send_result(
                        chat_id,
                        "⛔ <b>Trading halted.</b> No new positions will be opened.\n"
                        "Use /resume to re-enable.",
                    )
                elif command == "resume":
                    self._manual_halt = False
                    self._telegram.send_result(
                        chat_id,
                        "✅ <b>Trading resumed.</b>",
                    )
                elif command == "close":
                    self._cmd_close(chat_id, args.upper())
                else:
                    self._telegram.send_result(
                        chat_id,
                        f"❓ Unknown command: <code>/{command}</code>\n\n"
                        f"Available: /status /halt /resume /close SYMBOL",
                    )
            except Exception as exc:
                logger.error(f"Error processing /{command}: {exc}")
                self._telegram.send_result(chat_id, f"❌ Error: {exc}")

    def _cmd_status(self, chat_id: int):
        open_positions = [
            pos for pos in self._positions.values()
            if pos.status == PositionStatus.OPEN
        ]
        halt_note = " ⛔ <i>Halted</i>" if self._manual_halt else ""
        if not open_positions:
            self._telegram.send_result(
                chat_id,
                f"📊 <b>Crypto Bot Status</b>{halt_note}\n\nNo open positions.",
            )
            return

        lines = [f"📊 <b>Open positions</b>{halt_note}\n"]
        for pos in open_positions:
            pnl = pos.unrealized_pnl
            pct = pos.unrealized_pnl_pct
            emoji = "🟢" if pnl >= 0 else "🔴"
            lines.append(
                f"{emoji} <code>{pos.symbol}</code> LONG {pos.quantity}\n"
                f"   Entry: {pos.entry_price:.6f} | Now: {pos.current_price:.6f}\n"
                f"   P&amp;L: <b>{pnl:+.4f} USDT</b> ({pct:+.2f}%)\n"
                f"   SL: {pos.stop_loss:.6f} | TP: {pos.take_profit:.6f}"
            )
        self._telegram.send_result(chat_id, "\n".join(lines))

    def _cmd_close(self, chat_id: int, symbol: str):
        if not symbol:
            self._telegram.send_result(
                chat_id,
                "❌ Usage: <code>/close SYMBOL</code>  (e.g. <code>/close BTCUSDT</code>)",
            )
            return

        pos = self._positions.get(symbol)
        if pos is None or pos.status != PositionStatus.OPEN:
            self._telegram.send_result(
                chat_id,
                f"❌ No open position for <code>{symbol}</code>.",
            )
            return

        price = self._broker.get_quote(symbol) or pos.current_price
        self._exit_position(symbol, price, "manual")
        self._telegram.send_result(
            chat_id,
            f"✅ Closing <code>{symbol}</code> at market…",
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_positions(self):
        try:
            data = {sym: pos.to_dict() for sym, pos in self._positions.items()}
            POSITIONS_FILE.write_text(json.dumps(data, indent=2, default=str))
        except Exception as exc:
            logger.warning(f"Could not save positions: {exc}")

    def _load_positions(self):
        try:
            if POSITIONS_FILE.exists():
                data = json.loads(POSITIONS_FILE.read_text())
                self._positions = {
                    sym: Position.from_dict(pos_data)
                    for sym, pos_data in data.items()
                }
                open_count = sum(
                    1 for p in self._positions.values()
                    if p.status == PositionStatus.OPEN
                )
                logger.info(
                    f"Loaded {len(self._positions)} positions from disk "
                    f"({open_count} open)"
                )
        except Exception as exc:
            logger.warning(f"Could not load positions: {exc}")

    def _log_trade(self, action: str, position: Position):
        try:
            now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            if action == "ENTER":
                line = (
                    f"{now} UTC | ENTER | {position.symbol:<12} | LONG  |"
                    f" qty={position.quantity:<12} | entry={position.entry_price:.8f}"
                    f" | SL={position.stop_loss:.8f} | TP={position.take_profit:.8f}"
                    f" | cost={position.cost_usdt:.2f} USDT"
                )
            else:
                pnl = position.realized_pnl or 0.0
                reason = (position.close_reason or "unknown").replace("_", "-")
                line = (
                    f"{now} UTC | EXIT  | {position.symbol:<12} | LONG  |"
                    f" qty={position.quantity:<12} | entry={position.entry_price:.8f}"
                    f" | exit={position.close_price:.8f}"
                    f" | P&L={pnl:+.6f} USDT | reason={reason}"
                )
            with open(TRADES_LOG_FILE, "a") as f:
                f.write(line + "\n")
        except Exception as exc:
            logger.warning(f"Could not write trade log: {exc}")
