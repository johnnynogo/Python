import { useParams, useNavigate } from 'react-router-dom'
import { format } from 'date-fns'
import { api } from '../lib/api'
import { useFetch } from '../hooks/useFetch'
import './MatchDetail.css'

function ProbGauge({ label, prob, color }) {
  return (
    <div className="gauge-wrap">
      <div className="gauge-label">{label}</div>
      <div className="gauge-pct" style={{ color }}>{(prob * 100).toFixed(1)}%</div>
      <div className="gauge-bar-bg">
        <div className="gauge-bar-fill" style={{ width: `${prob * 100}%`, background: color }} />
      </div>
    </div>
  )
}

function BestBetBox({ pred, odds, match }) {
  if (!odds) return null

  const evs = {
    home: pred.home_prob * odds.home - 1,
    draw: pred.draw_prob * odds.draw - 1,
    away: pred.away_prob * odds.away - 1,
  }

  const best = Object.entries(evs).sort((a, b) => b[1] - a[1])[0]
  if (!best || best[1] < 0.05) return null

  const [bestKey, bestEv] = best
  const bestOdds  = odds[bestKey]
  const bestProb  = pred[`${bestKey}_prob`]
  const bestLabel = bestKey === 'home'
    ? match.home_team?.name
    : bestKey === 'away'
    ? match.away_team?.name
    : 'DRAW'

  const total   = (odds.home ? 1/odds.home : 0) + (odds.draw ? 1/odds.draw : 0) + (odds.away ? 1/odds.away : 0)
  const mktFair = bestOdds && total > 0 ? (1/bestOdds) / total : null
  const kelly   = Math.min(Math.max((bestProb * bestOdds - 1) / (bestOdds - 1), 0) * 0.25, 0.10)

  return (
    <div className="kelly-box">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <span className="badge badge-acid">★ BET: {bestLabel} WIN</span>
        <span style={{ fontSize: 18, fontWeight: 700, color: '#fff' }}>@ {bestOdds?.toFixed(2)}</span>
      </div>
      <div style={{ display: 'flex', gap: 24 }}>
        <div>
          <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--teal)' }}>
            +{(bestEv * 100).toFixed(1)}%
          </div>
          <div style={{ fontSize: 11, color: 'var(--muted)' }}>EXPECTED VALUE</div>
        </div>
        <div>
          <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--acid)' }}>
            {(kelly * 100).toFixed(1)}%
          </div>
          <div style={{ fontSize: 11, color: 'var(--muted)' }}>KELLY STAKE</div>
        </div>
        <div>
          <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--amber)' }}>
            {(kelly * 1000).toFixed(0)}kr
          </div>
          <div style={{ fontSize: 11, color: 'var(--muted)' }}>PER 1000kr BANKROLL</div>
        </div>
      </div>
      <div style={{ marginTop: 8, fontSize: 12, color: 'var(--muted)' }}>
        Model gives {(bestProb * 100).toFixed(1)}% — market prices {mktFair != null ? (mktFair * 100).toFixed(1) : '–'}%
      </div>
    </div>
  )
}

export default function MatchDetail() {
  const { id }     = useParams()
  const navigate   = useNavigate()
  const { data: match, loading } = useFetch(() => api.match(Number(id)), [id])

  if (loading) return <div className="loader"><div className="spinner" /> Loading match…</div>
  if (!match)  return <div className="loader">Match not found.</div>

  const pred    = match.prediction
  const odds    = match.odds
  const kickoff = match.kickoff ? new Date(match.kickoff) : null
  const isDone  = match.status === 'FT'

  const oddsTotal = odds
    ? (odds.home ? 1/odds.home : 0) + (odds.draw ? 1/odds.draw : 0) + (odds.away ? 1/odds.away : 0)
    : 0

  return (
    <div className="page-wrap container">
      <button className="btn btn-ghost back-btn" onClick={() => navigate(-1)}>← Back</button>

      {/* Match header */}
      <div className="md-hero card card-accent">
        <div className="md-league">{match.league}</div>
        <div className="md-teams">
          <div className="md-team">
            {match.home_team?.logo && <img src={match.home_team.logo} className="md-logo" alt="" />}
            <span className="md-team-name">{match.home_team?.name}</span>
          </div>
          <div className="md-center">
            {isDone
              ? <div className="md-score">{match.score}</div>
              : <div className="md-vs">vs</div>
            }
            <div className="md-time">
              {kickoff ? format(kickoff, 'EEEE d MMMM yyyy · HH:mm') : 'TBD'}
            </div>
            {match.home_xg != null && (
              <div className="md-xg-row">
                <span style={{ color: 'var(--teal)' }}>{match.home_xg?.toFixed(2)}</span>
                <span style={{ color: 'var(--muted)', fontSize: 11 }}>xG</span>
                <span style={{ color: 'var(--coral)' }}>{match.away_xg?.toFixed(2)}</span>
              </div>
            )}
          </div>
          <div className="md-team md-team-r">
            <span className="md-team-name">{match.away_team?.name}</span>
            {match.away_team?.logo && <img src={match.away_team.logo} className="md-logo" alt="" />}
          </div>
        </div>
      </div>

      <div className="md-grid">

        {/* Model Prediction panel */}
        {pred && (
          <div className="card md-section">
            <h2 className="md-section-title">Model Prediction</h2>
            <div className="gauges">
              <ProbGauge label={match.home_team?.name} prob={pred.home_prob} color="var(--teal)" />
              <ProbGauge label="Draw"                  prob={pred.draw_prob} color="var(--amber)" />
              <ProbGauge label={match.away_team?.name} prob={pred.away_prob} color="var(--coral)" />
            </div>

            <div className="md-model-row">
              <div className="md-model-col">
                <div className="md-model-label">Poisson (Dixon-Coles)</div>
                <div className="md-model-vals">
                  <span>{(pred.poisson_home * 100).toFixed(0)}%</span>
                  <span>{(pred.poisson_draw * 100).toFixed(0)}%</span>
                  <span>{(pred.poisson_away * 100).toFixed(0)}%</span>
                </div>
              </div>
              <div className="md-model-col">
                <div className="md-model-label">ML / Elo model</div>
                <div className="md-model-vals">
                  <span>{(pred.ml_home * 100).toFixed(0)}%</span>
                  <span>{(pred.ml_draw * 100).toFixed(0)}%</span>
                  <span>{(pred.ml_away * 100).toFixed(0)}%</span>
                </div>
              </div>
            </div>

            <div className="md-confidence">
              Confidence: <strong style={{ color: 'var(--acid)' }}>{(pred.confidence * 100).toFixed(0)}%</strong>
            </div>
          </div>
        )}

        {/* Market vs Model panel */}
        {pred && (
          <div className="card md-section">
            <h2 className="md-section-title">Market vs Model</h2>
            {odds ? (
              <>
                <table className="odds-table">
                  <thead>
                    <tr>
                      <th>Outcome</th>
                      <th>Odds</th>
                      <th>Mkt prob</th>
                      <th>Our prob</th>
                      <th>EV</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      { key: 'home', label: match.home_team?.name, oddsVal: odds.home, probKey: 'home_prob' },
                      { key: 'draw', label: 'Draw',                oddsVal: odds.draw, probKey: 'draw_prob' },
                      { key: 'away', label: match.away_team?.name, oddsVal: odds.away, probKey: 'away_prob' },
                    ].map(({ key, label, oddsVal, probKey }) => {
                      const ourProb = pred[probKey]
                      const mktFair = oddsVal && oddsTotal > 0 ? (1/oddsVal) / oddsTotal : null
                      const ev      = oddsVal && ourProb ? ourProb * oddsVal - 1 : null
                      const evClass = ev >= 0.05 ? 'ev-positive' : ev < 0 ? 'ev-negative' : ''
                      const isBest  = ev != null && ev === Math.max(
                        pred.home_prob * odds.home - 1,
                        pred.draw_prob * odds.draw - 1,
                        pred.away_prob * odds.away - 1,
                      )
                      return (
                        <tr key={key} className={isBest && ev >= 0.05 ? 'best-row' : ''}>
                          <td>{isBest && ev >= 0.05 ? '★ ' : ''}{label}</td>
                          <td style={{ fontWeight: 700, color: '#fff' }}>{oddsVal?.toFixed(2) ?? '–'}</td>
                          <td style={{ color: 'var(--muted)' }}>
                            {mktFair != null ? (mktFair * 100).toFixed(1) + '%' : '–'}
                          </td>
                          <td style={{ color: ourProb > (mktFair ?? 0) ? 'var(--teal)' : 'var(--coral)' }}>
                            {(ourProb * 100).toFixed(1)}%
                          </td>
                          <td className={evClass}>
                            {ev != null ? (ev >= 0 ? '+' : '') + (ev * 100).toFixed(1) + '%' : '–'}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>

                <BestBetBox pred={pred} odds={odds} match={match} />
              </>
            ) : (
              <div style={{ color: 'var(--muted)', fontSize: 13, padding: '16px 0' }}>
                No market odds available for this match yet.<br />
                Click <strong>Sync Odds</strong> in Admin to fetch latest odds.
              </div>
            )}
          </div>
        )}

        {!pred && (
          <div className="card md-section" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 180 }}>
            <div style={{ color: 'var(--muted)', textAlign: 'center', fontSize: 14 }}>
              <div style={{ fontSize: 32, marginBottom: 8 }}>🔮</div>
              No prediction generated yet.<br />Run predictions from Admin.
            </div>
          </div>
        )}

      </div>
    </div>
  )
}