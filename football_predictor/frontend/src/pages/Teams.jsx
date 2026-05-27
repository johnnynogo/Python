import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { api } from '../lib/api'
import { useFetch } from '../hooks/useFetch'
import './Teams.css'

export default function Teams() {
  const navigate  = useNavigate()
  const [leagueId, setLeagueId] = useState('')
  const [view, setView]         = useState('table')  // 'table' | 'chart'

  const { data: leagues } = useFetch(() => api.leagues())
  const { data: teams, loading } = useFetch(
    () => api.teams(leagueId || undefined),
    [leagueId]
  )
  const { data: dcRatings } = useFetch(() => api.teamRatings())

  const dcMap = {}
  if (dcRatings) dcRatings.forEach(r => { dcMap[r.team] = r })

  const sorted = teams ? [...teams].sort((a, b) => b.elo_rating - a.elo_rating) : []
  const chartData = sorted.slice(0, 20).map(t => ({
    name:   t.name.length > 12 ? t.name.slice(0, 12) + '…' : t.name,
    elo:    Math.round(t.elo_rating),
    attack: dcMap[t.name]?.attack,
    defence: dcMap[t.name]?.defence,
  }))

  return (
    <div className="page-wrap container">
      <div className="page-header">
        <div>
          <h1 className="page-title">Team Ratings</h1>
          <p className="page-sub">Elo ratings updated after every result</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            className={`btn ${view === 'table' ? 'btn-primary' : 'btn-ghost'}`}
            onClick={() => setView('table')}
            style={{ padding: '8px 16px', fontSize: 13 }}
          >Table</button>
          <button
            className={`btn ${view === 'chart' ? 'btn-primary' : 'btn-ghost'}`}
            onClick={() => setView('chart')}
            style={{ padding: '8px 16px', fontSize: 13 }}
          >Chart</button>
        </div>
      </div>

      <div className="filters">
        <select value={leagueId} onChange={e => setLeagueId(e.target.value)}>
          <option value="">All leagues</option>
          {leagues?.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
        </select>
        <span className="pred-count">{sorted.length} teams</span>
      </div>

      {loading && <div className="loader"><div className="spinner" /> Loading…</div>}

      {view === 'chart' && sorted.length > 0 && (
        <div className="card" style={{ padding: 24, marginBottom: 24 }}>
          <h3 style={{ marginBottom: 16, fontSize: 16 }}>Elo Ratings — Top 20</h3>
          <ResponsiveContainer width="100%" height={360}>
            <BarChart data={chartData} layout="vertical" margin={{ left: 90, right: 24 }}>
              <XAxis type="number" domain={['auto', 'auto']} tick={{ fill: 'var(--muted)', fontSize: 11 }} />
              <YAxis type="category" dataKey="name" tick={{ fill: 'var(--navy-100)', fontSize: 12 }} width={85} />
              <Tooltip
                contentStyle={{ background: 'var(--navy-800)', border: 'var(--border)', borderRadius: 8 }}
                labelStyle={{ color: '#fff', fontFamily: 'var(--font-display)' }}
                itemStyle={{ color: 'var(--acid)' }}
              />
              <Bar dataKey="elo" radius={[0,4,4,0]} maxBarSize={22}>
                {chartData.map((_, i) => (
                  <Cell key={i} fill={i === 0 ? 'var(--acid)' : i < 3 ? 'var(--teal)' : 'var(--navy-400)'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {view === 'table' && sorted.length > 0 && (
        <div className="card">
          <table className="teams-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Team</th>
                <th>Elo</th>
                <th>Attack</th>
                <th>Defence</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((team, i) => {
                const dc = dcMap[team.name]
                return (
                  <tr key={team.id} onClick={() => navigate(`/teams/${team.id}`)} className="team-row">
                    <td className="rank">{i + 1}</td>
                    <td className="team-name-cell">
                      {team.logo_url && <img src={team.logo_url} className="team-logo-sm" alt="" />}
                      <span>{team.name}</span>
                    </td>
                    <td>
                      <span className={`elo-val ${i === 0 ? 'elo-gold' : i < 3 ? 'elo-silver' : ''}`}>
                        {Math.round(team.elo_rating)}
                      </span>
                    </td>
                    <td className={dc?.attack > 0 ? 'ev-positive' : 'ev-negative'}>
                      {dc ? (dc.attack > 0 ? '+' : '') + dc.attack.toFixed(3) : '–'}
                    </td>
                    <td className={dc?.defence < 0 ? 'ev-positive' : 'ev-negative'}>
                      {dc ? (dc.defence > 0 ? '+' : '') + dc.defence.toFixed(3) : '–'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
