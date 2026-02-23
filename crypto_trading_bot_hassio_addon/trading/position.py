"""
Position data model for crypto trading.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

logger = logging.getLogger("crypto_bot.position")


class PositionSide(str, Enum):
    LONG = "long"


class PositionStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


@dataclass
class Position:
    symbol: str
    side: PositionSide
    entry_price: float
    quantity: float          # in base asset (e.g. BTC for BTCUSDT)
    stop_loss: float
    take_profit: float

    entry_time: datetime = field(default_factory=datetime.utcnow)
    order_id: Optional[str] = None
    oco_order_list_id: Optional[str] = None  # Binance OCO list ID for SL+TP orders
    current_price: float = 0.0
    status: PositionStatus = PositionStatus.OPEN

    close_price: Optional[float] = None
    close_time: Optional[datetime] = None
    close_reason: Optional[str] = None  # "stop_loss" | "take_profit" | "manual"

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def cost_usdt(self) -> float:
        return self.entry_price * self.quantity

    @property
    def unrealized_pnl(self) -> float:
        if self.current_price == 0:
            return 0.0
        return (self.current_price - self.entry_price) * self.quantity

    @property
    def unrealized_pnl_pct(self) -> float:
        cost = self.cost_usdt
        return (self.unrealized_pnl / cost * 100) if cost else 0.0

    @property
    def realized_pnl(self) -> Optional[float]:
        if self.close_price is None:
            return None
        return (self.close_price - self.entry_price) * self.quantity

    # ------------------------------------------------------------------
    # Trigger checks (used for local monitoring fallback)
    # ------------------------------------------------------------------

    def is_stop_loss_hit(self) -> bool:
        if self.current_price == 0:
            return False
        return self.current_price <= self.stop_loss

    def is_take_profit_hit(self) -> bool:
        if self.current_price == 0:
            return False
        return self.current_price >= self.take_profit

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self, price: float, reason: str):
        self.close_price = price
        self.close_time = datetime.utcnow()
        self.close_reason = reason
        self.status = PositionStatus.CLOSED
        logger.info(
            f"Position closed: {self.symbol} LONG "
            f"entry={self.entry_price:.6f} close={price:.6f} "
            f"pnl={self.realized_pnl:.4f} USDT reason={reason}"
        )

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side.value,
            "entry_price": self.entry_price,
            "quantity": self.quantity,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "entry_time": self.entry_time.isoformat(),
            "order_id": self.order_id,
            "oco_order_list_id": self.oco_order_list_id,
            "current_price": self.current_price,
            "status": self.status.value,
            "close_price": self.close_price,
            "close_time": self.close_time.isoformat() if self.close_time else None,
            "close_reason": self.close_reason,
            "unrealized_pnl": round(self.unrealized_pnl, 6),
            "unrealized_pnl_pct": round(self.unrealized_pnl_pct, 4),
            "realized_pnl": round(self.realized_pnl, 6) if self.realized_pnl is not None else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Position":
        return cls(
            symbol=data["symbol"],
            side=PositionSide(data["side"]),
            entry_price=data["entry_price"],
            quantity=data["quantity"],
            stop_loss=data["stop_loss"],
            take_profit=data["take_profit"],
            entry_time=datetime.fromisoformat(data["entry_time"]),
            order_id=data.get("order_id"),
            oco_order_list_id=data.get("oco_order_list_id"),
            current_price=data.get("current_price", 0.0),
            status=PositionStatus(data["status"]),
            close_price=data.get("close_price"),
            close_time=datetime.fromisoformat(data["close_time"]) if data.get("close_time") else None,
            close_reason=data.get("close_reason"),
        )
