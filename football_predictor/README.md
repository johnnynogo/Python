# ⚽ MatchMind — Football Prediction Engine

> Dixon-Coles Poisson + Elo ratings + XGBoost ensemble  
> Built for Eliteserien, tuned for the World Cup.

---

## Architecture

```
soccer-predictor/
├── backend/
│   ├── main.py                   # FastAPI REST API
│   ├── models.py                 # SQLAlchemy ORM (League, Team, Match, Prediction…)
│   ├── database.py               # DB connection + session factory
│   ├── ingestion_api_football.py # Pulls fixtures, teams, odds from API-Football
│   ├── ingestion_understat.py    # Scrapes xG data from Understat
│   ├── elo.py                    # Elo rating engine (with goal-diff multiplier)
│   ├── dixon_coles.py            # Dixon-Coles Poisson model (time-weighted MLE)
│   ├── features.py               # Feature engineering (rolling xG, form, H2H)
│   ├── predictor.py              # Ensemble orchestrator + prediction writer
│   ├── kelly.py                  # Kelly criterion bet-sizing utilities
│   └── requirements.txt
└── frontend/
    └── src/
        ├── pages/
        │   ├── Dashboard.jsx     # Hero + stats + upcoming matches
        │   ├── Predictions.jsx   # All predictions with filters
        │   ├── Matches.jsx       # Match list
        │   ├── MatchDetail.jsx   # Full analysis for one match
        │   ├── Teams.jsx         # Elo leaderboard + DC ratings chart
        │   └── Admin.jsx         # Data sync, model management, logs
        ├── components/
        │   ├── Nav.jsx           # Sticky navigation
        │   └── MatchCard.jsx     # Reusable match card with prediction bar
        └── lib/api.js            # Typed API client
```

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 20+
- PostgreSQL 14+

### 1. One-command setup
```bash
chmod +x setup.sh && ./setup.sh
```

### 2. Add API keys
Edit `backend/.env`:
```
API_FOOTBALL_KEY=your_key_here   # https://www.api-football.com/ (free)
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/soccer_predictor
```

### 3. Start PostgreSQL
```bash
# Docker (easiest):
docker run --name soccer-db \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=soccer_predictor \
  -p 5432:5432 -d postgres

# Or macOS:
brew services start postgresql
createdb soccer_predictor
```

### 4. Start backend
```bash
cd backend
source venv/bin/activate
uvicorn main:app --reload --port 8000
```

### 5. Start frontend
```bash
cd frontend
npm run dev
# → http://localhost:5173
```

### 6. First sync
Open http://localhost:5173/admin → **Run Full Sync**

This will:
1. Fetch Eliteserien + OBOS-ligaen teams and fixtures
2. Rebuild Elo ratings from historical results
3. Fit the Dixon-Coles model
4. Generate predictions for all upcoming matches

---

## API Reference

All endpoints are available at `http://localhost:8000` with interactive docs at `/docs`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | DB health check |
| GET | `/leagues` | List all leagues |
| GET | `/teams?league_id=N` | Teams with Elo ratings |
| GET | `/matches?upcoming=true` | Fixture list |
| GET | `/matches/{id}` | Match detail + prediction |
| GET | `/predictions?best_only=true` | Value bets |
| GET | `/stats/summary` | Dashboard numbers |
| GET | `/stats/team_ratings` | Dixon-Coles attack/defence |
| POST | `/admin/sync` | Trigger full data sync |
| POST | `/admin/predict` | Re-run predictions |
| POST | `/admin/rebuild_elo` | Rebuild Elo from scratch |

---

## Model Stack (Week 1 baseline)

### Elo Rating Engine (`elo.py`)
- Standard 400-point Elo with football tweaks
- Home advantage = +100 Elo equivalent
- Goal-difference multiplier (a 4-0 counts more than a 1-0)
- K = 20 for league, 40 for international, 60 for World Cup

### Dixon-Coles Poisson (`dixon_coles.py`)
- Estimates attack/defence parameter per team via MLE
- Time-weighted: recent matches count more (90-day half-life)
- Low-score correction (tau) for 0-0, 1-0, 0-1, 1-1
- Outputs full score probability matrix → win/draw/loss probs

### Ensemble (`predictor.py`)
- Dixon-Coles: 70%, Elo: 30%
- Weights tuned on back-test in Week 2

### Kelly Criterion (`kelly.py`)
- Removes bookmaker margin from odds → fair probabilities
- Computes expected value per outcome
- Recommends bet only if EV > 3%
- Uses 25% fractional Kelly, capped at 10% of bankroll

---

## 3-Week Roadmap

| Week | Focus | What to do |
|------|-------|-----------|
| **1** ✓ | Data + baseline | This code. Sync Eliteserien. Baseline Poisson + Elo. |
| **2** | Feature engineering + back-test | Add xG features, form windows. Walk-forward back-test on 2023. Tune ensemble weights. Add XGBoost layer. |
| **3** | Nations League → World Cup | Test on Nations League. Retrain for international football. Deploy. |

---

## Data Sources

| Source | What | How |
|--------|------|-----|
| [API-Football](https://www.api-football.com/) | Fixtures, teams, odds | REST API (100 free calls/day) |
| [Understat](https://understat.com/) | xG data | HTML scraping |
| [ClubElo](http://clubelo.com/) | Historical Elo | Manual seed (optional) |

---

## Notes

- **Free tier**: API-Football gives 100 calls/day. A full Eliteserien sync uses ~20 calls.
- **xG for Norwegian leagues**: Understat covers top 6 European leagues only. For Eliteserien, xG comes from API-Football match statistics where available.
- **Odds**: The free API-Football tier includes odds. For better coverage add [The Odds API](https://the-odds-api.com/) key.
