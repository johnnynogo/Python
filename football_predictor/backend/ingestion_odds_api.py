"""
The Odds API ingestion client.
Docs: https://the-odds-api.com/liveapi/guides/v4/

Free tier: 500 requests/month. Each call to /odds costs 1 request.
We fetch h2h (1X2) odds only — the most useful market for our model.

Covers leagues that API-Football free tier misses:
  - Eliteserien (Norway)
  - Allsvenskan (Sweden)
  - Premier League (backup / better bookmaker coverage)
"""
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from models import League, Match, Odds, SyncLog

logger = logging.getLogger(__name__)

API_BASE = "https://api.the-odds-api.com/v4"
ODDS_KEY = os.getenv("ODDS_API_KEY", "")

# Minimum hours between automatic odds syncs (protects token budget)
MIN_SYNC_INTERVAL_HOURS = 4

ODDS_API_LEAGUES: dict[int, str] = {
    39:  "soccer_epl",
    78:  "soccer_germany_bundesliga",
    135: "soccer_italy_serie_a",
    61:  "soccer_france_ligue_one",
    140: "soccer_spain_la_liga",
    103: "soccer_norway_eliteserien",
    113: "soccer_sweden_allsvenskan",
}

# Bookmaker regions — eu covers Pinnacle, Unibet, Betsson etc.
REGIONS = "eu"


class OddsAPIClient:
    def __init__(self, api_key: str = ODDS_KEY):
        self.api_key = api_key
        self.session = httpx.Client(timeout=30.0)
        self._requests_used      = 0
        self._requests_remaining: Optional[int] = None

    def _get(self, path: str, params: dict) -> list:
        if not self.api_key:
            raise ValueError("ODDS_API_KEY not set — add it to .env")
        params["apiKey"] = self.api_key
        resp = self.session.get(f"{API_BASE}{path}", params=params)

        # Track quota from response headers
        used      = resp.headers.get("x-requests-used")
        remaining = resp.headers.get("x-requests-remaining")
        if used:
            self._requests_used = int(used)
        if remaining:
            self._requests_remaining = int(remaining)

        resp.raise_for_status()
        return resp.json()

    def fetch_odds(self, sport_key: str) -> list[dict]:
        """Fetch upcoming h2h odds for a sport."""
        data = self._get(
            f"/sports/{sport_key}/odds",
            {
                "regions":    REGIONS,
                "markets":    "h2h",
                "oddsFormat": "decimal",
            },
        )
        logger.info(
            f"OddsAPI [{sport_key}]: {len(data)} events | "
            f"used={self._requests_used}, remaining={self._requests_remaining}"
        )
        return data

    def close(self):
        self.session.close()


def _last_odds_sync_time(db: Session) -> Optional[datetime]:
    """Return the datetime of the last successful odds sync, or None."""
    log = (
        db.query(SyncLog)
        .filter_by(source="odds_api", status="success")
        .order_by(SyncLog.started_at.desc())
        .first()
    )
    return log.started_at if log else None


def _normalize(name: str) -> str:
    return (
        name.lower().strip()
        .replace("ø", "o").replace("æ", "ae").replace("å", "a")
        .replace("-", " ")          # ham-kam → ham kam
        .replace("/", " ")          # bodo/glimt → bodo glimt
        .replace(" fk", "").replace(" bk", "").replace(" sk", "")
        .replace(" fc", "").replace(" if", "")
        .replace("08 ff", "").replace("08", "")
        .replace("ballklubb", "")
        .strip()
    )


def _team_name_matches(api_name: str, db_name: str) -> bool:
    a = _normalize(api_name)
    b = _normalize(db_name)
    if a == b:
        return True
    if a in b or b in a:
        return True
    # First word match handles "SK Brann" vs "Brann"
    a_words = a.split()
    b_words = b.split()
    if a_words and b_words:
        if a_words[-1] == b_words[-1]:   # last word (main club name)
            return True
        if a_words[0] == b_words[0]:     # first word
            return True
    return False


def sync_odds_for_league(
    db: Session,
    client: OddsAPIClient,
    league_api_id: int,
    sport_key: str,
) -> int:
    """Fetch odds for one league and upsert into Odds table."""
    league = db.query(League).filter_by(api_id=league_api_id).first()
    if not league:
        logger.warning(f"League {league_api_id} not in DB — skipping")
        return 0

    try:
        events = client.fetch_odds(sport_key)
    except httpx.HTTPStatusError as e:
        logger.warning(f"OddsAPI HTTP error for {sport_key}: {e}")
        return 0
    except Exception as e:
        logger.warning(f"OddsAPI error for {sport_key}: {e}")
        return 0
    
    now = datetime.utcnow()  # naive UTC, matches DB storage
    upcoming = (
        db.query(Match)
        .filter(
            Match.league_id == league.id,
            Match.kickoff > now,
            Match.home_goals.is_(None),
        )
        .all()
    )

    count = 0
    for event in events:
        home_api = event.get("home_team", "")
        away_api = event.get("away_team", "")

        # Match to DB by team names
        db_match = None
        for m in upcoming:
            if not m.home_team or not m.away_team:
                continue
            if (
                _team_name_matches(home_api, m.home_team.name)
                and _team_name_matches(away_api, m.away_team.name)
            ):
                db_match = m
                break

        if not db_match:
            logger.debug(f"No DB match for {home_api} vs {away_api}")
            continue

        # Pick best (lowest margin) bookmaker
        best_home = best_draw = best_away = None
        best_margin = float("inf")
        best_bookie = ""

        for bookie in event.get("bookmakers", []):
            for market in bookie.get("markets", []):
                if market["key"] != "h2h":
                    continue
                outcomes = {o["name"]: o["price"] for o in market["outcomes"]}
                home_o = outcomes.get(home_api)
                away_o = outcomes.get(away_api)
                draw_o = outcomes.get("Draw")

                if not all([home_o, draw_o, away_o]):
                    continue
                if any(x <= 1.0 for x in [home_o, draw_o, away_o]):
                    continue

                margin = 1/home_o + 1/draw_o + 1/away_o - 1.0
                if margin < best_margin:
                    best_margin = margin
                    best_home   = home_o
                    best_draw   = draw_o
                    best_away   = away_o
                    best_bookie = bookie.get("title", "unknown")

        if best_home is None:
            continue

        total = 1/best_home + 1/best_draw + 1/best_away
        db.add(Odds(
            match_id  = db_match.id,
            bookmaker = best_bookie,
            market    = "1X2",
            home_odds = best_home,
            draw_odds = best_draw,
            away_odds = best_away,
            home_prob = (1/best_home) / total,
            draw_prob = (1/best_draw) / total,
            away_prob = (1/best_away) / total,
            margin    = best_margin,
        ))
        count += 1

    db.commit()
    logger.info(f"OddsAPI: stored {count} odds rows for league {league_api_id}")
    return count


def run_odds_sync(db: Session, force: bool = False) -> dict:
    """
    Sync odds from The Odds API for all configured leagues.

    Args:
        force: If True, skip the minimum interval check and always sync.
               Used when the user clicks "Sync Odds" manually.
               If False (default, called from run_full_sync), respects
               the MIN_SYNC_INTERVAL_HOURS limit to protect token budget.

    Returns dict with status and rows stored.
    """
    if not ODDS_KEY:
        logger.warning("ODDS_API_KEY not set — skipping odds sync")
        return {"status": "skipped", "reason": "no api key", "rows": 0}

    # Rate-limit automatic syncs — skip if synced recently
    if not force:
        last = _last_odds_sync_time(db)
        if last:
            age_hours = (datetime.utcnow() - last.replace(tzinfo=None)).total_seconds() / 3600
            if age_hours < MIN_SYNC_INTERVAL_HOURS:
                logger.info(
                    f"Odds sync skipped — last sync was {age_hours:.1f}h ago "
                    f"(min interval: {MIN_SYNC_INTERVAL_HOURS}h)"
                )
                return {
                    "status": "skipped",
                    "reason": f"synced {age_hours:.1f}h ago, min interval {MIN_SYNC_INTERVAL_HOURS}h",
                    "rows": 0,
                }

    started = datetime.now(timezone.utc)
    client  = OddsAPIClient()
    total   = 0
    seen: set[str] = set()

    try:
        for league_api_id, sport_key in ODDS_API_LEAGUES.items():
            if sport_key in seen:
                continue
            seen.add(sport_key)
            total += sync_odds_for_league(db, client, league_api_id, sport_key)

        # Log success
        db.add(SyncLog(
            source      = "odds_api",
            status      = "success",
            records     = total,
            started_at  = started,
            finished_at = datetime.now(timezone.utc),
        ))
        db.commit()
        logger.info(
            f"Odds sync complete — {total} rows stored | "
            f"API requests used this month: {client._requests_used}, "
            f"remaining: {client._requests_remaining}"
        )
        return {
            "status":    "success",
            "rows":      total,
            "api_requests_used":      client._requests_used,
            "api_requests_remaining": client._requests_remaining,
        }

    except Exception as exc:
        db.add(SyncLog(
            source      = "odds_api",
            status      = "error",
            error_msg   = str(exc),
            started_at  = started,
            finished_at = datetime.now(timezone.utc),
        ))
        db.commit()
        logger.error(f"Odds sync failed: {exc}")
        raise

    finally:
        client.close()