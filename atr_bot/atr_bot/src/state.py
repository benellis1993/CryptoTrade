\
import json
import logging
from dataclasses import dataclass, asdict, field
from typing import Optional
from datetime import datetime, timezone
from .utils import atomic_write_json

logger = logging.getLogger(__name__)

@dataclass
class BotState:
    mode: str = "FLAT"          # FLAT or LONG
    ref_price: Optional[float] = None
    position_qty: float = 0.0
    realized_pnl: float = 0.0
    cum_fees: float = 0.0
    trades_today: int = 0
    last_trade_ts: Optional[int] = None
    equity_start_of_day: float = 0.0
    realized_pnl_today: float = 0.0
    day_key: str = ""           # YYYY-MM-DD

def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def load_state(path: str) -> BotState:
    try:
        with open(path, "r") as f:
            data = json.load(f)
        st = BotState(**data)
        # rollover day
        if st.day_key != _today_key():
            st.trades_today = 0
            st.realized_pnl_today = 0.0
            st.equity_start_of_day = st.realized_pnl
            st.day_key = _today_key()
        return st
    except FileNotFoundError:
        st = BotState(day_key=_today_key())
        return st

def save_state(path: str, st: BotState):
    atomic_write_json(path, asdict(st))
