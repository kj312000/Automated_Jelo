import { useEffect, useRef, useState } from 'react'
import {
  createChart,
  IChartApi,
  ISeriesApi,
  CandlestickData,
  Time,
  ColorType,
} from 'lightweight-charts'
import { useMarketStore } from '../stores/marketStore'
import { Btn } from './ui/Btn'
import type { Signal } from '../types'

const INTERVALS = [1, 5, 15, 60]

export function CenterPanel() {
  const chartRef = useRef<HTMLDivElement>(null)
  const chartApi = useRef<IChartApi | null>(null)
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeRef = useRef<ISeriesApi<'Histogram'> | null>(null)

  const candles = useMarketStore(s => s.candles)
  const currentCandle = useMarketStore(s => s.currentCandle)
  const signals = useMarketStore(s => s.signals)
  const setCandleInterval = useMarketStore(s => s.setCandleInterval)
  const candleInterval = useMarketStore(s => s.candleInterval)

  const [displayInterval, setDisplayInterval] = useState(5)

  // Init chart
  useEffect(() => {
    if (!chartRef.current) return

    const chart = createChart(chartRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#0f0f1a' },
        textColor: '#8888aa',
      },
      grid: {
        vertLines: { color: '#1e1e35' },
        horzLines: { color: '#1e1e35' },
      },
      crosshair: {
        mode: 1,
      },
      rightPriceScale: {
        borderColor: '#1e1e35',
      },
      timeScale: {
        borderColor: '#1e1e35',
        timeVisible: true,
        secondsVisible: true,
      },
      width: chartRef.current.clientWidth,
      height: chartRef.current.clientHeight,
    })

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#00ff88',
      downColor: '#ff3366',
      borderUpColor: '#00ff88',
      borderDownColor: '#ff3366',
      wickUpColor: '#00ff8866',
      wickDownColor: '#ff336666',
    })

    chartApi.current = chart
    candleRef.current = candleSeries

    const observer = new ResizeObserver(() => {
      if (chartRef.current) {
        chart.resize(chartRef.current.clientWidth, chartRef.current.clientHeight)
      }
    })
    observer.observe(chartRef.current)

    return () => {
      observer.disconnect()
      chart.remove()
    }
  }, [])

  // Update candles
  useEffect(() => {
    if (!candleRef.current) return
    const all = [...candles, ...(currentCandle ? [currentCandle] : [])]
    if (!all.length) return

    const data: CandlestickData[] = all.map(c => ({
      time: c.time as Time,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }))

    candleRef.current.setData(data)
  }, [candles, currentCandle])

  const handleIntervalChange = (seconds: number) => {
    setDisplayInterval(seconds)
    setCandleInterval(seconds)
  }

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-bg-border shrink-0 bg-bg-panel">
        <span className="text-[9px] font-mono text-text-muted uppercase tracking-widest">Interval</span>
        <div className="flex gap-1">
          {INTERVALS.map(s => (
            <button
              key={s}
              onClick={() => handleIntervalChange(s)}
              className={`px-2 py-0.5 text-[9px] font-mono rounded border transition-all ${
                displayInterval === s
                  ? 'border-accent-blue/60 text-accent-blue bg-accent-blue/10'
                  : 'border-bg-border text-text-muted hover:text-text-secondary'
              }`}
            >
              {s < 60 ? `${s}s` : `${s / 60}m`}
            </button>
          ))}
        </div>

        <div className="flex-1" />

        {/* Signal legend */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1">
            <div className="w-2 h-2 rounded-full bg-accent-green" />
            <span className="text-[9px] font-mono text-text-muted">Long</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-2 h-2 rounded-full bg-accent-red" />
            <span className="text-[9px] font-mono text-text-muted">Short</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-2 h-2 rounded-full bg-accent-yellow" />
            <span className="text-[9px] font-mono text-text-muted">Sweep</span>
          </div>
        </div>

        {/* Recent signals overlay list */}
        <div className="flex items-center gap-1 max-w-48 overflow-x-auto">
          {signals.slice(0, 3).map(s => (
            <SignalTag key={s.id} signal={s} />
          ))}
        </div>
      </div>

      {/* Chart */}
      <div ref={chartRef} className="flex-1 w-full" />
    </div>
  )
}

function SignalTag({ signal }: { signal: Signal }) {
  const isLong = signal.signal_type.includes('LONG')
  const isSweep = signal.signal_type.includes('SWEEP')
  return (
    <div className={`px-1.5 py-0.5 text-[8px] font-mono rounded border shrink-0 ${
      isSweep
        ? 'border-accent-yellow/30 text-accent-yellow bg-accent-yellow/10'
        : isLong
          ? 'border-accent-green/30 text-accent-green bg-accent-green/10'
          : 'border-accent-red/30 text-accent-red bg-accent-red/10'
    }`}>
      {signal.signal_type.replace(/_/g, ' ').slice(0, 16)} {(signal.confidence * 100).toFixed(0)}%
    </div>
  )
}
