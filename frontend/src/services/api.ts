import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export const flowApi = {
  start: () => api.post('/flow/start'),
  stop: () => api.post('/flow/stop'),
  pauseSignals: () => api.post('/flow/pause-signals'),
  resumeSignals: () => api.post('/flow/resume-signals'),
  reset: () => api.post('/flow/reset'),
}

export const tradeApi = {
  open: (side: string, lot_size?: number) => api.post('/trade/open', { side, lot_size }),
  close: (id: number) => api.post(`/trade/${id}/close`),
  closeAll: () => api.post('/trade/close-all'),
  getOpen: () => api.get('/trade/open'),
  getAll: () => api.get('/trade/all'),
  setAutoExecute: (enabled: boolean) =>
    api.post('/trade/auto-execute', null, { params: { enabled } }),
}

export const signalApi = {
  getRecent: (limit = 50) => api.get('/signals', { params: { limit } }),
}

export const analyticsApi = {
  get: () => api.get('/analytics'),
  getPerformance: () => api.get('/performance'),
}

export const aiApi = {
  analyze: () => api.post('/ai/analyze'),
  getEnabled: () => api.get('/ai/enabled'),
  setSignalsEnabled: (enabled: boolean) =>
    api.post('/ai/signals-enabled', null, { params: { enabled } }),
  setWeaknessEnabled: (enabled: boolean) =>
    api.post('/ai/weakness-enabled', null, { params: { enabled } }),
}

export const statusApi = {
  get: () => api.get('/status'),
}

export const configApi = {
  get: () => api.get('/config'),
  getRuntime: () => api.get('/config/runtime'),
  setRuntime: (data: Record<string, number | string>) => api.post('/config/runtime', data),
}

export const replayApi = {
  play: (speed: number) => api.post('/replay/play', { speed }),
  pause: () => api.post('/replay/pause'),
  status: () => api.get('/replay/status'),
}

export const executorApi = {
  heartbeat: (executor_id = '', version = '') =>
    api.post('/executor/heartbeat', null, { params: { executor_id, version } }),
  queuePending: () => api.get('/executor/queue'),
  queueRecent: (limit = 50) => api.get('/executor/queue/recent', { params: { limit } }),
  ack: (id: number, status: string, mt5_ticket?: number, error = '') =>
    api.post(`/executor/queue/${id}/ack`, { status, mt5_ticket, error }),
}

export const tradingApi = {
  status: () => api.get('/trading/status'),
  kill: () => api.post('/trading/kill'),
  resume: () => api.post('/trading/resume'),
}

export const mt5Api = {
  connect: () => api.post('/mt5/connect'),
  disconnect: () => api.post('/mt5/disconnect'),
  enable: (enabled: boolean) => api.post('/mt5/enable', null, { params: { enabled } }),
  autoExecute: (enabled: boolean) => api.post('/mt5/auto-execute', null, { params: { enabled } }),
  account: () => api.get('/mt5/account'),
  positions: () => api.get('/mt5/positions'),
  open: (side: string, lot_size?: number) => api.post('/mt5/trade/open', { side, lot_size }),
  close: (ticket: number) => api.post(`/mt5/trade/${ticket}/close`),
  closeAll: () => api.post('/mt5/trade/close-all'),
  searchSymbols: (query: string) => api.get('/mt5/symbols/search', { params: { query } }),
  activeSymbol: () => api.get('/mt5/symbol/active'),
}
