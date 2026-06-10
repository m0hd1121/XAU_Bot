'use client'

import { useState, useMemo, useEffect, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, RefreshCw, Filter } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { TradeDecision, DecisionType } from '@/types'
import { apiClient } from '@/lib/api'
import { MetricTile } from '@/components/ui/MetricTile'
import { Spinner } from '@/components/ui/Spinner'
import { Button } from '@/components/ui/Button'
import { DecisionCard } from '@/components/explainability/DecisionCard'

// ── Types ─────────────────────────────────────────────────────────────────────

type DateRange = 'today' | '7d' | '30d' | 'all'
type DirectionFilter = 'all' | 'BUY' | 'SELL'

const PAGE_SIZE = 20

// ── Filter pill button ────────────────────────────────────────────────────────

function FilterPill({
  label,
  active,
  onClick,
  colorClass,
}: {
  label: string
  active: boolean
  onClick: () => void
  colorClass?: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'px-3 py-1 rounded-full text-xs font-medium border transition-all',
        active
          ? colorClass ?? 'bg-zinc-700 text-zinc-100 border-zinc-600'
          : 'bg-transparent text-zinc-500 border-zinc-700 hover:border-zinc-500 hover:text-zinc-300'
      )}
    >
      {label}
    </button>
  )
}

// ── Page header ───────────────────────────────────────────────────────────────

function PageHeaderBlock({
  onRefresh,
  isRefreshing,
}: {
  onRefresh: () => void
  isRefreshing: boolean
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <h1 className="text-lg font-semibold text-zinc-100">Explainability Center</h1>
        <p className="text-zinc-500 text-xs mt-0.5">
          Complete transparency into every trading decision made by the AI agents
        </p>
      </div>
      <button
        type="button"
        onClick={onRefresh}
        className="text-zinc-500 hover:text-zinc-300 transition-colors mt-1"
        title="Refresh"
      >
        <RefreshCw className={cn('w-4 h-4', isRefreshing && 'animate-spin')} />
      </button>
    </div>
  )
}

// ── Stats row ─────────────────────────────────────────────────────────────────

function StatsRow({
  decisions,
  loading,
}: {
  decisions: TradeDecision[]
  loading: boolean
}) {
  const total = decisions.length
  const executed = decisions.filter((d) => d.decision === 'EXECUTE').length
  const rejected = decisions.filter((d) => d.decision === 'REJECT').length
  const deferred = decisions.filter((d) => d.decision === 'DEFER').length
  const execPct = total > 0 ? ((executed / total) * 100).toFixed(1) : '0.0'
  const rejPct = total > 0 ? ((rejected / total) * 100).toFixed(1) : '0.0'
  const defPct = total > 0 ? ((deferred / total) * 100).toFixed(1) : '0.0'

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      <MetricTile
        label="Total Decisions"
        value={loading ? '—' : String(total)}
        loading={loading}
      />
      <MetricTile
        label="Executed"
        value={loading ? '—' : `${executed}`}
        sub={loading ? undefined : `${execPct}%`}
        loading={loading}
        valueClassName="text-emerald-400"
      />
      <MetricTile
        label="Rejected"
        value={loading ? '—' : `${rejected}`}
        sub={loading ? undefined : `${rejPct}%`}
        loading={loading}
        valueClassName="text-red-400"
      />
      <MetricTile
        label="Deferred"
        value={loading ? '—' : `${deferred}`}
        sub={loading ? undefined : `${defPct}%`}
        loading={loading}
        valueClassName="text-amber-400"
      />
    </div>
  )
}

// ── Skeleton card ─────────────────────────────────────────────────────────────

function SkeletonCard() {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl border-l-4 border-l-zinc-700 p-4 animate-pulse">
      <div className="flex items-center gap-3 mb-2">
        <div className="h-5 w-16 bg-zinc-800 rounded-full" />
        <div className="h-5 w-12 bg-zinc-800 rounded-full" />
        <div className="h-4 w-20 bg-zinc-800 rounded" />
        <div className="h-4 flex-1 bg-zinc-800 rounded" />
      </div>
      <div className="flex gap-4">
        <div className="h-3 w-24 bg-zinc-800 rounded" />
        <div className="h-3 w-20 bg-zinc-800 rounded" />
        <div className="h-3 w-16 bg-zinc-800 rounded" />
      </div>
    </div>
  )
}

// ── Pagination ────────────────────────────────────────────────────────────────

function Pagination({
  page,
  totalPages,
  onPage,
}: {
  page: number
  totalPages: number
  onPage: (p: number) => void
}) {
  if (totalPages <= 1) return null
  return (
    <div className="flex items-center justify-center gap-2 pt-2">
      <button
        type="button"
        onClick={() => onPage(page - 1)}
        disabled={page === 1}
        className="px-3 py-1.5 text-xs rounded-lg bg-zinc-800 text-zinc-400 hover:bg-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        Previous
      </button>
      <span className="text-zinc-500 text-xs px-2">
        Page {page} of {totalPages}
      </span>
      <button
        type="button"
        onClick={() => onPage(page + 1)}
        disabled={page === totalPages}
        className="px-3 py-1.5 text-xs rounded-lg bg-zinc-800 text-zinc-400 hover:bg-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        Next
      </button>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ExplainabilityPage() {
  const [decisionFilter, setDecisionFilter] = useState<DecisionType | 'all'>('all')
  const [dateRange, setDateRange] = useState<DateRange>('all')
  const [directionFilter, setDirectionFilter] = useState<DirectionFilter>('all')
  const [search, setSearch] = useState('')
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [page, setPage] = useState(1)

  const {
    data: decisions = [],
    isLoading,
    isFetching,
    refetch,
  } = useQuery<TradeDecision[]>({
    queryKey: ['decisions', 200],
    queryFn: () => apiClient.getRecentDecisions(200),
    refetchInterval: 30_000,
    staleTime: 20_000,
  })

  // Reset page on filter change
  useEffect(() => {
    setPage(1)
  }, [decisionFilter, dateRange, directionFilter, search])

  // Date range cutoff
  const cutoff = useMemo(() => {
    const now = Date.now() / 1000
    switch (dateRange) {
      case 'today': return now - 86400
      case '7d': return now - 7 * 86400
      case '30d': return now - 30 * 86400
      default: return 0
    }
  }, [dateRange])

  // Filtered + sorted decisions
  const filtered = useMemo(() => {
    return decisions
      .filter((d) => {
        if (decisionFilter !== 'all' && d.decision !== decisionFilter) return false
        if (dateRange !== 'all' && d.timestamp < cutoff) return false
        if (directionFilter !== 'all') {
          const dir = d.explanation.direction?.toUpperCase()
          if (dir !== directionFilter) return false
        }
        if (search.trim()) {
          const q = search.toLowerCase()
          const matchReason = d.reason.toLowerCase().includes(q)
          const matchTrade = d.trade_id?.toLowerCase().includes(q)
          const matchStrategy = d.strategy_id?.toLowerCase().includes(q)
          if (!matchReason && !matchTrade && !matchStrategy) return false
        }
        return true
      })
      .sort((a, b) => b.timestamp - a.timestamp)
  }, [decisions, decisionFilter, dateRange, directionFilter, search, cutoff])

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  const handleToggle = useCallback((id: number) => {
    setExpandedId((prev) => (prev === id ? null : id))
  }, [])

  return (
    <div className="min-h-screen bg-zinc-950 p-4 space-y-4">

      {/* Page header */}
      <PageHeaderBlock onRefresh={() => void refetch()} isRefreshing={isFetching} />

      {/* Stats row */}
      <StatsRow decisions={decisions} loading={isLoading} />

      {/* Filter bar */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-3 space-y-3">
        {/* Row 1: Decision type + date range */}
        <div className="flex flex-wrap gap-2 items-center">
          <Filter className="w-3.5 h-3.5 text-zinc-500 flex-shrink-0" />
          <div className="flex flex-wrap gap-1.5">
            {(['all', 'EXECUTE', 'REJECT', 'DEFER'] as const).map((v) => (
              <FilterPill
                key={v}
                label={v === 'all' ? 'All' : v}
                active={decisionFilter === v}
                onClick={() => setDecisionFilter(v)}
                colorClass={
                  v === 'EXECUTE'
                    ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                    : v === 'REJECT'
                    ? 'bg-red-500/15 text-red-400 border-red-500/30'
                    : v === 'DEFER'
                    ? 'bg-amber-500/15 text-amber-400 border-amber-500/30'
                    : 'bg-zinc-700 text-zinc-100 border-zinc-600'
                }
              />
            ))}
          </div>

          <div className="w-px h-4 bg-zinc-700 mx-1 hidden sm:block" />

          <div className="flex flex-wrap gap-1.5">
            {([
              { v: 'today' as DateRange, label: 'Today' },
              { v: '7d' as DateRange, label: '7 days' },
              { v: '30d' as DateRange, label: '30 days' },
              { v: 'all' as DateRange, label: 'All' },
            ]).map(({ v, label }) => (
              <FilterPill
                key={v}
                label={label}
                active={dateRange === v}
                onClick={() => setDateRange(v)}
              />
            ))}
          </div>
        </div>

        {/* Row 2: Direction + Search */}
        <div className="flex flex-wrap gap-2 items-center">
          <div className="flex flex-wrap gap-1.5">
            {(['all', 'BUY', 'SELL'] as const).map((v) => (
              <FilterPill
                key={v}
                label={v === 'all' ? 'All Directions' : v}
                active={directionFilter === v}
                onClick={() => setDirectionFilter(v)}
                colorClass={
                  v === 'BUY'
                    ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                    : v === 'SELL'
                    ? 'bg-red-500/15 text-red-400 border-red-500/30'
                    : 'bg-zinc-700 text-zinc-100 border-zinc-600'
                }
              />
            ))}
          </div>

          <div className="flex-1 min-w-[200px]">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-500 pointer-events-none" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search reason, trade ID…"
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg pl-8 pr-3 py-1.5 text-xs text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 focus:ring-1 focus:ring-zinc-500/30 transition-colors"
              />
            </div>
          </div>
        </div>

        {/* Result count */}
        <div className="flex items-center gap-2">
          <span className="text-zinc-600 text-xs">
            {isLoading ? 'Loading…' : `${filtered.length} decision${filtered.length !== 1 ? 's' : ''} matching filters`}
          </span>
        </div>
      </div>

      {/* Decision list */}
      <div className="space-y-2">
        {isLoading ? (
          Array.from({ length: 6 }).map((_, i) => <SkeletonCard key={i} />)
        ) : paginated.length === 0 ? (
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-12 flex flex-col items-center text-zinc-600">
            <Search className="w-10 h-10 mb-3" />
            <p className="text-sm font-medium text-zinc-500">No decisions found</p>
            <p className="text-xs mt-1">Try adjusting your filters or search query</p>
          </div>
        ) : (
          paginated.map((decision) => (
            <DecisionCard
              key={decision.id}
              decision={decision}
              expanded={expandedId === decision.id}
              onToggle={() => handleToggle(decision.id)}
            />
          ))
        )}
      </div>

      {/* Pagination */}
      <Pagination page={page} totalPages={totalPages} onPage={setPage} />
    </div>
  )
}
