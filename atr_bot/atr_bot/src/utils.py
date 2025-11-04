\
import json
import os
import time
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict

def ensure_dirs():
    Path("logs").mkdir(parents=True, exist_ok=True)
    Path("reports").mkdir(parents=True, exist_ok=True)

def setup_logging(level: str = "INFO"):
    ensure_dirs()
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    fmt = logging.Formatter(
        fmt="ts=%(asctime)s level=%(levelname)s module=%(name)s msg=%(message)s"
    )
    # Console
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    # Rotating file
    fh = RotatingFileHandler("logs/bot.log", maxBytes=2_000_000, backupCount=3)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

def log_kv(logger: logging.Logger, msg: str, **kwargs):
    kv = " ".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k,v in kwargs.items())
    logger.info(f"{msg} {kv}".strip())

def atomic_write_json(path: str, data: Dict[str, Any]):
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)

def now_ms() -> int:
    return int(time.time() * 1000)

def clamp(n: float, minn: float, maxn: float) -> float:
    return max(min(maxn, n), minn)
