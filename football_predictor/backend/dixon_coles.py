"""
Dixon-Coles Poisson model for football score prediction.
Reference: Dixon & Coles (1997) "Modelling Association Football Scores
           and Inefficiencies in the Football Betting Market"

Estimates attack/defence parameters per team and a home advantage constant.
Uses time-weighting so recent matches matter more than old ones.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson
from sqlalchemy.orm import Session

from models import Match, Team

logger = logging.getLogger(__name__)

# Down-weight matches older than this
TIME_DECAY_HALF_LIFE_DAYS = 90


def time_weight(match_date: datetime, reference_date: datetime) -> float:
    """Exponential decay weight: 1.0 for today, ~0.5 for 90-day-old match."""
    delta = max(0, (reference_date - match_date).days)
    return np.exp(-np.log(2) * delta / TIME_DECAY_HALF_LIFE_DAYS)


def dc_tau(home_goals: int, away_goals: int, lambda_: float, mu_: float, rho: float) -> float:
    """
    Dixon-Coles low-score correction factor (tau).
    Corrects for over/under-dispersion in 0-0, 1-0, 0-1, 1-1 results.
    """
    if home_goals == 0 and away_goals == 0:
        return 1 - lambda_ * mu_ * rho
    elif home_goals == 1 and away_goals == 0:
        return 1 + mu_ * rho
    elif home_goals == 0 and away_goals == 1:
        return 1 + lambda_ * rho
    elif home_goals == 1 and away_goals == 1:
        return 1 - rho
    else:
        return 1.0


def log_likelihood(params: np.ndarray, data: list[dict], teams: list[str]) -> float:
    """
    Negative log-likelihood for the Dixon-Coles model.
    params layout: [attack_0, ..., attack_n, defence_0, ..., defence_n, home_adv, rho]
    """
    n = len(teams)
    attack   = {t: params[i]   for i, t in enumerate(teams)}
    defence  = {t: params[n+i] for i, t in enumerate(teams)}
    home_adv = params[2*n]
    rho      = params[2*n + 1]

    ll = 0.0
    for row in data:
        ht, at = row["home_team"], row["away_team"]
        if ht not in attack or at not in attack:
            continue
        hg, ag = row["home_goals"], row["away_goals"]
        w = row["weight"]

        lambda_ = np.exp(attack[ht] + defence[at] + home_adv)
        mu_     = np.exp(attack[at] + defence[ht])

        tau = dc_tau(hg, ag, lambda_, mu_, rho)
        if tau <= 0:
            tau = 1e-10

        ll += w * (
            np.log(tau)
            + poisson.logpmf(hg, lambda_)
            + poisson.logpmf(ag, mu_)
        )

    return -ll


class DixonColesModel:
    def __init__(self):
        self.teams:    list[str]          = []
        self.attack:   dict[str, float]   = {}
        self.defence:  dict[str, float]   = {}
        self.home_adv: float              = 0.0
        self.rho:      float              = 0.0
        self.fitted:   bool               = False
        self.fit_date: Optional[datetime] = None

    def fit(self, db: Session) -> None:
        """Fit the model on all finished matches in the DB."""
        ref = datetime.utcnow()

        matches = (
            db.query(Match)
            .filter(Match.status == "FT", Match.home_goals != None)
            .order_by(Match.kickoff.desc())
            .limit(500)
            .all()
        )
        if len(matches) < 20:
            logger.warning("Dixon-Coles: fewer than 20 matches — model may be unreliable")

        data = []
        team_set: set[str] = set()
        for m in matches:
            hn = m.home_team.name
            an = m.away_team.name
            w  = time_weight(m.kickoff or ref, ref) if m.kickoff else 0.01
            data.append({
                "home_team":  hn,
                "away_team":  an,
                "home_goals": m.home_goals,
                "away_goals": m.away_goals,
                "weight":     w,
            })
            team_set.update([hn, an])

        self.teams = sorted(team_set)
        n = len(self.teams)

        x0 = np.zeros(2 * n + 2)
        x0[2*n]     =  0.1
        x0[2*n + 1] = -0.1

        result = minimize(
            log_likelihood,
            x0,
            args=(data, self.teams),
            method="L-BFGS-B",
            options={"maxiter": 100, "ftol": 1e-5},
        )

        best = result.x
        self.attack   = {t: best[i]   for i, t in enumerate(self.teams)}
        self.defence  = {t: best[n+i] for i, t in enumerate(self.teams)}
        self.home_adv = best[2*n]
        self.rho      = best[2*n + 1]
        self.fitted   = True
        self.fit_date = ref

        logger.info(
            f"Dixon-Coles fitted on {len(data)} matches, "
            f"{n} teams, home_adv={self.home_adv:.3f}, rho={self.rho:.3f}"
        )

    def predict_score_matrix(
        self,
        home_team:  str,
        away_team:  str,
        is_neutral: bool = False,
        max_goals:  int  = 8,
    ) -> Optional[np.ndarray]:
        """
        Return a (max_goals+1 x max_goals+1) probability matrix.
        Element [i, j] = P(home scores i, away scores j).
        """
        if not self.fitted:
            raise RuntimeError("Model not fitted — call fit() first")

        if home_team not in self.attack:
            logger.warning(f"Dixon-Coles: unknown team '{home_team}', using mean attack")
        if away_team not in self.attack:
            logger.warning(f"Dixon-Coles: unknown team '{away_team}', using mean attack")

        ha = self.attack.get(home_team,  np.mean(list(self.attack.values())))
        hd = self.defence.get(home_team, np.mean(list(self.defence.values())))
        aa = self.attack.get(away_team,  np.mean(list(self.attack.values())))
        ad = self.defence.get(away_team, np.mean(list(self.defence.values())))

        home_adj = self.home_adv if not is_neutral else 0.0
        lambda_  = np.exp(ha + ad + home_adj)
        mu_      = np.exp(aa + hd)

        matrix = np.zeros((max_goals + 1, max_goals + 1))
        for i in range(max_goals + 1):
            for j in range(max_goals + 1):
                tau = dc_tau(i, j, lambda_, mu_, self.rho)
                matrix[i, j] = (
                    tau
                    * poisson.pmf(i, lambda_)
                    * poisson.pmf(j, mu_)
                )
        return matrix

    def predict_outcome_probs(
        self,
        home_team:  str,
        away_team:  str,
        is_neutral: bool = False,
    ) -> dict[str, float]:
        """Return dict with 'home', 'draw', 'away' win probabilities."""
        mat = self.predict_score_matrix(home_team, away_team, is_neutral)
        if mat is None:
            return {"home": 0.33, "draw": 0.33, "away": 0.34}

        p_home = float(np.sum(np.tril(mat, -1)))
        p_draw = float(np.sum(np.diag(mat)))
        p_away = float(np.sum(np.triu(mat,  1)))

        total = p_home + p_draw + p_away
        return {
            "home": round(p_home / total, 4),
            "draw": round(p_draw / total, 4),
            "away": round(p_away / total, 4),
        }

    def predict_expected_goals(
        self,
        home_team:  str,
        away_team:  str,
        is_neutral: bool = False,
    ) -> dict[str, float]:
        """Return expected goals for each team."""
        ha = self.attack.get(home_team,  np.mean(list(self.attack.values())))
        hd = self.defence.get(home_team, np.mean(list(self.defence.values())))
        aa = self.attack.get(away_team,  np.mean(list(self.attack.values())))
        ad = self.defence.get(away_team, np.mean(list(self.defence.values())))

        home_adj = self.home_adv if not is_neutral else 0.0
        return {
            "home_xg": round(np.exp(ha + ad + home_adj), 2),
            "away_xg": round(np.exp(aa + hd), 2),
        }

    def team_ratings(self) -> list[dict]:
        """Return all team ratings sorted by attack - defence (net strength)."""
        rows = []
        for t in self.teams:
            rows.append({
                "team":    t,
                "attack":  round(self.attack[t], 3),
                "defence": round(self.defence[t], 3),
                "net":     round(self.attack[t] - self.defence[t], 3),
            })
        return sorted(rows, key=lambda r: -r["net"])