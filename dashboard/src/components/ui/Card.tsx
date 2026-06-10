import React from 'react'
import { cn } from '@/lib/utils'

type Padding = 'none' | 'sm' | 'md' | 'lg'

interface CardProps {
  children: React.ReactNode
  className?: string
  glass?: boolean
  padding?: Padding
}

const paddingClasses: Record<Padding, string> = {
  none: '',
  sm: 'p-3',
  md: 'p-5',
  lg: 'p-6',
}

export default function Card({
  children,
  className,
  glass = false,
  padding,
}: CardProps) {
  return (
    <div
      className={cn(
        'rounded-xl border border-zinc-800',
        glass ? 'bg-zinc-900/80 backdrop-blur-sm' : 'bg-zinc-900',
        padding && paddingClasses[padding],
        className,
      )}
    >
      {children}
    </div>
  )
}

// ─── Sub-components ───────────────────────────────────────────────────────────

interface CardHeaderProps {
  children: React.ReactNode
  className?: string
}

export function CardHeader({ children, className }: CardHeaderProps) {
  return (
    <div
      className={cn(
        'flex items-center justify-between px-5 py-3.5 border-b border-zinc-800/60',
        className,
      )}
    >
      {children}
    </div>
  )
}

interface CardTitleProps {
  children: React.ReactNode
  className?: string
}

export function CardTitle({ children, className }: CardTitleProps) {
  return (
    <h3
      className={cn(
        'flex items-center gap-2 text-sm font-medium text-zinc-300',
        className,
      )}
    >
      {children}
    </h3>
  )
}

interface CardContentProps {
  children: React.ReactNode
  className?: string
}

export function CardContent({ children, className }: CardContentProps) {
  return <div className={cn('px-5 py-4', className)}>{children}</div>
}
