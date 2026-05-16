import { create } from 'zustand'
import type { MarketState, Signal, CandleData } from '../types'

const MAX_SIGNALS = 100
const MAX_CANDLES = 500
const MAX_PRICE_HISTORY = 300

interface PriceTick {
  time: number
  price: number
  cvd: number
  velocity: number
}

interface MarketStore {
  market: MarketState | null
  signals: Signal[]
  candles: CandleData[]
  priceHistory: PriceTick[]
  currentCandle: CandleData | null
  candleInterval: number // seconds

  updateMarket: (data: MarketState) => void
  addSignal: (signal: Signal) => void
  setCandleInterval: (seconds: number) => void
  reset: () => void
}

function buildCandle(price: number, ts: number): CandleData {
  return { time: ts, open: price, high: price, low: price, close: price }
}

export const useMarketStore = create<MarketStore>((set, get) => ({
  market: null,
  signals: [],
  candles: [],
  priceHistory: [],
  currentCandle: null,
  candleInterval: 5,

  updateMarket(data) {
    const { currentCandle, candles, candleInterval, priceHistory } = get()
    const price = data.price
    const ts = data.timestamp
    const bucketTs = Math.floor(ts / candleInterval) * candleInterval

    let nextCandle = currentCandle
    let nextCandles = candles

    if (!nextCandle) {
      nextCandle = buildCandle(price, bucketTs)
    } else if (bucketTs > nextCandle.time) {
      nextCandles = [...candles, nextCandle].slice(-MAX_CANDLES)
      nextCandle = buildCandle(price, bucketTs)
    } else {
      nextCandle = {
        ...nextCandle,
        high: Math.max(nextCandle.high, price),
        low: Math.min(nextCandle.low, price),
        close: price,
      }
    }

    const tick: PriceTick = {
      time: ts,
      price,
      cvd: data.cvd,
      velocity: data.velocity[5] ?? 0,
    }

    set({
      market: data,
      currentCandle: nextCandle,
      candles: nextCandles,
      priceHistory: [...priceHistory, tick].slice(-MAX_PRICE_HISTORY),
    })
  },

  addSignal(signal) {
    set(s => ({ signals: [signal, ...s.signals].slice(0, MAX_SIGNALS) }))
  },

  setCandleInterval(seconds) {
    set({ candleInterval: seconds, currentCandle: null })
  },

  reset() {
    set({ market: null, signals: [], candles: [], priceHistory: [], currentCandle: null })
  },
}))
