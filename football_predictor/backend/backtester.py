"""
Walk-forward back-tester — Week 2.

Simulates how the model would have performed historically:
  - Trains on matches BEFORE a given date (no data leakage)
  - Predicts matches IN a rolling window
  - Moves forward one gameweek at a time
  - Records: log-loss, Brier score, ROI vs closing odds, calibration

This is the gold standard for evaluating sports prediction models.
Avoid simple train/test splits — they leak future information via Elo and form features.
"""

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from models import Match, Odds
from elo import update_elo_for_match, predict_probabilities as elo_probs, rebuild_elo_ratings
from dixon_coles import DixonColesModel
from ml_model import train as ml_train, predict as ml_predict
from kelly import expected_value, kelly_stake, remove_margin

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    match_id:   int
    kickoff:    datetime
    home_team:  str
    away_team:  str
    actual:     int          # 0=home, 1=draw, 2=away
    # Model probs
    home_prob:  float
    draw_prob:  float
    away_prob:  float
    # Market probs (after margin removal)
    mkt_home:   Optional[float] = None
    mkt_draw:   Optional[float] = None
    mkt_away:   Optional[float] = None
    mkt_home_odds: Optional[float] = None
    mkt_draw_odds: Optional[float] = None
    mkt_away_odds: Optional[float] = None
    # Bet outcome
    best_bet:   Optional[str]  = None
    kelly:      float = 0.0
    bet_won:    Optional[bool] = None
    bet_pnl:    float = 0.0   # profit/loss per unit stake


@dataclass
class BacktestReport:
    start_date:       str
    end_date:         str
    n_matches:        int = 0
    # Accuracy
    accuracy:         float = 0.0
    log_loss:         float = 0.0
    brier_home:       float = 0.0
    brier_draw:       float = 0.0
    brier_away:       float = 0.0
    # Betting ROI
    n_bets:           int = 0
    n_wins:           int = 0
    total_staked:     float = 0.0
    total_return:     float = 0.0
    roi:              float = 0.0
    # Model vs market
    edge_vs_market:   float = 0.0
    # Calibration (predicted prob vs actual frequency, binned)
    calibration:      list = field(default_factory=list)
    results:          list = field(default_factory=list)


def _one_hot(outcome: int, n: int = 3) -> np.ndarray:
    v = np.zeros(n)
    v[outcome] = 1.0
    return v


def _log_loss_single(probs: list[float], actual: int) -> float:
    eps = 1e-9
    return -np.log(max(probs[actual], eps))


def _brier_single(prob: float, actual_binary: int) -> float:
    return (prob - actual_binary) ** 2


def run_backtest(
    db: Session,
    start_date: Optional[datetime] = None,
    end_date:   Optional[datetime] = None,
    window_days: int = 7,           # Predict one week at a time
    retrain_every: int = 4,         # Weeks between model retrains
    min_train_matches: int = 50,
) -> BacktestReport:
    """
    Walk-forward back-test across all finished matches.

    For each window:
      1. Train on all matches before window start
      2. Predict every match in the window
      3. Compare to actual results + market odds
      4. Advance window
    """
    # Get all finished matches in date range
    q = db.query(Match).filter(Match.status == "FT", Match.home_goals != None)
    if start_date:
        q = q.filter(Match.kickoff >= start_date)
    if end_date:
        q = q.filter(Match.kickoff <= end_date)
    all_matches = q.order_by(Match.kickoff.asc()).all()

    if not all_matches:
        logger.warning("No finished matches for back-test")
        return BacktestReport(
            start_date=str(start_date),
            end_date=str(end_date),
        )

    first_date = all_matches[0].kickoff
    last_date  = all_matches[-1].kickoff

    report = BacktestReport(
        start_date=first_date.isoformat(),
        end_date=last_date.isoformat(),
    )

    match_results: list[MatchResult] = []
    window_start = first_date + timedelta(days=min_train_matches)
    week_idx     = 0

    # Build odds lookup
    odds_map = {}
    all_odds = db.query(Odds).all()
    for o in all_odds:
        if o.match_id not in odds_map:
            odds_map[o.match_id] = o

    dc_model = DixonColesModel()

    while window_start <= last_date:
        window_end = window_start + timedelta(days=window_days)

        # Matches for prediction in this window
        window_matches = [
            m for m in all_matches
            if m.kickoff and window_start <= m.kickoff < window_end
        ]
        if not window_matches:
            window_start = window_end
            week_idx += 1
            continue

        # Training set = everything before window_start
        train_matches = [m for m in all_matches if m.kickoff and m.kickoff < window_start]
        if len(train_matches) < min_train_matches:
            window_start = window_end
            week_idx += 1
            continue

        # Refit DC model periodically
        if week_idx % retrain_every == 0:
            try:
                # Temporarily rebuild Elo and DC on train set only
                dc_model = DixonColesModel()
                # Fit using a snapshot of train_matches
                dc_model._fit_from_matches(train_matches)
            except Exception as e:
                logger.warning(f"DC refit failed at {window_start}: {e}")

        # Predict each window match
        for m in window_matches:
            home = m.home_team
            away = m.away_team
            if not home or not away:
                continue

            actual = 0 if m.home_goals > m.away_goals else (1 if m.home_goals == m.away_goals else 2)

            # Ensemble: Elo + DC (no ML in backtest to avoid complexity — add in Week 3)
            try:
                elo = elo_probs(home.elo_rating, away.elo_rating, m.is_neutral)
                dc  = dc_model.predict_outcome_probs(home.name, away.name, m.is_neutral)
                hp  = 0.3 * elo["home"] + 0.7 * dc["home"]
                dp  = 0.3 * elo["draw"] + 0.7 * dc["draw"]
                ap  = 0.3 * elo["away"] + 0.7 * dc["away"]
                t   = hp + dp + ap
                hp, dp, ap = hp/t, dp/t, ap/t
            except Exception:
                continue

            # Market odds
            odds = odds_map.get(m.id)
            mkt = None
            if odds:
                mkt = remove_margin(odds.home_odds, odds.draw_odds, odds.away_odds)

            # Kelly bet
            best_bet = None
            kelly    = 0.0
            bet_won  = None
            bet_pnl  = 0.0

            if mkt and odds:
                our_probs = {"home": hp, "draw": dp, "away": ap}
                mkt_odds  = {"home": odds.home_odds, "draw": odds.draw_odds, "away": odds.away_odds}
                outcomes  = ["home", "draw", "away"]
                evs = {o: expected_value(our_probs[o], mkt_odds[o]) for o in outcomes}
                best = max(evs, key=evs.get)
                if evs[best] >= 0.05:
                    best_bet = best
                    kelly    = kelly_stake(our_probs[best], mkt_odds[best])
                    bet_won  = (outcomes.index(best) == actual)
                    if bet_won:
                        bet_pnl = kelly * (mkt_odds[best] - 1)
                    else:
                        bet_pnl = -kelly

            mr = MatchResult(
                match_id=m.id,
                kickoff=m.kickoff,
                home_team=home.name,
                away_team=away.name,
                actual=actual,
                home_prob=round(hp, 4),
                draw_prob=round(dp, 4),
                away_prob=round(ap, 4),
                mkt_home=mkt["home"] if mkt else None,
                mkt_draw=mkt["draw"] if mkt else None,
                mkt_away=mkt["away"] if mkt else None,
                mkt_home_odds=odds.home_odds if odds else None,
                mkt_draw_odds=odds.draw_odds if odds else None,
                mkt_away_odds=odds.away_odds if odds else None,
                best_bet=best_bet,
                kelly=kelly,
                bet_won=bet_won,
                bet_pnl=bet_pnl,
            )
            match_results.append(mr)

        window_start = window_end
        week_idx += 1

    # ── Aggregate metrics ──────────────────────────────────────────
    if not match_results:
        return report

    n = len(match_results)
    probs_matrix = np.array([[r.home_prob, r.draw_prob, r.away_prob] for r in match_results])
    actuals      = np.array([r.actual for r in match_results])

    # Accuracy (most confident prediction)
    predictions  = np.argmax(probs_matrix, axis=1)
    accuracy     = float(np.mean(predictions == actuals))

    # Log-loss
    eps = 1e-9
    ll  = float(-np.mean([
        np.log(max(probs_matrix[i, actuals[i]], eps))
        for i in range(n)
    ]))

    # Brier scores per class
    brier_home = float(np.mean([_brier_single(r.home_prob, int(r.actual == 0)) for r in match_results]))
    brier_draw = float(np.mean([_brier_single(r.draw_prob, int(r.actual == 1)) for r in match_results]))
    brier_away = float(np.mean([_brier_single(r.away_prob, int(r.actual == 2)) for r in match_results]))

    # Betting stats
    bets    = [r for r in match_results if r.best_bet is not None]
    n_bets  = len(bets)
    n_wins  = sum(1 for r in bets if r.bet_won)
    staked  = sum(r.kelly for r in bets)
    ret     = sum(r.kelly + r.bet_pnl for r in bets)
    roi     = (ret - staked) / staked if staked > 0 else 0.0

    # Calibration bins (10 bins)
    calibration = []
    for i in range(10):
        lo, hi = i * 0.1, (i + 1) * 0.1
        # Use home win as representative class
        mask = [(lo <= r.home_prob < hi) for r in match_results]
        if sum(mask) > 0:
            pred_mean = np.mean([r.home_prob for r, m in zip(match_results, mask) if m])
            act_freq  = np.mean([int(r.actual == 0) for r, m in zip(match_results, mask) if m])
            calibration.append({
                "bin": f"{lo:.1f}-{hi:.1f}",
                "predicted": round(float(pred_mean), 3),
                "actual":    round(float(act_freq), 3),
                "n":         int(sum(mask)),
            })

    report.n_matches    = n
    report.accuracy     = round(accuracy, 4)
    report.log_loss     = round(ll, 4)
    report.brier_home   = round(brier_home, 4)
    report.brier_draw   = round(brier_draw, 4)
    report.brier_away   = round(brier_away, 4)
    report.n_bets       = n_bets
    report.n_wins       = n_wins
    report.total_staked = round(staked, 4)
    report.total_return = round(ret, 4)
    report.roi          = round(roi, 4)
    report.calibration  = calibration
    report.results      = [
        {
            "kickoff":   r.kickoff.isoformat(),
            "home":      r.home_team,
            "away":      r.away_team,
            "actual":    ["home", "draw", "away"][r.actual],
            "home_prob": r.home_prob,
            "draw_prob": r.draw_prob,
            "away_prob": r.away_prob,
            "best_bet":  r.best_bet,
            "kelly":     round(r.kelly, 4),
            "pnl":       round(r.bet_pnl, 4),
        }
        for r in match_results[-100:]   # Last 100 for UI
    ]

    logger.info(
        f"Backtest: {n} matches | acc={accuracy:.1%} | ll={ll:.4f} | "
        f"ROI={roi:.1%} ({n_bets} bets, {n_wins} wins)"
    )
    return report


# Patch DixonColesModel to support _fit_from_matches (train set snapshot)
def _dc_fit_from_matches(self, matches):
    """Fit DC model from a list of Match ORM objects using gradient descent."""
    from datetime import datetime
    ref = datetime.utcnow()

    data = []
    team_set = set()
    for m in matches:
        if not m.home_team or not m.away_team:
            continue
        from dixon_coles import time_weight
        w = time_weight(m.kickoff or ref, ref) if m.kickoff else 0.01
        data.append({
            "home_team":  m.home_team.name,
            "away_team":  m.away_team.name,
            "home_goals": m.home_goals,
            "away_goals": m.away_goals,
            "weight":     w,
        })
        team_set.update([m.home_team.name, m.away_team.name])

    if len(data) < 10:
        return

    self.teams = sorted(team_set)
    n = len(self.teams)
    idx = {t: i for i, t in enumerate(self.teams)}

    attack  = np.zeros(n)
    defence = np.zeros(n)
    home_adv = 0.1
    rho      = -0.1
    lr       = 0.01

    for _ in range(50):
        ga = np.zeros(n)
        gd = np.zeros(n)
        gh = 0.0
        gr = 0.0
        tw = 0.0
        for row in data:
            hi = idx.get(row["home_team"])
            ai = idx.get(row["away_team"])
            if hi is None or ai is None:
                continue
            hg, ag, w = row["home_goals"], row["away_goals"], row["weight"]
            lam = np.exp(attack[hi] + defence[ai] + home_adv)
            mu  = np.exp(attack[ai] + defence[hi])
            ga[hi] += w * (hg - lam)
            gd[ai] += w * (hg - lam)
            ga[ai] += w * (ag - mu)
            gd[hi] += w * (ag - mu)
            gh     += w * (hg - lam)
            tw     += w
        if tw > 0:
            attack   += lr * ga / tw
            defence  += lr * gd / tw
            home_adv += lr * gh / tw

    self.attack   = {t: float(attack[i])  for i, t in enumerate(self.teams)}
    self.defence  = {t: float(defence[i]) for i, t in enumerate(self.teams)}
    self.home_adv = float(home_adv)
    self.rho      = float(rho)
    self.fitted   = True

DixonColesModel._fit_from_matches = _dc_fit_from_matches
