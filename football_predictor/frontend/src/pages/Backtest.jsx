import { useState } from 'react'
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, ReferenceLine, Cell, ScatterChart, Scatter,
} from 'recharts'
import { api } from '../lib/api'
import { useFetch } from '../hooks/useFetch'
import './Backtest.css'

const TOOLTIP_STYLE = {
  contentStyle: { background: 'var(--navy-800)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8 },
  labelStyle: { color: '#fff', fontFamily: 'var(--font-display)', fontSize: 13 },
  itemStyle: { color: 'var(--acid)', fontSize: 12 },
}

function MetricCard({ label, value, sub, good, bad }) {
  const color = good ? 'var(--teal)' : bad ? 'var(--coral)' : 'var(--acid)'
  return (
    <div className="stat-card">
      <div className="stat-value" style={{ color, fontSize: 24 }}>{value}</div>
      <div className="stat-label">{label}</div>
      {sub && <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 3 }}>{sub}</div>}
    </div>
  )
}

export default function Backtest() {
  const [days, setDays]   = useState(180)
  const [running, setRunning] = useState(false)
  const [report, setReport]   = useState(null)
  const [error, setError]     = useState(null)

  const { data: mlInfo } = useFetch(() => api.mlInfo())

  const runTest = async () => {
    setRunning(true)
    setError(null)
    try {
      const r = await api.backtest(days)
      setReport(r)
    } catch (e) {
      setError(e.message)
    } finally {
      setRunning(false)
    }
  }

  // Build cumulative PnL series
  const pnlSeries = report?.results
    ? (() => {
        let cum = 0
        return report.results.map((r, i) => {
          cum += r.pnl || 0
          return { i, pnl: parseFloat(cum.toFixed(4)), match: `${r.home} vs ${r.away}` }
        })
      })()
    : []

  return (
    <div className="page-wrap container">
      <div className="page-header">
        <div>
          <h1 className="page-title">Back-test</h1>
          <p className="page-sub">Walk-forward validation — no data leakage</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <select
            value={days}
            onChange={e => setDays(Number(e.target.value))}
            style={{ minWidth: 160 }}
          >
            <option value={90}>Last 3 months</option>
            <option value={180}>Last 6 months</option>
            <option value={365}>Last 12 months</option>
            <option value={730}>Last 2 years</option>
            <option value={1825}>Last 5 years</option>
            <option value={3650}>Last 10 years</option>
            <option value={9999}>All time</option>
          </select>
          <button className="btn btn-primary" onClick={runTest} disabled={running}>
            {running ? <><div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> Running…</> : '▶ Run Back-test'}
          </button>
        </div>
      </div>

      {/* ML status */}
      <div className={`ml-status-bar ${mlInfo?.trained ? 'trained' : 'untrained'}`}>
        {mlInfo?.trained
          ? `✓ LightGBM model trained on ${mlInfo.n_features} features (${mlInfo.trained_at?.slice(0,10)})`
          : '⚠ LightGBM not trained — go to Admin → Train ML Model for best results'
        }
      </div>

      {error && <div className="error-box">{error}</div>}

      {report && (
        <>
          {/* Summary metrics */}
          <div className="stat-grid" style={{ marginBottom: 32 }}>
            <MetricCard label="Matches" value={report.n_matches} />
            <MetricCard label="Accuracy" value={`${(report.accuracy * 100).toFixed(1)}%`}
              good={report.accuracy > 0.50} bad={report.accuracy < 0.42}
              sub="Correct outcome prediction" />
            <MetricCard label="Log-loss" value={report.log_loss?.toFixed(4)}
              good={report.log_loss < 0.95} bad={report.log_loss > 1.05}
              sub="Lower = better calibrated" />
            <MetricCard label="Brier (home)" value={report.brier_home?.toFixed(4)}
              good={report.brier_home < 0.22} sub="Lower = better" />
            <MetricCard label="Bets placed" value={report.n_bets}
              sub={`${report.n_wins} won`} />
            <MetricCard label="ROI"
              value={`${(report.roi * 100).toFixed(1)}%`}
              good={report.roi > 0.02} bad={report.roi < -0.05}
              sub="Return on investment" />
          </div>

          {/* Cumulative PnL chart */}
          {pnlSeries.length > 0 && (
            <div className="chart-card card">
              <h3 className="chart-title">Cumulative P&L (Kelly stakes)</h3>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={pnlSeries} margin={{ left: 0, right: 16, top: 8, bottom: 0 }}>
                  <XAxis dataKey="i" hide />
                  <YAxis tick={{ fill: 'var(--muted)', fontSize: 11 }} tickFormatter={v => v.toFixed(2)} />
                  <Tooltip
                    {...TOOLTIP_STYLE}
                    formatter={(v) => [`${v >= 0 ? '+' : ''}${v.toFixed(4)} units`]}
                    labelFormatter={(i) => pnlSeries[i]?.match || ''}
                  />
                  <ReferenceLine y={0} stroke="rgba(255,255,255,0.15)" strokeDasharray="4 4" />
                  <Line
                    type="monotone" dataKey="pnl" stroke="var(--acid)"
                    strokeWidth={2} dot={false}
                    activeDot={{ r: 4, fill: 'var(--acid)' }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Calibration chart */}
          {report.calibration?.length > 0 && (
            <div className="chart-card card">
              <h3 className="chart-title">Calibration — predicted vs actual (home win)</h3>
              <p className="chart-sub">Bars on the diagonal line = perfectly calibrated</p>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={report.calibration} margin={{ left: 0, right: 16, top: 8, bottom: 16 }}>
                  <XAxis dataKey="bin" tick={{ fill: 'var(--muted)', fontSize: 10 }} />
                  <YAxis tick={{ fill: 'var(--muted)', fontSize: 11 }} domain={[0, 1]} tickFormatter={v => `${(v*100).toFixed(0)}%`} />
                  <Tooltip {...TOOLTIP_STYLE}
                    formatter={(v, name) => [`${(v*100).toFixed(1)}%`, name === 'predicted' ? 'Predicted' : 'Actual']} />
                  <Bar dataKey="actual" name="Actual" fill="var(--teal)" opacity={0.8} radius={[3,3,0,0]} />
                  <Bar dataKey="predicted" name="Predicted" fill="var(--amber)" opacity={0.5} radius={[3,3,0,0]} />
                </BarChart>
              </ResponsiveContainer>
              <div className="chart-legend">
                <span className="legend-dot" style={{ background: 'var(--teal)' }} /> Actual frequency
                <span className="legend-dot" style={{ background: 'var(--amber)', marginLeft: 16 }} /> Predicted prob
              </div>
            </div>
          )}

          {/* Last 20 bets */}
          {report.results?.filter(r => r.best_bet).length > 0 && (
            <div className="card" style={{ marginTop: 24 }}>
              <div style={{ padding: '16px 20px', borderBottom: 'var(--border)' }}>
                <h3 style={{ fontSize: 16 }}>Recent bets</h3>
              </div>
              <table className="bt-table">
                <thead>
                  <tr><th>Match</th><th>Bet</th><th>Kelly</th><th>P&L</th></tr>
                </thead>
                <tbody>
                  {report.results.filter(r => r.best_bet).slice(-20).reverse().map((r, i) => (
                    <tr key={i}>
                      <td>{r.home} vs {r.away}</td>
                      <td><span className="badge badge-acid">{r.best_bet?.toUpperCase()}</span></td>
                      <td>{(r.kelly * 100).toFixed(1)}%</td>
                      <td className={r.pnl > 0 ? 'ev-positive' : r.pnl < 0 ? 'ev-negative' : ''}>
                        {r.pnl > 0 ? '+' : ''}{r.pnl?.toFixed(4)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {!report && !running && (
        <div className="empty-state">
          <div style={{ fontSize: 40 }}>📊</div>
          <p>Select a time range and click Run Back-test.</p>
          <p style={{ fontSize: 13, color: 'var(--muted)' }}>
            Requires finished matches in the database. Sync data first.
          </p>
        </div>
      )}
    </div>
  )
}
