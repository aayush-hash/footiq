"""Week 4 tests: predictions, scoring, leaderboard, Fan vs AI, transparency,
favorites and home, Nations League, and players."""

from datetime import date

import pytest
from sqlalchemy import select

from app.models import Match, Team, UserPrediction
from app.services.ingest import sync_all
from app.services.predictor import generate_predictions
from app.services.scoring import POINTS, ai_pick, score_finished_matches, score_prediction, streaks
from tests.conftest import finish, make_fixture


def match_id(db, external_id):
    return db.scalar(select(Match.id).where(Match.external_id == external_id))


# ---------- Day 23: scoring rules ----------

@pytest.mark.parametrize("pred, real, expected", [
    ((2, 1), (2, 1), {"result", "goal_difference", "exact_score", "over_under"}),   # perfect
    ((2, 0), (3, 1), {"result", "goal_difference"}),                                 # right margin, 2 vs 4 goals
    ((1, 0), (3, 0), {"result", "over_under"} - {"over_under"}),                     # right winner only
    ((1, 1), (2, 2), {"draw", "over_under"} - {"over_under"}),                       # draw, 2 vs 4 goals
    ((0, 0), (0, 0), {"draw", "exact_score", "over_under"}),                          # exact draw
    ((2, 1), (1, 2), {"over_under"}),                                                 # wrong winner, 3 goals both
    ((0, 1), (3, 0), set()),                                                          # nothing
])
def test_scoring_rules(pred, real, expected):
    points, breakdown = score_prediction(*pred, *real)
    assert set(breakdown) == expected
    assert points == sum(POINTS[k] for k in expected)


def test_best_possible_scores():
    assert score_prediction(2, 1, 2, 1)[0] == 5 + 8 + 15 + 5
    assert score_prediction(1, 1, 1, 1)[0] == 7 + 15 + 5


def test_streaks():
    class P:
        def __init__(self, bd): self.breakdown = bd
    history = [P({"result": 5}), P({"draw": 7}), P({}), P({"result": 5}), P({"result": 5}), P({"result": 5})]
    assert streaks(history) == {"current": 3, "best": 3}
    assert streaks(history + [P({"over_under": 5})]) == {"current": 0, "best": 3}


# ---------- Day 22: making predictions ----------

def test_predict_change_and_lock(client, db, provider, auth):
    sync_all(db, provider, ["E0"])
    headers = auth()
    upcoming, finished = match_id(db, "fake:1"), match_id(db, "fake:3")

    r = client.put(f"/api/v1/matches/{upcoming}/my-prediction", json={"home_goals": 2, "away_goals": 1}, headers=headers)
    assert r.status_code == 200 and r.json()["points"] is None
    r = client.put(f"/api/v1/matches/{upcoming}/my-prediction", json={"home_goals": 3, "away_goals": 1}, headers=headers)
    assert r.json()["home_goals"] == 3  # changed, not duplicated
    assert len(db.scalars(select(UserPrediction)).all()) == 1

    locked = client.put(f"/api/v1/matches/{finished}/my-prediction", json={"home_goals": 1, "away_goals": 2}, headers=headers)
    assert locked.status_code == 409
    assert client.put(f"/api/v1/matches/{upcoming}/my-prediction", json={"home_goals": 1, "away_goals": 0}).status_code == 401
    assert client.put(f"/api/v1/matches/{upcoming}/my-prediction", json={"home_goals": -1, "away_goals": 0},
                      headers=headers).status_code == 422
    assert client.delete(f"/api/v1/matches/{upcoming}/my-prediction", headers=headers).status_code == 204
    assert client.get(f"/api/v1/matches/{upcoming}/my-prediction", headers=headers).status_code == 404


def test_kickoff_time_locks_even_if_status_not_updated(client, db, auth):
    from tests.conftest import FakeProvider
    late = FakeProvider({"E0": [make_fixture(50, "Manchester City", "Arsenal", days=-1, status="scheduled")]})
    sync_all(db, late, ["E0"])
    r = client.put(f"/api/v1/matches/{match_id(db, 'fake:50')}/my-prediction",
                   json={"home_goals": 1, "away_goals": 0}, headers=auth())
    assert r.status_code == 409


# ---------- Days 23-24: scoring, leaderboard, Fan vs AI ----------

@pytest.fixture
def played_round(client, db, provider, auth):
    """Two fans predict two matches; both matches finish; everything is scored."""
    sync_all(db, provider, ["E0"])
    generate_predictions(db)  # FOOTIQ's predictions, frozen before kickoff
    a, b = auth("aayush"), auth("sita")
    m1, m2 = match_id(db, "fake:1"), match_id(db, "fake:2")
    client.put(f"/api/v1/matches/{m1}/my-prediction", json={"home_goals": 2, "away_goals": 1}, headers=a)
    client.put(f"/api/v1/matches/{m2}/my-prediction", json={"home_goals": 1, "away_goals": 1}, headers=a)
    client.put(f"/api/v1/matches/{m1}/my-prediction", json={"home_goals": 0, "away_goals": 3}, headers=b)
    finish(db, "fake:1", 2, 1)
    finish(db, "fake:2", 0, 0)
    assert score_finished_matches(db) == {"scored": 3}
    assert score_finished_matches(db) == {"scored": 0}  # never scored twice
    return {"aayush": a, "sita": b}


def test_scoring_awards_fans_and_ai(db, played_round):
    rows = {(up.user.username, up.match.external_id): up for up in db.scalars(select(UserPrediction))}
    exact = rows[("aayush", "fake:1")]
    assert exact.points == 33 and "exact_score" in exact.breakdown
    assert rows[("aayush", "fake:2")].points == 7 + 5  # draw right, under 2.5 right
    assert rows[("sita", "fake:1")].points == 5        # wrong winner, but 3 goals predicted and 3 scored: over 2.5
    assert exact.ai_score is not None and exact.ai_points is not None


def test_ai_pick_uses_the_most_likely_result(db, provider):
    sync_all(db, provider, ["E0"])
    generate_predictions(db)
    match = db.scalar(select(Match).where(Match.external_id == "fake:1"))
    pred = next(p for p in match.predictions if p.model == "dixon_coles")
    h, a = ai_pick(match)
    best = max({"H": pred.home_win, "D": pred.draw, "A": pred.away_win}.items(), key=lambda kv: kv[1])[0]
    assert ("H" if h > a else "A" if h < a else "D") == best


def test_leaderboard_and_my_stats(client, played_round):
    board = client.get("/api/v1/leaderboard").json()
    assert [r["username"] for r in board["rows"]] == ["aayush", "sita"]
    assert board["rows"][0]["points"] == 45 and board["rows"][0]["exact_scores"] == 1
    assert board["me"] is None
    mine = client.get("/api/v1/leaderboard", headers=played_round["sita"]).json()["me"]
    assert mine["rank"] == 2
    assert client.get("/api/v1/leaderboard", params={"league": "SP1"}).json()["rows"] == []

    stats = client.get("/api/v1/me/stats", headers=played_round["aayush"]).json()
    assert stats["points"] == 45 and stats["rank"] == 1
    assert stats["streak"] == {"current": 2, "best": 2}
    assert stats["correct_results"] == 2 and stats["exact_scores"] == 1


def test_fan_vs_ai(client, played_round):
    mine = client.get("/api/v1/me/fan-vs-ai", headers=played_round["aayush"]).json()
    assert mine["matches"] == 2 and mine["fan_wins"] + mine["ai_wins"] + mine["ties"] == 2
    everyone = client.get("/api/v1/fan-vs-ai").json()
    assert everyone["matches"] == 3


# ---------- Day 25: transparency ----------

def test_model_performance(client, played_round):
    body = client.get("/api/v1/model-performance").json()
    live = body["live"]
    assert live["matches"] == 2 and live["reliable"] is False and "note" in live
    assert 0 <= live["accuracy"] <= 1 and live["brier"] >= 0 and "baseline" in live
    assert "E0" in live["by_league"]
    assert client.get("/api/v1/model-performance", params={"model": "magic"}).status_code == 422


def test_model_performance_with_no_data(client):
    live = client.get("/api/v1/model-performance").json()["live"]
    assert live["matches"] == 0 and live["reliable"] is False


# ---------- Day 26: favorites and home ----------

def test_favorites_and_home(client, db, provider, auth):
    sync_all(db, provider, ["E0", "UNL"])
    generate_predictions(db)
    headers = auth()
    city = db.scalar(select(Team).where(Team.name == "Manchester City"))

    teams = client.get("/api/v1/teams", params={"league": "E0", "search": "man"}).json()
    assert [t["name"] for t in teams] == ["Manchester City"]

    home = client.get("/api/v1/me/home", headers=headers).json()
    assert home["has_favorites"] is False and home["favorite_matches"] == []

    r = client.put("/api/v1/me/favorites", json={"team_ids": [city.id], "league_codes": ["UNL"]}, headers=headers)
    assert [t["name"] for t in r.json()["teams"]] == ["Manchester City"]
    assert client.put("/api/v1/me/favorites", json={"team_ids": [999999]}, headers=headers).status_code == 400
    assert client.put("/api/v1/me/favorites", json={"league_codes": ["XX"]}, headers=headers).status_code == 400

    home = client.get("/api/v1/me/home", params={"tz": "Asia/Kathmandu"}, headers=headers).json()
    names = {(m["home_team"]["name"], m["away_team"]["name"]) for m in home["favorite_matches"]}
    assert ("Manchester City", "Arsenal") in names and ("England", "Spain") in names
    assert ("Liverpool", "Chelsea") not in names
    assert len(home["needs_your_prediction"]) == 2
    assert home["favorite_matches"][0]["predictions"]  # predictions come with the matches

    m1 = match_id(db, "fake:1")
    client.put(f"/api/v1/matches/{m1}/my-prediction", json={"home_goals": 1, "away_goals": 0}, headers=headers)
    home = client.get("/api/v1/me/home", headers=headers).json()
    assert len(home["needs_your_prediction"]) == 1
    assert client.get("/api/v1/me/home", params={"tz": "Mars/Base"}, headers=headers).status_code == 400


# ---------- Day 27: Nations League ----------

@pytest.fixture
def nl_csv(tmp_path):
    path = tmp_path / "nl.csv"
    rows = ["group,date,home_team,away_team,home_goals,away_goals"]
    teams = ["Spain", "England", "Croatia", "Czech Republic"]
    fixtures = [(h, a) for h in teams for a in teams if h != a]
    for i, (h, a) in enumerate(fixtures):
        played = i < 2
        day = f"2026-09-{24 + i // 2:02d}" if played else f"2026-12-{1 + i:02d}"
        score = ("2,0" if i == 0 else "1,1") if played else ","
        rows.append(f"A3,{day},{h},{a},{score}")
    path.write_text("\n".join(rows))
    return path


def test_nations_league(client, db, nl_csv):
    from app.services.nations_league import import_fixtures
    assert import_fixtures(db, nl_csv) == {"rows": 12, "created": 12, "updated": 0}
    assert import_fixtures(db, nl_csv)["created"] == 0  # re-import updates, never duplicates

    groups = client.get("/api/v1/nations-league/groups").json()
    assert groups == [{"group": "A3", "teams": ["Croatia", "Czech Republic", "England", "Spain"]}]

    body = client.get("/api/v1/nations-league/groups/a3", params={"simulations": 2000}).json()
    assert body["played"] == 2 and body["remaining"] == 10 and len(body["matches"]) == 12
    table = {r["team"]: r for r in body["table"]}
    assert table["Spain"]["points"] == 4  # 2-0 win + 1-1 draw
    odds = {r["team"]: r for r in body["odds"]}
    assert sum(r["p1"] for r in body["odds"]) == pytest.approx(1)
    assert odds["Spain"]["quarter_finals"] > odds["Czech Republic"]["quarter_finals"]
    assert client.get("/api/v1/nations-league/groups/Z9").status_code == 404


# ---------- Day 28: players ----------

@pytest.fixture
def player_provider(provider):
    from app.services.providers import PlayerData, ScorerData
    haaland = PlayerData("fdo:1", "Erling Haaland", "Offence", date(2000, 7, 21), "Norway", 9)
    saka = PlayerData("fdo:2", "Bukayo Saka", "Offence", date(2001, 9, 5), "England", 7)
    odegaard = PlayerData("fdo:3", "Martin Ødegaard", "Midfield", date(1998, 12, 17), "Norway", 8)
    provider.squads = {"fake:Manchester City": [haaland], "fake:Arsenal": [saka, odegaard]}
    provider.scorer_rows = {"E0": [
        ScorerData(haaland, "fake:Manchester City", "Manchester City", 6, 9, 1, 2),
        ScorerData(saka, "fake:Arsenal", "Arsenal", 6, 3, 4, 0),
    ]}
    return provider


def test_player_sync_search_and_detail(client, db, player_provider):
    from app.services.players import sync_scorers, sync_squads
    sync_all(db, player_provider, ["E0"])
    for team in db.scalars(select(Team)):  # our fake teams use "fake:" ids; pretend they're football-data ones
        team.external_id = team.external_id.replace("fake:", "football_data_org:")
    db.commit()
    player_provider.squads = {k.replace("fake:", "football_data_org:"): v for k, v in player_provider.squads.items()}
    for rows in player_provider.scorer_rows.values():
        for r in rows:
            r.team_external_id = r.team_external_id.replace("fake:", "football_data_org:")

    assert sync_squads(db, player_provider, ["E0"], progress=lambda *_: None)["players_saved"] == 3
    assert sync_scorers(db, player_provider, ["E0"]) == [{"league": "E0", "scorers": 2}]
    assert sync_scorers(db, player_provider, ["E0"]) == [{"league": "E0", "scorers": 2}]  # updates, no duplicates

    found = client.get("/api/v1/players", params={"search": "odegaard"}).json()
    assert [p["name"] for p in found] == ["Martin Ødegaard"]  # no accent typed, still found
    assert found[0]["team"]["name"] == "Arsenal"
    assert client.get("/api/v1/players", params={"search": "a"}).status_code == 422

    haaland = client.get("/api/v1/players", params={"search": "HAALAND"}).json()[0]
    detail = client.get(f"/api/v1/players/{haaland['id']}").json()
    assert detail["age"] >= 26 and detail["nationality"] == "Norway"
    assert detail["stats"][0] == {"league_code": "E0", "league": "Premier League", "season": 2026,
                                  "team": "Manchester City", "appearances": 6, "goals": 9, "assists": 1, "penalties": 2}
    scorers = client.get("/api/v1/leagues/E0/top-scorers").json()
    assert [s["name"] for s in scorers] == ["Erling Haaland", "Bukayo Saka"] and scorers[0]["rank"] == 1
    assert client.get("/api/v1/players/999999").status_code == 404
    assert client.get("/api/v1/leagues/XX/top-scorers").status_code == 404


def test_search_key_handles_special_letters():
    from app.services.players import search_key
    assert search_key("Martin Ødegaard") == "martin odegaard"
    assert search_key("Kylian Mbappé") == "kylian mbappe"
    assert search_key("Łukasz Fabiański") == "lukasz fabianski"
    assert search_key("Leroy Sané") == "leroy sane"


def test_api_football_explains_it_has_no_player_data():
    from app.competitions import by_code
    from app.services.providers import ApiFootballProvider, ProviderError
    with pytest.raises(ProviderError, match="football-data.org"):
        ApiFootballProvider("KEY").scorers(by_code("E0"), 2026)
