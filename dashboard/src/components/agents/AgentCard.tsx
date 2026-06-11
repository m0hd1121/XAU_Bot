'use client'

import { AgentState, AgentId, AgentStatus } from '@/types'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardContent } from '@/components/ui/Card'
import { StatusDot } from '@/components/ui/StatusDot'
import {
  RefreshCw,
  Pause,
  Play,
  Square,
  Cpu,
  TrendingUp,
  BarChart2,
  Activity,
} from 'lucide-react'

export interface AgentCardProps {
  agent: AgentState
  onControl: (command: 'start' | 'pause' | 'resume' | 'stop' | 'restart') => void
  isPending?: boolean
  className?: string
}

const AGENT_LABELS: Record<AgentId, { title: string; subtitle: string }> = {
  agent1: { title: 'Agent 1', subtitle: 'Research' },
  agent2: { title: 'Agent 2', subtitle: 'Intelligence' },
  agent3: { title: 'Agent 3', subtitle: 'Trader' },
}

const STATUS_BORDER: Record<AgentStatus, string> = {
  running: 'border-l-emerald-500',
  paused: 'border-l-amber-500',
  error: 'border-l-red-500',
  stopped: 'border-l-zinc-600',
}

const STATUS_BADGE_VARIANT: Record<AgentStatus, string> = {
  running: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  paused: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  error: 'bg-red-500/10 text-red-400 border-red-500/20',
  stopped: 'bg-zinc-800 text-zinc-400 border-zinc-700',
}

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return `${h}h ${m}m`
}

function formatHeartbeat(ts: number): string {
  const diff = Math.floor((Date.now() / 1000) - ts)
  if (diff < 5) return 'just now'
  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  return `${Math.floor(diff / 3600)}h ago`
}

function Agent1Metrics({ metrics }: { metrics: AgentState['metrics'] }) {
  return (
    <div className="grid grid-cols-3 gap-2 mt-3">
      <div className="flex flex-col items-center bg-zinc-800/50 rounded-lg py-2 px-1">
        <span className="text-zinc-500 text-[10px] uppercase tracking-wide">Gen</span>
        <span className="text-zinc-100 text-sm font-mono font-medium mt-0.5">
          {metrics.generation ?? '—'}
        </span>
      </div>
      <div className="flex flex-col items-center bg-zinc-800/50 rounded-lg py-2 px-1">
        <span className="text-zinc-500 text-[10px] uppercase tracking-wide">Score</span>
        <span className="text-zinc-100 text-sm font-mono font-medium mt-0.5">
          {metrics.best_score != null ? metrics.best_score.toFixed(2) : '—'}
        </span>
      </div>
      <div className="flex flex-col items-center bg-zinc-800/50 rounded-lg py-2 px-1">
        <span className="text-zinc-500 text-[10px] uppercase tracking-wide">Pop</span>
        <span className="text-zinc-100 text-sm font-mono font-medium mt-0.5">
          {metrics.population_size ?? '—'}
        </span>
      </div>
    </div>
  )
}

function Agent2Metrics({ metrics }: { metrics: AgentState['metrics'] }) {
  const riskScore = metrics.risk_score as number | undefined
  const riskColor =
    riskScore == null
      ? 'text-zinc-400'
      : riskScore > 0.7
      ? 'text-red-400'
      : riskScore > 0.4
      ? 'text-amber-400'
      : 'text-emerald-400'

  return (
    <div className="grid grid-cols-2 gap-2 mt-3">
      <div className="flex flex-col bg-zinc-800/50 rounded-lg py-2 px-3">
        <span className="text-zinc-500 text-[10px] uppercase tracking-wide">Regime</span>
        <span className="text-zinc-100 text-sm font-medium mt-0.5 truncate">
          {(metrics.regime as string | undefined) ?? '—'}
        </span>
      </div>
      <div className="flex flex-col bg-zinc-800/50 rounded-lg py-2 px-3">
        <span className="text-zinc-500 text-[10px] uppercase tracking-wide">Risk</span>
        <span className={cn('text-sm font-mono font-medium mt-0.5', riskColor)}>
          {riskScore != null ? riskScore.toFixed(2) : '—'}
          <span className="text-zinc-500 text-[10px]"> /1.0</span>
        </span>
      </div>
    </div>
  )
}

function Agent3Metrics({ metrics }: { metrics: AgentState['metrics'] }) {
  const openTrades = metrics.open_trades_count as number | undefined
  const consecLosses = metrics.consecutive_losses as number | undefined

  return (
    <div className="grid grid-cols-2 gap-2 mt-3">
      <div className="flex flex-col bg-zinc-800/50 rounded-lg py-2 px-3">
        <span className="text-zinc-500 text-[10px] uppercase tracking-wide">Open</span>
        <span className="text-zinc-100 text-sm font-mono font-medium mt-0.5">
          {openTrades ?? '—'} <span className="text-zinc-500 text-[10px]">trades</span>
        </span>
      </div>
      <div className="flex flex-col bg-zinc-800/50 rounded-lg py-2 px-3">
        <span className="text-zinc-500 text-[10px] uppercase tracking-wide">Consec Loss</span>
        <span
          className={cn(
            'text-sm font-mono font-medium mt-0.5',
            consecLosses != null && consecLosses >= 3 ? 'text-red-400' : 'text-zinc-100'
          )}
        >
          {consecLosses ?? '—'}
        </span>
      </div>
    </div>
  )
}

export function AgentCard({ agent, onControl, isPending = false, className }: AgentCardProps) {
  const label = AGENT_LABELS[agent.agent_id]
  const borderClass = STATUS_BORDER[agent.status]
  const badgeClass = STATUS_BADGE_VARIANT[agent.status]

  const canStart = agent.status !== 'running'
  const canPause = agent.status === 'running'
  const canResume = false  // Start covers this — Resume only works if process is alive
  const canStop = agent.status === 'running' || agent.status === 'paused'

  return (
    <Card
      className={cn(
        'bg-zinc-900 border border-zinc-800 rounded-xl border-l-4 overflow-hidden',
        borderClass,
        className
      )}
    >
      <CardContent className="p-4">
        {/* Header */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <StatusDot status={agent.status} size="lg" />
            <div className="min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="text-zinc-100 font-semibold text-sm">{label.title}</span>
                <span className="text-zinc-500 text-sm">–</span>
                <span className="text-zinc-400 text-sm">{label.subtitle}</span>
              </div>
            </div>
          </div>
          <span
            className={cn(
              'inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium border flex-shrink-0',
              badgeClass
            )}
          >
            {agent.status}
          </span>
        </div>

        {/* Current task */}
        <p className="mt-2 text-zinc-500 text-xs italic truncate" title={agent.current_task}>
          {agent.current_task || 'Idle'}
        </p>

        {/* Agent-specific metrics */}
        {agent.agent_id === 'agent1' && <Agent1Metrics metrics={agent.metrics} />}
        {agent.agent_id === 'agent2' && <Agent2Metrics metrics={agent.metrics} />}
        {agent.agent_id === 'agent3' && <Agent3Metrics metrics={agent.metrics} />}

        {/* Cycle / error counts */}
        <div className="flex items-center gap-3 mt-3">
          {agent.metrics.cycle_count != null && (
            <div className="flex items-center gap-1 text-zinc-500 text-xs">
              <Activity className="w-3 h-3" />
              <span>{(agent.metrics.cycle_count as number).toLocaleString()} cycles</span>
            </div>
          )}
          {agent.metrics.error_count != null && (agent.metrics.error_count as number) > 0 && (
            <div className="flex items-center gap-1 text-red-400 text-xs">
              <span>{agent.metrics.error_count as number} errors</span>
            </div>
          )}
        </div>

        {/* Uptime & heartbeat */}
        <div className="flex items-center justify-between mt-2">
          <span className="text-zinc-600 text-[10px]">
            Uptime: {formatUptime(agent.uptime_seconds)}
          </span>
          <span className="text-zinc-600 text-[10px]">
            ♥ {formatHeartbeat(agent.last_heartbeat)}
          </span>
        </div>

        {/* Control buttons */}
        <div className="flex items-center gap-1.5 mt-3 pt-3 border-t border-zinc-800">
          {canStart && (
            <Button
              variant="ghost"
              size="sm"
              className="flex-1 h-7 text-xs text-emerald-400 hover:bg-emerald-500/10 hover:text-emerald-300"
              onClick={() => onControl('start')}
              disabled={isPending}
            >
              <Play className="w-3 h-3 mr-1" />
              Start
            </Button>
          )}
          {canPause && (
            <Button
              variant="ghost"
              size="sm"
              className="flex-1 h-7 text-xs text-amber-400 hover:bg-amber-500/10 hover:text-amber-300"
              onClick={() => onControl('pause')}
              disabled={isPending}
            >
              <Pause className="w-3 h-3 mr-1" />
              Pause
            </Button>
          )}
          {canResume && (
            <Button
              variant="ghost"
              size="sm"
              className="flex-1 h-7 text-xs text-emerald-400 hover:bg-emerald-500/10 hover:text-emerald-300"
              onClick={() => onControl('resume')}
              disabled={isPending}
            >
              <Play className="w-3 h-3 mr-1" />
              Resume
            </Button>
          )}
          {canStop && (
            <Button
              variant="ghost"
              size="sm"
              className="flex-1 h-7 text-xs text-red-400 hover:bg-red-500/10 hover:text-red-300"
              onClick={() => onControl('stop')}
              disabled={isPending}
            >
              <Square className="w-3 h-3 mr-1" />
              Stop
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            className="flex-1 h-7 text-xs text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
            onClick={() => onControl('restart')}
            disabled={isPending}
          >
            <RefreshCw className={cn('w-3 h-3 mr-1', isPending && 'animate-spin')} />
            Restart
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
