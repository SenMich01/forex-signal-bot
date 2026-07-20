"""
Forex Signal Bot - Multi-Timeframe Confluence Pullback Strategy.

Designed for high-probability 5-minute and 1-hour swing trades.

Core concept:
- Trade in the direction of the higher timeframe (HTF) trend.
- Enter on pullbacks to a key EMA (21 / 50) on the signal timeframe.
- Require momentum resumption (RSI + MACD) and candle confirmation.
- Use ATR-based stop loss and a fixed risk/reward target.

Timeframes:
- M5 signal : HTF = H1,   signal TF = M5
- H1 signal : HTF = H4,   signal TF = H1

The strategy deliberately does NOT always return a signal. It only returns
a signal when enough confluence factors align, which helps keep the win-rate
high and avoids low-quality chop entries.
"""

import pandas as pd
import numpy as np
import logging
from datetime import datetime, timezone
from typing import Dict, Optional

from config import (
    EMA_PERIODS, RSI_PERIOD, ATR_PERIOD, ATR_MULTIPLIERS,
    ADX_PERIOD, ADX_THRESHOLD, is_trading_session, get_pair_name
)
from data_fetcher import get_candles

logger = logging.getLogger(__name__)


def is_market_open() -> bool:
    """Check if the Forex market is broadly open (not weekend)."""
    now = datetime.now(timezone.utc)
    if now.weekday() == 5:          # Saturday
        return False
    if now.weekday() == 6 and now.hour < 22:  # Sunday before 22:00 UTC
        return False
    return True


def get_pip_size(pair: str) -> float:
    """Return the pip size and display decimals for a given pair."""
    if "JPY" in pair:
        return 0.01, 3
    if "XAU" in pair:
        return 0.10, 2
    return 0.0001, 5


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add EMAs, RSI, MACD, ATR and candle-body columns to a DataFrame."""
    df = df.copy()

    # EMAs
    df["ema8"]  = df["close"].ewm(span=8,  adjust=False).mean()
    df["ema21"] = df["close"].ewm(span=21, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()

    # RSI(14)
    delta = df["close"].diff()
    gain  = delta.clip(lower=0)
    loss  = -delta.clip(upper=0)
    avg_gain = gain.ewm(span=RSI_PERIOD, adjust=False).mean()
    avg_loss = loss.ewm(span=RSI_PERIOD, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 0.0001)
    df["rsi"] = 100 - (100 / (1 + rs))

    # MACD
    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    df["macd"]        = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()

    # ATR(14)
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"]  - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    df["atr"] = tr.ewm(span=ATR_PERIOD, adjust=False).mean()

    # ADX(14) / +DI / -DI — Wilder-style smoothing (alpha = 1/period),
    # used as a regime filter so we only trade pullbacks in a market that's
    # actually trending, not just one where a fast/slow EMA happen to cross.
    up_move   = df["high"].diff()
    down_move = -df["low"].diff()
    plus_dm  = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    alpha = 1 / ADX_PERIOD
    tr_smooth    = tr.ewm(alpha=alpha, adjust=False).mean()
    plus_dm_sm   = pd.Series(plus_dm, index=df.index).ewm(alpha=alpha, adjust=False).mean()
    minus_dm_sm  = pd.Series(minus_dm, index=df.index).ewm(alpha=alpha, adjust=False).mean()

    plus_di  = 100 * (plus_dm_sm  / tr_smooth.replace(0, 0.0001))
    minus_di = 100 * (minus_dm_sm / tr_smooth.replace(0, 0.0001))
    di_sum   = (plus_di + minus_di).replace(0, 0.0001)
    dx       = 100 * (plus_di - minus_di).abs() / di_sum

    df["plus_di"]  = plus_di
    df["minus_di"] = minus_di
    df["adx"]      = dx.ewm(alpha=alpha, adjust=False).mean()

    # Candle body / range
    df["body"]     = (df["close"] - df["open"]).abs()
    df["range"]    = df["high"] - df["low"]
    df["bull"]     = df["close"] > df["open"]
    df["bear"]     = df["close"] < df["open"]

    return df


def _require_min_candles(df: Optional[pd.DataFrame], min_candles: int) -> bool:
    return df is not None and not df.empty and len(df) >= min_candles


def check_round_numbers(price: float, atr: float, pair: str):
    """Check if price is near a psychological round number level."""
    if "JPY" in pair:
        intervals = [0.50, 1.0, 5.0, 10.0]
    elif "XAU" in pair:
        intervals = [5.0, 10.0, 25.0, 50.0, 100.0]
    else:
        intervals = [0.00500, 0.01000, 0.05000, 0.10000]

    proximity = atr * 1.5
    for interval in intervals:
        nearest = round(price / interval) * interval
        distance = abs(price - nearest)
        if distance <= proximity:
            if price >= nearest:
                return "NEAR_SUPPORT", nearest
            return "NEAR_RESISTANCE", nearest
    return "NEUTRAL", None


def get_signal(pair: str, timeframe: str = "M5") -> Dict:
    """
    Generate a high-probability pullback signal for a given pair and timeframe.

    Args:
        pair:      e.g. "EURUSD", "USDJPY", "XAUUSD"
        timeframe: "M5" or "H1"

    Returns:
        Dict with signal details, or {"error": True, "message": ...} on failure.
        If no confluence is found, returns {"signal": False, "message": ...}.
    """
    try:
        pair = pair.upper()
        timeframe = timeframe.upper()

        if timeframe not in ("M5", "H1"):
            return {"error": True, "message": "Timeframe must be M5 or H1."}

        logger.info(f"Analyzing {pair} on {timeframe}")

        # --- Fetch data ---
        if timeframe == "M5":
            htf = get_candles(pair, "1h", "10d")   # higher timeframe
            sig = get_candles(pair, "5m", "5d")    # signal timeframe
        else:  # H1
            htf = get_candles(pair, "4h", "60d")
            sig = get_candles(pair, "1h", "30d")

        if not _require_min_candles(htf, 50):
            return {"error": True, "message": f"Not enough HTF data for {pair}."}
        if not _require_min_candles(sig, 50):
            return {"error": True, "message": f"Not enough {timeframe} data for {pair}."}

        # Standardise columns
        for df in (htf, sig):
            df.columns = [str(c).lower().strip() for c in df.columns]

        # Add indicators
        htf = add_indicators(htf)
        sig = add_indicators(sig)

        # Drop incomplete rows
        sig = sig.dropna(subset=["close", "high", "low", "open", "atr", "rsi", "adx"])
        htf = htf.dropna(subset=["close", "ema21", "ema50"])
        if len(sig) < 10 or len(htf) < 10:
            return {"error": True, "message": f"Insufficient clean data for {pair}."}

        # --- Latest values ---
        htf_last = htf.iloc[-1]
        s_last   = sig.iloc[-1]
        s_prev   = sig.iloc[-2]
        s_prev2  = sig.iloc[-3]

        htf_close = float(htf_last["close"])
        htf_ema21 = float(htf_last["ema21"])
        htf_ema50 = float(htf_last["ema50"])

        close = float(s_last["close"])
        atr   = float(s_last["atr"])
        rsi   = float(s_last["rsi"])
        rsi_prev = float(s_prev["rsi"])
        rsi_prev2 = float(s_prev2["rsi"])
        adx   = float(s_last["adx"])

        ema8  = float(s_last["ema8"])
        ema21 = float(s_last["ema21"])
        ema50 = float(s_last["ema50"])

        macd       = float(s_last["macd"])
        macd_sig   = float(s_last["macd_signal"])
        macd_prev  = float(s_prev["macd"])
        macds_prev = float(s_prev["macd_signal"])

        # Look-back window for pullback detection
        recent_low  = float(sig["low"].iloc[-5:].min())
        recent_high = float(sig["high"].iloc[-5:].max())
        swing_low   = float(sig["low"].iloc[-20:].min())
        swing_high  = float(sig["high"].iloc[-20:].max())

        pip_size, decimals = get_pip_size(pair)

        # --- CONFLUENCE SCORING ---
        score = 0
        reasons = []

        # 1. HTF trend (max +/- 35)
        htf_bull = htf_ema21 > htf_ema50 and htf_close > htf_ema21
        htf_bear = htf_ema21 < htf_ema50 and htf_close < htf_ema21

        if htf_bull:
            score += 35
            reasons.append("HTF trend bullish")
        elif htf_bear:
            score -= 35
            reasons.append("HTF trend bearish")
        else:
            return {"signal": False, "message": f"{pair}: No clear HTF trend. Skip."}

        # 1b. ADX regime filter — reject weak/choppy conditions outright.
        # This is the piece that was missing before: EMA21 vs EMA50 can
        # flip "bullish" in a market that's barely trending at all, and a
        # pullback in that kind of chop is far more likely to just stop out.
        if adx < ADX_THRESHOLD:
            return {
                "signal": False,
                "message": f"{pair}: ADX {adx:.1f} below {ADX_THRESHOLD} — market not trending. Skip."
            }

        # 2. Pullback to EMA21 / EMA50 (max +/- 25)
        pullback_buffer = atr * 0.5
        bull_pullback = (
            recent_low <= ema21 + pullback_buffer and
            close > ema21 and
            close > ema50
        )
        bear_pullback = (
            recent_high >= ema21 - pullback_buffer and
            close < ema21 and
            close < ema50
        )

        if bull_pullback and htf_bull:
            score += 25
            reasons.append("bullish EMA21 pullback")
        elif bear_pullback and htf_bear:
            score -= 25
            reasons.append("bearish EMA21 pullback")
        else:
            return {"signal": False, "message": f"{pair}: No valid pullback to EMA21. Skip."}

        # 3. RSI momentum resumption (max +/- 20)
        rsi_buy  = (35 <= rsi <= 60) and rsi > rsi_prev
        rsi_sell = (40 <= rsi <= 65) and rsi < rsi_prev

        if rsi_buy and htf_bull:
            score += 20
            reasons.append("RSI momentum rising")
        elif rsi_sell and htf_bear:
            score -= 20
            reasons.append("RSI momentum falling")
        else:
            return {"signal": False, "message": f"{pair}: RSI momentum not aligned. Skip."}

        # 4. MACD alignment (max +/- 20)
        macd_bull = macd > macd_sig and macd_prev <= macds_prev
        macd_bear = macd < macd_sig and macd_prev >= macds_prev
        macd_aligned_bull = macd > macd_sig
        macd_aligned_bear = macd < macd_sig

        if macd_bull and htf_bull:
            score += 20
            reasons.append("MACD bullish crossover")
        elif macd_bear and htf_bear:
            score -= 20
            reasons.append("MACD bearish crossover")
        elif macd_aligned_bull and htf_bull:
            score += 10
            reasons.append("MACD bullish aligned")
        elif macd_aligned_bear and htf_bear:
            score -= 10
            reasons.append("MACD bearish aligned")
        else:
            return {"signal": False, "message": f"{pair}: MACD not aligned. Skip."}

        # 5. Candle confirmation (max +/- 15)
        body = float(s_last["body"])
        rng  = float(s_last["range"])
        strong_body = rng > 0 and body / rng > 0.55

        if strong_body and s_last["bull"] and htf_bull:
            score += 15
            reasons.append("strong bullish candle")
        elif strong_body and s_last["bear"] and htf_bear:
            score -= 15
            reasons.append("strong bearish candle")
        else:
            return {"signal": False, "message": f"{pair}: No confirming candle. Skip."}

        # 6. Round-number confluence (max +/- 10)
        rn_result, rn_level = check_round_numbers(close, atr, pair)
        if htf_bull and rn_result == "NEAR_SUPPORT":
            score += 10
            reasons.append("round-number support")
        elif htf_bear and rn_result == "NEAR_RESISTANCE":
            score -= 10
            reasons.append("round-number resistance")

        # --- Direction & strength ---
        direction = "BUY" if score > 0 else "SELL"
        abs_score = abs(score)

        if abs_score >= 75:
            strength = "STRONG"
        elif abs_score >= 45:
            strength = "MODERATE"
        else:
            return {
                "signal": False,
                "message": f"{pair}: Confluence too weak ({abs_score}/100). Skip."
            }

        # --- SL / TP ---
        sl_distance = atr * ATR_MULTIPLIERS["SL"]

        if direction == "BUY":
            sl = min(close - sl_distance, swing_low)
            sl = max(sl, close - atr * 2.0)   # cap SL distance
            tp = close + (close - sl) * ATR_MULTIPLIERS["TP_BUY"]
        else:
            sl = max(close + sl_distance, swing_high)
            sl = min(sl, close + atr * 2.0)
            tp = close - (sl - close) * ATR_MULTIPLIERS["TP"]

        sl_pips = abs(close - sl) / pip_size
        tp_pips = abs(close - tp) / pip_size
        rr = tp_pips / sl_pips if sl_pips > 0 else 0

        # Notes
        rn_note = ""
        if rn_level and rn_result != "NEUTRAL":
            label = "Support" if rn_result == "NEAR_SUPPORT" else "Resistance"
            rn_note = f"🔢 Round Level: {round(rn_level, decimals)} ({label})\n"

        htf_trend = "BULLISH" if htf_bull else "BEARISH"
        macd_label = "BULLISH" if macd > macd_sig else "BEARISH"
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        return {
            "pair":        pair,
            "timeframe":   timeframe,
            "direction":   direction,
            "strength":    strength,
            "score":       abs_score,
            "entry":       round(close, decimals),
            "stop_loss":   round(sl, decimals),
            "take_profit": round(tp, decimals),
            "sl_pips":     round(sl_pips, 1),
            "tp_pips":     round(tp_pips, 1),
            "rr_ratio":    f"1:{rr:.1f}" if rr > 0 else "1:1.5",
            "rsi":         round(rsi, 1),
            "adx":         round(adx, 1),
            "htf_trend":   htf_trend,
            "macd_signal": macd_label,
            "rn_note":     rn_note,
            "atr":         round(atr, 5),
            "reasons":     " | ".join(reasons),
            "timestamp":   timestamp,
            "signal":      True,
            "error":       False
        }

    except Exception as e:
        logger.exception(f"Strategy error for {pair}: {e}")
        return {"error": True, "message": f"Analysis failed: {str(e)}"}


def scan_all_pairs(timeframe: str = "M5") -> list:
    """Scan all configured pairs and return only valid signals."""
    from config import FOREX_PAIRS

    results = []
    for raw in FOREX_PAIRS:
        pair = raw.replace("=X", "")
        sig = get_signal(pair, timeframe)
        if sig.get("signal"):
            results.append(sig)
    return results
