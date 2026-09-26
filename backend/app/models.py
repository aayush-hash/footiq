"""Day 15: the database tables.

Each class is one table; each attribute is one column. Relationships
(match.home_team, league.matches) let you move between tables without
writing SQL joins by hand.

    League ─┬─< Match >─┬─ Team (home)
            │           └─ Team (away)
            │  Match ──< Prediction          (the model's odds)
            │  Match ──< UserPrediction >── User   (Week 4: fans' predictions)
    Team ──< Player ──< PlayerSeasonStats   (Week 4)
    User ──< FavoriteTeam / FavoriteLeague  (Week 4)
"""

from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class League(Base):
    __tablename__ = "leagues"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)      # our short code: "E0", "UNL"
    name: Mapped[str] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(100))
    model_key: Mapped[str] = mapped_column(String(30))               # which trained model predicts it: "E0" or "international"
    is_international: Mapped[bool] = mapped_column(Boolean, default=False)
    current_season: Mapped[int] = mapped_column(Integer)             # start year: 2026 = 2026/27

    matches: Mapped[list["Match"]] = relationship(back_populates="league")


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(50), unique=True)  # "api_football:529"
    name: Mapped[str] = mapped_column(String(100))
    short_name: Mapped[str | None] = mapped_column(String(50))
    country: Mapped[str | None] = mapped_column(String(100))
    is_national: Mapped[bool] = mapped_column(Boolean, default=False)
    model_name: Mapped[str | None] = mapped_column(String(100))        # the name our ML models use, e.g. "Man City"

    players: Mapped[list["Player"]] = relationship(back_populates="team")


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(50), unique=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"), index=True)
    season: Mapped[int] = mapped_column(Integer)
    round: Mapped[str | None] = mapped_column(String(100))
    kickoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)       # scheduled / live / finished / postponed / cancelled
    minute: Mapped[int | None] = mapped_column(Integer)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    home_goals: Mapped[int | None] = mapped_column(Integer)
    away_goals: Mapped[int | None] = mapped_column(Integer)
    neutral: Mapped[bool] = mapped_column(Boolean, default=False)
    group_name: Mapped[str | None] = mapped_column(String(20), index=True)  # Week 4: "A1" for Nations League
    venue: Mapped[str | None] = mapped_column(String(150))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    league: Mapped[League] = relationship(back_populates="matches")
    home_team: Mapped[Team] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped[Team] = relationship(foreign_keys=[away_team_id])
    predictions: Mapped[list["Prediction"]] = relationship(back_populates="match", cascade="all, delete-orphan")


class Prediction(Base):
    """The model's prediction for a match. Updated daily until kickoff, then
    frozen, so the transparency page can later compare it with the result."""

    __tablename__ = "predictions"
    __table_args__ = (UniqueConstraint("match_id", "model", name="uq_prediction_match_model"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    model: Mapped[str] = mapped_column(String(30))                    # "dixon_coles" or "elo"
    home_win: Mapped[float] = mapped_column(Float)
    draw: Mapped[float] = mapped_column(Float)
    away_win: Mapped[float] = mapped_column(Float)
    expected_home_goals: Mapped[float] = mapped_column(Float)
    expected_away_goals: Mapped[float] = mapped_column(Float)
    top_scorelines: Mapped[list] = mapped_column(JSON)
    model_version: Mapped[str | None] = mapped_column(String(40))     # when the model was trained
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    match: Mapped[Match] = relationship(back_populates="predictions")


class Player(Base):
    """Day 28: players from the data provider (squads and top scorers)."""

    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    nationality: Mapped[str | None] = mapped_column(String(100))
    birth_date: Mapped[date | None] = mapped_column(Date)
    position: Mapped[str | None] = mapped_column(String(30))
    shirt_number: Mapped[int | None] = mapped_column(Integer)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    # Week 4: lowercase, no accents, so "mbappe" finds "Mbappé"
    search_name: Mapped[str] = mapped_column(String(120), index=True, default="")

    team: Mapped[Team | None] = relationship(back_populates="players")
    stats: Mapped[list["PlayerSeasonStats"]] = relationship(back_populates="player", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(100))            # never the password itself
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------- Week 4


class UserPrediction(Base):
    """Day 22: a fan's predicted score. Can be changed until kickoff, then locked.
    Day 23 fills in the points once the match finishes, and the AI's points
    for the same match (for Fan vs AI)."""

    __tablename__ = "user_predictions"
    __table_args__ = (UniqueConstraint("user_id", "match_id", name="uq_user_prediction"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    home_goals: Mapped[int] = mapped_column(Integer)
    away_goals: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    points: Mapped[int | None] = mapped_column(Integer)        # empty until the match is scored
    breakdown: Mapped[dict | None] = mapped_column(JSON)       # {"result": 5, "exact_score": 15, ...}
    ai_score: Mapped[str | None] = mapped_column(String(10))   # what FOOTIQ predicted, e.g. "2-1"
    ai_points: Mapped[int | None] = mapped_column(Integer)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    user: Mapped[User] = relationship()
    match: Mapped[Match] = relationship()


class FavoriteTeam(Base):
    """Day 26"""

    __tablename__ = "favorite_teams"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True)


class FavoriteLeague(Base):
    """Day 26"""

    __tablename__ = "favorite_leagues"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"), primary_key=True)


class PlayerSeasonStats(Base):
    """Day 28: one row per player, per competition, per season."""

    __tablename__ = "player_season_stats"
    __table_args__ = (UniqueConstraint("player_id", "league_id", "season", name="uq_player_season"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"))
    season: Mapped[int] = mapped_column(Integer)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    appearances: Mapped[int | None] = mapped_column(Integer)
    goals: Mapped[int] = mapped_column(Integer, default=0)
    assists: Mapped[int | None] = mapped_column(Integer)
    penalties: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    player: Mapped[Player] = relationship(back_populates="stats")
    league: Mapped[League] = relationship()
    team: Mapped[Team | None] = relationship()
