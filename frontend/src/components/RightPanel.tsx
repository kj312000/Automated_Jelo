import { useState } from 'react'
import { useTradeStore } from '../stores/tradeStore'
import { Panel } from './ui/Panel'
import { Metric } from './ui/Metric'
import { Btn } from './ui/Btn'
import { Badge } from './ui/Badge'
import { tradeApi } from '../services/api'
import { clsx } from 'clsx'
import type { Trade } from '../types'

function TradeRow({ trade }: { trade: Trade }) {
  const isOpen = trade.status === 'OPEN'
  const pnl = isOpen ? trade.unrealized_pnl : trade.pnl
  const pnlPositive = pnl >= 0

  const handleClose = async () => {
    try { await tradeApi.close(trade.id) } catch {}
  }

  return (
    <div className={clsx(
      'rounded border p-2 space-y-1.5 transition-all',
      isOpen ? 'border-accent-blue/20 bg-accent-blue/5' : 'border-bg-border bg-bg-card/30'
    )}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Badge variant={trade.side === 'BUY' ? 'green' : 'red'}>
            {trade.side}
          </Badge>
          <Badge variant={isOpen ? 'blue' : 'gray'} pulse={isOpen}>
            {isOpen ? 'OPEN' : trade.exit_reason}
          </Badge>
        </div>
        {isOpen && (
          <Btn variant="red" size="xs" onClick={handleClose}>✕</Btn>
        )}
      </div>

      <div className="grid grid-cols-2 gap-1">
        <Metric label="Entry" value={`$${trade.entry_price.toFixed(2)}`} size="sm" />
        {!isOpen && (
          <Metric label="Exit" value={`$${trade.exit_price.toFixed(2)}`} size="sm" />
        )}
        {isOpen && (
          <Metric
            label="Current"
            value={`$${trade.entry_price.toFixed(2)}`}
            size="sm"
            color="muted"
          />
        )}
        <Metric
          label={isOpen ? 'Unreal PnL' : 'PnL'}
          value={`${pnlPositive ? '+' : ''}$${pnl.toFixed(3)}`}
          color={pnlPositive ? 'green' : 'red'}
          size="sm"
        />
        <Metric label="Lot" value={trade.lot_size.toFixed(3)} size="sm" color="muted" />
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-[8px] font-mono text-text-muted">
          Slip: ${trade.slippage.toFixed(4)}
        </span>
        <span className="text-[8px] font-mono text-text-muted">
          Lat: {trade.latency_ms.toFixed(0)}ms
        </span>
        {isOpen && (
          <>
            <span className="text-[8px] font-mono text-accent-green">
              MFE: ${trade.mfe.toFixed(3)}
            </span>
            <span className="text-[8px] font-mono text-accent-red">
              MAE: ${trade.mae.toFixed(3)}
            </span>
          </>
        )}
        {!isOpen && trade.duration_seconds > 0 && (
          <span className="text-[8px] font-mono text-text-muted">
            {trade.duration_seconds.toFixed(1)}s
          </span>
        )}
      </div>
    </div>
  )
}

export function RightPanel() {
  const [lotSize, setLotSize] = useState('0.1')
  const autoExecute = useTradeStore(s => s.autoExecute)
  const setAutoExecute = useTradeStore(s => s.setAutoExecute)
  const openTrades = useTradeStore(s => s.openTrades)
  const closedTrades = useTradeStore(s => s.closedTrades)
  const totalPnl = useTradeStore(s => s.totalPnl)
  const winRate = useTradeStore(s => s.winRate)

  const handleBuy = async () => {
    try { await tradeApi.open('BUY', parseFloat(lotSize)) } catch {}
  }

  const handleSell = async () => {
    try { await tradeApi.open('SELL', parseFloat(lotSize)) } catch {}
  }

  const handleCloseAll = async () => {
    try { await tradeApi.closeAll() } catch {}
  }

  const handleAutoToggle = async () => {
    const next = !autoExecute
    try {
      await tradeApi.setAutoExecute(next)
      setAutoExecute(next)
    } catch {}
  }

  return (
    <div className="flex flex-col gap-2 h-full overflow-y-auto">
      {/* Session metrics */}
      <Panel title="Session" compact>
        <div className="grid grid-cols-2 gap-2">
          <Metric
            label="Total PnL"
            value={`${totalPnl >= 0 ? '+' : ''}$${totalPnl.toFixed(3)}`}
            color={totalPnl >= 0 ? 'green' : 'red'}
          />
          <Metric
            label="Win Rate"
            value={`${(winRate * 100).toFixed(0)}%`}
            color={winRate > 0.5 ? 'green' : winRate > 0.35 ? 'yellow' : 'red'}
          />
          <Metric label="Open" value={openTrades.length} color="blue" />
          <Metric label="Closed" value={closedTrades.length} color="muted" />
        </div>
      </Panel>

      {/* Controls */}
      <Panel title="Execution" compact>
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <span className="text-[9px] font-mono text-text-muted shrink-0">Lot ETH</span>
            <input
              type="number"
              value={lotSize}
              onChange={e => setLotSize(e.target.value)}
              step="0.01"
              min="0.01"
              className="flex-1 bg-bg-border text-text-primary text-[10px] font-mono px-2 py-0.5 rounded border border-bg-border focus:border-accent-blue/50 outline-none"
            />
          </div>
          <div className="flex gap-1">
            <Btn variant="green" size="sm" onClick={handleBuy} className="flex-1">▲ BUY</Btn>
            <Btn variant="red" size="sm" onClick={handleSell} className="flex-1">▼ SELL</Btn>
          </div>
          <div className="flex gap-1">
            <Btn variant="ghost" size="xs" onClick={handleCloseAll} className="flex-1">
              CLOSE ALL
            </Btn>
            <button
              onClick={handleAutoToggle}
              className={clsx(
                'flex-1 px-2 py-1 text-[9px] font-mono rounded border transition-all',
                autoExecute
                  ? 'border-accent-yellow/60 text-accent-yellow bg-accent-yellow/10'
                  : 'border-bg-border text-text-muted hover:border-bg-border/80'
              )}
            >
              AUTO {autoExecute ? 'ON' : 'OFF'}
            </button>
          </div>
        </div>
      </Panel>

      {/* Open positions */}
      <Panel
        title={`Open Positions (${openTrades.length})`}
        compact
        headerRight={
          openTrades.length > 0 ? (
            <Btn variant="red" size="xs" onClick={handleCloseAll}>Close All</Btn>
          ) : undefined
        }
      >
        <div className="space-y-2 max-h-56 overflow-y-auto">
          {openTrades.length === 0 ? (
            <span className="text-[9px] font-mono text-text-muted">No open positions</span>
          ) : (
            openTrades.map(t => <TradeRow key={t.id} trade={t} />)
          )}
        </div>
      </Panel>

      {/* Closed trades */}
      <Panel title={`History (${closedTrades.length})`} compact>
        <div className="space-y-1.5 max-h-48 overflow-y-auto">
          {closedTrades.length === 0 ? (
            <span className="text-[9px] font-mono text-text-muted">No trades yet</span>
          ) : (
            closedTrades.slice(0, 20).map(t => <TradeRow key={t.id} trade={t} />)
          )}
        </div>
      </Panel>
    </div>
  )
}
