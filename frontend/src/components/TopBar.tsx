import { useSystemStore } from '../stores/systemStore'
import { useMarketStore } from '../stores/marketStore'
import { Badge } from './ui/Badge'
import { Btn } from './ui/Btn'
import { flowApi, tradeApi } from '../services/api'

export function TopBar() {
  const wsConnected = useSystemStore(s => s.wsConnected)
  const status = useSystemStore(s => s.status)
  const price = useMarketStore(s => s.market?.price)
  const setActivePanel = useSystemStore(s => s.setActivePanel)
  const activePanel = useSystemStore(s => s.activePanel)

  const handleStart = async () => { try { await flowApi.start() } catch {} }
  const handleStop = async () => { try { await flowApi.stop() } catch {} }
  const handlePause = async () => { try { await flowApi.pauseSignals() } catch {} }
  const handleReset = async () => { try { await flowApi.reset() } catch {} }
  const handleClearTrades = async () => { try { await tradeApi.closeAll() } catch {} }

  return (
    <header className="h-12 bg-bg-secondary border-b border-bg-border flex items-center px-4 gap-4 shrink-0">
      {/* Brand */}
      <div className="flex items-center gap-2 mr-2">
        <div className="w-2 h-2 rounded-full bg-accent-green animate-pulse" />
        <span className="font-mono text-xs font-bold text-text-primary uppercase tracking-widest">
          ETH-MST
        </span>
        <span className="text-text-muted text-[9px] font-mono">MICROSTRUCTURE TERMINAL</span>
      </div>

      {/* Price */}
      {price && (
        <span className="font-mono text-base font-bold text-accent-green">
          ${price.toFixed(2)}
        </span>
      )}

      {/* Status indicators */}
      <div className="flex items-center gap-2 ml-2">
        <Badge variant={wsConnected ? 'green' : 'red'} pulse={wsConnected}>
          WS
        </Badge>
        <Badge variant={status?.binance_connected ? 'green' : 'gray'} pulse={status?.binance_connected}>
          BINANCE
        </Badge>
        <Badge variant={status?.signal_engine_running ? 'blue' : 'gray'}>
          SIGNALS {status?.signal_engine_paused ? '⏸' : ''}
        </Badge>
        <Badge variant={status?.execution_simulator_running ? 'yellow' : 'gray'}>
          SIM
        </Badge>
        <Badge variant={status?.ai_running ? 'purple' : 'gray'} pulse={status?.ai_running}>
          AI
        </Badge>
        <Badge
          variant={status?.mt5_connected ? (status.mt5_enabled ? 'yellow' : 'green') : 'gray'}
          pulse={status?.mt5_connected && status.mt5_enabled}
        >
          MT5 {status?.mt5_connected ? (status.mt5_enabled ? 'LIVE' : 'READY') : 'OFF'}
        </Badge>
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Panel tabs */}
      <div className="flex items-center gap-1">
        {(['flow', 'mt5', 'analytics', 'replay'] as const).map(p => (
          <button
            key={p}
            onClick={() => setActivePanel(p)}
            className={`px-2 py-0.5 text-[9px] font-mono uppercase tracking-widest rounded border transition-all ${
              activePanel === p
                ? 'border-accent-blue/60 text-accent-blue bg-accent-blue/10'
                : 'border-bg-border text-text-muted hover:text-text-secondary hover:border-bg-border/80'
            }`}
          >
            {p === 'mt5' ? 'EXNESS' : p}
          </button>
        ))}
      </div>

      {/* Control buttons */}
      <div className="flex items-center gap-1">
        <Btn variant="green" size="xs" onClick={handleStart}>▶ START</Btn>
        <Btn variant="red" size="xs" onClick={handleStop}>■ STOP</Btn>
        <Btn variant="yellow" size="xs" onClick={handlePause}>⏸ PAUSE</Btn>
        <Btn variant="ghost" size="xs" onClick={handleReset}>↺ RESET</Btn>
        <Btn variant="ghost" size="xs" onClick={handleClearTrades}>✕ CLEAR</Btn>
      </div>
    </header>
  )
}
