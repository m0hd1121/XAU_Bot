'use client'

import { useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'
import type { LogEntry, LogLevel } from '@/types'

const LEVEL_STYLES: Record<LogLevel, { badge: string; text: string }> = {
  DEBUG:    { badge: 'text-zinc-500',   text: 'text-zinc-500' },
  INFO:     { badge: 'text-sky-400',    text: 'text-zinc-200' },
  WARNING:  { badge: 'text-amber-400',  text: 'text-amber-200' },
  ERROR:    { badge: 'text-red-400',    text: 'text-red-200' },
  CRITICAL: { badge: 'text-red-600 font-bold', text: 'text-red-300 font-semibold' },
}

function formatLogTimestamp(ts: string): string {
  try {
    return new Date(ts).toLocaleTimeString('en-US', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return ts.slice(0, 8)
  }
}

interface LogRowProps {
  log: LogEntry
  showSource?: boolean
  compact?: boolean
}

function LogRow({ log, showSource = true, compact = false }: LogRowProps) {
  const styles = LEVEL_STYLES[log.level] ?? LEVEL_STYLES.INFO
  return (
    <div
      className={cn(
        'flex items-start gap-2 px-3 font-mono text-xs leading-relaxed border-b border-zinc-800/50 hover:bg-zinc-800/30 transition-colors',
        compact ? 'py-0.5' : 'py-1',
      )}
    >
      {/* Timestamp */}
      <span className="shrink-0 text-zinc-600 tabular-nums w-20">
        {formatLogTimestamp(log.timestamp)}
      </span>

      {/* Level badge */}
      <span className={cn('shrink-0 w-8 uppercase', styles.badge)}>
        {log.level.slice(0, 4)}
      </span>

      {/* Source */}
      {showSource && (
        <span className="shrink-0 text-zinc-500 max-w-24 truncate">
          {log.source}
        </span>
      )}

      {/* Message */}
      <span className={cn('flex-1 break-all whitespace-pre-wrap', styles.text)}>
        {log.message}
      </span>
    </div>
  )
}

interface LogViewerProps {
  logs: LogEntry[]
  loading?: boolean
  maxHeight?: string
  autoScroll?: boolean
  className?: string
  showSource?: boolean
  compact?: boolean
}

export function LogViewer({
  logs,
  loading = false,
  maxHeight = '480px',
  autoScroll = true,
  className,
  showSource = true,
  compact = false,
}: LogViewerProps) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // Cap at 500 entries to avoid performance issues
  const visibleLogs = logs.slice(-500)

  useEffect(() => {
    if (autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [visibleLogs.length, autoScroll])

  if (loading && visibleLogs.length === 0) {
    return (
      <div
        className={cn(
          'bg-zinc-950 rounded-lg border border-zinc-800 overflow-hidden',
          className,
        )}
        style={{ maxHeight }}
      >
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="flex gap-2 px-3 py-1 border-b border-zinc-800/50">
            <div className="shimmer h-3 w-20 rounded" />
            <div className="shimmer h-3 w-8 rounded" />
            <div className="shimmer h-3 flex-1 rounded" />
          </div>
        ))}
      </div>
    )
  }

  if (!loading && visibleLogs.length === 0) {
    return (
      <div
        className={cn(
          'bg-zinc-950 rounded-lg border border-zinc-800 flex items-center justify-center',
          className,
        )}
        style={{ maxHeight, minHeight: '120px' }}
      >
        <p className="text-zinc-600 text-sm font-mono">No log entries</p>
      </div>
    )
  }

  return (
    <div
      ref={containerRef}
      className={cn(
        'bg-zinc-950 rounded-lg border border-zinc-800 overflow-y-auto',
        className,
      )}
      style={{ maxHeight }}
    >
      {visibleLogs.map((log, i) => (
        <LogRow
          key={log.id ?? i}
          log={log}
          showSource={showSource}
          compact={compact}
        />
      ))}
      <div ref={bottomRef} />
    </div>
  )
}

export default LogViewer
