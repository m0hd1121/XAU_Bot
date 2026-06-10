'use client'

import { useState } from 'react'
import { cn } from '@/lib/utils'
import { Spinner } from '@/components/ui/Spinner'
import { JsonViewer } from '@/components/ui/JsonViewer'
import { ChevronDown, ChevronUp } from 'lucide-react'

export interface ActivityEvent {
  id: string
  timestamp: number
  agent: 'agent1' | 'agent2' | 'agent3' | 'system'
  eventType:
    | 'STRATEGY'
    | 'INTELLIGENCE'
    | 'TRADE_EXECUTE'
    | 'TRADE_REJECT'
    | 'TRADE_DEFER'
    | 'VALIDATION'
    | 'SYSTEM'
    | 'LOG'
  title: string
  description?: string
  severity: 'info' | 'warning' | 'error' | 'success'
  payload?: Record<string, unknown>
}

export interface ActivityFeedProps {
  events: ActivityEvent[]
  loading?: boolean
  maxItems?: number
  compact?: boolean
  className?: string
}

// ─── Agent config ────────────────────────────────────────────────────────────

const AGENT_CONFIG = {
  agent1: {
    label: 'A1',
    initials: 'A1',
    borderColor: 'border-l-indigo-500',
    bgColor: 'bg-indigo-600',
    textColor: 'text-indigo-400',
    badgeBg: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20',
  },
  agent2: {
    label: 'A2',
    initials: 'A2',
    borderColor: 'border-l-sky-500',
    bgColor: 'bg-sky-600',
    textColor: 'text-sky-400',
    badgeBg: 'bg-sky-500/10 text-sky-400 border-sky-500/20',
  },
  agent3: {
    label: 'A3',
    initials: 'A3',
    borderColor: 'border-l-emerald-500',
    bgColor: 'bg-emerald-600',
    textColor: 'text-emerald-400',
    badgeBg: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  },
  system: {
    label: 'SYS',
    initials: 'SY',
    borderColor: 'border-l-zinc-500',
    bgColor: 'bg-zinc-600',
    textColor: 'text-zinc-400',
    badgeBg: 'bg-zinc-800 text-zinc-400 border-zinc-700',
  },
} as const

// ─── Event type badge ────────────────────────────────────────────────────────

const EVENT_TYPE_STYLES: Record<ActivityEvent['eventType'], string> = {
  STRATEGY: 'bg-indigo-500/10 text-indigo-300 border-indigo-500/20',
  INTELLIGENCE: 'bg-sky-500/10 text-sky-300 border-sky-500/20',
  TRADE_EXECUTE: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20',
  TRADE_REJECT: 'bg-red-500/10 text-red-300 border-red-500/20',
  TRADE_DEFER: 'bg-amber-500/10 text-amber-300 border-amber-500/20',
  VALIDATION: 'bg-violet-500/10 text-violet-300 border-violet-500/20',
  SYSTEM: 'bg-zinc-700 text-zinc-300 border-zinc-600',
  LOG: 'bg-zinc-800 text-zinc-400 border-zinc-700',
}

// ─── Severity styles ──────────────────────────────────────────────────────────

const SEVERITY_LEFT_BORDER: Record<ActivityEvent['severity'], string> = {
  info: 'border-l-zinc-600',
  warning: 'border-l-amber-500',
  error: 'border-l-red-500',
  success: 'border-l-emerald-500',
}

// ─── Time helper ──────────────────────────────────────────────────────────────

function timeAgo(ts: number): string {
  const diffSec = Math.floor(Date.now() / 1000 - ts)
  if (diffSec < 5) return 'just now'
  if (diffSec < 60) return `${diffSec}s ago`
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`
  return `${Math.floor(diffSec / 86400)}d ago`
}

// ─── Single item ──────────────────────────────────────────────────────────────

function ActivityItem({
  event,
  compact,
}: {
  event: ActivityEvent
  compact: boolean
}) {
  const [expanded, setExpanded] = useState(false)
  const [descExpanded, setDescExpanded] = useState(false)

  const agentCfg =
    AGENT_CONFIG[event.agent] ?? AGENT_CONFIG.system
  const eventStyle = EVENT_TYPE_STYLES[event.eventType] ?? EVENT_TYPE_STYLES.LOG

  // For trade events override agent3 border color
  const borderColor =
    event.eventType === 'TRADE_REJECT'
      ? 'border-l-red-500'
      : event.eventType === 'TRADE_EXECUTE'
      ? 'border-l-emerald-500'
      : event.severity !== 'info'
      ? SEVERITY_LEFT_BORDER[event.severity]
      : agentCfg.borderColor

  return (
    <div
      className={cn(
        'bg-zinc-900 border border-zinc-800 rounded-lg border-l-4 p-3 transition-colors hover:bg-zinc-800/50',
        borderColor,
        compact ? 'py-2' : 'py-3'
      )}
    >
      <div className="flex items-start gap-3">
        {/* Agent avatar */}
        <div
          className={cn(
            'flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-white font-bold text-[10px]',
            agentCfg.bgColor
          )}
        >
          {agentCfg.initials}
        </div>

        <div className="flex-1 min-w-0">
          {/* Top row: timestamp + event type badge */}
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="text-zinc-500 text-[11px] font-mono flex-shrink-0">
              {timeAgo(event.timestamp)}
            </span>
            <span
              className={cn(
                'inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border',
                eventStyle
              )}
            >
              {event.eventType.replace('_', ' ')}
            </span>
            <span
              className={cn(
                'inline-flex items-center px-1.5 py-0.5 rounded text-[10px] border',
                agentCfg.badgeBg
              )}
            >
              {agentCfg.label}
            </span>
          </div>

          {/* Title */}
          <p className="text-zinc-100 text-sm font-medium leading-snug">{event.title}</p>

          {/* Description */}
          {event.description && (
            <div className="mt-1">
              <p
                className={cn(
                  'text-zinc-400 text-xs leading-relaxed',
                  !descExpanded && 'line-clamp-2'
                )}
              >
                {event.description}
              </p>
              {event.description.length > 120 && (
                <button
                  className="text-zinc-500 text-[11px] hover:text-zinc-300 mt-0.5 transition-colors"
                  onClick={() => setDescExpanded((v) => !v)}
                >
                  {descExpanded ? 'Show less' : 'Show more'}
                </button>
              )}
            </div>
          )}

          {/* Expandable payload */}
          {event.payload && !compact && (
            <div className="mt-2">
              <button
                className="flex items-center gap-1 text-zinc-500 text-[11px] hover:text-zinc-300 transition-colors"
                onClick={() => setExpanded((v) => !v)}
              >
                {expanded ? (
                  <ChevronUp className="w-3 h-3" />
                ) : (
                  <ChevronDown className="w-3 h-3" />
                )}
                {expanded ? 'Hide' : 'View'} payload
              </button>
              {expanded && (
                <div className="mt-2">
                  <JsonViewer data={event.payload} />
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Skeleton ──────────────────────────────────────────────────────────────────

function SkeletonItem() {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg border-l-4 border-l-zinc-700 p-3 animate-pulse">
      <div className="flex items-start gap-3">
        <div className="w-7 h-7 rounded-full bg-zinc-700 flex-shrink-0" />
        <div className="flex-1 space-y-2">
          <div className="flex gap-2">
            <div className="h-3 w-16 bg-zinc-700 rounded" />
            <div className="h-3 w-20 bg-zinc-700 rounded" />
          </div>
          <div className="h-4 w-3/4 bg-zinc-700 rounded" />
          <div className="h-3 w-1/2 bg-zinc-700 rounded" />
        </div>
      </div>
    </div>
  )
}

// ─── Main component ────────────────────────────────────────────────────────────

export function ActivityFeed({
  events,
  loading = false,
  maxItems,
  compact = false,
  className,
}: ActivityFeedProps) {
  const displayed = maxItems ? events.slice(0, maxItems) : events

  if (loading && events.length === 0) {
    return (
      <div className={cn('space-y-2', className)}>
        {Array.from({ length: 5 }).map((_, i) => (
          <SkeletonItem key={i} />
        ))}
      </div>
    )
  }

  if (!loading && events.length === 0) {
    return (
      <div
        className={cn(
          'flex flex-col items-center justify-center py-12 text-zinc-600',
          className
        )}
      >
        <div className="w-12 h-12 rounded-full bg-zinc-800 flex items-center justify-center mb-3">
          <span className="text-2xl">📭</span>
        </div>
        <p className="text-sm">No activity yet</p>
        <p className="text-xs text-zinc-700 mt-1">Events will appear here as agents run</p>
      </div>
    )
  }

  return (
    <div className={cn('space-y-2', className)}>
      {displayed.map((event) => (
        <ActivityItem key={event.id} event={event} compact={compact} />
      ))}
      {loading && events.length > 0 && (
        <div className="flex justify-center py-3">
          <Spinner size="sm" />
        </div>
      )}
    </div>
  )
}
