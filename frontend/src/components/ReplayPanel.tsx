import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { replayApi } from '../services/api'
import { Panel } from './ui/Panel'
import { Btn } from './ui/Btn'
import { Metric } from './ui/Metric'

export function ReplayPanel() {
  const [speed, setSpeed] = useState(1.0)

  const { data: status, refetch } = useQuery({
    queryKey: ['replay-status'],
    queryFn: async () => {
      const r = await replayApi.status()
      return r.data
    },
    refetchInterval: 1000,
  })

  const handlePlay = async () => {
    try { await replayApi.play(speed); refetch() } catch {}
  }

  const handlePause = async () => {
    try { await replayApi.pause(); refetch() } catch {}
  }

  const pct = status ? (status.position / Math.max(status.total, 1)) * 100 : 0

  return (
    <div className="h-full flex flex-col items-center justify-start p-6 gap-6">
      <Panel title="Replay Engine" className="w-full max-w-lg">
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-4">
            <Metric label="Position" value={status?.position ?? 0} />
            <Metric label="Total Frames" value={status?.total ?? 0} />
            <Metric
              label="Status"
              value={status?.playing ? 'PLAYING' : 'PAUSED'}
              color={status?.playing ? 'green' : 'yellow'}
            />
          </div>

          {/* Progress bar */}
          <div className="space-y-1">
            <div className="h-2 bg-bg-border rounded-full overflow-hidden">
              <div
                className="h-full bg-accent-blue rounded-full transition-all"
                style={{ width: `${pct}%` }}
              />
            </div>
            <div className="flex justify-between text-[9px] font-mono text-text-muted">
              <span>{status?.position ?? 0}</span>
              <span>{status?.total ?? 0}</span>
            </div>
          </div>

          {/* Speed */}
          <div className="flex items-center gap-3">
            <span className="text-[9px] font-mono text-text-muted">Speed</span>
            {[0.25, 0.5, 1, 2, 5, 10].map(s => (
              <button
                key={s}
                onClick={() => setSpeed(s)}
                className={`px-2 py-0.5 text-[9px] font-mono rounded border transition-all ${
                  speed === s
                    ? 'border-accent-blue/60 text-accent-blue bg-accent-blue/10'
                    : 'border-bg-border text-text-muted'
                }`}
              >
                {s}x
              </button>
            ))}
          </div>

          {/* Controls */}
          <div className="flex gap-2">
            <Btn variant="green" size="sm" onClick={handlePlay} disabled={status?.playing}>
              ▶ PLAY
            </Btn>
            <Btn variant="yellow" size="sm" onClick={handlePause} disabled={!status?.playing}>
              ⏸ PAUSE
            </Btn>
          </div>
        </div>
      </Panel>

      <div className="text-[10px] font-mono text-text-muted text-center max-w-sm">
        Replay loads from stored market snapshots. Load data via backend replay API.
        Adjust speed to analyze microstructure patterns at any pace.
      </div>
    </div>
  )
}
