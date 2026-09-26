"""The shapes of data going in and out of the API (Pydantic models).

These are separate from the database models on purpose: the API decides
what the outside world sees. A User in the database has a password_hash;
UserOut simply doesn't include it, so it can never leak by accident.
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LeagueOut(ORM):
    code: str
    name: str
    country: str | None
    is_international: bool
    current_season: int


class TeamOut(ORM):
    id: int
    name: str
    short_name: str | None
    is_national: bool


class Scoreline(BaseModel):
    score: str
    probability: float


class PredictionOut(ORM):
    model: str
    home_win: float
    draw: float
    away_win: float
    expected_home_goals: float
    expected_away_goals: float
    top_scorelines: list[Scoreline]
    model_version: str | None
    created_at: datetime


class MatchOut(ORM):
    id: int
    league: LeagueOut
    season: int
    round: str | None
    kickoff: datetime
    status: str
    minute: int | None
    home_team: TeamOut
    away_team: TeamOut
    home_goals: int | None
    away_goals: int | None
    venue: str | None


class MatchDetail(MatchOut):
    predictions: list[PredictionOut]


class MatchStateIn(BaseModel):
    """Day 19: a match situation for the what-if engine."""
    minute: int = Field(0, ge=0, le=90)
    home_goals: int = Field(0, ge=0, le=20)
    away_goals: int = Field(0, ge=0, le=20)
    home_red_cards: int = Field(0, ge=0, le=4)
    away_red_cards: int = Field(0, ge=0, le=4)
    neutral: bool | None = None  # None = use the real venue
    model: str = "dixon_coles"


class FreeSimulationIn(MatchStateIn):
    competition: str = Field(description="league code (E0, SP1, D1, I1, F1) or 'international'")
    home_team: str
    away_team: str


class Probabilities(BaseModel):
    home_win: float
    draw: float
    away_win: float


class SimulationOut(BaseModel):
    home_team: str
    away_team: str
    model: str
    state: MatchStateIn
    expected_goals_remaining: dict[str, float]
    probabilities: Probabilities
    top_scorelines: list[Scoreline]


class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=30, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=8, max_length=72)


class UserOut(ORM):
    id: int
    email: str
    username: str
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------------------------------------------------------------- Week 4



class UserPredictionIn(BaseModel):
    """Day 22: your predicted score."""
    home_goals: int = Field(ge=0, le=15)
    away_goals: int = Field(ge=0, le=15)


class UserPredictionOut(ORM):
    match_id: int
    home_goals: int
    away_goals: int
    points: int | None
    breakdown: dict | None
    ai_score: str | None
    ai_points: int | None
    created_at: datetime
    updated_at: datetime
    scored_at: datetime | None


class FanVsAIOut(BaseModel):
    """Day 24: fans against FOOTIQ, on the same matches and the same scoring rules."""
    matches: int
    fan_points: int
    ai_points: int
    fan_wins: int
    ai_wins: int
    ties: int


class Streak(BaseModel):
    current: int
    best: int


class MyStatsOut(BaseModel):
    username: str
    points: int
    rank: int | None
    predictions_scored: int
    predictions_pending: int
    correct_results: int
    exact_scores: int
    streak: Streak
    fan_vs_ai: FanVsAIOut


class LeaderboardRow(BaseModel):
    rank: int
    user_id: int
    username: str
    points: int
    predictions: int
    exact_scores: int


class LeaderboardOut(BaseModel):
    period: str
    league: str | None
    rows: list[LeaderboardRow]
    me: LeaderboardRow | None


class FavoritesIn(BaseModel):
    """Day 26"""
    team_ids: list[int] = []
    league_codes: list[str] = []


class FavoritesOut(BaseModel):
    teams: list[TeamOut]
    leagues: list[LeagueOut]


class HomeOut(BaseModel):
    username: str
    local_time: str
    has_favorites: bool
    today: dict[str, int]
    stats: MyStatsOut
    favorite_matches: list[MatchDetail]
    needs_your_prediction: list[MatchDetail]
    recent_results: list[UserPredictionOut]


class GroupSummary(BaseModel):
    """Day 27"""
    group: str
    teams: list[str]


class GroupTableRow(BaseModel):
    pos: int
    team: str
    played: int
    points: int
    gf: int
    ga: int
    gd: int


class GroupOddsRow(BaseModel):
    team: str
    avg_points: float
    p1: float
    p2: float
    p3: float
    p4: float
    quarter_finals: float
    playoff: float
    relegated: float


class GroupOut(BaseModel):
    group: str
    played: int
    remaining: int
    simulations: int
    table: list[GroupTableRow]
    odds: list[GroupOddsRow]
    matches: list[MatchOut]


class PlayerOut(ORM):
    """Day 28"""
    id: int
    name: str
    position: str | None
    nationality: str | None
    birth_date: date | None
    age: int | None
    shirt_number: int | None
    team: TeamOut | None


class PlayerStatsOut(BaseModel):
    league_code: str
    league: str
    season: int
    team: str | None
    appearances: int | None
    goals: int
    assists: int | None
    penalties: int | None


class PlayerDetail(PlayerOut):
    stats: list[PlayerStatsOut]


class TopScorerOut(BaseModel):
    rank: int
    player_id: int
    name: str
    team: str | None
    appearances: int | None
    goals: int
    assists: int | None
    penalties: int | None
