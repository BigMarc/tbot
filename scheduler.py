"""scheduler.py — Session-Aware Trading Scheduler"""
from datetime import datetime, time as dt_time
from typing import Optional, Callable
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

SESSION_WINDOWS = {
    "london":  (dt_time(9,  0), dt_time(12, 0)),
    "overlap": (dt_time(14,30), dt_time(16,30)),
    "ny_open": (dt_time(15,30), dt_time(17,30)),
}
TZ_CET = pytz.timezone("Europe/Berlin")

def get_current_session():
    now = datetime.now(TZ_CET).time()
    for name, (start, end) in SESSION_WINDOWS.items():
        if start <= now <= end:
            return name
    return None

def is_trading_day():
    return datetime.now(TZ_CET).weekday() < 5

def is_in_any_session():
    return get_current_session() is not None

class TradingScheduler:
    def __init__(self, scan_interval_min=5, position_check_min=1, timezone="Europe/Berlin"):
        self.scan_interval   = scan_interval_min
        self.position_check  = position_check_min
        self.timezone        = timezone
        self._scheduler      = BackgroundScheduler(timezone=timezone)
        self._scan_fn        = None
        self._monitor_fn     = None
        self._briefing_fn    = None
        self._eod_fn         = None
        self._daily_reset_fn = None

    def register(self, on_scan=None, on_monitor=None, on_briefing=None, on_eod=None, on_daily_reset=None):
        self._scan_fn=on_scan; self._monitor_fn=on_monitor
        self._briefing_fn=on_briefing; self._eod_fn=on_eod
        self._daily_reset_fn=on_daily_reset

    def start(self):
        if self._scan_fn:
            self._scheduler.add_job(self._guarded_scan,IntervalTrigger(minutes=self.scan_interval),
                id="signal_scan",max_instances=1,coalesce=True,misfire_grace_time=60)
        if self._monitor_fn:
            self._scheduler.add_job(self._monitor_fn,IntervalTrigger(minutes=self.position_check),
                id="pos_monitor",max_instances=1,coalesce=True,misfire_grace_time=30)
        if self._briefing_fn:
            self._scheduler.add_job(self._briefing_fn,CronTrigger(hour=9,minute=0,day_of_week="mon-fri",timezone=self.timezone),id="briefing")
        if self._eod_fn:
            self._scheduler.add_job(self._eod_fn,CronTrigger(hour=22,minute=15,day_of_week="mon-fri",timezone=self.timezone),id="eod")
        if self._daily_reset_fn:
            self._scheduler.add_job(self._daily_reset_fn,CronTrigger(hour=0,minute=1,day_of_week="mon-fri",timezone=self.timezone),id="reset")
        self._scheduler.start()
        logger.info(f"TradingScheduler started | scan={self.scan_interval}min | monitor={self.position_check}min")

    def stop(self): self._scheduler.shutdown(wait=False)

    def _guarded_scan(self):
        if not is_trading_day(): return
        session = get_current_session()
        if session is None: return
        if self._scan_fn:
            try: self._scan_fn(session)
            except Exception as e: logger.error(f"Scan error: {e}")
