'use client'

import { BotStatus, AgentState, AgentId } from '@/types'
import { cn } from '@/lib/utils'

export interface ServiceHealth {
  name: string
  status: 'online' | 'offline' | 'degraded' | 'unknown'
  latency?: number
  lastCheck?: string
  details?: string
}

interface SystemHealthGridProps {
  botStatus: BotStatus | null
  agentStates: AgentState[]
  wsStatus: 'connected' | 'reconnecting' | 'offline'
  dataLoaded: boolean
}

const STATUS_CONFIG = {
  online: {
    dot: 'bg-emerald-500',
    ring: 'ring-emerald-500/30',
    glow: 'shadow-emerald-500/20',
    label: 'Online',
    labelClass: 'text-emerald-400',
    cardBorder: 'border-emerald-500/20',
  },
  offline: {
    dot: 'bg-red-500',
    ring: 'ring-red-500/30',
    glow: 'shadow-red-500/20',
    label: 'Offline',
    labelClass: 'text-red-400',
    cardBorder: 'border-red-500/20',
  },
  degraded: {
    dot: 'bg-amber-500',
    ring: 'ring-amber-500/30',
    glow: 'shadow-amber-500/20',
    label: 'Degraded',
    labelClass: 'text-amber-400',
    cardBorder: 'border-amber-500/20',
  },
  unknown: {
    dot: 'bg-zinc-600',
    ring: 'ring-zinc-600/30',
    glow: '',
    label: 'Unknown',
    labelClass: 'text-zinc-500',
    cardBorder: 'border-zinc-700/50',
  },
}

function ServiceCard({ service }: { service: ServiceHealth }) {
  const cfg = STATUS_CONFIG[service.status]

  return (
    <div
      className={cn(
        'bg-zinc-900 border rounded-xl p-4 flex flex-col items-center gap-2',
        cfg.cardBorder
      )}
    >
      {/* Status circle */}
      <div
        className={cn(
          'w-8 h-8 rounded-full flex items-center justify-center ring-4',
          cfg.ring,
          service.status === 'online' && 'shadow-lg ' + cfg.glow
        )}
      >
        <div
          className={cn(
            'w-4 h-4 rounded-full',
            cfg.dot,
            service.status === 'online' && 'animate-pulse-slow'
          )}
        />
      </div>

      {/* Name */}
      <p className="text-zinc-300 text-xs font-medium text-center leading-tight">
        {service.name}
      </p>

      {/* Status label */}
      <span className={cn('text-[10px] font-semibold uppercase tracking-wider', cfg.labelClass)}>
        {cfg.label}
      </span>

      {/* Optional latency */}
      {service.latency != null && (
        <span className="text-zinc-600 text-[10px]">{service.latency}ms</span>
      )}

      {/* Optional details */}
      {service.details && (
        <span className="text-zinc-600 text-[10px] text-center truncate w-full text-center">
          {service.details}
        </span>
      )}
    </div>
  )
}

function agentStatusToHealth(
  status: AgentState['status']
): ServiceHealth['status'] {
  switch (status) {
    case 'running':
      return 'online'
    case 'paused':
      return 'degraded'
    case 'starting':
      return 'degraded'
    case 'error':
      return 'offline'
    case 'stopped':
      return 'offline'
  }
}

export function SystemHealthGrid({
  botStatus,
  agentStates,
  wsStatus,
  dataLoaded,
}: SystemHealthGridProps) {
  // Build services list
  const agentMap = agentStates.reduce<Record<AgentId, AgentState>>(
    (acc, a) => ({ ...acc, [a.agent_id]: a }),
    {} as Record<AgentId, AgentState>
  )

  const services: ServiceHealth[] = [
    {
      name: 'Trading Engine',
      status: botStatus == null
        ? 'unknown'
        : botStatus.emergency_stopped
        ? 'offline'
        : botStatus.running
        ? 'online'
        : 'offline',
      details: botStatus?.mode ?? undefined,
    },
    {
      name: 'FastAPI',
      status: dataLoaded ? 'online' : 'unknown',
      details: 'API Server',
    },
    {
      name: 'Agent 1',
      status: agentMap.agent1 ? agentStatusToHealth(agentMap.agent1.status) : 'unknown',
      details: agentMap.agent1?.current_task ?? undefined,
    },
    {
      name: 'Agent 2',
      status: agentMap.agent2 ? agentStatusToHealth(agentMap.agent2.status) : 'unknown',
      details: agentMap.agent2?.current_task ?? undefined,
    },
    {
      name: 'Agent 3',
      status: agentMap.agent3 ? agentStatusToHealth(agentMap.agent3.status) : 'unknown',
      details: agentMap.agent3?.current_task ?? undefined,
    },
    {
      name: 'Broker',
      status: botStatus == null
        ? 'unknown'
        : botStatus.running
        ? 'online'
        : 'offline',
      details: botStatus?.running ? 'Connected' : 'Disconnected',
    },
    {
      name: 'Database',
      status: dataLoaded ? 'online' : 'unknown',
      details: 'SQLite',
    },
    {
      name: 'WebSocket',
      status:
        wsStatus === 'connected'
          ? 'online'
          : wsStatus === 'reconnecting'
          ? 'degraded'
          : 'offline',
      details: wsStatus,
    },
  ]

  const onlineCount = services.filter((s) => s.status === 'online').length

  return (
    <div className="space-y-3">
      {/* Summary line */}
      <div className="flex items-center gap-2">
        <span className="text-zinc-400 text-xs">
          {onlineCount}/{services.length} services online
        </span>
        <div
          className={cn(
            'h-1.5 w-1.5 rounded-full',
            onlineCount === services.length
              ? 'bg-emerald-400'
              : onlineCount > services.length / 2
              ? 'bg-amber-400'
              : 'bg-red-400'
          )}
        />
      </div>

      {/* Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {services.map((svc) => (
          <ServiceCard key={svc.name} service={svc} />
        ))}
      </div>
    </div>
  )
}
