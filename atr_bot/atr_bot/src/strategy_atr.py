\
import logging
from dataclasses import dataclass
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

@dataclass
class ATRConfig:
    k: float = 1.5
    stop_enabled: bool = True
    stop_loss_atr: float = 1.0

class ATRStrategy:
    def __init__(self, cfg: ATRConfig):
        self.cfg = cfg

    def signal(self, price: float, atr: Optional[float], mode: str, ref_price: Optional[float]) -> Tuple[Optional[str], Optional[float]]:
        """Return (signal, stop_price). signal in {'BUY','SELL',None}"""
        if atr is None or atr <= 0:
            return None, None

        if mode == "FLAT":
            trigger = (ref_price if ref_price is not None else price) - self.cfg.k * atr
            if price <= trigger:
                stop_price = price - self.cfg.stop_loss_atr * atr if self.cfg.stop_enabled else None
                return "BUY", stop_price
            return None, None

        elif mode == "LONG":
            trigger = (ref_price if ref_price is not None else price) + self.cfg.k * atr
            if price >= trigger:
                return "SELL", None
            # Stop-loss check
            if self.cfg.stop_enabled and ref_price is not None and price <= (ref_price - self.cfg.stop_loss_atr * atr):
                logger.info("Stop-loss trigger reached")
                return "SELL", None
            return None, None

        return None, None
