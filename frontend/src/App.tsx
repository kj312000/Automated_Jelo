/**
 * BTC-MST — compact full-screen terminal.
 */
import { useEffect, useRef, useState } from 'react'
import { useWebSocket } from './hooks/useWebSocket'
import { useMarketStore } from './stores/marketStore'
import { useAIStore } from './stores/aiStore'
import { useMT5Store } from './stores/mt5Store'
import { useSystemStore } from './stores/systemStore'
import { flowApi, mt5Api, tradingApi } from './services/api'
import { LogsView } from './components/LogsView'
import { SettingsView } from './components/SettingsView'

// ── helpers ───────────────────────────────────────────────────────────────────

function fmtHold(s: number) {
  const m = Math.floor(s / 60)
  const r = Math.floor(s % 60)
  return m > 0 ? `${m}m${r}s` : `${r}s`
}

function fmtK(n: number) {
  if (Math.abs(n) >= 1000) return `${(n / 1000).toFixed(1)}K`
  return n.toFixed(0)
}

// ── primitives ────────────────────────────────────────────────────────────────

function Dot({ on, color }: { on: boolean; color: string }) {
  return <span style={{ color: on ? color : '#444', userSelect: 'none' }}>●</span>
}

function Sep() {
  return <div style={{ borderTop: '1px solid #1e1e1e', margin: '3px 0' }} />
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ color: '#3a3a3a', fontSize: 9, fontWeight: 700, letterSpacing: 1, marginBottom: 2, userSelect: 'none' }}>
      {children}
    </div>
  )
}

function KV({ k, children, dim }: { k: string; children: React.ReactNode; dim?: boolean }) {
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'baseline', opacity: dim ? 0.45 : 1, lineHeight: 1.6 }}>
      <span style={{ color: '#444', width: 72, flexShrink: 0, fontSize: 9, textAlign: 'right' }}>{k}</span>
      <span style={{ fontSize: 11 }}>{children}</span>
    </div>
  )
}

function Btn({
  children, onClick, active, activeColor = '#2a2a4a', activeText = '#8af',
  dangerColor = '#2a1414', dangerText = '#d44', disabled,
  variant = 'default',
}: {
  children: React.ReactNode
  onClick: () => void
  active?: boolean
  activeColor?: string
  activeText?: string
  dangerColor?: string
  dangerText?: string
  disabled?: boolean
  variant?: 'default' | 'buy' | 'sell' | 'danger' | 'start' | 'stop'
}) {
  const colors: Record<string, [string, string]> = {
    default:  ['#1a1a1a', '#666'],
    buy:      ['#0f2010', '#3a3'],
    sell:     ['#200f0f', '#a33'],
    danger:   ['#2a1010', '#d44'],
    start:    ['#0f200f', '#3d3'],
    stop:     ['#1e1010', '#c33'],
  }
  const [bg, fg] = active ? [activeColor, activeText] : colors[variant]
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        background: disabled ? '#111' : bg,
        color: disabled ? '#333' : fg,
        border: `1px solid ${disabled ? '#222' : (active ? activeText + '55' : '#2a2a2a')}`,
        borderRadius: 3,
        padding: '3px 10px',
        fontSize: 10,
        fontFamily: 'inherit',
        cursor: disabled ? 'not-allowed' : 'pointer',
        lineHeight: 1.5,
        whiteSpace: 'nowrap',
      }}
    >
      {children}
    </button>
  )
}

// ── main ──────────────────────────────────────────────────────────────────────

export function App() {
  useWebSocket()

  const market   = useMarketStore(s => s.market)
  const signals  = useMarketStore(s => s.signals)
  const analyses = useAIStore(s => s.analyses)
  const wsConn   = useSystemStore(s => s.wsConnected)

  const positions    = useMT5Store(s => s.positions)
  const closedTrades = useMT5Store(s => s.closedTrades)
  const account      = useMT5Store(s => s.account)
  const mt5Errors    = useMT5Store(s => s.errors)
  const totalProfit  = useMT5Store(s => s.totalProfit)
  const setAccount   = useMT5Store(s => s.setAccount)

  const [status, setStatus]       = useState<any>(null)
  const [liveEnabled, setLive]    = useState(false)
  const [autoExec, setAutoExec]   = useState(false)
  const [connecting, setConn]     = useState(false)
  const [lotInput, setLot]        = useState('1')
  const [flash, setFlash]         = useState('')
  const [mainTab, setMainTab]     = useState<'terminal' | 'logs' | 'settings'>('terminal')
  const aiScrollRef               = useRef<HTMLDivElement>(null)

  // Status poll
  useEffect(() => {
    const tick = async () => {
      try { const r = await fetch('/api/status'); setStatus(await r.json()) } catch {}
    }
    tick()
    const id = setInterval(tick, 2000)
    return () => clearInterval(id)
  }, [])

  // Account poll when connected
  useEffect(() => {
    if (!status?.mt5_connected) return
    const tick = async () => {
      try {
        const r = await fetch('/api/mt5/account')
        const d = await r.json()
        if (d.ok) setAccount(d)
      } catch {}
    }
    tick()
    const id = setInterval(tick, 5000)
    return () => clearInterval(id)
  }, [status?.mt5_connected])

  // Flash helper
  const msg = (m: string) => { setFlash(m); setTimeout(() => setFlash(''), 4000) }

  // Actions
  const handleStart      = async () => { try { await flowApi.start(); msg('flow started') } catch (e: any) { msg('err: ' + e.message) } }
  const handleStop       = async () => { try { await flowApi.stop();  msg('flow stopped') } catch (e: any) { msg('err: ' + e.message) } }
  const handleConnect    = async () => {
    setConn(true)
    try { await mt5Api.connect(); msg('MT5 connected') }
    catch (e: any) {
      const d = e?.response?.data?.detail ?? e?.message ?? 'connect failed'
      msg('MT5: ' + d)
      useMT5Store.getState().addError(String(d))
    }
    setConn(false)
  }
  const handleDisconnect = async () => { try { await mt5Api.disconnect(); msg('disconnected') } catch {} }
  const handleLive       = async () => { const n = !liveEnabled; try { await mt5Api.enable(n); setLive(n) } catch {} }
  const handleAuto       = async () => { const n = !autoExec;    try { await mt5Api.autoExecute(n); setAutoExec(n) } catch {} }
  const handleBuy        = async () => {
    try { await mt5Api.open('BUY', parseFloat(lotInput)); msg('BUY sent') }
    catch (e: any) { msg('err: ' + (e?.response?.data?.detail ?? e.message)) }
  }
  const handleSell = async () => {
    try { await mt5Api.open('SELL', parseFloat(lotInput)); msg('SELL sent') }
    catch (e: any) { msg('err: ' + (e?.response?.data?.detail ?? e.message)) }
  }
  const handleCloseAll = async () => { try { await mt5Api.closeAll(); msg('all closed') } catch {} }
  const handleCloseOne = async (t: number) => { try { await mt5Api.close(t); msg(`#${t} closed`) } catch {} }
  const handleKillSwitch = async () => {
    try {
      if (globalEnabled) { await tradingApi.kill(); msg('KILL SWITCH — trading disabled') }
      else               { await tradingApi.resume(); msg('Trading resumed') }
    } catch (e: any) { msg('err: ' + e.message) }
  }

  // Derived
  const mt5On   = status?.mt5_connected ?? false
  const bncOn   = status?.binance_connected ?? false
  const aiOn    = status?.ai_running ?? false
  const aiThr   = status?.ai_threshold as number | undefined
  const aiBias  = (status?.ai_bias ?? 'BOTH') as string
  const aiNote  = status?.ai_bias_reason as string | undefined
  const openPos = Object.values(positions)
  const lastSig = signals[0] ?? null
  const vel5    = market?.velocity?.[5] ?? 0
  const net5    = market?.net_delta?.[5] ?? 0
  const RR      = 3.33  // $100 TP / $30 SL

  const pColor = (p: number) => p >= 0 ? '#3a3' : '#a33'
  const sColor = (s: string) => s === 'BUY' ? '#3d3' : '#d33'

  const regime     = (status?.regime  ?? '') as string
  const session    = (status?.session ?? '') as string
  const execHealth = (status?.exec_health ?? '') as string
  const cooldown   = status?.cooldown as { active: boolean; remaining_seconds: number; reason: string } | undefined
  const adaptive   = status?.adaptive as { sl: number; tp: number; rr: number } | undefined
  const tradeable       = status?.tradeable as boolean | undefined
  const execOnline      = (status?.executor_online ?? false) as boolean
  const globalEnabled   = (status?.global_trading_enabled ?? true) as boolean

  const regimeColor = (r: string) =>
    r === 'NORMAL_TREND' ? '#3d3'
    : r === 'HIGH_VOL_EXP' ? '#fa0'
    : r === 'LIQUIDATION'  ? '#f55'
    : r === 'EXHAUSTION'   ? '#a5f'
    : '#555'

  const sessionColor = (s: string) =>
    s === 'LONDON_NY' ? '#3d3'
    : s === 'NY'      ? '#4b4'
    : s === 'LONDON'  ? '#3aa'
    : s === 'ASIAN'   ? '#aa7'
    : s === 'DEAD'    ? '#a33'
    : '#555'

  const healthColor = (h: string) =>
    h === 'EXCELLENT' ? '#3d3'
    : h === 'GOOD'    ? '#3aa'
    : h === 'DEGRADED'? '#fa0'
    : h === 'UNSAFE'  ? '#f44'
    : '#555'

  // ── layout ────────────────────────────────────────────────────────────────
  // Full viewport, flex column, fixed header + controls, scrollable AI feed
  return (
    <div style={{
      width: '100vw', height: '100vh',
      background: '#0a0a0a', color: '#bbb',
      fontFamily: '"Consolas", "Fira Code", "Courier New", monospace',
      fontSize: 11, display: 'flex', flexDirection: 'column',
      boxSizing: 'border-box', overflow: 'hidden',
    }}>

      {/* ── HEADER BAR ─────────────────────────────────────────────────────── */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '6px 14px', borderBottom: '1px solid #1e1e1e',
        flexShrink: 0, background: '#0d0d0d',
      }}>
        <span style={{ color: '#7af', fontWeight: 700, fontSize: 13, letterSpacing: 1 }}>BTC-MST</span>
        {/* main tab switcher */}
        {(['terminal', 'logs', 'settings'] as const).map(t => (
          <button key={t} onClick={() => setMainTab(t)} style={{
            background: mainTab === t ? '#1a1a2a' : 'transparent',
            color: mainTab === t ? '#7af' : '#444',
            border: 'none', borderBottom: mainTab === t ? '2px solid #5af' : '2px solid transparent',
            padding: '2px 10px', cursor: 'pointer', fontFamily: 'inherit',
            fontSize: 10, fontWeight: 700, letterSpacing: 0.5, textTransform: 'uppercase',
          }}>{t}</button>
        ))}
        {market && (
          <span style={{ color: '#eee', fontWeight: 600, fontSize: 14 }}>
            ${market.price.toFixed(2)}
          </span>
        )}
        {market && (
          <span style={{ color: vel5 >= 0 ? '#3a3' : '#a33', fontSize: 10 }}>
            {vel5 >= 0 ? '▲' : '▼'} {fmtK(Math.abs(vel5))}/s
          </span>
        )}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 10, alignItems: 'center', fontSize: 10 }}>
          <span><Dot on={wsConn} color="#3a3" /> WS</span>
          <span><Dot on={bncOn} color="#3a3" /> BNC</span>
          <span><Dot on={mt5On} color="#5af" /> MT5</span>
          <span>
            <Dot on={aiOn} color="#a5f" /> AI
            {aiThr != null ? ` thr=${aiThr.toFixed(2)}` : ''}
            {aiOn && (
              <>
                <span style={{ color: status?.ai_signals_enabled ? '#a5f' : '#333', marginLeft: 4, fontSize: 9 }}>SIG</span>
                <span style={{ color: status?.ai_weakness_enabled ? '#a5f' : '#333', marginLeft: 3, fontSize: 9 }}>WEK</span>
              </>
            )}
          </span>
          {aiOn && (
            <span style={{
              color: aiBias === 'PAUSE' ? '#f55'
                   : aiBias === 'LONG'  ? '#3d3'
                   : aiBias === 'SHORT' ? '#d33'
                   : '#fa0',
              fontWeight: 700,
              background: '#1a1a1a',
              padding: '0 5px',
              borderRadius: 2,
            }}>
              {aiBias}
            </span>
          )}
          <span style={{ color: '#555' }}>R:R {adaptive ? adaptive.rr.toFixed(1) : RR}:1</span>
          {regime && (
            <span style={{ color: regimeColor(regime), fontSize: 10, fontWeight: 600 }}>
              {regime.replace('_', ' ')}
            </span>
          )}
          {session && (
            <span style={{ color: sessionColor(session), fontSize: 10 }}>
              {session.replace('_', '+')}
            </span>
          )}
          {execHealth && (
            <span style={{ color: healthColor(execHealth), fontSize: 10 }}>
              {execHealth}
            </span>
          )}
          {cooldown?.active && (
            <span style={{
              color: '#f44', fontWeight: 700, fontSize: 10,
              background: '#1a0808', padding: '0 5px', borderRadius: 2,
            }}>
              COOLDOWN {cooldown.remaining_seconds.toFixed(0)}s
            </span>
          )}
          {tradeable === false && !cooldown?.active && regime && (
            <span style={{ color: '#a33', fontSize: 10 }}>NO-TRADE</span>
          )}
          {mt5On && (
            <>
              <span style={{ color: liveEnabled ? '#fa0' : '#555' }}>LIVE {liveEnabled ? 'ON' : 'OFF'}</span>
              <span style={{ color: autoExec ? '#a5f' : '#555' }}>AUTO {autoExec ? 'ON' : 'OFF'}</span>
            </>
          )}
          <span style={{ color: execOnline ? '#3d3' : '#555', fontSize: 10 }}>
            <Dot on={execOnline} color="#3d3" /> EXEC
          </span>
          {!globalEnabled && (
            <span style={{
              color: '#f44', fontWeight: 700, fontSize: 10,
              background: '#1a0808', padding: '0 5px', borderRadius: 2,
              border: '1px solid #4a1010',
            }}>
              KILL ACTIVE
            </span>
          )}
        </div>
      </div>

      {/* ── LOGS TAB ──────────────────────────────────────────────────────────── */}
      {mainTab === 'logs' && (
        <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <LogsView />
        </div>
      )}

      {/* ── SETTINGS TAB ──────────────────────────────────────────────────────── */}
      {mainTab === 'settings' && (
        <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <SettingsView />
        </div>
      )}

      {/* ── MAIN BODY (scrollable columns) ─────────────────────────────────── */}
      <div style={{ flex: 1, overflow: 'hidden', display: mainTab === 'terminal' ? 'flex' : 'none' }}>

        {/* ── LEFT COLUMN: market + signal + positions + closed ─────────────── */}
        <div style={{
          width: 340, flexShrink: 0, display: 'flex', flexDirection: 'column',
          borderRight: '1px solid #1e1e1e', padding: '8px 10px', overflow: 'hidden',
        }}>

          {/* Market microstructure */}
          {market && (
            <>
              <SectionLabel>MARKET</SectionLabel>
              <KV k="CVD">
                <span style={{ color: market.cvd >= 0 ? '#3a3' : '#a33' }}>{fmtK(market.cvd)}</span>
                <span style={{ color: '#444', marginLeft: 8 }}>imb={market.imbalance?.toFixed(2)}</span>
                <span style={{ color: '#444', marginLeft: 8 }}>agg={market.aggression_score?.toFixed(2)}</span>
              </KV>
              <KV k="velocity">
                <span style={{ color: vel5 >= 0 ? '#3a3' : '#a33' }}>{fmtK(vel5)}/s</span>
                <span style={{ color: '#444', marginLeft: 8 }}>net={fmtK(net5)}</span>
                {market.sweep_detected && <span style={{ color: '#fa0', marginLeft: 8 }}>SWEEP</span>}
                {market.absorption_detected && <span style={{ color: '#a5f', marginLeft: 8 }}>ABS</span>}
              </KV>
              <KV k="spread">${market.spread?.toFixed(4)}</KV>
              <Sep />
            </>
          )}

          {/* Last signal */}
          <SectionLabel>LAST SIGNAL</SectionLabel>
          {lastSig ? (
            <>
              <KV k="type">
                <span style={{ color: (lastSig as any).signal_type?.includes('LONG') || (lastSig as any).signal_type === 'ABSORPTION_REVERSAL' ? '#3d3' : '#d33', fontWeight: 700 }}>
                  {(lastSig as any).signal_type}
                </span>
                <span style={{ color: '#666', marginLeft: 8 }}>{(((lastSig as any).confidence ?? 0) * 100).toFixed(0)}%</span>
              </KV>
              <KV k="AI bias">
                <span style={{
                  color: aiBias === 'PAUSE' ? '#f55'
                       : aiBias === 'LONG'  ? '#3d3'
                       : aiBias === 'SHORT' ? '#d33'
                       : '#fa0',
                  fontWeight: 700,
                }}>
                  {aiBias}
                </span>
                {aiNote && (
                  <span style={{ color: '#555', marginLeft: 8, fontSize: 10 }}>{aiNote.slice(0, 55)}</span>
                )}
              </KV>
              {(lastSig as any).quality_score != null && (
                <KV k="quality">
                  <span style={{
                    color: (lastSig as any).quality_score >= 70 ? '#3d3'
                         : (lastSig as any).quality_score >= 55 ? '#fa0'
                         : '#a33',
                    fontWeight: 600,
                  }}>
                    {(lastSig as any).quality_score}/100
                  </span>
                  {(lastSig as any).breakout_phase && (
                    <span style={{ color: '#555', marginLeft: 8 }}>{(lastSig as any).breakout_phase}</span>
                  )}
                </KV>
              )}
              <KV k="reason" dim>{(lastSig as any).trigger_reason?.slice(0, 60)}</KV>
            </>
          ) : (
            <div style={{ color: '#333', fontSize: 10, padding: '2px 0' }}>— waiting —</div>
          )}

          <Sep />

          {/* Open positions */}
          <SectionLabel>OPEN POSITIONS ({openPos.length}){openPos.length > 0 && (
            <span style={{ color: pColor(totalProfit), marginLeft: 8 }}>
              {totalProfit >= 0 ? '+' : ''}${totalProfit.toFixed(2)}
            </span>
          )}</SectionLabel>
          <div style={{ overflowY: 'auto', maxHeight: 150 }}>
            {openPos.length === 0 ? (
              <div style={{ color: '#333', fontSize: 10 }}>— none —</div>
            ) : openPos.map(pos => (
              <div key={pos.ticket} style={{
                display: 'flex', gap: 6, alignItems: 'center', fontSize: 10,
                background: '#111', borderRadius: 3, padding: '3px 6px', marginBottom: 2,
              }}>
                <span style={{ color: sColor(pos.side), fontWeight: 700, width: 32 }}>{pos.side}</span>
                <span style={{ color: '#999' }}>${pos.entry_price.toFixed(2)}</span>
                <span style={{ color: '#3a3a3a' }}>→</span>
                <span>${pos.current_price.toFixed(2)}</span>
                <span style={{ color: pColor(pos.profit), fontWeight: 600 }}>
                  {pos.profit >= 0 ? '+' : ''}${pos.profit.toFixed(2)}
                </span>
                <span style={{ color: '#555' }}>{fmtHold(pos.hold_seconds)}</span>
                <span style={{ color: '#3a3a3a', fontSize: 9, marginLeft: 'auto' }}>
                  SL={pos.sl?.toFixed(0)} TP={pos.tp?.toFixed(0)}
                </span>
                <button
                  onClick={() => handleCloseOne(pos.ticket)}
                  style={{
                    background: '#1a0808', color: '#c33', border: '1px solid #3a1010',
                    borderRadius: 2, padding: '0 5px', cursor: 'pointer', fontSize: 9, lineHeight: 1.6,
                  }}>✕</button>
              </div>
            ))}
          </div>

          <Sep />

          {/* Closed trades */}
          <SectionLabel>RECENT CLOSED ({closedTrades.length})</SectionLabel>
          <div style={{ overflowY: 'auto', flex: 1 }}>
            {closedTrades.length === 0 ? (
              <div style={{ color: '#333', fontSize: 10 }}>— none this session —</div>
            ) : closedTrades.map((t, i) => (
              <div key={i} style={{
                display: 'flex', gap: 6, fontSize: 10, marginBottom: 1,
                padding: '1px 0', borderBottom: '1px solid #141414',
              }}>
                <span style={{ color: sColor(t.side), width: 32 }}>{t.side}</span>
                <span style={{ color: '#777' }}>${t.entry_price.toFixed(2)}</span>
                <span style={{ color: '#555', fontSize: 9 }}>→ ${t.current_price?.toFixed(2)}</span>
                <span style={{ color: pColor(t.profit), fontWeight: 600 }}>
                  {t.profit >= 0 ? '+' : ''}${t.profit.toFixed(2)}
                </span>
                <span style={{ color: '#555' }}>{fmtHold(t.hold_seconds)}</span>
                <span style={{ color: '#444', fontSize: 9, marginLeft: 'auto' }}>{t.exit_reason}</span>
              </div>
            ))}
          </div>
        </div>

        {/* ── RIGHT COLUMN: AI feed (scrollable) + account + errors ─────────── */}
        <div style={{
          flex: 1, display: 'flex', flexDirection: 'column',
          padding: '8px 12px', overflow: 'hidden',
        }}>

          {/* AI feed — scrollable, takes all remaining height */}
          <SectionLabel>AI FEED</SectionLabel>
          <div
            ref={aiScrollRef}
            style={{
              flex: 1, overflowY: 'auto', paddingRight: 4,
              scrollbarWidth: 'thin',
              scrollbarColor: '#2a2a2a #0a0a0a',
            }}
          >
            {analyses.length === 0 ? (
              <div style={{ color: '#333', fontSize: 10 }}>waiting for AI analysis…</div>
            ) : analyses.map((a, i) => (
              <div key={i} style={{
                marginBottom: 8, paddingBottom: 6,
                borderBottom: '1px solid #181818',
              }}>
                <div style={{ display: 'flex', gap: 8, marginBottom: 2, flexWrap: 'wrap' }}>
                  <span style={{ color: '#5af', fontSize: 9, fontWeight: 700 }}>
                    {a.analysis_type ?? 'AI'}
                  </span>
                  {a.bias && (
                    <span style={{
                      fontSize: 9, fontWeight: 700,
                      color: a.bias === 'PAUSE' ? '#f55'
                           : a.bias === 'LONG'  ? '#3d3'
                           : a.bias === 'SHORT' ? '#d33'
                           : '#fa0',
                    }}>{a.bias}</span>
                  )}
                  {a.threshold != null && (
                    <span style={{ color: '#a5f', fontSize: 9 }}>thr={a.threshold.toFixed(2)}</span>
                  )}
                  {a.rr_ratio != null && (
                    <span style={{ color: '#888', fontSize: 9 }}>R:R={a.rr_ratio.toFixed(2)}</span>
                  )}
                  {a.signals_reviewed != null && (
                    <span style={{ color: '#555', fontSize: 9 }}>{a.signals_reviewed} sigs</span>
                  )}
                  <span style={{ color: '#333', fontSize: 9, marginLeft: 'auto' }}>
                    {new Date(a.timestamp * 1000).toLocaleTimeString()}
                  </span>
                </div>
                {a.content.split('\n').filter(Boolean).map((line: string, j: number) => {
                  const isRegime    = line.startsWith('REGIME:')
                  const isBias      = line.startsWith('BIAS:')
                  const isThreshold = line.startsWith('THRESHOLD:')
                  const isRR        = line.startsWith('RR:') || line.startsWith('RR_VERDICT:')
                  const isNote      = line.startsWith('Note:') || line.startsWith('Analysis:')
                  return (
                    <div key={j} style={{
                      fontSize: 10,
                      color: isRegime    ? '#fa0'
                           : isBias      ? '#5af'
                           : isThreshold ? '#a5f'
                           : isRR        ? '#3af'
                           : isNote      ? '#aaa'
                           : '#777',
                      paddingLeft: 8,
                      lineHeight: 1.6,
                    }}>
                      {line}
                    </div>
                  )
                })}
              </div>
            ))}
          </div>

          <Sep />

          {/* Account summary */}
          {account && (
            <>
              <SectionLabel>ACCOUNT #{account.login}</SectionLabel>
              <div style={{ display: 'flex', gap: 16, fontSize: 10, flexWrap: 'wrap' }}>
                <span>bal=<span style={{ color: '#ccc' }}>${account.balance.toFixed(2)}</span></span>
                <span>eq=<span style={{ color: account.equity >= account.balance ? '#3a3' : '#a33' }}>${account.equity.toFixed(2)}</span></span>
                <span>free=<span style={{ color: '#888' }}>${account.margin_free.toFixed(2)}</span></span>
                <span>P&L=<span style={{ color: pColor(account.profit) }}>{account.profit >= 0 ? '+' : ''}${account.profit.toFixed(2)}</span></span>
                <span style={{ color: '#555' }}>lev=1:{account.leverage}</span>
                <span style={{ color: '#555' }}>{account.server?.slice(0, 16)}</span>
              </div>
              <Sep />
            </>
          )}

          {/* Errors */}
          {mt5Errors.length > 0 && (
            <>
              {mt5Errors.slice(0, 4).map((e, i) => (
                <div key={i} style={{ color: '#c44', fontSize: 10, marginBottom: 1 }}>⚠ {e}</div>
              ))}
              {mt5Errors[0]?.includes('AutoTrading') && (
                <div style={{
                  background: '#1a0a0a', border: '1px solid #4a1a1a', borderRadius: 3,
                  padding: '4px 8px', marginTop: 4, fontSize: 10, color: '#fa0', lineHeight: 1.7,
                }}>
                  FIX: In MT5 terminal → toolbar → click <strong>"Algo Trading"</strong> button to enable AutoTrading.
                  <br />Then retry your trade.
                </div>
              )}
              <Sep />
            </>
          )}

          {/* Flash */}
          {flash && (
            <div style={{ color: '#fa0', fontSize: 10, marginBottom: 4 }}>» {flash}</div>
          )}
        </div>
      </div>

      {/* ── CONTROLS BAR — terminal only ──────────────────────────────────── */}
      {mainTab === 'terminal' && <div style={{
        borderTop: '1px solid #1e1e1e', padding: '6px 14px',
        display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap',
        flexShrink: 0, background: '#0d0d0d',
      }}>
        <Btn onClick={handleStart} variant="start">▶ START</Btn>
        <Btn onClick={handleStop} variant="stop">■ STOP</Btn>

        <div style={{ width: 1, height: 18, background: '#2a2a2a', margin: '0 2px' }} />

        {!mt5On ? (
          <Btn onClick={handleConnect} disabled={connecting} variant="default" activeColor="#0f102a" activeText="#7af">
            {connecting ? '…' : '⚡ CONNECT MT5'}
          </Btn>
        ) : (
          <Btn onClick={handleDisconnect} variant="default">DISCONNECT</Btn>
        )}

        {mt5On && (
          <>
            <Btn onClick={handleLive} active={liveEnabled} activeColor="#1a1400" activeText="#fa0">
              LIVE {liveEnabled ? 'ON' : 'OFF'}
            </Btn>
            <Btn onClick={handleAuto} active={autoExec} activeColor="#120a22" activeText="#a5f">
              AUTO {autoExec ? 'ON' : 'OFF'}
            </Btn>
          </>
        )}

        <div style={{ width: 1, height: 18, background: '#2a2a2a', margin: '0 2px' }} />

        <input
          type="number"
          value={lotInput}
          onChange={e => setLot(e.target.value)}
          style={{
            width: 52, background: '#111', color: '#bbb',
            border: '1px solid #2a2a2a', borderRadius: 3,
            padding: '3px 5px', fontSize: 10, fontFamily: 'inherit',
          }}
          step="0.1" min="0.01"
        />
        <span style={{ fontSize: 9, color: '#444' }}>lots</span>

        <Btn onClick={handleBuy} disabled={!mt5On || !liveEnabled} variant="buy">▲ BUY</Btn>
        <Btn onClick={handleSell} disabled={!mt5On || !liveEnabled} variant="sell">▼ SELL</Btn>

        {openPos.length > 0 && (
          <Btn onClick={handleCloseAll} variant="danger">CLOSE ALL ({openPos.length})</Btn>
        )}

        <div style={{ width: 1, height: 18, background: '#2a2a2a', margin: '0 2px' }} />

        {/* Kill switch — always visible, prominent */}
        <Btn
          onClick={handleKillSwitch}
          variant={globalEnabled ? 'danger' : 'start'}
          active={!globalEnabled}
          activeColor="#0f200f"
          activeText="#3d3"
        >
          {globalEnabled ? '⬛ KILL' : '▶ RESUME'}
        </Btn>

        {liveEnabled && (
          <span style={{ color: '#fa0', fontSize: 9, marginLeft: 8 }}>
            ⚠ LIVE — 1 BTC lot ·{' '}
            TP=${adaptive?.tp ?? 100} SL=${adaptive?.sl ?? 30} · R:R={(adaptive?.rr ?? RR).toFixed(1)}:1{' '}
            · {regime || 'NORMAL_TREND'} · max 5min hold
          </span>
        )}
      </div>}
    </div>
  )
}
