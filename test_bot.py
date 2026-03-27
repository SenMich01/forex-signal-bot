#!/usr/bin/env python3
"""
Test script for Forex Signal Bot components.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import FOREX_PAIRS, get_pair_name
from data_fetcher import get_data, get_latest_price
from strategy import generate_signals_for_pair, Signal
from scanner import get_scanner

def test_config():
    """Test configuration loading."""
    print("Testing Configuration...")
    print(f"Monitored pairs: {len(FOREX_PAIRS)}")
    for pair in FOREX_PAIRS:
        print(f"  - {get_pair_name(pair)}")
    print("✓ Configuration loaded successfully\n")

def test_data_fetcher():
    """Test data fetching."""
    print("Testing Data Fetcher...")
    
    # Test with EURUSD
    pair = "EURUSD=X"
    print(f"Fetching data for {get_pair_name(pair)}...")
    
    data = get_data(pair, "M5")
    if data is not None:
        print(f"✓ Data fetched: {data.shape[0]} rows, {data.shape[1]} columns")
        print(f"  Latest price: {data['close'].iloc[-1]:.5f}")
        print(f"  Time range: {data['timestamp'].iloc[0]} to {data['timestamp'].iloc[-1]}")
    else:
        print("✗ Failed to fetch data")
    
    # Test latest price
    latest_price = get_latest_price(pair)
    if latest_price:
        print(f"✓ Latest price: {latest_price:.5f}")
    else:
        print("✗ Failed to get latest price")
    
    print()

def test_strategy():
    """Test strategy signal generation."""
    print("Testing Strategy...")
    
    for pair in FOREX_PAIRS[:2]:  # Test first 2 pairs
        print(f"Testing {get_pair_name(pair)}...")
        
        signals = generate_signals_for_pair(pair)
        print(f"  Generated {len(signals)} signals")
        
        if signals:
            signal = signals[0]
            print(f"  Signal: {signal.direction} at {signal.entry:.5f}")
            print(f"  SL: {signal.stop_loss:.5f} ({signal.pips_risk:+.1f} pips)")
            print(f"  TP: {signal.take_profit:.5f} ({signal.pips_reward:+.1f} pips)")
            print(f"  R/R: 1:{signal.risk_reward:.1f}")
            print(f"  RSI: {signal.rsi:.1f}")
    
    print()

def test_scanner():
    """Test scanner functionality."""
    print("Testing Scanner...")
    
    scanner = get_scanner()
    
    # Test subscriber management
    print(f"Current subscribers: {scanner.get_subscriber_count()}")
    
    # Test pairs listing
    pairs_message = scanner.get_pairs_message()
    print("Pairs message preview:")
    print(pairs_message[:200] + "..." if len(pairs_message) > 200 else pairs_message)
    
    print()

def main():
    """Run all tests."""
    print("Forex Signal Bot - Component Tests")
    print("=" * 40)
    
    try:
        test_config()
        test_data_fetcher()
        test_strategy()
        test_scanner()
        
        print("All tests completed successfully! ✓")
        print("\nTo run the bot:")
        print("1. Create .env file with your Telegram bot token")
        print("2. Run: python bot.py")
        
    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())