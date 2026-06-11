import React from 'react'
import { cn } from '@/lib/utils'

export type StatusType =
  | 'running'
  | 'stopped'
  | 'paused'
  | 'error'
  | 'warning'
  | 'unknown'
  | 'starting'

type DotSize = 'sm' | 'md' | 'lg'

interface StatusDotProps {
  status: StatusType
  label?: string
  size?: DotSize
  className?: string
}

const dotConfig: Record<
  StatusType,
  { bg: string; ring?: string; animate?: string }
> = {
  running: {
    bg: 'bg-emerald-500',
    ring: 'ring-emerald-500/30',
    animate: 'animate-pulse',
  },
  paused: {
    bg: 'bg-amber-500',
    ring: 'ring-amber-500/30',
    animate: 'animate-pulse-slow',
  },
  error: {
    bg: 'bg-red-500',
    ring: 'ring-red-500/30',
    animate: 'animate-pulse',
  },
  stopped: {
    bg: 'bg-zinc-500',
  },
  warning: {
    bg: 'bg-amber-400',
    ring: 'ring-amber-400/30',
  },
  unknown: {
    bg: 'bg-zinc-600',
  },
  starting: {
    bg: 'bg-blue-500',
    ring: 'ring-blue-500/30',
    animate: 'animate-pulse',
  },
}

const sizeClasses: Record<DotSize, { dot: string; label: string }> = {
  sm: { dot: 'w-2 h-2', label: 'text-xs' },
  md: { dot: 'w-2.5 h-2.5', label: 'text-xs' },
  lg: { dot: 'w-3 h-3', label: 'text-sm' },
}

export default function StatusDot({
  status,
  label,
  size = 'md',
  className,
}: StatusDotProps) {
  const config = dotConfig[status]
  const sizes = sizeClasses[size]

  return (
    <span className={cn('inline-flex items-center gap-1.5', className)}>
      <span
        className={cn(
          'rounded-full flex-shrink-0 ring-2 ring-transparent',
          sizes.dot,
          config.bg,
          config.ring,
          config.animate,
        )}
      />
      {label && (
        <span className={cn('text-zinc-400 font-medium', sizes.label)}>
          {label}
        </span>
      )}
    </span>
  )
}

export { StatusDot }