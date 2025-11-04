# seed_refprice.py  (creates a clean state.json anchored to current price)
import json
from pathlib import Path

import requests
import yaml

CFG = yaml.safe_load(Path("config.yaml").read_text())
coin_id = CFG["coingecko"]["coin_id"]
vs = CFG["coingecko"]["vs_currency"].lower()

# Map common stablecoins to 'usd' for CoinGecko
if vs in {"usdc", "usdt", "busd", "tusd", "usdd", "dai"}:
    vs = "usd"

def cg_price(coin_id: str, vs: str) -> float:
    # Try simple/price first
    u = "https://api.coingecko.com/api/v3/simple/price"
    r = requests.get(u, params={"ids": coin_id, "vs_currencies": vs}, timeout=15)
    if r.ok:
        j = r.json()
        if coin_id in j and vs in j[coin_id]:
            return float(j[coin_id][vs])
    # Fallback: coins/markets
    u2 = "https://api.coingecko.com/api/v3/coins/markets"
    r = requests.get(u2, params={"vs_currency": vs, "ids": coin_id, "per_page": 1}, timeout=15)
    r.raise_for_status()
    arr = r.json()
    if not arr:
        raise RuntimeError("No markets returned from CoinGecko")
    return float(arr[0]["current_price"])

px = cg_price(coin_id, vs)

state = {
    "mode": "FLAT",
    "ref_price": px,
    "position_qty": 0.0,
    "realized_pnl_today": 0.0,
    "last_trade_ts": 0
}
Path("state.json").write_text(json.dumps(state, indent=2))
print(f"Seeded state.json with ref_price={px} ({coin_id}/{vs})")
