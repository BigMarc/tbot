"""risk_manager.py — Risk Management Engine"""
from dataclasses import dataclass
from loguru import logger

@dataclass
class SizeResult:
    shares: int
    dollar_risk: float
    dollar_reward: float
    position_value: float
    risk_pct: float
    allowed: bool
    reason: str = ""

class RiskManager:
    def __init__(self, capital=50000, risk_per_trade=0.01,
                 max_daily_loss_pct=0.03, max_open_positions=3, min_rr=2.5):
        self.initial_capital    = capital
        self.current_capital    = capital
        self.risk_per_trade     = risk_per_trade
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_open_positions = max_open_positions
        self.min_rr             = min_rr
        self._daily_pnl         = 0.0
        self._bot_paused        = False
        self._open_positions    = 0

    def update_capital(self, v): self.current_capital = v
    def update_open_positions(self, n): self._open_positions = n
    def resume(self): self._bot_paused = False

    def update_daily_pnl(self, pnl):
        self._daily_pnl = pnl
        if pnl / self.initial_capital <= -self.max_daily_loss_pct and not self._bot_paused:
            self._bot_paused = True
            logger.warning(f"Daily loss limit hit ({pnl/self.initial_capital*100:.1f}%) — paused")

    def reset_daily(self):
        self._daily_pnl = 0.0
        self._bot_paused = False

    def is_trading_allowed(self):
        if self._bot_paused:
            return False, f"Daily loss limit reached ({abs(self._daily_pnl/self.initial_capital)*100:.1f}%)"
        if self._open_positions >= self.max_open_positions:
            return False, f"Max positions ({self.max_open_positions}) reached"
        return True, "ok"

    def calculate_position_size(self, entry_price, stop_loss, take_profit, direction):
        allowed, reason = self.is_trading_allowed()
        if not allowed:
            return SizeResult(0,0,0,0,0,False,reason)
        risk_per_share = abs(entry_price - stop_loss)
        if risk_per_share <= 0:
            return SizeResult(0,0,0,0,0,False,"Zero risk per share")
        reward_per_share = abs(take_profit - entry_price)
        rr = reward_per_share / risk_per_share
        if rr < self.min_rr:
            return SizeResult(0,0,0,0,0,False,f"RR {rr:.2f} < min {self.min_rr}")
        dollar_risk = self.current_capital * self.risk_per_trade
        shares = int(dollar_risk / risk_per_share)
        if shares <= 0:
            return SizeResult(0,0,0,0,0,False,"0 shares")
        actual_risk = shares * risk_per_share
        actual_reward = shares * reward_per_share
        logger.info(f"Position size: {shares} shares | Risk=${actual_risk:.0f} ({actual_risk/self.current_capital*100:.1f}%) | Reward=${actual_reward:.0f} | RR=1:{rr:.1f}")
        return SizeResult(shares=shares, dollar_risk=round(actual_risk,2),
                         dollar_reward=round(actual_reward,2),
                         position_value=round(shares*entry_price,2),
                         risk_pct=round(actual_risk/self.current_capital,4),
                         allowed=True, reason="ok")

    def status_dict(self):
        return {"capital": round(self.current_capital,2),
                "daily_pnl": round(self._daily_pnl,2),
                "daily_pnl_pct": round(self._daily_pnl/self.initial_capital*100,2),
                "open_positions": self._open_positions,
                "paused": self._bot_paused,
                "daily_limit_pct": self.max_daily_loss_pct*100,
                "risk_per_trade": self.risk_per_trade*100}
