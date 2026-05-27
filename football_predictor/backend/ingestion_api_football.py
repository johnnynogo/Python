"""
API-Football ingestion client.
Docs: https://www.api-football.com/documentation-v3

Free tier: 100 calls/day.  We budget carefully.
"""
import os
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from models import League, Team, Match, Odds, SyncLog

logger = logging.getLogger(__name__)

API_BASE = "https://v3.football.api-sports.io"
API_KEY  = os.getenv("API_FOOTBALL_KEY", "")

TARGET_LEAGUES = {
    39:  ("Premier League",   "England",     2025),
    78:  ("Bundesliga",       "Germany",     2025),
    135: ("Serie A",          "Italy",       2025),
    61:  ("Ligue 1",          "France",      2025),
    140: ("La Liga",          "Spain",       2025),
    103: ("Eliteserien",      "Norway",      2026),
    104: ("OBOS-ligaen",      "Norway",      2026),
    108: ("Toppserien",       "Norway",      2026),
    113: ("Allsvenskan",      "Sweden",      2026),
    5:   ("UEFA Nations Lg.", "World",       2024),
    1:   ("World Cup",        "World",       2022),
}

HISTORICAL_SEASONS = [
    # Bundesliga
    (78,  "Bundesliga",       "Germany",     2024),
    (78,  "Bundesliga",       "Germany",     2023),
    (78,  "Bundesliga",       "Germany",     2022),
    (78,  "Bundesliga",       "Germany",     2021),
    (78,  "Bundesliga",       "Germany",     2020),
    (78,  "Bundesliga",       "Germany",     2019),
    (78,  "Bundesliga",       "Germany",     2018),
    (78,  "Bundesliga",       "Germany",     2017),
    (78,  "Bundesliga",       "Germany",     2016),
    (78,  "Bundesliga",       "Germany",     2015),
    (78,  "Bundesliga",       "Germany",     2014),
    (78,  "Bundesliga",       "Germany",     2013),
    (78,  "Bundesliga",       "Germany",     2012),
    (78,  "Bundesliga",       "Germany",     2011),
    (78,  "Bundesliga",       "Germany",     2010),
    # Serie A
    (135, "Serie A",          "Italy",       2024),
    (135, "Serie A",          "Italy",       2023),
    (135, "Serie A",          "Italy",       2022),
    (135, "Serie A",          "Italy",       2021),
    (135, "Serie A",          "Italy",       2020),
    (135, "Serie A",          "Italy",       2019),
    (135, "Serie A",          "Italy",       2018),
    (135, "Serie A",          "Italy",       2017),
    (135, "Serie A",          "Italy",       2016),
    (135, "Serie A",          "Italy",       2015),
    (135, "Serie A",          "Italy",       2014),
    (135, "Serie A",          "Italy",       2013),
    (135, "Serie A",          "Italy",       2012),
    (135, "Serie A",          "Italy",       2011),
    (135, "Serie A",          "Italy",       2010),
    # Ligue 1
    (61,  "Ligue 1",          "France",      2024),
    (61,  "Ligue 1",          "France",      2023),
    (61,  "Ligue 1",          "France",      2022),
    (61,  "Ligue 1",          "France",      2021),
    (61,  "Ligue 1",          "France",      2020),
    (61,  "Ligue 1",          "France",      2019),
    (61,  "Ligue 1",          "France",      2018),
    (61,  "Ligue 1",          "France",      2017),
    (61,  "Ligue 1",          "France",      2016),
    (61,  "Ligue 1",          "France",      2015),
    (61,  "Ligue 1",          "France",      2014),
    (61,  "Ligue 1",          "France",      2013),
    (61,  "Ligue 1",          "France",      2012),
    (61,  "Ligue 1",          "France",      2011),
    (61,  "Ligue 1",          "France",      2010),
    # La Liga
    (140, "La Liga",          "Spain",       2024),
    (140, "La Liga",          "Spain",       2023),
    (140, "La Liga",          "Spain",       2022),
    (140, "La Liga",          "Spain",       2021),
    (140, "La Liga",          "Spain",       2020),
    (140, "La Liga",          "Spain",       2019),
    (140, "La Liga",          "Spain",       2018),
    (140, "La Liga",          "Spain",       2017),
    (140, "La Liga",          "Spain",       2016),
    (140, "La Liga",          "Spain",       2015),
    (140, "La Liga",          "Spain",       2014),
    (140, "La Liga",          "Spain",       2013),
    (140, "La Liga",          "Spain",       2012),
    (140, "La Liga",          "Spain",       2011),
    (140, "La Liga",          "Spain",       2010),
    # Eliteserien
    (103, "Eliteserien",      "Norway",      2025),
    (103, "Eliteserien",      "Norway",      2024),
    (103, "Eliteserien",      "Norway",      2023),
    (103, "Eliteserien",      "Norway",      2022),
    (103, "Eliteserien",      "Norway",      2021),
    (103, "Eliteserien",      "Norway",      2020),
    # OBOS
    (104, "OBOS-ligaen",      "Norway",      2025),
    (104, "OBOS-ligaen",      "Norway",      2024),
    (104, "OBOS-ligaen",      "Norway",      2023),
    # Allsvenskan
    (113, "Allsvenskan",      "Sweden",      2025),
    (113, "Allsvenskan",      "Sweden",      2024),
    (113, "Allsvenskan",      "Sweden",      2023),
    (113, "Allsvenskan",      "Sweden",      2022),
    (113, "Allsvenskan",      "Sweden",      2021),
    (113, "Allsvenskan",      "Sweden",      2020),
    # Premier League
    (39,  "Premier League",   "England",     2024),
    (39,  "Premier League",   "England",     2023),
    (39,  "Premier League",   "England",     2022),
    (39,  "Premier League",   "England",     2021),
    (39,  "Premier League",   "England",     2020),
    (39,  "Premier League",   "England",     2019),
    (39,  "Premier League",   "England",     2018),
    (39,  "Premier League",   "England",     2017),
    (39,  "Premier League",   "England",     2016),
    (39,  "Premier League",   "England",     2015),
    (39,  "Premier League",   "England",     2014),
    (39,  "Premier League",   "England",     2013),
    (39,  "Premier League",   "England",     2012),
    (39,  "Premier League",   "England",     2011),
    (39,  "Premier League",   "England",     2010),
    # International
    (1,   "World Cup",        "World",       2018),
    (5,   "UEFA Nations Lg.", "World",       2022),
]


class APIFootballClient:
    def __init__(self, api_key: str = API_KEY):
        self.api_key = api_key
        self.session = httpx.Client(
            base_url=API_BASE,
            headers={"x-apisports-key": api_key},
            timeout=30.0,
        )
        self._calls_this_run = 0

    def _get(self, endpoint: str, params: dict) -> dict:
        """Make a GET request, respect rate limits, log calls."""
        if not self.api_key or self.api_key == "your_api_football_key_here":
            raise ValueError("API_FOOTBALL_KEY not set — add it to .env")
        resp = self.session.get(endpoint, params=params)
        resp.raise_for_status()
        self._calls_this_run += 1
        time.sleep(0.5)   # Stay well within free-tier limits
        data = resp.json()
        if data.get("errors"):
            raise RuntimeError(f"API error: {data['errors']}")
        return data

    # ---------------------------------------------------------------
    # Leagues
    # ---------------------------------------------------------------
    def sync_leagues(self, db: Session) -> int:
        """Upsert our target leagues into the DB."""
        count = 0
        for api_id, (name, country, season) in TARGET_LEAGUES.items():
            league = db.query(League).filter_by(api_id=api_id).first()
            if not league:
                league = League(api_id=api_id, name=name, country=country, season=season)
                db.add(league)
            else:
                league.season = season
            db.commit()
            count += 1
        logger.info(f"sync_leagues: upserted {count} leagues")
        return count

    # ---------------------------------------------------------------
    # Teams
    # ---------------------------------------------------------------
    def sync_teams(self, db: Session, league_api_id: int, season: int) -> int:
        """Fetch all teams for a league+season and upsert into DB."""
        league = db.query(League).filter_by(api_id=league_api_id).first()
        if not league:
            raise ValueError(f"League {league_api_id} not in DB — run sync_leagues first")

        data = self._get("/teams", {"league": league_api_id, "season": season})
        teams_raw = data.get("response", [])
        count = 0

        for entry in teams_raw:
            t = entry["team"]
            v = entry.get("venue", {})
            team = db.query(Team).filter_by(api_id=t["id"]).first()
            if not team:
                team = Team(api_id=t["id"])
                db.add(team)
            team.name      = t["name"]
            team.country   = t.get("country", league.country)
            team.league_id = league.id
            team.logo_url  = t.get("logo")
            team.founded   = t.get("founded")
            team.venue     = v.get("name") if v else None
            count += 1

        db.commit()
        logger.info(f"sync_teams(league={league_api_id}): upserted {count} teams")
        return count

    # ---------------------------------------------------------------
    # Fixtures / Matches
    # ---------------------------------------------------------------
    def sync_fixtures(self, db: Session, league_api_id: int, season: int) -> int:
        """Fetch all fixtures for a league+season and upsert into DB."""
        league = db.query(League).filter_by(api_id=league_api_id).first()
        if not league:
            raise ValueError(f"League {league_api_id} not in DB")

        data = self._get("/fixtures", {"league": league_api_id, "season": season})
        fixtures = data.get("response", [])
        count = 0

        for f in fixtures:
            fix   = f["fixture"]
            score = f["score"]
            goals = f["goals"]
            teams = f["teams"]

            home_team = db.query(Team).filter_by(api_id=teams["home"]["id"]).first()
            away_team = db.query(Team).filter_by(api_id=teams["away"]["id"]).first()
            if not home_team or not away_team:
                continue   # Team not synced yet

            match = db.query(Match).filter_by(api_id=fix["id"]).first()
            if not match:
                match = Match(api_id=fix["id"])
                db.add(match)

            kickoff_str = fix.get("date")
            match.league_id    = league.id
            match.home_team_id = home_team.id
            match.away_team_id = away_team.id
            match.kickoff      = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00")) if kickoff_str else None
            match.status       = fix["status"]["short"]
            match.home_goals   = goals.get("home")
            match.away_goals   = goals.get("away")
            match.home_goals_ht = score.get("halftime", {}).get("home")
            match.away_goals_ht = score.get("halftime", {}).get("away")
            match.updated_at   = datetime.now(timezone.utc)
            count += 1

        db.commit()
        logger.info(f"sync_fixtures(league={league_api_id}): upserted {count} fixtures")
        return count

    # ---------------------------------------------------------------
    # Match statistics (xG, shots, possession, etc.)
    # ---------------------------------------------------------------
    def sync_match_stats(self, db: Session, match_api_id: int) -> bool:
        """Fetch and store stats for a single completed match."""
        data = self._get("/fixtures/statistics", {"fixture": match_api_id})
        stats_raw = data.get("response", [])
        if not stats_raw:
            return False

        match = db.query(Match).filter_by(api_id=match_api_id).first()
        if not match:
            return False

        stats_dict = {}
        for team_stats in stats_raw:
            team_id  = team_stats["team"]["id"]
            side     = "home" if team_id == match.home_team.api_id else "away"
            stats_dict[side] = {s["type"]: s["value"] for s in team_stats["statistics"]}

        match.stats = stats_dict

        # Parse xG from stats if available
        home_xg = stats_dict.get("home", {}).get("expected_goals")
        away_xg = stats_dict.get("away", {}).get("expected_goals")
        if home_xg is not None:
            try:
                match.home_xg = float(home_xg)
                match.away_xg = float(away_xg)
            except (ValueError, TypeError):
                pass

        db.commit()
        return True

    # ---------------------------------------------------------------
    # Odds
    # ---------------------------------------------------------------
    def sync_odds(self, db: Session, league_api_id: int, season: int) -> int:
        """Fetch 1X2 pre-match odds for upcoming fixtures."""
        data = self._get("/odds", {
            "league": league_api_id,
            "season": season,
            "bet":    1,   # bet ID 1 = Match Winner (1X2)
        })
        entries = data.get("response", [])
        count = 0

        for entry in entries:
            fix_id = entry["fixture"]["id"]
            match  = db.query(Match).filter_by(api_id=fix_id).first()
            if not match:
                continue

            for bookie in entry.get("bookmakers", [])[:3]:   # top 3 bookmakers
                for bet in bookie.get("bets", []):
                    if bet["name"] != "Match Winner":
                        continue
                    values = {v["value"]: float(v["odd"]) for v in bet["values"]}
                    home_o = values.get("Home", 0)
                    draw_o = values.get("Draw", 0)
                    away_o = values.get("Away", 0)
                    if not all([home_o, draw_o, away_o]):
                        continue

                    # Remove bookmaker margin to get fair probabilities
                    total = 1/home_o + 1/draw_o + 1/away_o
                    margin = total - 1.0

                    odds_row = Odds(
                        match_id  = match.id,
                        bookmaker = bookie["name"],
                        market    = "1X2",
                        home_odds = home_o,
                        draw_odds = draw_o,
                        away_odds = away_o,
                        home_prob = (1/home_o) / total,
                        draw_prob = (1/draw_o) / total,
                        away_prob = (1/away_o) / total,
                        margin    = margin,
                    )
                    db.add(odds_row)
                    count += 1

        db.commit()
        logger.info(f"sync_odds(league={league_api_id}): stored {count} odds rows")
        return count

    def close(self):
        self.session.close()


# ---------------------------------------------------------------
# High-level sync runner (called by scheduler or CLI)
# ---------------------------------------------------------------
def run_full_sync(db: Session, dry_run: bool = False):
    """Run a complete data sync across all target leagues."""
    client = APIFootballClient()
    started = datetime.now(timezone.utc)

    try:
        # 1. Leagues
        client.sync_leagues(db)

        # 2. Teams + Fixtures + Odds per league
        for api_id, (name, _, season) in TARGET_LEAGUES.items():
            logger.info(f"--- Syncing {name} (id={api_id}, season={season}) ---")
            if not dry_run:
                client.sync_teams(db, api_id, season)
                client.sync_fixtures(db, api_id, season)
                client.sync_odds(db, api_id, season)
        
        # 3. Historical seasons for richer training data
        logger.info("--- Syncing historical seasons ---")
        for api_id, name, country, season in HISTORICAL_SEASONS:
            logger.info(f"--- Historical: {name} {season} ---")
            if not dry_run:
                try:
                    client.sync_teams(db, api_id, season)
                    client.sync_fixtures(db, api_id, season)
                except Exception as e:
                    logger.warning(f"Historical sync failed {name} {season}: {e}")

        # 4. Odds from The Odds API (covers Eliteserien, Allsvenskan, EPL)
        if not dry_run:
            logger.info("--- Syncing odds from The Odds API ---")
            try:
                from ingestion_odds_api import run_odds_sync
                run_odds_sync(db)
            except Exception as e:
                logger.warning(f"Odds API sync failed: {e}")

        # Log success
        log = SyncLog(
            source     = "api_football",
            status     = "success",
            records    = client._calls_this_run,
            started_at = started,
            finished_at = datetime.now(timezone.utc),
        )
        db.add(log)
        db.commit()
        logger.info(f"Full sync complete — {client._calls_this_run} API calls used.")

    except Exception as exc:
        log = SyncLog(
            source      = "api_football",
            status      = "error",
            error_msg   = str(exc),
            started_at  = started,
            finished_at = datetime.now(timezone.utc),
        )
        db.add(log)
        db.commit()
        logger.error(f"Sync failed: {exc}")
        raise
    finally:
        client.close()