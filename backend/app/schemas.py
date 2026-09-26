"""The shapes of data going in and out of the API (Pydantic models).

These are separate from the database models on purpose: the API decides
what the outside world sees. A User in the database has a password_hash;
UserOut simply doesn't include it, so it can never leak by accident.
"""

from datetime import datetime

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
