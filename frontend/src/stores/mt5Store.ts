import { create } from 'zustand'
import type { MT5Position, MT5AccountInfo } from '../types'

const CLOSED_EVENTS = new Set(['CLOSED_EXTERNAL','AUTO_TP','MAX_HOLD','MANUAL','MANUAL_ALL','CLOSE_ALL','AI_WEAKNESS','SL_HIT'])

export interface ClosedTrade extends MT5Position {
  exit_reason: string
  closed_at: number
}

interface MT5Store {
  positions: Record<number, MT5Position>
  closedTrades: ClosedTrade[]
  account: MT5AccountInfo | null
  errors: string[]
  totalProfit: number

  upsertPosition: (pos: MT5Position, event: string) => void
  setAccount: (info: MT5AccountInfo) => void
  addError: (err: string) => void
  reset: () => void
}

export const useMT5Store = create<MT5Store>((set) => ({
  positions: {},
  closedTrades: [],
  account: null,
  errors: [],
  totalProfit: 0,

  upsertPosition(pos, event) {
    set(s => {
      let positions = { ...s.positions }
      let closedTrades = s.closedTrades
      if (CLOSED_EVENTS.has(event)) {
        const prev = positions[pos.ticket]
        if (prev) {
          const closed: ClosedTrade = { ...prev, ...pos, exit_reason: event, closed_at: Date.now() / 1000 }
          closedTrades = [closed, ...closedTrades].slice(0, 20)
        }
        delete positions[pos.ticket]
      } else {
        positions[pos.ticket] = pos
      }
      const totalProfit = Object.values(positions).reduce((s, p) => s + p.profit, 0)
      return { positions, closedTrades, totalProfit }
    })
  },

  setAccount(info) {
    set({ account: info })
  },

  addError(err) {
    set(s => ({ errors: [err, ...s.errors].slice(0, 10) }))
  },

  reset() {
    set({ positions: {}, account: null, errors: [], totalProfit: 0 })
  },
}))
