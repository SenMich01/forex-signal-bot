"""
Signal scanner module for Forex Signal Bot.

Handles the scanning process, signal generation, and alert distribution.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Set
import json
import os

from config import (
    SCAN_INTERVAL_MINUTES, DUPLICATE_SIGNAL_COOLDOWN_MINUTES,
    SUBSCRIBERS_FILE, get_pair_name
)
from strategy import generate_signals_for_all_pairs, Signal
from data_fetcher import get_latest_price

logger = logging.getLogger(__name__)

class SignalScanner:
    """Main signal scanner that orchestrates the scanning process."""
    
    def __init__(self):
        self.subscribers = self._load_subscribers()
        self.last_scan_time = None
        self.last_signals = {}  # Track last signals to avoid duplicates
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
        """Add a new subscriber."""
        self.subscribers.add(chat_id)
        self._save_subscribers()
        logger.info(f"New subscriber added: {chat_id}")
    
    def remove_subscriber(self, chat_id: int):
        """Remove a subscriber."""
        self.subscribers.discard(chat_id)
        self._save_subscribers()
        logger.info(f"Subscriber removed: {chat_id}")
    
    def get_subscriber_count(self) -> int:
        """Get the number of subscribers."""
        return len(self.subscribers)
    
    def should_scan(self) -> bool:
        """Check if it's time to scan for signals."""
        if self.last_scan_time is None:
            return True
        
        time_since_last_scan = datetime.now() - self.last_scan_time
        return time_since_last_scan.total_seconds() >= SCAN_INTERVAL_MINUTES * 60
    
    def should_send_signal(self, signal: Signal) -> bool:
        """Check if signal should be sent (avoid duplicates)."""
        key = f"{signal.pair}_{signal.direction}"
        last_signal = self.last_signals.get(key)
        
        if last_signal is None:
            self.last_signals[key] = signal
            return True
        
        # Check cooldown period
        time_diff = signal.timestamp - last_signal.timestamp
        if time_diff.total_seconds() / 60 >= DUPLICATE_SIGNAL_COOLDOWN_MINUTES:
            self.last_signals[key] = signal
            return True
        
        return False
    
    async def scan_and_generate_signals(self) -> List[Signal]:
        """
        Perform a full scan and generate signals for all pairs.
        
        Returns:
            List of new signals generated
        """
        if not self.should_scan():
            return []
        
        self.scan_count += 1
        self.last_scan_time = datetime.now()
        
        logger.info(f"Starting scan #{self.scan_count}")
        
        try:
            # Generate signals for all pairs
            signals = generate_signals_for_all_pairs()
            
            # Filter out duplicates
            new_signals = []
            for signal in signals:
                if self.should_send_signal(signal):
                    new_signals.append(signal)
                    logger.info(f"New signal: {signal.direction} {signal.pair} at {signal.entry}")
                else:
                    logger.debug(f"Duplicate signal ignored: {signal.direction} {signal.pair}")
            
            if new_signals:
                logger.info(f"Generated {len(new_signals)} new signals")
            else:
                logger.info("No new signals generated")
            
            return new_signals
            
        except Exception as e:
            logger.error(f"Error during scan: {e}")
            return []
    
    def format_signal_message(self, signal: Signal) -> str:
        """
        Format a signal into a Telegram message.
        
        Returns:
            Formatted message string
        """
        pair_name = get_pair_name(signal.pair)
        
        # Calculate breakeven info
        breakeven_info = ""
        atr_distance = signal.atr if hasattr(signal, 'atr') else 0
        if atr_distance > 0 and signal.risk >= atr_distance:
            breakeven_info = "\n💡 Tip: Move SL to breakeven once +1x ATR in profit"
        
        # Get current price for context
        current_price = get_latest_price(signal.pair)
        price_info = f"\n📊 Current Price: {current_price:.5f}" if current_price else ""
        
        message = f"""🔔 FOREX SIGNAL — {pair_name}
📈 Direction: {signal.direction}
💰 Entry Price: {signal.entry:.5f}{price_info}
🛑 Stop Loss: {signal.stop_loss:.5f}  ({signal.pips_risk:+.1f} pips)
🎯 Take Profit: {signal.take_profit:.5f}  ({signal.pips_reward:+.1f} pips)
⚖️ Risk/Reward: 1:{signal.risk_reward:.1f}
📊 RSI: {signal.rsi:.1f}
⏰ Timeframe: M5 | Session: London/New York
{breakeven_info}
⏱️ Signal Time: {signal.timestamp.strftime('%Y-%m-%d %H:%M UTC')}"""
        
        return message
    
    def get_status_message(self) -> str:
        """Get bot status information."""
        status_time = self.last_scan_time.strftime('%Y-%m-%d %H:%M:%S') if self.last_scan_time else "Never"
        
        message = f"""🤖 Bot Status
📊 Subscribers: {self.get_subscriber_count()}
🔄 Last Scan: {status_time}
⚡ Scans: {self.scan_count}
⏱️ Scan Interval: {SCAN_INTERVAL_MINUTES} minutes
📅 Uptime: Active since startup"""
        
        return message
    
    def get_pairs_message(self) -> str:
        """Get list of monitored pairs."""
        pairs = [get_pair_name(pair) for pair in sorted(self.get_monitored_pairs())]
        message = "📈 Monitored Pairs:\n" + "\n".join([f"• {pair}" for pair in pairs])
        return message
    
    def get_monitored_pairs(self) -> List[str]:
        """Get list of all monitored pairs."""
        from config import FOREX_PAIRS
        return FOREX_PAIRS
    
    async def manual_signal_request(self, pair_symbol: str) -> List[Signal]:
        """
        Generate signals for a specific pair on manual request.
        
        Args:
            pair_symbol: Forex pair symbol (e.g., "EURUSD=X")
            
        Returns:
            List of signals for the requested pair
        """
        try:
            # Validate pair
            from config import FOREX_PAIRS
            if pair_symbol not in FOREX_PAIRS:
                return []
            
            # Generate signals for the specific pair
            signals = generate_signals_for_all_pairs()
            
            # Filter for the requested pair
            pair_signals = [s for s in signals if s.pair == pair_symbol]
            
            return pair_signals
            
        except Exception as e:
            logger.error(f"Error generating manual signal for {pair_symbol}: {e}")
            return []

# Global scanner instance
scanner = SignalScanner()

def get_scanner() -> SignalScanner:
    """Get the global scanner instance."""
    return scanner