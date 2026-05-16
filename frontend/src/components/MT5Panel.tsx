import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useMT5Store } from '../stores/mt5Store'
import { useSystemStore } from '../stores/systemStore'
import { mt5Api } from '../services/api'
import { Panel } from './ui/Panel'
import { Metric } from './ui/Metric'
import { Btn } from './ui/Btn'
import { Badge } from './ui/Badge'
import { clsx } from 'clsx'
import type { MT5Position } from '../types'

function MT5PositionRow({ pos, onClose }: { pos: MT5Position; onClose: (t: number) => void }) {
  const profitPos = pos.profit >= 0
  const holdMins = Math.floor(pos.hold_seconds / 60)
  const holdSecs = Math.floor(pos.hold_seconds % 60)

  return (
    <div className={clsx(
      'rounded border p-2 space-y-1.5',
      profitPos ? 'border-accent-green/20 bg-accent-green/5' : 'border-accent-red/20 bg-accent-red/5'
    )}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Badge variant={pos.side === 'BUY' ? 'green' : 'red'}>{pos.side}</Badge>
          <span className="text-[9px] font-mono text-text-muted">#{pos.ticket}</span>
          <span className="text-[9px] font-mono text-text-muted">{pos.symbol}</span>
        </div>
        <Btn variant="red" size="xs" onClick={() => onClose(pos.ticket)}>✕</Btn>
      </div>

      <div className="grid grid-cols-3 gap-1">
        <Metric label="Entry" value={`$${pos.entry_price.toFixed(2)}`} size="sm" />
        <Metric label="Current" value={`$${pos.current_price.toFixed(2)}`} size="sm" color="muted" />
        <Metric
          label="Profit"
          value={`${profitPos ? '+' : ''}$${pos.profit.toFixed(2)}`}
          color={profitPos ? 'green' : 'red'}
          size="sm"
        />
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-[8px] font-mono text-text-muted">Vol: {pos.volume}</span>
        <span className="text-[8px] font-mono text-text-muted">
          Hold: {holdMins}m {holdSecs}s
        </span>
        {pos.swap !== 0 && (
          <span className="text-[8px] font-mono text-text-muted">Swap: ${pos.swap.toFixed(3)}</span>
        )}
        {pos.signal_confidence && (
          <span className="text-[8px] font-mono text-accent-purple">
            conf: {(pos.signal_confidence * 100).toFixed(0)}%
          </span>
        )}
      </div>
    </div>
  )
}

export function MT5Panel() {
  const status = useSystemStore(s => s.status)
  const positions = useMT5Store(s => s.positions)
  const account = useMT5Store(s => s.account)
  const errors = useMT5Store(s => s.errors)
  const totalProfit = useMT5Store(s => s.totalProfit)
  const setAccount = useMT5Store(s => s.setAccount)

  const [lotSize, setLotSize] = useState('0.1')
  const [connecting, setConnecting] = useState(false)
  const [liveEnabled, setLiveEnabled] = useState(false)
  const [autoExec, setAutoExec] = useState(false)
  const [availableSymbols, setAvailableSymbols] = useState<string[]>([])
  const [activeSymbol, setActiveSymbol] = useState<string>('')
  const [symbolSearchQuery, setSymbolSearchQuery] = useState('ETH')
  const [searchResults, setSearchResults] = useState<Array<{name: string; description: string}>>([])

  const mt5Connected = status?.mt5_connected ?? false
  const openPositions = Object.values(positions)

  // Poll account info when connected
  useQuery({
    queryKey: ['mt5-account'],
    queryFn: async () => {
      const r = await mt5Api.account()
      if (r.data.ok) setAccount(r.data)
      return r.data
    },
    refetchInterval: 5000,
    enabled: mt5Connected,
  })

  // Poll active symbol when connected
  useQuery({
    queryKey: ['mt5-symbol'],
    queryFn: async () => {
      const r = await mt5Api.activeSymbol()
      setActiveSymbol(r.data.active)
      return r.data
    },
    refetchInterval: 10000,
    enabled: mt5Connected,
  })

  const handleConnect = async () => {
    setConnecting(true)
    setAvailableSymbols([])
    try {
      await mt5Api.connect()
    } catch (e: any) {
      const detail = e?.response?.data?.detail ?? ''
      const syms: string[] = e?.response?.data?.available_eth_symbols ?? []
      useMT5Store.getState().addError(detail || 'Connect failed')
      if (syms.length > 0) setAvailableSymbols(syms)
    }
    setConnecting(false)
  }

  const handleSearchSymbols = async () => {
    try {
      const r = await mt5Api.searchSymbols(symbolSearchQuery)
      setSearchResults(r.data.symbols)
    } catch {}
  }

  const handleDisconnect = async () => {
    try { await mt5Api.disconnect() } catch {}
  }

  const handleEnableToggle = async () => {
    const next = !liveEnabled
    try {
      await mt5Api.enable(next)
      setLiveEnabled(next)
    } catch {}
  }

  const handleAutoExecToggle = async () => {
    const next = !autoExec
    try {
      await mt5Api.autoExecute(next)
      setAutoExec(next)
    } catch {}
  }

  const handleBuy = async () => {
    try { await mt5Api.open('BUY', parseFloat(lotSize)) } catch {}
  }

  const handleSell = async () => {
    try { await mt5Api.open('SELL', parseFloat(lotSize)) } catch {}
  }

  const handleCloseAll = async () => {
    try { await mt5Api.closeAll() } catch {}
  }

  const handleCloseOne = async (ticket: number) => {
    try { await mt5Api.close(ticket) } catch {}
  }

  return (
    <div className="flex flex-col gap-2 h-full overflow-y-auto">
      {/* Connection */}
      <Panel title="MT5 / Exness Connection" compact>
        <div className="space-y-2">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant={mt5Connected ? 'green' : 'red'} pulse={mt5Connected}>
              {mt5Connected ? 'CONNECTED' : 'DISCONNECTED'}
            </Badge>
            {mt5Connected && (
              <>
                <Badge variant={liveEnabled ? 'yellow' : 'gray'}>
                  LIVE {liveEnabled ? 'ON' : 'OFF'}
                </Badge>
                <Badge variant={autoExec ? 'purple' : 'gray'}>
                  AUTO {autoExec ? 'ON' : 'OFF'}
                </Badge>
              </>
            )}
          </div>

          <div className="flex gap-1 flex-wrap">
            {!mt5Connected ? (
              <Btn variant="green" size="sm" onClick={handleConnect} disabled={connecting}>
                {connecting ? '...' : '⚡ CONNECT MT5'}
              </Btn>
            ) : (
              <Btn variant="ghost" size="sm" onClick={handleDisconnect}>DISCONNECT</Btn>
            )}

            {mt5Connected && (
              <>
                <button
                  onClick={handleEnableToggle}
                  className={clsx(
                    'px-2 py-1 text-[9px] font-mono rounded border transition-all',
                    liveEnabled
                      ? 'border-accent-yellow/60 text-accent-yellow bg-accent-yellow/10'
                      : 'border-bg-border text-text-muted'
                  )}
                >
                  LIVE TRADE {liveEnabled ? 'ON' : 'OFF'}
                </button>
                <button
                  onClick={handleAutoExecToggle}
                  className={clsx(
                    'px-2 py-1 text-[9px] font-mono rounded border transition-all',
                    autoExec
                      ? 'border-accent-purple/60 text-accent-purple bg-accent-purple/10'
                      : 'border-bg-border text-text-muted'
                  )}
                >
                  AUTO-EXEC {autoExec ? 'ON' : 'OFF'}
                </button>
              </>
            )}
          </div>

          {/* Safety warning when live enabled */}
          {liveEnabled && (
            <div className="border border-accent-yellow/30 bg-accent-yellow/5 rounded p-1.5">
              <span className="text-[9px] font-mono text-accent-yellow">
                ⚠ LIVE MODE — real money at risk. Auto-TP at $10 / max hold {Math.floor(120 / 60)}min.
              </span>
            </div>
          )}
        </div>
      </Panel>

      {/* Account info */}
      {account && (
        <Panel title={`Account — ${account.login}`} compact>
          <div className="grid grid-cols-2 gap-2">
            <Metric label="Balance" value={`$${account.balance.toFixed(2)}`} color="white" />
            <Metric
              label="Equity"
              value={`$${account.equity.toFixed(2)}`}
              color={account.equity >= account.balance ? 'green' : 'red'}
            />
            <Metric label="Free Margin" value={`$${account.margin_free.toFixed(2)}`} color="muted" />
            <Metric
              label="Open P&L"
              value={`${account.profit >= 0 ? '+' : ''}$${account.profit.toFixed(2)}`}
              color={account.profit >= 0 ? 'green' : 'red'}
            />
            <Metric label="Leverage" value={`1:${account.leverage}`} color="muted" />
            <Metric label="Server" value={account.server.slice(0, 12)} color="muted" />
          </div>
        </Panel>
      )}

      {/* Manual execution — only when connected */}
      {mt5Connected && (
        <Panel title="Manual Execution" compact>
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
              <Btn
                variant="green"
                size="sm"
                onClick={handleBuy}
                disabled={!liveEnabled}
                className="flex-1"
              >
                ▲ BUY
              </Btn>
              <Btn
                variant="red"
                size="sm"
                onClick={handleSell}
                disabled={!liveEnabled}
                className="flex-1"
              >
                ▼ SELL
              </Btn>
            </div>
            {!liveEnabled && (
              <span className="text-[9px] font-mono text-text-muted">
                Enable LIVE TRADE to execute
              </span>
            )}
            {openPositions.length > 0 && (
              <Btn variant="red" size="xs" onClick={handleCloseAll} className="w-full">
                CLOSE ALL ({openPositions.length})
              </Btn>
            )}
          </div>
        </Panel>
      )}

      {/* Open positions */}
      <Panel
        title={`Live Positions (${openPositions.length})`}
        compact
        headerRight={
          <span className={clsx(
            'text-[10px] font-mono font-bold',
            totalProfit >= 0 ? 'text-accent-green' : 'text-accent-red'
          )}>
            {totalProfit >= 0 ? '+' : ''}${totalProfit.toFixed(2)}
          </span>
        }
      >
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {openPositions.length === 0 ? (
            <span className="text-[9px] font-mono text-text-muted">No open positions</span>
          ) : (
            openPositions.map(pos => (
              <MT5PositionRow key={pos.ticket} pos={pos} onClose={handleCloseOne} />
            ))
          )}
        </div>
      </Panel>

      {/* Active symbol indicator */}
      {mt5Connected && activeSymbol && (
        <Panel title="Active Symbol" compact>
          <div className="flex items-center gap-2">
            <Badge variant="green">{activeSymbol}</Badge>
            <span className="text-[9px] font-mono text-text-muted">
              Set MT5_SYMBOL={activeSymbol} in .env to make permanent
            </span>
          </div>
        </Panel>
      )}

      {/* Symbol search — shown when connected OR after symbol_select error */}
      {(mt5Connected || availableSymbols.length > 0) && (
        <Panel title="Symbol Finder" compact>
          <div className="space-y-2">
            {availableSymbols.length > 0 && (
              <div className="space-y-1">
                <div className="text-[9px] font-mono text-accent-yellow">
                  ETH symbols on your account — update MT5_SYMBOL in .env:
                </div>
                {availableSymbols.map(s => (
                  <div key={s} className="text-[10px] font-mono text-accent-green font-bold pl-1">
                    → {s}
                  </div>
                ))}
              </div>
            )}

            {mt5Connected && (
              <>
                <div className="flex items-center gap-1">
                  <input
                    type="text"
                    value={symbolSearchQuery}
                    onChange={e => setSymbolSearchQuery(e.target.value)}
                    placeholder="ETH"
                    className="flex-1 bg-bg-border text-text-primary text-[10px] font-mono px-2 py-0.5 rounded border border-bg-border focus:border-accent-blue/50 outline-none"
                  />
                  <Btn variant="blue" size="xs" onClick={handleSearchSymbols}>SEARCH</Btn>
                </div>
                {searchResults.length > 0 && (
                  <div className="max-h-32 overflow-y-auto space-y-0.5">
                    {searchResults.map(s => (
                      <div key={s.name} className="flex items-center gap-2">
                        <span className="text-[10px] font-mono text-accent-green font-semibold w-20 shrink-0">
                          {s.name}
                        </span>
                        <span className="text-[9px] font-mono text-text-muted truncate">
                          {s.description}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        </Panel>
      )}

      {/* Errors */}
      {errors.length > 0 && (
        <Panel title="MT5 Errors" compact>
          <div className="space-y-1 max-h-24 overflow-y-auto">
            {errors.map((e, i) => (
              <div key={i} className="text-[9px] font-mono text-accent-red">{e}</div>
            ))}
          </div>
        </Panel>
      )}

      {/* Setup instructions when not connected */}
      {!mt5Connected && availableSymbols.length === 0 && (
        <Panel title="Setup Required" compact>
          <div className="space-y-1 text-[9px] font-mono text-text-muted">
            <div>1. Edit <span className="text-accent-blue">backend/.env</span></div>
            <div className="pl-2 text-text-secondary">MT5_LOGIN=12345678</div>
            <div className="pl-2 text-text-secondary">MT5_PASSWORD=your_password</div>
            <div className="pl-2 text-text-secondary">MT5_SERVER=Exness-MT5Real8</div>
            <div className="pl-2 text-text-secondary">MT5_SYMBOL=ETHUSD</div>
            <div className="mt-1">2. Restart backend after editing .env</div>
            <div>3. Click CONNECT MT5</div>
            <div className="text-accent-yellow mt-1">
              ⚠ If symbol error: system auto-detects ETH variants and shows correct name above
            </div>
          </div>
        </Panel>
      )}
    </div>
  )
}
