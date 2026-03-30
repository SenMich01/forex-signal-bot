"""
Trading strategy implementation for Forex Signal Bot.

New strategy focuses on:
1. Following dominant trend (H4 bias)
2. Finding optimal entry points (pullbacks, not breakouts)
3. Checking psychological round number levels for confluence
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

def get_h4_candles(pair):
    """Fetch H4 data for dominant trend bias."""
    df = get_candles(pair, "4h", "60d")
    if df is None or len(df) < 20:
        df = get_candles(pair, "4h", "30d")
    return df

def get_candles(pair, interval, period):
    """Fetch candles using data_fetcher."""
    from data_fetcher import get_candles as fetch_candles
    return fetch_candles(pair, interval, period)

def get_market_structure(h1_df):
    """Check market structure for higher highs/lows."""
    # Get last 5 swing highs and lows
    highs = h1_df["high"].rolling(5, center=True).max()
    lows  = h1_df["low"].rolling(5, center=True).min()
    
    recent_highs = highs.dropna().tail(3).values
    recent_lows  = lows.dropna().tail(3).values
    
    # Bullish structure: each low higher than previous
    bull_structure = (
        len(recent_lows) >= 2 and 
        recent_lows[-1] > recent_lows[-2]
    )
    
    # Bearish structure: each high lower than previous
    bear_structure = (
        len(recent_highs) >= 2 and 
        recent_highs[-1] < recent_highs[-2]
    )
    
    return bull_structure, bear_structure

def check_round_numbers(price, atr, pair):
    """
    Check if price is near a round number level.
    Returns: 
      'NEAR_SUPPORT'    - price just above round number (bullish)
      'NEAR_RESISTANCE' - price just below round number (bearish)
      'NEUTRAL'         - not near round number
    """
    # Determine pip size
    if "JPY" in pair:
        round_intervals = [0.50, 1.0, 5.0, 10.0]
        proximity = atr * 1.5
    elif "XAU" in pair:
        round_intervals = [5.0, 10.0, 25.0, 50.0, 100.0]
        proximity = atr * 1.5
    else:
        round_intervals = [0.00500, 0.01000, 0.05000, 0.10000]
        proximity = atr * 1.5

    for interval in round_intervals:
        # Find nearest round number
        nearest = round(price / interval) * interval
        distance = abs(price - nearest)
        
        if distance <= proximity:
            # Price is above round number = support below
            if price >= nearest:
                return 'NEAR_SUPPORT', nearest
            # Price is below round number = resistance above
            else:
                return 'NEAR_RESISTANCE', nearest
    
    return 'NEUTRAL', None

def get_rsi_signal(rsi_series):
    """Calculate RSI signal with zones."""
    current = rsi_series.iloc[-1]
    previous = rsi_series.iloc[-3]
    
    score = 0
    
    # Crossed above 40 = bullish momentum returning
    if previous < 40 and current >= 40:
        score += 15
    # Crossed below 60 = bearish momentum returning    
    elif previous > 60 and current <= 60:
        score -= 15
    # Good buy zone
    elif 50 <= current <= 65:
        score += 10
    # Good sell zone
    elif 35 <= current <= 50:
        score -= 10
    # Overbought - avoid buys
    elif current > 70:
        score -= 20
    # Oversold - favor buys
    elif current < 30:
        score += 20
        
    return score, current

def check_ema_pullback(m5_df):
    """
    Check for EMA pullback entries.
    BUY pullback: price dipped to EMA21 then bounced back up
    SELL pullback: price rallied to EMA21 then rejected back down
    """
    close  = m5_df["close"]
    ema21  = m5_df["ema21"]
    ema50  = m5_df["ema50"]
    
    # Check last 3 candles for pullback
    recent_low  = m5_df["low"].iloc[-3:].min()
    recent_high = m5_df["high"].iloc[-3:].max()
    current     = close.iloc[-1]
    atr         = m5_df["atr"].iloc[-1]
    
    # Bullish pullback: recent low touched EMA21 area, 
    # now price back above EMA21
    bull_pullback = (
        recent_low <= ema21.iloc[-1] + atr * 0.3 and
        current > ema21.iloc[-1] and
        current > ema50.iloc[-1]
    )
    
    # Bearish pullback: recent high touched EMA21 area,
    # now price back below EMA21
    bear_pullback = (
        recent_high >= ema21.iloc[-1] - atr * 0.3 and
        current < ema21.iloc[-1] and
        current < ema50.iloc[-1]
    )
    
    return bull_pullback, bear_pullback

def get_macd_score(m5_df):
    """Calculate MACD momentum score."""
    macd     = m5_df["macd"]
    signal   = m5_df["macd_signal"]
    
    current_macd   = macd.iloc[-1]
    current_signal = signal.iloc[-1]
    prev_macd      = macd.iloc[-2]
    prev_signal    = signal.iloc[-2]
    
    score = 0
    
    # Fresh bullish crossover (most powerful)
    if prev_macd <= prev_signal and current_macd > current_signal:
        score += 20
    # Fresh bearish crossover (most powerful)
    elif prev_macd >= prev_signal and current_macd < current_signal:
        score -= 20
    # Already bullish
    elif current_macd > current_signal:
        score += 10
    # Already bearish
    elif current_macd < current_signal:
        score -= 10
        
    return score

def get_signal(pair):
    """
    Generate a trading signal for a specific pair using improved scoring system.
    
    This function ALWAYS returns a signal (never "no signal found").
    """
    try:
        logger.info(f"Getting signal for {pair}")
        
        # Fetch data
        m5 = get_m5_candles(pair)
        h1 = get_h1_candles(pair)
        h4 = get_h4_candles(pair)
        
        if m5 is None or m5.empty or len(m5) < 20:
            logger.error(f"Not enough M5 data for {pair}: got {len(m5) if m5 is not None else 0} candles")
            return {"error": True, "message": f"Not enough market data for {pair}."}

        if h1 is None or h1.empty or len(h1) < 10:
            logger.error(f"Not enough H1 data for {pair}")
            return {"error": True, "message": f"Not enough H1 data for {pair}."}

        # Clean columns
        for df in [m5, h1]:
            df.columns = [c.lower().strip() for c in df.columns]
        if h4 is not None:
            h4.columns = [c.lower().strip() for c in h4.columns]
        
        # Check required columns exist
        required = ["open", "high", "low", "close", "volume"]
        for col in required:
            if col not in m5.columns:
                logger.error(f"Missing column {col} in M5 data")
                return {"error": True, "message": f"Data format error for {pair}."}

        # Drop NaN rows
        m5 = m5.dropna(subset=["close", "high", "low", "open"])
        h1 = h1.dropna(subset=["close"])
        if h4 is not None:
            h4 = h4.dropna(subset=["close"])

        # Calculate M5 indicators
        m5["ema8"]  = m5["close"].ewm(span=8,  adjust=False).mean()
        m5["ema21"] = m5["close"].ewm(span=21, adjust=False).mean()
        m5["ema50"] = m5["close"].ewm(span=50, adjust=False).mean()
        
        delta    = m5["close"].diff()
        gain     = delta.clip(lower=0)
        loss     = -delta.clip(upper=0)
        avg_gain = gain.ewm(span=14, adjust=False).mean()
        avg_loss = loss.ewm(span=14, adjust=False).mean()
        rs       = avg_gain / avg_loss.replace(0, 0.0001)
        m5["rsi"] = 100 - (100 / (1 + rs))
        
        ema12        = m5["close"].ewm(span=12, adjust=False).mean()
        ema26        = m5["close"].ewm(span=26, adjust=False).mean()
        m5["macd"]         = ema12 - ema26
        m5["macd_signal"]  = m5["macd"].ewm(span=9, adjust=False).mean()
        
        hl  = m5["high"] - m5["low"]
        hc  = abs(m5["high"] - m5["close"].shift())
        lc  = abs(m5["low"]  - m5["close"].shift())
        tr  = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        m5["atr"] = tr.ewm(span=14, adjust=False).mean()
        
        # Calculate H1 indicators
        h1["ema21"] = h1["close"].ewm(span=21, adjust=False).mean()
        h1["ema50"] = h1["close"].ewm(span=50, adjust=False).mean()
        
        # Calculate H4 indicators
        h4_ema21_val = None
        h4_ema50_val = None
        h4_bias      = "NEUTRAL"
        if h4 is not None and len(h4) >= 20:
            h4["ema21"]  = h4["close"].ewm(span=21, adjust=False).mean()
            h4["ema50"]  = h4["close"].ewm(span=50, adjust=False).mean()
            h4_ema21_val = float(h4["ema21"].iloc[-1])
            h4_ema50_val = float(h4["ema50"].iloc[-1])
            h4_bias      = "BULL" if h4_ema21_val > h4_ema50_val else "BEAR"
        
        # Get latest values
        latest        = m5.iloc[-1]
        h1_latest     = h1.iloc[-1]
        current_close = float(latest["close"])
        current_atr   = float(latest["atr"])
        h1_ema21_val  = float(h1_latest["ema21"])
        h1_ema50_val  = float(h1_latest["ema50"])
        swing_low     = float(m5["low"].tail(20).min())
        swing_high    = float(m5["high"].tail(20).max())
        
        # ── SCORING ──────────────────────────────────
        score = 0
        
        # 1. H4 dominant trend (+/- 30)
        if h4_bias == "BULL":
            score += 30
        elif h4_bias == "BEAR":
            score -= 30
        
        # 2. H1 trend (+/- 20)
        if h1_ema21_val > h1_ema50_val:
            score += 20
        else:
            score -= 20
        
        # 3. Market structure (+/- 20)
        bull_struct, bear_struct = get_market_structure(h1)
        if bull_struct:
            score += 20
        elif bear_struct:
            score -= 20
        
        # 4. EMA pullback entry (+/- 20)
        bull_pb, bear_pb = check_ema_pullback(m5)
        if bull_pb:
            score += 20
        elif bear_pb:
            score -= 20
        
        # 5. RSI score (+/- 20)
        rsi_score, current_rsi = get_rsi_signal(m5["rsi"])
        score += rsi_score
        
        # 6. MACD (+/- 20)
        macd_score = get_macd_score(m5)
        score += macd_score
        
        # 7. Round number check (+/- 15)
        rn_result, rn_level = check_round_numbers(
            current_close, current_atr, pair
        )
        # We apply round number score AFTER direction decision
        
        # ── DIRECTION DECISION ────────────────────────
        # H4 bias overrides if strong enough
        direction = "BUY" if score > 0 else "SELL"
        
        # Apply round number scoring based on direction
        if direction == "BUY":
            if rn_result == "NEAR_SUPPORT":
                score += 15   # Support below = good for buy
            elif rn_result == "NEAR_RESISTANCE":
                score -= 15   # Resistance above = bad for buy
        else:
            if rn_result == "NEAR_RESISTANCE":
                score += 15   # Resistance above = good for sell
            elif rn_result == "NEAR_SUPPORT":
                score -= 15   # Support below = bad for sell
        
        # Recalculate direction after round numbers
        direction = "BUY" if score > 0 else "SELL"
        
        abs_score = abs(score)
        if abs_score >= 70:
            strength = "STRONG"
        elif abs_score >= 40:
            strength = "MODERATE"
        else:
            strength = "WEAK"
        
        h1_trend    = "BULLISH" if h1_ema21_val > h1_ema50_val else "BEARISH"
        macd_label  = "BULLISH" if float(latest["macd"]) > float(latest["macd_signal"]) else "BEARISH"
        
        # ── SL AND TP ─────────────────────────────────
        sl_distance = current_atr * 1.5
        
        if direction == "BUY":
            sl = min(current_close - sl_distance, swing_low)
            sl = max(sl, current_close - current_atr * 2.0)
            tp = current_close + (current_close - sl) * 1.5
        else:
            sl = max(current_close + sl_distance, swing_high)
            sl = min(sl, current_close + current_atr * 2.0)
            tp = current_close - (sl - current_close) * 1.5
        
        # ── PIP CALCULATION ───────────────────────────
        if "JPY" in pair:
            pip_size = 0.01
            decimals = 3
        elif "XAU" in pair:
            pip_size = 0.1
            decimals = 2
        else:
            pip_size = 0.0001
            decimals = 5
        
        sl_pips = abs(current_close - sl) / pip_size
        tp_pips = abs(current_close - tp) / pip_size
        
        # Add round number info to signal if relevant
        rn_note = ""
        if rn_level and rn_result != "NEUTRAL":
            rn_note = (
                f"🔢 Round Level: {round(rn_level, decimals)} "
                f"({'Support' if rn_result == 'NEAR_SUPPORT' else 'Resistance'})\n"
            )
        
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        
        return {
            "pair":        pair,
            "direction":   direction,
            "strength":    strength,
            "score":       abs_score,
            "entry":       round(current_close, decimals),
            "stop_loss":   round(sl, decimals),
            "take_profit": round(tp, decimals),
            "sl_pips":     round(sl_pips, 1),
            "tp_pips":     round(tp_pips, 1),
            "rr_ratio":    "1:1.5",
            "rsi":         round(current_rsi, 1),
            "h1_trend":    h1_trend,
            "h4_bias":     h4_bias,
            "macd_signal": macd_label,
            "rn_note":     rn_note,
            "atr":         round(current_atr, 5),
            "timestamp":   timestamp,
            "error":       False
        }
        
    except Exception as e:
        logger.exception(f"Strategy error for {pair}: {e}")
        return {
            "error": True,
            "message": f"Analysis failed: {str(e)}"
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
        
        if m5_data is None or len(m5_data) < 20:
            logger.error(f"Not enough M5 data for {pair}")
            return {
                "pair": pair.replace("=X", ""),
                "error": True,
                "message": f"Could not fetch market data for {pair}. Market may be closed."
            }
            
        if h1_data is None or len(h1_data) < 10:
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