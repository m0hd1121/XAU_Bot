import React from 'react'
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { cn } from '@/lib/utils'

type Size = 'sm' | 'md' | 'lg'

interface MetricTileProps {
  label: string
  value: string | number
  sub?: string
  change?: number
  prefix?: string
  suffix?: string
  colorize?: boolean
  loading?: boolean
  size?: Size
  icon?: React.ReactNode
  onClick?: () => void
  className?: string
  valueClassName?: string
}

function ChangeIndicator({ change, colorize }: { change: number; colorize: boolean }) {
  if (change === 0) {
    return (
      <span className="flex items-center gap-0.5 text-zinc-500 text-[10px]">
        <Minus className="w-3 h-3" />
        0.00
      </span>
    )
  }
  const positive = change > 0
  const color = colorize
    ? positive
      ? 'text-emerald-400'
      : 'text-red-400'
    : 'text-zinc-400'

  return (
    <span className={cn('flex items-center gap-0.5 text-[10px] font-medium', color)}>
      {positive ? (
        <TrendingUp className="w-3 h-3" />
      ) : (
        <TrendingDown className="w-3 h-3" />
      )}
      {positive ? '+' : ''}
      {change.toFixed(2)}
    </span>
  )
}

const valueSize: Record<Size, string> = {
  sm: 'text-lg',
  md: 'text-2xl',
  lg: 'text-3xl',
}

export default function MetricTile({
  label,
  value,
  sub,
  change,
  prefix,
  suffix,
  colorize = false,
  loading = false,
  size = 'md',
  icon,
  onClick,
  className,
  valueClassName,
}: MetricTileProps) {
  const valueColor =
    colorize && typeof change === 'number'
      ? change > 0
        ? 'text-emerald-400'
        : change < 0
        ? 'text-red-400'
        : 'text-zinc-200'
      : 'text-zinc-100'

  return (
    <div
      onClick={onClick}
      className={cn(
        'bg-zinc-900 border border-zinc-800 rounded-xl p-4 flex flex-col gap-1.5',
        onClick && 'cursor-pointer hover:bg-zinc-800/80 hover:border-zinc-700 transition-colors',
        className,
      )}
    >
      {/* Label row */}
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-zinc-500 truncate">{label}</span>
        {icon && <span className="text-zinc-600 flex-shrink-0">{icon}</span>}
      </div>

      {/* Value */}
      {loading ? (
        <div className="space-y-1.5 mt-1">
          <div className={cn('shimmer rounded', size === 'lg' ? 'h-8' : size === 'md' ? 'h-7' : 'h-5', 'w-3/4')} />
          {change !== undefined && <div className="shimmer h-3 w-1/3 rounded" />}
        </div>
      ) : (
        <>
          <div
            className={cn(
              'font-semibold font-mono leading-tight tracking-tight',
              valueSize[size],
              valueColor,
              valueClassName,
            )}
          >
            {prefix}
            {value}
            {suffix}
          </div>
          {sub && (
            <span className="text-xs text-zinc-500 truncate">{sub}</span>
          )}
          {change !== undefined && (
            <ChangeIndicator change={change} colorize={colorize} />
          )}
        </>
      )}
    </div>
  )
}

export { MetricTile }
