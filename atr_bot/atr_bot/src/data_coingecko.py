# src/data_coingecko.py
import os
import logging
from typing import Optional, Dict, Any, List, Tuple

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

# Treat common stablecoin quotes as USD for CoinGecko endpoints that don't support 'usdc' directly
STABLECOIN_TO_USD = {"usdc", "usdt", "busd", "tusd", "usdd", "dai"}


def _normalize_vs_currency(v: str) -> str:
    if not v:
        return "usd"
    v = v.lower().strip()
    return "usd" if v in STABLECOIN_TO_USD else v


class CoinGeckoClient:
    """
    Thin client around CoinGecko with:
      - public vs. pro API base selection
      - retry/backoff
      - robust last-price fallbacks
      - daily OHLC for ATR, with minute-bar TR fallback
    """

    def __init__(self, coin_id: str, vs_currency: str, timeout: int = 15):
        self.coin_id = (coin_id or "").strip()
        self.vs_currency = _normalize_vs_currency(vs_currency)
        self.timeout = timeout

        # If a Pro key is present, use the Pro base (and auth header). Otherwise, use the public base.
        self.api_key = os.getenv("COINGECKO_API_KEY") or None
        self.base = (
            "https://pro-api.coingecko.com/api/v3"
            if self.api_key
            else "https://api.coingecko.com/api/v3"
        )

    # -------------------------- internal --------------------------

    def _headers(self) -> Dict[str, str]:
        h = {"Accept": "application/json"}
        if self.api_key:
            # CoinGecko Pro header
            h["x-cg-pro-api-key"] = self.api_key
        return h

    def _get(self, path: str, params: Dict[str, Any]) -> requests.Response:
        url = f"{self.base}{path}"
        return requests.get(url, params=params, headers=self._headers(), timeout=self.timeout)

    # -------------------------- public ---------------------------

    @retry(
        reraise=True,
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        retry=retry_if_exception_type(requests.RequestException),
    )
    def get_last_price(self) -> float:
        """
        Return the latest price for self.coin_id in self.vs_currency.
        Fallback order:
          1) /simple/price
          2) /coins/markets
          3) /coins/{id} (market_data.current_price)
        Raises HTTPError if all fail (tenacity handles retry/backoff).
        """
        # 1) simple/price
        r = self._get("/simple/price", {"ids": self.coin_id, "vs_currencies": self.vs_currency})
        if r.ok:
            j = r.json()
            if self.coin_id in j and self.vs_currency in j[self.coin_id]:
                return float(j[self.coin_id][self.vs_currency])
            logger.warning(
                "coingecko_simple_price_missing_data id=%s vs=%s body=%s",
                self.coin_id,
                self.vs_currency,
                j,
            )
        else:
            logger.warning(
                "coingecko_simple_price_status code=%s body=%s", r.status_code, r.text
            )

        # 2) coins/markets
        r = self._get(
            "/coins/markets",
            {"vs_currency": self.vs_currency, "ids": self.coin_id, "per_page": 1, "page": 1},
        )
        if r.ok:
            arr = r.json()
            if isinstance(arr, list) and arr:
                price = arr[0].get("current_price")
                if price is not None:
                    logger.info("coingecko_price_fallback used=coins/markets")
                    return float(price)
            logger.warning(
                "coingecko_markets_empty id=%s vs=%s body=%s",
                self.coin_id,
                self.vs_currency,
                arr,
            )
        else:
            logger.warning("coingecko_markets_status code=%s body=%s", r.status_code, r.text)

        # 3) coins/{id} (market_data.current_price)
        r = self._get(
            f"/coins/{self.coin_id}",
            {
                "localization": "false",
                "tickers": "false",
                "market_data": "true",
                "community_data": "false",
                "developer_data": "false",
                "sparkline": "false",
            },
        )
        if r.ok:
            j = r.json()
            md = (j.get("market_data") or {}).get("current_price") or {}
            price = md.get(self.vs_currency)
            if price is not None:
                logger.info("coingecko_price_fallback used=coins/{id}")
                return float(price)
            logger.warning(
                "coingecko_coins_id_missing_price id=%s vs=%s", self.coin_id, self.vs_currency
            )

        # If all three failed, raise for tenacity to retry
        r.raise_for_status()
        assert False, "unreachable"

    @retry(
        reraise=True,
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        retry=retry_if_exception_type(requests.RequestException),
    )
    def get_ohlc_daily(self, days: int = 30) -> Optional[List[List[float]]]:
        """
        Try daily OHLC for self.coin_id in self.vs_currency.
        Returns list of [timestamp(ms), open, high, low, close] or raises HTTPError.
        Not all assets/periods are supported by CG; caller can fallback to TR from minute bars.
        """
        r = self._get(f"/coins/{self.coin_id}/ohlc", {"vs_currency": self.vs_currency, "days": days})
        if r.ok:
            return r.json()
        r.raise_for_status()
        return None  # for type checkers

    @retry(
        reraise=True,
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        retry=retry_if_exception_type(requests.RequestException),
    )
    def get_market_chart_minutes(self, days: int = 1) -> List[Tuple[int, float]]:
        """
        Pull minute-resolution 'prices' for up to the last N days.
        Returns a list of (timestamp_ms, price).
        """
        params = {"vs_currency": self.vs_currency, "days": days, "interval": "minute"}
        r = self._get(f"/coins/{self.coin_id}/market_chart", params)
        if not r.ok:
            logger.warning("coingecko_market_chart_status code=%s body=%s", r.status_code, r.text)
            r.raise_for_status()
        j = r.json()
        prices = j.get("prices") or []
        out: List[Tuple[int, float]] = []
        for row in prices:
            # API returns [[ms, price], ...]
            try:
                ts, p = int(row[0]), float(row[1])
                out.append((ts, p))
            except Exception:
                continue
        if not out:
            logger.warning("coingecko_market_chart_empty id=%s vs=%s", self.coin_id, self.vs_currency)
        return out

    def get_tr_from_market_chart(self, days: int = 1) -> List[float]:
        """
        Fallback TR from minute bars when daily OHLC is unavailable.
        TR approximation for minute data uses |p_t - p_{t-1}|.
        Returns a list of TR values (len = n-1).
        """
        series = self.get_market_chart_minutes(days=days)
        if len(series) < 2:
            return []
        trs: List[float] = []
        prev_p = series[0][1]
        for _, p in series[1:]:
            trs.append(abs(p - prev_p))
            prev_p = p
        return trs


# -------------------------- helpers used by runner.py --------------------------

def compute_atr_from_ohlc(ohlc: List[List[float]], window: int) -> Optional[float]:
    """
    Compute ATR from CoinGecko OHLC data (rows: [ms, open, high, low, close]).
    Uses Wilder-style TR (max of H-L, |H-prevClose|, |L-prevClose|) and
    returns a simple moving average of the last `window` TRs.
    """
    if not ohlc or len(ohlc) < 2:
        return None

    trs: List[float] = []
    prev_close = float(ohlc[0][4])
    for i in range(1, len(ohlc)):
        _, _o, h, l, c = ohlc[i]
        h = float(h); l = float(l); c = float(c)
        tr = max(h - l, abs(h - prev_close), abs(l - prev_close))
        trs.append(tr)
        prev_close = c

    if not trs:
        return None

    n = max(1, min(window, len(trs)))
    return sum(trs[-n:]) / n


def compute_tr_from_prices(prices: List[Tuple[int, float]]) -> List[float]:
    """
    Given a list of (timestamp_ms, price), return TR approximations as |p_t - p_{t-1}|.
    """
    if not prices or len(prices) < 2:
        return []
    trs: List[float] = []
    prev_p = float(prices[0][1])
    for _, p in prices[1:]:
        p = float(p)
        trs.append(abs(p - prev_p))
        prev_p = p
    return trs
