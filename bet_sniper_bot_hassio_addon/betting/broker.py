"""Betfair API wrapper for the Bet Sniper Bot.

Uses ``betfairlightweight`` (https://github.com/liampauling/betfair) with
interactive (non-certificate) login: username + password + app_key.

Key Betfair concepts
--------------------
* **Event Type ID 1** = Soccer/Football
* **Market type MATCH_ODDS** = the standard 1X2 market
* **Runner names** for 1X2: "Home" · "The Draw" · "Away"
* **BACK** side = betting FOR an outcome to occur
* **LAPSE** persistence = the order is cancelled at in-play if unmatched

League → Betfair competition name mapping
-----------------------------------------
We resolve each configured league slug (e.g. "soccer_italy_serie_a") to the
Betfair competition name used in ``listCompetitions`` / ``listEvents``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import betfairlightweight
from betfairlightweight import filters as bf_filters

from betting.strategy import Runner

logger = logging.getLogger("bet_sniper.broker")

# ---------------------------------------------------------------------------
# League slug → Betfair competition display name
# ---------------------------------------------------------------------------
LEAGUE_COMPETITIONS: Dict[str, str] = {
    "soccer_italy_serie_a": "Serie A",
    "soccer_epl": "English Premier League",
    "soccer_spain_la_liga": "Spanish La Liga",
    "soccer_germany_bundesliga": "German Bundesliga",
    "soccer_france_ligue_1": "French Ligue 1",
    "soccer_portugal_primeira_liga": "Primeira Liga",
    "soccer_uefa_champs_league": "UEFA Champions League",
    "soccer_uefa_europa_league": "UEFA Europa League",
}

FOOTBALL_EVENT_TYPE_ID = "1"


@dataclass
class BetEvent:
    """Minimal event data needed by the bot."""

    id: str
    name: str
    competition: str
    kick_off: datetime


@dataclass
class MarketOdds:
    """Current MATCH_ODDS market data for an event."""

    market_id: str
    event_id: str
    runners: List[Runner]


@dataclass
class PlacedBet:
    """Result of a successful place_back_bet call."""

    bet_id: str
    market_id: str
    selection_id: int
    odds: float
    stake: float
    status: str   # "SUCCESS" | "FAILURE"


@dataclass
class SettledBet:
    """Settlement data for a previously placed bet."""

    bet_id: str
    market_id: str
    selection_id: int
    profit_loss: float
    result: str   # "WON" | "LOST" | "VOID"


class BetfairBroker:
    """Thin wrapper around betfairlightweight.APIClient.

    All public methods log errors and return safe defaults so the bot can
    continue running even when the Betfair API is temporarily unavailable.
    """

    def __init__(self, username: str, password: str, app_key: str) -> None:
        self._username = username
        self._password = password
        self._app_key = app_key
        self._client: Optional[betfairlightweight.APIClient] = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Authenticate with Betfair. Returns True on success."""
        try:
            self._client = betfairlightweight.APIClient(
                username=self._username,
                password=self._password,
                app_key=self._app_key,
            )
            self._client.login()
            logger.info("Connected to Betfair as %s", self._username)
            return True
        except Exception as exc:
            logger.error("Betfair login failed: %s", exc)
            self._client = None
            return False

    def _ensure_connected(self) -> bool:
        """Re-authenticate if the session has expired."""
        if self._client is None:
            return self.connect()
        try:
            self._client.keep_alive()
            return True
        except Exception:
            return self.connect()

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    def get_balance(self) -> float:
        """Return available funds (wallet) or 0.0 on error."""
        if not self._ensure_connected():
            return 0.0
        try:
            funds = self._client.account.get_account_funds()
            balance = funds.available_to_bet_balance
            logger.debug("Betfair balance: %.2f", balance)
            return float(balance)
        except Exception as exc:
            logger.error("Failed to fetch account balance: %s", exc)
            return 0.0

    # ------------------------------------------------------------------
    # Market discovery
    # ------------------------------------------------------------------

    def get_upcoming_events(
        self,
        leagues: List[str],
        lookahead_hours: int,
    ) -> List[BetEvent]:
        """Return upcoming football events for the configured leagues.

        Filters by competition name derived from the league slug.
        """
        if not self._ensure_connected():
            return []

        competition_names = [
            LEAGUE_COMPETITIONS[lg]
            for lg in leagues
            if lg in LEAGUE_COMPETITIONS
        ]
        if not competition_names:
            logger.warning("No recognised leagues in config: %s", leagues)
            return []

        now = datetime.now(timezone.utc)
        end = now + timedelta(hours=lookahead_hours)

        try:
            # 1. Resolve competition IDs from names
            comp_results = self._client.betting.list_competitions(
                filter=bf_filters.market_filter(
                    event_type_ids=[FOOTBALL_EVENT_TYPE_ID],
                    market_start_time=bf_filters.time_range(
                        from_=now.isoformat(),
                        to=end.isoformat(),
                    ),
                )
            )
            comp_id_map: Dict[str, str] = {}   # name → id
            for cr in comp_results:
                if cr.competition and cr.competition.name in competition_names:
                    comp_id_map[cr.competition.name] = cr.competition.id

            if not comp_id_map:
                logger.info(
                    "No Betfair competitions found for: %s", competition_names
                )
                return []

            # 2. List events for the resolved competitions
            events_result = self._client.betting.list_events(
                filter=bf_filters.market_filter(
                    event_type_ids=[FOOTBALL_EVENT_TYPE_ID],
                    competition_ids=list(comp_id_map.values()),
                    market_start_time=bf_filters.time_range(
                        from_=now.isoformat(),
                        to=end.isoformat(),
                    ),
                )
            )

            bet_events: List[BetEvent] = []
            for er in events_result:
                ev = er.event
                if not ev:
                    continue
                comp_name = ev.competition_id or ""
                # Resolve competition display name from id
                for name, cid in comp_id_map.items():
                    if cid == ev.competition_id or cid == getattr(ev, "competition_id", None):
                        comp_name = name
                        break
                bet_events.append(BetEvent(
                    id=ev.id,
                    name=ev.name,
                    competition=comp_name,
                    kick_off=ev.open_date or now,
                ))

            logger.info(
                "Found %d upcoming events across %d competitions",
                len(bet_events), len(comp_id_map),
            )
            return bet_events

        except Exception as exc:
            logger.error("Failed to fetch upcoming events: %s", exc)
            return []

    def get_match_odds(self, event_id: str) -> Optional[MarketOdds]:
        """Return the MATCH_ODDS market for the given event, with runner prices."""
        if not self._ensure_connected():
            return None
        try:
            # 1. Find the MATCH_ODDS market for this event
            catalogue = self._client.betting.list_market_catalogue(
                filter=bf_filters.market_filter(
                    event_ids=[event_id],
                    market_type_codes=["MATCH_ODDS"],
                ),
                market_projection=["RUNNERS"],
                max_results=1,
            )
            if not catalogue:
                logger.debug("No MATCH_ODDS market found for event %s", event_id)
                return None

            market_cat = catalogue[0]
            market_id = market_cat.market_id

            # 2. Fetch live prices
            market_books = self._client.betting.list_market_book(
                market_ids=[market_id],
                price_projection=bf_filters.price_projection(
                    price_data=bf_filters.price_data("EX_BEST_OFFERS"),
                ),
            )
            if not market_books:
                return None

            book = market_books[0]

            # Map selection_id → runner name from catalogue
            id_to_name: Dict[int, str] = {}
            if market_cat.runners:
                for r in market_cat.runners:
                    id_to_name[r.selection_id] = r.runner_name

            runners: List[Runner] = []
            for runner in book.runners:
                name = id_to_name.get(runner.selection_id, str(runner.selection_id))
                best_back = 0.0
                if runner.ex and runner.ex.available_to_back:
                    best_back = float(runner.ex.available_to_back[0].price)
                runners.append(Runner(
                    selection_id=runner.selection_id,
                    name=name,
                    best_back_price=best_back,
                ))

            return MarketOdds(
                market_id=market_id,
                event_id=event_id,
                runners=runners,
            )

        except Exception as exc:
            logger.error("Failed to fetch match odds for event %s: %s", event_id, exc)
            return None

    # ------------------------------------------------------------------
    # Order placement
    # ------------------------------------------------------------------

    def place_back_bet(
        self,
        market_id: str,
        selection_id: int,
        odds: float,
        stake: float,
    ) -> Optional[PlacedBet]:
        """Place a BACK LIMIT order at the specified odds.

        Returns ``None`` if the order was rejected or an exception occurred.
        The order uses ``persistence_type='LAPSE'`` so it is cancelled at
        in-play if it remains unmatched.
        """
        if not self._ensure_connected():
            return None
        try:
            limit_order = bf_filters.limit_order(
                size=stake,
                price=odds,
                persistence_type="LAPSE",
            )
            instruction = bf_filters.place_instruction(
                selection_id=str(selection_id),
                order_type="LIMIT",
                side="BACK",
                limit_order=limit_order,
            )
            result = self._client.betting.place_orders(
                market_id=market_id,
                instructions=[instruction],
                customer_strategy_ref="bet_sniper",
            )

            if not result or not result.instruction_reports:
                logger.error("place_orders returned empty result for market %s", market_id)
                return None

            report = result.instruction_reports[0]
            if report.status != "SUCCESS":
                logger.error(
                    "Bet placement failed: status=%s, error=%s",
                    report.status,
                    getattr(report, "error_code", "unknown"),
                )
                return None

            bet_id = report.bet_id
            logger.info(
                "Bet placed: id=%s market=%s sel=%d odds=%.2f stake=%.2f",
                bet_id, market_id, selection_id, odds, stake,
            )
            return PlacedBet(
                bet_id=bet_id,
                market_id=market_id,
                selection_id=selection_id,
                odds=odds,
                stake=stake,
                status="SUCCESS",
            )

        except Exception as exc:
            logger.error(
                "Exception placing bet on market %s sel %d: %s",
                market_id, selection_id, exc,
            )
            return None

    # ------------------------------------------------------------------
    # Settlement
    # ------------------------------------------------------------------

    def get_settled_bets(self, bet_ids: List[str]) -> List[SettledBet]:
        """Fetch settlement data for a list of bet IDs.

        Uses ``listClearedOrders`` with ``SETTLED`` status.
        Returns an empty list on error.
        """
        if not self._ensure_connected() or not bet_ids:
            return []
        try:
            cleared = self._client.betting.list_cleared_orders(
                bet_status="SETTLED",
                bet_ids=bet_ids,
            )
            settled: List[SettledBet] = []
            for order in (cleared.orders or []):
                profit = float(order.profit)
                result = "WON" if profit > 0 else ("VOID" if profit == 0 else "LOST")
                settled.append(SettledBet(
                    bet_id=order.bet_id,
                    market_id=order.market_id,
                    selection_id=order.selection_id,
                    profit_loss=profit,
                    result=result,
                ))
            return settled
        except Exception as exc:
            logger.error("Failed to fetch settled bets: %s", exc)
            return []
