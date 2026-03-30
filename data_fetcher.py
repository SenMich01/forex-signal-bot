import logging
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

PAIR_MAP = {
    "USDJPY": "USDJPY=X",
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "XAUUSD": "GC=F",
    "USDCAD": "USDCAD=X",
    "EURJPY": "EURJPY=X",
    "GBPJPY": "GBPJPY=X"
}

def clean_df(df):
    """Flatten columns, lowercase, drop NaN."""
    if df is None or df.empty:
        return None
    # Flatten MultiIndex columns yfinance sometimes returns
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(c).lower().strip() for c in df.columns]
    df = df.dropna(subset=["close"])
    df = df[df["close"] > 0]
    return df

def get_candles(pair, interval, period):
    ticker = PAIR_MAP.get(pair.upper())
    if not ticker:
        logger.error(f"Unknown pair: {pair}")
        return None
    try:
        logger.info(f"Fetching {pair} ({ticker}) {interval} {period}")
        df = yf.download(
            ticker,
            interval=interval,
            period=period,
            auto_adjust=True,
            progress=False,
            threads=False
        )
        df = clean_df(df)
        if df is None or df.empty:
            logger.error(f"Empty data for {pair}")
            return None
        logger.info(f"Got {len(df)} candles for {pair} {interval}")
        return df
    except Exception as e:
        logger.exception(f"yfinance error {pair} {interval}: {e}")
        return None

def get_m5_candles(pair):
    # Try 5d first, fall back to 2d
    df = get_candles(pair, "5m", "5d")
    if df is None or len(df) < 50:
        logger.warning(f"Trying 2d fallback for {pair} M5")
        df = get_candles(pair, "5m", "2d")
    return df

def get_h1_candles(pair):
    # Try 30d first, fall back to 7d
    df = get_candles(pair, "1h", "30d")
    if df is None or len(df) < 21:
        logger.warning(f"Trying 7d fallback for {pair} H1")
        df = get_candles(pair, "1h", "7d")
    return df