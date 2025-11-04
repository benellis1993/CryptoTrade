# src/exchange.py
import os
import logging
from typing import Optional, Dict, Any, Tuple

from dotenv import load_dotenv
import ccxt

logger = logging.getLogger(__name__)


class ExchangeWrapper:
    def __init__(self, exchange_id: str, paper: bool = True, allow_derivatives: bool = False):
        # Load environment variables from .env
        load_dotenv()
        self.exchange_id = exchange_id
        self.paper = paper
        self.allow_derivatives = allow_derivatives
        self.exchange = self._create_exchange(exchange_id)
        # Load markets (some exchanges require auth even in paper mode)
        self.exchange.load_markets()
        # Coinbase requires special handling for market BUY (amount as cost)
        if getattr(self.exchange, 'id', '') == 'coinbase':
            # Allow sending quote cost as the 'amount' for market buys
            self.exchange.options['createMarketBuyOrderRequiresPrice'] = False

    # ---------------- Internal helpers ----------------

    @staticmethod
    def _normalize_coinbase_secret(secret: str) -> str:
        """
        Coinbase Advanced Trade ECDSA secrets are PEMs. Users often paste them as a single
        line with literal '\n' sequences or with accidental quotes/braces from JSON.
        This converts '\\n' -> '\n', strips wrapping quotes/braces, and ensures trailing newline.
        """
        if not secret:
            return secret

        s = secret.strip()

        # Strip accidental surrounding quotes
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            s = s[1:-1].strip()

        # If someone pasted a JSON object tail with a '}' at the end, attempt to trim it off
        if s.endswith("}"):
            end_marker = "-----END EC PRIVATE KEY-----"
            end_idx = s.find(end_marker)
            if end_idx != -1:
                s = s[: end_idx + len(end_marker)]

        # Replace literal backslash-n with real newlines (common when storing in .env)
        if "\\n" in s:
            s = s.replace("\\n", "\n")

        # Ensure the PEM ends with a newline for parsers
        if "BEGIN EC PRIVATE KEY" in s and not s.endswith("\n"):
            s += "\n"

        return s

    def _create_exchange(self, exchange_id: str):
        klass = getattr(ccxt, exchange_id)

        apiKey = (os.getenv("API_KEY") or "").strip()
        secret = (os.getenv("API_SECRET") or "").strip()
        password = os.getenv("API_PASSWORD") or os.getenv("API_PASSPHRASE")  # used by some exchanges, ignored by coinbase

        if exchange_id.lower() == "coinbase":
            # Normalize Coinbase Advanced ECDSA PEM secrets
            secret = self._normalize_coinbase_secret(secret)

        if not apiKey or not secret:
            logger.warning("API_KEY or API_SECRET not set; live trading/auth-required endpoints may fail. Paper mode recommended.")

        # Base params for all exchanges
        params: Dict[str, Any] = {
            "apiKey": apiKey,
            "secret": secret,
            "password": password,
            "enableRateLimit": True,
            "timeout": 20000,
            "options": {},
        }

        # Coinbase Advanced: explicitly set ECDSA
        if exchange_id.lower() == "coinbase":
            params["options"]["signatureAlgorithm"] = "ecdsa"

        ex = klass(params)
        return ex

    # ---------------- Public API ----------------

    def validate_symbol(self, symbol: str) -> Tuple[bool, str]:
        markets = self.exchange.markets
        if symbol not in markets:
            sample = list(self.exchange.symbols)[:5]
            return False, f"Symbol {symbol} not found on {self.exchange_id}. Examples: {sample}"
        market = markets[symbol]
        # Block non-spot unless explicitly allowed
        if (market.get("type") in ("swap", "future", "margin") or market.get("spot") is False) and not self.allow_derivatives:
            return False, f"Symbol {symbol} is not spot (type={market.get('type')}); set allow_derivatives=true to proceed."
        return True, ""

    def get_symbol_limits(self, symbol: str) -> Dict[str, Any]:
        market = self.exchange.market(symbol)
        return market.get("limits", {}) or {}

    def price_precision(self, symbol: str) -> Optional[int]:
        market = self.exchange.market(symbol)
        return (market.get("precision") or {}).get("price")

    def amount_precision(self, symbol: str) -> Optional[int]:
        market = self.exchange.market(symbol)
        return (market.get("precision") or {}).get("amount")

    def round_amount(self, symbol: str, amount: float) -> float:
        try:
            return float(self.exchange.amount_to_precision(symbol, amount))
        except Exception:
            return amount

    def round_price(self, symbol: str, price: float) -> float:
        try:
            return float(self.exchange.price_to_precision(symbol, price))
        except Exception:
            return price

    def check_minimums(self, symbol: str, amount: float, cost: float) -> Tuple[bool, str]:
        limits = self.get_symbol_limits(symbol)
        min_amount = (limits.get("amount") or {}).get("min") or 0.0
        min_cost = (limits.get("cost") or {}).get("min") or 0.0
        if amount < min_amount:
            return False, f"Order amount {amount} < min {min_amount}"
        if min_cost and cost < min_cost:
            return False, f"Order notional {cost} < min {min_cost}"
        return True, ""

    def place_order(self, symbol: str, side: str, order_type: str, amount: float, price: float = None):
        """
        Places an order. For Coinbase market BUY on spot, automatically uses 'amount' as QUOTE COST.
        """
        side_l = side.lower()
        type_l = order_type.lower()

        try:
            if type_l == "market":
                # Standard path for most exchanges
                if side_l == "buy":
                    # For Coinbase: our __init__ already set the option so 'amount' is interpreted as quote cost.
                    params = {}
                    if getattr(self.exchange, 'id', '') == 'coinbase':
                        params['createMarketBuyOrderRequiresPrice'] = False
                    return self.exchange.create_order(symbol, "market", "buy", amount, None, params)
                else:
                    return self.exchange.create_order(symbol, "market", "sell", amount)
            else:
                # limit
                if price is None:
                    raise ValueError("Limit order requires price")
                return self.exchange.create_order(symbol, "limit", side_l, amount, price)

        except Exception as e:
            # Fallback: if Coinbase still complains for market buy, convert base 'amount' to cost using last price
            msg = str(e)
            is_coinbase = getattr(self.exchange, 'id', '') == 'coinbase'
            need_cost = (
                is_coinbase and
                type_l == "market" and
                side_l == "buy" and
                "createOrder() requires a price argument for market buy orders" in msg
            )
            if need_cost:
                # Estimate quote cost from ticker; close/last/ask as available
                tkr = self.exchange.fetch_ticker(symbol) or {}
                px = tkr.get("last") or tkr.get("close") or tkr.get("ask") or tkr.get("bid")
                if not px:
                    raise
                cost = float(amount) * float(px)   # ≈ your notional
                params = {'createMarketBuyOrderRequiresPrice': False}
                # pass 'cost' as the amount for Coinbase market BUY
                return self.exchange.create_order(symbol, "market", "buy", cost, None, params)
            raise


    def fetch_balance(self):
        if self.paper:
            return {}
        return self.exchange.fetch_balance()
