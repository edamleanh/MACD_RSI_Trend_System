"""
data_fetcher.py
---------------
Responsible for fetching OHLCV data from vnstock for VN30F1M.
"""

import pandas as pd
from vnstock import Vnstock

def fetch_data(symbol: str, source: str, start_date: str,
               end_date: str, interval: str) -> pd.DataFrame:
    """
    Download candle data from vnstock, clean it, and return a standard DataFrame.

    Parameters
    ----------
    symbol      : Ticker, e.g., "VN30F1M"
    source      : Data source, e.g., "VCI" or "TCBS"
    start_date  : Start date "YYYY-MM-DD"
    end_date    : End date "YYYY-MM-DD"
    interval    : Candle timeframe "1m", "15m", "1H", "1D" ...

    Returns
    -------
    pd.DataFrame with DatetimeIndex and columns: Open, High, Low, Close, Volume
    """
    print(f"[*] Fetching {symbol} ({interval}) from {start_date} to {end_date}...")

    stock = Vnstock().stock(symbol=symbol, source=source)
    df = stock.quote.history(start=start_date, end=end_date, interval=interval)

    if df is None or df.empty:
        print("[!] Error: No data received from source.")
        return pd.DataFrame()

    # Drop rows with NaN values (e.g., lunch breaks)
    df = df.dropna()

    # Standardize column names
    df = df.rename(columns={
        "time":   "Datetime",
        "open":   "Open",
        "high":   "High",
        "low":    "Low",
        "close":  "Close",
        "volume": "Volume",
    })

    df["Datetime"] = pd.to_datetime(df["Datetime"])
    df = df.set_index("Datetime").sort_index()

    print(f"[OK] Loaded {len(df):,} candles "
          f"({df.index[0].date()} -> {df.index[-1].date()})")
    return df

def filter_date_range(df: pd.DataFrame,
                      start_date: str,
                      end_date: str) -> pd.DataFrame:
    """Filters DataFrame by date range [start_date, end_date]."""
    mask = (df.index >= start_date) & (df.index <= end_date)
    filtered = df.loc[mask]
    
    if filtered.empty:
        print(f"[!] Warning: No data found for range {start_date} to {end_date}")
    else:
        print(f"[--] Filtered to {len(filtered):,} candles "
              f"({filtered.index[0].date()} -> {filtered.index[-1].date()})")
    return filtered

def fetch_live_data(symbol: str, source: str, interval: str, lookback_days: int = 10) -> pd.DataFrame:
    """
    Fetches the most recent OHLCV data for live signal calculation.
    """
    from datetime import datetime, timedelta
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=lookback_days)
    
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    
    try:
        stock = Vnstock().stock(symbol=symbol, source=source)
        df = stock.quote.history(start=start_str, end=end_str, interval=interval)
        
        if df is None or df.empty:
            return None
            
        df = df.dropna()
        df = df.rename(columns={
            "time": "Datetime", "open": "Open",
            "high": "High", "low": "Low", "close": "Close", "volume": "Volume"
        })
        df["Datetime"] = pd.to_datetime(df["Datetime"])
        df = df.set_index("Datetime").sort_index()
        
        return df
    except Exception as e:
        print(f"[!] Error fetching live data: {e}")
        return None
