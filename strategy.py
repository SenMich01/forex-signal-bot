import numpy as np
import pandas as pd


def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """Calculate Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calculate Relative Strength Index."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    # Fallback to avoid division by zero or NaN issues
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def calculate_macd(
    series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
):
    """Calculate MACD line and Signal line."""
    ema_fast = calculate_ema(series, fast)
    ema_slow = calculate_ema(series, slow)
    macd_line = ema_fast - ema_slow
    macd_signal = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, macd_signal


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Average True Range."""
    high = df["high"]
    low = df["low"]
    close = df["close"]

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


def get_signal(
    df: pd.DataFrame,
    df_htf: pd.DataFrame = None,
    mode: str = "M5 (HTF=H1)",
    min_strength: str = "MODERATE",
    sl_atr_mult: float = 1.0,
    tp_atr_mult_buy: float = 2.0,
    tp_atr_mult_sell: float = 1.5,
) -> dict:
    """Evaluates market data against the Confluence Pullback Strategy rules.

    Returns a signal dictionary structured for the bot.
    """
    if df is None or len(df) < 50:
        return {"signal": "NONE", "reason": "Insufficient data"}

    # 1. Base Timeframe Indicators
    df = df.copy()
    df["ema21"] = calculate_ema(df["close"], 21)
    df["ema50"] = calculate_ema(df["close"], 50)
    df["rsi"] = calculate_rsi(df["close"], 14)
    df["macd_line"], df["macd_signal"] = calculate_macd(df["close"], 12, 26, 9)
    df["atr"] = calculate_atr(df, 14)

    curr = df.iloc[-1]
    prev1 = df.iloc[-2]
    prev2 = df.iloc[-3]

    # Recent Highs/Lows
    recent_low_5 = df["low"].tail(5).min()
    recent_high_5 = df["high"].tail(5).max()
    swing_low_20 = df["low"].tail(20).min()
    swing_high_20 = df["high"].tail(20).max()

    # Candle Analysis
    body = abs(curr["close"] - curr["open"])
    rng = curr["high"] - curr["low"]
    strong_body = (rng > 0) and ((body / rng) > 0.55)
    is_bull_candle = curr["close"] > curr["open"]
    is_bear_candle = curr["close"] < curr["open"]

    # 2. HTF (Higher Timeframe) Gate Check
    htf_bull = False
    htf_bear = False

    if df_htf is not None and len(df_htf) >= 50:
        df_htf = df_htf.copy()
        df_htf["htf_ema21"] = calculate_ema(df_htf["close"], 21)
        df_htf["htf_ema50"] = calculate_ema(df_htf["close"], 50)
        htf_curr = df_htf.iloc[-1]

        htf_bull = (htf_curr["htf_ema21"] > htf_curr["htf_ema50"]) and (
            htf_curr["close"] > htf_curr["htf_ema21"]
        )
        htf_bear = (htf_curr["htf_ema21"] < htf_curr["htf_ema50"]) and (
            htf_curr["close"] < htf_curr["htf_ema21"]
        )
    else:
        # Fallback to current chart HTF approximation if HTF dataframe isn't provided
        htf_bull = (curr["ema21"] > curr["ema50"]) and (
            curr["close"] > curr["ema21"]
        )
        htf_bear = (curr["ema21"] < curr["ema50"]) and (
            curr["close"] < curr["ema21"]
        )

    # 3. Pullback Conditions
    pullback_buffer = curr["atr"] * 0.5
    bull_pullback = (
        (recent_low_5 <= curr["ema21"] + pullback_buffer)
        and (curr["close"] > curr["ema21"])
        and (curr["close"] > curr["ema50"])
    )
    bear_pullback = (
        (recent_high_5 >= curr["ema21"] - pullback_buffer)
        and (curr["close"] < curr["ema21"])
        and (curr["close"] < curr["ema50"])
    )

    # 4. RSI Momentum Resumption (3-bar sequence)
    rsi_buy = (
        (curr["rsi"] >= 35)
        and (curr["rsi"] <= 60)
        and (curr["rsi"] > prev1["rsi"])
        and (prev1["rsi"] > prev2["rsi"])
    )
    rsi_sell = (
        (curr["rsi"] >= 40)
        and (curr["rsi"] <= 65)
        and (curr["rsi"] < prev1["rsi"])
        and (prev1["rsi"] < prev2["rsi"])
    )

    # 5. MACD Alignment / Cross
    macd_bull_cross = (curr["macd_line"] > curr["macd_signal"]) and (
        prev1["macd_line"] <= prev1["macd_signal"]
    )
    macd_bear_cross = (curr["macd_line"] < curr["macd_signal"]) and (
        prev1["macd_line"] >= prev1["macd_signal"]
    )

    macd_aligned_bull = curr["macd_line"] > curr["macd_signal"]
    macd_aligned_bear = curr["macd_line"] < curr["macd_signal"]

    # Confluence Signal Gate Checks
    long_setup = (
        htf_bull
        and bull_pullback
        and rsi_buy
        and (macd_bull_cross or macd_aligned_bull)
        and strong_body
        and is_bull_candle
    )

    short_setup = (
        htf_bear
        and bear_pullback
        and rsi_sell
        and (macd_bear_cross or macd_aligned_bear)
        and strong_body
        and is_bear_candle
    )

    # 6. Scoring Logic
    score = 0.0
    if long_setup:
        score += 35  # HTF
        score += 25  # Pullback
        score += 20  # RSI
        score += 20 if macd_bull_cross else 10  # MACD
        score += 15  # Candle
    elif short_setup:
        score -= 35
        score -= 25
        score -= 20
        score -= 20 if macd_bear_cross else 10
        score -= 15

    abs_score = abs(score)

    if abs_score >= 75:
        strength = "STRONG"
    elif abs_score >= 45:
        strength = "MODERATE"
    else:
        strength = "NONE"

    # Strength threshold check
    strength_ok = False
    if min_strength == "MODERATE":
        strength_ok = strength in ["MODERATE", "STRONG"]
    elif min_strength == "STRONG":
        strength_ok = strength == "STRONG"

    # 7. Final Signal & Target Determination
    if long_setup and strength_ok:
        signal = "BUY"
        sl_dist = curr["atr"] * sl_atr_mult
        stop_loss = min(curr["close"] - sl_dist, swing_low_20)
        stop_loss = max(stop_loss, curr["close"] - (curr["atr"] * 2.0))
        take_profit = curr["close"] + (
            (curr["close"] - stop_loss) * tp_atr_mult_buy
        )

    elif short_setup and strength_ok:
        signal = "SELL"
        sl_dist = curr["atr"] * sl_atr_mult
        stop_loss = max(curr["close"] + sl_dist, swing_high_20)
        stop_loss = min(stop_loss, curr["close"] + (curr["atr"] * 2.0))
        take_profit = curr["close"] - (
            (stop_loss - curr["close"]) * tp_atr_mult_sell
        )

    else:
        signal = "NONE"
        stop_loss = None
        take_profit = None

    return {
        "signal": signal,
        "strength": strength,
        "score": abs_score,
        "close": round(curr["close"], 5),
        "sl": round(stop_loss, 5) if stop_loss else None,
        "tp": round(take_profit, 5) if take_profit else None,
        "rsi": round(curr["rsi"], 2),
        "atr": round(curr["atr"], 5),
    }
