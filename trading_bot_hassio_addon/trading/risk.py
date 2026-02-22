"""
Risk management: position sizing, stop-loss / take-profit calculation,
daily loss limit enforcement.
"""

import logging
from typing import Optional

from trading.config import TradingConfig
from trading.position import PositionSide

logger = logging.getLogger("trading_bot.risk")


class RiskManager:
    def __init__(self, config: TradingConfig):
        self._max_position_value = config.max_position_value
        self._stop_loss_pct = config.stop_loss_pct / 100.0
        self._take_profit_pct = config.take_profit_pct / 100.0
        self._max_daily_loss_pct = config.max_daily_loss_pct / 100.0

        self._initial_portfolio_value: Optional[float] = None
        self._daily_realized_pnl: float = 0.0
        self._trading_halted: bool = False

    # ------------------------------------------------------------------
    # Daily book-keeping
    # ------------------------------------------------------------------

    def set_initial_portfolio_value(self, value: float):
        """Call once at the start of each trading day."""
        self._initial_portfolio_value = value
        self._daily_realized_pnl = 0.0
        self._trading_halted = False
        logger.info(f"Day started. Initial portfolio value: {value:.2f}")

    def record_realized_pnl(self, pnl: float):
        self._daily_realized_pnl += pnl
        logger.info(
            f"Realized PnL: {pnl:+.2f}  |  Daily total: {self._daily_realized_pnl:+.2f}"
        )

    def reset_daily(self):
        """Reset counters at end of day."""
        self._initial_portfolio_value = None
        self._daily_realized_pnl = 0.0
        self._trading_halted = False
        logger.info("Daily risk counters reset.")

    # ------------------------------------------------------------------
    # Safety checks
    # ------------------------------------------------------------------

    def should_halt_trading(self, current_portfolio_value: float) -> bool:
        """Return True if the daily loss limit has been breached."""
        if self._trading_halted:
            return True
        if self._initial_portfolio_value is None or self._initial_portfolio_value == 0:
            return False

        loss_pct = (self._initial_portfolio_value - current_portfolio_value) / self._initial_portfolio_value
        if loss_pct >= self._max_daily_loss_pct:
            logger.warning(
                f"Daily loss limit reached: {loss_pct:.2%} >= {self._max_daily_loss_pct:.2%}. "
                "Halting new entries for today."
            )
            self._trading_halted = True
            return True
        return False

    # ------------------------------------------------------------------
    # Position sizing
    # ------------------------------------------------------------------

    def calculate_quantity(self, price: float) -> int:
        """
        Calculate integer number of units to buy/sell based on
        max_position_value and current price.

        For XTB CFD stock positions, volume is expressed in lots where
        1 lot = 1 share (for most stock CFDs). Returns at least 1 if
        price <= max_position_value.
        """
        if price <= 0:
            return 0
        qty = int(self._max_position_value / price)
        return max(qty, 0)

    # ------------------------------------------------------------------
    # Stop loss / take profit calculation
    # ------------------------------------------------------------------

    def stop_loss_price(self, entry_price: float, side: PositionSide) -> float:
        if side == PositionSide.LONG:
            return round(entry_price * (1.0 - self._stop_loss_pct), 4)
        return round(entry_price * (1.0 + self._stop_loss_pct), 4)

    def take_profit_price(self, entry_price: float, side: PositionSide) -> float:
        if side == PositionSide.LONG:
            return round(entry_price * (1.0 + self._take_profit_pct), 4)
        return round(entry_price * (1.0 - self._take_profit_pct), 4)

    def orb_stop_loss_price(
        self, side: PositionSide, orb_high: float, orb_low: float
    ) -> float:
        """
        For ORB strategy, stop loss is placed at the opposite boundary
        of the opening range, with a small buffer (0.1%).
        """
        buffer = 0.001
        if side == PositionSide.LONG:
            return round(orb_low * (1.0 - buffer), 4)
        return round(orb_high * (1.0 + buffer), 4)
