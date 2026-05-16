import { clsx } from 'clsx'

interface BtnProps {
  onClick?: () => void
  children: React.ReactNode
  variant?: 'green' | 'red' | 'blue' | 'yellow' | 'ghost'
  size?: 'xs' | 'sm' | 'md'
  disabled?: boolean
  className?: string
}

const VARIANTS = {
  green: 'bg-accent-green/10 hover:bg-accent-green/20 text-accent-green border-accent-green/30 hover:border-accent-green/60',
  red: 'bg-accent-red/10 hover:bg-accent-red/20 text-accent-red border-accent-red/30 hover:border-accent-red/60',
  blue: 'bg-accent-blue/10 hover:bg-accent-blue/20 text-accent-blue border-accent-blue/30 hover:border-accent-blue/60',
  yellow: 'bg-accent-yellow/10 hover:bg-accent-yellow/20 text-accent-yellow border-accent-yellow/30 hover:border-accent-yellow/60',
  ghost: 'bg-white/5 hover:bg-white/10 text-text-secondary border-bg-border hover:text-text-primary',
}

const SIZES = {
  xs: 'px-2 py-0.5 text-[9px]',
  sm: 'px-2.5 py-1 text-[10px]',
  md: 'px-3 py-1.5 text-xs',
}

export function Btn({ onClick, children, variant = 'ghost', size = 'sm', disabled, className }: BtnProps) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={clsx(
        'font-mono font-semibold uppercase tracking-wider border rounded',
        'transition-all duration-150 cursor-pointer',
        'disabled:opacity-40 disabled:cursor-not-allowed',
        VARIANTS[variant],
        SIZES[size],
        className
      )}
    >
      {children}
    </button>
  )
}
