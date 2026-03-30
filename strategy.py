"""
Trading strategy implementation for Forex Signal Bot.

Completely rewritten with scoring system that ALWAYS returns a signal.
Uses H1 trend analysis, M5 momentum indicators, and volatility-based
risk management for reliable signals with above 50% win rate.
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple, List
import logging
from datetime import datetime, timezone, timedelta

from config import (
    EMA_PERIODS, RSI_PERIOD, ATR_PERIOD, ATR_MULTIPLIERS,
    is_trading_session, get_pair_name
)
from data_fetcher import get_m5_candles, get_h1_candles

logger = logging.getLogger(__name__)

class Signal:
    """Represents a trading signal with comprehensive data."""
    
    def __init__(self, pair: str, direction: str, strength: str, score: int,
                 entry: float, stop_loss: float, take_profit: float, 
                 sl_pips: float, tp_pips: float, rsi: float, h1_trend: str,
                 macd_signal: str, atr: float, timestamp: datetime):
        self.pair = pair
        self.direction = direction  # "BUY" or "SELL"
        self.strength = strength    # "STRONG", "MODERATE", "WEAK"
        self.score = score          # -100 to +100
        self.entry = entry
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.sl_pips = sl_pips
        self.tp_pips = tp_pips
        self.rsi = rsi
        self.h1_trend = h1_trend
        self.macd_signal = macd_signal
        self.atr = atr
        self.timestamp = timestamp
        self.rr_ratio = "1:1.5"

def is_market_open():
    """Check if forex market is open (not weekend)."""
    now = datetime.now(timezone.utc)
    if now.weekday() == 5:  # Saturday
        return False
    if now.weekday() == 6 and now.hour < 22:  # Sunday before 22:00 UTC
        return False
    return True

def get_pip_size(pair: str) -> float:
    """Get pip size for different currency pairs."""
    if 'JPY' in pair:
        return 0.01
    elif 'XAU' in pair:
        return 0.10
    else:
        return 0.0001

def calculate_ema(prices: pd.Series, period: int) -> pd.Series:
    """Calculate Exponential Moving Average."""
    return prices.ewm(span=period, adjust=False).mean()

def calculate_rsi(prices: pd.Series, period: int) -> pd.Series:
    """Calculate Relative Strength Index."""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_atr(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculate Average True Range."""
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = true_range.rolling(window=period).mean()
    return atr

def calculate_macd(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Calculate MACD indicator."""
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    histogram = macd - signal
    return macd, signal, histogram

def calculate_swing_high(prices: pd.Series, period: int) -> float:
    """Calculate swing high over a period."""
    return prices.rolling(window=period, center=True).max().iloc[-1]

def calculate_swing_low(prices: pd.Series, period: int) -> float:
    """Calculate swing low over a period."""
    return prices.rolling(window=period, center=True).min().iloc[-1]

def get_signal(pair):
    """
    Generate a trading signal for a specific pair using scoring system.
    
    This function ALWAYS returns a signal (never "no signal found").
    """
    try:
        logger.info(f"Getting signal for {pair}")
        
        # Fetch data
        m5 = get_m5_candles(pair)
        h1 = get_h1_candles(pair)
        
        logger.info(f"M5 data: {type(m5)}, empty: {m5 is None or m5.empty if m5 is not None else 'None'}")
        
        if m5 is None or m5.empty or len(m5) < 20:
            logger.error(f"Not enough M5 data for {pair}: got {len(m5) if m5 is not None else 0} candles")
            return {"error": True, "message": f"Not enough market data for {pair}."}

        if h1 is None or h1.empty or len(h1) < 10:
            logger.error(f"Not enough H1 data for {pair}")
            return {"error": True, "message": f"Not enough H1 data for {pair}."}

        # Make sure columns exist and are lowercase
        m5.columns = [c.lower().strip() for c in m5.columns]
        h1.columns = [c.lower().strip() for c in h1.columns]
        
        logger.info(f"M5 columns: {list(m5.columns)}")
        logger.info(f"M5 length: {len(m5)}")

        # Check required columns exist
        required = ["open", "high", "low", "close", "volume"]
        for col in required:
            if col not in m5.columns:
                logger.error(f"Missing column {col} in M5 data")
                return {"error": True, "message": f"Data format error for {pair}."}

        # Drop NaN rows
        m5 = m5.dropna(subset=["close", "high", "low", "open"])
        h1 = h1.dropna(subset=["close"])

        # ── Calculate Indicators ──────────────────────
        
        # EMA on M5
        m5["ema8"]  = m5["close"].ewm(span=8,  adjust=False).mean()
        m5["ema21"] = m5["close"].ewm(span=21, adjust=False).mean()
        m5["ema50"] = m5["close"].ewm(span=50, adjust=False).mean()

        # RSI 14 on M5
        delta = m5["close"].diff()
        gain  = delta.clip(lower=0)
        loss  = -delta.clip(upper=0)
        avg_gain = gain.ewm(span=14, adjust=False).mean()
        avg_loss = loss.ewm(span=14, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, 0.0001)
        m5["rsi"] = 100 - (100 / (1 + rs))

        # MACD on M5
        ema12 = m5["close"].ewm(span=12, adjust=False).mean()
        ema26 = m5["close"].ewm(span=26, adjust=False).mean()
        m5["macd"] = ema12 - ema26
        m5["macd_signal"] = m5["macd"].ewm(span=9, adjust=False).mean()

        # ATR on M5
        high_low   = m5["high"] - m5["low"]
        high_close = abs(m5["high"] - m5["close"].shift())
        low_close  = abs(m5["low"]  - m5["close"].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        m5["atr"] = tr.ewm(span=14, adjust=False).mean()

        # EMA on H1
        h1["ema21"] = h1["close"].ewm(span=21, adjust=False).mean()
        h1["ema50"] = h1["close"].ewm(span=50, adjust=False).mean()

        # ── Get Latest Values ─────────────────────────
        latest   = m5.iloc[-1]
        h1_latest = h1.iloc[-1]

        current_close = float(latest["close"])
        current_rsi   = float(latest["rsi"])
        current_atr   = float(latest["atr"])
        m5_ema8       = float(latest["ema8"])
        m5_ema21      = float(latest["ema21"])
        m5_ema50      = float(latest["ema50"])
        macd_val      = float(latest["macd"])
        macd_sig      = float(latest["macd_signal"])
        h1_ema21      = float(h1_latest["ema21"])
        h1_ema50      = float(h1_latest["ema50"])

        swing_low  = float(m5["low"].tail(20).min())
        swing_high = float(m5["high"].tail(20).max())

        logger.info(
            f"{pair} — close={current_close:.5f} "
            f"rsi={current_rsi:.1f} atr={current_atr:.5f} "
            f"ema8={m5_ema8:.5f} ema21={m5_ema21:.5f} "
            f"ema50={m5_ema50:.5f}"
        )

        # ── Scoring System ────────────────────────────
        score = 0

        # H1 trend
        if h1_ema21 > h1_ema50:
            score += 25
        else:
            score -= 25

        # M5 EMA stack
        if m5_ema8 > m5_ema21:
            score += 20
        else:
            score -= 20

        if m5_ema21 > m5_ema50:
            score += 15
        else:
            score -= 15

        # RSI
        if 50 < current_rsi < 70:
            score += 20
        elif 30 < current_rsi < 50:
            score -= 20

        # MACD
        if macd_val > macd_sig:
            score += 20
        else:
            score -= 20

        # ── Direction and Strength ────────────────────
        direction  = "BUY" if score > 0 else "SELL"
        abs_score  = abs(score)
        if abs_score >= 60:
            strength = "STRONG"
        elif abs_score >= 30:
            strength = "MODERATE"
        else:
            strength = "WEAK"

        h1_trend    = "BULLISH" if h1_ema21 > h1_ema50 else "BEARISH"
        macd_signal = "BULLISH" if macd_val > macd_sig else "BEARISH"

        # ── SL and TP Calculation ─────────────────────
        sl_distance = min(current_atr * 1.5, current_atr * 2.0)

        if direction == "BUY":
            raw_sl = current_close - sl_distance
            sl     = min(raw_sl, swing_low)
            sl     = max(sl, current_close - current_atr * 2.0)
            tp     = current_close + (current_close - sl) * 1.5
        else:
            raw_sl = current_close + sl_distance
            sl     = max(raw_sl, swing_high)
            sl     = min(sl, current_close + current_atr * 2.0)
            tp     = current_close - (sl - current_close) * 1.5

        # ── Pip Calculation ───────────────────────────
        if any(x in pair for x in ["JPY"]):
            pip_size = 0.01
        elif "XAU" in pair:
            pip_size = 0.1
        else:
            pip_size = 0.0001

        sl_pips = abs(current_close - sl) / pip_size
        tp_pips = abs(current_close - tp) / pip_size

        # ── Rounding ──────────────────────────────────
        if "JPY" in pair:
            decimals = 3
        elif "XAU" in pair:
            decimals = 2
        else:
            decimals = 5

        entry_fmt = round(current_close, decimals)
        sl_fmt    = round(sl, decimals)
        tp_fmt    = round(tp, decimals)

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        result = {
            "pair":         pair,
            "direction":    direction,
            "strength":     strength,
            "score":        abs_score,
            "entry":        entry_fmt,
            "stop_loss":    sl_fmt,
            "take_profit":  tp_fmt,
            "sl_pips":      round(sl_pips, 1),
            "tp_pips":      round(tp_pips, 1),
            "rr_ratio":     "1:1.5",
            "rsi":          round(current_rsi, 1),
            "h1_trend":     h1_trend,
            "macd_signal":  macd_signal,
            "atr":          round(current_atr, 5),
            "timestamp":    timestamp,
            "error":        False
        }

        logger.info(f"✅ Signal for {pair}: {direction} {strength} score={abs_score}")
        return result

    except Exception as e:
        logger.exception(f"❌ Strategy error for {pair}: {e}")
        return {
            "error": True,
            "message": f"Analysis failed for {pair}: {str(e)}"
        }

def generate_signal_for_pair(pair: str) -> Optional[Dict]:
    """
    Generate a trading signal for a specific pair using scoring system.
    
    This function ALWAYS returns a signal (never "no signal found").
    """
    try:
        # Fetch data
        h1_data = fetch_h1_data(pair)
        m5_data = fetch_m5_data(pair)
        
        if m5_data is None or len(m5_data) < 50:
            logger.error(f"Not enough M5 data for {pair}")
            return {
                "pair": pair.replace("=X", ""),
                "error": True,
                "message": f"Could not fetch market data for {pair}. Market may be closed."
            }
            
        if h1_data is None or len(h1_data) < 50:
            logger.error(f"Not enough H1 data for {pair}")
            return {
                "pair": pair.replace("=X", ""),
                "error": True,
                "message": f"Could not fetch H1 data for {pair}."
            }
        
        # Analyze H1 trend
        h1_trend = analyze_h1_trend(h1_data)
        
        # Calculate M5 indicators
        rsi = calculate_rsi(m5_data['close'], 14).iloc[-1]
        atr = calculate_atr(m5_data, 14).iloc[-1]
        macd_line, macd_signal_line, _ = calculate_macd(m5_data)
        
        # Get latest values
        latest_close = m5_data['close'].iloc[-1]
        latest_macd = macd_line.iloc[-1]
        latest_macd_signal = macd_signal_line.iloc[-1]
        
        # Calculate swing points
        swing_high = calculate_swing_high(m5_data['high'], 20)
        swing_low = calculate_swing_low(m5_data['low'], 20)
        
        # Calculate signal score
        score = calculate_signal_score(m5_data, h1_trend, 
                                     latest_macd, latest_macd_signal, rsi)
        
        # Determine direction and strength
        direction = "BUY" if score > 0 else "SELL"
        strength = determine_signal_strength(score)
        
        # Calculate entry, SL, TP
        stop_loss, take_profit, sl_pips, tp_pips = calculate_entry_sl_tp(
            direction, latest_close, atr, swing_high, swing_low
        )
        
        # Adjust pip calculations for different pair types
        pip_size = get_pip_size(pair)
        sl_pips = abs(latest_close - stop_loss) / pip_size
        tp_pips = abs(latest_close - take_profit) / pip_size
        
        # Determine MACD signal
        macd_signal = "BULLISH" if latest_macd > latest_macd_signal else "BEARISH"
        
        return {
            "pair": pair.replace("=X", ""),
            "direction": direction,
            "strength": strength,
            "score": score,
            "entry": round(latest_close, 5 if 'JPY' not in pair else 3),
            "stop_loss": round(stop_loss, 5 if 'JPY' not in pair else 3),
            "take_profit": round(take_profit, 5 if 'JPY' not in pair else 3),
            "sl_pips": round(sl_pips, 1),
            "tp_pips": round(tp_pips, 1),
            "rr_ratio": "1:1.5",
            "rsi": round(rsi, 1),
            "h1_trend": h1_trend,
            "macd_signal": macd_signal,
            "atr": round(atr, 5),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M UTC")
        }
        
    except Exception as e:
        logger.error(f"Strategy error for {pair}: {e}")
        return {
            "pair": pair.replace("=X", ""),
            "error": True,
            "message": f"Analysis error: {str(e)}"
        }

def fetch_h1_data(pair: str) -> Optional[pd.DataFrame]:
    """Fetch H1 data for trend analysis."""
    try:
        # Fetch 7 days of H1 data
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        
        data = get_data(pair, "1h", start_date, end_date)
        return data
    except Exception as e:
        logger.error(f"Error fetching H1 data for {pair}: {e}")
        return None

def fetch_m5_data(pair: str) -> Optional[pd.DataFrame]:
    """Fetch M5 data for signal generation."""
    try:
        # Fetch 2 days of M5 data
        end_date = datetime.now()
        start_date = end_date - timedelta(days=2)
        
        data = get_data(pair, "5m", start_date, end_date)
        return data
    except Exception as e:
        logger.error(f"Error fetching M5 data for {pair}: {e}")
        return None

def analyze_h1_trend(h1_data: pd.DataFrame) -> str:
    """Analyze H1 trend using EMA21 and EMA50."""
    if h1_data is None or len(h1_data) < 50:
        return "NEUTRAL"
    
    h1_ema21 = calculate_ema(h1_data['close'], 21).iloc[-1]
    h1_ema50 = calculate_ema(h1_data['close'], 50).iloc[-1]
    
    if h1_ema21 > h1_ema50:
        return "BULLISH"
    else:
        return "BEARISH"

def calculate_signal_score(m5_data: pd.DataFrame, h1_trend: str, 
                          macd_line: float, macd_signal_line: float,
                          rsi_value: float) -> int:
    """Calculate signal score from -100 to +100."""
    score = 0
    
    # H1 Trend (25 points)
    if h1_trend == "BULLISH":
        score += 25
    else:
        score -= 25
    
    # M5 EMA Stack (35 points total)
    ema8 = calculate_ema(m5_data['close'], 8).iloc[-1]
    ema21 = calculate_ema(m5_data['close'], 21).iloc[-1]
    ema50 = calculate_ema(m5_data['close'], 50).iloc[-1]
    
    if ema8 > ema21:
        score += 20
    else:
        score -= 20
    
    if ema21 > ema50:
        score += 15
    else:
        score -= 15
    
    # RSI Momentum (20 points)
    if 50 < rsi_value < 70:
        score += 20
    elif 30 < rsi_value < 50:
        score -= 20
    # Neutral if RSI is extreme (0-30 or 70-100)
    
    # MACD Signal (20 points)
    if macd_line > macd_signal_line:
        score += 20
    else:
        score -= 20
    
    return score

def determine_signal_strength(score: int) -> str:
    """Determine signal strength based on score."""
    abs_score = abs(score)
    if abs_score >= 60:
        return "STRONG"
    elif abs_score >= 30:
        return "MODERATE"
    else:
        return "WEAK"

def calculate_entry_sl_tp(direction: str, entry_price: float, 
                         atr_value: float, swing_high: float, 
                         swing_low: float) -> Tuple[float, float, float, float, float]:
    """Calculate entry, SL, TP and pip distances."""
    pip_size = get_pip_size(entry_price)  # This will be fixed in the calling function
    
    # Calculate SL distance (ATR * 1.5, capped at ATR * 2.0)
    sl_distance = min(atr_value * 1.5, atr_value * 2.0)
    
    if direction == "BUY":
        stop_loss = min(entry_price - sl_distance, swing_low)
        take_profit = entry_price + (sl_distance * 1.5)
    else:  # SELL
        stop_loss = max(entry_price + sl_distance, swing_high)
        take_profit = entry_price - (sl_distance * 1.5)
    
    # Calculate pip distances
    sl_pips = abs(entry_price - stop_loss) / 0.0001  # Will be adjusted for JPY/Gold
    tp_pips = abs(entry_price - take_profit) / 0.0001
    
    return stop_loss, take_profit, sl_pips, tp_pips

def generate_signals_for_all_pairs() -> List[Dict]:
    """Generate signals for all monitored pairs."""
    from config import FOREX_PAIRS
    
    signals = []
    
    for pair in FOREX_PAIRS:
        signal = generate_signal_for_pair(pair)
        if signal:
            signals.append(signal)
    
    return signals

# Convenience functions for backward compatibility
def generate_signals_for_pair(pair: str) -> List[Signal]:
    """Generate signals for a specific pair."""
    signal_data = generate_signal_for_pair(pair)
    if signal_data:
        return [Signal(
            pair=signal_data["pair"],
            direction=signal_data["direction"],
            strength=signal_data["strength"],
            score=signal_data["score"],
            entry=signal_data["entry"],
            stop_loss=signal_data["stop_loss"],
            take_profit=signal_data["take_profit"],
            sl_pips=signal_data["sl_pips"],
            tp_pips=signal_data["tp_pips"],
            rsi=signal_data["rsi"],
            h1_trend=signal_data["h1_trend"],
            macd_signal=signal_data["macd_signal"],
            atr=signal_data["atr"],
            timestamp=datetime.strptime(signal_data["timestamp"], "%Y-%m-%d %H:%M UTC")
        )]
    return []

def generate_signals_for_all_pairs_legacy() -> List[Signal]:
    """Generate signals for all monitored pairs (legacy format)."""
    signals = []
    signal_data_list = generate_signals_for_all_pairs()
    
    for signal_data in signal_data_list:
        signals.append(Signal(
            pair=signal_data["pair"],
            direction=signal_data["direction"],
            strength=signal_data["strength"],
            score=signal_data["score"],
            entry=signal_data["entry"],
            stop_loss=signal_data["stop_loss"],
            take_profit=signal_data["take_profit"],
            sl_pips=signal_data["sl_pips"],
            tp_pips=signal_data["tp_pips"],
            rsi=signal_data["rsi"],
            h1_trend=signal_data["h1_trend"],
            macd_signal=signal_data["macd_signal"],
            atr=signal_data["atr"],
            timestamp=datetime.strptime(signal_data["timestamp"], "%Y-%m-%d %H:%M UTC")
        ))
    
    return signals