"""
Position data model.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Optional

logger = logging.getLogger("trading_bot.position")


class PositionSide(str, Enum):
    LONG = "long"
    SHORT = "short"


class PositionStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


@dataclass
class Position:
    symbol: str
    exchange: str
    side: PositionSide
    entry_price: float
    quantity: float
    stop_loss: float
    take_profit: float

    entry_time: datetime = field(default_factory=datetime.utcnow)
    order_id: Optional[str] = None
    current_price: float = 0.0
    status: PositionStatus = PositionStatus.OPEN

    close_price: Optional[float] = None
    close_time: Optional[datetime] = None
    close_reason: Optional[str] = None  # "stop_loss" | "take_profit" | "market_close" | "manual"

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def unrealized_pnl(self) -> float:
        if self.current_price == 0:
            return 0.0
        if self.side == PositionSide.LONG:
            return (self.current_price - self.entry_price) * self.quantity
        return (self.entry_price - self.current_price) * self.quantity

    @property
    def unrealized_pnl_pct(self) -> float:
        cost = self.entry_price * self.quantity
        return (self.unrealized_pnl / cost * 100) if cost else 0.0

    @property
    def realized_pnl(self) -> Optional[float]:
        if self.close_price is None:
            return None
        if self.side == PositionSide.LONG:
            return (self.close_price - self.entry_price) * self.quantity
        return (self.entry_price - self.close_price) * self.quantity

    # ------------------------------------------------------------------
    # Trigger checks
    # ------------------------------------------------------------------

    def is_stop_loss_hit(self) -> bool:
        if self.current_price == 0:
            return False
        if self.side == PositionSide.LONG:
            return self.current_price <= self.stop_loss
        return self.current_price >= self.stop_loss

    def is_take_profit_hit(self) -> bool:
        if self.current_price == 0:
            return False
        if self.side == PositionSide.LONG:
            return self.current_price >= self.take_profit
        return self.current_price <= self.take_profit

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self, price: float, reason: str):
        self.close_price = price
        self.close_time = datetime.utcnow()
        self.close_reason = reason
        self.status = PositionStatus.CLOSED
        logger.info(
            f"Position closed: {self.symbol} {self.side.value} "
            f"entry={self.entry_price:.4f} close={price:.4f} "
            f"pnl={self.realized_pnl:.2f} reason={reason}"
        )

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "exchange": self.exchange,
            "side": self.side.value,
            "entry_price": self.entry_price,
            "quantity": self.quantity,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "entry_time": self.entry_time.isoformat(),
            "order_id": self.order_id,
            "current_price": self.current_price,
            "status": self.status.value,
            "close_price": self.close_price,
            "close_time": self.close_time.isoformat() if self.close_time else None,
            "close_reason": self.close_reason,
            "unrealized_pnl": round(self.unrealized_pnl, 4),
            "unrealized_pnl_pct": round(self.unrealized_pnl_pct, 2),
            "realized_pnl": round(self.realized_pnl, 4) if self.realized_pnl is not None else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Position":
        return cls(
            symbol=data["symbol"],
            exchange=data["exchange"],
            side=PositionSide(data["side"]),
            entry_price=data["entry_price"],
            quantity=data["quantity"],
            stop_loss=data["stop_loss"],
            take_profit=data["take_profit"],
            entry_time=datetime.fromisoformat(data["entry_time"]),
            order_id=data.get("order_id"),
            current_price=data.get("current_price", 0.0),
            status=PositionStatus(data["status"]),
            close_price=data.get("close_price"),
            close_time=datetime.fromisoformat(data["close_time"]) if data.get("close_time") else None,
            close_reason=data.get("close_reason"),
        )
