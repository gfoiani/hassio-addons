"""Main bot class for the Bet Sniper Bot.

Lifecycle::

    bot = BetSniperBot(config)
    bot.run()          # blocks; calls shutdown() on SIGINT/SIGTERM

The main loop:
1. Authenticate with Betfair.
2. Every ``check_interval`` seconds:
   a. Fetch account balance.
   b. Compute today's spend from the DB.
   c. Fetch upcoming events for configured leagues.
   d. For each event not yet bet on:
      - Fetch MATCH_ODDS market and runner prices.
      - Apply the strategy to select an outcome within [min_odds, max_odds].
      - Check risk constraints (daily cap, reserve).
      - Place a BACK bet (or log in paper-trading mode).
3. Poll Telegram commands (/status, /stats, /halt, /resume).
4. Try to settle pending bets via listClearedOrders.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from betting.bet_db import BetDatabase
from betting.broker import BetfairBroker, BetEvent, MarketOdds
from betting.config import BetSniperConfig
from betting.risk import RiskManager
from betting.strategy import BetStrategy, Selection
from betting.telegram_notifier import TelegramNotifier

logger = logging.getLogger("bet_sniper.bot")

STORAGE_DIR = Path("/data")
BETS_DB_FILE = STORAGE_DIR / "bets.db"
BETS_LOG_FILE = STORAGE_DIR / "bets.log"


class BetSniperBot:
    """Autonomous Betfair football betting bot."""

    def __init__(self, config: BetSniperConfig) -> None:
        self._config = config
        self._broker = BetfairBroker(
            username=config.username,
            password=config.password,
            app_key=config.app_key,
        )
        self._strategy = BetStrategy()
        self._risk = RiskManager()
        self._telegram = TelegramNotifier(
            relay_url=config.telegram_relay_url,
            api_key=config.telegram_api_key,
        )

        self._halt = False
        self._running = False

        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        self._bet_db = BetDatabase(BETS_DB_FILE)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the main loop. Blocks until shutdown() is called."""
        self._running = True
        logger.info("Bet Sniper Bot starting …")

        self._telegram.start_keepalive()

        if not self._config.paper_trading:
            if not self._broker.connect():
                logger.error("Cannot connect to Betfair. Exiting.")
                return
        else:
            logger.info("PAPER TRADING mode – no real bets will be placed.")

        mode_label = "PAPER" if self._config.paper_trading else "LIVE"
        self._telegram.notify(
            f"🎯 <b>Bet Sniper Bot started</b> [{mode_label}]\n"
            f"Leagues: {', '.join(self._config.leagues)}\n"
            f"Odds range: {self._config.min_odds:.2f}–{self._config.max_odds:.2f}\n"
            f"Stake: {self._config.stake_per_bet:.2f} | "
            f"Daily cap: {self._config.max_daily_loss_pct:.0f}% | "
            f"Reserve: {self._config.reserve_pct:.0f}%"
        )

        while self._running:
            try:
                if not self._halt:
                    self._run_cycle()
                    self._settle_pending_bets()
                self._process_telegram_commands()
            except Exception as exc:
                logger.error("Unexpected error in main loop: %s", exc, exc_info=True)

            logger.debug("Sleeping for %d seconds …", self._config.check_interval)
            time.sleep(self._config.check_interval)

    def shutdown(self) -> None:
        """Signal the main loop to stop gracefully."""
        logger.info("Shutting down Bet Sniper Bot …")
        self._running = False

    # ------------------------------------------------------------------
    # Core cycle
    # ------------------------------------------------------------------

    def _run_cycle(self) -> None:
        """Scan events and place qualifying bets for this cycle."""
        logger.info("=== Starting bet scan cycle ===")

        balance = self._broker.get_balance() if not self._config.paper_trading else 0.0
        today_spend = self._bet_db.get_today_spend()

        logger.info(
            "Balance: %.2f | Today spend: %.2f | Daily cap: %.2f%%",
            balance, today_spend, self._config.max_daily_loss_pct,
        )

        events = self._broker.get_upcoming_events(
            self._config.leagues,
            self._config.lookahead_hours,
        ) if not self._config.paper_trading else self._get_paper_events()

        if not events:
            logger.info("No upcoming events found for configured leagues.")
            return

        bets_this_cycle = 0
        for event in events:
            if not self._running or self._halt:
                break

            if self._bet_db.already_bet(event.id):
                logger.debug("Already bet on event %s (%s), skipping.", event.id, event.name)
                continue

            if not self._is_in_snipe_window(event):
                continue

            market = self._broker.get_match_odds(event.id) if not self._config.paper_trading else None

            selection = None
            if market is not None:
                selection = self._strategy.select_outcome(
                    market.runners,
                    self._config.min_odds,
                    self._config.max_odds,
                )
            elif self._config.paper_trading:
                # In paper mode create a dummy selection for logging purposes
                selection = Selection(runner_id=0, name="Home (paper)", odds=self._config.min_odds)
                market_id = f"paper-{event.id}"
            else:
                logger.debug("No MATCH_ODDS market for %s", event.name)
                continue

            if selection is None:
                logger.debug(
                    "No qualifying selection for %s (odds range %.2f–%.2f)",
                    event.name, self._config.min_odds, self._config.max_odds,
                )
                continue

            if not self._config.paper_trading:
                if not self._risk.can_place_bet(
                    balance=balance,
                    today_spend=today_spend,
                    stake=self._config.stake_per_bet,
                    max_daily_loss_pct=self._config.max_daily_loss_pct,
                    reserve_pct=self._config.reserve_pct,
                ):
                    logger.info("Daily budget limit reached – stopping cycle.")
                    self._telegram.notify(
                        "⚠️ <b>Daily budget limit reached.</b> No more bets until tomorrow."
                    )
                    break

            market_id_final = market.market_id if market else f"paper-{event.id}"
            self._place_or_paper_bet(event, market_id_final, selection)
            today_spend += self._config.stake_per_bet
            bets_this_cycle += 1

        logger.info("Cycle complete. Bets placed this cycle: %d", bets_this_cycle)

    def _place_or_paper_bet(
        self,
        event: BetEvent,
        market_id: str,
        selection: Selection,
    ) -> None:
        """Place a real bet or log a paper bet."""
        stake = self._config.stake_per_bet

        if self._config.paper_trading:
            logger.info(
                "[PAPER] Would bet %.2f on %s – %s @ %.2f",
                stake, event.name, selection.name, selection.odds,
            )
            self._bet_db.record_bet(
                event_id=event.id,
                event_name=event.name,
                competition=event.competition,
                market_id=market_id,
                selection_id=selection.runner_id,
                selection_name=selection.name,
                odds=selection.odds,
                stake=stake,
                paper_trade=True,
            )
            self._log_bet(event, selection, stake, paper=True)
            return

        placed = self._broker.place_back_bet(
            market_id=market_id,
            selection_id=selection.runner_id,
            odds=selection.odds,
            stake=stake,
        )

        if placed is None:
            logger.error("Bet placement failed for %s – %s", event.name, selection.name)
            return

        self._bet_db.record_bet(
            event_id=event.id,
            event_name=event.name,
            competition=event.competition,
            market_id=market_id,
            selection_id=selection.runner_id,
            selection_name=selection.name,
            odds=selection.odds,
            stake=stake,
            paper_trade=False,
        )
        self._log_bet(event, selection, stake, paper=False)
        self._telegram.notify(
            f"✅ <b>Bet placed</b>\n"
            f"Match: <b>{event.name}</b>\n"
            f"Competition: {event.competition}\n"
            f"Selection: <b>{selection.name}</b> @ {selection.odds:.2f}\n"
            f"Stake: {stake:.2f} | Bet ID: <code>{placed.bet_id}</code>"
        )

    # ------------------------------------------------------------------
    # Settlement
    # ------------------------------------------------------------------

    def _settle_pending_bets(self) -> None:
        """Check Betfair for settled outcomes of pending bets."""
        if self._config.paper_trading:
            return

        pending = self._bet_db.get_pending_bets()
        if not pending:
            return

        bet_ids = [str(row["id"]) for row in pending]

        # We need the actual Betfair bet IDs, which are stored as selection_id
        # in our DB.  Use listClearedOrders by market_id grouping instead.
        market_ids_to_db: Dict[str, dict] = {row["market_id"]: row for row in pending}

        settled = self._broker.get_settled_bets(bet_ids)
        for s in settled:
            db_row = market_ids_to_db.get(s.market_id)
            if db_row is None:
                continue
            self._bet_db.settle_bet(
                bet_id=db_row["id"],
                result=s.result,
                profit_loss=s.profit_loss,
            )
            icon = "✅" if s.result == "WON" else ("↩️" if s.result == "VOID" else "❌")
            self._telegram.notify(
                f"{icon} <b>Bet settled</b>: {db_row['event_name']} – "
                f"{db_row['selection_name']} → <b>{s.result}</b> "
                f"(P&amp;L: {s.profit_loss:+.2f})"
            )

    # ------------------------------------------------------------------
    # Telegram command handling
    # ------------------------------------------------------------------

    def _process_telegram_commands(self) -> None:
        commands = self._telegram.poll_commands()
        for cmd in commands:
            command = cmd.get("command", "").lower().lstrip("/")
            args = cmd.get("args", "").strip()
            chat_id = cmd.get("chat_id")
            try:
                if command == "status":
                    self._cmd_status(chat_id)
                elif command == "halt":
                    self._halt = True
                    self._telegram.send_result(chat_id, "🛑 <b>Betting halted.</b>")
                elif command == "resume":
                    self._halt = False
                    self._telegram.send_result(chat_id, "✅ <b>Betting resumed.</b>")
                elif command == "stats":
                    self._cmd_stats(chat_id)
                else:
                    self._telegram.send_result(
                        chat_id,
                        f"❓ Unknown command: <code>/{command}</code>\n\n"
                        f"Available: /status /halt /resume /stats",
                    )
            except Exception as exc:
                logger.error("Error processing /%s: %s", command, exc)
                self._telegram.send_result(chat_id, f"❌ Error: {exc}")

    def _cmd_status(self, chat_id: int) -> None:
        balance = self._broker.get_balance() if not self._config.paper_trading else 0.0
        today_spend = self._bet_db.get_today_spend()
        pending = self._bet_db.get_pending_bets()
        mode = "PAPER" if self._config.paper_trading else "LIVE"

        lines = [
            f"🎯 <b>Bet Sniper Status</b> [{mode}]",
            "",
            f"Balance: <b>{balance:.2f}</b>",
            f"Today spend: {today_spend:.2f}",
            f"Daily cap: {self._config.max_daily_loss_pct:.0f}% "
            f"({balance * self._config.max_daily_loss_pct / 100:.2f} max)",
            f"Reserve: {self._config.reserve_pct:.0f}% "
            f"({balance * self._config.reserve_pct / 100:.2f} locked)",
            f"Pending bets: {len(pending)}",
            f"Bot status: {'🛑 HALTED' if self._halt else '✅ Running'}",
        ]
        self._telegram.send_result(chat_id, "\n".join(lines))

    def _cmd_stats(self, chat_id: int) -> None:
        s = self._bet_db.get_stats()
        if not s:
            self._telegram.send_result(chat_id, "❌ Could not retrieve statistics.")
            return

        total = s["total_settled"]
        if total == 0:
            self._telegram.send_result(
                chat_id,
                "📊 <b>Bet Sniper Statistics</b>\n\nNo settled bets yet.",
            )
            return

        wins = s["wins"]
        losses = total - wins
        comp_lines = [
            f"   • {comp}: {d['count']} bets ({d['pnl']:+.2f})"
            for comp, d in s["by_competition"].items()
        ]

        lines = [
            "📊 <b>Bet Sniper Statistics</b>\n",
            f"<b>All-time</b> ({total} settled bets)",
            f"  Won/Lost: {wins}W – {losses}L | Win rate: <b>{s['win_rate']:.1f}%</b>",
            f"  Total P&amp;L: <b>{s['total_pnl']:+.2f}</b>",
            f"  Avg P&amp;L: {s['avg_pnl']:+.2f}",
            f"  Best: {s['best_pnl']:+.2f} | Worst: {s['worst_pnl']:+.2f}",
        ]
        if comp_lines:
            lines.append("\n<b>By competition:</b>")
            lines.extend(comp_lines)
        lines.append(
            f"\n<b>Yesterday:</b> {s['yesterday_bets']} bets | "
            f"P&amp;L {s['yesterday_pnl']:+.2f}"
        )
        lines.append(
            f"<b>Last 7 days:</b> {s['week_bets']} bets | "
            f"P&amp;L {s['week_pnl']:+.2f}"
        )
        if s["open_count"]:
            lines.append(f"\n📂 Pending bets: {s['open_count']}")
        if s["paper_count"]:
            lines.append(f"📝 Paper bets (all-time): {s['paper_count']}")

        self._telegram.send_result(chat_id, "\n".join(lines))

    # ------------------------------------------------------------------
    # Snipe window
    # ------------------------------------------------------------------

    def _is_in_snipe_window(self, event: BetEvent) -> bool:
        """Return True only if kick-off falls inside the configured snipe window.

        The window is defined by two config parameters:
        - ``bet_window_hours``: maximum hours before kick-off to place the bet.
        - ``min_time_to_ko_minutes``: minimum minutes before kick-off (avoids
          betting when the market is already very tight or partially in-play).

        Events too far in the future are *monitored* but not bet on yet.
        Events that are about to kick off (< min_time_to_ko_minutes) are skipped
        to avoid last-second surprises (line-up changes, suspensions, etc.).
        """
        now = datetime.now(timezone.utc)
        kick_off = event.kick_off
        if kick_off.tzinfo is None:
            kick_off = kick_off.replace(tzinfo=timezone.utc)

        time_to_ko_secs = (kick_off - now).total_seconds()
        min_secs = self._config.min_time_to_ko_minutes * 60
        max_secs = self._config.bet_window_hours * 3600

        in_window = min_secs <= time_to_ko_secs <= max_secs

        if not in_window:
            if time_to_ko_secs > max_secs:
                logger.debug(
                    "Too early to bet on '%s' (KO in %.1fh, window opens at %.1fh).",
                    event.name,
                    time_to_ko_secs / 3600,
                    self._config.bet_window_hours,
                )
            else:
                logger.debug(
                    "Too late to bet on '%s' (KO in %.0fmin, min is %dmin).",
                    event.name,
                    time_to_ko_secs / 60,
                    self._config.min_time_to_ko_minutes,
                )

        return in_window

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log_bet(
        self,
        event: BetEvent,
        selection: Selection,
        stake: float,
        paper: bool,
    ) -> None:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        tag = "PAPER" if paper else "REAL "
        line = (
            f"{now} UTC | {tag} | {event.name:<35} | {event.competition:<25} | "
            f"{selection.name:<10} @ {selection.odds:.2f} | stake={stake:.2f}"
        )
        try:
            with open(BETS_LOG_FILE, "a") as f:
                f.write(line + "\n")
        except Exception as exc:
            logger.warning("Could not write bet log: %s", exc)

    # ------------------------------------------------------------------
    # Paper trading helpers
    # ------------------------------------------------------------------

    def _get_paper_events(self) -> List[BetEvent]:
        """Return a small set of dummy events for paper-trading mode.

        Kick-off times are spaced inside the snipe window so that
        ``_is_in_snipe_window`` passes without needing real Betfair data.
        """
        now = datetime.now(timezone.utc)
        # Place dummy kick-offs at the midpoint of the snipe window.
        # e.g. bet_window_hours=2, min_time_to_ko=30 → midpoint ≈ 75 min from now.
        min_secs = self._config.min_time_to_ko_minutes * 60
        max_secs = int(self._config.bet_window_hours * 3600)
        midpoint_secs = (min_secs + max_secs) // 2
        return [
            BetEvent(
                id=f"paper-event-{i}",
                name=f"Paper Match {i}",
                competition="Paper League",
                kick_off=now + timedelta(seconds=midpoint_secs + i * 300),
            )
            for i in range(1, 4)
        ]
