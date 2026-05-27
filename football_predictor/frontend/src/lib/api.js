const BASE = '/api'

async function request(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...opts.headers },
    ...opts,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'API error')
  }
  return res.json()
}

export const api = {
  health:          ()            => request('/health'),
  summary:         ()            => request('/stats/summary'),
  leagues:         ()            => request('/leagues'),
  teams:           (leagueId)    => request(`/teams${leagueId ? `?league_id=${leagueId}` : ''}`),
  team:            (id)          => request(`/teams/${id}`),
  teamRatings:     ()            => request('/stats/team_ratings'),
  matches:         (params = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v != null)).toString()
    return request(`/matches${qs ? `?${qs}` : ''}`)
  },
  match:           (id)          => request(`/matches/${id}`),
  predictions:     (params = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v != null)).toString()
    return request(`/predictions${qs ? `?${qs}` : ''}`)
  },
  prediction:      (matchId)     => request(`/predictions/${matchId}`),
  // ML
  mlInfo:          ()            => request('/ml/info'),
  trainML:         ()            => request('/ml/train', { method: 'POST' }),
  // Back-test
  backtest:        (days = 180)  => request(`/backtest?days_back=${days}`),
  // International / World Cup
  wcTeams:         ()            => request('/worldcup/teams'),
  simulateWC:      (body)        => request('/worldcup/simulate', { method: 'POST', body: JSON.stringify(body) }),
  predictIntl:     (body)        => request('/international/predict', { method: 'POST', body: JSON.stringify(body) }),
  // Admin
  syncLogs:        ()            => request('/admin/sync_logs'),
  triggerSync:     ()            => request('/admin/sync',    { method: 'POST' }),
  triggerPredict:  ()            => request('/admin/predict', { method: 'POST' }),
  rebuildElo:      ()            => request('/admin/rebuild_elo', { method: 'POST' }),
  syncOdds: () => request('/admin/sync_odds', { method: 'POST' }),
}
