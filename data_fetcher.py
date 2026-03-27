"""
Data fetching module using yfinance for Forex market data.

Handles fetching M5 and H1 candle data for all monitored pairs.
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

from config import DATA_CONFIG, FOREX_PAIRS

logger = logging.getLogger(__name__)

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
        config_key = timeframe.upper()
        if config_key not in DATA_CONFIG:
            logger.error(f"Unknown timeframe: {timeframe}")
            return None
        
        config = DATA_CONFIG[config_key]
        
        try:
            # Create cache key
            cache_key = f"{pair}_{timeframe}"
            
            # Check if we have recent data in cache
            if cache_key in self.cache:
                last_fetch = self.last_fetch_time.get(cache_key, datetime.min)
                # Refresh cache if older than 1 minute
                if datetime.now() - last_fetch < timedelta(minutes=1):
                    return self.cache[cache_key]
            
            logger.info(f"Fetching {timeframe} data for {pair}")
            
            # Fetch data from yfinance
            ticker = yf.Ticker(pair)
            data = ticker.history(
                interval=config["interval"],
                period=config["period"]
            )
            
            if data.empty:
                logger.warning(f"No data returned for {pair}")
                return None
            
            # Validate minimum candles requirement
            if len(data) < config["candles_required"]:
                logger.warning(f"Insufficient data for {pair}: {len(data)} candles (need {config['candles_required']})")
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
        # Reset index to make datetime a column
        data = data.reset_index()
        
        # Rename columns to standard format
        data = data.rename(columns={
            'Datetime': 'timestamp' if timeframe == "M5" else 'timestamp',
            'Date': 'timestamp' if timeframe == "H1" else 'timestamp',
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume'
        })
        
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