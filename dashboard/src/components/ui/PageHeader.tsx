import React from 'react'
import { cn } from '@/lib/utils'
import Badge, { type BadgeVariant } from './Badge'

interface PageHeaderProps {
  title: string
  subtitle?: string
  actions?: React.ReactNode
  badge?: { text: string; variant: string }
  className?: string
}

export default function PageHeader({
  title,
  subtitle,
  actions,
  badge,
  className,
}: PageHeaderProps) {
  return (
    <div className={cn('flex items-start justify-between gap-4 pb-4 border-b border-zinc-800', className)}>
      <div className="flex items-center gap-3 min-w-0">
        <div className="min-w-0">
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl font-semibold text-zinc-100 truncate">{title}</h1>
            {badge && (
              <Badge variant={badge.variant as BadgeVariant} size="sm">
                {badge.text}
              </Badge>
            )}
          </div>
          {subtitle && (
            <p className="text-sm text-zinc-500 mt-0.5 truncate">{subtitle}</p>
          )}
        </div>
      </div>
      {actions && (
        <div className="flex items-center gap-2 flex-shrink-0">{actions}</div>
      )}
    </div>
  )
}
