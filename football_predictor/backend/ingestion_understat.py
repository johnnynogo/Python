"""
Understat xG scraper.
Understat has no public API — we parse the JSON embedded in each page.
Covers top European leagues. For Eliteserien we fall back to api-football stats.
"""
import re
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from models import Match, Team, SyncLog

logger = logging.getLogger(__name__)

BASE_URL = "https://understat.com"

# Understat league slugs
LEAGUE_SLUGS = {
    "EPL":        "EPL",
    "La Liga":    "La_liga",
    "Bundesliga": "Bundesliga",
    "Serie A":    "Serie_A",
    "Ligue 1":    "Ligue_1",
}


def _extract_json_var(html: str, var_name: str) -> list:
    """Pull a JavaScript variable assignment from the page HTML."""
    pattern = rf"var {re.escape(var_name)}\s*=\s*JSON\.parse\('(.+?)'\)"
    match   = re.search(pattern, html)
    if not match:
        return []
    raw = match.group(1).encode("utf-8").decode("unicode_escape")
    return json.loads(raw)


class UnderstatScraper:
    def __init__(self):
        self.client = httpx.Client(
            headers={"User-Agent": "Mozilla/5.0 (compatible; SoccerPredictor/1.0)"},
            timeout=30.0,
            follow_redirects=True,
        )

    def fetch_league_xg(self, league_slug: str, season: int) -> list[dict]:
        """
        Fetch all match xG for a league-season.
        Returns list of dicts with keys: home_team, away_team, home_xg, away_xg, date
        """
        url  = f"{BASE_URL}/league/{league_slug}/{season}"
        resp = self.client.get(url)
        resp.raise_for_status()
        matches = _extract_json_var(resp.text, "datesData")

        results = []
        for m in matches:
            try:
                results.append({
                    "understat_id": m["id"],
                    "home_team":    m["h"]["title"],
                    "away_team":    m["a"]["title"],
                    "home_xg":      float(m["xG"]["h"]) if m["xG"]["h"] else None,
                    "away_xg":      float(m["xG"]["a"]) if m["xG"]["a"] else None,
                    "home_goals":   int(m["goals"]["h"]) if m["goals"]["h"] else None,
                    "away_goals":   int(m["goals"]["a"]) if m["goals"]["a"] else None,
                    "date":         m["datetime"],
                    "result":       m.get("result"),   # "w" | "d" | "l" (home perspective)
                })
            except (KeyError, ValueError, TypeError):
                continue

        logger.info(f"understat {league_slug}/{season}: fetched {len(results)} matches")
        return results

    def sync_xg_to_db(self, db: Session, league_slug: str, season: int) -> int:
        """
        Match understat records to DB matches by team names + date proximity.
        Updates home_xg / away_xg where found.
        """
        started = datetime.now(timezone.utc)
        rows = self.fetch_league_xg(league_slug, season)
        updated = 0

        for row in rows:
            if row["home_xg"] is None:
                continue

            # Find the team by a loose name match
            home_team = (
                db.query(Team)
                .filter(Team.name.ilike(f"%{row['home_team']}%"))
                .first()
            )
            away_team = (
                db.query(Team)
                .filter(Team.name.ilike(f"%{row['away_team']}%"))
                .first()
            )
            if not home_team or not away_team:
                continue

            # Find the match (±1 day to handle timezone offsets)
            try:
                match_date = datetime.fromisoformat(row["date"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                continue

            match = (
                db.query(Match)
                .filter(
                    Match.home_team_id == home_team.id,
                    Match.away_team_id == away_team.id,
                    Match.kickoff.between(
                        match_date.replace(hour=0, minute=0, second=0),
                        match_date.replace(hour=23, minute=59, second=59),
                    ),
                )
                .first()
            )
            if not match:
                continue

            match.home_xg = row["home_xg"]
            match.away_xg = row["away_xg"]
            match.updated_at = datetime.now(timezone.utc)
            updated += 1

        db.commit()

        log = SyncLog(
            source      = "understat",
            status      = "success",
            records     = updated,
            started_at  = started,
            finished_at = datetime.now(timezone.utc),
        )
        db.add(log)
        db.commit()

        logger.info(f"understat sync: updated xG for {updated} matches")
        return updated

    def close(self):
        self.client.close()


def run_xg_sync(db: Session, leagues: list[str] = None, season: int = 2024):
    """Sync xG for all (or specified) Understat leagues."""
    scraper = UnderstatScraper()
    slugs   = leagues or list(LEAGUE_SLUGS.values())
    try:
        for slug in slugs:
            try:
                scraper.sync_xg_to_db(db, slug, season)
            except httpx.HTTPError as e:
                logger.warning(f"understat fetch failed for {slug}: {e}")
    finally:
        scraper.close()
