"""
data_feed.py — Marktdaten via yfinance
Holt OHLCV-Daten für alle Timeframes. Caching um API-Limits zu vermeiden.
"""
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from loguru import logger
from functools import lru_cache
from src.config import (
    TF_WEEKLY, TF_DAILY, TF_4H, TF_1H, TF_30M, TF_15M
)

# Timeframe → Anzahl Bars die wir für Analyse brauchen
TF_PERIODS = {
    TF_WEEKLY: ("2y",  "1wk"),
    TF_DAILY:  ("1y",  "1d"),
    TF_4H:     ("60d", "1h"),   # yfinance hat kein 4h — wir resamplen
    TF_1H:     ("30d", "1h"),
    TF_30M:    ("10d", "30m"),
    TF_15M:    ("7d",  "15m"),
}


def get_ohlcv(symbol: str, timeframe: str) -> pd.DataFrame:
    """
    Holt OHLCV-Daten für ein Symbol und einen Timeframe.
    Gibt einen sauberen DataFrame zurück mit Spalten:
    open, high, low, close, volume
    """
    if timeframe not in TF_PERIODS:
        raise ValueError(f"Unbekannter Timeframe: {timeframe}")

    period, yf_interval = TF_PERIODS[timeframe]

    # 4H-Daten: 1H Daten holen und auf 4H resamplen
    if timeframe == TF_4H:
        df = _fetch_raw(symbol, "1h", "60d")
        df = _resample_to_4h(df)
    else:
        df = _fetch_raw(symbol, yf_interval, period)

    if df is None or df.empty:
        logger.warning(f"Keine Daten für {symbol} [{timeframe}]")
        return pd.DataFrame()

    # Spalten normalisieren
    df.columns = [c.lower() for c in df.columns]
    df = df[["open", "high", "low", "close", "volume"]].copy()
    df.dropna(inplace=True)
    return df


def _fetch_raw(symbol: str, interval: str, period: str) -> pd.DataFrame:
    """Interner Fetch mit Error Handling."""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval, auto_adjust=True)
        if df.empty:
            logger.error(f"Leerer DataFrame für {symbol} [{interval}]")
            return pd.DataFrame()
        return df
    except Exception as e:
        logger.error(f"Datenfehler {symbol} [{interval}]: {e}")
        return pd.DataFrame()


def _resample_to_4h(df_1h: pd.DataFrame) -> pd.DataFrame:
    """Resamplet 1H-Daten zu 4H-Daten."""
    if df_1h.empty:
        return df_1h
    df_4h = df_1h.resample("4h").agg({
        "Open":   "first",
        "High":   "max",
        "Low":    "min",
        "Close":  "last",
        "Volume": "sum"
    }).dropna()
    return df_4h


def get_current_price(symbol: str) -> float:
    """Gibt den aktuellen Preis zurück (letzter Close)."""
    try:
        ticker = yf.Ticker(symbol)
        data = ticker.history(period="1d", interval="1m")
        if not data.empty:
            return float(data["Close"].iloc[-1])
        return 0.0
    except Exception as e:
        logger.error(f"Preisfehler {symbol}: {e}")
        return 0.0


def get_multi_tf_data(symbol: str) -> dict:
    """
    Holt alle relevanten Timeframes auf einmal.
    Returns: Dict mit TF als Key, DataFrame als Value
    """
    timeframes = [TF_WEEKLY, TF_DAILY, TF_4H, TF_1H]
    result = {}
    for tf in timeframes:
        df = get_ohlcv(symbol, tf)
        if not df.empty:
            result[tf] = df
            logger.debug(f"{symbol} [{tf}]: {len(df)} Bars geladen")
        else:
            logger.warning(f"{symbol} [{tf}]: Keine Daten")
    return result
