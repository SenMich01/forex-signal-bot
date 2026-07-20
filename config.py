"""
Configuration module for Forex Signal Bot.

Contains all settings, pairs to monitor, and trading parameters.
"""

import os
from datetime import datetime, time

# Forex pairs to monitor (Yahoo Finance suffixes)
FOREX_PAIRS = [
    "USDJPY=X",
    "EURUSD=X",
    "GBPUSD=X",
    "XAUUSD=X",  # Gold
    "USDCAD=X",
    "EURJPY=X",
    "GBPJPY=X"
]

# User-facing pair names
PAIR_NAMES = {
    "USDJPY=X": "USD/JPY",
    "EURUSD=X": "EUR/USD",
    "GBPUSD=X": "GBP/USD",
    "XAUUSD=X": "XAU/USD (Gold)",
    "USDCAD=X": "USD/CAD",
    "EURJPY=X": "EUR/JPY",
    "GBPJPY=X": "GBP/JPY"
}

# Trading session hours (UTC)
TRADING_SESSIONS = [
    {"start": time(7, 0),  "end": time(16, 0)},  # London
    {"start": time(13, 0), "end": time(21, 0)}  # New York
]

# Indicator parameters
EMA_PERIODS = {
    "EMA8": 8,
    "EMA21": 21,
    "EMA50": 50
}

RSI_PERIOD = 14
ATR_PERIOD = 14
ADX_PERIOD = 14
ADX_THRESHOLD = 22  # minimum ADX to consider the market "trending" enough to trade a pullback

# Signal parameters
ATR_MULTIPLIERS = {
    "SL": 1.0,        # Stop-loss distance from entry
    "TP": 1.5,        # Take-profit for SELL trades
    "TP_BUY": 2.0,    # Take-profit for BUY trades
    "ENTRY": 0.5      # Pullback buffer around EMA21
}

# Risk management
MAX_RISK_PERCENT = 1.0  # Maximum risk per trade (% of account)
MIN_RISK_REWARD = 1.0   # Minimum risk-to-reward ratio

# Timing settings
SCAN_INTERVAL_MINUTES = 5
DUPLICATE_SIGNAL_COOLDOWN_MINUTES = 15

# Data settings
DATA_CONFIG = {
    "M5": {
        "interval": "5m",
        "period": "5d",
        "candles_required": 100
    },
    "H1": {
        "interval": "1h",
        "period": "30d",
        "candles_required": 50
    }
}

# Bot settings
BOT_NAME = "ForexSignalBot"
BOT_DESCRIPTION = "High-probability Forex signal bot with multi-timeframe pullback strategy"

# File paths
DATA_DIR = "data"
SUBSCRIBERS_FILE = os.path.join(DATA_DIR, "subscribers.json")

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)


def is_trading_session() -> bool:
    """Check if current UTC time is within trading sessions."""
    now = datetime.utcnow().time()
    for session in TRADING_SESSIONS:
        if session["start"] <= now <= session["end"]:
            return True
    return False


def get_pair_name(symbol: str) -> str:
    """Get human-readable name for a forex pair symbol."""
    return PAIR_NAMES.get(symbol, symbol.replace("=X", ""))
