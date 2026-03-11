"""
market_analyzer.py — Top-Down Analysis Engine (Alex G Method)
Weekly → Daily → 4H → 1H structural analysis
"""
from dataclasses import dataclass, field
from typing import Optional
import numpy as np
import pandas as pd
import pandas_ta as ta
from loguru import logger


@dataclass
class AOIZone:
    upper: float
    lower: float
    mid: float
    timeframe: str
    touches: int = 1
    def contains(self, price, tol=0.004):
        band = self.mid * tol
        return (self.lower - band) <= price <= (self.upper + band)

@dataclass
class TimeframeAnalysis:
    label: str
    trend: str
    last_swing_high: Optional[float] = None
    last_swing_low: Optional[float] = None
    aoi_zones: list = field(default_factory=list)
    ema50: Optional[float] = None
    ma200: Optional[float] = None
    valid: bool = True

@dataclass
class MarketBias:
    symbol: str
    bias: str
    strength: int
    macro_ok: bool
    timeframes: dict
    active_aois: list
    current_price: float = 0.0
    dxy_trend: str = "unknown"
    def score(self):
        if self.strength >= 4 and self.macro_ok: return "A"
        elif self.strength >= 3 and self.macro_ok: return "B"
        elif self.strength >= 3: return "C"
        return "F"


def detect_swings(df, lookback=10):
    highs, lows = [], []
    for i in range(lookback, len(df) - lookback):
        wh = df["High"].iloc[i-lookback:i+lookback+1]
        if df["High"].iloc[i] == wh.max():
            highs.append((i, float(df["High"].iloc[i])))
        wl = df["Low"].iloc[i-lookback:i+lookback+1]
        if df["Low"].iloc[i] == wl.min():
            lows.append((i, float(df["Low"].iloc[i])))
    return highs, lows


def determine_trend(swing_highs, swing_lows):
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return "neutral"
    rh = sorted(swing_highs[-3:], key=lambda x: x[0])
    rl = sorted(swing_lows[-3:],  key=lambda x: x[0])
    hh = rh[-1][1] > rh[-2][1]
    hl = rl[-1][1] > rl[-2][1]
    lh = rh[-1][1] < rh[-2][1]
    ll = rl[-1][1] < rl[-2][1]
    if hh and hl: return "bullish"
    elif lh and ll: return "bearish"
    return "neutral"


def analyze_timeframe(df, label, swing_lookback=10):
    if df is None or len(df) < swing_lookback * 3:
        return TimeframeAnalysis(label=label, trend="neutral", valid=False)
    try:
        close = df["Close"]
        ema50 = ta.ema(close, length=50)
        ma200 = ta.ema(close, length=200)
        last_ema50 = float(ema50.iloc[-1]) if ema50 is not None and not ema50.empty else None
        last_ma200 = float(ma200.iloc[-1]) if ma200 is not None and not ma200.empty else None
        highs, lows = detect_swings(df, lookback=swing_lookback)
        trend = determine_trend(highs, lows)
        # Build AOI zones from recent swings
        aoi_zones = []
        for i, price in (highs[-5:] + lows[-5:]):
            row = df.iloc[i]
            bh = max(row["Open"], row["Close"])
            bl = min(row["Open"], row["Close"])
            if bh == bl: bh = row["High"]; bl = row["Low"]
            aoi_zones.append(AOIZone(upper=bh, lower=bl, mid=(bh+bl)/2, timeframe=label))
        last_sh = highs[-1][1] if highs else None
        last_sl = lows[-1][1]  if lows  else None
        return TimeframeAnalysis(label=label, trend=trend, last_swing_high=last_sh,
            last_swing_low=last_sl, aoi_zones=aoi_zones, ema50=last_ema50, ma200=last_ma200, valid=True)
    except Exception as e:
        logger.error(f"analyze_timeframe {label}: {e}")
        return TimeframeAnalysis(label=label, trend="neutral", valid=False)


def get_macro_bias(spy_daily, dxy_daily):
    macro_ok = False
    dxy_trend = "unknown"
    try:
        if spy_daily is not None and len(spy_daily) >= 200:
            ma200 = spy_daily["Close"].rolling(200).mean()
            macro_ok = float(spy_daily["Close"].iloc[-1]) > float(ma200.iloc[-1])
    except: pass
    try:
        if dxy_daily is not None and len(dxy_daily) >= 20:
            ema20 = dxy_daily["Close"].ewm(span=20).mean()
            dxy_trend = "rising" if float(dxy_daily["Close"].iloc[-1]) > float(ema20.iloc[-1]) else "falling"
    except: pass
    return macro_ok, dxy_trend


def run_top_down_analysis(symbol, all_tf_data, dxy_data, current_price,
                           aoi_tolerance=0.004, swing_lookback=10, min_tf_alignment=3):
    tf_map = {"weekly": all_tf_data.get("weekly"), "daily": all_tf_data.get("daily"),
              "4H": all_tf_data.get("h4"), "1H": all_tf_data.get("h1")}
    analyses = {}
    for label, df in tf_map.items():
        lkb = 5 if label == "weekly" else swing_lookback
        analyses[label] = analyze_timeframe(df, label, swing_lookback=lkb)
    valid = [a for a in analyses.values() if a.valid]
    bull  = sum(1 for a in valid if a.trend == "bullish")
    bear  = sum(1 for a in valid if a.trend == "bearish")
    total = len(valid)
    if total == 0: bias, strength = "NEUTRAL", 0
    elif bull >= min_tf_alignment: bias, strength = "LONG", bull
    elif bear >= min_tf_alignment: bias, strength = "SHORT", bear
    else: bias, strength = "NEUTRAL", max(bull, bear)
    macro_ok, dxy_trend = get_macro_bias(all_tf_data.get("daily"), dxy_data)
    active_aois = []
    for a in analyses.values():
        for zone in a.aoi_zones:
            if zone.contains(current_price, tol=aoi_tolerance):
                active_aois.append(zone)
    result = MarketBias(symbol=symbol, bias=bias, strength=strength, macro_ok=macro_ok,
                        timeframes=analyses, active_aois=active_aois,
                        current_price=current_price, dxy_trend=dxy_trend)
    logger.info(f"[TopDown] {symbol} → {bias} ({strength}/{total}) macro={'✓' if macro_ok else '✗'} DXY={dxy_trend} AOIs={len(active_aois)} grade={result.score()}")
    return result
