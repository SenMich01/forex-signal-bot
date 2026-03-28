"""
Data fetching module using yfinance for Forex market data.

Handles fetching M5 and H1 candle data for all monitored pairs with proper error handling.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
from typing import Dict, Optional, Tuple
import warnings

# Suppress yfinance warnings
warnings.filterwarnings('ignore', category=UserWarning)

logger = logging.getLogger(__name__)

# Pair ticker mapping
PAIR_TICKER_MAP = {
    "USDJPY": "USDJPY=X",
    "EURUSD": "EURUSD=X", 
    "GBPUSD": "GBPUSD=X",
    "XAUUSD": "GC=F",       # Gold futures - more reliable
    "USDCAD": "USDCAD=X",
    "EURJPY": "EURJPY=X",
    "GBPJPY": "GBPJPY=X"
}

def get_candles(pair, interval="5m", period="2d"):
    """Fetch candles with proper error handling and debug logging."""
    ticker = PAIR_TICKER_MAP.get(pair.upper())
    if not ticker:
        logger.error(f"Unknown pair: {pair}")
        return None
    
    try:
        logger.info(f"Fetching {pair} ({ticker}) interval={interval}")
        df = yf.download(
            ticker,
            interval=interval,
            period=period,
            auto_adjust=True,
            progress=False
        )
        
        if df is None or df.empty:
            logger.error(f"No data returned for {pair}")
            return None
            
        # Flatten MultiIndex columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        # Rename columns to lowercase
        df.columns = [c.lower() for c in df.columns]
        
        # Add timestamp column
        df['timestamp'] = df.index
        df = df.reset_index(drop=True)
        
        logger.info(f"✅ Got {len(df)} candles for {pair}")
        return df
        
    except Exception as e:
        logger.error(f"❌ yfinance error for {pair}: {e}")
        return None

def get_m5_candles(pair):
    """Get M5 candles for a pair."""
    return get_candles(pair, interval="5m", period="2d")

def get_h1_candles(pair):
    """Get H1 candles for a pair."""
    return get_candles(pair, interval="1h", period="7d")

class DataFetcher:
    """Handles fetching and preprocessing of Forex market data."""
    
    def __init__(self):
        self.cache = {}
        self.last_fetch_time = {}
    
    def fetch_data(self, pair: str, timeframe: str = "M5") -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV data for a specific pair and timeframe.
        
        Args:
            pair: Forex pair symbol (e.g., "EURUSD=X")
            timeframe: "M5" for 5-minute or "H1" for 1-hour
            
        Returns:
            DataFrame with OHLCV data or None if fetch failed
        """
        try:
            # Get the correct ticker
            ticker = PAIR_TICKER_MAP.get(pair.upper())
            if not ticker:
                logger.error(f"Unknown pair: {pair}")
                return None
            
            # Determine interval and period based on timeframe
            if timeframe.upper() == "M5":
                interval = "5m"
                period = "2d"
            elif timeframe.upper() == "H1":
                interval = "1h"
                period = "7d"
            else:
                logger.error(f"Unknown timeframe: {timeframe}")
                return None
            
            # Create cache key
            cache_key = f"{pair}_{timeframe}"
            
            # Check if we have recent data in cache
            if cache_key in self.cache:
                last_fetch = self.last_fetch_time.get(cache_key, datetime.min)
                # Refresh cache if older than 1 minute
                if datetime.now() - last_fetch < timedelta(minutes=1):
                    return self.cache[cache_key]
            
            logger.info(f"Fetching {timeframe} data for {pair} ({ticker})")
            
            # Fetch data using our improved function
            data = get_candles(pair, interval, period)
            
            if data is None or data.empty:
                logger.warning(f"No data returned for {pair}")
                return None
            
            # Validate minimum data requirement
            if len(data) < 50:  # Minimum 50 candles required
                logger.warning(f"Insufficient data for {pair}: {len(data)} candles (need 50)")
                return None
            
            # Preprocess data
            processed_data = self._preprocess_data(data, timeframe)
            
            # Cache the result
            self.cache[cache_key] = processed_data
            self.last_fetch_time[cache_key] = datetime.now()
            
            logger.info(f"Successfully fetched {len(processed_data)} {timeframe} candles for {pair}")
            return processed_data
            
        except Exception as e:
            logger.error(f"Error fetching data for {pair}: {str(e)}")
            return None
    
    def _preprocess_data(self, data: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        """
        Preprocess raw yfinance data for indicator calculations.
        
        Args:
            data: Raw DataFrame from yfinance
            timeframe: Timeframe identifier
            
        Returns:
            Preprocessed DataFrame with required columns
        """
        # Ensure timestamp is datetime
        data['timestamp'] = pd.to_datetime(data['timestamp'])
        
        # Sort by timestamp
        data = data.sort_values('timestamp').reset_index(drop=True)
        
        # Remove any rows with NaN values
        data = data.dropna()
        
        # Add additional calculated columns
        data['range'] = data['high'] - data['low']
        data['body'] = abs(data['close'] - data['open'])
        data['bullish'] = data['close'] > data['open']
        data['bearish'] = data['close'] < data['open']
        
        return data
    
    def fetch_all_pairs(self, timeframe: str = "M5") -> Dict[str, pd.DataFrame]:
        """
        Fetch data for all monitored pairs.
        
        Args:
            timeframe: Timeframe to fetch data for
            
        Returns:
            Dictionary mapping pair symbols to DataFrames
        """
        results = {}
        
        # Import FOREX_PAIRS from config
        from config import FOREX_PAIRS
        
        for pair in FOREX_PAIRS:
            data = self.fetch_data(pair, timeframe)
            if data is not None:
                results[pair] = data
            else:
                logger.warning(f"Failed to fetch data for {pair}")
        
        return results
    
    def get_latest_price(self, pair: str) -> Optional[float]:
        """
        Get the latest closing price for a pair.
        
        Args:
            pair: Forex pair symbol
            
        Returns:
            Latest closing price or None if unavailable
        """
        data = self.fetch_data(pair, "M5")
        if data is not None and len(data) > 0:
            return float(data['close'].iloc[-1])
        return None

# Global data fetcher instance
data_fetcher = DataFetcher()

def get_data(pair: str, timeframe: str = "M5") -> Optional[pd.DataFrame]:
    """Convenience function to get data for a pair."""
    return data_fetcher.fetch_data(pair, timeframe)

def get_latest_price(pair: str) -> Optional[float]:
    """Convenience function to get latest price for a pair."""
    return data_fetcher.get_latest_price(pair)