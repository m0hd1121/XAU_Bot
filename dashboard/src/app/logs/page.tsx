'use client'

import { useState, useCallback, useRef, useEffect } from 'react'
import { Download, RefreshCw, ChevronsDown, Pause, Play } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import PageHeader from '@/components/ui/PageHeader'
import Button from '@/components/ui/Button'
import { LogViewer } from '@/components/logs/LogViewer'
import { apiClient } from '@/lib/api'
import type { LogEntry, LogLevel } from '@/types'

// ─── Types ────────────────────────────────────────────────────────────────────

const LOG_TYPES = [
  { id: 'all',      label: 'All' },
  { id: 'trading',  label: 'Trading' },
  { id: 'learning', label: 'Learning' },
  { id: 'agent1',   label: 'Agent 1' },
  { id: 'agent2',   label: 'Agent 2' },
  { id: 'agent3',   label: 'Agent 3' },
  { id: 'api',      label: 'API' },
  { id: 'vps',      label: 'VPS' },
  { id: 'auth',     label: 'Auth' },
] as const

const LOG_LEVELS: { id: LogLevel | 'ALL'; label: string; color: string }[] = [
  { id: 'ALL',      label: 'All',      color: 'text-zinc-400' },
  { id: 'DEBUG',    label: 'Debug',    color: 'text-zinc-500' },
  { id: 'INFO',     label: 'Info',     color: 'text-sky-400'  },
  { id: 'WARNING',  label: 'Warning',  color: 'text-amber-400' },
  { id: 'ERROR',    label: 'Error',    color: 'text-red-400'  },
  { id: 'CRITICAL', label: 'Critical', color: 'text-red-600'  },
]

const REFRESH_RATES = [
  { label: 'Off',  ms: 0 },
  { label: '5s',   ms: 5_000 },
  { label: '10s',  ms: 10_000 },
  { label: '30s',  ms: 30_000 },
]

// ─── Component ────────────────────────────────────────────────────────────────

export default function LogsPage() {
  const [activeType, setActiveType] = useState<string>('all')
  const [activeLevel, setActiveLevel] = useState<LogLevel | 'ALL'>('ALL')
  const [search, setSearch] = useState('')
  const [refreshRateMs, setRefreshRateMs] = useState(10_000)
  const [autoScroll, setAutoScroll] = useState(true)
  const [displayedLogs, setDisplayedLogs] = useState<LogEntry[]>([])

  const { data, isLoading, refetch, dataUpdatedAt } = useQuery({
    queryKey: ['logs', activeType, activeLevel, search],
    queryFn: () =>
      apiClient.getLogs({
        type:   activeType === 'all' ? undefined : activeType,
        level:  activeLevel === 'ALL' ? undefined : activeLevel,
        search: search.trim() || undefined,
        limit:  500,
      }),
    refetchInterval: refreshRateMs > 0 ? refreshRateMs : false,
    staleTime: 0,
  })

  // Accumulate logs — don't replace on every fetch, append new ones
  const prevUpdateRef = useRef(0)
  useEffect(() => {
    if (!data?.logs) return
    if (dataUpdatedAt !== prevUpdateRef.current) {
      setDisplayedLogs(data.logs)
      prevUpdateRef.current = dataUpdatedAt
    }
  }, [data, dataUpdatedAt])

  const handleExport = useCallback(() => {
    const text = displayedLogs
      .map((l) => `[${l.timestamp}] [${l.level}] [${l.source}] ${l.message}`)
      .join('\n')
    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `xau-logs-${new Date().toISOString().slice(0, 10)}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }, [displayedLogs])

  const errorCount = displayedLogs.filter(
    (l) => l.level === 'ERROR' || l.level === 'CRITICAL',
  ).length
  const warnCount  = displayedLogs.filter((l) => l.level === 'WARNING').length

  return (
    <div className="p-6 space-y-5 h-full flex flex-col">
      <PageHeader
        title="Logs Center"
        subtitle="Real-time access to all system logs"
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setAutoScroll((v) => !v)}
              iconLeft={autoScroll ? <Pause size={14} /> : <Play size={14} />}
            >
              {autoScroll ? 'Auto-scroll On' : 'Auto-scroll Off'}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleExport}
              iconLeft={<Download size={14} />}
              disabled={displayedLogs.length === 0}
            >
              Export
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void refetch()}
              iconLeft={<RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />}
            >
              Refresh
            </Button>
          </div>
        }
      />

      {/* Filters */}
      <div className="space-y-3">
        {/* Log type tabs */}
        <div className="flex flex-wrap gap-1">
          {LOG_TYPES.map((t) => (
            <button
              key={t.id}
              onClick={() => setActiveType(t.id)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                activeType === t.id
                  ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                  : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 border border-transparent'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Level filter */}
          <div className="flex gap-1">
            {LOG_LEVELS.map((lvl) => (
              <button
                key={lvl.id}
                onClick={() => setActiveLevel(lvl.id as LogLevel | 'ALL')}
                className={`px-2.5 py-1 rounded text-xs font-mono font-medium transition-colors ${
                  activeLevel === lvl.id
                    ? `bg-zinc-700 ${lvl.color}`
                    : 'text-zinc-600 hover:text-zinc-400 hover:bg-zinc-800'
                }`}
              >
                {lvl.label}
              </button>
            ))}
          </div>

          {/* Search */}
          <input
            type="text"
            placeholder="Filter messages..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="flex-1 min-w-48 px-3 py-1.5 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-amber-500/50"
          />

          {/* Refresh rate */}
          <div className="flex items-center gap-1.5 text-xs text-zinc-500">
            <span>Refresh:</span>
            <select
              value={refreshRateMs}
              onChange={(e) => setRefreshRateMs(Number(e.target.value))}
              className="bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-zinc-300 text-xs focus:outline-none focus:border-amber-500/50"
            >
              {REFRESH_RATES.map((r) => (
                <option key={r.ms} value={r.ms}>{r.label}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Log viewer — flex-1 to fill remaining height */}
      <div className="flex-1 min-h-0">
        <LogViewer
          logs={displayedLogs}
          loading={isLoading}
          maxHeight="100%"
          autoScroll={autoScroll}
          className="h-full"
        />
      </div>

      {/* Stats bar */}
      <div className="flex items-center justify-between text-xs text-zinc-500 pt-1">
        <div className="flex items-center gap-4">
          <span>{displayedLogs.length.toLocaleString()} entries shown</span>
          {errorCount > 0 && (
            <span className="text-red-400">{errorCount} error{errorCount !== 1 ? 's' : ''}</span>
          )}
          {warnCount > 0 && (
            <span className="text-amber-400">{warnCount} warning{warnCount !== 1 ? 's' : ''}</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <ChevronsDown size={12} />
          <span>
            {refreshRateMs > 0
              ? `Auto-refreshing every ${refreshRateMs / 1000}s`
              : 'Auto-refresh off'}
          </span>
        </div>
      </div>
    </div>
  )
}
