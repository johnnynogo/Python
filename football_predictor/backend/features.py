"""
Feature engineering for match prediction.
Produces a flat feature dict for each upcoming match.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import and_

from models import Match, Team, Odds

logger = logging.getLogger(__name__)

FORM_WINDOW  = 5    # Last N matches for form
LONG_WINDOW  = 10   # Longer window for stability
MIN_MATCHES  = 3    # Minimum matches before trusting stats


def _get_recent_matches(
    db: Session,
    team_id: int,
    before_date: datetime,
    n: int = LONG_WINDOW,
) -> list[Match]:
    """Return the last N completed matches for a team before a given date."""
    home_matches = (
        db.query(Match)
        .filter(
            Match.home_team_id == team_id,
            Match.status == "FT",
            Match.kickoff < before_date,
        )
        .order_by(Match.kickoff.desc())
        .limit(n)
        .all()
    )
    away_matches = (
        db.query(Match)
        .filter(
            Match.away_team_id == team_id,
            Match.status == "FT",
            Match.kickoff < before_date,
        )
        .order_by(Match.kickoff.desc())
        .limit(n)
        .all()
    )
    combined = home_matches + away_matches
    combined.sort(key=lambda m: m.kickoff or datetime.min, reverse=True)
    return combined[:n]


def _team_features(
    db: Session,
    team: Team,
    as_home: bool,
    before_date: datetime,
) -> dict:
    """Compute per-team features from recent match history."""
    recent = _get_recent_matches(db, team.id, before_date, LONG_WINDOW)
    short  = recent[:FORM_WINDOW]

    def goals_for(m: Match, tid: int) -> Optional[int]:
        if m.home_team_id == tid:
            return m.home_goals
        return m.away_goals

    def goals_against(m: Match, tid: int) -> Optional[int]:
        if m.home_team_id == tid:
            return m.away_goals
        return m.home_goals

    def xg_for(m: Match, tid: int) -> Optional[float]:
        if m.home_team_id == tid:
            return m.home_xg
        return m.away_xg

    def xg_against(m: Match, tid: int) -> Optional[float]:
        if m.home_team_id == tid:
            return m.away_xg
        return m.home_xg

    def result(m: Match, tid: int) -> str:
        gf = goals_for(m, tid)
        ga = goals_against(m, tid)
        if gf is None or ga is None:
            return "u"
        if gf > ga:
            return "w"
        if gf == ga:
            return "d"
        return "l"

    tid = team.id

    def safe_mean(vals):
        v = [x for x in vals if x is not None]
        return np.mean(v) if v else 0.0

    # Points per game (form window and long window)
    def points(r): return {"w": 3, "d": 1, "l": 0, "u": 0}[r]

    short_results = [result(m, tid) for m in short]
    long_results  = [result(m, tid) for m in recent]

    ppg_short = safe_mean([points(r) for r in short_results])
    ppg_long  = safe_mean([points(r) for r in long_results])

    # xG features
    xg_for_short   = safe_mean([xg_for(m, tid)      for m in short])
    xg_ag_short    = safe_mean([xg_against(m, tid)   for m in short])
    xg_for_long    = safe_mean([xg_for(m, tid)      for m in recent])
    xg_ag_long     = safe_mean([xg_against(m, tid)   for m in recent])
    goals_for_long = safe_mean([goals_for(m, tid)    for m in recent])
    goals_ag_long  = safe_mean([goals_against(m, tid) for m in recent])

    # Days since last match (fatigue proxy)
    last_match = recent[0] if recent else None
    days_rest = (
        (before_date - last_match.kickoff).days
        if last_match and last_match.kickoff
        else 14
    )

    # Home/away split performance
    home_m = [m for m in recent if m.home_team_id == tid]
    away_m = [m for m in recent if m.away_team_id == tid]
    home_ppg = safe_mean([points(result(m, tid)) for m in home_m]) if home_m else 1.0
    away_ppg = safe_mean([points(result(m, tid)) for m in away_m]) if away_m else 1.0

    prefix = "home" if as_home else "away"
    return {
        f"{prefix}_elo":          round(team.elo_rating, 1),
        f"{prefix}_ppg_short":    round(ppg_short, 3),
        f"{prefix}_ppg_long":     round(ppg_long, 3),
        f"{prefix}_xg_for_s":     round(xg_for_short, 3),
        f"{prefix}_xg_ag_s":      round(xg_ag_short, 3),
        f"{prefix}_xg_for_l":     round(xg_for_long, 3),
        f"{prefix}_xg_ag_l":      round(xg_ag_long, 3),
        f"{prefix}_goals_for_l":  round(goals_for_long, 3),
        f"{prefix}_goals_ag_l":   round(goals_ag_long, 3),
        f"{prefix}_days_rest":    days_rest,
        f"{prefix}_home_ppg":     round(home_ppg, 3),
        f"{prefix}_away_ppg":     round(away_ppg, 3),
        f"{prefix}_matches_used": len(recent),
    }


def _head_to_head(
    db: Session,
    home_team_id: int,
    away_team_id: int,
    before_date: datetime,
    n: int = 5,
) -> dict:
    """Head-to-head record between two teams."""
    h2h = (
        db.query(Match)
        .filter(
            Match.status == "FT",
            Match.kickoff < before_date,
            (
                and_(Match.home_team_id == home_team_id, Match.away_team_id == away_team_id)
                |
                and_(Match.home_team_id == away_team_id, Match.away_team_id == home_team_id)
            ),
        )
        .order_by(Match.kickoff.desc())
        .limit(n)
        .all()
    )

    wins_h = draws = wins_a = 0
    for m in h2h:
        if m.home_goals is None:
            continue
        if m.home_team_id == home_team_id:
            if m.home_goals > m.away_goals:
                wins_h += 1
            elif m.home_goals == m.away_goals:
                draws += 1
            else:
                wins_a += 1
        else:
            if m.away_goals > m.home_goals:
                wins_h += 1
            elif m.away_goals == m.home_goals:
                draws += 1
            else:
                wins_a += 1

    total = wins_h + draws + wins_a or 1
    return {
        "h2h_home_wins":  wins_h,
        "h2h_draws":      draws,
        "h2h_away_wins":  wins_a,
        "h2h_home_rate":  round(wins_h / total, 3),
        "h2h_draw_rate":  round(draws  / total, 3),
        "h2h_away_rate":  round(wins_a / total, 3),
        "h2h_total":      total,
    }


def build_features(db: Session, match: Match) -> Optional[dict]:
    """
    Build the full feature dict for a single match.
    Returns None if insufficient data.
    """
    if not match.kickoff:
        return None

    home = match.home_team
    away = match.away_team
    if not home or not away:
        return None

    ref_date = match.kickoff

    feats = {
        "match_id":    match.id,
        "home_team":   home.name,
        "away_team":   away.name,
        "is_neutral":  int(match.is_neutral),
        "elo_diff":    round(home.elo_rating - away.elo_rating, 1),
    }

    feats.update(_team_features(db, home, as_home=True,  before_date=ref_date))
    feats.update(_team_features(db, away, as_home=False, before_date=ref_date))
    feats.update(_head_to_head(db, home.id, away.id, before_date=ref_date))

    # Market odds as a feature (when available)
    latest_odds = (
        db.query(Odds)
        .filter_by(match_id=match.id)
        .order_by(Odds.fetched_at.desc())
        .first()
    )
    if latest_odds:
        feats["mkt_home_prob"] = latest_odds.home_prob
        feats["mkt_draw_prob"] = latest_odds.draw_prob
        feats["mkt_away_prob"] = latest_odds.away_prob
        feats["mkt_margin"]    = latest_odds.margin
    else:
        feats["mkt_home_prob"] = None
        feats["mkt_draw_prob"] = None
        feats["mkt_away_prob"] = None
        feats["mkt_margin"]    = None

    # Ground truth (for back-testing)
    if match.status == "FT" and match.home_goals is not None:
        hg, ag = match.home_goals, match.away_goals
        if hg > ag:
            feats["result"] = 0   # home win
        elif hg == ag:
            feats["result"] = 1   # draw
        else:
            feats["result"] = 2   # away win
    else:
        feats["result"] = None

    return feats


def build_feature_dataset(db: Session) -> pd.DataFrame:
    """Build a DataFrame of features for ALL finished matches (for training)."""
    matches = (
        db.query(Match)
        .filter(Match.status == "FT")
        .order_by(Match.kickoff.asc())
        .all()
    )
    rows = []
    for m in matches:
        f = build_features(db, m)
        if f and f.get("result") is not None:
            rows.append(f)

    logger.info(f"Feature dataset: {len(rows)} matches")
    return pd.DataFrame(rows)
