import { useEffect, useRef } from 'react'
import type { WSMessage } from '../types'
import { useMarketStore } from '../stores/marketStore'
import { useTradeStore } from '../stores/tradeStore'
import { useAIStore } from '../stores/aiStore'
import { useSystemStore } from '../stores/systemStore'
import { useMT5Store } from '../stores/mt5Store'

const WS_URL = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`
const RECONNECT_DELAY = 2000

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)

  // Stable refs to store actions — Zustand actions are stable but using refs
  // guarantees dispatch closure never captures a stale action even if store recreates.
  const updateMarket = useRef(useMarketStore.getState().updateMarket)
  const addSignal = useRef(useMarketStore.getState().addSignal)
  const upsertTrade = useRef(useTradeStore.getState().upsertTrade)
  const addAnalysis = useRef(useAIStore.getState().addAnalysis)
  const setWsConnected = useRef(useSystemStore.getState().setWsConnected)
  const upsertMT5Position = useRef(useMT5Store.getState().upsertPosition)
  const addMT5Error = useRef(useMT5Store.getState().addError)

  function dispatch(msg: WSMessage) {
    switch (msg.type) {
      case 'market_update':
        updateMarket.current(msg)
        break
      case 'signal':
        addSignal.current(msg)
        break
      case 'trade_update':
        upsertTrade.current(msg)
        break
      case 'ai_analysis':
        addAnalysis.current(msg)
        break
      case 'mt5_position':
        upsertMT5Position.current(msg, msg.event)
        break
      case 'mt5_error':
        addMT5Error.current(msg.error)
        break
      default:
        break
    }
  }

  function connect() {
    if (!mountedRef.current) return
    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      setWsConnected.current(true)
    }

    ws.onclose = () => {
      setWsConnected.current(false)
      if (mountedRef.current) {
        reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY)
      }
    }

    ws.onerror = () => {
      ws.close()
    }

    ws.onmessage = (evt) => {
      try {
        const msg: WSMessage = JSON.parse(evt.data)
        dispatch(msg)
      } catch {
        // ignore malformed
      }
    }
  }

  useEffect(() => {
    mountedRef.current = true
    connect()
    return () => {
      mountedRef.current = false
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [])
}
