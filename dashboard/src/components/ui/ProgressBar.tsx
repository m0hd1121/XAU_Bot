import React from 'react'
import { cn } from '@/lib/utils'

type ProgressColor = 'amber' | 'emerald' | 'red' | 'sky' | 'auto'
type ProgressSize = 'sm' | 'md' | 'lg'

interface ProgressBarProps {
  value: number
  max?: number
  label?: string
  showValue?: boolean
  color?: ProgressColor
  size?: ProgressSize
  animated?: boolean
  className?: string
}

function resolveColor(color: ProgressColor, pct: number): string {
  if (color !== 'auto') {
    const map: Record<Exclude<ProgressColor, 'auto'>, string> = {
      amber: 'bg-amber-500',
      emerald: 'bg-emerald-500',
      red: 'bg-red-500',
      sky: 'bg-sky-500',
    }
    return map[color]
  }

  // Auto: green → amber → red based on percentage
  if (pct >= 66) return 'bg-emerald-500'
  if (pct >= 33) return 'bg-amber-500'
  return 'bg-red-500'
}

const sizeClasses: Record<ProgressSize, string> = {
  sm: 'h-1',
  md: 'h-2',
  lg: 'h-3',
}

export default function ProgressBar({
  value,
  max = 100,
  label,
  showValue = false,
  color = 'amber',
  size = 'md',
  animated = false,
  className,
}: ProgressBarProps) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100))
  const barColor = resolveColor(color, pct)

  return (
    <div className={cn('space-y-1', className)}>
      {(label || showValue) && (
        <div className="flex items-center justify-between">
          {label && (
            <span className="text-xs text-zinc-400">{label}</span>
          )}
          {showValue && (
            <span className="text-xs font-mono text-zinc-300 ml-auto">
              {pct.toFixed(0)}%
            </span>
          )}
        </div>
      )}
      <div
        className={cn(
          'w-full rounded-full bg-zinc-800 overflow-hidden',
          sizeClasses[size],
        )}
        role="progressbar"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={max}
      >
        <div
          className={cn(
            'h-full rounded-full transition-all duration-500',
            barColor,
            animated && 'animate-pulse-slow',
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

export { ProgressBar }
