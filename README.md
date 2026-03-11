# 🤖 Trading Bot — Beta Paper Mode

**Stack:** Python | yfinance | pandas-ta | APScheduler | SQLite | Telegram  
**Mode:** ⚠️ PAPER TRADING — kein echtes Kapital  
**Instrument:** SPY (S&P 500 ETF)

---

## Architektur

```
main.py                    ← Entry Point + Scheduler + Main Loop
src/
  config.py                ← Alle Parameter (1 Stelle ändern = überall wirksam)
  data_feed.py             ← yfinance OHLCV, Multi-Timeframe
  market_analyzer.py       ← Top-Down Analyse: Weekly→Daily→4H→1H
  signal_engine.py         ← SoS + Engulfing Entry Logic (Alex G)
  risk_manager.py          ← 1% Risk, Daily Loss Guard, Position Sizing
  paper_broker.py          ← Simuliertes Execution Layer + P&L Tracking
  telegram_notifier.py     ← Push Notifications
  trade_journal.py         ← SQLite Journal (Trades, Signale, Daily Stats)
  scheduler.py             ← Session-Timing (London/Overlap/NY)
```

---

## Strategie-Logik

### 1. Makro-Filter (Druckenmiller)
- SPY > 200 EMA → **Long Bias** (Risk ON)
- SPY < 200 EMA → **Short Bias** (Risk OFF)

### 2. Top-Down Analyse (Alex G — Set & Forget)
```
Weekly  → Trend (HH/HL oder LH/LL)
Daily   → Trend + AOI Zonen
4H      → Trend + AOI Zonen
1H      → Entry Timeframe
```
Min. 3/4 Timeframes müssen in die gleiche Richtung zeigen.

### 3. Entry Trigger
1. Preis an AOI Zone
2. **Shift of Structure** auf Entry-TF
3. **Engulfing Candle** Bestätigung

### 4. Risk Management
- Risk per Trade: **1%** des Kapitals
- Min RR: **2.5:1** (Day Trade)
- Max Daily Loss: **-3%** → Bot stoppt automatisch
- Max Open Positions: **3**
- SL: 0.15% hinter AOI-Zone

---

## Setup

```bash
# 1. Repo auf VPS klonen
git clone <your-repo> trading_bot
cd trading_bot

# 2. Setup ausführen
bash setup.sh

# 3. Telegram Credentials eintragen
nano .env

# 4. Bot starten
python3 main.py

# 5. Als systemd Service (empfohlen für VPS)
sudo nano /etc/systemd/system/tradingbot.service
```

### systemd Service
```ini
[Unit]
Description=Trading Bot Paper Mode
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/trading_bot
ExecStart=/usr/bin/python3 main.py
EnvironmentFile=/home/ubuntu/trading_bot/.env
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable tradingbot
sudo systemctl start tradingbot
sudo systemctl status tradingbot
sudo journalctl -u tradingbot -f   # Live Logs
```

---

## Telegram Commands (via Signal)

Bot schickt automatisch:
- 🌅 **Daily Briefing** → 08:30 UTC (Makro, Trends, Portfolio)
- 🔔 **Trade Signal** → bei neuem Setup (Entry, SL, TP, Score, Konfluenzen)
- 💰/💸 **Trade Close** → bei TP/SL Hit
- 📊 **Portfolio Snapshot** → stündlich
- 🚨 **Risk Alerts** → Daily Loss Limit, Fehler

---

## Konfiguration (src/config.py)

| Parameter | Default | Beschreibung |
|---|---|---|
| `PAPER_CAPITAL` | $50,000 | Simuliertes Startkapital |
| `RISK_PER_TRADE_PCT` | 1.0% | Risk pro Trade |
| `MAX_DAILY_LOSS_PCT` | 3.0% | Bot-Stop Schwelle |
| `MAX_OPEN_POSITIONS` | 3 | Max gleichzeitige Positionen |
| `MIN_RR_DAYTRADE` | 2.5 | Min Risk:Reward |
| `MIN_ENGULFING_RATIO` | 1.2 | Engulfing Stärke |

---

## Nächste Phase (Phase 2)

- [ ] Order Flow / CVD Integration (Fabio Valentini Methode)
- [ ] News Filter (Economic Calendar API)
- [ ] Web Dashboard (FastAPI + Chart.js)
- [ ] Alpaca Live-Trading Anbindung
- [ ] Backtest Engine (vectorbt)
