import { create } from 'zustand'
import type { Trade } from '../types'

interface TradeStore {
  trades: Record<number, Trade>
  autoExecute: boolean
  // Derived — recomputed on every upsert, stable refs between updates
  openTrades: Trade[]
  closedTrades: Trade[]
  totalPnl: number
  winRate: number

  upsertTrade: (trade: Trade) => void
  setAutoExecute: (v: boolean) => void
  reset: () => void
}

function derive(trades: Record<number, Trade>) {
  const all = Object.values(trades)
  const open = all.filter(t => t.status === 'OPEN')
  const closed = all
    .filter(t => t.status === 'CLOSED')
    .sort((a, b) => b.closed_at - a.closed_at)
  const totalPnl = closed.reduce((sum, t) => sum + t.pnl, 0)
  const winRate = closed.length ? closed.filter(t => t.pnl > 0).length / closed.length : 0
  return { openTrades: open, closedTrades: closed, totalPnl, winRate }
}

export const useTradeStore = create<TradeStore>((set) => ({
  trades: {},
  autoExecute: false,
  openTrades: [],
  closedTrades: [],
  totalPnl: 0,
  winRate: 0,

  upsertTrade(trade) {
    set(s => {
      const trades = { ...s.trades, [trade.id]: trade }
      return { trades, ...derive(trades) }
    })
  },

  setAutoExecute(v) {
    set({ autoExecute: v })
  },

  reset() {
    set({ trades: {}, openTrades: [], closedTrades: [], totalPnl: 0, winRate: 0 })
  },
}))
