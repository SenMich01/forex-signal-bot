#!/usr/bin/env python3
"""
Test script for Forex Signal Bot components.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import FOREX_PAIRS, get_pair_name
from data_fetcher import get_candles, get_latest_price
from strategy import get_signal, scan_all_pairs
from scanner import get_scanner


def test_config():
    print("Testing Configuration...")
    print(f"Monitored pairs: {len(FOREX_PAIRS)}")
    for pair in FOREX_PAIRS:
        print(f"  - {get_pair_name(pair)}")
    print("✓ Configuration loaded successfully\n")


def test_data_fetcher():
    print("Testing Data Fetcher...")
    pair = "EURUSD"
    print(f"Fetching data for {pair}...")

    m5 = get_candles(pair, "5m", "2d")
    if m5 is not None:
        print(f"✓ M5 fetched: {m5.shape[0]} rows, {m5.shape[1]} columns")
        print(f"  Latest price: {m5['close'].iloc[-1]:.5f}")
    else:
        print("✗ Failed to fetch M5 data")

    latest_price = get_latest_price(pair)
    if latest_price:
        print(f"✓ Latest price: {latest_price:.5f}")
    else:
        print("✗ Failed to get latest price")
    print()


def test_strategy():
    print("Testing Strategy...")
    for pair in ["EURUSD", "USDJPY"]:
        for tf in ["M5", "H1"]:
            print(f"Testing {pair} {tf}...")
            sig = get_signal(pair, tf)
            if sig.get("error"):
                print(f"  ✗ Error: {sig['message']}")
            elif sig.get("signal"):
                print(f"  ✓ {sig['direction']} {sig['strength']} at {sig['entry']}")
                print(f"    SL: {sig['stop_loss']} ({sig['sl_pips']:+.1f} pips)")
                print(f"    TP: {sig['take_profit']} ({sig['tp_pips']:+.1f} pips)")
                print(f"    RR: {sig['rr_ratio']} | RSI: {sig['rsi']:.1f}")
            else:
                print(f"  — {sig.get('message', 'No signal')}")
    print()


def test_scanner():
    print("Testing Scanner...")
    scanner = get_scanner()
    print(f"Current subscribers: {scanner.get_subscriber_count()}")
    print(scanner.get_pairs_message()[:300] + "...")
    print()


def main():
    print("Forex Signal Bot - Component Tests")
    print("=" * 40)
    try:
        test_config()
        test_data_fetcher()
        test_strategy()
        test_scanner()
        print("All tests completed successfully! ✓")
    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
