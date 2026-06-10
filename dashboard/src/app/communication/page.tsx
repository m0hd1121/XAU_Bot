'use client'

import { useState, useMemo } from 'react'
import {
  MessageSquare,
  ArrowRight,
  RefreshCw,
  Activity,
  TrendingUp,
  Brain,
  Bot,
} from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import PageHeader from '@/components/ui/PageHeader'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import Badge, { type BadgeVariant } from '@/components/ui/Badge'
import Button from '@/components/ui/Button'
import Spinner from '@/components/ui/Spinner'
import { apiClient } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { TradeDecision, MarketIntel, StrategyCandidate, AgentState } from '@/types'

// ─── Types ────────────────────────────────────────────────────────────────────

type Channel = 'market' | 'strategy' | 'trade' | 'system'

interface CommEvent {
  id: string
  timestamp: number
  channel: Channel
  from: string
  to: string
  type: string
  summary: string
  detail?: string
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const CH_STYLES: Record<Channel, string> = {
  market:   'border-amber-500/30 bg-amber-500/5 text-amber-400',
  strategy: 'border-sky-500/30 bg-sky-500/5 text-sky-400',
  trade:    'border-emerald-500/30 bg-emerald-500/5 text-emerald-400',
  system:   'border-zinc-700 bg-zinc-800/40 text-zinc-400',
}

const CH_DOT: Record<Channel, string> = {
  market:   'bg-amber-400',
  strategy: 'bg-sky-400',
  trade:    'bg-emerald-400',
  system:   'bg-zinc-500',
}

function fmtTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString()
}

function statusVariant(status: string): BadgeVariant {
  if (status === 'running') return 'success'
  if (status === 'error')   return 'danger'
  if (status === 'paused')  return 'warning'
  return 'default'
}

// ─── Agent flow card ──────────────────────────────────────────────────────────

function AgentFlowCard({
  agentKey,
  label,
  sub,
  borderColor,
  textColor,
  Icon,
  state,
}: {
  agentKey: string
  label: string
  sub: string
  borderColor: string
  textColor: string
  Icon: React.ElementType
  state?: AgentState
}) {
  return (
    <div className={cn('flex flex-col items-center gap-2 p-4 rounded-xl border bg-zinc-900 min-w-[110px]', borderColor)}>
      <Icon className={cn('w-6 h-6', textColor)} />
      <div className="text-center">
        <p className="text-sm font-semibold text-zinc-200">{label}</p>
        <p className="text-xs text-zinc-500">{sub}</p>
      </div>
      {state && (
        <Badge variant={statusVariant(state.status)} size="sm">
          {state.status}
        </Badge>
      )}
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

const CHANNEL_FILTERS = [
  { id: 'all',      label: 'All Channels' },
  { id: 'market',   label: 'Market Intel' },
  { id: 'strategy', label: 'Strategies' },
  { id: 'trade',    label: 'Trades' },
  { id: 'system',   label: 'System' },
]

export default function CommunicationPage() {
  const [channelFilter, setChannelFilter] = useState<string>('all')
  const [autoRefresh, setAutoRefresh]     = useState(true)

  const interval = autoRefresh ? 15_000 : (false as const)

  const { data: decisions, isLoading: decLoading, refetch: refetchDec } = useQuery({
    queryKey: ['decisions', 100],
    queryFn: () => apiClient.getRecentDecisions(100),
    refetchInterval: interval,
  })

  const { data: intel, isLoading: intelLoading, refetch: refetchIntel } = useQuery({
    queryKey: ['intel', 'history', 50],
    queryFn: () => apiClient.getIntelHistory(50),
    refetchInterval: autoRefresh ? 30_000 : false,
  })

  const { data: strategies, isLoading: stratLoading, refetch: refetchStrat } = useQuery({
    queryKey: ['strategies', 'candidates', 50],
    queryFn: () => apiClient.getStrategyCandidates(undefined, 50),
    refetchInterval: autoRefresh ? 60_000 : false,
  })

  const { data: agents } = useQuery({
    queryKey: ['agents'],
    queryFn: () => apiClient.getAllAgentStatus(),
    refetchInterval: interval,
  })

  const isLoading = decLoading || intelLoading || stratLoading

  const events = useMemo<CommEvent[]>(() => {
    const items: CommEvent[] = []

    intel?.forEach((i: MarketIntel) => {
      items.push({
        id:        `intel-${i.timestamp}`,
        timestamp:  i.timestamp,
        channel:   'market',
        from:      'Agent 2',
        to:        'Agent 3',
        type:      'MARKET_INTEL',
        summary:   `Regime: ${i.regime} | Risk: ${(i.risk_score * 100).toFixed(0)}%`,
        detail:    i.trend ? `Trend: ${i.trend}` : undefined,
      })
    })

    decisions?.forEach((d: TradeDecision) => {
      items.push({
        id:        `decision-${d.id}`,
        timestamp:  d.timestamp,
        channel:   'trade',
        from:      'Agent 3',
        to:        d.decision === 'EXECUTE' ? 'Broker' : 'Risk Filter',
        type:       d.decision,
        summary:
          d.decision === 'EXECUTE'
            ? `${d.explanation?.direction ?? '?'} @ ${d.explanation?.entry_price?.toFixed(2) ?? '?'}`
            : (d.reason ?? 'Skipped'),
        detail:    d.strategy_id ? `Strategy: ${d.strategy_id.slice(0, 12)}` : undefined,
      })
    })

    strategies
      ?.filter((s: StrategyCandidate) =>
        s.status === 'promoted' || s.status === 'validated' || s.status === 'shadow',
      )
      .forEach((s: StrategyCandidate) => {
        items.push({
          id:        `strategy-${s.genome_hash}`,
          timestamp:  s.created_at,
          channel:   'strategy',
          from:      'Agent 1',
          to:        s.status === 'promoted' ? 'Agent 3' : 'Validator',
          type:      `STRATEGY_${s.status.toUpperCase()}`,
          summary:   `Hash ${s.genome_hash.slice(0, 8)} | Score ${s.fitness.composite_score?.toFixed(3) ?? '?'}`,
          detail:    `PF ${s.fitness.profit_factor?.toFixed(2) ?? '?'} | WR ${s.fitness.win_rate != null ? (s.fitness.win_rate * 100).toFixed(1) : '?'}%`,
        })
      })

    agents &&
      Object.values(agents).forEach((a: AgentState) => {
        items.push({
          id:        `heartbeat-${a.agent_id}`,
          timestamp:  a.last_heartbeat,
          channel:   'system',
          from:       a.agent_id.charAt(0).toUpperCase() + a.agent_id.slice(1),
          to:        'System',
          type:      'HEARTBEAT',
          summary:   `Status: ${a.status} | ${a.current_task}`,
          detail:    `Uptime: ${Math.floor(a.uptime_seconds / 60)}m`,
        })
      })

    return items
      .filter((e) => channelFilter === 'all' || e.channel === channelFilter)
      .sort((a, b) => b.timestamp - a.timestamp)
  }, [decisions, intel, strategies, agents, channelFilter])

  function handleRefresh() {
    void refetchDec()
    void refetchIntel()
    void refetchStrat()
  }

  const agentDefs = [
    { key: 'agent1', label: 'Agent 1', sub: 'Research',     border: 'border-sky-500/40',     text: 'text-sky-400',     Icon: Brain },
    { key: 'agent2', label: 'Agent 2', sub: 'Intelligence', border: 'border-amber-500/40',   text: 'text-amber-400',   Icon: Activity },
    { key: 'agent3', label: 'Agent 3', sub: 'Trader',       border: 'border-emerald-500/40', text: 'text-emerald-400', Icon: TrendingUp },
  ]

  return (
    <div className="p-6 space-y-6">
      <PageHeader
        title="Agent Communication"
        subtitle="Real-time message flow between all three agents via the shared SQLite bus"
        icon={<MessageSquare className="w-5 h-5 text-sky-400" />}
        badge={{ text: 'Live', variant: 'success' }}
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant={autoRefresh ? 'primary' : 'outline'}
              size="sm"
              onClick={() => setAutoRefresh((v) => !v)}
            >
              {autoRefresh ? 'Auto-refresh On' : 'Auto-refresh Off'}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleRefresh}
              iconLeft={<RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />}
            >
              Refresh
            </Button>
          </div>
        }
      />

      {/* Agent flow diagram */}
      <Card>
        <CardContent className="pt-5">
          <div className="flex items-center justify-center gap-3 flex-wrap">
            {agentDefs.flatMap((ag, idx) => {
              const state = agents?.[ag.key as keyof typeof agents] as AgentState | undefined
              const card = (
                <AgentFlowCard
                  key={ag.key}
                  agentKey={ag.key}
                  label={ag.label}
                  sub={ag.sub}
                  borderColor={ag.border}
                  textColor={ag.text}
                  Icon={ag.Icon}
                  state={state}
                />
              )
              if (idx < agentDefs.length - 1) {
                return [
                  card,
                  <div key={`arrow-${idx}`} className="flex flex-col items-center gap-1 text-zinc-600">
                    <ArrowRight className="w-4 h-4" />
                    <span className="text-[10px]">{idx === 0 ? 'Strategies' : 'Intel'}</span>
                  </div>,
                ]
              }
              return [card]
            })}
          </div>

          {/* Legend */}
          <div className="flex items-center justify-center gap-4 mt-4 pt-4 border-t border-zinc-800 flex-wrap">
            {(['market', 'strategy', 'trade', 'system'] as Channel[]).map((ch) => (
              <span key={ch} className="flex items-center gap-1.5 text-xs text-zinc-500 capitalize">
                <span className={cn('w-2 h-2 rounded-full flex-shrink-0', CH_DOT[ch])} />
                {ch}
              </span>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Channel filter */}
      <div className="flex flex-wrap gap-1">
        {CHANNEL_FILTERS.map((f) => (
          <button
            key={f.id}
            onClick={() => setChannelFilter(f.id)}
            className={cn(
              'px-3 py-1.5 rounded-lg text-sm font-medium transition-colors border',
              channelFilter === f.id
                ? 'bg-amber-500/20 text-amber-400 border-amber-500/30'
                : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 border-transparent',
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Event feed */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm">
            <Bot className="w-4 h-4 text-sky-400" />
            {events.length} events
            {isLoading && <Spinner size="xs" />}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading && events.length === 0 ? (
            <div className="flex justify-center py-8">
              <Spinner />
            </div>
          ) : events.length === 0 ? (
            <p className="text-sm text-zinc-500 text-center py-8">
              No events in this channel
            </p>
          ) : (
            <div className="space-y-2 max-h-[600px] overflow-y-auto">
              {events.map((ev) => (
                <div
                  key={ev.id}
                  className={cn('flex gap-3 p-3 rounded-lg border', CH_STYLES[ev.channel])}
                >
                  <span className={cn('w-1.5 h-1.5 rounded-full flex-shrink-0 mt-1.5', CH_DOT[ev.channel])} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs font-mono font-semibold">{ev.type}</span>
                      <span className="text-xs text-zinc-500 flex items-center gap-1">
                        {ev.from}
                        <ArrowRight className="w-2.5 h-2.5" />
                        {ev.to}
                      </span>
                    </div>
                    <p className="text-xs text-zinc-300 mt-0.5">{ev.summary}</p>
                    {ev.detail && (
                      <p className="text-[10px] text-zinc-500 mt-0.5">{ev.detail}</p>
                    )}
                  </div>
                  <span className="text-[10px] text-zinc-600 flex-shrink-0 whitespace-nowrap">
                    {fmtTime(ev.timestamp)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
