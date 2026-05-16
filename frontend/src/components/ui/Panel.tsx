import { clsx } from 'clsx'

interface PanelProps {
  title?: string
  children: React.ReactNode
  className?: string
  headerRight?: React.ReactNode
  compact?: boolean
}

export function Panel({ title, children, className, headerRight, compact }: PanelProps) {
  return (
    <div className={clsx('bg-bg-panel border border-bg-border rounded-lg flex flex-col', className)}>
      {title && (
        <div className="flex items-center justify-between px-3 py-2 border-b border-bg-border shrink-0">
          <span className="text-[10px] font-mono font-semibold uppercase tracking-widest text-text-muted">
            {title}
          </span>
          {headerRight}
        </div>
      )}
      <div className={clsx('flex-1 overflow-hidden', compact ? 'p-2' : 'p-3')}>
        {children}
      </div>
    </div>
  )
}
