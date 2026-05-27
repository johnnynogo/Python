"""
FastAPI application — Week 2/3 complete version.
New endpoints: backtest, ML train, World Cup simulator, international match predictor.
"""
import os
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import init_db, get_db, health_check
from models import League, Team, Match, Prediction, Odds, SyncLog
from predictor import predict_all_upcoming, predict_match, get_dc_model
from elo import rebuild_elo_ratings
from ingestion_api_football import run_full_sync
from ml_model import train as ml_train, model_info as ml_model_info
from backtester import run_backtest
from international import (
    simulate_tournament, predict_international_match,
    WORLD_CUP_2026_TEAMS
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Soccer Predictor API v2 started ✓")
    yield


app = FastAPI(
    title="MatchMind Soccer Predictor API",
    version="0.3.0",
    description="Eliteserien → World Cup prediction engine",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "status": "ok" if health_check() else "db_error",
        "time":   datetime.now(timezone.utc).isoformat(),
    }


# ── Leagues ───────────────────────────────────────────────────────
@app.get("/leagues")
def list_leagues(db: Session = Depends(get_db)):
    leagues = db.query(League).filter_by(is_active=True).all()
    return [{"id": l.id, "api_id": l.api_id, "name": l.name,
             "country": l.country, "season": l.season} for l in leagues]


# ── Teams ─────────────────────────────────────────────────────────
@app.get("/teams")
def list_teams(league_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(Team)
    if league_id:
        q = q.filter_by(league_id=league_id)
    teams = q.order_by(Team.elo_rating.desc()).all()
    return [{"id": t.id, "name": t.name, "elo_rating": t.elo_rating,
             "squad_value": t.squad_value, "logo_url": t.logo_url, "venue": t.venue}
            for t in teams]


@app.get("/teams/{team_id}")
def get_team(team_id: int, db: Session = Depends(get_db)):
    team = db.query(Team).get(team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    recent = sorted(
        list(db.query(Match).filter_by(home_team_id=team_id, status="FT")
             .order_by(Match.kickoff.desc()).limit(5).all()) +
        list(db.query(Match).filter_by(away_team_id=team_id, status="FT")
             .order_by(Match.kickoff.desc()).limit(5).all()),
        key=lambda m: m.kickoff or datetime.min, reverse=True
    )[:5]
    return {
        "id": team.id, "name": team.name, "elo_rating": team.elo_rating,
        "logo_url": team.logo_url, "venue": team.venue,
        "recent_form": [
            {"home": m.home_team.name, "away": m.away_team.name,
             "score": f"{m.home_goals}-{m.away_goals}" if m.home_goals is not None else "?",
             "date": m.kickoff.isoformat() if m.kickoff else None}
            for m in recent
        ],
    }


# ── Matches ───────────────────────────────────────────────────────
@app.get("/matches")
def list_matches(
    league_id: Optional[int] = None,
    status:    Optional[str] = None,
    upcoming:  bool = False,
    limit:     int  = Query(50, le=1000),
    db: Session = Depends(get_db),
):
    q = db.query(Match)
    if league_id: q = q.filter_by(league_id=league_id)
    if status:    q = q.filter_by(status=status)
    if upcoming:  q = q.filter(Match.status.in_(["NS", "TBD"]))
    matches = q.order_by(Match.kickoff.asc()).limit(limit).all()
    return [_match_to_dict(m) for m in matches]


@app.get("/matches/{match_id}")
def get_match(match_id: int, db: Session = Depends(get_db)):
    m = db.query(Match).get(match_id)
    if not m:
        raise HTTPException(404, "Match not found")
    d = _match_to_dict(m)
    if m.prediction:
        d["prediction"] = _pred_to_dict(m.prediction)
    odds = db.query(Odds).filter_by(match_id=match_id).order_by(Odds.margin.asc()).first()
    if odds:
        d["odds"] = {"bookmaker": odds.bookmaker, "home": odds.home_odds,
                     "draw": odds.draw_odds, "away": odds.away_odds, "margin": odds.margin}
    return d


def _match_to_dict(m: Match) -> dict:
    return {
        "id": m.id, "league": m.league.name if m.league else None,
        "home_team": {"id": m.home_team.id, "name": m.home_team.name, "logo": m.home_team.logo_url} if m.home_team else None,
        "away_team": {"id": m.away_team.id, "name": m.away_team.name, "logo": m.away_team.logo_url} if m.away_team else None,
        "kickoff": m.kickoff.isoformat() if m.kickoff else None,
        "status": m.status,
        "score": f"{m.home_goals}-{m.away_goals}" if m.home_goals is not None else None,
        "home_xg": m.home_xg, "away_xg": m.away_xg,
        "has_prediction": m.prediction is not None,
    }


# ── Predictions ───────────────────────────────────────────────────
@app.get("/predictions")
def list_predictions(
    league_id: Optional[int] = None,
    best_only: bool = False,
    limit:     int  = Query(50, le=1000),
    db: Session = Depends(get_db),
):
    q = (db.query(Prediction)
         .join(Match, Prediction.match_id == Match.id)
         .filter(Match.status.in_(["NS", "TBD"])))
    if league_id: q = q.filter(Match.league_id == league_id)
    if best_only:  q = q.filter(Prediction.best_bet != "none")
    preds = q.order_by(Prediction.confidence.desc()).limit(limit).all()

    # Fetch best odds per match in one query
    match_ids = [p.match_id for p in preds]
    odds_rows = (
        db.query(Odds)
        .filter(Odds.match_id.in_(match_ids))
        .order_by(Odds.margin.asc())
        .all()
    )
    odds_map = {}
    for o in odds_rows:
        if o.match_id not in odds_map:
            odds_map[o.match_id] = o

    return [_pred_to_dict(p, odds_map.get(p.match_id)) for p in preds]


@app.get("/predictions/{match_id}")
def get_prediction(match_id: int, db: Session = Depends(get_db)):
    pred = db.query(Prediction).filter_by(match_id=match_id).first()
    if not pred:
        raise HTTPException(404, "No prediction for this match")
    odds = db.query(Odds).filter_by(match_id=match_id).order_by(Odds.margin.asc()).first()
    return _pred_to_dict(pred, odds)


def _pred_to_dict(p: Prediction, odds: Odds = None) -> dict:
    d = {
        "match_id": p.match_id, "model_version": p.model_version,
        "home_prob": p.home_prob, "draw_prob": p.draw_prob, "away_prob": p.away_prob,
        "confidence": p.confidence,
        "poisson_home": p.poisson_home, "poisson_draw": p.poisson_draw, "poisson_away": p.poisson_away,
        "ml_home": p.ml_home, "ml_draw": p.ml_draw, "ml_away": p.ml_away,
        "home_ev": p.home_ev, "draw_ev": p.draw_ev, "away_ev": p.away_ev,
        "best_bet": p.best_bet, "kelly": p.kelly_fraction,
        "features": p.features,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        # Odds fields
        "home_odds": None, "draw_odds": None, "away_odds": None,
        "bookmaker": None, "margin": None,
    }
    if odds:
        d["home_odds"] = odds.home_odds
        d["draw_odds"] = odds.draw_odds
        d["away_odds"] = odds.away_odds
        d["bookmaker"] = odds.bookmaker
        d["margin"]    = odds.margin
    return d


# ── ML / Back-test ────────────────────────────────────────────────
@app.post("/ml/train")
def train_ml(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Train the LightGBM model on all finished matches."""
    def _train():
        result = ml_train(db)
        logger.info(f"ML training complete: {result}")
    background_tasks.add_task(_train)
    return {"status": "training_started", "message": "LightGBM training running in background."}


@app.get("/ml/info")
def ml_info():
    return ml_model_info()


@app.get("/backtest")
def backtest(
    days_back: int = Query(180, ge=1, le=9999, description="How many days of history to back-test"),
    db: Session = Depends(get_db),
):
    """Run walk-forward back-test and return performance metrics."""
    from datetime import timedelta
    start = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days_back)
    report = run_backtest(db, start_date=start)
    from dataclasses import asdict
    return asdict(report)


# ── World Cup / International ─────────────────────────────────────
class WCSimRequest(BaseModel):
    groups: dict[str, list[str]]        # {"A": ["Team1","Team2","Team3","Team4"], ...}
    elo_overrides: Optional[dict[str, float]] = None   # Override default Elo ratings
    n_simulations: int = 10000


@app.post("/worldcup/simulate")
def simulate_wc(req: WCSimRequest):
    """Run Monte Carlo World Cup simulation."""
    elo = {**WORLD_CUP_2026_TEAMS}
    if req.elo_overrides:
        elo.update(req.elo_overrides)
    result = simulate_tournament(req.groups, elo, req.n_simulations)
    return result


@app.get("/worldcup/teams")
def wc_teams():
    """Return all known 2026 WC teams with default Elo ratings."""
    return [
        {"team": name, "elo": elo}
        for name, elo in sorted(WORLD_CUP_2026_TEAMS.items(), key=lambda kv: -kv[1])
    ]


class IntlMatchRequest(BaseModel):
    home_team:  str
    away_team:  str
    home_elo:   Optional[float] = None
    away_elo:   Optional[float] = None
    neutral:    bool = True
    n_sims:     int  = 50000


@app.post("/international/predict")
def predict_intl(req: IntlMatchRequest):
    """Predict a single international match using Monte Carlo."""
    return predict_international_match(
        home_team=req.home_team,
        away_team=req.away_team,
        home_elo=req.home_elo,
        away_elo=req.away_elo,
        neutral=req.neutral,
        n_sims=req.n_sims,
    )


# ── Admin ─────────────────────────────────────────────────────────
@app.post("/admin/sync")
def trigger_sync(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    def _sync():
        run_full_sync(db)
        rebuild_elo_ratings(db)
        predict_all_upcoming(db, force_refit=True)
    background_tasks.add_task(_sync)
    return {"status": "sync_started"}


@app.post("/admin/predict")
def trigger_predictions(background_tasks: BackgroundTasks, force_refit: bool = False, db: Session = Depends(get_db)):
    background_tasks.add_task(predict_all_upcoming, db, force_refit)
    return {"status": "prediction_started"}


@app.post("/admin/rebuild_elo")
def rebuild_elo(db: Session = Depends(get_db)):
    rebuild_elo_ratings(db)
    return {"status": "elo_rebuilt"}

@app.post("/admin/sync_odds")
def trigger_odds_sync(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    def _sync():
        from ingestion_odds_api import run_odds_sync
        from predictor import predict_all_upcoming
        run_odds_sync(db, force=True)
        predict_all_upcoming(db)   # ← recalculate predictions with new odds
    background_tasks.add_task(_sync)
    return {"status": "odds_sync_started", "message": "Fetching odds and updating predictions (3 tokens)"}


@app.get("/admin/sync_logs")
def sync_logs(limit: int = 20, db: Session = Depends(get_db)):
    logs = db.query(SyncLog).order_by(SyncLog.started_at.desc()).limit(limit).all()
    return [{"source": l.source, "status": l.status, "records": l.records,
             "error": l.error_msg, "started_at": l.started_at.isoformat() if l.started_at else None}
            for l in logs]


# ── Stats ─────────────────────────────────────────────────────────
@app.get("/stats/summary")
def summary(db: Session = Depends(get_db)):
    return {
        "total_matches":   db.query(Match).count(),
        "finished":        db.query(Match).filter_by(status="FT").count(),
        "upcoming":        db.query(Match).filter(Match.status.in_(["NS", "TBD"])).count(),
        "with_prediction": db.query(Prediction).count(),
        "with_xg":         db.query(Match).filter(Match.home_xg != None).count(),
        "teams":           db.query(Team).count(),
        "leagues":         db.query(League).count(),
        "ml_trained":      ml_model_info().get("trained", False),
    }


@app.get("/stats/team_ratings")
def team_ratings(db: Session = Depends(get_db)):
    try:
        dc = get_dc_model(db, force_refit=False)
        return dc.team_ratings()
    except Exception as e:
        raise HTTPException(500, f"Model not ready: {e}")
