\
import logging
import time
from dataclasses import dataclass
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

@dataclass
class RiskConfig:
    max_trades_per_day: int = 10
    cooldown_seconds: int = 60
    max_daily_loss_pct: float = 3.0
    start_equity: float = 1000.0
    taker_fee_pct: float = 0.1 # per side, percent

class RiskManager:
    def __init__(self, cfg: RiskConfig):
        self.cfg = cfg

    def can_trade(self, now_ms: int, trades_today: int, last_trade_ts: Optional[int], realized_pnl_today: float) -> Tuple[bool, str]:
        if trades_today >= self.cfg.max_trades_per_day:
            return False, "max_trades_per_day reached"
        if last_trade_ts is not None and (now_ms - last_trade_ts) < self.cfg.cooldown_seconds * 1000:
            return False, "in cooldown"
        if self.cfg.max_daily_loss_pct > 0 and realized_pnl_today <= -abs(self.cfg.max_daily_loss_pct/100.0 * self.cfg.start_equity):
            return False, "max_daily_loss_pct kill-switch triggered"
        return True, ""

    def apply_fees(self, notional: float) -> float:
        # taker fee each side: reduce PnL by fee * notional
        fee = abs(notional) * (self.cfg.taker_fee_pct / 100.0)
        return fee
