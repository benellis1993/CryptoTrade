\
import argparse
from src.runner import run_bot

def main():
    ap = argparse.ArgumentParser(description="ATR-based crypto bot (CoinGecko + ccxt)")
    ap.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    ap.add_argument("--paper", action="store_true", help="Run in paper mode regardless of config")
    ap.add_argument("--live", action="store_true", help="Force live trading mode (overrides config paper=true)")
    ap.add_argument("--once", action="store_true", help="Run one iteration then exit")
    args = ap.parse_args()

    override_paper = None
    if args.paper:
        override_paper = True
    elif args.live:
        override_paper = False

    run_bot(args.config, override_paper=override_paper, once=args.once)

if __name__ == "__main__":
    main()
