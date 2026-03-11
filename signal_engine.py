"""
signal_engine.py — Signal Detection Engine
Implements: Shift of Structure (SoS) + Engulfing Candle confirmation
Entry logic from Alex G Set & Forget strategy
"""

from dataclasses import dataclass
from typing import Optional

import pandas as pd
from loguru import logger


@dataclass
class TradeSignal:
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward: float
    entry_timeframe: str
    trigger_candle_time: object
    setup_grade: str
    confluence: dict
    session: str
    bias_strength: int
    active_aoi_mid: Optional[float] = None


def detect_shift_of_structure(df, direction, lookback=30):
    if df is None or len(df) < lookback:
        return False, None
    recent = df.tail(lookback).copy()
    if direction == "LONG":
        highs = recent["High"].values
        last_lh_price = None
        for i in range(2, len(highs) - 1):
            is_sh = (highs[i] > highs[i-1]) and (highs[i] > highs[i+1])
            if is_sh:
                if last_lh_price is None or highs[i] < last_lh_price:
                    last_lh_price = highs[i]
        if last_lh_price is None:
            return False, None
        body_high = max(float(recent["Close"].iloc[-1]), float(recent["Open"].iloc[-1]))
        if body_high > last_lh_price:
            return True, last_lh_price
    elif direction == "SHORT":
        lows = recent["Low"].values
        last_hl_price = None
        for i in range(2, len(lows) - 1):
            is_sl = (lows[i] < lows[i-1]) and (lows[i] < lows[i+1])
            if is_sl:
                if last_hl_price is None or lows[i] > last_hl_price:
                    last_hl_price = lows[i]
        if last_hl_price is None:
            return False, None
        body_low = min(float(recent["Close"].iloc[-1]), float(recent["Open"].iloc[-1]))
        if body_low < last_hl_price:
            return True, last_hl_price
    return False, None


def detect_engulfing(df, direction, min_ratio=0.6):
    if df is None or len(df) < 2:
        return False, None
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    cb_high = max(curr["Open"], curr["Close"])
    cb_low  = min(curr["Open"], curr["Close"])
    pb_high = max(prev["Open"], prev["Close"])
    pb_low  = min(prev["Open"], prev["Close"])
    pb_size = pb_high - pb_low
    if pb_size == 0:
        return False, None
    if direction == "LONG":
        if (curr["Close"] > curr["Open"] and cb_low <= pb_low
                and cb_high >= (pb_low + pb_size * min_ratio)):
            return True, curr
    elif direction == "SHORT":
        if (curr["Close"] < curr["Open"] and cb_high >= pb_high
                and cb_low <= (pb_high - pb_size * min_ratio)):
            return True, curr
    return False, None


def calculate_sl_tp(direction, entry, aoi_mid, nearest_structure, min_rr=2.5, sl_buffer_pct=0.001):
    buffer = entry * sl_buffer_pct
    if direction == "LONG":
        stop_loss = aoi_mid * (1 - 0.004) - buffer
        risk = abs(entry - stop_loss) or entry * 0.005
        take_profit = nearest_structure if nearest_structure > entry else entry + risk * min_rr
        rr = abs(take_profit - entry) / risk
        if rr < min_rr:
            take_profit = entry + risk * min_rr
            rr = min_rr
    else:
        stop_loss = aoi_mid * (1 + 0.004) + buffer
        risk = abs(stop_loss - entry) or entry * 0.005
        take_profit = nearest_structure if nearest_structure < entry else entry - risk * min_rr
        rr = abs(entry - take_profit) / risk
        if rr < min_rr:
            take_profit = entry - risk * min_rr
            rr = min_rr
    return round(stop_loss, 2), round(take_profit, 2), round(rr, 2)


def find_next_structure_level(bias, direction, current_price):
    candidates = []
    for tf_label, tf_analysis in bias.timeframes.items():
        if direction == "LONG":
            if tf_analysis.last_swing_high and tf_analysis.last_swing_high > current_price:
                candidates.append(tf_analysis.last_swing_high)
        else:
            if tf_analysis.last_swing_low and tf_analysis.last_swing_low < current_price:
                candidates.append(tf_analysis.last_swing_low)
    if not candidates:
        return current_price
    return min(candidates) if direction == "LONG" else max(candidates)


def check_for_signal(bias, h1_df, m15_df, current_session,
                     min_rr=2.5, engulf_min_ratio=0.6,
                     sos_lookback=30, sl_buffer_pct=0.001):
    if bias.bias == "NEUTRAL":
        return None
    direction = bias.bias
    grade = bias.score()
    if grade == "F":
        return None
    if not bias.active_aois:
        return None

    tf_priority = ["weekly", "daily", "4H", "1H"]
    best_aoi = None
    for zone in bias.active_aois:
        if best_aoi is None:
            best_aoi = zone
        elif zone.timeframe in tf_priority and best_aoi.timeframe in tf_priority:
            if tf_priority.index(zone.timeframe) < tf_priority.index(best_aoi.timeframe):
                best_aoi = zone

    if best_aoi is None:
        return None

    sos_confirmed, sos_level = detect_shift_of_structure(h1_df, direction, lookback=sos_lookback)
    confluence = {
        "htf_trend":  bias.strength >= 3,
        "at_aoi":     True,
        "macro_ok":   bias.macro_ok,
        "sos_on_1h":  sos_confirmed,
        "engulf_1h":  False,
        "engulf_15m": False,
    }

    if not sos_confirmed:
        return None

    engulf_found, trigger_candle = detect_engulfing(h1_df, direction, min_ratio=engulf_min_ratio)
    entry_tf = "1H"
    if engulf_found:
        confluence["engulf_1h"] = True
    else:
        ef2, tc2 = detect_engulfing(m15_df, direction, min_ratio=engulf_min_ratio)
        if ef2:
            engulf_found = True
            trigger_candle = tc2
            entry_tf = "15m"
            confluence["engulf_15m"] = True
        else:
            return None

    entry_price = float(h1_df["Close"].iloc[-1])
    next_struct = find_next_structure_level(bias, direction, entry_price)
    stop_loss, take_profit, rr = calculate_sl_tp(
        direction, entry_price, best_aoi.mid, next_struct, min_rr, sl_buffer_pct
    )

    if rr < min_rr:
        return None

    return TradeSignal(
        symbol=bias.symbol,
        direction=direction,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_reward=rr,
        entry_timeframe=entry_tf,
        trigger_candle_time=trigger_candle.name if trigger_candle is not None else pd.Timestamp.now(tz="UTC"),
        setup_grade=grade,
        confluence=confluence,
        session=current_session,
        bias_strength=bias.strength,
        active_aoi_mid=best_aoi.mid,
    )
