"""Risk management for the Bet Sniper Bot.

Controls how much of the Betfair balance may be deployed on any given day,
protecting capital via two independent guardrails:

1. **Reserve**: a fixed percentage of the balance is always kept untouched.
2. **Daily spend cap**: the total stake placed today must not exceed
   ``max_daily_loss_pct`` of the current balance.

Example (balance = 100 €, reserve_pct = 20, max_daily_loss_pct = 10,
         stake = 5, today_spend = 0):

    reserved       = 100 * 0.20 = 20 €
    deployable     = 100 - 20 - 0 = 80 € → stake 5 ≤ 80 ✓
    max_daily      = 100 * 0.10 = 10 €   → 0 + 5 ≤ 10 ✓  → can_place = True

After 2 bets (today_spend = 10):

    deployable     = 100 - 20 - 10 = 70 € → stake 5 ≤ 70 ✓
    daily cap      = 0 + 5 > 10 ✗ → can_place = False
"""

from __future__ import annotations

import logging

logger = logging.getLogger("bet_sniper.risk")


class RiskManager:
    """Stateless risk guard: decides if a single bet may be placed."""

    def can_place_bet(
        self,
        balance: float,
        today_spend: float,
        stake: float,
        max_daily_loss_pct: float,
        reserve_pct: float,
    ) -> bool:
        """Return True if placing ``stake`` respects both risk constraints.

        Parameters
        ----------
        balance:
            Current available Betfair balance (funds that can be withdrawn).
        today_spend:
            Total stake already committed today (UTC day, real bets only).
        stake:
            The stake about to be placed.
        max_daily_loss_pct:
            Maximum percentage of ``balance`` that may be spent today.
        reserve_pct:
            Percentage of ``balance`` permanently reserved (never touched).
        """
        if balance <= 0 or stake <= 0:
            return False

        reserved = balance * (reserve_pct / 100.0)
        max_daily = balance * (max_daily_loss_pct / 100.0)
        deployable = balance - reserved - today_spend

        daily_ok = (today_spend + stake) <= max_daily
        deploy_ok = stake <= deployable

        if not daily_ok:
            logger.info(
                "Risk: daily cap reached (spend=%.2f + stake=%.2f > max=%.2f)",
                today_spend, stake, max_daily,
            )
        if not deploy_ok:
            logger.info(
                "Risk: deployable insufficient (deployable=%.2f < stake=%.2f)",
                deployable, stake,
            )

        return daily_ok and deploy_ok
