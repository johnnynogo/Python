"""
football-data.co.uk historical odds importer.

Downloads free CSV files with historical match results + bookmaker odds
(Pinnacle, Bet365, market average) going back to 2000 for most leagues.

URL format:
  Premier League:  https://www.football-data.co.uk/mmz4281/{season}/E0.csv
  Eliteserien:     https://www.football-data.co.uk/new/NOR.csv  (all seasons in one file)
  Allsvenskan:     https://www.football-data.co.uk/new/SWE.csv  (all seasons in one file)

Run once to backfill historical odds, then no need to re-run unless
you want to refresh the current season's data.

Usage:
  python ingestion_footballdata.py          # imports all configured leagues
  python ingestion_footballdata.py --dry-run # shows what would be imported
"""
import csv
import io
import logging
import sys
from datetime import datetime
from typing import Optional

import httpx
from dotenv import load_dotenv
load_dotenv()
from sqlalchemy.orm import Session

from database import SessionLocal
from models import League, Match, Odds

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

BASE = "https://www.football-data.co.uk"

# Each entry: (our league api_id, url, season_label)
SOURCES = [
    # Premier League
    (39,  f"{BASE}/mmz4281/2324/E0.csv", "2024/25"),
    (39,  f"{BASE}/mmz4281/2324/E0.csv", "2023/24"),
    (39,  f"{BASE}/mmz4281/2223/E0.csv", "2022/23"),
    (39,  f"{BASE}/mmz4281/2122/E0.csv", "2021/22"),
    (39,  f"{BASE}/mmz4281/2021/E0.csv", "2020/21"),
    (39,  f"{BASE}/mmz4281/1920/E0.csv", "2019/20"),
    (39,  f"{BASE}/mmz4281/1819/E0.csv", "2018/19"),
    (39,  f"{BASE}/mmz4281/1718/E0.csv", "2017/18"),
    (39,  f"{BASE}/mmz4281/1617/E0.csv", "2016/17"),
    (39,  f"{BASE}/mmz4281/1516/E0.csv", "2015/16"),
    (39,  f"{BASE}/mmz4281/1415/E0.csv", "2014/15"),
    (39,  f"{BASE}/mmz4281/1314/E0.csv", "2013/14"),
    (39,  f"{BASE}/mmz4281/1213/E0.csv", "2012/13"),
    (39,  f"{BASE}/mmz4281/1112/E0.csv", "2011/12"),
    (39,  f"{BASE}/mmz4281/1011/E0.csv", "2010/11"),
    (39,  f"{BASE}/mmz4281/0910/E0.csv", "2009/10"),
    # Bundesliga
    (78,  f"{BASE}/mmz4281/2324/D1.csv", "2024/25"),
    (78,  f"{BASE}/mmz4281/2324/D1.csv", "2023/24"),
    (78,  f"{BASE}/mmz4281/2223/D1.csv", "2022/23"),
    (78,  f"{BASE}/mmz4281/2122/D1.csv", "2021/22"),
    (78,  f"{BASE}/mmz4281/2021/D1.csv", "2020/21"),
    (78,  f"{BASE}/mmz4281/1920/D1.csv", "2019/20"),
    (78,  f"{BASE}/mmz4281/1819/D1.csv", "2018/19"),
    (78,  f"{BASE}/mmz4281/1718/D1.csv", "2017/18"),
    (78,  f"{BASE}/mmz4281/1617/D1.csv", "2016/17"),
    (78,  f"{BASE}/mmz4281/1516/D1.csv", "2015/16"),
    (78,  f"{BASE}/mmz4281/1415/D1.csv", "2014/15"),
    (78,  f"{BASE}/mmz4281/1314/D1.csv", "2013/14"),
    (78,  f"{BASE}/mmz4281/1213/D1.csv", "2012/13"),
    (78,  f"{BASE}/mmz4281/1112/D1.csv", "2011/12"),
    (78,  f"{BASE}/mmz4281/1011/D1.csv", "2010/11"),
    # Serie A
    (135, f"{BASE}/mmz4281/2324/I1.csv", "2024/25"),
    (135, f"{BASE}/mmz4281/2324/I1.csv", "2023/24"),
    (135, f"{BASE}/mmz4281/2223/I1.csv", "2022/23"),
    (135, f"{BASE}/mmz4281/2122/I1.csv", "2021/22"),
    (135, f"{BASE}/mmz4281/2021/I1.csv", "2020/21"),
    (135, f"{BASE}/mmz4281/1920/I1.csv", "2019/20"),
    (135, f"{BASE}/mmz4281/1819/I1.csv", "2018/19"),
    (135, f"{BASE}/mmz4281/1718/I1.csv", "2017/18"),
    (135, f"{BASE}/mmz4281/1617/I1.csv", "2016/17"),
    (135, f"{BASE}/mmz4281/1516/I1.csv", "2015/16"),
    (135, f"{BASE}/mmz4281/1415/I1.csv", "2014/15"),
    (135, f"{BASE}/mmz4281/1314/I1.csv", "2013/14"),
    (135, f"{BASE}/mmz4281/1213/I1.csv", "2012/13"),
    (135, f"{BASE}/mmz4281/1112/I1.csv", "2011/12"),
    (135, f"{BASE}/mmz4281/1011/I1.csv", "2010/11"),
    # Ligue 1
    (61,  f"{BASE}/mmz4281/2324/F1.csv", "2024/25"),
    (61,  f"{BASE}/mmz4281/2324/F1.csv", "2023/24"),
    (61,  f"{BASE}/mmz4281/2223/F1.csv", "2022/23"),
    (61,  f"{BASE}/mmz4281/2122/F1.csv", "2021/22"),
    (61,  f"{BASE}/mmz4281/2021/F1.csv", "2020/21"),
    (61,  f"{BASE}/mmz4281/1920/F1.csv", "2019/20"),
    (61,  f"{BASE}/mmz4281/1819/F1.csv", "2018/19"),
    (61,  f"{BASE}/mmz4281/1718/F1.csv", "2017/18"),
    (61,  f"{BASE}/mmz4281/1617/F1.csv", "2016/17"),
    (61,  f"{BASE}/mmz4281/1516/F1.csv", "2015/16"),
    (61,  f"{BASE}/mmz4281/1415/F1.csv", "2014/15"),
    (61,  f"{BASE}/mmz4281/1314/F1.csv", "2013/14"),
    (61,  f"{BASE}/mmz4281/1213/F1.csv", "2012/13"),
    (61,  f"{BASE}/mmz4281/1112/F1.csv", "2011/12"),
    (61,  f"{BASE}/mmz4281/1011/F1.csv", "2010/11"),
    # La Liga
    (140, f"{BASE}/mmz4281/2324/SP1.csv", "2024/25"),
    (140, f"{BASE}/mmz4281/2324/SP1.csv", "2023/24"),
    (140, f"{BASE}/mmz4281/2223/SP1.csv", "2022/23"),
    (140, f"{BASE}/mmz4281/2122/SP1.csv", "2021/22"),
    (140, f"{BASE}/mmz4281/2021/SP1.csv", "2020/21"),
    (140, f"{BASE}/mmz4281/1920/SP1.csv", "2019/20"),
    (140, f"{BASE}/mmz4281/1819/SP1.csv", "2018/19"),
    (140, f"{BASE}/mmz4281/1718/SP1.csv", "2017/18"),
    (140, f"{BASE}/mmz4281/1617/SP1.csv", "2016/17"),
    (140, f"{BASE}/mmz4281/1516/SP1.csv", "2015/16"),
    (140, f"{BASE}/mmz4281/1415/SP1.csv", "2014/15"),
    (140, f"{BASE}/mmz4281/1314/SP1.csv", "2013/14"),
    (140, f"{BASE}/mmz4281/1213/SP1.csv", "2012/13"),
    (140, f"{BASE}/mmz4281/1112/SP1.csv", "2011/12"),
    (140, f"{BASE}/mmz4281/1011/SP1.csv", "2010/11"),
    # Eliteserien + Allsvenskan
    (103, f"{BASE}/new/NOR.csv", None),
    (113, f"{BASE}/new/SWE.csv", None),
]

# Standard format (Premier League season files)
ODDS_COLS = [
    ("PSH",  "PSD",  "PSA",  "Pinnacle"),
    ("MaxH", "MaxD", "MaxA", "Market Max"),
    ("AvgH", "AvgD", "AvgA", "Market Avg"),
    ("B365H","B365D","B365A","Bet365"),
]

# "New" format (NOR.csv, SWE.csv) — closing odds, different column names
ODDS_COLS_NEW = [
    ("PSCH",  "PSCD",  "PSCA",  "Pinnacle"),
    ("MaxCH", "MaxCD", "MaxCA", "Market Max"),
    ("AvgCH", "AvgCD", "AvgCA", "Market Avg"),
    ("B365CH","B365CD","B365CA","Bet365"),
]

ALL_BOOKMAKERS = list({b for _, _, _, b in ODDS_COLS + ODDS_COLS_NEW})


def _parse_date(date_str: str) -> Optional[datetime]:
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


def _normalize(name: str) -> str:
    return (
        name.lower().strip()
        .replace("ø", "o").replace("æ", "ae").replace("å", "a")
        .replace("-", " ").replace("/", " ")
        .replace(" fk", "").replace(" bk", "").replace(" sk", "")
        .replace(" fc", "").replace(" if", "")
        .replace("08 ff", "").replace("08", "")
        .replace("ballklubb", "")
        .strip()
    )


def _team_matches(csv_name: str, db_name: str) -> bool:
    a = _normalize(csv_name)
    b = _normalize(db_name)
    if a == b: return True
    if a in b or b in a: return True
    aw, bw = a.split(), b.split()
    if aw and bw:
        if aw[-1] == bw[-1]: return True
        if aw[0] == bw[0]: return True
    return False


def _find_match(db: Session, league: League, home_csv: str, away_csv: str, date: datetime) -> Optional[Match]:
    from datetime import timedelta
    window_start = date.replace(hour=0, minute=0, second=0) - timedelta(days=1)
    window_end   = date.replace(hour=23, minute=59, second=59) + timedelta(days=2)

    candidates = (
        db.query(Match)
        .filter(
            Match.league_id == league.id,
            Match.kickoff >= window_start,
            Match.kickoff <= window_end,
        )
        .all()
    )

    for m in candidates:
        if not m.home_team or not m.away_team:
            continue
        if (
            _team_matches(home_csv, m.home_team.name)
            and _team_matches(away_csv, m.away_team.name)
        ):
            return m
    return None


def _get_odds_from_row(row: dict, cols: list) -> Optional[tuple]:
    for h_col, d_col, a_col, bookie in cols:
        try:
            h = float(row.get(h_col, "") or 0)
            d = float(row.get(d_col, "") or 0)
            a = float(row.get(a_col, "") or 0)
            if h > 1.0 and d > 1.0 and a > 1.0:
                return h, d, a, bookie
        except (ValueError, TypeError):
            continue
    return None


def import_csv(db: Session, league_api_id: int, url: str, dry_run: bool = False) -> int:
    league = db.query(League).filter_by(api_id=league_api_id).first()
    if not league:
        logger.warning(f"League {league_api_id} not in DB — run a full sync first")
        return 0

    logger.info(f"Fetching {url}")
    try:
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return 0

    try:
        text = resp.content.decode("utf-8")
    except UnicodeDecodeError:
        text = resp.content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    count = matched = skipped_no_match = skipped_no_odds = skipped_exists = 0

    for row in reader:
        # Skip empty rows — handle both column name formats
        home_raw = row.get("HomeTeam") or row.get("Home", "")
        away_raw = row.get("AwayTeam") or row.get("Away", "")
        if not home_raw or not away_raw:
            continue

        date = _parse_date(row.get("Date", ""))
        if not date:
            continue

        home_csv = home_raw.strip()
        away_csv = away_raw.strip()

        match = _find_match(db, league, home_csv, away_csv, date)
        if not match:
            skipped_no_match += 1
            logger.debug(f"  No DB match: {home_csv} vs {away_csv} on {date.date()}")
            continue
        matched += 1

        # Skip if we already have odds from football-data for this match
        existing = (
            db.query(Odds)
            .filter(
                Odds.match_id == match.id,
                Odds.bookmaker.in_(ALL_BOOKMAKERS),
            )
            .first()
        )
        if existing:
            skipped_exists += 1
            continue

        # Detect format and get best odds
        is_new_fmt = "Home" in row and "HomeTeam" not in row
        cols = ODDS_COLS_NEW if is_new_fmt else ODDS_COLS
        odds_data = _get_odds_from_row(row, cols)
        if not odds_data:
            skipped_no_odds += 1
            continue

        home_o, draw_o, away_o, bookie = odds_data
        total  = 1/home_o + 1/draw_o + 1/away_o
        margin = total - 1.0

        if not dry_run:
            db.add(Odds(
                match_id  = match.id,
                bookmaker = bookie,
                market    = "1X2",
                home_odds = home_o,
                draw_odds = draw_o,
                away_odds = away_o,
                home_prob = (1/home_o) / total,
                draw_prob = (1/draw_o) / total,
                away_prob = (1/away_o) / total,
                margin    = margin,
            ))
        count += 1

    if not dry_run:
        db.commit()

    logger.info(
        f"  → {count} odds stored | "
        f"{matched} matches found | "
        f"{skipped_no_match} unmatched | "
        f"{skipped_no_odds} no odds | "
        f"{skipped_exists} already existed"
    )
    return count


def run_footballdata_import(db: Session, dry_run: bool = False) -> int:
    total = 0
    for league_api_id, url, season_label in SOURCES:
        label = season_label or "all seasons"
        logger.info(f"--- League {league_api_id} | {label} ---")
        total += import_csv(db, league_api_id, url, dry_run=dry_run)
    logger.info(f"football-data.co.uk import complete — {total} odds rows stored total")
    return total


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        logger.info("DRY RUN — no data will be written")
    db = SessionLocal()
    try:
        run_footballdata_import(db, dry_run=dry_run)
    finally:
        db.close()