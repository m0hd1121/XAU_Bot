'use client'

import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Activity,
  AlertTriangle,
  Play,
  Square,
  RefreshCw,
  MessageSquare,
  Zap,
  Database,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { AgentState, AgentId, AgentStatus } from '@/types'
import { apiClient } from '@/lib/api'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { PageHeader } from '@/components/ui/PageHeader'
import { Spinner } from '@/components/ui/Spinner'
import { AgentCard } from '@/components/agents/AgentCard'
import { useAllAgents, useControlAgent } from '@/hooks/useApi'

// ── Agent communication diagram ───────────────────────────────────────────────
interface DiagramNodeProps {
  label: string
  sublabel: string
  status: AgentStatus | 'unknown'
  x: number
  y: number
}

const STATUS_COLORS: Record<AgentStatus | 'unknown', { fill: string; stroke: string; text: string }> = {
  running: { fill: '#052e16', stroke: '#34d399', text: '#34d399' },
  paused: { fill: '#451a03', stroke: '#f59e0b', text: '#f59e0b' },
  error: { fill: '#450a0a', stroke: '#f87171', text: '#f87171' },
  stopped: { fill: '#1c1c1e', stroke: '#3f3f46', text: '#a1a1aa' },
  unknown: { fill: '#18181b', stroke: '#3f3f46', text: '#71717a' },
}

function AgentCommunicationDiagram({ agents }: { agents: AgentState[] }) {
  const agentMap = agents.reduce<Record<string, AgentState>>(
    (acc, a) => ({ ...acc, [a.agent_id]: a }),
    {}
  )

  function statusFor(id: AgentId): AgentStatus | 'unknown' {
    return agentMap[id]?.status ?? 'unknown'
  }

  const s1 = STATUS_COLORS[statusFor('agent1')]
  const s2 = STATUS_COLORS[statusFor('agent2')]
  const s3 = STATUS_COLORS[statusFor('agent3')]

  // SVG dimensions
  const W = 480
  const H = 280

  // Node centers
  const A1 = { x: 80, y: 80 }
  const A2 = { x: 80, y: 200 }
  const A3 = { x: 360, y: 140 }

  const nodeW = 110
  const nodeH = 52
  const r = 8

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
      <div className="flex items-center gap-2 mb-4">
        <Zap className="w-4 h-4 text-zinc-400" />
        <h3 className="text-sm font-medium text-zinc-400">Agent Communication Flow</h3>
      </div>
      <div className="overflow-x-auto flex justify-center">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="w-full max-w-lg"
          style={{ minWidth: 320 }}
          aria-label="Agent communication diagram"
        >
          <defs>
            {/* Animated dash arrow: agent1 → agent3 */}
            <marker id="arrowGreen" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
              <path d="M0,0 L0,6 L8,3 z" fill="#34d399" opacity="0.7" />
            </marker>
            <marker id="arrowAmber" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
              <path d="M0,0 L0,6 L8,3 z" fill="#f59e0b" opacity="0.7" />
            </marker>
            <marker id="arrowZinc" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
              <path d="M0,0 L0,6 L8,3 z" fill="#71717a" opacity="0.7" />
            </marker>
          </defs>

          {/* ── Arrows ── */}
          {/* Agent 1 → Agent 3: strategy */}
          <line
            x1={A1.x + nodeW}
            y1={A1.y + nodeH / 2}
            x2={A3.x}
            y2={A3.y + nodeH / 2 - 14}
            stroke="#34d399"
            strokeWidth="1.5"
            strokeDasharray="6,3"
            markerEnd="url(#arrowGreen)"
            opacity="0.6"
          >
            <animate attributeName="stroke-dashoffset" from="0" to="-18" dur="1.5s" repeatCount="indefinite" />
          </line>

          {/* Agent 2 → Agent 3: market intel */}
          <line
            x1={A2.x + nodeW}
            y1={A2.y + nodeH / 2}
            x2={A3.x}
            y2={A3.y + nodeH / 2 + 14}
            stroke="#f59e0b"
            strokeWidth="1.5"
            strokeDasharray="6,3"
            markerEnd="url(#arrowAmber)"
            opacity="0.6"
          >
            <animate attributeName="stroke-dashoffset" from="0" to="-18" dur="1.8s" repeatCount="indefinite" />
          </line>

          {/* Agent 3 → Agent 1: trade feedback (curved, going back) */}
          <path
            d={`M ${A3.x} ${A3.y + nodeH / 2 - 20} Q ${W / 2} ${-10} ${A1.x + nodeW / 2} ${A1.y}`}
            fill="none"
            stroke="#71717a"
            strokeWidth="1.5"
            strokeDasharray="5,4"
            markerEnd="url(#arrowZinc)"
            opacity="0.45"
          >
            <animate attributeName="stroke-dashoffset" from="0" to="-18" dur="2.2s" repeatCount="indefinite" />
          </path>

          {/* ── Arrow labels ── */}
          <text x="210" y="78" fill="#34d399" fontSize="9" opacity="0.8" textAnchor="middle">
            strategy
          </text>
          <text x="210" y="210" fill="#f59e0b" fontSize="9" opacity="0.8" textAnchor="middle">
            market intel
          </text>
          <text x="240" y="18" fill="#71717a" fontSize="9" opacity="0.7" textAnchor="middle">
            trade feedback
          </text>

          {/* ── Nodes ── */}
          {/* Agent 1 */}
          <rect
            x={A1.x}
            y={A1.y}
            width={nodeW}
            height={nodeH}
            rx={r}
            fill={s1.fill}
            stroke={s1.stroke}
            strokeWidth="1.5"
          />
          <text x={A1.x + nodeW / 2} y={A1.y + 18} fill={s1.text} fontSize="11" fontWeight="600" textAnchor="middle">
            Agent 1
          </text>
          <text x={A1.x + nodeW / 2} y={A1.y + 34} fill="#71717a" fontSize="9" textAnchor="middle">
            Research
          </text>
          <circle cx={A1.x + nodeW - 10} cy={A1.y + 10} r="4" fill={s1.stroke} opacity="0.8">
            {statusFor('agent1') === 'running' && (
              <animate attributeName="opacity" values="0.8;0.2;0.8" dur="2s" repeatCount="indefinite" />
            )}
          </circle>

          {/* Agent 2 */}
          <rect
            x={A2.x}
            y={A2.y}
            width={nodeW}
            height={nodeH}
            rx={r}
            fill={s2.fill}
            stroke={s2.stroke}
            strokeWidth="1.5"
          />
          <text x={A2.x + nodeW / 2} y={A2.y + 18} fill={s2.text} fontSize="11" fontWeight="600" textAnchor="middle">
            Agent 2
          </text>
          <text x={A2.x + nodeW / 2} y={A2.y + 34} fill="#71717a" fontSize="9" textAnchor="middle">
            Intelligence
          </text>
          <circle cx={A2.x + nodeW - 10} cy={A2.y + 10} r="4" fill={s2.stroke} opacity="0.8">
            {statusFor('agent2') === 'running' && (
              <animate attributeName="opacity" values="0.8;0.2;0.8" dur="2s" repeatCount="indefinite" />
            )}
          </circle>

          {/* Agent 3 */}
          <rect
            x={A3.x}
            y={A3.y}
            width={nodeW}
            height={nodeH}
            rx={r}
            fill={s3.fill}
            stroke={s3.stroke}
            strokeWidth="1.5"
          />
          <text x={A3.x + nodeW / 2} y={A3.y + 18} fill={s3.text} fontSize="11" fontWeight="600" textAnchor="middle">
            Agent 3
          </text>
          <text x={A3.x + nodeW / 2} y={A3.y + 34} fill="#71717a" fontSize="9" textAnchor="middle">
            Trader
          </text>
          <circle cx={A3.x + nodeW - 10} cy={A3.y + 10} r="4" fill={s3.stroke} opacity="0.8">
            {statusFor('agent3') === 'running' && (
              <animate attributeName="opacity" values="0.8;0.2;0.8" dur="2s" repeatCount="indefinite" />
            )}
          </circle>

          {/* ── Message Bus Bar ── */}
          <rect x={W / 2 - 60} y={H - 40} width={120} height={28} rx={6} fill="#27272a" stroke="#3f3f46" strokeWidth="1" />
          <text x={W / 2} y={H - 22} fill="#71717a" fontSize="10" textAnchor="middle">
            Message Bus (SQLite)
          </text>
          {/* Bus connection lines */}
          {[A1, A2, A3].map((node, i) => (
            <line
              key={i}
              x1={node.x + nodeW / 2}
              y1={node.y + nodeH}
              x2={W / 2}
              y2={H - 40}
              stroke="#3f3f46"
              strokeWidth="1"
              strokeDasharray="3,3"
              opacity="0.5"
            />
          ))}
        </svg>
      </div>
    </div>
  )
}

// ── Message bus stats ─────────────────────────────────────────────────────────
interface AgentsStatusData {
  agents: AgentState[]
  message_bus?: {
    total_events?: number
    pending_events?: number
    channels?: Record<string, number>
  }
}

function MessageBusStats({ data }: { data: AgentsStatusData | undefined }) {
  const bus = data?.message_bus
  const agents = data?.agents ?? []

  const totalCycles = agents.reduce(
    (sum, a) => sum + ((a.metrics.cycle_count as number | undefined) ?? 0),
    0
  )
  const totalErrors = agents.reduce(
    (sum, a) => sum + ((a.metrics.error_count as number | undefined) ?? 0),
    0
  )

  return (
    <Card className="bg-zinc-900 border border-zinc-800 rounded-xl">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-zinc-400 flex items-center gap-2">
          <MessageSquare className="w-4 h-4" />
          Message Bus Stats
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="bg-zinc-800/50 rounded-lg p-3">
            <p className="text-zinc-500 text-[10px] uppercase tracking-wide">Total Events</p>
            <p className="text-zinc-100 text-xl font-mono font-semibold mt-1">
              {bus?.total_events != null ? bus.total_events.toLocaleString() : '—'}
            </p>
          </div>
          <div className="bg-zinc-800/50 rounded-lg p-3">
            <p className="text-zinc-500 text-[10px] uppercase tracking-wide">Pending</p>
            <p className="text-zinc-100 text-xl font-mono font-semibold mt-1">
              {bus?.pending_events != null ? bus.pending_events : '—'}
            </p>
          </div>
          <div className="bg-zinc-800/50 rounded-lg p-3">
            <p className="text-zinc-500 text-[10px] uppercase tracking-wide">Total Cycles</p>
            <p className="text-zinc-100 text-xl font-mono font-semibold mt-1">
              {totalCycles.toLocaleString()}
            </p>
          </div>
          <div className="bg-zinc-800/50 rounded-lg p-3">
            <p className="text-zinc-500 text-[10px] uppercase tracking-wide">Errors</p>
            <p
              className={cn(
                'text-xl font-mono font-semibold mt-1',
                totalErrors > 0 ? 'text-red-400' : 'text-zinc-100'
              )}
            >
              {totalErrors}
            </p>
          </div>
        </div>

        {bus?.channels && Object.keys(bus.channels).length > 0 && (
          <div className="mt-3 pt-3 border-t border-zinc-800">
            <p className="text-zinc-500 text-[10px] uppercase tracking-wide mb-2">Channels</p>
            <div className="flex flex-wrap gap-2">
              {Object.entries(bus.channels).map(([ch, count]) => (
                <span
                  key={ch}
                  className="inline-flex items-center gap-1.5 bg-zinc-800 rounded px-2 py-1 text-xs"
                >
                  <span className="text-zinc-400 font-mono">{ch}</span>
                  <span className="text-zinc-600">·</span>
                  <span className="text-zinc-300 font-mono">{count}</span>
                </span>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── Main page ────────────────────────────────────────────────────────────────
export default function AgentsPage() {
  const queryClient = useQueryClient()
  const [confirmAllStop, setConfirmAllStop] = useState(false)

  const { data: agents = [], isLoading, error, refetch } = useAllAgents()
  const { mutate: controlAgent, isPending: controlPending } = useControlAgent()

  // Poll every 10s
  useEffect(() => {
    const timer = setInterval(() => refetch(), 10_000)
    return () => clearInterval(timer)
  }, [refetch])

  // Derive summary
  const runningCount = agents.filter((a) => a.status === 'running').length
  const allStopped = agents.every((a) => a.status === 'stopped' || a.status === 'error')
  const anyRunning = agents.some((a) => a.status === 'running' || a.status === 'paused')

  function handleControl(agentId: string, cmd: 'pause' | 'resume' | 'stop' | 'restart') {
    controlAgent({ agentId, command: cmd })
  }

  async function handleStartAll() {
    for (const a of agents) {
      if (a.status === 'stopped' || a.status === 'error') {
        controlAgent({ agentId: a.agent_id, command: 'resume' })
        await new Promise((r) => setTimeout(r, 500))
      }
    }
  }

  async function handleStopAll() {
    for (const a of agents) {
      if (a.status === 'running' || a.status === 'paused') {
        controlAgent({ agentId: a.agent_id, command: 'stop' })
        await new Promise((r) => setTimeout(r, 300))
      }
    }
    setConfirmAllStop(false)
  }

  const summaryColor =
    runningCount === 3
      ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20'
      : runningCount > 0
      ? 'text-amber-400 bg-amber-500/10 border-amber-500/20'
      : 'text-zinc-400 bg-zinc-800 border-zinc-700'

  return (
    <div className="min-h-screen bg-zinc-950 p-4 space-y-6">
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold text-zinc-100">Multi-Agent System</h1>
          <p className="text-zinc-500 text-sm mt-0.5">
            3 autonomous agents managing strategy research, market intelligence, and live trading
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => refetch()}
            className="p-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* ── Status summary bar ─────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <span
          className={cn(
            'inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium border',
            summaryColor
          )}
        >
          <Activity className="w-4 h-4" />
          {isLoading ? 'Loading...' : `${runningCount}/3 agents running`}
        </span>

        <div className="flex items-center gap-2">
          {allStopped && agents.length > 0 && (
            <button
              onClick={handleStartAll}
              disabled={controlPending}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium',
                'bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-400 border border-emerald-500/30',
                'transition-colors disabled:opacity-50 disabled:cursor-not-allowed'
              )}
            >
              <Play className="w-3.5 h-3.5" />
              Start All
            </button>
          )}
          {anyRunning && !confirmAllStop && (
            <button
              onClick={() => setConfirmAllStop(true)}
              disabled={controlPending}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium',
                'bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30',
                'transition-colors disabled:opacity-50 disabled:cursor-not-allowed'
              )}
            >
              <Square className="w-3.5 h-3.5" />
              Stop All
            </button>
          )}
          {confirmAllStop && (
            <div className="flex items-center gap-2 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5">
              <span className="text-zinc-300 text-xs">Stop all agents?</span>
              <button
                onClick={handleStopAll}
                className="text-red-400 hover:text-red-300 text-xs font-semibold"
              >
                Confirm
              </button>
              <button
                onClick={() => setConfirmAllStop(false)}
                className="text-zinc-500 hover:text-zinc-300 text-xs"
              >
                Cancel
              </button>
            </div>
          )}
        </div>
      </div>

      {/* ── Error state ────────────────────────────────────────────────── */}
      {error && (
        <div className="flex items-center gap-3 bg-amber-500/10 border border-amber-500/20 rounded-lg px-4 py-3">
          <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />
          <p className="text-amber-300 text-sm flex-1">
            Failed to load agent data. Data may be stale.
          </p>
          <button
            onClick={() => refetch()}
            className="text-amber-400 hover:text-amber-300 text-sm underline"
          >
            Retry
          </button>
        </div>
      )}

      {/* ── Agent cards grid ───────────────────────────────────────────── */}
      {isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-3 border-l-4 border-l-zinc-700"
            >
              <div className="flex items-center gap-2">
                <div className="shimmer w-3 h-3 rounded-full" />
                <div className="shimmer h-4 w-28 rounded" />
              </div>
              <div className="shimmer h-3 w-full rounded" />
              <div className="grid grid-cols-3 gap-2">
                <div className="shimmer h-12 rounded-lg" />
                <div className="shimmer h-12 rounded-lg" />
                <div className="shimmer h-12 rounded-lg" />
              </div>
              <div className="shimmer h-7 w-full rounded" />
            </div>
          ))}
        </div>
      ) : agents.length === 0 ? (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-12 flex flex-col items-center text-zinc-600">
          <Activity className="w-12 h-12 mb-4" />
          <p className="text-base font-medium text-zinc-500">No agents found</p>
          <p className="text-sm mt-1">
            Agents may not be running. Start them with{' '}
            <code className="bg-zinc-800 px-1 py-0.5 rounded text-zinc-300 text-xs">
              bash scripts/start_agents.sh
            </code>
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {agents.map((agent) => (
            <AgentCard
              key={agent.agent_id}
              agent={agent}
              onControl={(cmd) => handleControl(agent.agent_id, cmd)}
              isPending={controlPending}
            />
          ))}
        </div>
      )}

      {/* ── Message bus stats ──────────────────────────────────────────── */}
      <MessageBusStats data={{ agents }} />

      {/* ── Agent communication diagram ────────────────────────────────── */}
      <AgentCommunicationDiagram agents={agents} />
    </div>
  )
}
