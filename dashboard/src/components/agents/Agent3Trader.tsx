'use client'

import { cn } from '@/lib/utils'
import { StatusDot } from '@/components/ui/StatusDot'
import { Spinner } from '@/components/ui/Spinner'
import { AlertTriangle } from 'lucide-react'

export interface Agent3TraderProps {
  status: 'running' | 'stopped' | 'paused' | 'error'
  metrics: {
    open_trades_count?: number
    consecutive_losses?: number
    last_trade_direction?: string
    last_trade_entry?: number
  }
  dailyPnl?: number
  loading?: boolean
}

const STATUS_DOT_MAP: Record<Agent3TraderProps['status'], 'running' | 'paused' | 'error' | 'stopped'> = {
  running: 'running',
  paused: 'paused',
  error: 'error',
  stopped: 'stopped',
}

const STATUS_TEXT: Record<Agent3TraderProps['status'], string> = {
  running: 'Running',
  paused: 'Paused',
  error: 'Error',
  stopped: 'Stopped',
}

const STATUS_TEXT_CLASS: Record<Agent3TraderProps['status'], string> = {
  running: 'text-emerald-400',
  paused: 'text-amber-400',
  error: 'text-red-400',
  stopped: 'text-zinc-400',
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

export function Agent3Trader({
  status,
  metrics,
  dailyPnl,
  loading = false,
}: Agent3TraderProps) {
  if (loading) {
    return (
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Spinner size="sm" />
          <span className="text-zinc-500 text-xs">Loading Agent 3…</span>
        </div>
      </div>
    )
  }

  const consecLosses = metrics.consecutive_losses ?? 0
  const hasLossWarning = consecLosses > 2

  const directionBg =
    metrics.last_trade_direction?.toUpperCase() === 'BUY' ||
    metrics.last_trade_direction?.toUpperCase() === 'LONG'
      ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
      : metrics.last_trade_direction?.toUpperCase() === 'SELL' ||
        metrics.last_trade_direction?.toUpperCase() === 'SHORT'
      ? 'bg-red-500/10 text-red-400 border-red-500/20'
      : 'bg-zinc-800 text-zinc-400 border-zinc-700'

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-3 space-y-2">
      {/* Header row */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <StatusDot
            status={STATUS_DOT_MAP[status]}
            size="md"
          />
          <div>
            <p className="text-zinc-400 text-[10px] uppercase tracking-wider">Agent 3 — Trader</p>
            <p className={cn('text-sm font-semibold leading-tight', STATUS_TEXT_CLASS[status])}>
              {STATUS_TEXT[status]}
            </p>
          </div>
        </div>

        {/* Daily PnL */}
        {dailyPnl !== undefined && (
          <div className="text-right">
            <p className="text-zinc-500 text-[10px] uppercase tracking-wider">Daily P&L</p>
            <p
              className={cn(
                'text-sm font-mono font-semibold',
                dailyPnl > 0
                  ? 'text-emerald-400'
                  : dailyPnl < 0
                  ? 'text-red-400'
                  : 'text-zinc-400'
              )}
            >
              {formatCurrency(dailyPnl)}
            </p>
          </div>
        )}
      </div>

      {/* Metrics row */}
      <div className="flex items-center gap-3 flex-wrap">
        {/* Open trades */}
        <div className="flex items-center gap-1.5">
          <span className="text-zinc-500 text-[10px] uppercase">Open:</span>
          <span className="text-zinc-200 text-xs font-mono font-medium">
            {metrics.open_trades_count ?? 0}
          </span>
        </div>

        {/* Last trade direction */}
        {metrics.last_trade_direction && (
          <span
            className={cn(
              'inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border',
              directionBg
            )}
          >
            {metrics.last_trade_direction.toUpperCase()}
          </span>
        )}

        {/* Last entry */}
        {metrics.last_trade_entry != null && (
          <div className="flex items-center gap-1">
            <span className="text-zinc-500 text-[10px]">@ </span>
            <span className="text-zinc-300 text-[10px] font-mono">
              {metrics.last_trade_entry.toFixed(2)}
            </span>
          </div>
        )}

        {/* Consecutive losses warning */}
        {hasLossWarning && (
          <div className="flex items-center gap-1 text-red-400">
            <AlertTriangle className="w-3 h-3" />
            <span className="text-[10px] font-medium">{consecLosses} consec. losses</span>
          </div>
        )}
        {!hasLossWarning && consecLosses > 0 && (
          <div className="flex items-center gap-1 text-amber-400">
            <span className="text-[10px]">{consecLosses} loss streak</span>
          </div>
        )}
      </div>
    </div>
  )
}
