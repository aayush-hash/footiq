"""Test setup: a separate test database, small fake models, and a fake data provider.

The tests never touch your real database, never call a real API, and never
need your real trained models. They need Docker's Postgres running
(docker compose up -d), because the test database lives in it.
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

TEST_DB = "footiq_test"


def _database_server() -> str:
    """Same server as your .env DATABASE_URL (so a changed port like 5433 just works),
    but a separate database called footiq_test."""
    if os.environ.get("TEST_DATABASE_SERVER"):
        return os.environ["TEST_DATABASE_SERVER"]
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.strip().startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip().rsplit("/", 1)[0]
    return "postgresql+psycopg://footiq:footiq@localhost:5432"


BASE_URL = _database_server()
os.environ["DATABASE_URL"] = f"{BASE_URL}/{TEST_DB}"
os.environ["JWT_SECRET"] = "test-secret-that-is-at-least-32-bytes-long"
os.environ["ENABLE_SCHEDULER"] = "false"


def _create_test_database():
    from sqlalchemy import create_engine, text
    admin = create_engine(f"{BASE_URL}/postgres", isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        if not conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": TEST_DB}):
            conn.execute(text(f"CREATE DATABASE {TEST_DB}"))
    admin.dispose()


@pytest.fixture(scope="session")
def models_dir(tmp_path_factory):
    """Train tiny models on fake data, with real-looking team names."""
    from footiq.elo import EloGoalsModel, EloRatings
    from footiq.models import DixonColesModel
    from footiq.synthetic import make_league

    path = tmp_path_factory.mktemp("models")
    matches, _ = make_league(n_teams=6, n_seasons=2, seed=1)
    names = {f"Team {c}": n for c, n in zip("ABCDEF", ["Man City", "Arsenal", "Liverpool", "Chelsea", "Wolves", "Brentford"])}
    matches["home_team"] = matches["home_team"].map(names)
    matches["away_team"] = matches["away_team"].map(names)
    DixonColesModel().fit(matches).save(path / "E0_dixon_coles.json")
    elo = EloRatings(k=20, home_advantage=65)
    EloGoalsModel(elo).fit(elo.run(matches)).save(path / "E0_elo.json")

    intl = EloRatings(home_advantage=100)
    intl.ratings = {"Spain": 2300.0, "England": 2200.0, "Czech Republic": 1750.0, "Croatia": 1950.0}
    intl.last_date = datetime(2026, 8, 26)
    EloGoalsModel(intl).save(path / "international_elo.json")
    os.environ["MODELS_DIR"] = str(path)
    return path


@pytest.fixture(scope="session")
def engine(models_dir):
    _create_test_database()
    from app.config import get_settings
    get_settings.cache_clear()
    from app.database import Base, engine
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture
def db(engine):
    """A clean database for every test."""
    from app.database import Base, SessionLocal
    from app.services.predictor import reload_models
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    reload_models()
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


class FakeProvider:
    """Pretends to be API-Football, with fixtures we choose."""

    name = "fake"

    def __init__(self, fixtures_by_code):
        self.fixtures_by_code = fixtures_by_code
        self.calls = 0

    def fixtures(self, competition, season):
        self.calls += 1
        return self.fixtures_by_code.get(competition["code"], [])

    def status(self):
        return {"ok": True}

    # Day 28
    squads: dict = {}
    scorer_rows: dict = {}

    def squad(self, team_external_id):
        self.calls += 1
        return self.squads.get(team_external_id, [])

    def scorers(self, competition, season, limit=50):
        self.calls += 1
        return self.scorer_rows.get(competition["code"], [])


def make_fixture(ext, home, away, days=2, status="scheduled", hg=None, ag=None, home_id=None, away_id=None):
    from app.services.providers import FixtureData
    return FixtureData(
        external_id=f"fake:{ext}", kickoff=datetime.now(timezone.utc) + timedelta(days=days), status=status,
        home_id=home_id or f"fake:{home}", home_name=home, away_id=away_id or f"fake:{away}", away_name=away,
        home_goals=hg, away_goals=ag, round="Regular Season - 6",
    )


@pytest.fixture
def provider():
    return FakeProvider({
        "E0": [
            make_fixture(1, "Manchester City", "Arsenal", days=1),
            make_fixture(2, "Liverpool", "Chelsea", days=2),
            make_fixture(3, "Wolverhampton Wanderers", "Brentford", days=-3, status="finished", hg=1, ag=2),
            make_fixture(4, "Sunderland", "Chelsea", days=3),  # a team the model has never seen
        ],
        "UNL": [
            make_fixture(10, "England", "Spain", days=1),
            make_fixture(11, "Czechia", "Croatia", days=-1, status="finished", hg=0, ag=2,
                         home_id="fake:CZE", away_id="fake:CRO"),
        ],
    })


# ---------- Week 4 helpers ----------

@pytest.fixture
def auth(client):
    """Register a user and return a function that gives login headers: auth("aayush")."""
    def make(username="aayush"):
        client.post("/api/v1/auth/register", json={"email": f"{username}@example.com", "username": username,
                                                   "password": "goals1234"})
        token = client.post("/api/v1/auth/login", data={"username": username, "password": "goals1234"}).json()["access_token"]
        return {"Authorization": f"Bearer {token}"}
    return make


def finish(db, external_id, home_goals, away_goals):
    """Pretend a match just ended with this score."""
    from sqlalchemy import select
    from app.models import Match
    match = db.scalar(select(Match).where(Match.external_id == external_id))
    match.status, match.home_goals, match.away_goals = "finished", home_goals, away_goals
    match.kickoff = datetime.now(timezone.utc) - timedelta(hours=2)
    db.commit()
    return match
