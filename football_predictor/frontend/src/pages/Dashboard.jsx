import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useFetch } from '../hooks/useFetch'
import MatchCard from '../components/MatchCard'
import './Dashboard.css'

function StatCard({ value, label, accent }) {
  return (
    <div className="stat-card">
      <div className="stat-value" style={accent ? { color: accent } : {}}>{value ?? '–'}</div>
      <div className="stat-label">{label}</div>
    </div>
  )
}

export default function Dashboard() {
  const navigate = useNavigate()
  const { data: summary } = useFetch(() => api.summary())
  const { data: upcoming, loading } = useFetch(() =>
    api.matches({ upcoming: true, limit: 6 })
  )
  const { data: bestBets } = useFetch(() =>
    api.predictions({ best_only: true, limit: 3 })
  )
  const { data: preds } = useFetch(() =>
    api.predictions({ limit: 20 })
  )

  // Build prediction map
  const predMap = {}
  if (preds) preds.forEach(p => { predMap[p.match_id] = p })

  return (
    <div className="dashboard">
      {/* Hero */}
      <section className="hero container">
        <div className="hero-tag badge badge-acid">⚽ AI Prediction Engine</div>
        <h1 className="hero-title">
          Predict the<br />
          <span className="hero-accent">Beautiful Game</span>
        </h1>
        <p className="hero-sub">
          Dixon-Coles Poisson modelling + Elo ratings + XGBoost ensemble.
          Built for Eliteserien, tuned for the World Cup.
        </p>
        <div className="hero-actions">
          <button className="btn btn-primary" onClick={() => navigate('/predictions')}>
            View Predictions →
          </button>
          <button className="btn btn-ghost" onClick={() => navigate('/matches')}>
            All Matches
          </button>
        </div>
      </section>

      {/* Stats bar */}
      {summary && (
        <section className="container" style={{ marginBottom: 48 }}>
          <div className="stat-grid">
            <StatCard value={summary.total_matches?.toLocaleString()} label="Matches" />
            <StatCard value={summary.with_prediction?.toLocaleString()} label="Predictions" accent="var(--acid)" />
            <StatCard value={summary.upcoming?.toLocaleString()} label="Upcoming" accent="var(--teal)" />
            <StatCard value={summary.with_xg?.toLocaleString()} label="With xG" />
            <StatCard value={summary.teams?.toLocaleString()} label="Teams" />
            <StatCard value={summary.leagues?.toLocaleString()} label="Leagues" />
          </div>
        </section>
      )}

      {/* Best bets */}
      {bestBets && bestBets.length > 0 && (
        <section className="container section">
          <div className="section-header">
            <h2 className="section-title">⚡ Value Bets</h2>
            <span className="section-sub">Positive expected value vs market odds</span>
          </div>
          <div className="match-grid">
            {bestBets.map(pred => {
              const match = upcoming?.find(m => m.id === pred.match_id)
              if (!match) return null
              return (
                <MatchCard
                  key={match.id}
                  match={match}
                  prediction={pred}
                  onClick={() => navigate(`/matches/${match.id}`)}
                />
              )
            })}
          </div>
        </section>
      )}

      {/* Upcoming matches */}
      <section className="container section">
        <div className="section-header">
          <h2 className="section-title">Upcoming Matches</h2>
          <button className="btn btn-ghost" onClick={() => navigate('/matches')} style={{ fontSize: 13 }}>
            See all
          </button>
        </div>

        {loading && <div className="loader"><div className="spinner" /> Loading matches…</div>}

        {upcoming && (
          <div className="match-grid">
            {upcoming.map(m => (
              <MatchCard
                key={m.id}
                match={m}
                prediction={predMap[m.id]}
                onClick={() => navigate(`/matches/${m.id}`)}
              />
            ))}
          </div>
        )}

        {upcoming?.length === 0 && !loading && (
          <div className="empty-state">
            <div style={{ fontSize: 40 }}>📭</div>
            <p>No upcoming matches found.</p>
            <p style={{ fontSize: 13, color: 'var(--muted)' }}>
              Go to Admin → Sync Data to fetch matches from the API.
            </p>
            <button className="btn btn-primary" style={{ marginTop: 16 }} onClick={() => navigate('/admin')}>
              Go to Admin
            </button>
          </div>
        )}
      </section>
    </div>
  )
}
