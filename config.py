"""
config.py — Zentrale Konfiguration des Trading Bots
Alle Parameter hier anpassen. Kein Hard-Coding in anderen Modulen.
"""
import os
from dataclasses import dataclass, field
from typing import List

# ─────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "DEIN_TOKEN_HIER")
TELEGRAM_CHAT_ID: str   = os.getenv("TELEGRAM_CHAT_ID",   "DEINE_CHAT_ID_HIER")

# ─────────────────────────────────────────────
# PAPER TRADING KAPITAL
# ─────────────────────────────────────────────
PAPER_CAPITAL: float = 50_000.0        # Simuliertes Startkapital in USD

# ─────────────────────────────────────────────
# RISIKO-MANAGEMENT
# ─────────────────────────────────────────────
RISK_PER_TRADE_PCT: float   = 1.0      # % des Kapitals pro Trade (1% = professionell)
MAX_DAILY_LOSS_PCT: float   = 3.0      # Bot stoppt bei -3% Tages-Drawdown
MAX_OPEN_POSITIONS: int     = 3        # Max gleichzeitige Positionen
MIN_RR_DAYTRADE: float      = 2.5      # Min Risk:Reward für Day Trades
MIN_RR_SCALP: float         = 2.0      # Min Risk:Reward für Scalps
MIN_RR_SWING: float         = 3.0      # Min Risk:Reward für Swing Trades

# ─────────────────────────────────────────────
# INSTRUMENTE
# ─────────────────────────────────────────────
WATCHLIST: List[str] = ["SPY"]         # Phase 1: Nur SPY

# ─────────────────────────────────────────────
# TIMEFRAMES (yfinance Notation)
# ─────────────────────────────────────────────
TF_WEEKLY  = "1wk"
TF_DAILY   = "1d"
TF_4H      = "4h"
TF_1H      = "1h"
TF_30M     = "30m"
TF_15M     = "15m"

# Für Top-Down Analyse — Reihenfolge wichtig
TIMEFRAME_HIERARCHY = [TF_WEEKLY, TF_DAILY, TF_4H, TF_1H]

# ─────────────────────────────────────────────
# TRADING SESSIONS (UTC — VPS läuft auf UTC)
# ─────────────────────────────────────────────
# London Open:        08:00–12:00 CET = 07:00–11:00 UTC
# London-NY Overlap:  14:30–17:00 CET = 13:30–16:00 UTC
# NY Open:            14:30–17:30 CET = 13:30–16:30 UTC
SESSIONS = {
    "LONDON": {
        "start_utc": "07:00",
        "end_utc":   "11:00",
        "label":     "🇬🇧 London Open"
    },
    "OVERLAP": {
        "start_utc": "13:30",
        "end_utc":   "15:30",
        "label":     "⚡ London–NY Overlap"
    },
    "NY": {
        "start_utc": "13:30",
        "end_utc":   "16:30",
        "label":     "🗽 NY Open"
    }
}

# ─────────────────────────────────────────────
# MAKRO-FILTER (Druckenmiller)
# ─────────────────────────────────────────────
MACRO_MA_PERIOD: int   = 200           # 200 EMA für SPY als Master-Bias
DXY_SYMBOL: str        = "DX-Y.NYB"   # DXY via yfinance

# ─────────────────────────────────────────────
# SIGNAL ENGINE (Alex G — Set & Forget)
# ─────────────────────────────────────────────
AOI_LOOKBACK_BARS: int      = 50       # Wie viele Bars zurück für AOI-Erkennung
AOI_TOUCH_TOLERANCE_PCT: float = 0.15  # % Toleranz beim AOI-Touch
SL_BUFFER_PCT: float        = 0.15     # % über/unter AOI für Stop Loss
EMA_FAST: int               = 50       # Schnelle EMA für Konfluenz
EMA_SLOW: int               = 200      # Langsame EMA für Trend-Bias
MIN_ENGULFING_RATIO: float  = 1.2      # Engulfing-Kerze muss X mal größer sein als Vorgänger

# ─────────────────────────────────────────────
# NEWS FILTER — kein Entry X Minuten um High-Impact Events
# ─────────────────────────────────────────────
NEWS_BLACKOUT_MINUTES: int  = 30       # Kein Trade 30min vor/nach major news

# ─────────────────────────────────────────────
# DATENBANK & LOGGING
# ─────────────────────────────────────────────
DB_PATH: str  = "trading_bot.db"
LOG_DIR: str  = "logs"
LOG_LEVEL: str = "INFO"

# ─────────────────────────────────────────────
# MARKET BRIEFING (Daily — 08:30 UTC)
# ─────────────────────────────────────────────
DAILY_BRIEFING_TIME_UTC: str = "08:30"
