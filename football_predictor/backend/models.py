"""
Database models — SQLAlchemy ORM
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, Float, String, Boolean,
    DateTime, ForeignKey, UniqueConstraint, Text, JSON
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class League(Base):
    __tablename__ = "leagues"

    id          = Column(Integer, primary_key=True)
    api_id      = Column(Integer, unique=True, nullable=False)
    name        = Column(String(200), nullable=False)
    country     = Column(String(100))
    season      = Column(Integer)
    logo_url    = Column(String(500))
    is_active   = Column(Boolean, default=True)
    created_at  = Column(DateTime, default=datetime.utcnow)

    teams    = relationship("Team",    back_populates="league")
    matches  = relationship("Match",   back_populates="league")


class Team(Base):
    __tablename__ = "teams"

    id          = Column(Integer, primary_key=True)
    api_id      = Column(Integer, unique=True, nullable=False)
    name        = Column(String(200), nullable=False)
    short_name  = Column(String(10))
    country     = Column(String(100))
    league_id   = Column(Integer, ForeignKey("leagues.id"))
    logo_url    = Column(String(500))
    founded     = Column(Integer)
    venue       = Column(String(200))
    # Ratings — updated after each sync
    elo_rating  = Column(Float, default=1500.0)
    fifa_rank   = Column(Integer)
    squad_value = Column(Float)   # € millions
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    league       = relationship("League",   back_populates="teams")
    home_matches = relationship("Match",    foreign_keys="Match.home_team_id", back_populates="home_team")
    away_matches = relationship("Match",    foreign_keys="Match.away_team_id", back_populates="away_team")
    elo_history  = relationship("EloHistory", back_populates="team")


class Match(Base):
    __tablename__ = "matches"

    id              = Column(Integer, primary_key=True)
    api_id          = Column(Integer, unique=True, nullable=False)
    league_id       = Column(Integer, ForeignKey("leagues.id"))
    home_team_id    = Column(Integer, ForeignKey("teams.id"))
    away_team_id    = Column(Integer, ForeignKey("teams.id"))
    kickoff         = Column(DateTime)
    status          = Column(String(50))   # NS, 1H, HT, 2H, FT, etc.
    # Scoreline
    home_goals      = Column(Integer)
    away_goals      = Column(Integer)
    home_goals_ht   = Column(Integer)
    away_goals_ht   = Column(Integer)
    # xG (where available)
    home_xg         = Column(Float)
    away_xg         = Column(Float)
    # Match stats (JSON blob for flexibility)
    stats           = Column(JSON)
    # Venue
    is_neutral      = Column(Boolean, default=False)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    league    = relationship("League", back_populates="matches")
    home_team = relationship("Team",   foreign_keys=[home_team_id], back_populates="home_matches")
    away_team = relationship("Team",   foreign_keys=[away_team_id], back_populates="away_matches")
    odds      = relationship("Odds",   back_populates="match")
    prediction = relationship("Prediction", back_populates="match", uselist=False)

    __table_args__ = (UniqueConstraint("api_id", name="uq_match_api_id"),)


class Odds(Base):
    __tablename__ = "odds"

    id              = Column(Integer, primary_key=True)
    match_id        = Column(Integer, ForeignKey("matches.id"))
    bookmaker       = Column(String(100))
    market          = Column(String(50))   # 1X2, BTTS, O/U 2.5 ...
    home_odds       = Column(Float)
    draw_odds       = Column(Float)
    away_odds       = Column(Float)
    # Implied probabilities (after margin removal)
    home_prob       = Column(Float)
    draw_prob       = Column(Float)
    away_prob       = Column(Float)
    margin          = Column(Float)
    fetched_at      = Column(DateTime, default=datetime.utcnow)

    match = relationship("Match", back_populates="odds")


class Prediction(Base):
    __tablename__ = "predictions"

    id              = Column(Integer, primary_key=True)
    match_id        = Column(Integer, ForeignKey("matches.id"), unique=True)
    model_version   = Column(String(50))
    # Poisson model output
    poisson_home    = Column(Float)
    poisson_draw    = Column(Float)
    poisson_away    = Column(Float)
    # ML model output
    ml_home         = Column(Float)
    ml_draw         = Column(Float)
    ml_away         = Column(Float)
    # Ensemble (final)
    home_prob       = Column(Float)
    draw_prob       = Column(Float)
    away_prob       = Column(Float)
    confidence      = Column(Float)
    # Value vs market
    home_ev         = Column(Float)   # Expected value
    draw_ev         = Column(Float)
    away_ev         = Column(Float)
    best_bet        = Column(String(20))   # "home" | "draw" | "away" | "none"
    kelly_fraction  = Column(Float)
    # Feature snapshot
    features        = Column(JSON)
    created_at      = Column(DateTime, default=datetime.utcnow)

    match = relationship("Match", back_populates="prediction")


class EloHistory(Base):
    __tablename__ = "elo_history"

    id          = Column(Integer, primary_key=True)
    team_id     = Column(Integer, ForeignKey("teams.id"))
    match_id    = Column(Integer, ForeignKey("matches.id"), nullable=True)
    rating      = Column(Float, nullable=False)
    recorded_at = Column(DateTime, default=datetime.utcnow)

    team = relationship("Team", back_populates="elo_history")


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id          = Column(Integer, primary_key=True)
    source      = Column(String(100))   # api_football | understat | odds_api
    league_id   = Column(Integer, ForeignKey("leagues.id"), nullable=True)
    status      = Column(String(20))    # success | error
    records     = Column(Integer, default=0)
    error_msg   = Column(Text)
    started_at  = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)
