import os
import time
import csv
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any
import yaml

from .data_coingecko import CoinGeckoClient, compute_atr_from_ohlc, compute_tr_from_prices
from .exchange import ExchangeWrapper
from .strategy_atr import ATRStrategy, ATRConfig
from .risk import RiskManager, RiskConfig
from .state import load_state, save_state, BotState
from .utils import setup_logging, log_kv, now_ms, ensure_dirs

logger = logging.getLogger(__name__)

@dataclass
class Config:
    exchange_id: str
    order_type: str
    limit_slippage_bps: int
    allow_derivatives: bool
    symbol: str
    coin_id: str
    vs_currency: str
    poll_interval_seconds: int
    atr_window: int
    ohlc_days: int
    cg_timeout: int
    k: float
    stop_loss_atr: float
    stop_enabled: bool
    taker_fee_pct: float
    state_file: str
    sizing_mode: str
    notional: float
    quantity: float
    round_to_step: bool
    max_trades_per_day: int
    cooldown_seconds: int
    max_daily_loss_pct: float
    start_equity: float
    paper: bool
    once: bool
    log_level: str
    min_order_notional_warn: bool
    min_order_amount_warn: bool

def load_config(path: str) -> Config:
    with open(path, "r") as f:
        cfg = yaml.safe_load(f)
    return Config(
        exchange_id = cfg["exchange"]["id"],
        order_type = cfg["exchange"]["order_type"],
        limit_slippage_bps = int(cfg["exchange"].get("limit_slippage_bps", 10)),
        allow_derivatives = bool(cfg["exchange"].get("allow_derivatives", False)),
        symbol = cfg["market"]["symbol"],
        coin_id = cfg["coingecko"]["coin_id"],
        vs_currency = cfg["coingecko"]["vs_currency"],
        poll_interval_seconds = int(cfg["coingecko"]["poll_interval_seconds"]),
        atr_window = int(cfg["coingecko"]["atr_window"]),
        ohlc_days = int(cfg["coingecko"].get("ohlc_days", 30)),
        cg_timeout = int(cfg["coingecko"].get("timeout_seconds", 15)),
        k = float(cfg["strategy"]["k"]),
        stop_loss_atr = float(cfg["strategy"]["stop_loss_atr"]),
        stop_enabled = bool(cfg["strategy"]["stop_enabled"]),
        taker_fee_pct = float(cfg["strategy"]["taker_fee_pct"]),
        state_file = cfg["strategy"]["state_file"],
        sizing_mode = cfg["sizing"]["mode"],
        notional = float(cfg["sizing"]["notional"]),
        quantity = float(cfg["sizing"]["quantity"]),
        round_to_step = bool(cfg["sizing"]["round_to_step"]),
        max_trades_per_day = int(cfg["risk"]["max_trades_per_day"]),
        cooldown_seconds = int(cfg["risk"]["cooldown_seconds"]),
        max_daily_loss_pct = float(cfg["risk"]["max_daily_loss_pct"]),
        start_equity = float(cfg["risk"]["start_equity"]),
        paper = bool(cfg["runtime"]["paper"]),
        once = bool(cfg["runtime"]["once"]),
        log_level = cfg["runtime"]["log_level"],
        min_order_notional_warn = bool(cfg["market"].get("min_order_notional_warn", True)),
        min_order_amount_warn = bool(cfg["market"].get("min_order_amount_warn", True)),
    )

def write_equity(csv_path: str, ts: int, realized_pnl: float, cum_fees: float, position_qty: float):
    exists = os.path.exists(csv_path)
    with open(csv_path, "a", newline="") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["ts_ms","realized_pnl","cum_fees","position_qty"])
        w.writerow([ts, realized_pnl, cum_fees, position_qty])

def run_bot(config_path: str, override_paper: Optional[bool] = None, once: bool = False):
    cfg = load_config(config_path)
    if override_paper is not None:
        cfg.paper = override_paper
    if once:
        cfg.once = True

    setup_logging(cfg.log_level)
    ensure_dirs()

    # State
    st = load_state(cfg.state_file)
    if st.equity_start_of_day == 0.0 and st.realized_pnl != 0.0:
        st.equity_start_of_day = st.realized_pnl
    save_state(cfg.state_file, st)

    # Exchange + data feed
    ex = ExchangeWrapper(cfg.exchange_id, paper=cfg.paper, allow_derivatives=cfg.allow_derivatives)
    ok, reason = ex.validate_symbol(cfg.symbol)
    if not ok:
        logger.error(reason)
        return

    # Build data client
    data = CoinGeckoClient(cfg.coin_id, cfg.vs_currency, timeout=cfg.cg_timeout)

    # Strategy & Risk
    strat = ATRStrategy(ATRConfig(k=cfg.k, stop_enabled=cfg.stop_enabled, stop_loss_atr=cfg.stop_loss_atr))
    riskm = RiskManager(RiskConfig(max_trades_per_day=cfg.max_trades_per_day,
                                   cooldown_seconds=cfg.cooldown_seconds,
                                   max_daily_loss_pct=cfg.max_daily_loss_pct,
                                   start_equity=cfg.start_equity,
                                   taker_fee_pct=cfg.taker_fee_pct))

    log_kv(logger, "bot_start", exchange=cfg.exchange_id, symbol=cfg.symbol, paper=cfg.paper, k=cfg.k, atr_window=cfg.atr_window)

    while True:
        loop_start = now_ms()
        try:
            # Fetch latest price
            last_price = data.get_last_price()

            # Compute ATR (try OHLC, fallback to prices->TR)
            atr = None
            try:
                ohlc = data.get_ohlc_daily(cfg.ohlc_days)
                atr = compute_atr_from_ohlc(ohlc, cfg.atr_window)
            except Exception as e:
                logger.warning("OHLC unavailable, falling back to market_chart TR: %s", e)
                # NOTE: your data client may have different names; keep your working variant here.
                prices = data.get_market_chart(days=1)  # your existing code path
                atr = compute_tr_from_prices(prices, cfg.atr_window)

            if atr is None:
                logger.warning("ATR not available yet; skipping tick")
                if cfg.once: break
                time.sleep(max(0, cfg.poll_interval_seconds - (now_ms()-loop_start)/1000.0))
                continue

            # Generate signal
            sig, maybe_stop = strat.signal(last_price, atr, st.mode, st.ref_price)
            log_kv(logger, "tick", price=last_price, atr=atr, mode=st.mode, ref_price=st.ref_price, sig=sig)

            # Risk checks
            can, why = riskm.can_trade(loop_start, st.trades_today, st.last_trade_ts, st.realized_pnl_today)
            if not can:
                log_kv(logger, "risk_block", reason=why)
                sig = None  # veto

            # Place order if signal
            if sig in ("BUY","SELL"):
                side = sig

                # --- SIZING & MIN CHECKS (Coinbase market-buy fix) ---
                is_coinbase = (getattr(ex.exchange, 'id', '') == 'coinbase')
                is_market = (cfg.order_type.lower() == "market")
                is_market_buy = (is_market and side == "BUY")

                # Compute amount and estimated cost (quote)
                skip_round_amount = False
                if cfg.sizing_mode == "notional":
                    if is_coinbase and is_market_buy:
                        # For Coinbase market BUY, amount is interpreted as QUOTE COST (USDC)
                        amount = float(cfg.notional)
                        est_cost = amount
                        skip_round_amount = True  # do NOT round quote cost using base step
                    else:
                        # Normal path: amount is BASE quantity
                        amount = float(cfg.notional) / float(last_price)
                        est_cost = amount * float(last_price)
                else:
                    # sizing_mode == "quantity" -> amount is BASE quantity
                    amount = float(cfg.quantity)
                    est_cost = amount * float(last_price)

                # Round BASE quantity only (never round when amount is quote cost)
                if cfg.round_to_step and not skip_round_amount:
                    amount = ex.round_amount(cfg.symbol, amount)
                    est_cost = amount * float(last_price)

                # Validate minimums
                limits = ex.get_symbol_limits(cfg.symbol)
                min_amount = (limits.get("amount") or {}).get("min") or 0.0
                min_cost = (limits.get("cost") or {}).get("min") or 0.0

                ok_min = True
                # Skip amount-min check if this is Coinbase market BUY (amount is quote cost)
                if cfg.min_order_amount_warn and (not (is_coinbase and is_market_buy)) and amount < min_amount:
                    logger.warning("Amount below min: amount=%s < min=%s; skipping order", amount, min_amount)
                    ok_min = False
                if cfg.min_order_notional_warn and min_cost and est_cost < min_cost:
                    logger.warning("Notional below min: notional=%s < min_cost=%s; skipping order", est_cost, min_cost)
                    ok_min = False

                if ok_min and amount > 0:
                    price_for_limit = None
                    if cfg.order_type == "limit":
                        bps = cfg.limit_slippage_bps / 10000.0
                        if side == "BUY":
                            # your original behavior (bid below last)
                            price_for_limit = ex.round_price(cfg.symbol, last_price * (1 - bps))
                        else:
                            price_for_limit = ex.round_price(cfg.symbol, last_price * (1 + bps))

                    # Execute
                    order = ex.place_order(cfg.symbol, side, cfg.order_type, amount, price=price_for_limit)

                    # Conservative fill price assumption for accounting:
                    fill_price = last_price if cfg.order_type == "market" else (price_for_limit or last_price)

                    # Update state
                    if side == "BUY":
                        # Determine base quantity added:
                        if is_coinbase and is_market_buy and cfg.sizing_mode == "notional":
                            # amount is QUOTE cost; estimate base qty from fill_price
                            base_qty = float(amount) / float(fill_price) if float(fill_price) > 0 else 0.0
                        else:
                            base_qty = float(amount)

                        st.mode = "LONG"
                        st.ref_price = float(fill_price)
                        st.position_qty += base_qty

                        # Fees applied on notional of the executed trade
                        buy_value = base_qty * float(fill_price)
                        fee = riskm.apply_fees(buy_value)
                        st.cum_fees += fee

                        st.last_trade_ts = loop_start
                        st.trades_today += 1
                        log_kv(logger, "filled_buy", price=fill_price, amount=base_qty, fees=fee, paper=cfg.paper)

                    else:
                        # SELL entire position (simple one-position model)
                        qty_to_sell = st.position_qty if st.position_qty > 0 else float(amount)
                        if cfg.round_to_step:
                            qty_to_sell = ex.round_amount(cfg.symbol, qty_to_sell)
                        proceeds = qty_to_sell * float(fill_price)
                        cost = qty_to_sell * float(st.ref_price or fill_price)

                        # Fees: keep your current approach
                        fee = riskm.apply_fees(proceeds) + riskm.apply_fees(cost)
                        pnl = proceeds - cost - fee

                        st.realized_pnl += pnl
                        st.realized_pnl_today += pnl
                        st.cum_fees += fee
                        st.mode = "FLAT"
                        st.ref_price = float(fill_price)
                        st.position_qty = 0.0
                        st.last_trade_ts = loop_start
                        st.trades_today += 1
                        write_equity("reports/equity.csv", loop_start, st.realized_pnl, st.cum_fees, st.position_qty)
                        log_kv(logger, "filled_sell", price=fill_price, pnl=pnl, realized_pnl=st.realized_pnl, fees=fee, paper=cfg.paper)

                    save_state(cfg.state_file, st)
                else:
                    logger.info("Order not placed due to validation or zero amount (amount=%s, notional=%s)", amount, est_cost)

            if cfg.once:
                break

            # Sleep until next poll
            elapsed = (now_ms() - loop_start) / 1000.0
            to_sleep = max(0, cfg.poll_interval_seconds - elapsed)
            time.sleep(to_sleep)

        except KeyboardInterrupt:
            logger.info("Received SIGINT; shutting down gracefully.")
            break
        except Exception as e:
            logger.exception("Loop error: %s", e)
            time.sleep(min(30, cfg.poll_interval_seconds))

    # Print daily PnL summary
    logger.info("Daily summary: realized_pnl_today=%.4f realized_pnl_total=%.4f trades_today=%d fees=%.4f",
                st.realized_pnl_today, st.realized_pnl, st.trades_today, st.cum_fees)
