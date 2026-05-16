import { useAIStore } from '../stores/aiStore'
import { aiApi } from '../services/api'
import { Btn } from './ui/Btn'
import { useState } from 'react'

function parseSection(content: string, header: string): string {
  const re = new RegExp(`\\*\\*${header}\\*\\*\\s*([\\s\\S]*?)(?=\\*\\*[A-Z]|$)`, 'i')
  const m = content.match(re)
  return m ? m[1].trim() : ''
}

export function BottomPanel() {
  const latest = useAIStore(s => s.latest)
  const analyses = useAIStore(s => s.analyses)
  const [loading, setLoading] = useState(false)
  const [activeTab, setActiveTab] = useState<'latest' | 'history'>('latest')

  const handleAnalyze = async () => {
    setLoading(true)
    try { await aiApi.analyze() } catch {}
    setLoading(false)
  }

  const content = latest?.content ?? ''
  const marketCondition = parseSection(content, 'MARKET CONDITION')
  const flowAnalysis = parseSection(content, 'FLOW ANALYSIS')
  const signalQuality = parseSection(content, 'SIGNAL QUALITY')
  const tradeReview = parseSection(content, 'ACTIVE TRADE REVIEW')
  const continuationProb = parseSection(content, 'CONTINUATION PROBABILITY')
  const improvements = parseSection(content, 'IMPROVEMENT RECOMMENDATIONS')
  const riskWarnings = parseSection(content, 'RISK WARNINGS')

  return (
    <div className="h-full flex flex-col bg-bg-panel border-t border-bg-border">
      {/* Header */}
      <div className="flex items-center gap-3 px-3 py-1.5 border-b border-bg-border shrink-0">
        <div className="flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full bg-accent-purple animate-pulse" />
          <span className="text-[10px] font-mono font-semibold uppercase tracking-widest text-text-muted">
            AI Analysis Engine
          </span>
          {latest && (
            <span className="text-[9px] font-mono text-text-muted">
              #{latest.analysis_count}
            </span>
          )}
        </div>

        <div className="flex gap-1">
          {(['latest', 'history'] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-2 py-0.5 text-[9px] font-mono rounded border transition-all ${
                activeTab === tab
                  ? 'border-accent-purple/60 text-accent-purple bg-accent-purple/10'
                  : 'border-bg-border text-text-muted'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        <div className="flex-1" />

        <Btn
          variant="blue"
          size="xs"
          onClick={handleAnalyze}
          disabled={loading}
        >
          {loading ? '...' : '⚡ ANALYZE NOW'}
        </Btn>

        {latest && (
          <span className="text-[8px] font-mono text-text-muted">
            {new Date(latest.timestamp * 1000).toLocaleTimeString()}
          </span>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {activeTab === 'latest' ? (
          <LatestView
            marketCondition={marketCondition}
            flowAnalysis={flowAnalysis}
            signalQuality={signalQuality}
            tradeReview={tradeReview}
            continuationProb={continuationProb}
            improvements={improvements}
            riskWarnings={riskWarnings}
            hasContent={!!content}
          />
        ) : (
          <HistoryView analyses={analyses} />
        )}
      </div>
    </div>
  )
}

interface LatestViewProps {
  marketCondition: string
  flowAnalysis: string
  signalQuality: string
  tradeReview: string
  continuationProb: string
  improvements: string
  riskWarnings: string
  hasContent: boolean
}

function LatestView({
  marketCondition, flowAnalysis, signalQuality, tradeReview,
  continuationProb, improvements, riskWarnings, hasContent,
}: LatestViewProps) {
  if (!hasContent) {
    return (
      <div className="flex items-center justify-center h-full text-text-muted text-xs font-mono">
        Waiting for AI analysis... (auto-refreshes every 15s)
      </div>
    )
  }

  return (
    <div className="grid grid-cols-7 gap-0 h-full">
      <AISection title="Market Condition" content={marketCondition} color="blue" cols={1} />
      <AISection title="Flow Analysis" content={flowAnalysis} color="white" cols={2} />
      <AISection title="Signal Quality" content={signalQuality} color="yellow" cols={1} />
      <AISection title="Trade Review" content={tradeReview} color="green" cols={1} />
      <AISection title="Improvements" content={improvements} color="purple" cols={1} />
      <AISection title="Risk Warnings" content={riskWarnings} color="red" cols={1} />
    </div>
  )
}

interface AISectionProps {
  title: string
  content: string
  color: 'blue' | 'white' | 'yellow' | 'green' | 'purple' | 'red'
  cols: number
}

const COLOR_MAP = {
  blue: 'text-accent-blue border-accent-blue/20',
  white: 'text-text-primary border-bg-border',
  yellow: 'text-accent-yellow border-accent-yellow/20',
  green: 'text-accent-green border-accent-green/20',
  purple: 'text-accent-purple border-accent-purple/20',
  red: 'text-accent-red border-accent-red/20',
}

function AISection({ title, content, color, cols }: AISectionProps) {
  return (
    <div
      className={`border-r border-bg-border px-2 py-1.5 overflow-y-auto`}
      style={{ gridColumn: `span ${cols}` }}
    >
      <div className={`text-[8px] font-mono font-bold uppercase tracking-widest mb-1 ${COLOR_MAP[color].split(' ')[0]}`}>
        {title}
      </div>
      <div className="text-[9px] font-mono text-text-secondary leading-relaxed whitespace-pre-wrap">
        {content || '—'}
      </div>
    </div>
  )
}

function HistoryView({ analyses }: { analyses: Array<{ content: string; timestamp: number; analysis_count?: number }> }) {
  return (
    <div className="overflow-y-auto h-full p-2 space-y-2">
      {analyses.length === 0 ? (
        <div className="text-text-muted text-xs font-mono">No analysis history yet</div>
      ) : (
        analyses.map((a, i) => (
          <div key={i} className="border border-bg-border rounded p-2">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[9px] font-mono text-accent-purple">Analysis #{a.analysis_count}</span>
              <span className="text-[8px] font-mono text-text-muted">
                {new Date(a.timestamp * 1000).toLocaleTimeString()}
              </span>
            </div>
            <pre className="text-[9px] font-mono text-text-secondary whitespace-pre-wrap leading-relaxed">
              {a.content}
            </pre>
          </div>
        ))
      )}
    </div>
  )
}
