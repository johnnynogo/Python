import { useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { api } from '../lib/api'
import { useFetch } from '../hooks/useFetch'
import './WorldCup.css'

const TOOLTIP_STYLE = {
  contentStyle: { background: 'var(--navy-800)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8 },
  labelStyle: { color: '#fff', fontSize: 13 },
  itemStyle: { color: 'var(--acid)', fontSize: 12 },
}

// Default 2026 WC group template (update when draw confirmed)
const DEFAULT_GROUPS = {
  A: ["USA", "Mexico", "Canada", "Panama"],
  B: ["Argentina", "Chile", "Uruguay", "Ecuador"],
  C: ["France", "Belgium", "Croatia", "Ukraine"],
  D: ["England", "Netherlands", "Poland", "Serbia"],
  E: ["Spain", "Portugal", "Switzerland", "Denmark"],
  F: ["Brazil", "Colombia", "Venezuela", "Paraguay"],
  G: ["Germany", "Austria", "Czech Republic", "Hungary"],
  H: ["Japan", "South Korea", "Australia", "Indonesia"],
  I: ["Morocco", "Senegal", "Nigeria", "Cameroon"],
  J: ["Egypt", "South Africa", "Ivory Coast", "DR Congo"],
  K: ["Saudi Arabia", "Iran", "Iraq", "Jordan"],
  L: ["Norway", "Sweden", "Finland", "Slovakia"],
}

export default function WorldCup() {
  const [groups, setGroups] = useState(DEFAULT_GROUPS)
  const [nSims, setNSims]   = useState(10000)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]   = useState(null)
  const [editGroup, setEditGroup] = useState(null)
  const [view, setView]     = useState('chart') // 'chart' | 'table'

  const { data: wcTeams } = useFetch(() => api.wcTeams())

  const runSimulation = async () => {
    setLoading(true)
    setError(null)
    try {
      const r = await api.simulateWC({ groups, n_simulations: nSims })
      setResult(r)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const chartData = result?.teams.slice(0, 24).map(t => ({
    name:   t.team.length > 11 ? t.team.slice(0, 11) + '…' : t.team,
    win:    parseFloat((t.win_prob * 100).toFixed(1)),
    final:  parseFloat((t.final_prob * 100).toFixed(1)),
    semi:   parseFloat((t.semifinal_prob * 100).toFixed(1)),
  }))

  const winnerColor = (i) => i === 0 ? 'var(--acid)' : i < 3 ? 'var(--teal)' : i < 8 ? 'var(--navy-400)' : 'var(--navy-600)'

  return (
    <div className="page-wrap container">
      <div className="page-header">
        <div>
          <h1 className="page-title">⚽ World Cup 2026</h1>
          <p className="page-sub">Monte Carlo simulation — {nSims.toLocaleString()} runs per click</p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <select value={nSims} onChange={e => setNSims(Number(e.target.value))}>
            <option value={1000}>1,000 sims (fast)</option>
            <option value={10000}>10,000 sims</option>
            <option value={50000}>50,000 sims (slow)</option>
          </select>
          <button className="btn btn-primary" onClick={runSimulation} disabled={loading}>
            {loading
              ? <><div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> Simulating…</>
              : '▶ Run Simulation'
            }
          </button>
        </div>
      </div>

      {error && <div className="error-box">{error}</div>}

      {/* Groups grid */}
      <h2 className="section-head">Group Stage</h2>
      <div className="groups-grid">
        {Object.entries(groups).map(([gk, teams]) => (
          <div key={gk} className="group-card card">
            <div className="group-header">
              <span className="group-label">Group {gk}</span>
            </div>
            {teams.map((team, i) => {
              const teamData = result?.teams.find(t => t.team === team)
              return (
                <div key={i} className="group-team">
                  <span className="group-team-name">{team}</span>
                  {teamData && (
                    <span className="group-team-prob" style={{
                      color: teamData.win_prob > 0.08 ? 'var(--acid)' :
                             teamData.win_prob > 0.03 ? 'var(--teal)' : 'var(--muted)'
                    }}>
                      {(teamData.win_prob * 100).toFixed(1)}%
                    </span>
                  )}
                </div>
              )
            })}
          </div>
        ))}
      </div>

      {/* Results */}
      {result && (
        <>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', margin: '32px 0 16px' }}>
            <h2 className="section-head" style={{ margin: 0 }}>
              Win probabilities
              <span style={{ fontSize: 13, color: 'var(--muted)', fontWeight: 400, marginLeft: 12 }}>
                {result.n_simulations.toLocaleString()} simulations
              </span>
            </h2>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className={`btn ${view === 'chart' ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setView('chart')} style={{ padding: '7px 14px', fontSize: 13 }}>Chart</button>
              <button className={`btn ${view === 'table' ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setView('table')} style={{ padding: '7px 14px', fontSize: 13 }}>Table</button>
            </div>
          </div>

          {view === 'chart' && (
            <div className="card" style={{ padding: 24 }}>
              <ResponsiveContainer width="100%" height={500}>
                <BarChart data={chartData} layout="vertical" margin={{ left: 100, right: 60, top: 0, bottom: 0 }}>
                  <XAxis type="number" tickFormatter={v => `${v}%`} tick={{ fill: 'var(--muted)', fontSize: 11 }} />
                  <YAxis type="category" dataKey="name" tick={{ fill: 'var(--navy-100)', fontSize: 12 }} width={95} />
                  <Tooltip {...TOOLTIP_STYLE} formatter={v => [`${v}%`]} />
                  <Bar dataKey="win" name="Win tournament" radius={[0,4,4,0]} maxBarSize={18}>
                    {chartData.map((_, i) => <Cell key={i} fill={winnerColor(i)} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {view === 'table' && (
            <div className="card">
              <table className="wc-table">
                <thead>
                  <tr>
                    <th>#</th><th>Team</th><th>Elo</th>
                    <th>Win</th><th>Final</th><th>Semi</th><th>Quarter</th>
                  </tr>
                </thead>
                <tbody>
                  {result.teams.map((t, i) => (
                    <tr key={t.team} className={i < 3 ? 'top-row' : ''}>
                      <td className="rank">{i + 1}</td>
                      <td style={{ fontWeight: 600, color: '#fff' }}>{t.team}</td>
                      <td style={{ color: 'var(--muted)' }}>{t.elo}</td>
                      <td className={t.win_prob > 0.08 ? 'ev-positive' : ''}>
                        {(t.win_prob * 100).toFixed(1)}%
                      </td>
                      <td>{(t.final_prob * 100).toFixed(1)}%</td>
                      <td>{(t.semifinal_prob * 100).toFixed(1)}%</td>
                      <td>{(t.quarterfinal_prob * 100).toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {!result && !loading && (
        <div className="empty-state" style={{ marginTop: 32 }}>
          <div style={{ fontSize: 48 }}>🏆</div>
          <p style={{ fontSize: 16, color: '#fff' }}>Ready to simulate</p>
          <p style={{ fontSize: 13, color: 'var(--muted)' }}>
            Edit the groups above to match the actual draw, then click Run Simulation.
          </p>
        </div>
      )}
    </div>
  )
}
