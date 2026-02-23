"""
Risk management for crypto trading:
- Position sizing in USDT
- Stop-loss / take-profit calculation
- Daily loss limit enforcement
"""

import logging
import math
from typing import Optional

from trading.config import CryptoTradingConfig

logger = logging.getLogger("crypto_bot.risk")


class RiskManager:
    def __init__(self, config: CryptoTradingConfig):
        self._max_position_usdt = config.max_position_value_usdt
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
        """Call once at start of each UTC day."""
        self._initial_portfolio_value = value
        self._daily_realized_pnl = 0.0
        self._trading_halted = False
        logger.info(f"New day started. Portfolio value: {value:.2f} USDT")

    def record_realized_pnl(self, pnl: float):
        self._daily_realized_pnl += pnl
        logger.info(
            f"Realized P&L: {pnl:+.4f} USDT  |  Daily total: {self._daily_realized_pnl:+.4f} USDT"
        )

    def reset_daily(self):
        self._initial_portfolio_value = None
        self._daily_realized_pnl = 0.0
        self._trading_halted = False
        logger.info("Daily risk counters reset.")

    # ------------------------------------------------------------------
    # Safety checks
    # ------------------------------------------------------------------

    def should_halt_trading(self, current_portfolio_value: float) -> bool:
        if self._trading_halted:
            return True
        if self._initial_portfolio_value is None or self._initial_portfolio_value == 0:
            return False

        loss_pct = (self._initial_portfolio_value - current_portfolio_value) / self._initial_portfolio_value
        if loss_pct >= self._max_daily_loss_pct:
            logger.warning(
                f"Daily loss limit reached: {loss_pct:.2%} >= {self._max_daily_loss_pct:.2%}. "
                "Halting new entries."
            )
            self._trading_halted = True
            return True
        return False

    # ------------------------------------------------------------------
    # Position sizing
    # ------------------------------------------------------------------

    def calculate_quantity(self, price: float, step_size: float) -> float:
        """
        Calculate quantity of base asset to buy.

        Quantity = floor(max_position_usdt / price) rounded to Binance stepSize.
        Returns 0 if insufficient funds or price is invalid.
        """
        if price <= 0 or step_size <= 0:
            return 0.0

        raw_qty = self._max_position_usdt / price

        # Round down to nearest stepSize
        precision = max(0, -int(math.floor(math.log10(step_size))))
        qty = math.floor(raw_qty / step_size) * step_size
        qty = round(qty, precision)

        return qty

    # ------------------------------------------------------------------
    # SL / TP calculation
    # ------------------------------------------------------------------

    def stop_loss_price(self, entry_price: float) -> float:
        return round(entry_price * (1.0 - self._stop_loss_pct), 8)

    def take_profit_price(self, entry_price: float) -> float:
        return round(entry_price * (1.0 + self._take_profit_pct), 8)
