import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useFetch } from '../hooks/useFetch'
import MatchCard from '../components/MatchCard'
import './Predictions.css'

// Helper to get date range for filter
function getDateRange(filter) {
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const tomorrow = new Date(today); tomorrow.setDate(today.getDate() + 1)
  const dayAfter = new Date(today); dayAfter.setDate(today.getDate() + 2)
  const weekEnd = new Date(today); weekEnd.setDate(today.getDate() + 7)

  if (filter === 'today')    return { from: today, to: tomorrow }
  if (filter === 'tomorrow') return { from: tomorrow, to: dayAfter }
  if (filter === 'week')     return { from: today, to: weekEnd }
  return null
}

export default function Predictions() {
  const navigate = useNavigate()
  const [bestOnly, setBestOnly] = useState(false)
  const [leagueId, setLeagueId] = useState('')
  const [dateFilter, setDateFilter] = useState('today')  // default to today

  const { data: leagues } = useFetch(() => api.leagues())
  const { data: preds, loading } = useFetch(
    () => api.predictions({ best_only: bestOnly || undefined, league_id: leagueId || undefined, limit: 1000 }),
    [bestOnly, leagueId]
  )
  const { data: matches } = useFetch(() => api.matches({ upcoming: true, limit: 1000 }))

  const matchMap = {}
  if (matches) matches.forEach(m => { matchMap[m.id] = m })

  // Apply date filter client-side
  const dateRange = getDateRange(dateFilter)
  const filtered = preds ? preds.filter(p => {
    const match = matchMap[p.match_id]
    if (!match) return false
    if (dateRange) {
      const kickoff = new Date(match.kickoff)
      if (kickoff < dateRange.from || kickoff >= dateRange.to) return false
    }
    return true
  }) : []

  const sorted = [...filtered].sort((a, b) => {
    const ma = matchMap[a.match_id]
    const mb = matchMap[b.match_id]
    return new Date(ma?.kickoff) - new Date(mb?.kickoff)  // sort by kickoff time
  })

  return (
    <div className="page-wrap container">
      <div className="page-header">
        <div>
          <h1 className="page-title">Predictions</h1>
          <p className="page-sub">Model confidence + market edge analysis</p>
        </div>
      </div>

      <div className="filters">
        <select value={leagueId} onChange={e => setLeagueId(e.target.value)} style={{ minWidth: 180 }}>
          <option value="">All leagues</option>
          {leagues?.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
        </select>

        <select value={dateFilter} onChange={e => setDateFilter(e.target.value)}>
          <option value="today">Today</option>
          <option value="tomorrow">Tomorrow</option>
          <option value="week">This week</option>
          <option value="">All dates</option>
        </select>

        <label className="toggle-label">
          <input type="checkbox" checked={bestOnly} onChange={e => setBestOnly(e.target.checked)} />
          Value bets only
        </label>
        <span className="pred-count">{sorted.length} predictions</span>
      </div>

      {loading && <div className="loader"><div className="spinner" /> Loading predictions…</div>}

      <div className="match-grid">
        {sorted.map(pred => {
          const match = matchMap[pred.match_id]
          if (!match) return null
          return (
            <MatchCard
              key={pred.match_id}
              match={match}
              prediction={pred}
              onClick={() => navigate(`/matches/${pred.match_id}`)}
            />
          )
        })}
      </div>

      {!loading && sorted.length === 0 && (
        <div className="empty-state">
          <div style={{ fontSize: 40 }}>🔮</div>
          <p>No predictions found.</p>
          <p style={{ fontSize: 13, color: 'var(--muted)' }}>Try a different date or league filter.</p>
        </div>
      )}
    </div>
  )
}