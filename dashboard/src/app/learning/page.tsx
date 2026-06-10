'use client'

import { Brain, TrendingUp, CheckCircle, XCircle, Activity, RefreshCw, Zap } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import PageHeader from '@/components/ui/PageHeader'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import MetricTile from '@/components/ui/MetricTile'
import Badge, { type BadgeVariant } from '@/components/ui/Badge'
import Spinner from '@/components/ui/Spinner'
import Button from '@/components/ui/Button'
import { apiClient } from '@/lib/api'
import { cn } from '@/lib/utils'

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleString()
}

function outcomeBadgeVariant(outcome: string): BadgeVariant {
  if (outcome === 'win') return 'success'
  if (outcome === 'loss') return 'danger'
  return 'default'
}

export default function LearningPage() {
  const {
    data: stats,
    isLoading: statsLoading,
    refetch: refetchStats,
  } = useQuery({
    queryKey: ['learning', 'stats'],
    queryFn: () => apiClient.getLearningStats(),
    refetchInterval: 30_000,
  })

  const {
    data: eventsRaw,
    isLoading: eventsLoading,
    refetch: refetchEvents,
  } = useQuery<unknown[]>({
    queryKey: ['learning', 'events'],
    queryFn: () => apiClient.getLearningEvents(100),
    refetchInterval: 30_000,
  })
  const events: unknown[] = eventsRaw ?? []

  const isLoading = statsLoading || eventsLoading

  const enabled       = stats?.enabled as boolean | undefined
  const confidence    = stats?.confidence_score as number | undefined
  const accuracy      = stats?.accuracy as number | undefined
  const patternCount  = stats?.pattern_count as number | undefined
  const winRate       = stats?.win_rate_adjusted as number | undefined
  const totalEval     = stats?.total_evaluated as number | undefined
  const approved      = stats?.approved_count as number | undefined
  const rejected      = stats?.rejected_count as number | undefined

  function handleRefresh() {
    void refetchStats()
    void refetchEvents()
  }

  return (
    <div className="p-6 space-y-6">
      <PageHeader
        title="Learning Engine"
        subtitle="Self-learning confidence scores, pattern recognition and trade outcome tracking"
        icon={<Brain className="w-5 h-5 text-violet-400" />}
        badge={
          enabled === true
            ? { text: 'Active', variant: 'success' }
            : enabled === false
            ? { text: 'Disabled', variant: 'default' }
            : undefined
        }
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            iconLeft={<RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />}
          >
            Refresh
          </Button>
        }
      />

      {/* Key metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <MetricTile
          label="Confidence Score"
          value={confidence != null ? confidence.toFixed(3) : '—'}
          loading={statsLoading}
          icon={<Brain className="w-4 h-4" />}
          valueClassName={
            confidence != null
              ? confidence >= 0.7
                ? 'text-emerald-400'
                : confidence >= 0.5
                ? 'text-amber-400'
                : 'text-red-400'
              : undefined
          }
        />
        <MetricTile
          label="Accuracy"
          value={accuracy != null ? `${(accuracy * 100).toFixed(1)}%` : '—'}
          loading={statsLoading}
          icon={<CheckCircle className="w-4 h-4" />}
        />
        <MetricTile
          label="Patterns Learned"
          value={patternCount != null ? patternCount.toLocaleString() : '—'}
          loading={statsLoading}
          icon={<Activity className="w-4 h-4" />}
        />
        <MetricTile
          label="Adj. Win Rate"
          value={winRate != null ? `${(winRate * 100).toFixed(1)}%` : '—'}
          loading={statsLoading}
          icon={<TrendingUp className="w-4 h-4" />}
        />
        <MetricTile
          label="Total Evaluated"
          value={totalEval != null ? totalEval.toLocaleString() : '—'}
          loading={statsLoading}
        />
        <MetricTile
          label="Approved"
          value={approved != null ? approved.toLocaleString() : '—'}
          loading={statsLoading}
          valueClassName="text-emerald-400"
          icon={<CheckCircle className="w-4 h-4" />}
        />
        <MetricTile
          label="Rejected"
          value={rejected != null ? rejected.toLocaleString() : '—'}
          loading={statsLoading}
          valueClassName="text-red-400"
          icon={<XCircle className="w-4 h-4" />}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Event log */}
        <div className="lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-sm">
                <Zap className="w-4 h-4 text-violet-400" />
                Learning Events
                {eventsLoading && <Spinner size="xs" />}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {eventsLoading && events.length === 0 ? (
                <div className="flex justify-center py-8">
                  <Spinner />
                </div>
              ) : events.length > 0 ? (
                <div className="space-y-2 max-h-[500px] overflow-y-auto">
                  {events.map((ev, i) => {
                    const e = ev as Record<string, unknown>
                    const ts          = e.timestamp as number | undefined
                    const evType      = e.event_type as string | undefined
                    const outcome     = e.outcome as string | undefined
                    const confBefore  = e.confidence_before as number | undefined
                    const confAfter   = e.confidence_after as number | undefined
                    const pnl         = e.pnl as number | undefined
                    const delta       = confBefore != null && confAfter != null ? confAfter - confBefore : null

                    return (
                      <div
                        key={i}
                        className="flex items-start gap-3 p-2.5 rounded-lg bg-zinc-800/50 border border-zinc-800"
                      >
                        <span
                          className={cn(
                            'w-1.5 h-1.5 rounded-full flex-shrink-0 mt-1.5',
                            outcome === 'win'
                              ? 'bg-emerald-400'
                              : outcome === 'loss'
                              ? 'bg-red-400'
                              : 'bg-zinc-500',
                          )}
                        />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-xs font-medium text-zinc-200">
                              {evType ?? 'event'}
                            </span>
                            {outcome && (
                              <Badge variant={outcomeBadgeVariant(outcome)} size="sm">
                                {outcome}
                              </Badge>
                            )}
                            {pnl != null && (
                              <span
                                className={cn(
                                  'text-xs font-mono',
                                  pnl >= 0 ? 'text-emerald-400' : 'text-red-400',
                                )}
                              >
                                {pnl >= 0 ? '+' : ''}
                                {pnl.toFixed(2)}
                              </span>
                            )}
                          </div>
                          {confBefore != null && confAfter != null && (
                            <p className="text-xs text-zinc-500 mt-0.5">
                              Confidence: {confBefore.toFixed(3)} → {confAfter.toFixed(3)}
                              {delta != null && (
                                <span
                                  className={cn(
                                    'ml-1',
                                    delta > 0 ? 'text-emerald-400' : 'text-red-400',
                                  )}
                                >
                                  ({delta > 0 ? '+' : ''}
                                  {delta.toFixed(3)})
                                </span>
                              )}
                            </p>
                          )}
                        </div>
                        {ts != null && (
                          <span className="text-[10px] text-zinc-600 flex-shrink-0 whitespace-nowrap">
                            {formatTime(ts)}
                          </span>
                        )}
                      </div>
                    )
                  })}
                </div>
              ) : (
                <p className="text-sm text-zinc-500 text-center py-8">
                  No learning events yet
                </p>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Raw stats panel */}
        <div>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-sm">
                <Brain className="w-4 h-4 text-violet-400" />
                Engine State
              </CardTitle>
            </CardHeader>
            <CardContent>
              {statsLoading ? (
                <div className="flex justify-center py-8">
                  <Spinner />
                </div>
              ) : stats && Object.keys(stats).length > 0 ? (
                <div className="space-y-0">
                  {Object.entries(stats).map(([k, v]) => (
                    <div
                      key={k}
                      className="flex items-center justify-between gap-2 py-1.5 border-b border-zinc-800 last:border-0"
                    >
                      <span className="text-xs text-zinc-500 font-mono">{k}</span>
                      <span className="text-xs text-zinc-200 font-mono truncate max-w-[120px]">
                        {typeof v === 'boolean'
                          ? v
                            ? '✓ true'
                            : '✗ false'
                          : typeof v === 'number'
                          ? v.toFixed(4)
                          : String(v ?? '—')}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-zinc-500 text-center py-8">
                  Learning engine is disabled or has no data
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
