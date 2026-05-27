import { useState } from 'react'
import { format } from 'date-fns'
import { api } from '../lib/api'
import { useFetch } from '../hooks/useFetch'
import './Admin.css'

function ActionCard({ title, desc, action, label, danger }) {
  const [loading, setLoading] = useState(false)
  const [result,  setResult]  = useState(null)
  const run = async () => {
    setLoading(true); setResult(null)
    try {
      const r = await action()
      setResult({ ok: true, msg: r.message || r.status || 'Done ✓' })
    } catch (e) {
      setResult({ ok: false, msg: e.message })
    } finally { setLoading(false) }
  }
  return (
    <div className="action-card card">
      <h3 className="action-title">{title}</h3>
      <p className="action-desc">{desc}</p>
      {result && <div className={`action-result ${result.ok ? 'ok' : 'err'}`}>{result.msg}</div>}
      <button className={`btn ${danger ? 'btn-danger' : 'btn-primary'}`} onClick={run} disabled={loading}>
        {loading ? <><div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> Running…</> : label}
      </button>
    </div>
  )
}

export default function Admin() {
  const { data: logs, loading, refetch } = useFetch(() => api.syncLogs())
  const { data: health } = useFetch(() => api.health())
  const { data: mlInfo, refetch: refetchML } = useFetch(() => api.mlInfo())
  const { data: summary } = useFetch(() => api.summary())

  return (
    <div className="page-wrap container">
      <div className="page-header">
        <div>
          <h1 className="page-title">Admin</h1>
          <p className="page-sub">Data sync, model management, system health</p>
        </div>
        <div className={`health-badge badge ${health?.status === 'ok' ? 'badge-win' : 'badge-loss'}`}>
          {health?.status === 'ok' ? '● DB Connected' : '● DB Error'}
        </div>
      </div>

      {/* System status */}
      <div className="stat-grid" style={{ marginBottom: 32 }}>
        <div className="stat-card">
          <div className="stat-value">{summary?.total_matches ?? '–'}</div>
          <div className="stat-label">Total matches</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{summary?.with_prediction ?? '–'}</div>
          <div className="stat-label">Predictions</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: mlInfo?.trained ? 'var(--teal)' : 'var(--coral)' }}>
            {mlInfo?.trained ? 'Yes' : 'No'}
          </div>
          <div className="stat-label">ML model trained</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{mlInfo?.n_features ?? '–'}</div>
          <div className="stat-label">ML features</div>
        </div>
      </div>

      <h2 className="section-head">Step-by-step workflow</h2>
      <div className="workflow-steps">
        {['Sync data from API', 'Rebuild Elo ratings', 'Train ML model', 'Generate predictions'].map((s, i) => (
          <div key={i} className="workflow-step">
            <div className="step-num">{i + 1}</div>
            <div className="step-label">{s}</div>
          </div>
        ))}
      </div>

      <h2 className="section-head">Actions</h2>
      <div className="actions-grid">
        <ActionCard
          title="1 · Full Sync"
          desc="Fetch latest fixtures, teams, and odds from API-Football. Rebuilds Elo and predictions automatically."
          label="▶ Run Full Sync"
          action={api.triggerSync}
        />
        <ActionCard
          title="2 · Train LightGBM"
          desc="Fit the ML model on all finished matches. Run after syncing new data. Takes ~30s."
          label="▶ Train ML Model"
          action={() => api.trainML().then(r => { refetchML(); return r })}
        />
        <ActionCard
          title="3 · Generate Predictions"
          desc="Re-run Poisson + Elo + ML ensemble for all upcoming matches."
          label="▶ Run Predictions"
          action={api.triggerPredict}
        />
        <ActionCard
          title="Rebuild Elo only"
          desc="Replay all finished matches in order to recompute Elo from scratch."
          label="▶ Rebuild Elo"
          action={api.rebuildElo}
        />
        <ActionCard
          title="Sync Odds"
          desc="Fetch fresh odds from The Odds API for Eliteserien, Allsvenskan and Premier League. Uses 3 of your 500 monthly tokens."
          label="▶ Sync Odds"
          action={api.syncOdds}
        />
      </div>

      <div className="api-notice">
        <span className="notice-icon">🔑</span>
        <div>
          <strong>API Keys needed:</strong> Copy <code>backend/.env.example</code> to <code>backend/.env</code> and fill in
          your <a href="https://www.api-football.com/" target="_blank" rel="noreferrer">API-Football key</a>{' '}
          (free: 100 calls/day). Optional: <a href="https://the-odds-api.com/" target="_blank" rel="noreferrer">The Odds API</a> for better odds coverage.
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', margin: '32px 0 12px' }}>
        <h2 className="section-head" style={{ margin: 0 }}>Sync Logs</h2>
        <button className="btn btn-ghost" style={{ fontSize: 13, padding: '6px 12px' }} onClick={refetch}>↺ Refresh</button>
      </div>

      {loading && <div className="loader"><div className="spinner" /> Loading logs…</div>}
      {logs && (
        <div className="card">
          <table className="logs-table">
            <thead><tr><th>Source</th><th>Status</th><th>Records</th><th>Started</th><th>Error</th></tr></thead>
            <tbody>
              {logs.map((l, i) => (
                <tr key={i} className={l.status === 'error' ? 'log-err' : ''}>
                  <td><code>{l.source}</code></td>
                  <td><span className={`badge ${l.status === 'success' ? 'badge-win' : 'badge-loss'}`}>{l.status}</span></td>
                  <td>{l.records ?? '–'}</td>
                  <td>{l.started_at ? format(new Date(l.started_at), 'dd MMM HH:mm') : '–'}</td>
                  <td className="log-err-msg">{l.error || ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {logs.length === 0 && <div style={{ padding: 24, color: 'var(--muted)', textAlign: 'center', fontSize: 14 }}>No sync logs yet.</div>}
        </div>
      )}
    </div>
  )
}
