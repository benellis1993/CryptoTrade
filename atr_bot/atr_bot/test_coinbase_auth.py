# test_coinbase_auth.py
import os, ccxt
from dotenv import load_dotenv

# Load .env from the current folder
load_dotenv()

api_key = os.getenv("API_KEY")
secret  = os.getenv("API_SECRET")
pwd     = os.getenv("API_PASSWORD")

print("Have API_KEY? ", bool(api_key), " len:", len(api_key) if api_key else 0)
print("Have API_SECRET?", bool(secret), " len:", len(secret) if secret else 0)
print("Have API_PASSWORD?", bool(pwd))

ex = ccxt.coinbase({
    "apiKey": api_key,
    "secret": secret,
    "enableRateLimit": True,
})

try:
    mkts = ex.fetch_markets()
    print("OK: fetched", len(mkts), "markets")   # success path
except Exception as e:
    print("ERROR:", type(e).__name__, e)         # print one line; don't dump secrets
