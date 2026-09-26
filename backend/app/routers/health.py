"""Day 14: health check. The first endpoint every backend should have.

Hosting services (and you) call it to ask "is the server alive, and can it
reach the database and the models?"
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.predictor import available_models

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception as error:  # report the problem instead of crashing
        database = f"error: {error.__class__.__name__}"
    models = available_models()
    status = "ok" if database == "ok" and models else "degraded"
    return {"status": status, "database": database, "models": models}
