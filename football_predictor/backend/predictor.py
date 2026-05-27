"""
Prediction orchestrator — updated for Week 2/3.
Combines Elo + Dixon-Coles + LightGBM into weighted ensemble.
Weights are tuned based on back-test results.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from models import Match, Prediction, Odds
from elo import predict_probabilities as elo_probs
from dixon_coles import DixonColesModel
from ml_model import predict as ml_predict, load_model
from kelly import evaluate_match

logger = logging.getLogger(__name__)

# Ensemble weights — tune these after running the back-tester
# Start: 60% DC Poisson, 25% LightGBM, 15% Elo
# After back-test analysis bump whichever scores lowest log-loss
WEIGHTS = {
    "poisson": 0.60,
    "ml":      0.25,
    "elo":     0.15,
}

MODEL_VERSION = "v0.3-ensemble"

_dc_model: Optional[DixonColesModel] = None


def get_dc_model(db: Session, force_refit: bool = False) -> DixonColesModel:
    global _dc_model
    if _dc_model is None or force_refit:
        try:
            logger.info("Fitting Dixon-Coles model...")
            _dc_model = DixonColesModel()
            _dc_model.fit(db)
            logger.info("Dixon-Coles fit complete.")
        except Exception as e:
            logger.error(f"Dixon-Coles fit failed: {e}")
            raise
    return _dc_model


def ensemble(elo: dict, poisson: dict, ml: Optional[dict]) -> dict[str, float]:
    """Weighted ensemble. If ML not available falls back to DC+Elo only."""
    outcomes = ("home", "draw", "away")

    if ml is not None:
        w_p = WEIGHTS["poisson"]
        w_m = WEIGHTS["ml"]
        w_e = WEIGHTS["elo"]
    else:
        # No ML model — redistribute weights
        w_p = 0.70
        w_m = 0.00
        w_e = 0.30

    raw = {
        o: w_p * poisson[o] + w_m * (ml[o] if ml else 0) + w_e * elo[o]
        for o in outcomes
    }
    total = sum(raw.values())
    return {o: round(raw[o] / total, 4) for o in outcomes}


def predict_match(
    db: Session,
    match: Match,
    dc: Optional[DixonColesModel] = None,
) -> Optional[Prediction]:
    if not match.home_team or not match.away_team:
        return None

    home = match.home_team
    away = match.away_team

    # Elo prediction
    elo = elo_probs(
        home_rating=home.elo_rating,
        away_rating=away.elo_rating,
        is_neutral=match.is_neutral,
    )

    # Dixon-Coles Poisson
    if dc is None:
        dc = get_dc_model(db)
    poisson_preds = dc.predict_outcome_probs(home.name, away.name, match.is_neutral)
    xg_preds      = dc.predict_expected_goals(home.name, away.name, match.is_neutral)

    # LightGBM ML layer
    ml_preds = ml_predict(db, match)

    # Weighted ensemble
    final = ensemble(elo, poisson_preds, ml_preds)

    # Market odds & Kelly
    best_odds_row = (
        db.query(Odds)
        .filter_by(match_id=match.id)
        .order_by(Odds.margin.asc())
        .first()
    )
    kelly_eval = None
    if best_odds_row:
        market_odds = {
            "home": best_odds_row.home_odds,
            "draw": best_odds_row.draw_odds,
            "away": best_odds_row.away_odds,
        }
        kelly_eval = evaluate_match(final, market_odds)

    # Upsert
    pred = db.query(Prediction).filter_by(match_id=match.id).first()
    if not pred:
        pred = Prediction(match_id=match.id)
        db.add(pred)

    pred.model_version  = MODEL_VERSION
    pred.poisson_home   = poisson_preds["home"]
    pred.poisson_draw   = poisson_preds["draw"]
    pred.poisson_away   = poisson_preds["away"]
    pred.ml_home        = ml_preds["home"] if ml_preds else None
    pred.ml_draw        = ml_preds["draw"] if ml_preds else None
    pred.ml_away        = ml_preds["away"] if ml_preds else None
    pred.home_prob      = final["home"]
    pred.draw_prob      = final["draw"]
    pred.away_prob      = final["away"]
    pred.confidence     = max(final.values())

    if kelly_eval:
        pred.home_ev        = kelly_eval["home"]["ev"]
        pred.draw_ev        = kelly_eval["draw"]["ev"]
        pred.away_ev        = kelly_eval["away"]["ev"]
        pred.best_bet       = kelly_eval["best_bet"]
        pred.kelly_fraction = (
            kelly_eval[kelly_eval["best_bet"]]["kelly"]
            if kelly_eval["best_bet"] != "none" else 0.0
        )

    pred.features = {
        "elo":     elo,
        "poisson": poisson_preds,
        "ml":      ml_preds,
        "xg":      xg_preds,
        "weights": WEIGHTS,
    }
    db.commit()
    return pred


def predict_all_upcoming(db: Session, force_refit: bool = False) -> int:
    global _dc_model

    # Fit Dixon-Coles
    try:
        _dc_model = None
        logger.info("Fitting Dixon-Coles model...")
        _dc_model = DixonColesModel()
        _dc_model.fit(db)
        logger.info("Dixon-Coles fit complete.")
        dc_available = True
    except Exception as e:
        logger.error(f"Dixon-Coles failed, falling back to Elo only: {e}")
        dc_available = False

    upcoming = (
        db.query(Match)
        .filter(Match.status.in_(["NS", "TBD", "SUSP"]))
        .order_by(Match.kickoff.asc())
        .all()
    )

    count = 0
    for m in upcoming:
        try:
            if not m.home_team or not m.away_team:
                continue

            home = m.home_team
            away = m.away_team

            # Always compute Elo
            elo = elo_probs(
                home_rating=home.elo_rating,
                away_rating=away.elo_rating,
                is_neutral=m.is_neutral,
            )

            # Try full ensemble if DC available
            if dc_available and _dc_model:
                poisson_preds = _dc_model.predict_outcome_probs(home.name, away.name, m.is_neutral)
                xg_preds      = _dc_model.predict_expected_goals(home.name, away.name, m.is_neutral)
                ml_preds      = ml_predict(db, m)
                final         = ensemble(elo, poisson_preds, ml_preds)
                version       = MODEL_VERSION
            else:
                # Elo only fallback
                poisson_preds = elo
                xg_preds      = {}
                ml_preds      = None
                final         = elo
                version       = "v0.1-elo-only"

            pred = db.query(Prediction).filter_by(match_id=m.id).first()
            if not pred:
                pred = Prediction(match_id=m.id)
                db.add(pred)

            pred.model_version  = version
            pred.poisson_home   = poisson_preds["home"]
            pred.poisson_draw   = poisson_preds["draw"]
            pred.poisson_away   = poisson_preds["away"]
            pred.ml_home        = ml_preds["home"] if ml_preds else None
            pred.ml_draw        = ml_preds["draw"] if ml_preds else None
            pred.ml_away        = ml_preds["away"] if ml_preds else None
            pred.home_prob      = final["home"]
            pred.draw_prob      = final["draw"]
            pred.away_prob      = final["away"]
            pred.confidence     = max(final.values())
            pred.best_bet       = "none"
            pred.features       = {"elo": elo, "xg": xg_preds}
            db.commit()
            count += 1

        except Exception as e:
            logger.warning(f"Prediction failed for match {m.id}: {e}")

    logger.info(f"Predictions: {count}/{len(upcoming)} upcoming matches")
    return count