import { useEffect, useState } from 'react'
import { aiApi, configApi, tradingApi } from '../services/api'

const sect: React.CSSProperties = {
  marginBottom: 16,
}
const sectLabel: React.CSSProperties = {
  color: '#3a3a3a', fontSize: 9, fontWeight: 700, letterSpacing: 1,
  marginBottom: 6, textTransform: 'uppercase',
}
const rowStyle: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 10,
  padding: '3px 0', borderBottom: '1px solid #141414', minHeight: 26,
}
const labelStyle: React.CSSProperties = {
  color: '#555', fontSize: 10, width: 200, flexShrink: 0, textAlign: 'right',
}
const inputStyle: React.CSSProperties = {
  background: '#111', color: '#bbb', border: '1px solid #2a2a2a',
  borderRadius: 3, padding: '2px 6px', fontSize: 10, fontFamily: 'inherit',
  width: 90,
}
const hintStyle: React.CSSProperties = {
  color: '#3a3a3a', fontSize: 9, marginLeft: 4,
}

const FIELD_META: Record<string, { label: string; hint: string; step?: number; min?: number; max?: number }> = {
  min_confidence:              { label: 'Min confidence',        hint: '0.55–0.90', step: 0.01, min: 0.55, max: 0.90 },
  lot_size:                    { label: 'Lot size (BTC)',        hint: '0.01–10',   step: 0.01, min: 0.01 },
  tp_usd_per_lot:              { label: 'TP USD/lot',            hint: 'price move $', step: 1, min: 10 },
  sl_usd_per_lot:              { label: 'SL USD/lot',            hint: 'price move $', step: 1, min: 5 },
  max_hold_seconds:            { label: 'Max hold (sec)',        hint: '60–900',    step: 30, min: 60, max: 900 },
  signal_cooldown_seconds:     { label: 'Signal cooldown (sec)', hint: 'global',    step: 1, min: 0 },
  signal_type_cooldown_seconds:{ label: 'Type cooldown (sec)',   hint: 'per type',  step: 1, min: 0 },
  min_quality_score:           { label: 'Min quality score',     hint: '0–100',     step: 1, min: 0, max: 100 },
  ai_batch_size:               { label: 'AI batch size',         hint: 'signals',   step: 1, min: 1, max: 50 },
  ai_batch_interval:           { label: 'AI batch interval (sec)',hint: 'fallback',  step: 10, min: 10 },
  ai_analysis_interval:        { label: 'AI analysis interval (sec)', hint: 'bg loop', step: 5, min: 10 },
  min_delta_threshold:                 { label: 'Min delta threshold',          hint: 'USD notional', step: 50000, min: 0 },
  min_velocity_threshold:              { label: 'Min velocity threshold',        hint: 'USD/s',        step: 10000, min: 0 },
  max_ai_calls_per_minute:             { label: 'Max AI calls/min',             hint: 'rate limit',   step: 1, min: 1, max: 60 },
  cooldown_between_same_direction_signals: { label: 'Same-direction cooldown (sec)', hint: 'dedup gate', step: 5, min: 0, max: 300 },
  signal_queue_expiry_seconds:         { label: 'Queue expiry (sec)',           hint: 'executor TTL', step: 5, min: 10, max: 300 },
}

function ToggleBtn({ enabled, onToggle, labelOn = 'ON', labelOff = 'OFF' }: {
  enabled: boolean; onToggle: () => void; labelOn?: string; labelOff?: string
}) {
  return (
    <button
      onClick={onToggle}
      style={{
        background: enabled ? '#0f200f' : '#1a1a1a',
        color: enabled ? '#3d3' : '#555',
        border: `1px solid ${enabled ? '#2a4a2a' : '#2a2a2a'}`,
        borderRadius: 3, padding: '2px 14px',
        fontSize: 10, fontFamily: 'inherit', cursor: 'pointer',
        minWidth: 48,
      }}
    >
      {enabled ? labelOn : labelOff}
    </button>
  )
}

export function SettingsView() {
  const [config, setConfig]           = useState<Record<string, number>>({})
  const [pending, setPending]         = useState<Record<string, number>>({})
  const [sigEnabled, setSigEnabled]   = useState(true)
  const [weakEnabled, setWeakEnabled] = useState(true)
  const [killEnabled, setKillEnabled] = useState(true)  // global_trading_enabled
  const [saving, setSaving]           = useState(false)
  const [flash, setFlash]             = useState('')
  const [dirty, setDirty]             = useState(false)

  const msg = (m: string) => { setFlash(m); setTimeout(() => setFlash(''), 3000) }

  async function load() {
    try {
      const [cfg, ai, kill] = await Promise.all([
        configApi.getRuntime().then(r => r.data),
        aiApi.getEnabled().then(r => r.data),
        tradingApi.status().then(r => r.data),
      ])
      setConfig(cfg)
      setPending(cfg)
      setSigEnabled(ai.signals_enabled)
      setWeakEnabled(ai.weakness_enabled)
      setKillEnabled(kill.global_trading_enabled)
    } catch { msg('load failed') }
  }

  useEffect(() => { load() }, [])

  function handleChange(key: string, raw: string) {
    const v = parseFloat(raw)
    if (isNaN(v)) return
    setPending(p => ({ ...p, [key]: v }))
    setDirty(true)
  }

  async function handleSave() {
    setSaving(true)
    try {
      const changed = Object.fromEntries(
        Object.entries(pending).filter(([k, v]) => v !== config[k])
      )
      if (Object.keys(changed).length > 0) {
        await configApi.setRuntime(changed)
        setConfig(pending)
        setDirty(false)
        msg(`saved ${Object.keys(changed).length} change(s)`)
      } else {
        msg('no changes')
      }
    } catch { msg('save failed') }
    setSaving(false)
  }

  async function toggleSignals() {
    const next = !sigEnabled
    try { await aiApi.setSignalsEnabled(next); setSigEnabled(next) }
    catch { msg('toggle failed') }
  }

  async function toggleWeakness() {
    const next = !weakEnabled
    try { await aiApi.setWeaknessEnabled(next); setWeakEnabled(next) }
    catch { msg('toggle failed') }
  }

  async function toggleKillSwitch() {
    try {
      if (killEnabled) {
        await tradingApi.kill()
        setKillEnabled(false)
        msg('Kill switch activated — all trading blocked')
      } else {
        await tradingApi.resume()
        setKillEnabled(true)
        msg('Trading resumed')
      }
    } catch { msg('toggle failed') }
  }

  return (
    <div style={{
      flex: 1, overflowY: 'auto', padding: '14px 20px',
      scrollbarWidth: 'thin', scrollbarColor: '#2a2a2a #0a0a0a',
      maxWidth: 700,
    }}>

      {/* Kill switch */}
      <div style={sect}>
        <div style={sectLabel}>Global Kill Switch</div>
        <div style={{ ...rowStyle, paddingBottom: 8 }}>
          <span style={{ ...labelStyle, color: killEnabled ? '#555' : '#d44' }}>Trading enabled</span>
          <button
            onClick={toggleKillSwitch}
            style={{
              background: killEnabled ? '#0a1a0a' : '#1a0808',
              color: killEnabled ? '#3d3' : '#f44',
              border: `1px solid ${killEnabled ? '#2a4a2a' : '#4a1a1a'}`,
              borderRadius: 3, padding: '3px 18px',
              fontSize: 10, fontFamily: 'inherit', cursor: 'pointer', fontWeight: 700,
            }}
          >
            {killEnabled ? 'TRADING ON' : '⬛ KILL ACTIVE'}
          </button>
          <span style={{ ...hintStyle, color: killEnabled ? '#3a3a3a' : '#d44' }}>
            {killEnabled ? 'click to block all new executions' : 'click to resume trading'}
          </span>
        </div>
      </div>

      {/* AI toggles */}
      <div style={sect}>
        <div style={sectLabel}>AI Engine</div>
        <div style={rowStyle}>
          <span style={labelStyle}>Signal analysis</span>
          <ToggleBtn enabled={sigEnabled} onToggle={toggleSignals} labelOn="ON" labelOff="OFF" />
          <span style={hintStyle}>batch analysis + market loop + bias updates</span>
        </div>
        <div style={rowStyle}>
          <span style={labelStyle}>Weakness monitor</span>
          <ToggleBtn enabled={weakEnabled} onToggle={toggleWeakness} labelOn="ON" labelOff="OFF" />
          <span style={hintStyle}>checks open trades for early exit signals</span>
        </div>
      </div>

      {/* Config fields */}
      <div style={sect}>
        <div style={sectLabel}>Runtime Parameters</div>
        {Object.entries(FIELD_META).map(([key, meta]) => {
          const val = pending[key]
          const changed = val !== config[key]
          return (
            <div key={key} style={rowStyle}>
              <span style={{ ...labelStyle, color: changed ? '#8af' : '#555' }}>
                {meta.label}
              </span>
              <input
                type="number"
                value={val ?? ''}
                onChange={e => handleChange(key, e.target.value)}
                step={meta.step}
                min={meta.min}
                max={meta.max}
                style={{
                  ...inputStyle,
                  borderColor: changed ? '#4a5a8a' : '#2a2a2a',
                  color: changed ? '#cce' : '#bbb',
                }}
              />
              <span style={hintStyle}>{meta.hint}</span>
            </div>
          )
        })}
      </div>

      {/* Save bar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 12 }}>
        <button
          onClick={handleSave}
          disabled={saving || !dirty}
          style={{
            background: dirty ? '#0a1a2a' : '#111',
            color: dirty ? '#5af' : '#333',
            border: `1px solid ${dirty ? '#2a4a6a' : '#222'}`,
            borderRadius: 3, padding: '4px 18px',
            fontSize: 10, fontFamily: 'inherit',
            cursor: saving || !dirty ? 'not-allowed' : 'pointer',
          }}
        >
          {saving ? '…saving' : '✓ Save changes'}
        </button>
        <button
          onClick={load}
          style={{
            background: 'transparent', color: '#444',
            border: '1px solid #2a2a2a', borderRadius: 3,
            padding: '4px 12px', fontSize: 10, fontFamily: 'inherit', cursor: 'pointer',
          }}
        >
          ↻ reload
        </button>
        {flash && <span style={{ color: '#fa0', fontSize: 10 }}>{flash}</span>}
      </div>

      {/* RR summary */}
      {pending.tp_usd_per_lot && pending.sl_usd_per_lot && (
        <div style={{ marginTop: 16, color: '#555', fontSize: 10 }}>
          R:R ={' '}
          <span style={{ color: '#8af' }}>
            {(pending.tp_usd_per_lot / pending.sl_usd_per_lot).toFixed(2)}:1
          </span>
          {' '}(TP=${pending.tp_usd_per_lot} / SL=${pending.sl_usd_per_lot})
        </div>
      )}
    </div>
  )
}
