"""
International football module — Week 3.

Key differences from club football:
  1. Far fewer matches per team → small sample sizes
  2. Squad strength matters more than form (international breaks disrupt rhythm)
  3. Home advantage is smaller (many games at neutral venues)
  4. Tournament fatigue effects (extra time, penalties, travel)
  5. Player availability (injuries, suspensions from yellow card accumulation)

World Cup simulator:
  - Group stage: round-robin with Poisson score simulation
  - Knockout rounds: with extra time + penalty probability
  - Monte Carlo: N simulations → winner probability distribution
"""

import logging
import random
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Neutral venue reduces home advantage by this fraction
NEUTRAL_HOME_ADVANTAGE = 0.0   # Full neutral
# Elo K-factor adjustments for international
K_FRIENDLY      = 20.0
K_QUALIFIER     = 40.0
K_CONFEDERATION = 50.0
K_WORLD_CUP_GS  = 60.0
K_WORLD_CUP_KO  = 80.0

# Penalty probability when draw after ET in knockout
PENALTY_PROB = 0.5   # 50/50 in penalties (slight edge to stronger team handled below)


# ── Team strength (used when Elo not available from DB) ──────────
# 2026 World Cup qualified nations — approximate Elo entering tournament
# Updated from FIFA rankings + ClubElo international estimates
WORLD_CUP_2026_TEAMS = {
    # Group A (example — fill in actual groups once draw is done)
    "Argentina":    2010, "Canada":       1680, "Chile":        1720, "Peru":        1680,
    "France":       2000, "Belgium":      1850, "Croatia":      1830, "Ukraine":     1740,
    "Spain":        1950, "Germany":      1890, "Portugal":     1900, "Netherlands": 1870,
    "Brazil":       1960, "Uruguay":      1780, "Colombia":     1750, "Ecuador":     1680,
    "England":      1900, "USA":          1760, "Mexico":       1760, "Panama":      1620,
    "Morocco":      1760, "Senegal":      1740, "Egypt":        1700, "South Africa":1620,
    "Japan":        1790, "South Korea":  1740, "Australia":    1680, "Iran":        1700,
    "Saudi Arabia": 1660, "Qatar":        1620, "Nigeria":      1700, "Cameroon":    1660,
    "Serbia":       1800, "Switzerland":  1830, "Austria":      1790, "Denmark":     1820,
    "Poland":       1740, "Czech Republic":1760,"Slovakia":     1700, "Hungary":     1700,
    "Norway":       1780, "Sweden":       1760, "Finland":      1680,
    "New Zealand":  1600, "Honduras":     1600, "Jamaica":      1620, "Costa Rica":  1680,
    "Venezuela":    1660, "Bolivia":      1580, "Paraguay":     1660,
    "Tunisia":      1700, "Algeria":      1700, "Mali":         1660, "Guinea":      1620,
    "DR Congo":     1680, "Ivory Coast":  1720,
    "Indonesia":    1580, "Iraq":         1680, "Jordan":       1640, "Uzbekistan":  1660,
}


@dataclass
class SimTeam:
    name:   str
    elo:    float
    group:  str = ""
    # Group stage points
    points:  int = 0
    gf:      int = 0
    ga:      int = 0
    gd:      int = 0
    played:  int = 0


@dataclass
class GroupResult:
    group:   str
    teams:   list[SimTeam]
    matches: list[dict] = field(default_factory=list)

    def standings(self) -> list[SimTeam]:
        return sorted(
            self.teams,
            key=lambda t: (-t.points, -t.gd, -t.gf, t.name),
        )


@dataclass
class TournamentResult:
    winner:      str
    finalist:    str
    third:       Optional[str]
    fourth:      Optional[str]
    group_results: list[GroupResult] = field(default_factory=list)
    knockout_matches: list[dict] = field(default_factory=list)


def _elo_to_goal_rates(home_elo: float, away_elo: float, neutral: bool = True) -> tuple[float, float]:
    """
    Convert Elo ratings to expected goals per team using calibrated relationship.
    International: average goals per game ≈ 2.6 (lower than club football).
    """
    base_goals = 1.3   # Per team per game (international average)
    elo_diff   = home_elo - away_elo
    # Each 200 Elo points ≈ 0.3 goals advantage
    advantage  = elo_diff / 200.0 * 0.3
    home_adj   = 0.0 if neutral else 0.15   # Neutral = no home boost
    lambda_h   = max(0.3, base_goals + advantage + home_adj)
    mu_a       = max(0.3, base_goals - advantage)
    return lambda_h, mu_a


def simulate_match(
    home_elo: float,
    away_elo: float,
    neutral:  bool = True,
    allow_draw: bool = True,
) -> tuple[int, int, str]:
    """
    Simulate one match using Poisson goal sampling.
    Returns (home_goals, away_goals, outcome_code).
    outcome_code: "H" | "D" | "A" (or "PH"/"PA" for penalty shootout)
    """
    lh, la = _elo_to_goal_rates(home_elo, away_elo, neutral)
    hg = int(np.random.poisson(lh))
    ag = int(np.random.poisson(la))

    if hg > ag:
        return hg, ag, "H"
    elif hg < ag:
        return hg, ag, "A"
    else:
        if allow_draw:
            return hg, ag, "D"
        # Knockout: extra time + penalties
        # Extra time — small additional scoring
        et_lh, et_la = lh * 0.3, la * 0.3
        eth = int(np.random.poisson(et_lh))
        eta = int(np.random.poisson(et_la))
        hg += eth; ag += eta
        if hg > ag:
            return hg, ag, "H"
        elif hg < ag:
            return hg, ag, "A"
        # Penalties: slight edge to stronger team
        p_home_wins = 0.5 + (home_elo - away_elo) / 4000.0
        p_home_wins = max(0.35, min(0.65, p_home_wins))
        if random.random() < p_home_wins:
            return hg, ag, "PH"
        else:
            return hg, ag, "PA"


def simulate_group(teams: list[SimTeam], neutral: bool = True) -> GroupResult:
    """Run a full round-robin group stage."""
    group_teams = [SimTeam(name=t.name, elo=t.elo, group=t.group) for t in teams]
    matches = []

    for i in range(len(group_teams)):
        for j in range(i + 1, len(group_teams)):
            home = group_teams[i]
            away = group_teams[j]
            hg, ag, code = simulate_match(home.elo, away.elo, neutral=neutral, allow_draw=True)

            home.gf += hg; home.ga += ag; home.played += 1
            away.gf += ag; away.ga += hg; away.played += 1
            home.gd = home.gf - home.ga
            away.gd = away.gf - away.ga

            if code == "H":
                home.points += 3
            elif code == "D":
                home.points += 1
                away.points += 1
            else:
                away.points += 3

            matches.append({
                "home": home.name, "away": away.name,
                "home_goals": hg, "away_goals": ag, "code": code,
            })

    return GroupResult(
        group=group_teams[0].group,
        teams=group_teams,
        matches=matches,
    )


def _play_ko_round(teams: list[str], elo: dict[str, float]) -> list[str]:
    winners = []
    for i in range(0, len(teams), 2):
        if i + 1 >= len(teams):
            winners.append(teams[i])
            continue
        h, a = teams[i], teams[i + 1]
        _, _, code = simulate_match(elo[h], elo[a], neutral=True, allow_draw=False)
        winners.append(h if code in ("H", "PH") else a)
    return winners


def simulate_tournament(
    groups: dict[str, list[str]],
    elo_ratings: dict[str, float],
    n_simulations: int = 10_000,
) -> dict:
    """
    Monte Carlo simulation of the full tournament.

    Args:
        groups: {"A": ["Team1", "Team2", "Team3", "Team4"], "B": [...], ...}
        elo_ratings: {"Team1": 1850.0, ...}
        n_simulations: number of Monte Carlo runs

    Returns dict with win/finalist/semifinal probabilities per team.
    """
    all_teams = [t for g in groups.values() for t in g]
    win_count   = {t: 0 for t in all_teams}
    final_count = {t: 0 for t in all_teams}
    semi_count  = {t: 0 for t in all_teams}
    qf_count    = {t: 0 for t in all_teams}
    live_elo    = {t: elo_ratings.get(t, 1700.0) for t in all_teams}
    group_keys  = sorted(groups.keys())

    # ── Vectorized group stage ────────────────────────────────────────
    # Pre-generate ALL Poisson draws for every group in one batch call.
    # Since Elos are fixed across simulations, lambdas are constant per pair.
    advancers_by_group: dict[str, np.ndarray] = {}

    for gk, team_names in groups.items():
        n_teams = len(team_names)
        elos    = [elo_ratings.get(t, 1700.0) for t in team_names]
        pairs   = [(i, j) for i in range(n_teams) for j in range(i + 1, n_teams)]

        lh_arr = np.array([_elo_to_goal_rates(elos[i], elos[j])[0] for i, j in pairs])
        la_arr = np.array([_elo_to_goal_rates(elos[i], elos[j])[1] for i, j in pairs])

        # Shape: (n_simulations, n_matches)
        hg_all = np.random.poisson(lh_arr, size=(n_simulations, len(pairs)))
        ag_all = np.random.poisson(la_arr, size=(n_simulations, len(pairs)))

        pts = np.zeros((n_simulations, n_teams), dtype=np.int32)
        gf  = np.zeros((n_simulations, n_teams), dtype=np.int32)
        ga  = np.zeros((n_simulations, n_teams), dtype=np.int32)

        for m_idx, (ti, tj) in enumerate(pairs):
            hg = hg_all[:, m_idx]
            ag = ag_all[:, m_idx]
            hw   = hg > ag
            draw = hg == ag
            aw   = hg < ag
            pts[:, ti] += 3 * hw + draw
            pts[:, tj] += 3 * aw + draw
            gf[:, ti] += hg;  ga[:, ti] += ag
            gf[:, tj] += ag;  ga[:, tj] += hg

        gd = gf - ga
        # Composite sort key: points > gd > gf, all descending
        composite = pts * 10_000 + gd * 100 + gf
        order = np.argsort(-composite, axis=1)           # (n_sims, n_teams)
        top2  = np.array(team_names)[order[:, :2]]       # (n_sims, 2) of strings
        advancers_by_group[gk] = top2

    # ── Knockout rounds (sequential per simulation) ───────────────────
    for s in range(n_simulations):
        ko_teams: list[str] = []
        for gk in group_keys:
            if gk in advancers_by_group:
                ko_teams.extend(advancers_by_group[gk][s].tolist())

        r16 = _play_ko_round(ko_teams, live_elo)
        for t in r16:
            qf_count[t] += 1

        qf = _play_ko_round(r16, live_elo)
        for t in qf:
            semi_count[t] += 1

        sf = _play_ko_round(qf, live_elo)
        for t in sf:
            final_count[t] += 1

        if len(sf) >= 2:
            _, _, code = simulate_match(
                live_elo[sf[0]], live_elo[sf[1]], neutral=True, allow_draw=False
            )
            win_count[sf[0] if code in ("H", "PH") else sf[1]] += 1

    result = sorted(
        [
            {
                "team":              t,
                "elo":               elo_ratings.get(t, 1700.0),
                "win_prob":          round(win_count[t] / n_simulations, 4),
                "final_prob":        round(final_count[t] / n_simulations, 4),
                "semifinal_prob":    round(semi_count[t] / n_simulations, 4),
                "quarterfinal_prob": round(qf_count[t] / n_simulations, 4),
            }
            for t in all_teams
        ],
        key=lambda r: -r["win_prob"],
    )
    return {"n_simulations": n_simulations, "teams": result}


def predict_international_match(
    home_team: str,
    away_team: str,
    home_elo:  Optional[float] = None,
    away_elo:  Optional[float] = None,
    neutral:   bool = True,
    n_sims:    int = 50_000,
) -> dict:
    """
    Predict a single international match via Monte Carlo simulation.
    Falls back to WORLD_CUP_2026_TEAMS Elo if not provided.
    """
    h_elo = home_elo or WORLD_CUP_2026_TEAMS.get(home_team, 1700.0)
    a_elo = away_elo or WORLD_CUP_2026_TEAMS.get(away_team, 1700.0)

    results = {"H": 0, "D": 0, "A": 0, "PH": 0, "PA": 0}
    for _ in range(n_sims):
        _, _, code = simulate_match(h_elo, a_elo, neutral=neutral, allow_draw=True)
        results[code] += 1

    total = n_sims
    return {
        "home_team":  home_team,
        "away_team":  away_team,
        "home_elo":   h_elo,
        "away_elo":   a_elo,
        "home_prob":  round((results["H"]) / total, 4),
        "draw_prob":  round(results["D"] / total, 4),
        "away_prob":  round((results["A"]) / total, 4),
        "home_xg":    round(_elo_to_goal_rates(h_elo, a_elo, neutral)[0], 2),
        "away_xg":    round(_elo_to_goal_rates(h_elo, a_elo, neutral)[1], 2),
    }
