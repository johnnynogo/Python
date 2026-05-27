"""
Kelly criterion and bet value utilities.

Kelly fraction = (bp - q) / b
  b = decimal odds - 1  (net payout per unit stake)
  p = our estimated probability of winning
  q = 1 - p

We use fractional Kelly (25%) to reduce variance.
"""
from typing import Optional


KELLY_FRACTION = 0.25      # Fractional Kelly (conservative)
MIN_EDGE       = 0.05      # Minimum edge before flagging a bet (7%) made it more stricter as it was 3% in first iterations. 
MAX_KELLY      = 0.10      # Cap stake at 10% of bankroll no matter what


def remove_margin(home_odds: float, draw_odds: float, away_odds: float) -> dict:
    """
    Remove the bookmaker margin (overround) to get fair implied probabilities.
    """
    total = 1 / home_odds + 1 / draw_odds + 1 / away_odds
    return {
        "home": round((1 / home_odds) / total, 4),
        "draw": round((1 / draw_odds) / total, 4),
        "away": round((1 / away_odds) / total, 4),
        "margin": round(total - 1, 4),
    }


def expected_value(our_prob: float, decimal_odds: float) -> float:
    """
    EV per unit stake.  Positive = edge over the market.
    EV = p * (odds - 1) - (1 - p) = p * odds - 1
    """
    return round(our_prob * decimal_odds - 1.0, 4)


def kelly_stake(our_prob: float, decimal_odds: float) -> float:
    """
    Fractional Kelly stake as a fraction of bankroll (0–1).
    Returns 0 if the bet has no edge.
    """
    b = decimal_odds - 1.0
    if b <= 0:
        return 0.0
    q = 1.0 - our_prob
    k = (b * our_prob - q) / b
    if k <= 0:
        return 0.0
    return round(min(k * KELLY_FRACTION, MAX_KELLY), 4)


def evaluate_match(
    our_probs: dict[str, float],
    market_odds: dict[str, float],   # {"home": 2.10, "draw": 3.20, "away": 3.50}
) -> dict:
    """
    Given our probability estimates and market odds, compute:
    - Expected value per outcome
    - Kelly stake per outcome
    - Best bet recommendation
    """
    results = {}
    for outcome in ("home", "draw", "away"):
        p    = our_probs.get(outcome, 0.0)
        odds = market_odds.get(outcome)
        if not odds:
            results[outcome] = {"ev": None, "kelly": None, "odds": None}
            continue
        ev    = expected_value(p, odds)
        kelly = kelly_stake(p, odds)
        results[outcome] = {"ev": ev, "kelly": kelly, "odds": odds}

    # Best bet = outcome with highest EV, if EV > MIN_EDGE
    best = max(results.items(), key=lambda kv: kv[1].get("ev") or -999)
    best_bet = best[0] if best[1].get("ev", 0) >= MIN_EDGE else "none"

    return {
        "home":     results["home"],
        "draw":     results["draw"],
        "away":     results["away"],
        "best_bet": best_bet,
    }
