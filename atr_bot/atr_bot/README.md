# ATR Crypto Bot (CoinGecko + ccxt)

A minimal-but-solid ATR(14) breakout bot that polls **CoinGecko** for prices/ohlc and places **real spot orders** via **ccxt** (Binance/Kraken/Coinbase Advanced/etc.).
Runs locally (you can add a VPS later). Paper mode by default.

> ⚠️ Start with **paper trading** and **tiny sizes**. This bot is educational; use at your own risk.

---

## Features

- **Data feed**: CoinGecko simple price + OHLC (falls back to minute TR). Built-in retry with exponential backoff.
- **Strategy**: ATR breakout with state machine (FLAT/LONG), optional stop-loss at `1.0 × ATR`.
- **Trading**: ccxt live orders (market/limit), symbol validation, min order checks, fee-aware PnL.
- **Risk**: trade cooldown, daily trade cap, daily loss % kill-switch.
- **Sizing**: fixed notional **or** fixed quantity; step-size rounding.
- **Ops**: structured logging, rotating log file, persistent `state.json`, equity curve `reports/equity.csv`.
- **CLI**: `--paper`, `--config`, `--once`.

---

## Install

```bash
# 1) Create and activate a venv (recommended)
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2) Install dependencies
pip install -r requirements.txt
```

---

## Configure

1) Copy `.env.example` to `.env` and put your exchange API credentials:

```
API_KEY=your_key
API_SECRET=your_secret
API_PASSWORD=optional_passphrase
COINGECKO_API_KEY=optional_key
```

2) Edit `config.yaml`:

- **Choose exchange**: `exchange.id` (e.g., `binance`, `kraken`, `coinbase`).
- **Symbol**: `market.symbol` (spot only unless you set `allow_derivatives: true`).
  - Tip: Different exchanges may have different symbols (e.g., Kraken uses `XBT/USDT`).
- **K / ATR window**: `strategy.k`, `coingecko.atr_window`.
- **Order type**: `exchange.order_type` (`market` or `limit`), with `limit_slippage_bps` for limit anchoring.
- **Sizing**: set `sizing.mode` to `notional` or `quantity`. Adjust `notional` or `quantity` accordingly.
- **Risk**: `max_trades_per_day`, `cooldown_seconds`, `max_daily_loss_pct`, `start_equity`.

Defaults:
```yaml
market.symbol: BTC/USDT
coingecko.atr_window: 14
strategy.k: 1.5
strategy.stop_enabled: true
coingecko.poll_interval_seconds: 10
```

> If you use an exchange that **doesn't list BTC/USDT spot**, change to a valid symbol (e.g., Coinbase: `BTC/USDC`). Also set `coingecko.coin_id` and `vs_currency` to match (e.g., `bitcoin` + `usdc`).

---

## Run

Paper (default in config):
```bash
python main.py --config config.yaml --paper
```

Live (be careful!):
```bash
python main.py --config config.yaml --live
```

One-shot test (fetch once then exit):
```bash
python main.py --once
```

Logs:
- Console + `logs/bot.log` (rotating).

Reports:
- `reports/equity.csv` updates on each **SELL** (realized PnL point).

State:
- `state.json` persists between runs.

---

## How it trades (quick)

- **Entry** (when `mode=FLAT`): if `price ≤ ref_price - k*ATR` → **BUY**.  
  `ref_price` is `last fill price` (or current price if none yet).  
- **Exit** (when `mode=LONG`): if `price ≥ ref_price + k*ATR` → **SELL**.  
- **Stop-loss** (optional): if enabled and `price ≤ entry - 1.0*ATR` → **SELL**.
- After any fill: `ref_price := fill_price`.

PnL accounts for taker fees (default `0.1%` per side).

---

## Change k, ATR window, and position sizing

- **k**: `strategy.k` in `config.yaml`.
- **ATR window**: `coingecko.atr_window` in `config.yaml`.
- **Position sizing**:
  - Switch mode in `sizing.mode`: `notional` or `quantity`.
  - Then set `sizing.notional` (e.g., `200`) or `sizing.quantity` (e.g., `0.005`).

No code changes required—config only.

---

## Notes & Safety

- Spot only by default. To allow swaps/futures, set `exchange.allow_derivatives: true`.
- If the chosen amount/notional is below the exchange **minimums**, the bot **warns and skips** the order.
- Transient exchange errors are retried by ccxt internally; fatal auth errors will halt placement (you'll see errors).
- This is a **single-position** LONG-only example for clarity. Extend as needed.

Good luck, and trade tiny first. 🚀
