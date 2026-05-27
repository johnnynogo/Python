#!/usr/bin/env bash
# setup.sh — bootstrap the entire soccer predictor stack
set -e

BLUE='\033[0;34m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'

header() { echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; echo -e "${BLUE}  $1${NC}"; echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }
ok()     { echo -e "${GREEN}  ✓ $1${NC}"; }
warn()   { echo -e "${YELLOW}  ⚠ $1${NC}"; }
info()   { echo -e "  → $1"; }

header "⚽  MatchMind — Soccer Predictor Setup"

# ── Backend ───────────────────────────────────────────────────────
header "1/4  Python backend"

cd backend

if [ ! -f ".env" ]; then
  cp .env.example .env
  warn ".env created from template. Edit it to add your API keys!"
fi

if [ ! -d "venv" ]; then
  info "Creating Python virtual environment…"
  python3 -m venv venv
fi

info "Installing Python dependencies…"
source venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
ok "Backend dependencies installed"

# ── Frontend ──────────────────────────────────────────────────────
header "2/4  Node / React frontend"
cd ../frontend

if ! command -v node &>/dev/null; then
  echo -e "${RED}  ✗ Node.js not found. Install from https://nodejs.org${NC}"
  exit 1
fi

info "Installing Node dependencies…"
npm install --silent
ok "Frontend dependencies installed"

# ── Summary ───────────────────────────────────────────────────────
header "3/4  Setup complete!"

echo ""
echo "  Next steps:"
echo ""
echo -e "  ${YELLOW}1. Add your API key to backend/.env${NC}"
echo "     → https://www.api-football.com/ (free, 100 calls/day)"
echo ""
echo -e "  ${YELLOW}2. Start PostgreSQL${NC}"
echo "     → macOS:  brew services start postgresql"
echo "     → Linux:  sudo service postgresql start"
echo "     → Docker: docker run -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d postgres"
echo ""
echo -e "  ${YELLOW}3. Start the backend${NC}"
echo "     cd backend && source venv/bin/activate && uvicorn main:app --reload --port 8000"
echo ""
echo -e "  ${YELLOW}4. Start the frontend (new terminal)${NC}"
echo "     cd frontend && npm run dev"
echo ""
echo -e "  ${YELLOW}5. Open the app${NC}"
echo "     → http://localhost:5173"
echo ""
echo -e "  ${YELLOW}6. First-time sync${NC}"
echo "     → Go to Admin page → click 'Run Full Sync'"
echo ""
echo "  API docs: http://localhost:8000/docs"
echo ""
