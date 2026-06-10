'use client'

import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { cn } from '@/lib/utils'
import { apiClient } from '@/lib/api'
import type { StrategyCandidate, StrategyStatus } from '@/types'
import { PageHeader } from '@/components/ui/PageHeader'
import { MetricTile } from '@/components/ui/MetricTile'
import { Button } from '@/components/ui/Button'
import { Spinner } from '@/components/ui/Spinner'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { StrategyTable } from '@/components/strategies/StrategyTable'
import { StrategyDetail } from '@/components/strategies/StrategyDetail'
import { RefreshCw, Crown, TrendingUp, CheckCircle, XCircle } from 'lucide-react'

// ─── Filter pill ─────────────────────────────────────────────────────────────

type StatusFilter = 'all' | StrategyStatus

const STATUS_FILTERS: { key: StatusFilter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'pending', label: 'Pending' },
  { key: 'validating', label: 'Validating' },
  { key: 'validated', label: 'Validated' },
  { key: 'shadow', label: 'Shadow' },
  { key: 'promoted', label: 'Promoted' },
  { key: 'rejected', label: 'Rejected' },
]

type SortMode = 'newest' | 'best_score' | 'generation'

const SORT_OPTIONS: { key: SortMode; label: string }[] = [
  { key: 'newest', label: 'Newest' },
  { key: 'best_score', label: 'Best Score' },
  { key: 'generation', label: 'Generation' },
]

function formatCurrency(v: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
  }).format(v)
}

// ─── Promoted strategy spotlight ─────────────────────────────────────────────

function PromotedSpotlight({
  strategy,
  onView,
}: {
  strategy: StrategyCandidate
  onView: () => void
}) {
  const f = strategy.fitness
  return (
    <Card className="bg-gradient-to-br from-emerald-950/60 to-zinc-900 border border-emerald-500/30 rounded-xl overflow-hidden">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Crown className="w-5 h-5 text-emerald-400" />
            <CardTitle className="text-emerald-300 text-sm font-semibold">
              Active Strategy
            </CardTitle>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs text-emerald-400 hover:bg-emerald-500/10"
            onClick={onView}
          >
            View Details
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="flex items-start gap-4">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-1">
              <span className="font-mono text-amber-400 text-sm">
                {strategy.genome_hash.slice(0, 16)}…
              </span>
              <span className="text-zinc-500 text-xs">Gen {strategy.generation}</span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-3">
              <div>
                <p className="text-zinc-500 text-[10px] uppercase">Score</p>
                <p className="text-emerald-400 font-mono font-bold text-lg">
                  {f.composite_score != null ? (f.composite_score * 100).toFixed(0) : '—'}
                </p>
              </div>
              <div>
                <p className="text-zinc-500 text-[10px] uppercase">Expectancy</p>
                <p className="text-zinc-100 font-mono text-sm">
                  {f.expectancy != null ? formatCurrency(f.expectancy) : '—'}
                </p>
              </div>
              <div>
                <p className="text-zinc-500 text-[10px] uppercase">Win Rate</p>
                <p className="text-zinc-100 font-mono text-sm">
                  {f.win_rate != null ? `${(f.win_rate * 100).toFixed(1)}%` : '—'}
                </p>
              </div>
              <div>
                <p className="text-zinc-500 text-[10px] uppercase">Profit Factor</p>
                <p className="text-zinc-100 font-mono text-sm">
                  {f.profit_factor != null ? `${f.profit_factor.toFixed(2)}x` : '—'}
                </p>
              </div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function StrategiesPage() {
  const queryClient = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [sortMode, setSortMode] = useState<SortMode>('newest')
  const [minScore, setMinScore] = useState<number>(0)
  const [spotlightOpen, setSpotlightOpen] = useState(false)
  const [spotlightStrategy, setSpotlightStrategy] = useState<StrategyCandidate | null>(null)

  // ── Data ────────────────────────────────────────────────────────────────

  const {
    data: allStrategies = [],
    isLoading,
    isFetching,
    refetch,
  } = useQuery({
    queryKey: ['strategies', 'all'],
    queryFn: () => apiClient.getStrategyCandidates(undefined, 100),
    refetchInterval: 30_000,
  })

  const { data: validatedStrategies = [] } = useQuery({
    queryKey: ['strategies', 'validated'],
    queryFn: () => apiClient.getValidatedStrategies(),
    refetchInterval: 30_000,
  })

  // ── Mutations ────────────────────────────────────────────────────────────

  const promoteMutation = useMutation({
    mutationFn: (hash: string) => apiClient.promoteStrategy(hash),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['strategies'] })
    },
  })

  const rejectMutation = useMutation({
    mutationFn: (hash: string) => apiClient.rejectStrategy(hash),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['strategies'] })
    },
  })

  // ── Computed ─────────────────────────────────────────────────────────────

  const promotedStrategy = useMemo(
    () => allStrategies.find((s) => s.status === 'promoted') ?? null,
    [allStrategies]
  )

  const stats = useMemo(() => {
    const total = allStrategies.length
    const promoted = allStrategies.filter((s) => s.status === 'promoted').length
    const validated = allStrategies.filter(
      (s) => s.status === 'validated' || s.status === 'shadow'
    ).length
    const rejected = allStrategies.filter((s) => s.status === 'rejected').length
    return { total, promoted, validated, rejected }
  }, [allStrategies])

  const filtered = useMemo(() => {
    let arr = allStrategies.filter((s) => {
      if (statusFilter !== 'all' && s.status !== statusFilter) return false
      if (minScore > 0 && (s.fitness.composite_score ?? 0) < minScore) return false
      return true
    })

    if (sortMode === 'best_score') {
      arr = [...arr].sort(
        (a, b) => (b.fitness.composite_score ?? -1) - (a.fitness.composite_score ?? -1)
      )
    } else if (sortMode === 'generation') {
      arr = [...arr].sort((a, b) => b.generation - a.generation)
    } else {
      arr = [...arr].sort((a, b) => b.created_at - a.created_at)
    }

    return arr
  }, [allStrategies, statusFilter, minScore, sortMode])

  // ── Handlers ─────────────────────────────────────────────────────────────

  function openSpotlight(strategy: StrategyCandidate) {
    setSpotlightStrategy(strategy)
    setSpotlightOpen(true)
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="max-w-[1400px] mx-auto px-4 py-6 space-y-6">
        {/* Page header */}
        <PageHeader
          title="Strategy Explorer"
          subtitle="All generated strategies and their validation status"
          actions={
            <Button
              variant="ghost"
              size="sm"
              className="h-9 text-zinc-400 hover:text-zinc-100 border border-zinc-700 hover:border-zinc-500"
              onClick={() => void refetch()}
              disabled={isFetching}
            >
              <RefreshCw className={cn('w-4 h-4 mr-1.5', isFetching && 'animate-spin')} />
              Refresh
            </Button>
          }
        />

        {/* Promoted spotlight */}
        {promotedStrategy && (
          <PromotedSpotlight
            strategy={promotedStrategy}
            onView={() => openSpotlight(promotedStrategy)}
          />
        )}

        {/* Stats row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <MetricTile
            label="Total Strategies"
            value={String(stats.total)}
            icon={<TrendingUp className="w-4 h-4" />}
          />
          <MetricTile
            label="Promoted"
            value={String(stats.promoted)}
            valueClassName="text-emerald-400"
            icon={<Crown className="w-4 h-4 text-emerald-400" />}
          />
          <MetricTile
            label="Validated"
            value={String(stats.validated)}
            valueClassName="text-sky-400"
            icon={<CheckCircle className="w-4 h-4 text-sky-400" />}
          />
          <MetricTile
            label="Rejected"
            value={String(stats.rejected)}
            valueClassName="text-red-400"
            icon={<XCircle className="w-4 h-4 text-red-400" />}
          />
        </div>

        {/* Filter bar */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-4">
          {/* Status pills */}
          <div className="flex items-center gap-2 flex-wrap">
            {STATUS_FILTERS.map(({ key, label }) => (
              <button
                key={key}
                className={cn(
                  'px-3 py-1 rounded-full text-xs font-medium border transition-colors',
                  statusFilter === key
                    ? 'bg-amber-500/20 text-amber-400 border-amber-500/30'
                    : 'bg-zinc-800 text-zinc-400 border-zinc-700 hover:border-zinc-500 hover:text-zinc-200'
                )}
                onClick={() => {
                  setStatusFilter(key)
                }}
              >
                {label}
                {key !== 'all' && (
                  <span className="ml-1.5 text-zinc-600">
                    ({allStrategies.filter((s) => s.status === key).length})
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Second row: score filter + sort */}
          <div className="flex items-center gap-4 flex-wrap">
            <div className="flex items-center gap-2">
              <label className="text-zinc-500 text-xs">Min Score:</label>
              <input
                type="range"
                min={0}
                max={0.9}
                step={0.1}
                value={minScore}
                onChange={(e) => setMinScore(Number(e.target.value))}
                className="w-24 accent-amber-500"
              />
              <span className="text-zinc-300 text-xs font-mono w-8">
                {minScore > 0 ? minScore.toFixed(1) : 'Off'}
              </span>
            </div>

            <div className="flex items-center gap-2 ml-auto">
              <span className="text-zinc-500 text-xs">Sort:</span>
              {SORT_OPTIONS.map(({ key, label }) => (
                <button
                  key={key}
                  className={cn(
                    'px-2.5 py-1 rounded text-xs font-medium transition-colors',
                    sortMode === key
                      ? 'bg-zinc-700 text-zinc-100'
                      : 'text-zinc-500 hover:text-zinc-300'
                  )}
                  onClick={() => setSortMode(key)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Table */}
        <StrategyTable
          strategies={filtered}
          loading={isLoading}
          onPromote={(hash) => promoteMutation.mutate(hash)}
          onReject={(hash) => rejectMutation.mutate(hash)}
          promotePending={promoteMutation.isPending}
          rejectPending={rejectMutation.isPending}
        />
      </div>

      {/* Spotlight detail modal */}
      <StrategyDetail
        strategy={spotlightStrategy}
        open={spotlightOpen}
        onClose={() => setSpotlightOpen(false)}
        onPromote={(hash) => promoteMutation.mutate(hash)}
        onReject={(hash) => rejectMutation.mutate(hash)}
        promotePending={promoteMutation.isPending}
        rejectPending={rejectMutation.isPending}
      />
    </div>
  )
}
