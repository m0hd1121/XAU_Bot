import React from 'react'
import { cn } from '@/lib/utils'

type SpinnerSize = 'sm' | 'md' | 'lg'
type SpinnerColor = 'default' | 'amber' | 'dark'

interface SpinnerProps {
  size?: SpinnerSize
  color?: SpinnerColor
  className?: string
}

const sizeClasses: Record<SpinnerSize, string> = {
  sm: 'w-3.5 h-3.5 border-[1.5px]',
  md: 'w-5 h-5 border-2',
  lg: 'w-8 h-8 border-[2.5px]',
}

const colorClasses: Record<SpinnerColor, string> = {
  default: 'border-zinc-600 border-t-zinc-300',
  amber: 'border-amber-900/50 border-t-amber-500',
  dark: 'border-zinc-700/50 border-t-zinc-900',
}

export default function Spinner({
  size = 'md',
  color = 'amber',
  className,
}: SpinnerProps) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={cn(
        'inline-block rounded-full animate-spin',
        sizeClasses[size],
        colorClasses[color],
        className,
      )}
    />
  )
}

export { Spinner }
