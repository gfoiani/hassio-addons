"""Betting strategy for the Bet Sniper Bot.

Ported and adapted from the TypeScript ``BetStrategy`` class in
``betsniper/src/engine/recommendation.ts``.

Strategy
--------
For each football event with a MATCH_ODDS market (1X2):

1. Inspect all three runners (Home, Draw, Away).
2. Keep only runners whose best available back price falls in
   ``[min_odds, max_odds]``.
3. From the eligible runners, pick the one with the *lowest* odds
   (= highest implied probability = most confident pick).
4. Return that single ``Selection`` (or ``None`` if none qualify).

This is a conservative, single-selection approach: one bet per event,
always picking the most likely outcome within the configured risk band.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger("bet_sniper.strategy")


@dataclass(frozen=True)
class Runner:
    """A single outcome in a MATCH_ODDS market."""

    selection_id: int
    name: str          # "Home" | "Away" | "The Draw"
    best_back_price: float   # Best available back price (0.0 = no price)


@dataclass(frozen=True)
class Selection:
    """A chosen runner to back."""

    runner_id: int
    name: str
    odds: float


class BetStrategy:
    """Selects a single outcome to back from a list of runners."""

    def select_outcome(
        self,
        runners: List[Runner],
        min_odds: float,
        max_odds: float,
    ) -> Optional[Selection]:
        """Return the best qualifying runner, or ``None`` if none qualify.

        Parameters
        ----------
        runners:
            All runners for the event (typically 3 for a 1X2 market).
        min_odds:
            Inclusive lower bound for acceptable back odds.
        max_odds:
            Inclusive upper bound for acceptable back odds.
        """
        eligible = [
            r for r in runners
            if r.best_back_price > 0
            and min_odds <= r.best_back_price <= max_odds
        ]

        if not eligible:
            return None

        # Pick the runner with the lowest (safest) odds within the range.
        chosen = min(eligible, key=lambda r: r.best_back_price)

        logger.debug(
            "Selected: %s @ %.2f  (range %.2f–%.2f, %d eligible runners)",
            chosen.name, chosen.best_back_price, min_odds, max_odds, len(eligible),
        )

        return Selection(
            runner_id=chosen.selection_id,
            name=chosen.name,
            odds=chosen.best_back_price,
        )
