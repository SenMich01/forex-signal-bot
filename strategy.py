"""
Trading strategy implementation for Forex Signal Bot.

Contains all indicator calculations and signal generation logic
based on the M5 Scalper v3 Pine Script strategy.
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple, List
import logging
from datetime import datetime, timedelta

from config import (
    EMA_PERIODS, RSI_PERIOD, ATR_PERIOD, ATR_MULTIPLIERS,
    is_trading_session, get_pair_name
)
from data_fetcher import get_data

logger = logging.getLogger(__name__)

class Signal:
    """Represents a trading signal."""
    
    def __init__(self, pair: str, direction: str, entry: float, 
                 stop_loss: float, take_profit: float, rsi: float,
                 timestamp: datetime):
        self.pair = pair
        self.direction = direction  # "BUY" or "SELL"
        self.entry = entry
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.rsi = rsi
        self.timestamp = timestamp
        
        # Calculate risk and reward
        self.risk = abs(entry - stop_loss)
        self.reward = abs(take_profit - entry)
        self.risk_reward = self.reward / self.risk if self.risk > 0 else 0
        
        # Calculate pips (for Forex pairs)
        self.pips_risk = self.risk * 10000  # Standard pip calculation
        self.pips_reward = self.reward * 10000

class Strategy:
    """Main trading strategy implementation."""
    
    def __init__(self):
        self.last_signals = {}  # Track last signals to avoid duplicates
    
    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate all required indicators for the strategy.
        
        Args:
            data: DataFrame with OHLCV data
            
        Returns:
            DataFrame with indicator columns added
        """
        df = data.copy()
        
        # Calculate EMAs
        df['EMA8'] = self._calculate_ema(df['close'], EMA_PERIODS['EMA8'])
        df['EMA21'] = self._calculate_ema(df['close'], EMA_PERIODS['EMA21'])
        df['EMA50'] = self._calculate_ema(df['close'], EMA_PERIODS['EMA50'])
        
        # Calculate RSI
        df['RSI'] = self._calculate_rsi(df['close'], RSI_PERIOD)
        
        # Calculate ATR
        df['ATR'] = self._calculate_atr(df, ATR_PERIOD)
        
        # Calculate slopes (rate of change over 5 periods)
        df['EMA21_slope'] = self._calculate_slope(df['EMA21'], 5)
        df['EMA50_slope'] = self._calculate_slope(df['EMA50'], 5)
        
        # Calculate candle properties
        df['candle_range'] = df['high'] - df['low']
        df['bear_body'] = np.where(df['close'] < df['open'], 
                                   df['open'] - df['close'], 0)
        df['bull_body'] = np.where(df['close'] > df['open'], 
                                   df['close'] - df['open'], 0)
        
        # Calculate swing highs/lows for SL calculation
        df['swing_high'] = self._calculate_swing_high(df['high'], 10)
        df['swing_low'] = self._calculate_swing_low(df['low'], 10)
        
        return df
    
    def _calculate_ema(self, prices: pd.Series, period: int) -> pd.Series:
        """Calculate Exponential Moving Average."""
        return prices.ewm(span=period, adjust=False).mean()
    
    def _calculate_rsi(self, prices: pd.Series, period: int) -> pd.Series:
        """Calculate Relative Strength Index."""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def _calculate_atr(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate Average True Range."""
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(window=period).mean()
        return atr
    
    def _calculate_slope(self, series: pd.Series, period: int) -> pd.Series:
        """Calculate slope over a given period."""
        return (series - series.shift(period)) / period
    
    def _calculate_swing_high(self, high_prices: pd.Series, period: int) -> pd.Series:
        """Calculate swing high over a period."""
        return high_prices.rolling(window=period, center=True).max()
    
    def _calculate_swing_low(self, low_prices: pd.Series, period: int) -> pd.Series:
        """Calculate swing low over a period."""
        return low_prices.rolling(window=period, center=True).min()
    
    def check_sell_signal(self, df: pd.DataFrame, pair: str) -> Optional[Signal]:
        """
        Check for SELL signal based on all conditions.
        
        SELL conditions:
        1. M5: EMA8 < EMA21 < EMA50 (bearish stack)
        2. H1: EMA8 < EMA21 < EMA50 (strong H1 downtrend)
        3. EMA21 slope and EMA50 slope both negative over last 5 candles
        4. Price touched EMA21 within last 2 candles and close < EMA50
        5. Close < EMA50 - ATR*0.3 (clear of EMA50)
        6. RSI falling: rsi < rsi[2] and rsi < 60 and rsi > 35
        7. Strong bearish candle: bearBody > candleRange * 0.5 and close < (low + candleRange * 0.3)
        8. Current UTC hour is in session
        """
        if len(df) < 10:
            return None
        
        # Get latest values
        latest = df.iloc[-1]
        prev_1 = df.iloc[-2]
        prev_2 = df.iloc[-3]
        
        # Condition 1: M5 EMA stack (bearish)
        if not (latest['EMA8'] < latest['EMA21'] < latest['EMA50']):
            return None
        
        # Condition 2: H1 EMA stack (strong downtrend) - would need H1 data
        # For now, we'll use M5 as proxy, but ideally should fetch H1 data
        # This is a simplification for the initial implementation
        
        # Condition 3: EMA slopes negative
        if latest['EMA21_slope'] >= 0 or latest['EMA50_slope'] >= 0:
            return None
        
        # Condition 4: Price touched EMA21 within last 2 candles and close < EMA50
        touched_ema21 = (latest['high'] >= latest['EMA21'] - latest['ATR'] * ATR_MULTIPLIERS['ENTRY']) or \
                       (prev_1['high'] >= prev_1['EMA21'] - prev_1['ATR'] * ATR_MULTIPLIERS['ENTRY'])
        
        if not touched_ema21 or latest['close'] >= latest['EMA50']:
            return None
        
        # Condition 5: Clear of EMA50
        if latest['close'] >= latest['EMA50'] - latest['ATR'] * ATR_MULTIPLIERS['ENTRY']:
            return None
        
        # Condition 6: RSI falling and in range
        if not (latest['RSI'] < prev_2['RSI'] and 
                35 < latest['RSI'] < 60):
            return None
        
        # Condition 7: Strong bearish candle
        strong_bearish = (latest['bear_body'] > latest['candle_range'] * 0.5 and
                         latest['close'] < (latest['low'] + latest['candle_range'] * 0.3))
        
        if not strong_bearish:
            return None
        
        # Condition 8: Trading session
        if not is_trading_session():
            return None
        
        # Calculate entry, SL, TP
        entry = latest['close']
        sl = max(latest['EMA50'] + latest['ATR'] * ATR_MULTIPLIERS['SL'], 
                 latest['swing_high'])
        tp = entry - (sl - entry) * ATR_MULTIPLIERS['TP']
        
        # Validate risk/reward
        if (tp - entry) / (entry - sl) < 1.0:
            return None
        
        return Signal(
            pair=pair,
            direction="SELL",
            entry=entry,
            stop_loss=sl,
            take_profit=tp,
            rsi=latest['RSI'],
            timestamp=latest['timestamp']
        )
    
    def check_buy_signal(self, df: pd.DataFrame, pair: str) -> Optional[Signal]:
        """
        Check for BUY signal based on all conditions.
        
        BUY conditions:
        1. H1: EMA8 > EMA50 (H1 bullish) - simplified to M5 for now
        2. RSI dropped below 35 within last 5 candles (oversold dip)
        3. RSI now recovering: rsi > rsi[1] and rsi > rsi[2] and rsi > 35 and rsi < 60
        4. Price near EMA50: low <= EMA50 + ATR*1.5 and close > EMA50 - ATR*0.5
        5. Close > EMA21 and previous candle low < EMA21 (recaptured EMA21)
        6. Strong bullish candle: bullBody > candleRange * 0.5 and close > (high - candleRange * 0.3)
        7. EMA50 flat or rising: ema50 >= ema50[3 candles ago]
        8. Current UTC hour is in session
        """
        if len(df) < 10:
            return None
        
        # Get latest values
        latest = df.iloc[-1]
        prev_1 = df.iloc[-2]
        prev_2 = df.iloc[-3]
        prev_3 = df.iloc[-4]
        
        # Condition 1: EMA stack (simplified bullish check)
        if not (latest['EMA8'] > latest['EMA50']):
            return None
        
        # Condition 2: RSI was oversold within last 5 candles
        recent_rsi = df['RSI'].tail(5)
        was_oversold = (recent_rsi < 35).any()
        
        if not was_oversold:
            return None
        
        # Condition 3: RSI recovering
        if not (latest['RSI'] > prev_1['RSI'] and 
                latest['RSI'] > prev_2['RSI'] and
                35 < latest['RSI'] < 60):
            return None
        
        # Condition 4: Price near EMA50
        if not (latest['low'] <= latest['EMA50'] + latest['ATR'] * ATR_MULTIPLIERS['ENTRY_BUY'] and
                latest['close'] > latest['EMA50'] - latest['ATR'] * ATR_MULTIPLIERS['ENTRY']):
            return None
        
        # Condition 5: Recaptured EMA21
        if not (latest['close'] > latest['EMA21'] and 
                prev_1['low'] < prev_1['EMA21']):
            return None
        
        # Condition 6: Strong bullish candle
        strong_bullish = (latest['bull_body'] > latest['candle_range'] * 0.5 and
                         latest['close'] > (latest['high'] - latest['candle_range'] * 0.3))
        
        if not strong_bullish:
            return None
        
        # Condition 7: EMA50 flat or rising
        if latest['EMA50'] < prev_3['EMA50']:
            return None
        
        # Condition 8: Trading session
        if not is_trading_session():
            return None
        
        # Calculate entry, SL, TP
        entry = latest['close']
        sl = min(latest['EMA50'] - latest['ATR'] * ATR_MULTIPLIERS['SL'], 
                 latest['swing_low'])
        tp = entry + (entry - sl) * ATR_MULTIPLIERS['TP_BUY']
        
        # Validate risk/reward
        if (tp - entry) / (entry - sl) < 1.0:
            return None
        
        return Signal(
            pair=pair,
            direction="BUY",
            entry=entry,
            stop_loss=sl,
            take_profit=tp,
            rsi=latest['RSI'],
            timestamp=latest['timestamp']
        )
    
    def generate_signals(self, pair: str) -> List[Signal]:
        """
        Generate trading signals for a specific pair.
        
        Args:
            pair: Forex pair symbol
            
        Returns:
            List of generated signals (usually 0 or 1 per call)
        """
        signals = []
        
        try:
            # Fetch M5 data
            data = get_data(pair, "M5")
            if data is None or len(data) < 50:
                logger.warning(f"Insufficient data for {pair}")
                return signals
            
            # Calculate indicators
            df = self.calculate_indicators(data)
            
            # Check for signals
            sell_signal = self.check_sell_signal(df, pair)
            buy_signal = self.check_buy_signal(df, pair)
            
            # Add valid signals
            if sell_signal:
                signals.append(sell_signal)
                logger.info(f"SELL signal generated for {pair}")
            
            if buy_signal:
                signals.append(buy_signal)
                logger.info(f"BUY signal generated for {pair}")
            
        except Exception as e:
            logger.error(f"Error generating signals for {pair}: {str(e)}")
        
        return signals
    
    def should_send_signal(self, signal: Signal) -> bool:
        """
        Check if signal should be sent (avoid duplicates).
        
        Args:
            signal: Generated signal
            
        Returns:
            True if signal should be sent, False if duplicate
        """
        key = f"{signal.pair}_{signal.direction}"
        last_signal = self.last_signals.get(key)
        
        if last_signal is None:
            self.last_signals[key] = signal
            return True
        
        # Check cooldown period
        time_diff = signal.timestamp - last_signal.timestamp
        cooldown_minutes = 15  # From config
        
        if time_diff.total_seconds() / 60 >= cooldown_minutes:
            self.last_signals[key] = signal
            return True
        
        return False

# Global strategy instance
strategy = Strategy()

def generate_signals_for_pair(pair: str) -> List[Signal]:
    """Convenience function to generate signals for a pair."""
    return strategy.generate_signals(pair)

def generate_signals_for_all_pairs() -> List[Signal]:
    """Generate signals for all monitored pairs."""
    all_signals = []
    
    from config import FOREX_PAIRS
    
    for pair in FOREX_PAIRS:
        signals = generate_signals_for_pair(pair)
        all_signals.extend(signals)
    
    return all_signals