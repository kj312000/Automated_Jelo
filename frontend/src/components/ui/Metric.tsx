import { clsx } from 'clsx'

interface MetricProps {
  label: string
  value: string | number
  sub?: string
  color?: 'green' | 'red' | 'blue' | 'yellow' | 'white' | 'muted'
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

const COLORS = {
  green: 'text-accent-green',
  red: 'text-accent-red',
  blue: 'text-accent-blue',
  yellow: 'text-accent-yellow',
  white: 'text-text-primary',
  muted: 'text-text-secondary',
}

const SIZES = {
  sm: 'text-sm',
  md: 'text-base',
  lg: 'text-xl',
}

export function Metric({ label, value, sub, color = 'white', size = 'md', className }: MetricProps) {
  return (
    <div className={clsx('flex flex-col gap-0.5', className)}>
      <span className="text-[10px] font-mono text-text-muted uppercase tracking-widest">{label}</span>
      <span className={clsx('font-mono font-semibold leading-none', COLORS[color], SIZES[size])}>
        {value}
      </span>
      {sub && <span className="text-[9px] font-mono text-text-muted">{sub}</span>}
    </div>
  )
}
