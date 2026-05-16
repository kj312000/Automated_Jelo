export interface MarketState {
  price: number
  bid: number
  ask: number
  spread: number
  cvd: number
  imbalance: number
  bid_total: number
  ask_total: number
  agg_buy_delta: Record<number, number>
  agg_sell_delta: Record<number, number>
  net_delta: Record<number, number>
  velocity: Record<number, number>
  acceleration: Record<number, number>
  sweep_detected: boolean
  absorption_detected: boolean
  liquidity_pull_detected: boolean
  breakout_strength: number
  continuation_prob: number
  aggression_score: number
  timestamp: number
}

export type SignalType =
  | 'LONG_CONTINUATION'
  | 'SHORT_CONTINUATION'
  | 'SWEEP_REVERSAL_LONG'
  | 'SWEEP_REVERSAL_SHORT'
  | 'MOMENTUM_EXHAUSTION'
  | 'ABSORPTION_REVERSAL'

export interface AIDecision {
  execute: boolean
  reason: string
  confidence_override: number | null
}

export interface Signal {
  id: number
  signal_type: SignalType
  confidence: number
  continuation_prob: number
  velocity_score: number
  delta_score: number
  imbalance_score: number
  aggression_score: number
  price: number
  trigger_reason: string
  timestamp: number
  ai_decision?: AIDecision
  quality_score?: number
  breakout_phase?: string
  regime?: string
  ai_bias?: string
  ai_bias_reason?: string
}

export interface Trade {
  id: number
  side: 'BUY' | 'SELL'
  entry_price: number
  exit_price: number
  lot_size: number
  commission: number
  slippage: number
  latency_ms: number
  pnl: number
  unrealized_pnl: number
  mfe: number
  mae: number
  status: 'OPEN' | 'CLOSED'
  exit_reason: string
  signal_id: number | null
  signal_confidence: number | null
  opened_at: number
  closed_at: number
  duration_seconds: number
}

export interface AIAnalysis {
  type: 'ai_analysis'
  content: string
  analysis_type?: string
  analysis_count?: number
  threshold?: number
  bias?: string
  rr_ratio?: number
  signals_reviewed?: number
  price?: number
  timestamp: number
}

export interface CooldownState {
  active: boolean
  remaining_seconds: number
  reason: string
  consecutive_losses: number
}

export interface AdaptiveParams {
  sl: number
  tp: number
  rr: number
}

export interface SystemStatus {
  binance_connected: boolean
  signal_engine_running: boolean
  signal_engine_paused: boolean
  execution_simulator_running?: boolean
  ai_running: boolean
  ai_threshold?: number
  ai_bias?: string
  ai_bias_reason?: string
  mt5_connected: boolean
  mt5_enabled: boolean
  mt5_auto_execute: boolean
  mt5_symbol?: string
  ws_clients: number
  regime?: string
  session?: string
  exec_health?: string
  exec_spread_ratio?: number
  cooldown?: CooldownState
  adaptive?: AdaptiveParams
  consecutive_losses?: number
  tradeable?: boolean
  timestamp: number
}

export interface Analytics {
  total_trades: number
  winning: number
  losing: number
  win_rate: number
  avg_pnl: number
  total_pnl: number
  avg_win: number
  avg_loss: number
  profit_factor: number
  avg_hold_seconds: number
  avg_slippage: number
  avg_mfe: number
  avg_mae: number
  max_drawdown: number
  exit_reasons: Record<string, number>
  equity_curve: Array<{ t: number; pnl: number }>
  pnl_distribution: Array<{ bucket: number; count: number }>
}

export interface MT5Position {
  ticket: number
  side: 'BUY' | 'SELL'
  symbol: string
  volume: number
  entry_price: number
  current_price: number
  profit: number
  swap: number
  commission: number
  hold_seconds: number
  opened_at: number
  sl: number
  tp: number
  signal_id: number | null
  signal_confidence: number | null
  timestamp: number
}

export interface MT5AccountInfo {
  ok: boolean
  login: number
  name: string
  balance: number
  equity: number
  margin: number
  margin_free: number
  margin_level: number
  profit: number
  currency: string
  leverage: number
  server: string
}

export interface CandleData {
  time: number
  open: number
  high: number
  low: number
  close: number
}

export type WSMessage =
  | ({ type: 'market_update' } & MarketState)
  | ({ type: 'signal' } & Signal)
  | ({ type: 'trade_update' } & Trade)
  | AIAnalysis
  | ({ type: 'mt5_position'; event: string } & MT5Position)
  | { type: 'mt5_error'; error: string; timestamp: number }
  | { type: 'connected'; timestamp: number }
  | { type: 'replay_update'; replay_position: number }
