'use client'

import { useState } from 'react'
import { AgentId, AgentStatus } from '@/types'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/Button'
import { StatusDot } from '@/components/ui/StatusDot'
import { Spinner } from '@/components/ui/Spinner'
import {
  Play,
  Pause,
  Square,
  RefreshCw,
  AlertTriangle,
  X,
  Check,
} from 'lucide-react'

export interface AgentControlBarProps {
  agentId: AgentId
  status: AgentStatus
  onCommand: (cmd: 'start' | 'pause' | 'resume' | 'stop' | 'restart') => Promise<void>
  isPending?: boolean
}

type ConfirmAction = 'stop' | 'restart' | null

const STATUS_LABELS: Record<AgentStatus, string> = {
  running: 'Running',
  paused: 'Paused',
  error: 'Error',
  stopped: 'Stopped',
  starting: 'Starting',
}

const STATUS_DOT_MAP: Record<AgentStatus, 'running' | 'paused' | 'error' | 'stopped' | 'starting'> = {
  running: 'running',
  paused: 'paused',
  error: 'error',
  stopped: 'stopped',
  starting: 'starting',
}

const STATUS_TEXT_CLASS: Record<AgentStatus, string> = {
  running: 'text-emerald-400',
  paused: 'text-amber-400',
  error: 'text-red-400',
  stopped: 'text-zinc-400',
  starting: 'text-blue-400',
}

const CONFIRM_MESSAGES: Record<NonNullable<ConfirmAction>, string> = {
  stop: 'Stop this agent? It will terminate any in-progress work.',
  restart: 'Restart this agent? There will be a brief interruption.',
}

export function AgentControlBar({
  agentId,
  status,
  onCommand,
  isPending = false,
}: AgentControlBarProps) {
  const [confirmAction, setConfirmAction] = useState<ConfirmAction>(null)
  const [localPending, setLocalPending] = useState(false)

  const isAgent3 = agentId === 'agent3'
  const canStart = status === 'stopped' || status === 'error'
  const canPause = status === 'running'
  const canResume = status === 'paused'
  const canStop = status === 'running' || status === 'paused'
  const busy = isPending || localPending

  async function executeCommand(cmd: 'pause' | 'resume' | 'stop' | 'restart') {
    setLocalPending(true)
    try {
      await onCommand(cmd)
    } finally {
      setLocalPending(false)
      setConfirmAction(null)
    }
  }

  function handleActionClick(action: 'stop' | 'restart') {
    setConfirmAction(action)
  }

  function handleConfirm() {
    if (confirmAction) {
      executeCommand(confirmAction)
    }
  }

  function handleCancel() {
    setConfirmAction(null)
  }

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-4">
      {/* Status display */}
      <div className="flex items-center gap-3">
        <StatusDot status={STATUS_DOT_MAP[status]} size="lg" />
        <div>
          <p className="text-zinc-400 text-xs uppercase tracking-wider">Agent Status</p>
          <p className={cn('text-base font-semibold', STATUS_TEXT_CLASS[status])}>
            {STATUS_LABELS[status]}
          </p>
        </div>
        {busy && (
          <div className="ml-auto">
            <Spinner size="sm" />
          </div>
        )}
      </div>

      {/* Confirm dialog */}
      {confirmAction && (
        <div className="bg-zinc-800/60 border border-zinc-700 rounded-lg p-3">
          <div className="flex items-start gap-2 mb-3">
            <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
            <p className="text-zinc-300 text-sm">{CONFIRM_MESSAGES[confirmAction]}</p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              className={cn(
                'flex-1 h-8 text-xs font-medium',
                confirmAction === 'stop'
                  ? 'bg-red-500 hover:bg-red-600 text-white border-0'
                  : 'bg-amber-500 hover:bg-amber-600 text-zinc-950 border-0'
              )}
              onClick={handleConfirm}
              disabled={busy}
            >
              {busy ? <Spinner size="xs" /> : <Check className="w-3 h-3 mr-1" />}
              Confirm {confirmAction === 'stop' ? 'Stop' : 'Restart'}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="flex-1 h-8 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700"
              onClick={handleCancel}
              disabled={busy}
            >
              <X className="w-3 h-3 mr-1" />
              Cancel
            </Button>
          </div>
        </div>
      )}

      {/* Primary action buttons */}
      {!confirmAction && (
        <div className="flex items-center gap-2">
          {/* Start / Pause / Resume */}
          {canStart && (
            <Button
              size="sm"
              className="flex-1 h-9 bg-emerald-500 hover:bg-emerald-600 text-zinc-950 font-medium border-0 text-sm"
              onClick={() => executeCommand('start')}
              disabled={busy}
            >
              {busy ? <Spinner size="xs" /> : <Play className="w-4 h-4 mr-1.5" />}
              Start
            </Button>
          )}
          {canPause && (
            <Button
              size="sm"
              className="flex-1 h-9 bg-amber-500/20 hover:bg-amber-500/30 text-amber-400 border border-amber-500/30 text-sm"
              onClick={() => executeCommand('pause')}
              disabled={busy}
            >
              {busy ? <Spinner size="xs" /> : <Pause className="w-4 h-4 mr-1.5" />}
              Pause
            </Button>
          )}
          {canResume && (
            <Button
              size="sm"
              className="flex-1 h-9 bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-400 border border-emerald-500/30 text-sm"
              onClick={() => executeCommand('resume')}
              disabled={busy}
            >
              {busy ? <Spinner size="xs" /> : <Play className="w-4 h-4 mr-1.5" />}
              Resume
            </Button>
          )}

          {/* Stop */}
          {canStop && (
            <Button
              size="sm"
              className="flex-1 h-9 bg-red-500/20 hover:bg-red-500/30 text-red-400 border border-red-500/30 text-sm"
              onClick={() => handleActionClick('stop')}
              disabled={busy}
            >
              <Square className="w-4 h-4 mr-1.5" />
              Stop
            </Button>
          )}

          {/* Restart */}
          <Button
            size="sm"
            className="flex-1 h-9 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700 text-sm"
            onClick={() => handleActionClick('restart')}
            disabled={busy}
          >
            <RefreshCw className={cn('w-4 h-4 mr-1.5', busy && 'animate-spin')} />
            Restart
          </Button>
        </div>
      )}

      {/* Agent 3 emergency stop */}
      {isAgent3 && !confirmAction && (
        <button
          className={cn(
            'w-full h-10 rounded-lg border-2 border-red-600 bg-red-600/10',
            'text-red-400 hover:bg-red-600/20 hover:text-red-300',
            'font-semibold text-sm tracking-wide uppercase',
            'transition-colors duration-150',
            'flex items-center justify-center gap-2',
            'disabled:opacity-50 disabled:cursor-not-allowed'
          )}
          onClick={() => {
            if (window.confirm('EMERGENCY STOP: Immediately halt Agent 3 trading. All open positions will be left as-is. Continue?')) {
              executeCommand('stop')
            }
          }}
          disabled={busy || status === 'stopped'}
        >
          <AlertTriangle className="w-4 h-4" />
          Emergency Stop
        </button>
      )}
    </div>
  )
}
