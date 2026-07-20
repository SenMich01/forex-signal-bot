"""
Signal scanner module for Forex Signal Bot.

Handles scheduled scanning, signal generation, and alert distribution.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Set
import json
import os

from config import (
    SCAN_INTERVAL_MINUTES, DUPLICATE_SIGNAL_COOLDOWN_MINUTES,
    SUBSCRIBERS_FILE, get_pair_name, FOREX_PAIRS
)
from strategy import scan_all_pairs, get_signal
from data_fetcher import get_latest_price

logger = logging.getLogger(__name__)


class SignalScanner:
    """Main signal scanner that orchestrates the scanning process."""

    def __init__(self):
        self.subscribers = self._load_subscribers()
        self.last_scan_time = None
        # Cooldown tracker: key = "PAIR_TIMEFRAME_DIRECTION"
        self.last_signals = {}
        self.scan_count = 0

    def _load_subscribers(self) -> Set[int]:
        """Load subscriber chat IDs from file."""
        try:
            if os.path.exists(SUBSCRIBERS_FILE):
                with open(SUBSCRIBERS_FILE, 'r') as f:
                    data = json.load(f)
                    return set(data.get('subscribers', []))
        except Exception as e:
            logger.error(f"Error loading subscribers: {e}")
        return set()

    def _save_subscribers(self):
        """Save subscriber chat IDs to file."""
        try:
            with open(SUBSCRIBERS_FILE, 'w') as f:
                json.dump({'subscribers': list(self.subscribers)}, f)
        except Exception as e:
            logger.error(f"Error saving subscribers: {e}")

    def add_subscriber(self, chat_id: int):
        self.subscribers.add(chat_id)
        self._save_subscribers()
        logger.info(f"New subscriber added: {chat_id}")

    def remove_subscriber(self, chat_id: int):
        self.subscribers.discard(chat_id)
        self._save_subscribers()
        logger.info(f"Subscriber removed: {chat_id}")

    def get_subscriber_count(self) -> int:
        return len(self.subscribers)

    def should_scan(self) -> bool:
        if self.last_scan_time is None:
            return True
        elapsed = (datetime.now() - self.last_scan_time).total_seconds()
        return elapsed >= SCAN_INTERVAL_MINUTES * 60

    def should_send_signal(self, signal: Dict) -> bool:
        """Avoid duplicate signals within the cooldown window."""
        key = f"{signal['pair']}_{signal['timeframe']}_{signal['direction']}"
        last_time = self.last_signals.get(key)

        now = datetime.now(timezone.utc)
        if last_time is None:
            self.last_signals[key] = now
            return True

        elapsed_minutes = (now - last_time).total_seconds() / 60
        if elapsed_minutes >= DUPLICATE_SIGNAL_COOLDOWN_MINUTES:
            self.last_signals[key] = now
            return True

        return False

    async def scan_and_generate_signals(self, timeframe: str = "M5") -> List[Dict]:
        """Scan all pairs and return only new, valid signals."""
        if not self.should_scan():
            return []

        self.scan_count += 1
        self.last_scan_time = datetime.now()
        logger.info(f"Starting scan #{self.scan_count} on {timeframe}")

        try:
            signals = scan_all_pairs(timeframe)
            new_signals = []
            for signal in signals:
                if signal.get("strength") == "STRONG" and self.should_send_signal(signal):
                    new_signals.append(signal)
                    logger.info(
                        f"New STRONG signal: {signal['direction']} {signal['pair']} "
                        f"{signal['timeframe']} at {signal['entry']}"
                    )
            logger.info(f"Generated {len(new_signals)} new STRONG signals")
            return new_signals
        except Exception as e:
            logger.error(f"Error during scan: {e}")
            return []

    def format_signal_message(self, signal: Dict) -> str:
        """Format a signal dict into a Telegram message."""
        pair_name = get_pair_name(signal["pair"] + "=X")
        direction = signal["direction"]
        emoji = "📈" if direction == "BUY" else "📉"

        return (
            f"🔔 FOREX SIGNAL — {pair_name} ({signal['timeframe']})\n"
            f"{emoji} Direction: {direction}\n"
            f"💪 Strength: {signal['strength']} ({signal['score']}/100)\n\n"
            f"💰 Entry Price: {signal['entry']}\n"
            f"🛑 Stop Loss:   {signal['stop_loss']} ({signal['sl_pips']:+.1f} pips)\n"
            f"🎯 Take Profit: {signal['take_profit']} ({signal['tp_pips']:+.1f} pips)\n"
            f"⚖️ Risk/Reward: {signal['rr_ratio']}\n\n"
            f"📉 RSI: {signal['rsi']:.1f}\n"
            f"📊 HTF Trend: {signal['htf_trend']}\n"
            f"📈 MACD: {signal['macd_signal']}\n"
            f"🧩 Confluence: {signal.get('reasons', '')}\n"
            f"{signal.get('rn_note', '')}\n"
            f"⚠️ Risk 1-2% per trade only\n"
            f"⏱️ Signal Time: {signal['timestamp']}"
        )

    def get_status_message(self) -> str:
        status_time = (
            self.last_scan_time.strftime('%Y-%m-%d %H:%M:%S')
            if self.last_scan_time else "Never"
        )
        return (
            f"🤖 Bot Status\n"
            f"📊 Subscribers: {self.get_subscriber_count()}\n"
            f"🔄 Last Scan: {status_time}\n"
            f"⚡ Scans: {self.scan_count}\n"
            f"⏱️ Scan Interval: {SCAN_INTERVAL_MINUTES} minutes\n"
            f"📅 Uptime: Active since startup"
        )

    def get_pairs_message(self) -> str:
        pairs = [get_pair_name(pair) for pair in sorted(FOREX_PAIRS)]
        return "📈 Monitored Pairs:\n" + "\n".join([f"• {pair}" for pair in pairs])

    def get_monitored_pairs(self) -> List[str]:
        return FOREX_PAIRS

    async def manual_signal_request(self, pair_symbol: str, timeframe: str = "M5") -> List[Dict]:
        """Generate signal for a specific pair on manual request."""
        pair_clean = pair_symbol.replace("=X", "")
        if pair_symbol not in FOREX_PAIRS and pair_clean not in [p.replace("=X", "") for p in FOREX_PAIRS]:
            return []
        signal = get_signal(pair_clean, timeframe)
        if signal.get("signal"):
            return [signal]
        return []


# Global scanner instance
scanner = SignalScanner()


def get_scanner() -> SignalScanner:
    return scanner
