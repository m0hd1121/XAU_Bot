'use client'

import { Bell, BotOff, TrendingUp, AlertTriangle, Server, Shield, Activity, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import Badge from '@/components/ui/Badge'

export interface Notification {
  id: string
  type: 'trade' | 'strategy' | 'risk' | 'vps' | 'agent' | 'system'
  severity: 'info' | 'warning' | 'critical'
  title: string
  message: string
  timestamp: number
  read: boolean
  actionUrl?: string
}

const TYPE_ICON: Record<Notification['type'], React.FC<{ className?: string }>> = {
  trade:    TrendingUp,
  strategy: Activity,
  risk:     AlertTriangle,
  vps:      Server,
  agent:    BotOff,
  system:   Bell,
}

const SEVERITY_COLORS: Record<Notification['severity'], string> = {
  info:     'border-sky-500/30 bg-sky-500/5',
  warning:  'border-amber-500/30 bg-amber-500/5',
  critical: 'border-red-500/30 bg-red-500/10',
}

const SEVERITY_ICON_COLORS: Record<Notification['severity'], string> = {
  info:     'text-sky-400',
  warning:  'text-amber-400',
  critical: 'text-red-400',
}

const SEVERITY_BADGE: Record<Notification['severity'], React.ComponentProps<typeof Badge>['variant']> = {
  info:     'info',
  warning:  'warning',
  critical: 'danger',
}

function timeAgo(ts: number): string {
  const seconds = Math.floor(Date.now() / 1000 - ts)
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

interface NotificationItemProps {
  notification: Notification
  onMarkRead: (id: string) => void
  onDismiss: (id: string) => void
  compact?: boolean
}

function NotificationItem({ notification, onMarkRead, onDismiss, compact }: NotificationItemProps) {
  const Icon = TYPE_ICON[notification.type]
  const iconColor = SEVERITY_ICON_COLORS[notification.severity]

  return (
    <div
      className={cn(
        'relative flex gap-3 p-3 rounded-lg border transition-colors cursor-pointer',
        SEVERITY_COLORS[notification.severity],
        !notification.read && 'ring-1 ring-inset ring-zinc-700',
      )}
      onClick={() => onMarkRead(notification.id)}
    >
      {/* Unread indicator */}
      {!notification.read && (
        <span className="absolute top-3 right-8 w-1.5 h-1.5 rounded-full bg-amber-400 flex-shrink-0" />
      )}

      {/* Dismiss button */}
      <button
        onClick={(e) => { e.stopPropagation(); onDismiss(notification.id) }}
        className="absolute top-2 right-2 p-0.5 rounded text-zinc-600 hover:text-zinc-400 hover:bg-zinc-700 transition-colors"
      >
        <X size={12} />
      </button>

      {/* Icon */}
      <div className={cn('flex-shrink-0 mt-0.5', iconColor)}>
        <Icon className="w-4 h-4" />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0 pr-4">
        <div className="flex items-start gap-2 mb-0.5">
          <p className={cn('text-sm font-medium text-zinc-200 leading-snug', compact && 'text-xs')}>
            {notification.title}
          </p>
          <Badge variant={SEVERITY_BADGE[notification.severity]} size="sm" className="flex-shrink-0">
            {notification.severity}
          </Badge>
        </div>
        {!compact && (
          <p className="text-xs text-zinc-400 leading-snug line-clamp-2">
            {notification.message}
          </p>
        )}
        <p className="text-xs text-zinc-600 mt-1">{timeAgo(notification.timestamp)}</p>
      </div>
    </div>
  )
}

interface NotificationsPanelProps {
  notifications: Notification[]
  onMarkRead: (id: string) => void
  onMarkAllRead: () => void
  onDismiss: (id: string) => void
  compact?: boolean
  maxHeight?: string
  className?: string
}

export function NotificationsPanel({
  notifications,
  onMarkRead,
  onMarkAllRead,
  onDismiss,
  compact = false,
  maxHeight = '480px',
  className,
}: NotificationsPanelProps) {
  const unreadCount = notifications.filter((n) => !n.read).length

  if (notifications.length === 0) {
    return (
      <div
        className={cn(
          'flex flex-col items-center justify-center gap-2 py-12 text-zinc-600',
          className,
        )}
      >
        <Bell className="w-8 h-8 opacity-30" />
        <p className="text-sm">No notifications</p>
      </div>
    )
  }

  return (
    <div className={cn('flex flex-col', className)}>
      {/* Header */}
      <div className="flex items-center justify-between px-1 pb-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-zinc-300">
            {notifications.length} notification{notifications.length !== 1 ? 's' : ''}
          </span>
          {unreadCount > 0 && (
            <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-amber-500/20 text-amber-400 text-xs font-bold">
              {unreadCount}
            </span>
          )}
        </div>
        {unreadCount > 0 && (
          <button
            onClick={onMarkAllRead}
            className="text-xs text-amber-400 hover:text-amber-300 transition-colors"
          >
            Mark all read
          </button>
        )}
      </div>

      {/* Notifications list */}
      <div
        className="space-y-2 overflow-y-auto"
        style={{ maxHeight }}
      >
        {notifications.map((n) => (
          <NotificationItem
            key={n.id}
            notification={n}
            onMarkRead={onMarkRead}
            onDismiss={onDismiss}
            compact={compact}
          />
        ))}
      </div>
    </div>
  )
}

export default NotificationsPanel
