"""trade_journal.py — SQLite Trade Journal"""
import json
from datetime import date, datetime
from typing import Optional
from sqlalchemy import Boolean,Column,DateTime,Float,Integer,String,Text,create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from loguru import logger

class Base(DeclarativeBase): pass

class TradeRecord(Base):
    __tablename__ = "trades"
    id=Column(Integer,primary_key=True,autoincrement=True)
    symbol=Column(String(10),nullable=False)
    direction=Column(String(5),nullable=False)
    entry_price=Column(Float,nullable=False)
    stop_loss=Column(Float,nullable=False)
    take_profit=Column(Float,nullable=False)
    risk_reward=Column(Float,nullable=False)
    shares=Column(Integer,nullable=False)
    dollar_risk=Column(Float,nullable=False)
    entry_time=Column(DateTime,nullable=False)
    exit_time=Column(DateTime,nullable=True)
    exit_price=Column(Float,nullable=True)
    pnl=Column(Float,nullable=True)
    pnl_pct=Column(Float,nullable=True)
    status=Column(String(10),default="open")
    close_reason=Column(String(20),nullable=True)
    session=Column(String(20),nullable=True)
    entry_timeframe=Column(String(10),nullable=True)
    setup_grade=Column(String(2),nullable=True)
    confluence_json=Column(Text,nullable=True)
    aoi_level=Column(Float,nullable=True)
    bias_strength=Column(Integer,nullable=True)

class SignalLog(Base):
    __tablename__="signal_log"
    id=Column(Integer,primary_key=True,autoincrement=True)
    timestamp=Column(DateTime,nullable=False)
    symbol=Column(String(10))
    direction=Column(String(5))
    grade=Column(String(2))
    taken=Column(Boolean,default=False)
    skip_reason=Column(String(100),nullable=True)
    entry_price=Column(Float,nullable=True)

class DailySummary(Base):
    __tablename__="daily_summary"
    id=Column(Integer,primary_key=True,autoincrement=True)
    trade_date=Column(String(10),unique=True)
    total_trades=Column(Integer,default=0)
    winning_trades=Column(Integer,default=0)
    losing_trades=Column(Integer,default=0)
    gross_pnl=Column(Float,default=0.0)
    win_rate=Column(Float,default=0.0)
    best_trade=Column(Float,default=0.0)
    worst_trade=Column(Float,default=0.0)
    capital_eod=Column(Float,nullable=True)

class TradeJournal:
    def __init__(self, db_path="trade_journal.db"):
        self.engine=create_engine(f"sqlite:///{db_path}",echo=False)
        Base.metadata.create_all(self.engine)
        self.SessionLocal=sessionmaker(bind=self.engine)
        logger.info(f"TradeJournal initialized: {db_path}")

    def _s(self): return self.SessionLocal()

    def open_trade(self,symbol,direction,entry_price,stop_loss,take_profit,
                   risk_reward,shares,dollar_risk,session_name,entry_timeframe,
                   setup_grade,confluence,aoi_level,bias_strength):
        with self._s() as db:
            r=TradeRecord(symbol=symbol,direction=direction,entry_price=entry_price,
                stop_loss=stop_loss,take_profit=take_profit,risk_reward=risk_reward,
                shares=shares,dollar_risk=dollar_risk,entry_time=datetime.utcnow(),
                status="open",session=session_name,entry_timeframe=entry_timeframe,
                setup_grade=setup_grade,confluence_json=json.dumps(confluence),
                aoi_level=aoi_level,bias_strength=bias_strength)
            db.add(r); db.commit(); db.refresh(r)
            tid=r.id
            logger.info(f"Trade #{tid} opened: {direction} {symbol} @ {entry_price}")
            return tid

    def close_trade(self,trade_id,exit_price,close_reason,capital_at_close):
        with self._s() as db:
            r=db.query(TradeRecord).filter_by(id=trade_id,status="open").first()
            if not r: return None
            pnl=(exit_price-r.entry_price)*r.shares if r.direction=="LONG" else (r.entry_price-exit_price)*r.shares
            pnl_pct=pnl/(r.entry_price*r.shares)*100
            r.exit_price=exit_price; r.exit_time=datetime.utcnow()
            r.pnl=round(pnl,2); r.pnl_pct=round(pnl_pct,2)
            r.status="closed"; r.close_reason=close_reason
            db.commit()
            logger.info(f"Trade #{trade_id} closed @ {exit_price:.2f} | PnL=${pnl:.2f} ({'WIN' if pnl>0 else 'LOSS'})")
            self._update_daily(pnl,capital_at_close)
            return pnl

    def _update_daily(self,pnl,capital):
        today=str(date.today())
        with self._s() as db:
            s=db.query(DailySummary).filter_by(trade_date=today).first()
            if not s: s=DailySummary(trade_date=today); db.add(s)
            s.total_trades=(s.total_trades or 0)+1
            s.gross_pnl=round((s.gross_pnl or 0)+pnl,2)
            s.capital_eod=round(capital,2)
            if pnl>0: s.winning_trades=(s.winning_trades or 0)+1; s.best_trade=max(s.best_trade or 0,pnl)
            else: s.losing_trades=(s.losing_trades or 0)+1; s.worst_trade=min(s.worst_trade or 0,pnl)
            if s.total_trades: s.win_rate=round(s.winning_trades/s.total_trades*100,1)
            db.commit()

    def get_open_trades(self):
        with self._s() as db: return db.query(TradeRecord).filter_by(status="open").all()

    def get_open_trades_count(self):
        with self._s() as db: return db.query(TradeRecord).filter_by(status="open").count()

    def log_signal(self,symbol,direction,grade,taken,skip_reason="",entry_price=None):
        with self._s() as db:
            db.add(SignalLog(timestamp=datetime.utcnow(),symbol=symbol,direction=direction,
                grade=grade,taken=taken,skip_reason=skip_reason,entry_price=entry_price))
            db.commit()

    def get_daily_pnl(self):
        with self._s() as db:
            s=db.query(DailySummary).filter_by(trade_date=str(date.today())).first()
            return float(s.gross_pnl) if s and s.gross_pnl else 0.0

    def get_all_closed_trades(self,limit=50):
        with self._s() as db:
            return db.query(TradeRecord).filter_by(status="closed").order_by(TradeRecord.exit_time.desc()).limit(limit).all()

    def get_stats_summary(self):
        with self._s() as db:
            closed=db.query(TradeRecord).filter_by(status="closed").all()
            open_=db.query(TradeRecord).filter_by(status="open").all()
            if not closed: return {"total_closed":0,"open":len(open_),"total_pnl":0,"win_rate":0,"avg_win":0,"avg_loss":0,"best_trade":0,"worst_trade":0}
            pnls=[t.pnl for t in closed if t.pnl is not None]
            wins=[p for p in pnls if p>0]; losses=[p for p in pnls if p<=0]
            return {"total_closed":len(closed),"open":len(open_),"total_pnl":round(sum(pnls),2),
                    "win_rate":round(len(wins)/len(pnls)*100,1) if pnls else 0,
                    "avg_win":round(sum(wins)/len(wins) if wins else 0,2),
                    "avg_loss":round(sum(losses)/len(losses) if losses else 0,2),
                    "best_trade":round(max(pnls),2) if pnls else 0,
                    "worst_trade":round(min(pnls),2) if pnls else 0}
