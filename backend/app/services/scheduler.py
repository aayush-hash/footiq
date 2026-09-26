"""Day 17: the daily job - fetch new fixtures and results, then refresh predictions.
Week 4 adds: score finished matches (Day 23), update top scorers (Day 28), and a
weekly job for full squads (Day 28).

APScheduler runs it inside the server process, once a day at SCHEDULER_HOUR
(your timezone). Turn it on with ENABLE_SCHEDULER=true in .env.

Cost per day: one request per competition for fixtures, plus one per league
for top scorers. Well within football-data.org's free limit.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.database import SessionLocal
from app.services.ingest import sync_all
from app.services.players import sync_scorers, sync_squads
from app.services.predictor import generate_predictions
from app.services.providers import get_provider
from app.services.scoring import score_finished_matches

log = logging.getLogger("footiq.scheduler")


def run_daily_update(provider=None) -> dict:
    """Sync every competition, then predict upcoming matches. Safe to run any time."""
    db = SessionLocal()
    try:
        provider = provider or get_provider(get_settings())
        synced = sync_all(db, provider)
        scored = score_finished_matches(db)          # before predicting: uses the frozen predictions
        predictions = generate_predictions(db)
        scorers = sync_scorers(db, provider) if provider.name == "football_data_org" else []
        log.info("daily update: synced=%s scored=%s predictions=%s scorers=%s", synced, scored, predictions, scorers)
        return {"synced": synced, "scored": scored, "predictions": predictions, "scorers": scorers}
    finally:
        db.close()


def run_weekly_squads(provider=None) -> dict:
    db = SessionLocal()
    try:
        provider = provider or get_provider(get_settings())
        result = sync_squads(db, provider, progress=log.info)
        log.info("weekly squads: %s", {k: v for k, v in result.items() if k != "errors"})
        return result
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    settings = get_settings()
    scheduler = BackgroundScheduler(timezone=settings.timezone)
    scheduler.add_job(run_daily_update, CronTrigger(hour=settings.scheduler_hour, minute=0),
                      id="daily_update", replace_existing=True, misfire_grace_time=3600, coalesce=True)
    if settings.data_provider == "football_data_org":
        scheduler.add_job(run_weekly_squads, CronTrigger(day_of_week="mon", hour=(settings.scheduler_hour + 1) % 24),
                          id="weekly_squads", replace_existing=True, misfire_grace_time=3600, coalesce=True)
    scheduler.start()
    log.info("scheduler started: daily update at %02d:00 %s", settings.scheduler_hour, settings.timezone)
    return scheduler
