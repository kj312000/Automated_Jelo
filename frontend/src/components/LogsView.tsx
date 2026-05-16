import { useEffect, useState } from 'react'

const PAGE = 20

const cell: React.CSSProperties = {
  padding: '2px 8px', fontSize: 10, whiteSpace: 'nowrap',
  overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 180,
  borderBottom: '1px solid #161616',
}
const hcell: React.CSSProperties = {
  ...cell, color: '#3a3a3a', fontSize: 9, fontWeight: 700,
  letterSpacing: 0.5, borderBottom: '1px solid #2a2a2a',
  background: '#0d0d0d', position: 'sticky', top: 0,
}

function pColor(v: number) { return v > 0 ? '#3d3' : v < 0 ? '#d33' : '#666' }
function bColor(b: string) {
  return b === 'PAUSE' ? '#f55' : b === 'LONG' ? '#3d3' : b === 'SHORT' ? '#d33' : '#fa0'
}
function qColor(q: number) { return q >= 70 ? '#3d3' : q >= 50 ? '#fa0' : '#d33' }
function fmtTs(s: string) {
  if (!s) return '—'
  try { return new Date(s + 'Z').toLocaleTimeString() } catch { return s.slice(11, 19) }
}

// ── Signals table ──────────────────────────────────────────────────────────────
function SignalsTable({ rows }: { rows: any[] }) {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            {['#','time','type','conf','quality','phase','regime','session','bias','exec','skip reason'].map(h => (
              <th key={h} style={hcell}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r: any) => (
            <tr key={r.id} style={{ background: r.executed ? '#0a100a' : r.skipped ? '#100a0a' : '#0d0d0d' }}>
              <td style={cell}><span style={{ color: '#555' }}>{r.id}</span></td>
              <td style={cell}><span style={{ color: '#555' }}>{fmtTs(r.created_at)}</span></td>
              <td style={cell}>
                <span style={{ color: r.signal_type?.includes('LONG') || r.signal_type === 'ABSORPTION_REVERSAL' ? '#3d3' : '#d33', fontWeight: 700 }}>
                  {r.signal_type?.replace('_', ' ')}
                </span>
              </td>
              <td style={cell}><span style={{ color: '#aaa' }}>{((r.confidence ?? 0) * 100).toFixed(0)}%</span></td>
              <td style={cell}><span style={{ color: qColor(r.quality_score ?? 0) }}>{r.quality_score ?? '—'}</span></td>
              <td style={cell}><span style={{ color: '#888' }}>{r.breakout_phase ?? '—'}</span></td>
              <td style={cell}><span style={{ color: '#7af' }}>{r.regime ?? '—'}</span></td>
              <td style={cell}><span style={{ color: '#a7f' }}>{r.session ?? '—'}</span></td>
              <td style={cell}>
                {r.ai_bias && <span style={{ color: bColor(r.ai_bias), fontWeight: 700 }}>{r.ai_bias}</span>}
              </td>
              <td style={cell}>
                <span style={{ color: r.executed ? '#3d3' : '#555' }}>
                  {r.executed ? '✓' : '—'}
                </span>
              </td>
              <td style={{ ...cell, maxWidth: 240, color: '#555' }}>{r.skip_reason ?? ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Trades table ───────────────────────────────────────────────────────────────
function TradesTable({ rows }: { rows: any[] }) {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            {['#','ticket','time','side','entry','exit','pnl','dur','reason','quality','phase','regime','session','SL','TP'].map(h => (
              <th key={h} style={hcell}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r: any) => (
            <tr key={r.id} style={{ background: (r.pnl ?? 0) > 0 ? '#0a100a' : (r.pnl ?? 0) < 0 ? '#100a0a' : '#0d0d0d' }}>
              <td style={cell}><span style={{ color: '#555' }}>{r.id}</span></td>
              <td style={cell}><span style={{ color: '#444' }}>{r.mt5_ticket ?? '—'}</span></td>
              <td style={cell}><span style={{ color: '#555' }}>{fmtTs(r.opened_at)}</span></td>
              <td style={cell}>
                <span style={{ color: r.side === 'BUY' ? '#3d3' : '#d33', fontWeight: 700 }}>{r.side}</span>
              </td>
              <td style={cell}><span style={{ color: '#aaa' }}>${r.entry_price?.toFixed(2)}</span></td>
              <td style={cell}>
                <span style={{ color: '#888' }}>{r.exit_price ? `$${r.exit_price.toFixed(2)}` : 'OPEN'}</span>
              </td>
              <td style={cell}>
                <span style={{ color: pColor(r.pnl ?? 0), fontWeight: 600 }}>
                  {r.pnl != null ? `${r.pnl >= 0 ? '+' : ''}$${r.pnl.toFixed(2)}` : '—'}
                </span>
              </td>
              <td style={cell}>
                <span style={{ color: '#666' }}>
                  {r.duration_seconds != null ? `${r.duration_seconds.toFixed(0)}s` : '—'}
                </span>
              </td>
              <td style={cell}><span style={{ color: '#777' }}>{r.exit_reason ?? 'OPEN'}</span></td>
              <td style={cell}><span style={{ color: qColor(r.signal_quality_score ?? 0) }}>{r.signal_quality_score ?? '—'}</span></td>
              <td style={cell}><span style={{ color: '#888' }}>{r.signal_breakout_phase ?? '—'}</span></td>
              <td style={cell}><span style={{ color: '#7af' }}>{r.regime ?? '—'}</span></td>
              <td style={cell}><span style={{ color: '#a7f' }}>{r.session ?? '—'}</span></td>
              <td style={cell}><span style={{ color: '#d44' }}>{r.adaptive_sl ?? '—'}</span></td>
              <td style={cell}><span style={{ color: '#3a3' }}>{r.adaptive_tp ?? '—'}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Pagination bar ─────────────────────────────────────────────────────────────
function Pager({ page, total, onPrev, onNext }: { page: number; total: number; onPrev: () => void; onNext: () => void }) {
  const pages = Math.max(1, Math.ceil(total / PAGE))
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '6px 10px', borderTop: '1px solid #1e1e1e', flexShrink: 0, fontSize: 10 }}>
      <button onClick={onPrev} disabled={page === 0}
        style={{ background: '#1a1a1a', color: page === 0 ? '#333' : '#888', border: '1px solid #2a2a2a', borderRadius: 3, padding: '2px 8px', cursor: page === 0 ? 'not-allowed' : 'pointer', fontFamily: 'inherit', fontSize: 10 }}>
        ◀ prev
      </button>
      <span style={{ color: '#555' }}>page {page + 1} / {pages}</span>
      <button onClick={onNext} disabled={page >= pages - 1}
        style={{ background: '#1a1a1a', color: page >= pages - 1 ? '#333' : '#888', border: '1px solid #2a2a2a', borderRadius: 3, padding: '2px 8px', cursor: page >= pages - 1 ? 'not-allowed' : 'pointer', fontFamily: 'inherit', fontSize: 10 }}>
        next ▶
      </button>
      <span style={{ color: '#3a3a3a', marginLeft: 8 }}>{total} rows</span>
    </div>
  )
}

// ── Main ───────────────────────────────────────────────────────────────────────
export function LogsView() {
  const [activeTab, setTab]       = useState<'signals' | 'trades'>('signals')
  const [signals, setSignals]     = useState<any[]>([])
  const [trades, setTrades]       = useState<any[]>([])
  const [sigPage, setSigPage]     = useState(0)
  const [tradePage, setTradePage] = useState(0)
  const [loading, setLoading]     = useState(false)

  async function load() {
    setLoading(true)
    try {
      const [s, t] = await Promise.all([
        fetch('/api/logs/signals?limit=500').then(r => r.json()),
        fetch('/api/logs/trades?limit=500').then(r => r.json()),
      ])
      setSignals(Array.isArray(s) ? s : [])
      setTrades(Array.isArray(t) ? t : [])
    } catch {}
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  const sigRows   = signals.slice(sigPage * PAGE, (sigPage + 1) * PAGE)
  const tradeRows = trades.slice(tradePage * PAGE, (tradePage + 1) * PAGE)

  const tabStyle = (active: boolean): React.CSSProperties => ({
    padding: '4px 14px', fontSize: 10, fontWeight: 700,
    background: active ? '#1a1a2a' : 'transparent',
    color: active ? '#7af' : '#555',
    border: 'none', borderBottom: active ? '2px solid #5af' : '2px solid transparent',
    cursor: 'pointer', fontFamily: 'inherit', letterSpacing: 0.5,
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* tab bar */}
      <div style={{ display: 'flex', alignItems: 'center', borderBottom: '1px solid #1e1e1e', flexShrink: 0, background: '#0d0d0d', padding: '0 6px' }}>
        <button style={tabStyle(activeTab === 'signals')} onClick={() => setTab('signals')}>
          SIGNALS {signals.length > 0 && <span style={{ color: '#3a3a3a' }}>({signals.length})</span>}
        </button>
        <button style={tabStyle(activeTab === 'trades')} onClick={() => setTab('trades')}>
          TRADES {trades.length > 0 && <span style={{ color: '#3a3a3a' }}>({trades.length})</span>}
        </button>
        <button
          onClick={load}
          style={{ marginLeft: 'auto', background: 'transparent', color: loading ? '#555' : '#3a5', border: '1px solid #2a2a2a', borderRadius: 3, padding: '2px 8px', cursor: 'pointer', fontFamily: 'inherit', fontSize: 9 }}>
          {loading ? '…' : '↻ refresh'}
        </button>
      </div>

      {/* table area */}
      <div style={{ flex: 1, overflowY: 'auto', scrollbarWidth: 'thin', scrollbarColor: '#2a2a2a #0a0a0a' }}>
        {activeTab === 'signals' && (
          sigRows.length === 0
            ? <div style={{ color: '#333', fontSize: 10, padding: 12 }}>no signals yet</div>
            : <SignalsTable rows={sigRows} />
        )}
        {activeTab === 'trades' && (
          tradeRows.length === 0
            ? <div style={{ color: '#333', fontSize: 10, padding: 12 }}>no trades yet</div>
            : <TradesTable rows={tradeRows} />
        )}
      </div>

      {/* pagination */}
      {activeTab === 'signals' && signals.length > PAGE && (
        <Pager page={sigPage} total={signals.length}
          onPrev={() => setSigPage(p => Math.max(0, p - 1))}
          onNext={() => setSigPage(p => Math.min(Math.ceil(signals.length / PAGE) - 1, p + 1))} />
      )}
      {activeTab === 'trades' && trades.length > PAGE && (
        <Pager page={tradePage} total={trades.length}
          onPrev={() => setTradePage(p => Math.max(0, p - 1))}
          onNext={() => setTradePage(p => Math.min(Math.ceil(trades.length / PAGE) - 1, p + 1))} />
      )}
    </div>
  )
}
