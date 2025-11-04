🪙 CryptoTrade — Automated Trend-Based Crypto Trading Bot
Overview

CryptoTrade is an automated cryptocurrency trading application that identifies market trends using real-time data from the CoinGecko API and executes buy/sell orders through the Coinbase API.
It’s designed to analyze volatility and trend strength using the Average True Range (ATR) formula — a widely respected technical analysis tool for gauging market momentum and risk.

⚙️ Features

📊 Live Market Data — Retrieves up-to-date cryptocurrency prices and trend data from CoinGecko.

🤖 Automated Trading Logic — Places trades through Coinbase based on configurable ATR-based signals.

🧮 ATR Volatility Strategy — Uses the Average True Range to detect strong market movements and avoid false signals.

💾 Configurable Parameters — Easily adjust symbol pairs, risk thresholds, and ATR multipliers.

🧠 Trend Recognition — Determines bullish or bearish conditions through recent price action and volatility.

🔐 Secure API Integration — Safely connects to your Coinbase account using environment-stored credentials.

📈 How It Works

Fetch Data — The bot continuously polls CoinGecko for live price and volume data.

Calculate ATR — It calculates the Average True Range over a moving period to determine volatility.

Identify Trend — When the price moves beyond an ATR-defined threshold, it flags a potential trade opportunity.

Execute Trade — Orders are sent to Coinbase via API, following a risk-managed buy or sell logic.

Monitor & Adjust — The bot updates dynamically as new data arrives, adjusting its thresholds automatically.

🧰 Tech Stack

Language: Python 3.x

APIs:

CoinGecko API
 — Market and trend data

Coinbase API
 — Trade execution

Libraries:

ccxt or coinbase for trading integration

requests or aiohttp for data fetching

pandas or numpy for ATR calculation

dotenv for secure API key management

🚀 Setup Instructions
1. Clone the Repository
git clone https://github.com/benellis1993/CryptoTrade.git
cd CryptoTrade

2. Create a Virtual Environment
python -m venv venv
venv\Scripts\activate   # On Windows
source venv/bin/activate  # On macOS/Linux

3. Install Dependencies
pip install -r requirements.txt

4. Add API Keys

Create a .env file in the root directory:

COINGECKO_API_KEY=your_api_key_here
COINBASE_API_KEY=your_api_key_here
COINBASE_API_SECRET=your_api_secret_here

5. Run the Bot
python main.py

⚖️ Disclaimer

This bot is for educational and research purposes only.
Cryptocurrency trading involves significant risk. Use at your own discretion and always test thoroughly before using real funds.

📬 Contact

Created by Benjamin Ellis
GitHub: @benellis1993
