from datetime import datetime, timezone
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Indicator Calculations
# ---------------------------------------------------------------------------
def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """Calculate Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calculate Relative Strength Index."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def calculate_macd(
    series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
):
    """Calculate MACD Line and Signal Line."""
    ema_fast = calculate_ema(series, fast)
    ema_slow = calculate_ema(series, slow)
    macd_line = ema_fast - ema_slow
    macd_signal = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, macd_signal


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Average True Range."""
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - df["close"].shift(1)).abs()
    tr3 = (df["low"] - df["close"].shift(1)).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


# ---------------------------------------------------------------------------
# Market Status Check
# ---------------------------------------------------------------------------
def is_market_open(symbol: str = "EURUSD") -> bool:
    """Checks if the Forex or Crypto market is currently open.

    Forex markets are open Sunday 22:00 UTC to Friday 22:00 UTC. Crypto pairs
    (e.g., BTCUSD) are open 24/7.
    """
    symbol_upper = symbol.upper()

    # Crypto trades 24/7
    if any(crypto in symbol_upper for crypto in ["BTC", "ETH", "XRP", "SOL"]):
        return True

    # Forex / Metals schedule (UTC)
    now_utc = datetime.now(timezone.utc)
    weekday = now_utc.weekday()  # 0=Monday, 4=Friday, 5=Saturday, 6=Sunday
    hour = now_utc.hour

    # Closed all day Saturday
    if weekday == 5:
        return False

    # Closed Sunday before 22:00 UTC
    if weekday == 6 and hour < 22:
        return False

    # Closed Friday after 22:00 UTC
    if weekday == 4 and hour >= 22:
        return False

    return True


# ---------------------------------------------------------------------------
# Core Strategy Logic
# ---------------------------------------------------------------------------
def get_signal(
    df: pd.DataFrame,
    df_htf: pd.DataFrame = None,
    symbol: str = "UNKNOWN",
    timeframe: str = "M5",
    min_strength: str = "MODERATE",
    sl_atr_mult: float = 1.0,
    tp_atr_mult_buy: float = 2.0,
    tp_atr_mult_sell: float = 1.5,
) -> dict:
    """Evaluates market data against the Confluence Pullback Strategy rules.

    Returns a signal dictionary structured for bot formatting.
    """
    if df is None or len(df) < 50:
        return {
            "symbol": symbol,
            "pair": symbol,
            "timeframe": timeframe,
            "signal": "NONE",
            "strength": "NONE",
            "score": 0,
            "close": None,
            "sl": None,
            "tp": None,
            "reason": "Insufficient data",
        }

    # 1. Base Indicators Calculation
    df = df.copy()
    df["ema21"] = calculate_ema(df["close"], 21)
    df["ema50"] = calculate_ema(df["close"], 50)
    df["rsi"] = calculate_rsi(df["close"], 14)
    df["macd_line"], df["macd_signal"] = calculate_macd(df["close"])
    df["atr"] = calculate_atr(df, 14)

    curr = df.iloc[-1]
    prev1 = df.iloc[-2]
    prev2 = df.iloc[-3]

    # Lookback swings
    recent_low_8 = df["low"].tail(8).min()
    recent_high_8 = df["high"].tail(8).max()
    swing_low_20 = df["low"].tail(20).min()
    swing_high_20 = df["high"].tail(20).max()

    # Candle analysis
    body = abs(curr["close"] - curr["open"])
    rng = curr["high"] - curr["low"]
    strong_body = (rng > 0) and ((body / rng) >= 0.50)
    is_bull_candle = curr["close"] > curr["open"]
    is_bear_candle = curr["close"] < curr["open"]

    # 2. HTF (Higher Timeframe) Gate Check
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
        htf_bull = (curr["ema21"] > curr["ema50"]) and (
            curr["close"] > curr["ema21"]
        )
        htf_bear = (curr["ema21"] < curr["ema50"]) and (
            curr["close"] < curr["ema21"]
        )

    # 3. Pullback Conditions
    pullback_buffer = curr["atr"] * 0.6
    bull_pullback = (recent_low_8 <= curr["ema21"] + pullback_buffer) and (
        curr["close"] > curr["ema21"]
    )
    bear_pullback = (recent_high_8 >= curr["ema21"] - pullback_buffer) and (
        curr["close"] < curr["ema21"]
    )

    # 4. RSI Momentum Checks
    rsi_buy_strict = (
        (35 <= curr["rsi"] <= 65)
        and (curr["rsi"] > prev1["rsi"])
        and (prev1["rsi"] > prev2["rsi"])
    )
    rsi_buy_flex = (35 <= curr["rsi"] <= 65) and (curr["rsi"] > prev1["rsi"])

    rsi_sell_strict = (
        (35 <= curr["rsi"] <= 65)
        and (curr["rsi"] < prev1["rsi"])
        and (prev1["rsi"] < prev2["rsi"])
    )
    rsi_sell_flex = (35 <= curr["rsi"] <= 65) and (curr["rsi"] < prev1["rsi"])

    # 5. MACD Alignment
    macd_aligned_bull = curr["macd_line"] > curr["macd_signal"]
    macd_aligned_bear = curr["macd_line"] < curr["macd_signal"]

    # 6. Scoring Matrix
    buy_score = 0
    sell_score = 0

    if htf_bull:
        buy_score += 30
    if bull_pullback:
        buy_score += 25
    if rsi_buy_strict:
        buy_score += 20
    elif rsi_buy_flex:
        buy_score += 10
    if macd_aligned_bull:
        buy_score += 15
    if strong_body and is_bull_candle:
        buy_score += 10

    if htf_bear:
        sell_score += 30
    if bear_pullback:
        sell_score += 25
    if rsi_sell_strict:
        sell_score += 20
    elif rsi_sell_flex:
        sell_score += 10
    if macd_aligned_bear:
        sell_score += 15
    if strong_body and is_bear_candle:
        sell_score += 10

    # Determine Signal & Strength
    signal = "NONE"
    strength = "NONE"
    final_score = 0

    if buy_score >= 75:
        signal = "BUY"
        strength = "STRONG"
        final_score = buy_score
    elif buy_score >= 55 and min_strength == "MODERATE":
        signal = "BUY"
        strength = "MODERATE"
        final_score = buy_score

    elif sell_score >= 75:
        signal = "SELL"
        strength = "STRONG"
        final_score = sell_score
    elif sell_score >= 55 and min_strength == "MODERATE":
        signal = "SELL"
        strength = "MODERATE"
        final_score = sell_score

    # 7. Calculate SL / TP
    stop_loss = None
    take_profit = None

    if signal == "BUY":
        sl_dist = curr["atr"] * sl_atr_mult
        stop_loss = max(
            min(curr["close"] - sl_dist, swing_low_20),
            curr["close"] - (curr["atr"] * 2.0),
        )
        take_profit = curr["close"] + (
            (curr["close"] - stop_loss) * tp_atr_mult_buy
        )

    elif signal == "SELL":
        sl_dist = curr["atr"] * sl_atr_mult
        stop_loss = min(
            max(curr["close"] + sl_dist, swing_high_20),
            curr["close"] + (curr["atr"] * 2.0),
        )
        take_profit = curr["close"] - (
            (stop_loss - curr["close"]) * tp_atr_mult_sell
        )

    return {
        "symbol": symbol,
        "pair": symbol,  # Keeps backward compatibility with bot.py formatting
        "timeframe": timeframe,
        "signal": signal,
        "strength": strength,
        "score": final_score,
        "close": round(curr["close"], 5),
        "sl": round(stop_loss, 5) if stop_loss else None,
        "tp": round(take_profit, 5) if take_profit else None,
        "rsi": round(curr["rsi"], 2),
        "atr": round(curr["atr"], 5),
    }
