import logging
from typing import Optional
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

PAIR_MAP = {
    "USDJPY": "USDJPY=X",
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "XAUUSD": "GC=F",      # Gold futures on Yahoo Finance
    "USDCAD": "USDCAD=X",
    "EURJPY": "EURJPY=X",
    "GBPJPY": "GBPJPY=X"
}


def _clean_df(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Flatten columns, lowercase names, drop NaN, keep only positive closes."""
    if df is None or df.empty:
        return None

    # Flatten MultiIndex columns sometimes returned by yfinance
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df.columns = [str(c).lower().strip() for c in df.columns]
    df = df.dropna(subset=["close"])
    df = df[df["close"] > 0]
    return df


def get_candles(pair: str, interval: str, period: str):
    """
    Fetch OHLCV data from Yahoo Finance for a given pair.

    Args:
        pair:     e.g. "EURUSD", "USDJPY", "XAUUSD"
        interval: Yahoo interval string, e.g. "5m", "1h", "4h"
        period:   Yahoo period string, e.g. "5d", "10d", "60d"

    Returns:
        pd.DataFrame or None
    """
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
        df = _clean_df(df)
        if df is None or df.empty:
            logger.warning(f"Empty data for {pair} {interval}")
            return None
        logger.info(f"Got {len(df)} candles for {pair} {interval}")
        return df
    except Exception as e:
        logger.exception(f"yfinance error {pair} {interval}: {e}")
        return None


def get_m5_candles(pair: str):
    """Fetch M5 candles with fallback."""
    df = get_candles(pair, "5m", "5d")
    if df is None or len(df) < 50:
        logger.warning(f"Trying 2d fallback for {pair} M5")
        df = get_candles(pair, "5m", "2d")
    return df


def get_h1_candles(pair: str):
    """Fetch H1 candles with fallback."""
    df = get_candles(pair, "1h", "30d")
    if df is None or len(df) < 21:
        logger.warning(f"Trying 7d fallback for {pair} H1")
        df = get_candles(pair, "1h", "7d")
    return df


def get_h4_candles(pair: str):
    """Fetch H4 candles with fallback."""
    df = get_candles(pair, "4h", "60d")
    if df is None or len(df) < 21:
        logger.warning(f"Trying 30d fallback for {pair} H4")
        df = get_candles(pair, "4h", "30d")
    return df


def get_latest_price(pair: str) -> Optional[float]:
    """Return the latest closing price for a pair (helper for monitors)."""
    df = get_candles(pair, "5m", "1d")
    if df is not None and not df.empty:
        return float(df["close"].iloc[-1])
    return None
