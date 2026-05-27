"""
Elo rating engine for football teams.

Standard Elo with football-specific tweaks:
- K-factor varies by match importance
- Home advantage offset (+100 Elo points equivalent)
- Goal-difference multiplier (a 4-0 win updates more than a 1-0)
- Regress ratings toward mean at start of each season
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from models import Match, Team, EloHistory

logger = logging.getLogger(__name__)

DEFAULT_RATING   = 1500.0
HOME_ADVANTAGE   = 100.0      # Elo points added to home team before comparison
K_LEAGUE         = 20.0       # Standard league match
K_INTERNATIONAL  = 40.0       # International (higher variance)
K_WORLD_CUP      = 60.0       # World Cup knockout
SEASON_REGRESS   = 0.3        # Pull 30% back toward mean at season start


def expected_score(rating_a: float, rating_b: float) -> float:
    """Classic Elo expected score for player A."""
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def goal_diff_multiplier(home_goals: int, away_goals: int) -> float:
    """
    Weight larger wins more heavily.
    Based on World Football Elo Ratings methodology.
    """
    diff = abs(home_goals - away_goals)
    if diff <= 1:
        return 1.0
    elif diff == 2:
        return 1.5
    else:
        return (11.0 + diff) / 8.0


def actual_score(home_goals: int, away_goals: int) -> float:
    """
    Convert match result into 1.0 / 0.5 / 0.0 for home team.
    """
    if home_goals > away_goals:
        return 1.0
    elif home_goals == away_goals:
        return 0.5
    else:
        return 0.0


def update_elo(
    home_rating: float,
    away_rating: float,
    home_goals: int,
    away_goals: int,
    k: float = K_LEAGUE,
    is_neutral: bool = False,
) -> tuple[float, float]:
    """
    Compute updated Elo ratings after a match.
    Returns (new_home_rating, new_away_rating).
    """
    home_adj = home_rating + (0 if is_neutral else HOME_ADVANTAGE)
    exp_home  = expected_score(home_adj, away_rating)
    act_home  = actual_score(home_goals, away_goals)
    gdm       = goal_diff_multiplier(home_goals, away_goals)

    delta = k * gdm * (act_home - exp_home)
    return (
        round(home_rating + delta, 2),
        round(away_rating - delta, 2),
    )


def rebuild_elo_ratings(db: Session, k: float = K_LEAGUE) -> None:
    """
    Recalculate Elo ratings from scratch using all finished matches in DB.
    Resets all team ratings to DEFAULT_RATING first.
    """
    logger.info("Rebuilding Elo ratings from scratch…")

    # Reset all teams
    db.query(Team).update({"elo_rating": DEFAULT_RATING})
    db.query(EloHistory).delete()
    db.commit()

    # Replay matches in chronological order
    matches = (
        db.query(Match)
        .filter(Match.status == "FT", Match.home_goals != None)
        .order_by(Match.kickoff.asc())
        .all()
    )

    for match in matches:
        home = match.home_team
        away = match.away_team

        new_home, new_away = update_elo(
            home.elo_rating,
            away.elo_rating,
            match.home_goals,
            match.away_goals,
            k=k,
            is_neutral=match.is_neutral,
        )

        home.elo_rating = new_home
        away.elo_rating = new_away

        db.add(EloHistory(team_id=home.id, match_id=match.id, rating=new_home))
        db.add(EloHistory(team_id=away.id, match_id=match.id, rating=new_away))

    db.commit()
    logger.info(f"Elo rebuild complete — processed {len(matches)} matches.")


def update_elo_for_match(db: Session, match: Match, k: float = K_LEAGUE) -> None:
    """
    Update Elo for a single match (called incrementally after each result).
    """
    if match.status != "FT" or match.home_goals is None:
        return

    home = match.home_team
    away = match.away_team

    new_home, new_away = update_elo(
        home.elo_rating,
        away.elo_rating,
        match.home_goals,
        match.away_goals,
        k=k,
        is_neutral=match.is_neutral,
    )

    home.elo_rating = new_home
    away.elo_rating = new_away

    db.add(EloHistory(team_id=home.id, match_id=match.id, rating=new_home))
    db.add(EloHistory(team_id=away.id, match_id=match.id, rating=new_away))
    db.commit()


def predict_probabilities(
    home_rating: float,
    away_rating: float,
    is_neutral: bool = False,
) -> dict[str, float]:
    """
    Convert Elo ratings into win/draw/loss probabilities.
    Uses the method from Elo538 (FiveThirtyEight methodology):
      win_prob ≈ normal CDF of Elo difference / 600
    Draw probability is estimated as a function of the Elo gap.
    """
    import math

    home_adj  = home_rating + (0 if is_neutral else HOME_ADVANTAGE)
    elo_diff  = home_adj - away_rating
    elo_std   = 600.0

    # FiveThirtyEight approach: use logistic transform
    p_home_or_draw = 1.0 / (1.0 + 10.0 ** (-elo_diff / 400.0))
    p_away_or_draw = 1.0 - p_home_or_draw

    # Estimate draw probability (peaks at ~27% when teams are equal)
    draw_base = 0.27 * math.exp(-0.001 * (elo_diff ** 2))

    p_home = max(0.05, p_home_or_draw - draw_base / 2)
    p_away = max(0.05, p_away_or_draw - draw_base / 2)
    p_draw = max(0.05, 1.0 - p_home - p_away)

    # Normalise
    total  = p_home + p_draw + p_away
    return {
        "home": round(p_home / total, 4),
        "draw": round(p_draw / total, 4),
        "away": round(p_away / total, 4),
    }
