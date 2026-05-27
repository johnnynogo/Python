import { format } from 'date-fns'
import './MatchCard.css'

function ProbBar({ home, draw, away }) {
  return (
    <div className="prob-bar" title={`Home ${(home*100).toFixed(0)}% · Draw ${(draw*100).toFixed(0)}% · Away ${(away*100).toFixed(0)}%`}>
      <div className="prob-bar-home" style={{ flex: home }} />
      <div className="prob-bar-draw" style={{ flex: draw }} />
      <div className="prob-bar-away" style={{ flex: away }} />
    </div>
  )
}

function EVChip({ ev }) {
  if (ev == null) return null
  const cls = ev >= 0.05 ? 'ev-positive' : ev < 0 ? 'ev-negative' : 'ev-neutral'
  return <span className={`ev-chip ${cls}`}>{ev >= 0 ? '+' : ''}{(ev * 100).toFixed(1)}% EV</span>
}

function BetCard({ prediction, match }) {
  if (!prediction || prediction.best_bet === 'none') return null

  const bet     = prediction.best_bet          // "home" | "draw" | "away"
  const ev      = prediction[`${bet}_ev`]
  const kelly   = prediction.kelly             // fraction of bankroll
  const odds    = prediction[`${bet}_odds`]    // decimal odds — may be null

  // Label for the bet
  const betLabel = bet === 'home'
    ? `${match.home_team?.name} WIN`
    : bet === 'away'
    ? `${match.away_team?.name} WIN`
    : 'DRAW'

  if (ev == null || ev < 0.05) return null

  return (
    <div className="mc-bet-card">
      <div className="mc-bet-header">
        <span className="mc-bet-label">★ {betLabel}</span>
        {odds && <span className="mc-bet-odds">{odds.toFixed(2)}</span>}
      </div>
      <div className="mc-bet-metrics">
        <div className="mc-bet-metric">
          <span className="mc-bet-metric-val ev-positive">
            {ev >= 0 ? '+' : ''}{(ev * 100).toFixed(1)}%
          </span>
          <span className="mc-bet-metric-label">EV</span>
        </div>
        {kelly > 0 && (
          <div className="mc-bet-metric">
            <span className="mc-bet-metric-val" style={{ color: 'var(--acid)' }}>
              {(kelly * 100).toFixed(1)}%
            </span>
            <span className="mc-bet-metric-label">Kelly</span>
          </div>
        )}
        {kelly > 0 && (
          <div className="mc-bet-metric">
            <span className="mc-bet-metric-val" style={{ color: 'var(--muted)' }}>
              {(kelly * 1000).toFixed(0)}kr
            </span>
            <span className="mc-bet-metric-label">per 1000kr</span>
          </div>
        )}
      </div>
    </div>
  )
}

export default function MatchCard({ match, prediction, onClick }) {
  const kickoff = match.kickoff ? new Date(match.kickoff) : null
  const isLive  = ['1H','HT','2H','ET','BT','P','INT'].includes(match.status)
  const isDone  = match.status === 'FT'

  return (
    <div
      className={`match-card card ${prediction ? 'card-accent' : ''} fade-up`}
      onClick={onClick}
      role="button"
      tabIndex={0}
    >
      {/* Header */}
      <div className="mc-header">
        <span className="mc-league">{match.league}</span>
        <span className="mc-time">
          {isLive && <span className="badge badge-live">● LIVE</span>}
          {isDone && <span className="badge badge-draw">FT</span>}
          {!isLive && !isDone && kickoff && format(kickoff, 'EEE dd MMM · HH:mm')}
        </span>
      </div>

      {/* Teams */}
      <div className="mc-teams">
        <div className="mc-team mc-team-home">
          {match.home_team?.logo && <img src={match.home_team.logo} className="mc-logo" alt="" />}
          <span className="mc-name">{match.home_team?.name}</span>
        </div>

        <div className="mc-score-wrap">
          {isDone || isLive
            ? <span className="mc-score">{match.score || '–'}</span>
            : <span className="mc-vs">vs</span>
          }
        </div>

        <div className="mc-team mc-team-away">
          <span className="mc-name mc-name-r">{match.away_team?.name}</span>
          {match.away_team?.logo && <img src={match.away_team.logo} className="mc-logo" alt="" />}
        </div>
      </div>

      {/* xG row */}
      {(match.home_xg != null || match.away_xg != null) && (
        <div className="mc-xg">
          <span className="mc-xg-val">{match.home_xg?.toFixed(2) ?? '–'}</span>
          <span className="mc-xg-label">xG</span>
          <span className="mc-xg-val">{match.away_xg?.toFixed(2) ?? '–'}</span>
        </div>
      )}

      {/* Prediction */}
      {prediction && (
        <div className="mc-pred">
          <ProbBar home={prediction.home_prob} draw={prediction.draw_prob} away={prediction.away_prob} />
          <div className="mc-prob-labels">
            <span>{(prediction.home_prob * 100).toFixed(0)}%</span>
            <span className="mc-prob-mid">{(prediction.draw_prob * 100).toFixed(0)}%</span>
            <span>{(prediction.away_prob * 100).toFixed(0)}%</span>
          </div>
          <BetCard prediction={prediction} match={match} />
        </div>
      )}
    </div>
  )
}