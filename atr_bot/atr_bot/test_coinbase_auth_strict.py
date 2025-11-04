import os, sys, ccxt
from dotenv import load_dotenv

# Optional: validate the PEM loads with cryptography (already in your venv)
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.backends import default_backend

load_dotenv()

api_key = (os.getenv("API_KEY") or "").strip()
secret  = (os.getenv("API_SECRET") or "")

# 1) Strip accidental quotes/braces copied from JSON
s = secret.strip()
if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
    s = s[1:-1].strip()
if s.endswith("}"):
    end_marker = "-----END EC PRIVATE KEY-----"
    end_idx = s.find(end_marker)
    if end_idx != -1:
        s = s[: end_idx + len(end_marker)]

# 2) Turn literal "\n" into real newlines, normalize line endings, ensure trailing newline
if "\\n" in s:
    s = s.replace("\\n", "\n")
s = s.replace("\r\n", "\n")
if "BEGIN EC PRIVATE KEY" in s and not s.endswith("\n"):
    s += "\n"

# Quick visibility without leaking the key:
print("api_key prefix:", api_key[:24], "...  startswith 'organizations/'?", api_key.startswith("organizations/"))
print("secret has BEGIN/END?", ("BEGIN EC PRIVATE KEY" in s, "END EC PRIVATE KEY" in s))
print("secret length (chars):", len(s))

# 3) Verify PEM parses (good early warning if not)
try:
    _ = load_pem_private_key(s.encode(), password=None, backend=default_backend())
    print("PEM parse: OK")
except Exception as e:
    print("PEM parse: ERROR ->", type(e).__name__, e)
    sys.exit(1)

# 4) Try ccxt with explicit ECDSA
ex = ccxt.coinbase({
    "apiKey": api_key,
    "secret": s,
    "enableRateLimit": True,
    "options": {"signatureAlgorithm": "ecdsa"},
})

try:
    mkts = ex.fetch_markets()
    print("OK: fetched", len(mkts), "markets")
except Exception as e:
    print("ERROR:", type(e).__name__, e)
