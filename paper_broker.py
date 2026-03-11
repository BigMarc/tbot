"""
paper_broker.py — Simuliertes Execution Layer (kein externer Broker)
Vollständige Paper-Trading Simulation:
- Order Execution (Market / Limit)
- Position Management
- P&L Tracking (Daily + Total)
- Portfolio Snapshot
"""
import uuid
from datetime import datetime, date
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from loguru import logger
from src.config import PAPER_CAPITAL


# ─────────────────────────────────────────────
# DATENSTRUKTUREN
# ─────────────────────────────────────────────

@dataclass
class Order:
    order_id: str
    symbol: str
    direction: str          # "LONG" | "SHORT"
    order_type: str         # "MARKET" | "LIMIT"
    quantity: int
    entry_price: float
    stop_loss: float
    take_profit: float
    status: str             # "PENDING" | "FILLED" | "CANCELLED"
    filled_price: float = 0.0
    timestamp: str = ""
    fill_timestamp: str = ""

@dataclass
class Position:
    position_id: str
    symbol: str
    direction: str
    quantity: int
    entry_price: float
    current_price: float
    stop_loss: float
    take_profit: float
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    open_time: str = ""
    status: str = "OPEN"    # "OPEN" | "CLOSED"
    close_price: float = 0.0
    close_time: str = ""
    realized_pnl: float = 0.0

@dataclass
class Trade:
    trade_id: str
    symbol: str
    direction: str
    quantity: int
    entry_price: float
    exit_price: float
    pnl: float
    pnl_pct: float
    entry_time: str
    exit_time: str
    exit_reason: str        # "TP_HIT" | "SL_HIT" | "MANUAL" | "EOD"
    hold_duration_min: float = 0.0


# ─────────────────────────────────────────────
# PAPER BROKER
# ─────────────────────────────────────────────

class PaperBroker:
    """
    Vollständige Paper-Trading Simulation.
    Keine externe API — alles lokal im Speicher + SQLite via TradeJournal.
    """

    def __init__(self, initial_capital: float = PAPER_CAPITAL):
        self.initial_capital  = initial_capital
        self.equity           = initial_capital
        self.cash             = initial_capital
        self.positions: Dict[str, Position] = {}   # position_id → Position
        self.orders: Dict[str, Order]       = {}
        self.trade_history: List[Trade]     = []
        self.daily_start_equity = initial_capital
        self.daily_pnl          = 0.0
        self._today             = date.today()

    # ─────────────────────────────────────────
    # ORDER EXECUTION
    # ─────────────────────────────────────────

    def submit_order(
        self,
        symbol: str,
        direction: str,
        quantity: int,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        order_type: str = "MARKET"
    ) -> Order:
        """
        Simuliert Order-Execution. Bei MARKET → sofortige Füllung.
        Slippage: 0.02% (1 Tick bei SPY ≈ $0.01)
        """
        # Reset Daily P&L wenn neuer Tag
        self._check_new_day()

        slippage_pct = 0.02 / 100
        if order_type == "MARKET":
            if direction == "LONG":
                filled_price = round(entry_price * (1 + slippage_pct), 4)
            else:
                filled_price = round(entry_price * (1 - slippage_pct), 4)
        else:
            filled_price = entry_price

        order_id = str(uuid.uuid4())[:8]
        order = Order(
            order_id=order_id,
            symbol=symbol,
            direction=direction,
            order_type=order_type,
            quantity=quantity,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            status="FILLED",
            filled_price=filled_price,
            timestamp=datetime.utcnow().isoformat(),
            fill_timestamp=datetime.utcnow().isoformat()
        )
        self.orders[order_id] = order

        # Position öffnen
        position_id = str(uuid.uuid4())[:8]
        position = Position(
            position_id=position_id,
            symbol=symbol,
            direction=direction,
            quantity=quantity,
            entry_price=filled_price,
            current_price=filled_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            open_time=datetime.utcnow().isoformat()
        )
        self.positions[position_id] = position

        # Kapital reservieren
        cost = filled_price * quantity
        self.cash -= cost

        logger.info(
            f"📝 ORDER FILLED [{order_id}] | {direction} {quantity}x {symbol} "
            f"@ ${filled_price:.2f} | SL: ${stop_loss:.2f} | TP: ${take_profit:.2f}"
        )
        return order

    # ─────────────────────────────────────────
    # PREIS-UPDATE & SL/TP CHECK
    # ─────────────────────────────────────────

    def update_positions(self, current_prices: Dict[str, float]) -> List[Trade]:
        """
        Updated alle offenen Positionen mit aktuellen Preisen.
        Prüft SL und TP. Gibt abgeschlossene Trades zurück.
        """
        closed_trades = []

        for pos_id, pos in list(self.positions.items()):
            if pos.status != "OPEN":
                continue

            if pos.symbol not in current_prices:
                continue

            price = current_prices[pos.symbol]
            pos.current_price = price

            # Unrealized P&L
            if pos.direction == "LONG":
                pos.unrealized_pnl = (price - pos.entry_price) * pos.quantity
            else:
                pos.unrealized_pnl = (pos.entry_price - price) * pos.quantity

            pos.unrealized_pnl_pct = (pos.unrealized_pnl / (pos.entry_price * pos.quantity)) * 100

            # TP Hit?
            if pos.direction == "LONG" and price >= pos.take_profit:
                trade = self._close_position(pos_id, price, "TP_HIT")
                closed_trades.append(trade)
                logger.info(f"🎯 TP HIT [{pos.symbol}] @ ${price:.2f} | PnL: ${trade.pnl:.2f}")

            # SL Hit?
            elif pos.direction == "LONG" and price <= pos.stop_loss:
                trade = self._close_position(pos_id, price, "SL_HIT")
                closed_trades.append(trade)
                logger.info(f"🛑 SL HIT [{pos.symbol}] @ ${price:.2f} | PnL: ${trade.pnl:.2f}")

            # Short TP/SL
            elif pos.direction == "SHORT" and price <= pos.take_profit:
                trade = self._close_position(pos_id, price, "TP_HIT")
                closed_trades.append(trade)
                logger.info(f"🎯 TP HIT [{pos.symbol}] @ ${price:.2f} | PnL: ${trade.pnl:.2f}")

            elif pos.direction == "SHORT" and price >= pos.stop_loss:
                trade = self._close_position(pos_id, price, "SL_HIT")
                closed_trades.append(trade)
                logger.info(f"🛑 SL HIT [{pos.symbol}] @ ${price:.2f} | PnL: ${trade.pnl:.2f}")

        # Equity updaten
        self._update_equity()
        return closed_trades

    def _close_position(self, position_id: str, close_price: float, reason: str) -> Trade:
        """Schließt eine Position und realisiert den P&L."""
        pos = self.positions[position_id]
        pos.status = "CLOSED"
        pos.close_price = close_price
        pos.close_time = datetime.utcnow().isoformat()

        if pos.direction == "LONG":
            realized_pnl = (close_price - pos.entry_price) * pos.quantity
        else:
            realized_pnl = (pos.entry_price - close_price) * pos.quantity

        pos.realized_pnl = realized_pnl

        # Kapital zurück + P&L
        self.cash += (pos.entry_price * pos.quantity) + realized_pnl
        self.daily_pnl += realized_pnl

        # Trade History
        entry_time = datetime.fromisoformat(pos.open_time) if pos.open_time else datetime.utcnow()
        hold_mins = (datetime.utcnow() - entry_time).total_seconds() / 60

        trade = Trade(
            trade_id=str(uuid.uuid4())[:8],
            symbol=pos.symbol,
            direction=pos.direction,
            quantity=pos.quantity,
            entry_price=pos.entry_price,
            exit_price=close_price,
            pnl=round(realized_pnl, 2),
            pnl_pct=round((realized_pnl / (pos.entry_price * pos.quantity)) * 100, 2),
            entry_time=pos.open_time,
            exit_time=pos.close_time,
            exit_reason=reason,
            hold_duration_min=round(hold_mins, 1)
        )
        self.trade_history.append(trade)
        return trade

    def _update_equity(self):
        """Aktualisiert Equity = Cash + Wert aller offenen Positionen."""
        open_value = sum(
            pos.current_price * pos.quantity
            for pos in self.positions.values()
            if pos.status == "OPEN"
        )
        self.equity = self.cash + open_value

    def _check_new_day(self):
        """Reset Daily P&L wenn neuer Handelstag."""
        today = date.today()
        if today != self._today:
            self.daily_start_equity = self.equity
            self.daily_pnl = 0.0
            self._today = today
            logger.info(f"📅 Neuer Tag — Daily P&L Reset | Equity: ${self.equity:,.2f}")

    # ─────────────────────────────────────────
    # GETTER
    # ─────────────────────────────────────────

    def get_equity(self) -> float:
        return round(self.equity, 2)

    def get_daily_pnl(self) -> float:
        return round(self.daily_pnl, 2)

    def get_daily_pnl_pct(self) -> float:
        if self.daily_start_equity == 0:
            return 0.0
        return round((self.daily_pnl / self.daily_start_equity) * 100, 2)

    def get_open_positions_count(self) -> int:
        return sum(1 for p in self.positions.values() if p.status == "OPEN")

    def get_open_positions(self) -> List[Position]:
        return [p for p in self.positions.values() if p.status == "OPEN"]

    def get_portfolio_summary(self) -> dict:
        open_positions = self.get_open_positions()
        unrealized = sum(p.unrealized_pnl for p in open_positions)
        total_return = ((self.equity - self.initial_capital) / self.initial_capital) * 100
        wins   = [t for t in self.trade_history if t.pnl > 0]
        losses = [t for t in self.trade_history if t.pnl <= 0]
        win_rate = (len(wins) / len(self.trade_history) * 100) if self.trade_history else 0

        return {
            "equity":           self.equity,
            "cash":             self.cash,
            "initial_capital":  self.initial_capital,
            "total_return_pct": round(total_return, 2),
            "daily_pnl":        self.daily_pnl,
            "daily_pnl_pct":    self.get_daily_pnl_pct(),
            "unrealized_pnl":   round(unrealized, 2),
            "open_positions":   len(open_positions),
            "total_trades":     len(self.trade_history),
            "wins":             len(wins),
            "losses":           len(losses),
            "win_rate":         round(win_rate, 1),
            "avg_win":          round(sum(t.pnl for t in wins) / len(wins), 2) if wins else 0,
            "avg_loss":         round(sum(t.pnl for t in losses) / len(losses), 2) if losses else 0,
        }
