import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { format } from 'date-fns'
import { api } from '../lib/api'
import { useFetch } from '../hooks/useFetch'
import MatchCard from '../components/MatchCard'
import './Predictions.css'

export default function Matches() {
  const navigate  = useNavigate()
  const [leagueId, setLeagueId] = useState('')
  const [statusFilter, setStatus] = useState('')

  const { data: leagues } = useFetch(() => api.leagues())
  const { data: matches, loading } = useFetch(
    () => api.matches({ league_id: leagueId || undefined, status: statusFilter || undefined, limit: 1000 }),
    [leagueId, statusFilter]
  )
  const { data: preds } = useFetch(() => api.predictions({ limit: 1000 }))

  const predMap = {}
  if (preds) preds.forEach(p => { predMap[p.match_id] = p })

  return (
    <div className="page-wrap container">
      <div className="page-header">
        <div>
          <h1 className="page-title">Matches</h1>
          <p className="page-sub">{matches?.length ?? '…'} matches loaded</p>
        </div>
      </div>

      <div className="filters">
        <select value={leagueId} onChange={e => setLeagueId(e.target.value)}>
          <option value="">All leagues</option>
          {leagues?.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
        </select>
        <select value={statusFilter} onChange={e => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          <option value="NS">Not started</option>
          <option value="FT">Finished</option>
          <option value="1H">Live — 1st half</option>
          <option value="2H">Live — 2nd half</option>
        </select>
      </div>

      {loading && <div className="loader"><div className="spinner" /> Loading…</div>}

      <div className="match-grid">
        {matches?.map(m => (
          <MatchCard
            key={m.id}
            match={m}
            prediction={predMap[m.id]}
            onClick={() => navigate(`/matches/${m.id}`)}
          />
        ))}
      </div>

      {!loading && matches?.length === 0 && (
        <div className="empty-state">
          <div style={{ fontSize: 40 }}>📋</div>
          <p>No matches found.</p>
        </div>
      )}
    </div>
  )
}
