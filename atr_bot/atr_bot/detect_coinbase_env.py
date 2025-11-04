import os, ccxt
from dotenv import load_dotenv

load_dotenv()

creds = {"apiKey": os.getenv("API_KEY"), "secret": os.getenv("API_SECRET"), "enableRateLimit": True}

def try_env(sandbox: bool):
    ex = ccxt.coinbase(creds)
    ex.set_sandbox_mode(sandbox)
    which = "SANDBOX" if sandbox else "PRODUCTION"
    try:
        ex.fetch_markets()
        print(f"OK in {which}: fetched markets ✅")
    except Exception as e:
        print(f"ERROR in {which}: {type(e).__name__}: {e}")

try_env(False)  # production
try_env(True)   # sandbox
