'use client'

import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { cn } from '@/lib/utils'
import { apiClient } from '@/lib/api'
import type { TradeDecision, MarketIntel, StrategyCandidate, LogEntry } from '@/types'
import { PageHeader } from '@/components/ui/PageHeader'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Spinner } from '@/components/ui/Spinner'
import { ActivityFeed } from '@/components/activity/ActivityFeed'
import type { ActivityEvent } from '@/components/activity/ActivityFeed'
import { useWebSocket } from '@/hooks/useWebSocket'
import {
  RefreshCw,
  ChevronsDown,
  X,
  Bell,
  Wifi,
  WifiOff,
  Activity,
} from 'lucide-react'

// ─── Merge helpers ────────────────────────────────────────────────────────────

function decisionsToEvents(decisions: TradeDecision[]): ActivityEvent[] {
  return decisions.map((d) => ({
    id: `decision-${d.id}`,
    timestamp: d.timestamp,
    agent: 'agent3' as const,
    eventType:
      d.decision === 'EXECUTE'
        ? ('TRADE_EXECUTE' as const)
        : d.decision === 'REJECT'
        ? ('TRADE_REJECT' as const)
        : ('TRADE_DEFER' as const),
    title:
      d.decision === 'EXECUTE'
        ? `Trade executed${d.explanation.direction ? ` — ${d.explanation.direction}` : ''}`
        : d.decision === 'REJECT'
        ? `Trade rejected: ${d.reason}`
        : `Trade deferred: ${d.reason}`,
    description:
      d.explanation.why_executed ??
      d.explanation.risk_reason ??
      d.explanation.psych_reason ??
      d.reason,
    severity:
      d.decision === 'EXECUTE'
        ? 'success'
        : d.decision === 'REJECT'
        ? 'warning'
        : 'info',
    payload: d.explanation as Record<string, unknown>,
  }))
}

function intelToEvents(intelItems: MarketIntel[]): ActivityEvent[] {
  return intelItems.map((intel, idx) => ({
    id: `intel-${intel.timestamp}-${idx}`,
    timestamp: intel.timestamp,
    agent: 'agent2' as const,
    eventType: 'INTELLIGENCE' as const,
    title: `Market Intel: ${intel.regime} — ${intel.trend}`,
    description: `Risk: ${intel.risk_score.toFixed(2)} | Session: ${intel.session} | Confidence: ${intel.confidence.toFixed(2)}`,
    severity: intel.risk_score > 0.7 ? 'warning' : 'info',
    payload: {
      regime: intel.regime,
      trend: intel.trend,
      risk_score: intel.risk_score,
      confidence: intel.confidence,
      session: intel.session,
      technical: intel.technical,
      fundamental: intel.fundamental,
    },
  }))
}

function strategiesToEvents(strategies: StrategyCandidate[]): ActivityEvent[] {
  return strategies.map((s) => ({
    id: `strategy-${s.id}`,
    timestamp: s.created_at,
    agent: 'agent1' as const,
    eventType: 'STRATEGY' as const,
    title: `Strategy ${s.genome_hash.slice(0, 8)} — ${s.status}`,
    description: s.fitness.composite_score != null
      ? `Score: ${(s.fitness.composite_score * 100).toFixed(0)}/100 | Gen: ${s.generation}${s.notes ? ` | ${s.notes}` : ''}`
      : `Generation ${s.generation}${s.notes ? ` | ${s.notes}` : ''}`,
    severity:
      s.status === 'promoted'
        ? 'success'
        : s.status === 'rejected'
        ? 'error'
        : s.status === 'validating'
        ? 'warning'
        : 'info',
    payload: {
      genome_hash: s.genome_hash,
      status: s.status,
      generation: s.generation,
      fitness: s.fitness,
    } as Record<string, unknown>,
  }))
}

function logsToEvents(
  logs: LogEntry[],
  agentLabel: 'agent1' | 'agent2' | 'agent3' | 'system'
): ActivityEvent[] {
  return logs.map((log, idx) => ({
    id: `log-${agentLabel}-${log.id ?? idx}-${log.timestamp}`,
    timestamp: new Date(log.timestamp).getTime() / 1000,
    agent: agentLabel,
    eventType: 'LOG' as const,
    title: log.message.slice(0, 100),
    description: log.message.length > 100 ? log.message : undefined,
    severity:
      log.level === 'ERROR' || log.level === 'CRITICAL'
        ? 'error'
        : log.level === 'WARNING'
        ? 'warning'
        : 'info',
    payload: log.extra as Record<string, unknown> | undefined,
  }))
}

function mergeAndSort(events: ActivityEvent[][]): ActivityEvent[] {
  const merged = events.flat()
  merged.sort((a, b) => b.timestamp - a.timestamp)
  // Remove duplicates by id
  const seen = new Set<string>()
  return merged.filter((e) => {
    if (seen.has(e.id)) return false
    seen.add(e.id)
    return true
  })
}

// ─── Filter types ─────────────────────────────────────────────────────────────

type AgentFilter = 'all' | 'agent1' | 'agent2' | 'agent3'
type EventTypeFilter = 'all' | 'STRATEGY' | 'INTELLIGENCE' | 'TRADE' | 'SYSTEM'
type SeverityFilter = 'all' | 'info' | 'warning' | 'error'

function timeAgo(ts: number): string {
  const diff = Math.floor(Date.now() / 1000 - ts)
  if (diff < 5) return 'just now'
  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  return `${Math.floor(diff / 3600)}h ago`
}

// ─── Stats sidebar ────────────────────────────────────────────────────────────

function StatsSidebar({
  events,
  wsStatus,
}: {
  events: ActivityEvent[]
  wsStatus: string
}) {
  const agents = ['agent1', 'agent2', 'agent3'] as const
  const now = Date.now() / 1000

  const countByAgent = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const a of agents) counts[a] = events.filter((e) => e.agent === a).length
    return counts
  }, [events])

  const lastByAgent = useMemo(() => {
    const last: Record<string, number | null> = {}
    for (const a of agents) {
      const agentEvents = events.filter((e) => e.agent === a)
      last[a] = agentEvents.length > 0 ? agentEvents[0].timestamp : null
    }
    return last
  }, [events])

  // Events per min (last 60s)
  const recentCount = useMemo(
    () => events.filter((e) => now - e.timestamp < 60).length,
    [events]
  )

  const wsColor =
    wsStatus === 'connected'
      ? 'text-emerald-400'
      : wsStatus === 'reconnecting'
      ? 'text-amber-400'
      : 'text-zinc-500'

  const agentLabels: Record<string, string> = {
    agent1: 'Agent 1 — Research',
    agent2: 'Agent 2 — Intelligence',
    agent3: 'Agent 3 — Trader',
  }

  return (
    <div className="space-y-4">
      {/* Event rate */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
        <p className="text-zinc-500 text-[10px] uppercase tracking-wider mb-2">Event Rate</p>
        <div className="flex items-end gap-1">
          <span className="text-2xl font-mono font-bold text-zinc-100">{recentCount}</span>
          <span className="text-zinc-500 text-xs mb-1">events/min</span>
        </div>
      </div>

      {/* Per-agent stats */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-3">
        <p className="text-zinc-500 text-[10px] uppercase tracking-wider">Events by Agent</p>
        {agents.map((a) => (
          <div key={a}>
            <div className="flex items-center justify-between mb-0.5">
              <span className="text-zinc-400 text-xs">{agentLabels[a]}</span>
              <span className="text-zinc-200 text-xs font-mono font-medium">
                {countByAgent[a]}
              </span>
            </div>
            {lastByAgent[a] != null && (
              <p className="text-zinc-600 text-[10px]">
                Last: {timeAgo(lastByAgent[a]!)}
              </p>
            )}
          </div>
        ))}
      </div>

      {/* WebSocket status */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
        <p className="text-zinc-500 text-[10px] uppercase tracking-wider mb-2">WebSocket</p>
        <div className="flex items-center gap-2">
          {wsStatus === 'connected' ? (
            <Wifi className="w-4 h-4 text-emerald-400" />
          ) : (
            <WifiOff className="w-4 h-4 text-zinc-500" />
          )}
          <span className={cn('text-sm font-medium capitalize', wsColor)}>
            {wsStatus}
          </span>
        </div>
      </div>
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function ActivityPage() {
  const [agentFilter, setAgentFilter] = useState<AgentFilter>('all')
  const [typeFilter, setTypeFilter] = useState<EventTypeFilter>('all')
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('all')
  const [searchText, setSearchText] = useState('')
  const [autoScroll, setAutoScroll] = useState(true)
  const [newEventCount, setNewEventCount] = useState(0)
  const [prevTotalCount, setPrevTotalCount] = useState(0)
  const feedRef = useRef<HTMLDivElement>(null)
  const { state: wsState } = useWebSocket()

  // ── Data queries ─────────────────────────────────────────────────────────

  const { data: decisions = [], isLoading: loadingDecisions } = useQuery({
    queryKey: ['decisions', 'recent', 50],
    queryFn: () => apiClient.getRecentDecisions(50),
    refetchInterval: 15_000,
  })

  const { data: intelHistory = [], isLoading: loadingIntel } = useQuery({
    queryKey: ['intel', 'history', 20],
    queryFn: () => apiClient.getIntelHistory(20),
    refetchInterval: 15_000,
  })

  const { data: strategies = [], isLoading: loadingStrategies } = useQuery({
    queryKey: ['strategies', 'recent', 20],
    queryFn: () => apiClient.getStrategyCandidates(undefined, 20),
    refetchInterval: 15_000,
  })

  const { data: agent1LogsData, isLoading: loadingLogs1 } = useQuery({
    queryKey: ['logs', 'agent1', 20],
    queryFn: () => apiClient.getLogs({ type: 'agent1', limit: 20 }),
    refetchInterval: 15_000,
  })

  const { data: agent2LogsData, isLoading: loadingLogs2 } = useQuery({
    queryKey: ['logs', 'agent2', 20],
    queryFn: () => apiClient.getLogs({ type: 'agent2', limit: 20 }),
    refetchInterval: 15_000,
  })

  const { data: agent3LogsData, isLoading: loadingLogs3 } = useQuery({
    queryKey: ['logs', 'agent3', 20],
    queryFn: () => apiClient.getLogs({ type: 'agent3', limit: 20 }),
    refetchInterval: 15_000,
  })

  const isLoading =
    loadingDecisions ||
    loadingIntel ||
    loadingStrategies ||
    loadingLogs1 ||
    loadingLogs2 ||
    loadingLogs3

  // ── Merge all events ──────────────────────────────────────────────────────

  const allEvents = useMemo(
    () =>
      mergeAndSort([
        decisionsToEvents(decisions),
        intelToEvents(intelHistory),
        strategiesToEvents(strategies),
        logsToEvents(agent1LogsData?.logs ?? [], 'agent1'),
        logsToEvents(agent2LogsData?.logs ?? [], 'agent2'),
        logsToEvents(agent3LogsData?.logs ?? [], 'agent3'),
      ]),
    [decisions, intelHistory, strategies, agent1LogsData, agent2LogsData, agent3LogsData]
  )

  // Track new events
  useEffect(() => {
    if (allEvents.length > prevTotalCount && prevTotalCount > 0) {
      const diff = allEvents.length - prevTotalCount
      if (!autoScroll) {
        setNewEventCount((n) => n + diff)
      }
    }
    setPrevTotalCount(allEvents.length)
  }, [allEvents.length])

  // Auto-scroll
  useEffect(() => {
    if (autoScroll && feedRef.current) {
      feedRef.current.scrollTo({ top: 0, behavior: 'smooth' })
    }
  }, [allEvents, autoScroll])

  // ── Filtered events ───────────────────────────────────────────────────────

  const filtered = useMemo(() => {
    return allEvents.filter((e) => {
      if (agentFilter !== 'all' && e.agent !== agentFilter) return false
      if (typeFilter !== 'all') {
        if (typeFilter === 'TRADE') {
          if (
            !e.eventType.startsWith('TRADE_')
          )
            return false
        } else if (typeFilter === 'SYSTEM') {
          if (e.eventType !== 'SYSTEM' && e.eventType !== 'LOG') return false
        } else if (e.eventType !== typeFilter) {
          return false
        }
      }
      if (severityFilter !== 'all' && e.severity !== severityFilter) return false
      if (searchText.trim()) {
        const q = searchText.toLowerCase()
        if (
          !e.title.toLowerCase().includes(q) &&
          !(e.description?.toLowerCase().includes(q))
        )
          return false
      }
      return true
    })
  }, [allEvents, agentFilter, typeFilter, severityFilter, searchText])

  const hasActiveFilters =
    agentFilter !== 'all' ||
    typeFilter !== 'all' ||
    severityFilter !== 'all' ||
    searchText.trim() !== ''

  function clearFilters() {
    setAgentFilter('all')
    setTypeFilter('all')
    setSeverityFilter('all')
    setSearchText('')
  }

  function handleScrollToTop() {
    setNewEventCount(0)
    setAutoScroll(true)
    feedRef.current?.scrollTo({ top: 0, behavior: 'smooth' })
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="max-w-[1400px] mx-auto px-4 py-6">
        {/* Page header */}
        <PageHeader
          title="Activity Monitor"
          subtitle="Real-time events from all three agents"
          badge={{ text: 'Live', variant: 'success' }}
        />

        {/* Sticky filter bar */}
        <div className="sticky top-0 z-20 bg-zinc-950/95 backdrop-blur py-3 mt-4 border-b border-zinc-800/60">
          <div className="space-y-2">
            {/* Row 1: agent + type + severity filters */}
            <div className="flex items-center gap-2 flex-wrap">
              {/* Agent filter */}
              {(
                [
                  { key: 'all', label: 'All Agents' },
                  { key: 'agent1', label: 'Agent 1' },
                  { key: 'agent2', label: 'Agent 2' },
                  { key: 'agent3', label: 'Agent 3' },
                ] as { key: AgentFilter; label: string }[]
              ).map(({ key, label }) => (
                <button
                  key={key}
                  className={cn(
                    'px-2.5 py-1 rounded-full text-xs font-medium border transition-colors',
                    agentFilter === key
                      ? 'bg-zinc-700 text-zinc-100 border-zinc-600'
                      : 'bg-zinc-900 text-zinc-400 border-zinc-800 hover:border-zinc-600 hover:text-zinc-200'
                  )}
                  onClick={() => setAgentFilter(key)}
                >
                  {label}
                </button>
              ))}

              <div className="w-px h-4 bg-zinc-800 mx-1" />

              {/* Type filter */}
              {(
                [
                  { key: 'all', label: 'All Types' },
                  { key: 'STRATEGY', label: 'Strategy' },
                  { key: 'INTELLIGENCE', label: 'Intel' },
                  { key: 'TRADE', label: 'Trades' },
                  { key: 'SYSTEM', label: 'System' },
                ] as { key: EventTypeFilter; label: string }[]
              ).map(({ key, label }) => (
                <button
                  key={key}
                  className={cn(
                    'px-2.5 py-1 rounded-full text-xs font-medium border transition-colors',
                    typeFilter === key
                      ? 'bg-amber-500/20 text-amber-400 border-amber-500/30'
                      : 'bg-zinc-900 text-zinc-400 border-zinc-800 hover:border-zinc-600 hover:text-zinc-200'
                  )}
                  onClick={() => setTypeFilter(key)}
                >
                  {label}
                </button>
              ))}

              <div className="w-px h-4 bg-zinc-800 mx-1" />

              {/* Severity filter */}
              {(
                [
                  { key: 'all', label: 'All' },
                  { key: 'info', label: 'Info' },
                  { key: 'warning', label: 'Warning' },
                  { key: 'error', label: 'Error' },
                ] as { key: SeverityFilter; label: string }[]
              ).map(({ key, label }) => (
                <button
                  key={key}
                  className={cn(
                    'px-2.5 py-1 rounded-full text-xs font-medium border transition-colors',
                    severityFilter === key
                      ? key === 'error'
                        ? 'bg-red-500/20 text-red-400 border-red-500/30'
                        : key === 'warning'
                        ? 'bg-amber-500/20 text-amber-400 border-amber-500/30'
                        : 'bg-zinc-700 text-zinc-100 border-zinc-600'
                      : 'bg-zinc-900 text-zinc-400 border-zinc-800 hover:border-zinc-600 hover:text-zinc-200'
                  )}
                  onClick={() => setSeverityFilter(key)}
                >
                  {label}
                </button>
              ))}

              {hasActiveFilters && (
                <button
                  className="ml-auto flex items-center gap-1 text-zinc-500 text-xs hover:text-zinc-300 transition-colors"
                  onClick={clearFilters}
                >
                  <X className="w-3 h-3" />
                  Clear filters
                </button>
              )}
            </div>

            {/* Row 2: search */}
            <div className="flex items-center gap-2">
              <input
                type="text"
                placeholder="Search events…"
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                className="flex-1 max-w-sm bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-1.5 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600"
              />
              <span className="text-zinc-600 text-xs">
                {filtered.length} event{filtered.length !== 1 ? 's' : ''}
              </span>
              <button
                className={cn(
                  'flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg border transition-colors',
                  autoScroll
                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                    : 'bg-zinc-900 text-zinc-500 border-zinc-800 hover:text-zinc-300'
                )}
                onClick={() => setAutoScroll((v) => !v)}
              >
                <ChevronsDown className="w-3.5 h-3.5" />
                {autoScroll ? 'Auto-scroll on' : 'Auto-scroll off'}
              </button>
            </div>
          </div>
        </div>

        {/* New events banner */}
        {newEventCount > 0 && (
          <div className="mt-3">
            <button
              className="w-full bg-amber-500/10 border border-amber-500/30 rounded-lg py-2 text-amber-400 text-sm font-medium hover:bg-amber-500/20 transition-colors flex items-center justify-center gap-2"
              onClick={handleScrollToTop}
            >
              <Bell className="w-4 h-4" />
              {newEventCount} new event{newEventCount !== 1 ? 's' : ''} — click to view
            </button>
          </div>
        )}

        {/* Main layout: feed + sidebar */}
        <div className="flex gap-6 mt-4">
          {/* Activity feed */}
          <div ref={feedRef} className="flex-1 min-w-0 overflow-y-auto max-h-[calc(100vh-280px)]">
            <ActivityFeed
              events={filtered}
              loading={isLoading}
              compact={false}
            />
          </div>

          {/* Stats sidebar — hidden on mobile */}
          <div className="hidden lg:block w-[280px] flex-shrink-0">
            <StatsSidebar events={allEvents} wsStatus={wsState} />
          </div>
        </div>
      </div>
    </div>
  )
}
