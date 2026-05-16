import { useMarketStore } from '../stores/marketStore'
import { Panel } from './ui/Panel'
import { Metric } from './ui/Metric'
import { Badge } from './ui/Badge'
import { clsx } from 'clsx'

function DeltaBar({ value, max }: { value: number; max: number }) {
  const pct = Math.min(Math.abs(value) / max, 1) * 100
  const isPositive = value >= 0
  return (
    <div className="relative h-1.5 bg-bg-border rounded-full overflow-hidden">
      <div
        className={clsx('absolute top-0 h-full rounded-full transition-all duration-100', {
          'bg-accent-green left-1/2': isPositive,
          'bg-accent-red right-1/2': !isPositive,
        })}
        style={{ width: `${pct / 2}%` }}
      />
    </div>
  )
}

function AggressionMeter({ score }: { score: number }) {
  const pct = score * 100
  return (
    <div className="space-y-0.5">
      <div className="flex justify-between text-[9px] font-mono text-text-muted">
        <span>SELLERS</span>
        <span>BUYERS</span>
      </div>
      <div className="relative h-2 bg-bg-border rounded-full overflow-hidden">
        <div
          className="absolute left-0 top-0 h-full bg-gradient-to-r from-accent-red via-accent-yellow to-accent-green rounded-full"
          style={{ width: '100%', opacity: 0.3 }}
        />
        <div
          className="absolute top-0 w-1 h-full bg-white rounded-full transition-all duration-100"
          style={{ left: `${pct}%`, transform: 'translateX(-50%)' }}
        />
      </div>
      <div className="text-center text-[9px] font-mono text-text-muted">
        {(score * 100).toFixed(1)}%
      </div>
    </div>
  )
}

export function LeftPanel() {
  const market = useMarketStore(s => s.market)
  const signals = useMarketStore(s => s.signals)

  if (!market) {
    return (
      <div className="flex items-center justify-center h-full text-text-muted text-xs font-mono">
        Waiting for data...
      </div>
    )
  }

  const vel5 = market.velocity[5] ?? 0
  const vel1 = market.velocity[1] ?? 0
  const acc1 = market.acceleration[1] ?? 0
  const net5 = market.net_delta[5] ?? 0
  const buy5 = market.agg_buy_delta[5] ?? 0
  const sell5 = market.agg_sell_delta[5] ?? 0

  const fmt = (n: number) =>
    Math.abs(n) >= 1000
      ? `${(n / 1000).toFixed(1)}K`
      : n.toFixed(0)

  const fmtPrice = (n: number) => `$${n.toFixed(2)}`

  return (
    <div className="flex flex-col gap-2 h-full overflow-y-auto pr-0.5">
      {/* Price block */}
      <Panel title="ETH/USDT" compact>
        <div className="grid grid-cols-2 gap-2">
          <Metric label="Price" value={fmtPrice(market.price)} color="white" size="lg" />
          <Metric label="Spread" value={`$${market.spread.toFixed(4)}`} color="muted" />
          <Metric label="Bid" value={fmtPrice(market.bid)} color="green" />
          <Metric label="Ask" value={fmtPrice(market.ask)} color="red" />
        </div>
      </Panel>

      {/* Aggression meter */}
      <Panel title="Aggression" compact>
        <AggressionMeter score={market.aggression_score} />
      </Panel>

      {/* Delta metrics */}
      <Panel title="Order Flow Δ (5s)" compact>
        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <span className="text-[9px] font-mono text-text-muted">BUY Δ</span>
            <span className="text-[11px] font-mono text-accent-green font-semibold">${fmt(buy5)}</span>
          </div>
          <DeltaBar value={buy5} max={Math.max(buy5, sell5, 1)} />

          <div className="flex justify-between items-center">
            <span className="text-[9px] font-mono text-text-muted">SELL Δ</span>
            <span className="text-[11px] font-mono text-accent-red font-semibold">${fmt(sell5)}</span>
          </div>
          <DeltaBar value={-sell5} max={Math.max(buy5, sell5, 1)} />

          <div className="border-t border-bg-border pt-1 flex justify-between items-center">
            <span className="text-[9px] font-mono text-text-muted">NET Δ</span>
            <span className={clsx('text-[11px] font-mono font-bold', {
              'text-accent-green': net5 >= 0,
              'text-accent-red': net5 < 0,
            })}>
              {net5 >= 0 ? '+' : ''}{fmt(net5)}
            </span>
          </div>
        </div>
      </Panel>

      {/* CVD + Velocity */}
      <Panel title="Momentum" compact>
        <div className="grid grid-cols-2 gap-2">
          <Metric
            label="CVD"
            value={`${fmt(market.cvd)}`}
            color={market.cvd >= 0 ? 'green' : 'red'}
          />
          <Metric
            label="Vel (5s)"
            value={`${fmt(vel5)}/s`}
            color={vel5 >= 0 ? 'green' : 'red'}
          />
          <Metric
            label="Vel (1s)"
            value={`${fmt(vel1)}/s`}
            color={vel1 >= 0 ? 'green' : 'red'}
          />
          <Metric
            label="Accel"
            value={`${fmt(acc1)}`}
            color={acc1 >= 0 ? 'blue' : 'yellow'}
          />
        </div>
      </Panel>

      {/* Liquidity */}
      <Panel title="Liquidity" compact>
        <div className="space-y-1.5">
          <div className="flex justify-between">
            <span className="text-[9px] font-mono text-text-muted">Imbalance</span>
            <span className={clsx('text-[10px] font-mono font-semibold', {
              'text-accent-green': market.imbalance > 0.1,
              'text-accent-red': market.imbalance < -0.1,
              'text-text-secondary': Math.abs(market.imbalance) <= 0.1,
            })}>
              {(market.imbalance * 100).toFixed(1)}%
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-[9px] font-mono text-text-muted">Bid Depth</span>
            <span className="text-[10px] font-mono text-accent-green">${fmt(market.bid_total)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-[9px] font-mono text-text-muted">Ask Depth</span>
            <span className="text-[10px] font-mono text-accent-red">${fmt(market.ask_total)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-[9px] font-mono text-text-muted">Cont. Prob</span>
            <span className="text-[10px] font-mono text-accent-blue">
              {(market.continuation_prob * 100).toFixed(0)}%
            </span>
          </div>
        </div>
      </Panel>

      {/* Alerts */}
      <Panel title="Alerts" compact>
        <div className="space-y-1">
          {market.sweep_detected && (
            <Badge variant="yellow" pulse>SWEEP DETECTED</Badge>
          )}
          {market.absorption_detected && (
            <Badge variant="purple" pulse>ABSORPTION</Badge>
          )}
          {market.liquidity_pull_detected && (
            <Badge variant="yellow" pulse>LIQ PULL</Badge>
          )}
          {market.breakout_strength > 1.5 && (
            <Badge variant="blue" pulse>BREAKOUT {market.breakout_strength.toFixed(1)}x</Badge>
          )}
          {!market.sweep_detected && !market.absorption_detected && !market.liquidity_pull_detected && (
            <span className="text-[9px] font-mono text-text-muted">No active alerts</span>
          )}
        </div>
      </Panel>

      {/* Recent signals mini */}
      <Panel title={`Signals (${signals.length})`} compact>
        <div className="space-y-1 max-h-32 overflow-y-auto">
          {signals.slice(0, 8).map(s => (
            <div key={s.id} className="flex items-center justify-between">
              <span className={clsx('text-[9px] font-mono font-semibold', {
                'text-accent-green': s.signal_type.includes('LONG'),
                'text-accent-red': s.signal_type.includes('SHORT'),
                'text-accent-yellow': s.signal_type.includes('SWEEP'),
                'text-accent-purple': s.signal_type.includes('ABSORPTION'),
              })}>
                {s.signal_type.replace(/_/g, ' ')}
              </span>
              <span className="text-[9px] font-mono text-text-muted">
                {(s.confidence * 100).toFixed(0)}%
              </span>
            </div>
          ))}
          {signals.length === 0 && (
            <span className="text-[9px] font-mono text-text-muted">No signals yet</span>
          )}
        </div>
      </Panel>
    </div>
  )
}
