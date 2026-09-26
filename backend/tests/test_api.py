from sqlalchemy import select

from app.models import Match, Prediction, Team
from app.services.ingest import sync_all
from app.services.predictor import generate_predictions, get_model
from app.services.team_names import resolve, simplify


# ---------- Day 14: health ----------

def test_health(client):
    body = client.get("/health").json()
    assert body["database"] == "ok"
    assert "E0_dixon_coles" in body["models"] and "international_elo" in body["models"]
    assert body["status"] == "ok"


# ---------- Day 16: team names and ingest ----------

def test_team_name_matching():
    known = ["Man City", "Arsenal", "Nott'm Forest", "Bayern Munich", "Czech Republic", "Wolves"]
    assert resolve("Manchester City", known) == "Man City"      # alias file
    assert resolve("Arsenal FC", known) == "Arsenal"            # simplified
    assert resolve("FC Bayern München", known) == "Bayern Munich"
    assert resolve("Czechia", known) == "Czech Republic"        # country alias
    assert resolve("Sunderland", known) is None                 # unknown stays unknown
    assert simplify("1. FC Köln") == "koln"


def test_sync_saves_fixtures_without_duplicates(db, provider):
    first = sync_all(db, provider, ["E0", "UNL"])
    assert {r["league"]: r["created"] for r in first} == {"E0": 4, "UNL": 2}
    second = sync_all(db, provider, ["E0", "UNL"])  # running again only updates
    assert {r["league"]: r["created"] for r in second} == {"E0": 0, "UNL": 0}
    assert len(db.scalars(select(Match)).all()) == 6
    city = db.scalar(select(Team).where(Team.name == "Manchester City"))
    assert city.model_name == "Man City"
    assert db.scalar(select(Team).where(Team.name == "Sunderland")).model_name is None


def test_one_broken_league_does_not_stop_the_rest(db, provider):
    class Broken(type(provider)):
        def fixtures(self, competition, season):
            if competition["code"] == "E0":
                raise RuntimeError("API is down")
            return super().fixtures(competition, season)
    results = sync_all(db, Broken(provider.fixtures_by_code), ["E0", "UNL"])
    assert "error" in results[0] and results[1]["created"] == 2


# ---------- Day 17: predictions job ----------

def test_generate_predictions(db, provider):
    sync_all(db, provider, ["E0", "UNL"])
    report = generate_predictions(db)
    assert report["predicted"] == 3            # 2 club matches + England v Spain
    assert report["skipped_unknown_teams"] == 1  # Sunderland
    assert report["new_international_results"] == 1  # Czechia 0-2 Croatia moved the Elo ratings
    preds = db.scalars(select(Prediction)).all()
    assert {p.model for p in preds} == {"dixon_coles", "elo"}
    for p in preds:
        assert abs(p.home_win + p.draw + p.away_win - 1) < 1e-6


def test_finished_matches_are_never_re_predicted(db, provider):
    sync_all(db, provider, ["E0"])
    generate_predictions(db)
    finished = db.scalar(select(Match).where(Match.status == "finished"))
    assert not finished.predictions


def test_international_result_moves_elo(db, provider):
    before = get_model("international").ratings.rating("Croatia")
    sync_all(db, provider, ["UNL"])
    generate_predictions(db)
    assert get_model("international").ratings.rating("Croatia") > before
    generate_predictions(db)  # running again must not count the same result twice
    after_twice = get_model("international").ratings.rating("Croatia")
    generate_predictions(db)
    assert get_model("international").ratings.rating("Croatia") == after_twice


# ---------- Day 18: matches endpoints ----------

def test_list_and_filter_matches(client, db, provider):
    sync_all(db, provider, ["E0", "UNL"])
    generate_predictions(db)
    assert len(client.get("/api/v1/matches").json()) == 6
    assert len(client.get("/api/v1/matches", params={"league": "UNL"}).json()) == 2
    assert len(client.get("/api/v1/matches", params={"status": "finished"}).json()) == 2
    leagues = client.get("/api/v1/leagues").json()
    assert "E0" in [lg["code"] for lg in leagues]
    assert client.get("/api/v1/matches", params={"status": "nonsense"}).status_code == 422
    assert client.get("/api/v1/matches", params={"date": "2026-09-26", "tz": "Mars/Base"}).status_code == 400


def test_match_detail_includes_predictions(client, db, provider):
    sync_all(db, provider, ["E0"])
    generate_predictions(db)
    match = db.scalar(select(Match).where(Match.external_id == "fake:1"))
    body = client.get(f"/api/v1/matches/{match.id}").json()
    assert body["home_team"]["name"] == "Manchester City"
    assert {p["model"] for p in body["predictions"]} == {"dixon_coles", "elo"}
    pred = client.get(f"/api/v1/matches/{match.id}/prediction", params={"model": "elo"}).json()
    assert 0 < pred["home_win"] < 1 and len(pred["top_scorelines"]) == 5
    assert client.get("/api/v1/matches/999999").status_code == 404


# ---------- Day 19: simulate ----------

def test_simulate_match(client, db, provider):
    sync_all(db, provider, ["E0"])
    match = db.scalar(select(Match).where(Match.external_id == "fake:1"))
    kickoff = client.post(f"/api/v1/matches/{match.id}/simulate", json={}).json()
    late_lead = client.post(f"/api/v1/matches/{match.id}/simulate",
                            json={"minute": 85, "home_goals": 2, "away_goals": 0}).json()
    assert late_lead["probabilities"]["home_win"] > 0.9 > kickoff["probabilities"]["home_win"]
    red = client.post(f"/api/v1/matches/{match.id}/simulate", json={"minute": 20, "home_red_cards": 1}).json()
    assert red["probabilities"]["home_win"] < kickoff["probabilities"]["home_win"]
    bad = client.post(f"/api/v1/matches/{match.id}/simulate", json={"minute": 120})
    assert bad.status_code == 422


def test_simulate_any_teams(client):
    r = client.post("/api/v1/simulate", json={"competition": "international", "home_team": "Spain",
                                               "away_team": "Czech Republic", "neutral": True})
    assert r.status_code == 200 and r.json()["probabilities"]["home_win"] > 0.6
    unknown = client.post("/api/v1/simulate", json={"competition": "E0", "home_team": "Arsenal", "away_team": "Narnia FC"})
    assert unknown.status_code == 422
    bad_model = client.post("/api/v1/simulate", json={"competition": "E0", "home_team": "Arsenal",
                                                      "away_team": "Chelsea", "model": "magic"})
    assert bad_model.status_code == 400


# ---------- Day 20: auth ----------

def test_register_login_me(client):
    r = client.post("/api/v1/auth/register", json={"email": "Aayush@Example.com", "username": "aayush", "password": "goals1234"})
    assert r.status_code == 201 and "password" not in str(r.json())
    assert client.post("/api/v1/auth/register", json={"email": "aayush@example.com", "username": "other",
                                                      "password": "goals1234"}).status_code == 409
    token = client.post("/api/v1/auth/login", data={"username": "aayush@example.com", "password": "goals1234"}).json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["username"] == "aayush"
    # username works too, case-insensitive
    assert client.post("/api/v1/auth/login", data={"username": "AAYUSH", "password": "goals1234"}).status_code == 200


def test_bad_logins_and_tokens(client):
    client.post("/api/v1/auth/register", json={"email": "a@b.com", "username": "abc", "password": "goals1234"})
    assert client.post("/api/v1/auth/login", data={"username": "a@b.com", "password": "wrong-pass"}).status_code == 401
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer fake.token.here"}).status_code == 401
    short = client.post("/api/v1/auth/register", json={"email": "c@d.com", "username": "cde", "password": "short"})
    assert short.status_code == 422


def test_promoted_team_can_be_predicted_after_naming_it(db, provider):
    """A team the model has never seen (e.g. just promoted) is skipped until you give it
    a model name. The models then treat it like the weakest teams they know."""
    sync_all(db, provider, ["E0"])
    assert generate_predictions(db)["skipped_unknown_teams"] == 1
    sunderland = db.scalar(select(Team).where(Team.name == "Sunderland"))
    sunderland.model_name = "Sunderland"
    db.commit()
    sync_all(db, provider, ["E0"])  # a later sync must keep the name you set
    assert db.scalar(select(Team).where(Team.name == "Sunderland")).model_name == "Sunderland"
    report = generate_predictions(db)
    assert report["skipped_unknown_teams"] == 0 and report["predicted"] == 3
    match = db.scalar(select(Match).where(Match.external_id == "fake:4"))
    dc = next(p for p in match.predictions if p.model == "dixon_coles")
    assert dc.away_win > dc.home_win  # weak new side at home to Chelsea


def test_daily_job(db, provider):
    from app.services.scheduler import run_daily_update
    report = run_daily_update(provider)
    assert provider.calls == 6  # one request per competition
    assert report["predictions"]["predicted"] == 3
