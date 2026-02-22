"""
TradingBot – main orchestrator.

State machine per exchange:

  IDLE
   │
   ├─ market day? → PRE_MARKET (N min before open)
   │
   ├─ PRE_MARKET → log / prepare symbols
   │
   ├─ ORB_COLLECTION (first orb_minutes after open)
   │     collect high/low candles
   │
   ├─ TRADING (after ORB, before closing window)
   │     check signals → enter positions
   │     monitor open positions → SL / TP
   │
   ├─ CLOSING_WINDOW (last N min before close)
   │     close ALL positions for this exchange
   │
   └─ CLOSED (after market close)
         reset strategy ORB data
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from trading.config import TradingConfig
from trading.exchanges import ExchangeSchedule, get_exchange
from trading.position import Position, PositionSide, PositionStatus
from trading.risk import RiskManager
from trading.strategy import ORBStrategy, MomentumStrategy, Signal, create_strategy
from trading.broker import create_broker
from trading.broker.base import BrokerBase
from trading.telegram_notifier import TelegramNotifier

logger = logging.getLogger("trading_bot.bot")

STORAGE_DIR = Path("/usr/src/app/storage")
POSITIONS_FILE = STORAGE_DIR / "positions.json"
TRADES_LOG_FILE = STORAGE_DIR / "trades.log"


class ExchangeState:
    """Per-exchange runtime state."""

    IDLE = "idle"
    PRE_MARKET = "pre_market"
    ORB_COLLECTION = "orb_collection"
    TRADING = "trading"
    CLOSING = "closing"
    CLOSED = "closed"

    def __init__(self, exchange: ExchangeSchedule):
        self.exchange = exchange
        self.phase: str = self.IDLE
        self.orb_finalized: bool = False
        self.day_initialized: bool = False

    def reset_for_new_day(self):
        self.phase = self.IDLE
        self.orb_finalized = False
        self.day_initialized = False


class TradingBot:
    def __init__(self, config: TradingConfig):
        self._config = config
        self._broker: BrokerBase = create_broker(config)
        self._strategy = create_strategy(
            config.strategy, orb_minutes=config.orb_minutes
        )
        self._risk = RiskManager(config)
        self._running = False

        # Build exchange state objects
        self._exchange_states: Dict[str, ExchangeState] = {
            name: ExchangeState(get_exchange(name))
            for name in config.exchanges
        }

        # Active positions tracked by the bot (symbol → Position)
        self._positions: Dict[str, Position] = {}

        # Telegram relay client (no-op if relay_url is empty)
        self._telegram = TelegramNotifier(
            relay_url=config.telegram_relay_url,
            api_key=config.telegram_api_key,
        )

        # Manual halt flag set via /halt Telegram command
        self._manual_halt: bool = False

        # Ensure storage directory exists
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self):
        """Start the main event loop."""
        logger.info("Connecting to broker …")
        if not self._broker.connect():
            raise RuntimeError("Failed to connect to broker. Check credentials.")

        self._running = True
        logger.info(
            f"Trading bot started. Exchanges: {list(self._exchange_states.keys())} | "
            f"Strategy: {self._config.strategy}"
        )

        while self._running:
            try:
                self._tick()
            except Exception as exc:
                logger.error(f"Unhandled error in main loop: {exc}", exc_info=True)
            time.sleep(self._config.check_interval)

    def shutdown(self):
        """Gracefully close all positions and stop the loop."""
        logger.info("Shutdown requested – closing all positions …")
        self._running = False
        try:
            self._broker.close_all_positions()
        except Exception as exc:
            logger.error(f"Error during shutdown close: {exc}")
        try:
            self._broker.disconnect()
        except Exception:
            pass
        self._save_positions()
        logger.info("Shutdown complete.")

    # ------------------------------------------------------------------
    # Main tick
    # ------------------------------------------------------------------

    def _tick(self):
        # Process Telegram commands first
        self._process_telegram_commands()

        for name, state in self._exchange_states.items():
            self._process_exchange(name, state)

        # After processing exchanges, update and enforce SL/TP on all positions
        self._update_positions()

    # ------------------------------------------------------------------
    # Exchange processing
    # ------------------------------------------------------------------

    def _process_exchange(self, name: str, state: ExchangeState):
        ex = state.exchange
        symbols = self._config.symbols_for_exchange(name)
        if not symbols:
            return

        # ── Not a market day ──────────────────────────────────────────
        if not ex.is_market_day():
            if state.phase != ExchangeState.CLOSED:
                logger.debug(f"{name}: market closed (weekend/holiday)")
                state.phase = ExchangeState.CLOSED
            return

        # ── Market is closed (post-close) ─────────────────────────────
        if not ex.is_open() and ex.minutes_until_open() is None:
            if state.phase not in (ExchangeState.CLOSED, ExchangeState.IDLE):
                logger.info(f"{name}: market closed for the day. Resetting.")
                self._end_of_day(name, state, symbols)
            return

        # ── Pre-market window ─────────────────────────────────────────
        if ex.is_pre_market_window(self._config.pre_market_minutes):
            if state.phase != ExchangeState.PRE_MARKET:
                state.phase = ExchangeState.PRE_MARKET
                mins = ex.minutes_until_open()
                logger.info(
                    f"{name}: pre-market window ({mins:.0f} min to open). "
                    f"Symbols: {symbols}"
                )
                self._pre_market_prepare(name, state)
            return

        # ── ORB collection window ─────────────────────────────────────
        if ex.is_open() and ex.is_orb_window(self._config.orb_minutes):
            if state.phase != ExchangeState.ORB_COLLECTION:
                state.phase = ExchangeState.ORB_COLLECTION
                logger.info(f"{name}: ORB collection window started")
                self._initialize_day(name, state, symbols)
            self._collect_orb_data(name, symbols)
            return

        # ── ORB just ended → finalize ─────────────────────────────────
        if (
            ex.is_open()
            and not ex.is_orb_window(self._config.orb_minutes)
            and not state.orb_finalized
            and self._config.strategy == "orb"
        ):
            state.orb_finalized = True
            if isinstance(self._strategy, ORBStrategy):
                for sym in symbols:
                    self._strategy.finalize_orb(sym)
            logger.info(f"{name}: ORB collection complete")

        # ── Closing window ────────────────────────────────────────────
        if ex.is_closing_window(self._config.close_minutes):
            if state.phase != ExchangeState.CLOSING:
                state.phase = ExchangeState.CLOSING
                logger.info(
                    f"{name}: closing window ({self._config.close_minutes} min to close). "
                    "Closing all positions."
                )
                self._close_exchange_positions(name, symbols)
            return

        # ── Active trading ────────────────────────────────────────────
        if ex.is_open():
            if state.phase not in (ExchangeState.TRADING, ExchangeState.ORB_COLLECTION):
                state.phase = ExchangeState.TRADING
                logger.info(f"{name}: entering active trading phase")
            self._check_signals(name, symbols)

    # ------------------------------------------------------------------
    # Pre-market
    # ------------------------------------------------------------------

    def _pre_market_prepare(self, exchange_name: str, state: ExchangeState):
        state.reset_for_new_day()
        state.phase = ExchangeState.PRE_MARKET
        self._risk.reset_daily()
        logger.info(
            f"{exchange_name}: prepared for new trading day. "
            f"Config → SL={self._config.stop_loss_pct}% "
            f"TP={self._config.take_profit_pct}% "
            f"MaxPos={self._config.max_position_value}"
        )

    # ------------------------------------------------------------------
    # Day initialisation (called at first ORB tick)
    # ------------------------------------------------------------------

    def _initialize_day(self, exchange_name: str, state: ExchangeState, symbols: List[str]):
        if state.day_initialized:
            return
        state.day_initialized = True

        try:
            equity = self._broker.get_account_value()
            self._risk.set_initial_portfolio_value(equity)
        except Exception as exc:
            logger.warning(f"Could not fetch account equity: {exc}")

        # Reset strategy ORB data
        if isinstance(self._strategy, ORBStrategy):
            for sym in symbols:
                self._strategy.reset_symbol(sym)

        logger.info(f"{exchange_name}: day initialised for symbols {symbols}")

    # ------------------------------------------------------------------
    # ORB data collection
    # ------------------------------------------------------------------

    def _collect_orb_data(self, exchange_name: str, symbols: List[str]):
        if not isinstance(self._strategy, ORBStrategy):
            return
        for sym in symbols:
            try:
                # Fetch 1-minute bars; use last bar's high/low for live tick
                bars = self._broker.get_bars(sym, timeframe_minutes=1, limit=5)
                if bars.empty:
                    continue
                last = bars.iloc[-1]
                self._strategy.update_orb(sym, float(last["high"]), float(last["low"]))
            except Exception as exc:
                logger.warning(f"ORB data error for {sym}: {exc}")

    # ------------------------------------------------------------------
    # Telegram command processing
    # ------------------------------------------------------------------

    def _process_telegram_commands(self):
        try:
            commands = self._telegram.poll_commands()
        except Exception as exc:
            logger.warning(f"Failed to poll Telegram commands: {exc}")
            return

        for cmd in commands:
            command = cmd.get("command", "")
            args = cmd.get("args", "")
            chat_id = cmd.get("chat_id")
            cmd_id = cmd.get("id", "?")

            logger.info(f"Telegram command [{cmd_id}]: /{command} {args}")

            try:
                if command == "status":
                    self._cmd_status(chat_id)
                elif command in ("positions",):
                    self._cmd_status(chat_id)
                elif command == "halt":
                    self._manual_halt = True
                    self._telegram.send_result(
                        chat_id,
                        "⛔ <b>Trading halted.</b> No new positions will be opened.\n"
                        "Use /resume to re-enable trading.",
                    )
                    logger.info("Trading manually halted via Telegram.")
                elif command == "resume":
                    self._manual_halt = False
                    self._telegram.send_result(
                        chat_id,
                        "✅ <b>Trading resumed.</b> New signals will be acted upon.",
                    )
                    logger.info("Trading manually resumed via Telegram.")
                elif command == "close":
                    self._cmd_close(chat_id, args.strip().upper())
                else:
                    self._telegram.send_result(
                        chat_id,
                        f"❓ Unknown command: <code>{command}</code>",
                    )
            except Exception as exc:
                logger.error(f"Error processing Telegram command /{command}: {exc}")
                self._telegram.send_result(
                    chat_id,
                    f"❌ Error executing <code>/{command}</code>: {exc}",
                )

    def _cmd_status(self, chat_id: int):
        open_positions = [
            pos for pos in self._positions.values()
            if pos.status == PositionStatus.OPEN
        ]
        halt_flag = " ⛔ <i>Manual halt active</i>" if self._manual_halt else ""
        if not open_positions:
            self._telegram.send_result(
                chat_id,
                f"📊 <b>Status</b>{halt_flag}\n\nNo open positions.",
            )
            return

        lines = [f"📊 <b>Open positions</b>{halt_flag}\n"]
        for pos in open_positions:
            direction = "LONG" if pos.side == PositionSide.LONG else "SHORT"
            pnl = pos.unrealized_pnl
            pnl_pct = pos.unrealized_pnl_pct
            emoji = "🟢" if pnl >= 0 else "🔴"
            lines.append(
                f"{emoji} <code>{pos.symbol}</code> {direction} {pos.quantity}x\n"
                f"   Entry: {pos.entry_price:.4f} | Now: {pos.current_price:.4f}\n"
                f"   P&amp;L: <b>{pnl:+.2f}</b> ({pnl_pct:+.2f}%)\n"
                f"   SL: {pos.stop_loss:.4f} | TP: {pos.take_profit:.4f}"
            )
        self._telegram.send_result(chat_id, "\n".join(lines))

    def _cmd_close(self, chat_id: int, symbol: str):
        if not symbol:
            self._telegram.send_result(
                chat_id,
                "❌ Usage: <code>/close SYMBOL</code>  (e.g. <code>/close AAPL.US</code>)",
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
            f"✅ Closing <code>{symbol}</code> at market price…",
        )

    # ------------------------------------------------------------------
    # Signal detection & entry
    # ------------------------------------------------------------------

    def _check_signals(self, exchange_name: str, symbols: List[str]):
        # Manual halt via Telegram /halt command
        if self._manual_halt:
            return

        # Safety: halt if daily loss limit reached
        try:
            equity = self._broker.get_account_value()
            if self._risk.should_halt_trading(equity):
                logger.warning(f"{exchange_name}: trading halted – daily loss limit.")
                self._telegram.notify(
                    f"⛔ <b>Trading halted</b> – daily loss limit reached on <b>{exchange_name}</b>.\n"
                    f"No new positions will be opened today."
                )
                return
        except Exception:
            pass

        for sym in symbols:
            # Skip symbols where we already hold a position
            if sym in self._positions and self._positions[sym].status == PositionStatus.OPEN:
                continue

            try:
                signal = self._get_signal(sym)
                if signal == Signal.NONE:
                    continue

                self._enter_position(sym, exchange_name, signal)

            except Exception as exc:
                logger.error(f"Signal check error for {sym}: {exc}", exc_info=True)

    def _get_signal(self, symbol: str) -> Signal:
        if isinstance(self._strategy, ORBStrategy):
            price = self._broker.get_quote(symbol)
            if price is None:
                return Signal.NONE
            bars = self._broker.get_bars(symbol, timeframe_minutes=1, limit=30)
            avg_vol = float(bars["volume"].mean()) if not bars.empty else 0.0
            last_vol = float(bars.iloc[-1]["volume"]) if not bars.empty else 0.0
            return self._strategy.check_signal(symbol, price, last_vol, avg_vol)

        if isinstance(self._strategy, MomentumStrategy):
            bars = self._broker.get_bars(symbol, timeframe_minutes=5, limit=40)
            return self._strategy.check_signal(symbol, bars)

        return Signal.NONE

    # ------------------------------------------------------------------
    # Position entry
    # ------------------------------------------------------------------

    def _enter_position(self, symbol: str, exchange: str, signal: Signal):
        side = PositionSide.LONG if signal == Signal.LONG else PositionSide.SHORT
        price = self._broker.get_quote(symbol)
        if price is None or price <= 0:
            logger.warning(f"Cannot enter {symbol}: no price available")
            return

        qty = self._risk.calculate_quantity(price)
        if qty <= 0:
            logger.warning(f"Cannot enter {symbol}: position size is 0 (price={price}, max={self._config.max_position_value})")
            return

        # Determine SL/TP
        if isinstance(self._strategy, ORBStrategy) and self._strategy.is_established(symbol):
            stop_loss = self._strategy.orb_stop_loss(symbol, side)
            if stop_loss is None:
                stop_loss = self._risk.stop_loss_price(price, side)
        else:
            stop_loss = self._risk.stop_loss_price(price, side)

        take_profit = self._risk.take_profit_price(price, side)

        # Pre-trade notification
        direction = "LONG 📈" if side == PositionSide.LONG else "SHORT 📉"
        self._telegram.notify(
            f"🔔 <b>Signal detected</b> – {direction} <code>{symbol}</code>\n"
            f"Price: <b>{price:.4f}</b> | Qty: {qty}\n"
            f"SL: {stop_loss:.4f} | TP: {take_profit:.4f}\n"
            f"Placing order…"
        )

        order_id = self._broker.place_bracket_order(
            symbol=symbol,
            qty=qty,
            side="buy" if side == PositionSide.LONG else "sell",
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

        if order_id is None:
            logger.error(f"Order rejected for {symbol}")
            self._telegram.notify(f"❌ <b>Order rejected</b> for <code>{symbol}</code>")
            return

        position = Position(
            symbol=symbol,
            exchange=exchange,
            side=side,
            entry_price=price,
            quantity=qty,
            stop_loss=stop_loss,
            take_profit=take_profit,
            order_id=order_id,
            current_price=price,
        )
        self._positions[symbol] = position
        self._save_positions()

        logger.info(
            f"ENTERED {side.value.upper()} {qty}x {symbol} @ {price:.4f} | "
            f"SL={stop_loss:.4f} TP={take_profit:.4f}"
        )
        self._log_trade("ENTER", position)
        self._telegram.notify(
            f"✅ <b>Position opened</b> – {direction} <code>{symbol}</code>\n"
            f"Entry: <b>{price:.4f}</b> | Qty: {qty}\n"
            f"SL: {stop_loss:.4f} | TP: {take_profit:.4f}"
        )

    # ------------------------------------------------------------------
    # Position management
    # ------------------------------------------------------------------

    def _update_positions(self):
        """Update current prices and enforce SL/TP for all open positions."""
        for sym, pos in list(self._positions.items()):
            if pos.status != PositionStatus.OPEN:
                continue
            try:
                price = self._broker.get_quote(sym)
                if price is None:
                    continue
                pos.current_price = price

                if pos.is_stop_loss_hit():
                    logger.info(f"{sym}: stop loss hit at {price:.4f}")
                    self._exit_position(sym, price, "stop_loss")
                elif pos.is_take_profit_hit():
                    logger.info(f"{sym}: take profit hit at {price:.4f}")
                    self._exit_position(sym, price, "take_profit")
                else:
                    logger.debug(
                        f"{sym} {pos.side.value} @ {price:.4f} "
                        f"PnL={pos.unrealized_pnl:+.2f} ({pos.unrealized_pnl_pct:+.2f}%)"
                    )
            except Exception as exc:
                logger.warning(f"Position update error for {sym}: {exc}")

    def _exit_position(self, symbol: str, price: float, reason: str):
        pos = self._positions.get(symbol)
        if pos is None or pos.status != PositionStatus.OPEN:
            return

        success = self._broker.close_position(symbol)
        if success:
            pos.close(price, reason)
            self._risk.record_realized_pnl(pos.realized_pnl or 0.0)
            self._save_positions()
            self._log_trade("EXIT", pos)
            pnl = pos.realized_pnl or 0.0
            emoji = "🟢" if pnl >= 0 else "🔴"
            reason_labels = {
                "stop_loss": "Stop-loss hit",
                "take_profit": "Take-profit hit",
                "market_close": "Market close",
                "manual": "Manual close",
            }
            reason_label = reason_labels.get(reason, reason)
            self._telegram.notify(
                f"{emoji} <b>Position closed</b> – <code>{symbol}</code>\n"
                f"Reason: {reason_label}\n"
                f"Exit: <b>{price:.4f}</b> | P&amp;L: <b>{pnl:+.2f}</b>"
            )
        else:
            logger.error(f"Failed to close position {symbol} – will retry next tick")

    def _close_exchange_positions(self, exchange_name: str, symbols: List[str]):
        for sym in symbols:
            pos = self._positions.get(sym)
            if pos and pos.status == PositionStatus.OPEN:
                price = self._broker.get_quote(sym) or pos.current_price
                logger.info(f"{exchange_name}: closing {sym} at market close")
                self._exit_position(sym, price, "market_close")

    # ------------------------------------------------------------------
    # End of day
    # ------------------------------------------------------------------

    def _end_of_day(self, exchange_name: str, state: ExchangeState, symbols: List[str]):
        """Called when the market closes for the day."""
        self._close_exchange_positions(exchange_name, symbols)
        state.reset_for_new_day()
        state.phase = ExchangeState.CLOSED

        # Reset ORB strategy for these symbols
        if isinstance(self._strategy, ORBStrategy):
            for sym in symbols:
                self._strategy.reset_symbol(sym)

        logger.info(f"{exchange_name}: end-of-day cleanup complete.")

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
                logger.info(f"Loaded {len(self._positions)} positions from disk")
        except Exception as exc:
            logger.warning(f"Could not load positions: {exc}")

    def _log_trade(self, action: str, position: Position):
        try:
            line = (
                f"{datetime.utcnow().isoformat()} "
                f"{action} {position.exchange} {position.symbol} "
                f"{position.side.value} qty={position.quantity} "
                f"price={position.close_price if action == 'EXIT' else position.entry_price:.4f} "
                f"pnl={position.realized_pnl:.2f}" if action == "EXIT" else ""
            )
            with open(TRADES_LOG_FILE, "a") as f:
                f.write(line + "\n")
        except Exception:
            pass
