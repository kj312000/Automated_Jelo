import { clsx } from 'clsx'

interface BadgeProps {
  variant?: 'green' | 'red' | 'blue' | 'yellow' | 'purple' | 'gray'
  children: React.ReactNode
  className?: string
  pulse?: boolean
}

const VARIANTS = {
  green: 'bg-accent-green/10 text-accent-green border-accent-green/30',
  red: 'bg-accent-red/10 text-accent-red border-accent-red/30',
  blue: 'bg-accent-blue/10 text-accent-blue border-accent-blue/30',
  yellow: 'bg-accent-yellow/10 text-accent-yellow border-accent-yellow/30',
  purple: 'bg-accent-purple/10 text-accent-purple border-accent-purple/30',
  gray: 'bg-white/5 text-text-secondary border-bg-border',
}

export function Badge({ variant = 'gray', children, className, pulse }: BadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-mono font-semibold',
        'rounded border uppercase tracking-wider',
        VARIANTS[variant],
        className
      )}
    >
      {pulse && (
        <span className={clsx('w-1.5 h-1.5 rounded-full animate-pulse', {
          'bg-accent-green': variant === 'green',
          'bg-accent-red': variant === 'red',
          'bg-accent-blue': variant === 'blue',
          'bg-accent-yellow': variant === 'yellow',
        })} />
      )}
      {children}
    </span>
  )
}
