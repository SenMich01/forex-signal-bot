"""
Configuration module for Forex Signal Bot.

Contains all settings, pairs to monitor, and trading parameters.
"""

import os
from datetime import datetime, time

# Forex pairs to monitor (7 pairs as specified)
FOREX_PAIRS = [
    "USDJPY=X",
    "EURUSD=X", 
    "GBPUSD=X",
    "XAUUSD=X",  # Gold
    "USDCAD=X",
    "EURJPY=X",
    "GBPJPY=X"
]

# Human-readable pair names for display
PAIR_NAMES = {
    "USDJPY=X": "USD/JPY",
    "EURUSD=X": "EUR/USD",
    "GBPUSD=X": "GBP/USD",
    "XAUUSD=X": "XAU/USD (Gold)",
    "USDCAD=X": "USD/CAD",
    "EURJPY=X": "EUR/JPY",
    "GBPJPY=X": "GBP/JPY"
}

# Trading session hours (UTC) - London and New York overlap
TRADING_SESSIONS = [
    {"start": time(7, 0), "end": time(16, 0)},  # London session
    {"start": time(13, 0), "end": time(21, 0)}  # New York session
]

# Indicator parameters
EMA_PERIODS = {
    "EMA8": 8,
    "EMA21": 21,
    "EMA50": 50
}

RSI_PERIOD = 9
ATR_PERIOD = 14

# Signal parameters
ATR_MULTIPLIERS = {
    "SL": 1.0,      # Stop Loss distance from EMA50
    "TP": 1.3,      # Take Profit multiplier for SELL
    "TP_BUY": 1.5,  # Take Profit multiplier for BUY
    "ENTRY": 0.3,   # Entry proximity to EMA21
    "ENTRY_BUY": 1.5  # Entry proximity to EMA50 for BUY
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
        "period": "1d",  # Last 1 day for M5 data
        "candles_required": 100  # Minimum candles needed
    },
    "H1": {
        "interval": "1h", 
        "period": "5d",  # Last 5 days for H1 data
        "candles_required": 50   # Minimum candles needed
    }
}

# Bot settings
BOT_NAME = "ForexSignalBot"
BOT_DESCRIPTION = "Real-time Forex signal bot with M5 Scalper v3 strategy"

# File paths
DATA_DIR = "data"
SUBSCRIBERS_FILE = os.path.join(DATA_DIR, "subscribers.json")

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

def is_trading_session():
    """Check if current UTC time is within trading sessions."""
    now = datetime.utcnow().time()
    
    for session in TRADING_SESSIONS:
        if session["start"] <= now <= session["end"]:
            return True
    return False

def get_pair_name(symbol):
    """Get human-readable name for a forex pair symbol."""
    return PAIR_NAMES.get(symbol, symbol.replace("=X", ""))