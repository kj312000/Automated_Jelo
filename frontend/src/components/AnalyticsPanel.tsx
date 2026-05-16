import { useQuery } from '@tanstack/react-query'
import { analyticsApi } from '../services/api'
import { Panel } from './ui/Panel'
import { Metric } from './ui/Metric'
import type { Analytics } from '../types'

function EquityCurve({ data }: { data: Array<{ t: number; pnl: number }> }) {
  if (!data.length) return <div className="text-[9px] font-mono text-text-muted">No data</div>

  const min = Math.min(...data.map(d => d.pnl))
  const max = Math.max(...data.map(d => d.pnl))
  const range = max - min || 1
  const w = 300
  const h = 80
  const pts = data.map((d, i) => {
    const x = (i / (data.length - 1)) * w
    const y = h - ((d.pnl - min) / range) * h
    return `${x},${y}`
  })

  const last = data[data.length - 1]?.pnl ?? 0

  return (
    <div className="space-y-1">
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full" style={{ height: 80 }}>
        <polyline
          points={pts.join(' ')}
          fill="none"
          stroke={last >= 0 ? '#00ff88' : '#ff3366'}
          strokeWidth="1.5"
        />
        <line x1="0" y1={h - (0 - min) / range * h} x2={w} y2={h - (0 - min) / range * h}
          stroke="#1e1e35" strokeWidth="0.5" strokeDasharray="4" />
      </svg>
      <div className="flex justify-between text-[8px] font-mono text-text-muted">
        <span>Min: ${min.toFixed(2)}</span>
        <span>Max: ${max.toFixed(2)}</span>
      </div>
    </div>
  )
}

function PnlDistribution({ data }: { data: Array<{ bucket: number; count: number }> }) {
  if (!data.length) return <div className="text-[9px] font-mono text-text-muted">No data</div>
  const maxCount = Math.max(...data.map(d => d.count))
  return (
    <div className="flex items-end gap-0.5 h-12">
      {data.map((d, i) => (
        <div key={i} className="flex flex-col items-center flex-1">
          <div
            className={`w-full rounded-t transition-all ${d.bucket >= 0 ? 'bg-accent-green/60' : 'bg-accent-red/60'}`}
            style={{ height: `${(d.count / maxCount) * 100}%` }}
          />
        </div>
      ))}
    </div>
  )
}

export function AnalyticsPanel() {
  const { data: analytics, isLoading } = useQuery<Analytics>({
    queryKey: ['analytics'],
    queryFn: async () => {
      const r = await analyticsApi.get()
      return r.data
    },
    refetchInterval: 10000,
  })

  if (isLoading || !analytics) {
    return (
      <div className="flex items-center justify-center h-full text-text-muted text-xs font-mono">
        Loading analytics...
      </div>
    )
  }

  const a = analytics

  return (
    <div className="h-full overflow-y-auto p-3 grid grid-cols-3 gap-3 content-start">
      {/* Summary */}
      <Panel title="Performance Summary" className="col-span-1">
        <div className="grid grid-cols-2 gap-3">
          <Metric label="Total Trades" value={a.total_trades} />
          <Metric
            label="Win Rate"
            value={`${(a.win_rate * 100).toFixed(1)}%`}
            color={a.win_rate > 0.5 ? 'green' : a.win_rate > 0.35 ? 'yellow' : 'red'}
          />
          <Metric
            label="Total PnL"
            value={`$${a.total_pnl.toFixed(2)}`}
            color={a.total_pnl >= 0 ? 'green' : 'red'}
          />
          <Metric label="Avg PnL" value={`$${a.avg_pnl.toFixed(3)}`} color="muted" />
          <Metric label="Avg Win" value={`$${a.avg_win.toFixed(3)}`} color="green" />
          <Metric label="Avg Loss" value={`$${a.avg_loss.toFixed(3)}`} color="red" />
          <Metric
            label="Profit Factor"
            value={a.profit_factor === Infinity ? '∞' : a.profit_factor.toFixed(2)}
            color={a.profit_factor > 1.5 ? 'green' : a.profit_factor > 1 ? 'yellow' : 'red'}
          />
          <Metric label="Max DD" value={`$${a.max_drawdown.toFixed(2)}`} color="red" />
          <Metric label="Avg Hold" value={`${a.avg_hold_seconds.toFixed(1)}s`} color="muted" />
          <Metric label="Avg Slippage" value={`$${a.avg_slippage.toFixed(4)}`} color="muted" />
          <Metric label="Winners" value={a.winning} color="green" />
          <Metric label="Losers" value={a.losing} color="red" />
        </div>
      </Panel>

      {/* Equity curve */}
      <Panel title="Equity Curve" className="col-span-1">
        <EquityCurve data={a.equity_curve} />
      </Panel>

      {/* PnL distribution */}
      <Panel title="PnL Distribution" className="col-span-1">
        <PnlDistribution data={a.pnl_distribution} />
        <div className="mt-2 flex justify-between text-[8px] font-mono text-text-muted">
          <span>Loss</span>
          <span>Profit</span>
        </div>
      </Panel>

      {/* Exit reasons */}
      <Panel title="Exit Reasons" className="col-span-1">
        <div className="space-y-1">
          {Object.entries(a.exit_reasons).map(([reason, count]) => (
            <div key={reason} className="flex justify-between items-center">
              <span className="text-[9px] font-mono text-text-secondary">{reason}</span>
              <div className="flex items-center gap-2">
                <div
                  className="h-1 bg-accent-blue/40 rounded"
                  style={{ width: `${(count / a.total_trades) * 60}px` }}
                />
                <span className="text-[9px] font-mono text-text-muted">{count}</span>
              </div>
            </div>
          ))}
          {Object.keys(a.exit_reasons).length === 0 && (
            <span className="text-[9px] font-mono text-text-muted">No data</span>
          )}
        </div>
      </Panel>
    </div>
  )
}
