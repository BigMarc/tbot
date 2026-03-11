"""
main.py — Haupt-Entry-Point des Trading Bots
Startet alle Komponenten und den Main Loop.

USAGE:
    python main.py

PAPER MODE: Kein echtes Kapital. Vollständige Simulation.
"""
import time
import signal
import sys
from datetime import datetime
from loguru import logger
from apscheduler.schedulers.background import BackgroundScheduler

from src.config import (
    WATCHLIST, PAPER_CAPITAL, LOG_DIR, LOG_LEVEL,
    TF_WEEKLY, TF_DAILY, TF_4H, TF_1H
)
from src.data_feed import get_multi_tf_data, get_current_price
from src.market_analyzer import MarketAnalyzer
from src.signal_engine import SignalEngine
from src.risk_manager import RiskManager
from src.paper_broker import PaperBroker
from src.telegram_notifier import TelegramNotifier
from src.trade_journal import TradeJournal
from src.scheduler import (
    get_active_session, is_market_open,
    should_run_daily_briefing, get_next_session_info
)

import os
os.makedirs(LOG_DIR, exist_ok=True)

# ─────────────────────────────────────────────
# LOGGING SETUP
# ─────────────────────────────────────────────
logger.remove()
logger.add(sys.stdout, level=LOG_LEVEL, colorize=True,
           format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}")
logger.add(f"{LOG_DIR}/bot_{{time:YYYY-MM-DD}}.log",
           rotation="1 day", retention="30 days", level="DEBUG")


# ─────────────────────────────────────────────
# BOT KLASSE
# ─────────────────────────────────────────────

class TradingBot:

    def __init__(self):
        logger.info("🤖 Trading Bot wird initialisiert...")

        # Komponenten
        self.broker      = PaperBroker(initial_capital=PAPER_CAPITAL)
        self.analyzer    = MarketAnalyzer()
        self.signal_eng  = SignalEngine()
        self.risk_mgr    = RiskManager(self.broker)
        self.notifier    = TelegramNotifier()
        self.journal     = TradeJournal()
        self.scheduler   = BackgroundScheduler(timezone="UTC")

        self.running     = False
        self.scan_count  = 0

        # Graceful Shutdown
        signal.signal(signal.SIGINT,  self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

    def start(self):
        """Startet den Bot."""
        logger.info("="*50)
        logger.info("🚀 TRADING BOT STARTET — ⚠️ PAPER MODE")
        logger.info(f"   Kapital:     ${PAPER_CAPITAL:,.0f}")
        logger.info(f"   Watchlist:   {', '.join(WATCHLIST)}")
        logger.info(f"   Risk/Trade:  1%")
        logger.info(f"   Daily Limit: -3%")
        logger.info("="*50)

        self.running = True

        # Scheduler Jobs
        # Haupt-Scan: alle 5 Minuten während Sessions
        self.scheduler.add_job(
            self._scan_cycle, "interval", minutes=5,
            id="main_scan", max_instances=1
        )
        # SL/TP Monitor: alle 60 Sekunden
        self.scheduler.add_job(
            self._monitor_positions, "interval", seconds=60,
            id="position_monitor", max_instances=1
        )
        # Daily Briefing: jeden Werktag 08:30 UTC
        self.scheduler.add_job(
            self._send_daily_briefing, "cron",
            hour=8, minute=30, day_of_week="mon-fri",
            id="daily_briefing"
        )
        # Portfolio Snapshot: stündlich
        self.scheduler.add_job(
            self._portfolio_snapshot, "interval", hours=1,
            id="portfolio_snapshot"
        )
        # Daily Summary: 21:00 UTC (nach US Close)
        self.scheduler.add_job(
            self._save_daily_summary, "cron",
            hour=21, minute=0, day_of_week="mon-fri",
            id="daily_summary"
        )

        self.scheduler.start()

        # Start-Notification
        session_info = get_next_session_info()
        self.notifier.send_risk_alert(
            "BOT_START",
            f"Kapital: ${PAPER_CAPITAL:,.0f}\n"
            f"Watchlist: {', '.join(WATCHLIST)}\n"
            f"Session: {session_info.get('label', '–')}"
        )

        # Initialer Scan
        self._scan_cycle()

        # Main Loop
        logger.info("✅ Bot läuft. Ctrl+C zum Stoppen.")
        while self.running:
            time.sleep(10)

    # ─────────────────────────────────────────
    # HAUPT-SCAN CYCLE
    # ─────────────────────────────────────────

    def _scan_cycle(self):
        """
        Haupt-Scan: Top-Down Analyse → Signal-Check → Execution.
        Wird alle 5 Minuten aufgerufen.
        """
        try:
            # Market offen?
            if not is_market_open():
                logger.debug("Markt geschlossen — kein Scan")
                return

            session = get_active_session()
            if session == "CLOSED":
                logger.debug(f"Keine aktive Session — kein Scan")
                return

            self.scan_count += 1
            logger.info(f"🔍 Scan #{self.scan_count} | Session: {session} | "
                       f"{datetime.utcnow().strftime('%H:%M UTC')}")

            # Risk Check vor allem
            can_trade, reason = self.risk_mgr.can_trade()
            if not can_trade:
                logger.info(f"Trade blockiert: {reason}")
                return

            # Pro Symbol
            for symbol in WATCHLIST:
                self._analyze_symbol(symbol, session)

        except Exception as e:
            logger.error(f"Scan Fehler: {e}")
            self.notifier.send_risk_alert("ERROR", str(e))

    def _analyze_symbol(self, symbol: str, session: str):
        """Analysiert ein einzelnes Symbol und generiert ggf. ein Signal."""
        try:
            # 1. Daten laden
            logger.debug(f"Lade Daten für {symbol}...")
            data = get_multi_tf_data(symbol)
            if not data or TF_DAILY not in data:
                logger.warning(f"Keine Daten für {symbol}")
                return

            # 2. Top-Down Analyse
            top_down = self.analyzer.analyze(symbol, data)

            if not top_down.tradeable:
                logger.info(f"[{symbol}] Nicht tradeable: {top_down.reason}")
                return

            # 3. Signal-Scan (Entry auf 1H)
            entry_df = data.get(TF_1H, data.get(TF_4H))
            if entry_df is None or entry_df.empty:
                return

            signal = self.signal_eng.scan_for_signals(
                symbol=symbol,
                top_down=top_down,
                entry_df=entry_df,
                entry_tf=TF_1H,
                current_session=session
            )

            # Signal loggen (auch wenn rejected)
            if signal:
                self.journal.log_signal(signal)

            # 4. Valides Signal → Trade ausführen
            if signal and signal.valid and signal.score >= 60:
                self._execute_signal(signal)
            elif signal and signal.valid:
                logger.info(f"[{symbol}] Signal Score zu niedrig: {signal.score}/100 (Min: 60)")

        except Exception as e:
            logger.error(f"Analyse-Fehler {symbol}: {e}")

    # ─────────────────────────────────────────
    # TRADE EXECUTION
    # ─────────────────────────────────────────

    def _execute_signal(self, signal):
        """Führt ein Signal als Paper Trade aus."""
        # Final Risk Check
        can_trade, reason = self.risk_mgr.can_trade()
        if not can_trade:
            logger.info(f"Execution blockiert: {reason}")
            return

        # Position Sizing
        pos_size = self.risk_mgr.calculate_position_size(
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            direction=signal.direction
        )

        if not pos_size.valid or pos_size.shares < 1:
            logger.warning(f"Ungültige Position Size: {pos_size.reject_reason}")
            return

        # Order abschicken
        order = self.broker.submit_order(
            symbol=signal.symbol,
            direction=signal.direction,
            quantity=pos_size.shares,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            order_type="MARKET"
        )

        # Telegram Signal
        self.notifier.send_signal(signal)

        logger.info(
            f"✅ TRADE ERÖFFNET: {signal.direction} {pos_size.shares}x {signal.symbol} "
            f"| Entry: ${order.filled_price:.2f} | Risk: ${pos_size.risk_amount:.0f}"
        )

    # ─────────────────────────────────────────
    # POSITION MONITOR
    # ─────────────────────────────────────────

    def _monitor_positions(self):
        """Checkt offene Positionen auf SL/TP Hits."""
        try:
            open_count = self.broker.get_open_positions_count()
            if open_count == 0:
                return

            # Aktuelle Preise holen
            current_prices = {}
            for symbol in WATCHLIST:
                price = get_current_price(symbol)
                if price > 0:
                    current_prices[symbol] = price

            # Positionen updaten
            closed_trades = self.broker.update_positions(current_prices)

            # Geschlossene Trades loggen & notifizieren
            for trade in closed_trades:
                self.journal.log_trade(trade)
                self.notifier.send_trade_close(trade)

        except Exception as e:
            logger.error(f"Position Monitor Fehler: {e}")

    # ─────────────────────────────────────────
    # DAILY BRIEFING
    # ─────────────────────────────────────────

    def _send_daily_briefing(self):
        """Sendet das tägliche Market Briefing um 08:30 UTC."""
        try:
            # Daten für SPY laden
            data = get_multi_tf_data("SPY")
            top_down = self.analyzer.analyze("SPY", data)
            portfolio = self.broker.get_portfolio_summary()

            macro = {
                "bias":      top_down.macro_bias.bias if top_down.macro_bias else "NEUTRAL",
                "spy_price": top_down.macro_bias.spy_price if top_down.macro_bias else 0,
                "ema_200":   top_down.macro_bias.ema_200 if top_down.macro_bias else 0,
            }

            briefing_data = {
                "date":          datetime.utcnow().strftime("%d.%m.%Y"),
                "macro":         macro,
                "portfolio":     portfolio,
                "weekly_trend":  top_down.tf_analyses.get(TF_WEEKLY, type("x", (), {"trend": "?"})()).trend,
                "daily_trend":   top_down.tf_analyses.get(TF_DAILY,  type("x", (), {"trend": "?"})()).trend,
                "4h_trend":      top_down.tf_analyses.get(TF_4H,     type("x", (), {"trend": "?"})()).trend,
            }

            self.notifier.send_daily_briefing(briefing_data)
            logger.info("📊 Daily Briefing gesendet")

        except Exception as e:
            logger.error(f"Daily Briefing Fehler: {e}")

    def _portfolio_snapshot(self):
        """Stündlicher Portfolio-Snapshot an Telegram."""
        try:
            portfolio = self.broker.get_portfolio_summary()
            self.notifier.send_portfolio_snapshot(portfolio)
        except Exception as e:
            logger.error(f"Portfolio Snapshot Fehler: {e}")

    def _save_daily_summary(self):
        """Speichert die tägliche Zusammenfassung in die DB."""
        try:
            portfolio = self.broker.get_portfolio_summary()
            self.journal.save_daily_summary(portfolio)
            logger.info("📁 Daily Summary gespeichert")
        except Exception as e:
            logger.error(f"Daily Summary Fehler: {e}")

    # ─────────────────────────────────────────
    # SHUTDOWN
    # ─────────────────────────────────────────

    def _shutdown(self, signum, frame):
        """Graceful Shutdown."""
        logger.info("⏹ Bot wird gestoppt...")
        self.running = False
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

        # Offene Positionen schließen (EOD)
        open_positions = self.broker.get_open_positions()
        if open_positions:
            logger.warning(f"{len(open_positions)} offene Positionen beim Stop")
            for pos in open_positions:
                price = get_current_price(pos.symbol)
                if price > 0:
                    trade = self.broker._close_position(pos.position_id, price, "EOD")
                    self.journal.log_trade(trade)
                    self.notifier.send_trade_close(trade)

        # Final Summary
        portfolio = self.broker.get_portfolio_summary()
        self.journal.save_daily_summary(portfolio)
        self.notifier.send_risk_alert(
            "BOT_STOP",
            f"Equity: ${portfolio['equity']:,.2f} | "
            f"Daily P&L: ${portfolio['daily_pnl']:+.2f} ({portfolio['daily_pnl_pct']:+.2f}%)"
        )
        logger.info("✅ Bot gestoppt.")
        sys.exit(0)


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    bot = TradingBot()
    bot.start()
