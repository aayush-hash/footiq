"""The FastAPI application. Start it with:

    uvicorn app.main:app --reload

Then open http://localhost:8000/docs to see and try every endpoint.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import auth, health, home, matches, nations_league, performance, players, predictions, simulate

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if get_settings().jwt_secret == "change-me" or len(get_settings().jwt_secret) < 32:
        logging.getLogger("footiq").warning("JWT_SECRET is weak. Set a long random one in .env before going online.")
    scheduler = None
    if get_settings().enable_scheduler:
        from app.services.scheduler import start_scheduler
        scheduler = start_scheduler()
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="FOOTIQ API",
    description="Football predictions, simulations and what-if scenarios.",
    version="0.1.0",
    lifespan=lifespan,
)

# Lets the Expo app (and a browser during development) call the API.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(health.router)                        # /health stays short, for hosting checks
for router in (matches.router, simulate.router, auth.router, predictions.router, performance.router,
               home.router, nations_league.router, players.router):
    app.include_router(router, prefix="/api/v1")
