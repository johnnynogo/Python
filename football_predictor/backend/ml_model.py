"""
ML model layer — Week 2.

Pipeline:
  1. Build feature matrix from features.py
  2. Train LightGBM classifier (home win / draw / away win)
  3. Calibrate raw probabilities with Platt scaling (isotonic regression)
  4. Persist model to disk with joblib so it survives API restarts
  5. Expose predict() → {"home": p, "draw": p, "away": p}

Why LightGBM over XGBoost?
  - Faster on tabular data of this size
  - Handles missing values (xG often absent for older matches) natively
  - Generally equal or better accuracy at this scale

Feature importance is logged after each fit so we can see what drives predictions.
"""

import os
import logging
import joblib
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import log_loss, brier_score_loss
from sqlalchemy.orm import Session

from features import build_feature_dataset, build_features
from models import Match

logger = logging.getLogger(__name__)

MODEL_PATH   = os.path.join(os.path.dirname(__file__), "ml_model.joblib")
ENCODER_PATH = os.path.join(os.path.dirname(__file__), "label_encoder.joblib")

# In-memory cache — avoids re-loading from disk on every prediction call
_cached_model:     Optional[object]    = None
_cached_feat_cols: Optional[list[str]] = None

# Features used for training (drop metadata cols)
META_COLS = {"match_id", "home_team", "away_team", "result",
             "mkt_home_prob", "mkt_draw_prob", "mkt_away_prob", "mkt_margin"}

RESULT_MAP = {0: "home", 1: "draw", 2: "away"}


def _feature_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in META_COLS]


def train(db: Session, use_market_features: bool = False) -> dict:
    """
    Fit the LightGBM model on all finished matches.
    Returns a dict with training metrics.
    """
    logger.info("Building feature dataset for ML training…")
    df = build_feature_dataset(db)

    if df.empty or "result" not in df.columns:
        raise ValueError("No training data available — sync fixtures first.")

    df = df.dropna(subset=["result"])

    # Optionally include market odds as features (careful: data leakage risk)
    if not use_market_features:
        df = df.drop(columns=[c for c in META_COLS if c in df.columns
                               and c not in {"match_id", "home_team", "away_team", "result"}],
                     errors="ignore")

    feat_cols = _feature_cols(df)
    X = df[feat_cols].fillna(0).values
    y = df["result"].astype(int).values

    logger.info(f"Training on {len(X)} matches, {len(feat_cols)} features")

    # LightGBM base model
    lgbm = LGBMClassifier(
        n_estimators=400,
        learning_rate=0.05,
        max_depth=5,
        num_leaves=31,
        min_child_samples=10,
        subsample=0.8,
        colsample_bytree=0.8,
        class_weight="balanced",
        random_state=42,
        verbose=-1,
    )

    # Wrap with isotonic calibration (better than Platt/sigmoid for multiclass)
    model = CalibratedClassifierCV(lgbm, method="isotonic", cv=5)
    model.fit(X, y)

    # Cross-val log-loss
    raw_lgbm = LGBMClassifier(
        n_estimators=400, learning_rate=0.05, max_depth=5,
        num_leaves=31, min_child_samples=10, subsample=0.8,
        colsample_bytree=0.8, class_weight="balanced",
        random_state=42, verbose=-1,
    )
    cv_scores = cross_val_score(raw_lgbm, X, y, cv=5, scoring="neg_log_loss")
    cv_logloss = -cv_scores.mean()

    # In-sample metrics (for monitoring only)
    proba = model.predict_proba(X)
    ll = log_loss(y, proba)

    # Feature importance from the underlying LightGBM estimators
    importances = _extract_importances(model, feat_cols)
    top = sorted(importances.items(), key=lambda kv: -kv[1])[:10]
    logger.info("Top 10 features: " + ", ".join(f"{k}={v:.3f}" for k, v in top))

    # Persist + update in-memory cache so predict() is instant after training
    global _cached_model, _cached_feat_cols
    joblib.dump(model,     MODEL_PATH)
    joblib.dump(feat_cols, ENCODER_PATH)
    _cached_model     = model
    _cached_feat_cols = feat_cols
    logger.info(f"Model saved → {MODEL_PATH}")

    return {
        "n_matches":    len(X),
        "n_features":   len(feat_cols),
        "cv_logloss":   round(cv_logloss, 4),
        "train_logloss": round(ll, 4),
        "feature_importance": dict(top),
        "trained_at":   datetime.utcnow().isoformat(),
    }


def _extract_importances(calibrated_model, feat_cols: list[str]) -> dict[str, float]:
    """Average feature importances across all calibrated estimators."""
    importances = np.zeros(len(feat_cols))
    count = 0
    for est in calibrated_model.calibrated_classifiers_:
        base = est.estimator
        if hasattr(base, "feature_importances_"):
            importances += base.feature_importances_
            count += 1
    if count:
        importances /= count
    return dict(zip(feat_cols, importances.tolist()))


def load_model() -> tuple[Optional[object], Optional[list[str]]]:
    """Load persisted model + feature list. Returns (None, None) if not trained yet."""
    global _cached_model, _cached_feat_cols
    if _cached_model is not None:
        return _cached_model, _cached_feat_cols
    if os.path.exists(MODEL_PATH) and os.path.exists(ENCODER_PATH):
        _cached_model     = joblib.load(MODEL_PATH)
        _cached_feat_cols = joblib.load(ENCODER_PATH)
        return _cached_model, _cached_feat_cols
    return None, None


def predict(db: Session, match: Match) -> Optional[dict[str, float]]:
    """
    Generate ML probabilities for a single match.
    Returns {"home": p, "draw": p, "away": p} or None if model not trained.
    """
    model, feat_cols = load_model()
    if model is None:
        return None

    feats = build_features(db, match)
    if feats is None:
        return None

    row = pd.DataFrame([feats])
    X = row.reindex(columns=feat_cols, fill_value=0).fillna(0).values

    proba = model.predict_proba(X)[0]   # [p_home, p_draw, p_away]

    # Classes order: LightGBM preserves 0,1,2 = home,draw,away
    return {
        "home": round(float(proba[0]), 4),
        "draw": round(float(proba[1]), 4),
        "away": round(float(proba[2]), 4),
    }


def model_info() -> dict:
    """Return metadata about the current model."""
    if not os.path.exists(MODEL_PATH):
        return {"trained": False}
    mtime = os.path.getmtime(MODEL_PATH)
    feat_cols = joblib.load(ENCODER_PATH) if os.path.exists(ENCODER_PATH) else []
    return {
        "trained":    True,
        "trained_at": datetime.fromtimestamp(mtime).isoformat(),
        "n_features": len(feat_cols),
        "features":   feat_cols,
    }
