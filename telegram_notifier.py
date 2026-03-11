"""
telegram_notifier.py — Push Notifications via Telegram
Alle wichtigen Events → Handy.
Format: Clean, direkt, alle relevanten Infos auf einen Blick.
"""
import asyncio
import requests
from typing import Optional
from loguru import logger
from src.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from src.signal_engine import TradeSignal
from src.paper_broker import Trade, Position


class TelegramNotifier:

    def __init__(self):
        self.base_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
        self.chat_id  = TELEGRAM_CHAT_ID

    def send(self, message: str, parse_mode: str = "HTML") -> bool:
        """Sendet eine Nachricht via Telegram."""
        try:
            resp = requests.post(
                f"{self.base_url}/sendMessage",
                json={
                    "chat_id":    self.chat_id,
                    "text":       message,
                    "parse_mode": parse_mode
                },
                timeout=10
            )
            if resp.status_code == 200:
                return True
            else:
                logger.error(f"Telegram Fehler: {resp.status_code} — {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Telegram Exception: {e}")
            return False

    # ─────────────────────────────────────────
    # SIGNAL ALERT
    # ─────────────────────────────────────────

    def send_signal(self, signal: TradeSignal) -> bool:
        """Sendet ein neues Trade-Signal."""
        direction_emoji = "🟢" if signal.direction == "LONG" else "🔴"
        conf = signal.confluences

        # Konfluenz-Checkboxen
        def chk(val): return "✅" if val else "❌"

        msg = (
            f"{'='*32}\n"
            f"{direction_emoji} <b>NEUES SIGNAL — {signal.symbol}</b>\n"
            f"{'='*32}\n"
            f"📊 <b>{signal.direction}</b> | {signal.signal_type} | {signal.session}\n"
            f"⏱ Timeframe: {signal.entry_timeframe}\n\n"
            f"💰 <b>Entry:</b>  <code>${signal.entry_price:.2f}</code>\n"
            f"🛑 <b>SL:</b>     <code>${signal.stop_loss:.2f}</code>\n"
            f"🎯 <b>TP:</b>     <code>${signal.take_profit:.2f}</code>\n"
            f"⚖️ <b>RR:</b>    <code>{signal.risk_reward}:1</code>\n"
            f"⭐ <b>Score:</b>  <code>{signal.score}/100</code>\n\n"
            f"<b>📋 KONFLUENZEN:</b>\n"
            f"{chk(conf.get('htf_trend_sync'))} HTF Trend Sync ({signal.entry_timeframe})\n"
            f"{chk(conf.get('macro_aligned'))} Makro-Bias aligned (200 EMA)\n"
            f"{chk(conf.get('aoi_valid'))} AOI Zone ({conf.get('aoi_strength','?')})\n"
            f"{chk(conf.get('shift_of_structure'))} Shift of Structure\n"
            f"{chk(conf.get('engulfing_candle'))} Engulfing Candle\n"
            f"{chk(conf.get('tf_weekly'))} Weekly TF ✓\n"
            f"{chk(conf.get('tf_daily'))} Daily TF ✓\n"
            f"{chk(conf.get('tf_4h'))} 4H TF ✓\n"
        )
        return self.send(msg)

    # ─────────────────────────────────────────
    # TRADE CLOSE ALERT
    # ─────────────────────────────────────────

    def send_trade_close(self, trade: Trade) -> bool:
        """Sendet eine Benachrichtigung wenn ein Trade geschlossen wird."""
        pnl_emoji = "💰" if trade.pnl > 0 else "💸"
        reason_map = {"TP_HIT": "🎯 Take Profit", "SL_HIT": "🛑 Stop Loss",
                      "MANUAL": "👋 Manuell", "EOD": "🌙 End of Day"}
        reason_str = reason_map.get(trade.exit_reason, trade.exit_reason)

        msg = (
            f"{pnl_emoji} <b>TRADE GESCHLOSSEN — {trade.symbol}</b>\n"
            f"{'─'*28}\n"
            f"📊 {trade.direction} | {trade.quantity} Shares\n"
            f"📥 Entry: <code>${trade.entry_price:.2f}</code>\n"
            f"📤 Exit:  <code>${trade.exit_price:.2f}</code>\n"
            f"💵 P&L: <code>${trade.pnl:+.2f} ({trade.pnl_pct:+.2f}%)</code>\n"
            f"⏱ Dauer: {trade.hold_duration_min:.0f} Min\n"
            f"📌 Grund: {reason_str}\n"
        )
        return self.send(msg)

    # ─────────────────────────────────────────
    # DAILY BRIEFING
    # ─────────────────────────────────────────

    def send_daily_briefing(self, data: dict) -> bool:
        """Sendet das tägliche Market Briefing."""
        macro = data.get("macro", {})
        portfolio = data.get("portfolio", {})
        spy_trend = data.get("spy_trend", "NEUTRAL")

        bias_emoji = "🟢" if macro.get("bias") == "LONG" else ("🔴" if macro.get("bias") == "SHORT" else "⚪")
        session_block = (
            "🇬🇧 London:   09:00–12:00 CET\n"
            "⚡ Overlap:  14:30–16:30 CET\n"
            "🗽 NY Open:  14:30–17:30 CET"
        )

        msg = (
            f"🌅 <b>DAILY BRIEFING — {data.get('date','')}</b>\n"
            f"{'='*32}\n\n"
            f"<b>📊 MAKRO-BIAS</b>\n"
            f"{bias_emoji} SPY: <code>${macro.get('spy_price',0):.2f}</code> | "
            f"200 EMA: <code>${macro.get('ema_200',0):.2f}</code>\n"
            f"Bias: <b>{macro.get('bias','NEUTRAL')}</b>\n\n"
            f"<b>📈 SPY TREND</b>\n"
            f"Wöchentlich:  <code>{data.get('weekly_trend','?')}</code>\n"
            f"Täglich:      <code>{data.get('daily_trend','?')}</code>\n"
            f"4-Stunden:    <code>{data.get('4h_trend','?')}</code>\n\n"
            f"<b>💼 PORTFOLIO</b>\n"
            f"Equity:    <code>${portfolio.get('equity',0):,.2f}</code>\n"
            f"Gesamt P&L: <code>${portfolio.get('total_return_pct',0):+.2f}%</code>\n"
            f"Trades: {portfolio.get('total_trades',0)} | Win: {portfolio.get('win_rate',0):.0f}%\n\n"
            f"<b>⏰ SESSIONS HEUTE</b>\n"
            f"{session_block}\n\n"
            f"<b>🎯 WATCHLIST</b>: SPY\n"
            f"{'─'*28}\n"
            f"⚠️ PAPER MODE aktiv — kein echtes Kapital"
        )
        return self.send(msg)

    # ─────────────────────────────────────────
    # RISK ALERTS
    # ─────────────────────────────────────────

    def send_risk_alert(self, msg_type: str, detail: str = "") -> bool:
        alerts = {
            "DAILY_LOSS_LIMIT": f"🚨 <b>DAILY LOSS LIMIT ERREICHT</b>\n{detail}\nBot pausiert bis morgen.",
            "MAX_POSITIONS":    f"⏸ <b>MAX POSITIONEN</b>\n{detail}\nNeue Trades blockiert.",
            "BOT_START":        f"🤖 <b>TRADING BOT GESTARTET</b>\n{detail}\n⚠️ PAPER MODE",
            "BOT_STOP":         f"⏹ <b>TRADING BOT GESTOPPT</b>\n{detail}",
            "ERROR":            f"❌ <b>FEHLER</b>\n{detail}",
        }
        msg = alerts.get(msg_type, f"ℹ️ {msg_type}: {detail}")
        return self.send(msg)

    def send_portfolio_snapshot(self, portfolio: dict) -> bool:
        """Stündlicher Portfolio-Snapshot."""
        pnl_emoji = "📈" if portfolio.get("daily_pnl", 0) >= 0 else "📉"
        msg = (
            f"{pnl_emoji} <b>PORTFOLIO UPDATE</b>\n"
            f"{'─'*28}\n"
            f"Equity:     <code>${portfolio.get('equity',0):,.2f}</code>\n"
            f"Daily P&L:  <code>${portfolio.get('daily_pnl',0):+.2f} "
            f"({portfolio.get('daily_pnl_pct',0):+.2f}%)</code>\n"
            f"Unrealized: <code>${portfolio.get('unrealized_pnl',0):+.2f}</code>\n"
            f"Positionen: {portfolio.get('open_positions',0)}/{3}\n"
            f"⚠️ PAPER MODE"
        )
        return self.send(msg)
