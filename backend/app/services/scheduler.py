"""Day 17: the daily job - fetch new fixtures and results, then refresh predictions.

APScheduler runs it inside the server process, once a day at SCHEDULER_HOUR
(your timezone). Turn it on with ENABLE_SCHEDULER=true in .env.

It costs one API request per competition per day (6 in total), far below
API-Football's free limit of 100.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.database import SessionLocal
from app.services.ingest import sync_all
from app.services.predictor import generate_predictions
from app.services.providers import get_provider

log = logging.getLogger("footiq.scheduler")


def run_daily_update(provider=None) -> dict:
    """Sync every competition, then predict upcoming matches. Safe to run any time."""
    db = SessionLocal()
    try:
        provider = provider or get_provider(get_settings())
        synced = sync_all(db, provider)
        predictions = generate_predictions(db)
        log.info("daily update: synced=%s predictions=%s", synced, predictions)
        return {"synced": synced, "predictions": predictions}
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    settings = get_settings()
    scheduler = BackgroundScheduler(timezone=settings.timezone)
    scheduler.add_job(run_daily_update, CronTrigger(hour=settings.scheduler_hour, minute=0),
                      id="daily_update", replace_existing=True, misfire_grace_time=3600, coalesce=True)
    scheduler.start()
    log.info("scheduler started: daily update at %02d:00 %s", settings.scheduler_hour, settings.timezone)
    return scheduler
