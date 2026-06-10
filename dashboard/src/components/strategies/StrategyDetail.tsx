'use client'

import { useState } from 'react'
import { cn } from '@/lib/utils'
import type { StrategyCandidate } from '@/types'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { MetricTile } from '@/components/ui/MetricTile'
import { Modal } from '@/components/ui/Modal'
import { JsonViewer } from '@/components/ui/JsonViewer'
import { Spinner } from '@/components/ui/Spinner'
import {
  X,
  Crown,
  AlertTriangle,
  CheckCircle,
  XCircle,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'

export interface StrategyDetailProps {
  strategy: StrategyCandidate | null
  open: boolean
  onClose: () => void
  onPromote?: (hash: string) => void
  onReject?: (hash: string) => void
  promotePending?: boolean
  rejectPending?: boolean
}

type DetailTab = 'fitness' | 'genome' | 'history'

// ─── Status badge config ──────────────────────────────────────────────────────

const STATUS_BADGE: Record<
  string,
  { label: string; className: string; icon?: React.ReactNode }
> = {
  pending: { label: 'Pending', className: 'bg-zinc-800 text-zinc-400 border-zinc-700' },
  validating: {
    label: 'Validating',
    className: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  },
  validated: {
    label: 'Validated',
    className: 'bg-sky-500/10 text-sky-400 border-sky-500/20',
  },
  shadow: {
    label: 'Shadow',
    className: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20',
  },
  promoted: {
    label: 'Promoted',
    className: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    icon: <Crown className="w-3 h-3" />,
  },
  rejected: {
    label: 'Rejected',
    className: 'bg-red-500/10 text-red-400 border-red-500/20',
  },
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatPct(v: number | undefined | null): string {
  if (v == null) return '—'
  return `${(v * 100).toFixed(1)}%`
}

function formatNum(v: number | undefined | null, decimals = 3): string {
  if (v == null) return '—'
  return v.toFixed(decimals)
}

function formatCurrency(v: number | undefined | null): string {
  if (v == null) return '—'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(v)
}

function timeAgo(ts: number): string {
  const diff = Math.floor(Date.now() / 1000 - ts)
  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

// ─── Circular progress ────────────────────────────────────────────────────────

function CircularScore({ score }: { score: number | undefined | null }) {
  const pct = score != null ? Math.max(0, Math.min(1, score)) : 0
  const radius = 36
  const circumference = 2 * Math.PI * radius
  const dashOffset = circumference * (1 - pct)
  const color =
    pct >= 0.7 ? '#10b981' : pct >= 0.4 ? '#f59e0b' : '#ef4444'

  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative w-24 h-24">
        <svg className="w-24 h-24 -rotate-90" viewBox="0 0 88 88">
          <circle
            cx="44"
            cy="44"
            r={radius}
            fill="none"
            stroke="#27272a"
            strokeWidth="8"
          />
          <circle
            cx="44"
            cy="44"
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth="8"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            strokeLinecap="round"
            style={{ transition: 'stroke-dashoffset 0.5s ease' }}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-xl font-bold text-zinc-100 font-mono">
            {score != null ? (score * 100).toFixed(0) : '—'}
          </span>
        </div>
      </div>
      <span className="text-zinc-500 text-xs">Composite Score</span>
    </div>
  )
}

// ─── Tabs ─────────────────────────────────────────────────────────────────────

const TABS: { key: DetailTab; label: string }[] = [
  { key: 'fitness', label: 'Fitness Metrics' },
  { key: 'genome', label: 'Genome Parameters' },
  { key: 'history', label: 'Validation History' },
]

// ─── Tab content: Fitness ─────────────────────────────────────────────────────

function FitnessTab({ strategy }: { strategy: StrategyCandidate }) {
  const f = strategy.fitness
  const metrics: { label: string; value: string; sub?: string }[] = [
    { label: 'Expectancy', value: formatCurrency(f.expectancy) },
    {
      label: 'Profit Factor',
      value: f.profit_factor != null ? `${f.profit_factor.toFixed(2)}x` : '—',
    },
    {
      label: 'Sharpe Ratio',
      value: f.sharpe_ratio != null ? f.sharpe_ratio.toFixed(3) : '—',
    },
    {
      label: 'Max Drawdown',
      value: f.max_drawdown_pct != null ? `${(f.max_drawdown_pct * 100).toFixed(1)}%` : '—',
    },
    {
      label: 'Win Rate',
      value: f.win_rate != null ? `${(f.win_rate * 100).toFixed(1)}%` : '—',
    },
    {
      label: 'Total Trades',
      value: f.total_trades != null ? String(f.total_trades) : '—',
    },
    {
      label: 'Stability',
      value: f.stability_score != null ? f.stability_score.toFixed(3) : '—',
    },
  ]

  return (
    <div className="space-y-6">
      {/* Composite score highlight */}
      <div className="flex flex-col sm:flex-row items-center gap-6 bg-zinc-800/40 rounded-xl p-4">
        <CircularScore score={f.composite_score} />
        <div className="flex-1 space-y-2">
          {/* Passed minimum */}
          <div className="flex items-center gap-2">
            {f.passed_minimum ? (
              <>
                <CheckCircle className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                <span className="text-emerald-400 text-sm font-medium">
                  Passed minimum thresholds
                </span>
              </>
            ) : (
              <>
                <XCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
                <span className="text-red-400 text-sm font-medium">
                  Did not pass minimum thresholds
                </span>
              </>
            )}
          </div>

          {/* Rejection reason */}
          {f.rejection_reason && (
            <div className="flex items-start gap-2 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2">
              <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
              <p className="text-amber-300 text-sm">{f.rejection_reason}</p>
            </div>
          )}

          <p className="text-zinc-500 text-xs">
            Generation {strategy.generation} · Created {timeAgo(strategy.created_at)}
          </p>
          {strategy.notes && (
            <p className="text-zinc-400 text-xs italic">{strategy.notes}</p>
          )}
        </div>
      </div>

      {/* Metrics grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {metrics.map(({ label, value }) => (
          <MetricTile key={label} label={label} value={value} />
        ))}
      </div>
    </div>
  )
}

// ─── Tab content: Genome ──────────────────────────────────────────────────────

const GENOME_PARAMS: {
  key: string
  label: string
  range: string
  description: string
}[] = [
  {
    key: 'swing_lookback',
    label: 'Swing Lookback',
    range: '2–10',
    description: 'Number of bars to look back for swing identification',
  },
  {
    key: 'bos_confirmation_candles',
    label: 'BOS Confirmation Candles',
    range: '1–5',
    description: 'Candles required to confirm break of structure',
  },
  {
    key: 'sl_buffer_pips',
    label: 'SL Buffer Pips',
    range: '3–20',
    description: 'Extra pips added to stop loss for spread/slippage',
  },
  {
    key: 'tp1_rr',
    label: 'TP1 R:R',
    range: '1.0–3.0',
    description: 'Risk-to-reward ratio for first take profit',
  },
  {
    key: 'tp2_rr',
    label: 'TP2 R:R',
    range: '1.5–6.0',
    description: 'Risk-to-reward ratio for second take profit',
  },
  {
    key: 'risk_per_trade',
    label: 'Risk Per Trade',
    range: '0.005–0.02',
    description: 'Fraction of equity risked per trade',
  },
  {
    key: 'fvg_min_size_pips',
    label: 'Min FVG Size (Pips)',
    range: '3–20',
    description: 'Minimum size of fair value gap to consider',
  },
  {
    key: 'liquidity_lookback',
    label: 'Liquidity Lookback',
    range: '10–50',
    description: 'Bars to look back for liquidity level detection',
  },
]

function GenomeTab({
  strategy,
}: {
  strategy: StrategyCandidate
}) {
  // Try to extract genome data from the notes or fitness object
  const genomeData =
    typeof (strategy as { genome?: Record<string, unknown> }).genome === 'object'
      ? (strategy as { genome?: Record<string, unknown> }).genome
      : null

  return (
    <div className="space-y-4">
      {/* Known params table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-800">
              <th className="text-left text-zinc-500 text-xs font-medium pb-2 pr-4">Parameter</th>
              <th className="text-left text-zinc-500 text-xs font-medium pb-2 pr-4">Value</th>
              <th className="text-left text-zinc-500 text-xs font-medium pb-2 pr-4">Range</th>
              <th className="text-left text-zinc-500 text-xs font-medium pb-2">Description</th>
            </tr>
          </thead>
          <tbody>
            {GENOME_PARAMS.map(({ key, label, range, description }) => {
              const val = genomeData
                ? (genomeData as Record<string, unknown>)[key]
                : undefined
              return (
                <tr key={key} className="border-b border-zinc-800/50">
                  <td className="py-2 pr-4 text-zinc-300 text-xs font-medium">{label}</td>
                  <td className="py-2 pr-4">
                    <span
                      className={cn(
                        'font-mono text-xs',
                        val !== undefined ? 'text-amber-400' : 'text-zinc-600'
                      )}
                    >
                      {val !== undefined ? String(val) : '—'}
                    </span>
                  </td>
                  <td className="py-2 pr-4 text-zinc-600 text-xs font-mono">{range}</td>
                  <td className="py-2 text-zinc-500 text-xs">{description}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Raw genome JSON */}
      <div className="mt-4">
        <p className="text-zinc-500 text-xs font-medium mb-2">Raw Genome Data</p>
        {genomeData ? (
          <JsonViewer data={genomeData} />
        ) : (
          <div className="bg-zinc-800/50 border border-zinc-700 rounded-lg px-4 py-6 text-center">
            <p className="text-zinc-500 text-sm">Genome data not available</p>
            <p className="text-zinc-600 text-xs mt-1">
              Full genome parameters are only stored during the optimization process
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Tab content: Validation History ─────────────────────────────────────────

function HistoryTab({ strategy }: { strategy: StrategyCandidate }) {
  // In a real implementation this would come from an API endpoint
  const hasScore =
    strategy.fitness.composite_score != null

  return (
    <div className="space-y-4">
      {/* Fitness comparison */}
      {hasScore && (
        <div className="bg-zinc-800/40 rounded-xl p-4 space-y-3">
          <p className="text-zinc-300 text-sm font-medium">Fitness Summary</p>
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-zinc-900 rounded-lg p-3">
              <p className="text-zinc-500 text-[10px] uppercase tracking-wider mb-1">
                In-Sample Score
              </p>
              <p className="text-sky-400 text-xl font-mono font-bold">
                {formatNum(strategy.fitness.composite_score)}
              </p>
            </div>
            <div className="bg-zinc-900 rounded-lg p-3">
              <p className="text-zinc-500 text-[10px] uppercase tracking-wider mb-1">
                Stability Score
              </p>
              <p className="text-indigo-400 text-xl font-mono font-bold">
                {formatNum(strategy.fitness.stability_score)}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Status timeline */}
      <div>
        <p className="text-zinc-500 text-xs font-medium mb-3">Status Timeline</p>
        <div className="space-y-2">
          {[
            {
              step: 'Created',
              ts: strategy.created_at,
              done: true,
              color: 'bg-zinc-500',
            },
            {
              step: 'Queued for Validation',
              ts:
                strategy.status !== 'pending'
                  ? strategy.created_at + 60
                  : null,
              done: strategy.status !== 'pending',
              color: 'bg-amber-500',
            },
            {
              step: 'Validated',
              ts:
                strategy.status === 'validated' ||
                strategy.status === 'shadow' ||
                strategy.status === 'promoted'
                  ? strategy.created_at + 600
                  : null,
              done:
                strategy.status === 'validated' ||
                strategy.status === 'shadow' ||
                strategy.status === 'promoted',
              color: 'bg-sky-500',
            },
            {
              step: 'Shadow Testing',
              ts:
                strategy.status === 'shadow' || strategy.status === 'promoted'
                  ? strategy.created_at + 1200
                  : null,
              done:
                strategy.status === 'shadow' || strategy.status === 'promoted',
              color: 'bg-indigo-500',
            },
            {
              step: 'Promoted',
              ts: strategy.status === 'promoted' ? strategy.created_at + 2400 : null,
              done: strategy.status === 'promoted',
              color: 'bg-emerald-500',
            },
          ].map(({ step, ts, done, color }) => (
            <div key={step} className="flex items-center gap-3">
              <div
                className={cn(
                  'w-2.5 h-2.5 rounded-full flex-shrink-0',
                  done ? color : 'bg-zinc-700'
                )}
              />
              <span
                className={cn(
                  'text-xs flex-1',
                  done ? 'text-zinc-300' : 'text-zinc-600'
                )}
              >
                {step}
              </span>
              {ts && (
                <span className="text-zinc-600 text-[10px] font-mono">
                  {timeAgo(ts)}
                </span>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Notes */}
      {strategy.notes && (
        <div className="bg-zinc-800/50 border border-zinc-700 rounded-lg px-3 py-2">
          <p className="text-zinc-500 text-[10px] uppercase tracking-wider mb-1">Notes</p>
          <p className="text-zinc-300 text-sm">{strategy.notes}</p>
        </div>
      )}
    </div>
  )
}

// ─── Main component ────────────────────────────────────────────────────────────

export function StrategyDetail({
  strategy,
  open,
  onClose,
  onPromote,
  onReject,
  promotePending = false,
  rejectPending = false,
}: StrategyDetailProps) {
  const [activeTab, setActiveTab] = useState<DetailTab>('fitness')
  const [rejectConfirmText, setRejectConfirmText] = useState('')
  const [showRejectConfirm, setShowRejectConfirm] = useState(false)
  const [showPromoteConfirm, setShowPromoteConfirm] = useState(false)

  if (!strategy) return null

  const statusCfg = STATUS_BADGE[strategy.status] ?? STATUS_BADGE.pending
  const canPromote =
    strategy.status === 'validated' || strategy.status === 'shadow'
  const canReject = strategy.status !== 'promoted' && strategy.status !== 'rejected'

  function handlePromoteClick() {
    setShowPromoteConfirm(true)
  }

  function handlePromoteConfirm() {
    onPromote?.(strategy!.genome_hash)
    setShowPromoteConfirm(false)
  }

  function handleRejectClick() {
    setShowRejectConfirm(true)
    setRejectConfirmText('')
  }

  function handleRejectConfirm() {
    if (rejectConfirmText === 'REJECT') {
      onReject?.(strategy!.genome_hash)
      setShowRejectConfirm(false)
      setRejectConfirmText('')
    }
  }

  return (
    <Modal open={open} onClose={onClose} maxWidth="2xl">
      <div className="bg-zinc-950 rounded-xl overflow-hidden max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="bg-zinc-900 border-b border-zinc-800 px-5 py-4">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-mono text-amber-400 text-sm font-medium break-all">
                  {strategy.genome_hash}
                </span>
                <span
                  className={cn(
                    'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium border',
                    statusCfg.className
                  )}
                >
                  {statusCfg.icon}
                  {statusCfg.label}
                </span>
              </div>
              <p className="text-zinc-500 text-xs mt-1">
                Generation {strategy.generation} · ID #{strategy.id} ·{' '}
                {timeAgo(strategy.created_at)}
              </p>
            </div>
            <button
              className="flex-shrink-0 text-zinc-500 hover:text-zinc-200 transition-colors p-1"
              onClick={onClose}
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-2 mt-3">
            {canPromote && !showPromoteConfirm && (
              <Button
                size="sm"
                className="h-8 bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-400 border border-emerald-500/30 text-xs"
                onClick={handlePromoteClick}
                disabled={promotePending || rejectPending}
              >
                {promotePending ? (
                  <Spinner size="xs" />
                ) : (
                  <Crown className="w-3.5 h-3.5 mr-1" />
                )}
                Promote
              </Button>
            )}
            {showPromoteConfirm && (
              <div className="flex items-center gap-2">
                <span className="text-zinc-400 text-xs">Promote this strategy?</span>
                <Button
                  size="sm"
                  className="h-7 bg-emerald-500 hover:bg-emerald-600 text-white border-0 text-xs"
                  onClick={handlePromoteConfirm}
                  disabled={promotePending}
                >
                  {promotePending ? <Spinner size="xs" /> : 'Confirm'}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 text-xs text-zinc-400"
                  onClick={() => setShowPromoteConfirm(false)}
                >
                  Cancel
                </Button>
              </div>
            )}
            {canReject && !showRejectConfirm && (
              <Button
                size="sm"
                className="h-8 bg-red-500/20 hover:bg-red-500/30 text-red-400 border border-red-500/30 text-xs"
                onClick={handleRejectClick}
                disabled={promotePending || rejectPending}
              >
                {rejectPending ? <Spinner size="xs" /> : <XCircle className="w-3.5 h-3.5 mr-1" />}
                Reject
              </Button>
            )}
            {showRejectConfirm && (
              <div className="flex items-center gap-2 bg-zinc-800/60 border border-zinc-700 rounded-lg px-3 py-1.5">
                <span className="text-zinc-400 text-xs">Type REJECT to confirm:</span>
                <input
                  className="bg-zinc-900 border border-zinc-700 rounded px-2 py-0.5 text-xs text-zinc-100 font-mono w-20 focus:outline-none focus:border-red-500"
                  value={rejectConfirmText}
                  onChange={(e) => setRejectConfirmText(e.target.value)}
                  placeholder="REJECT"
                  autoFocus
                />
                <Button
                  size="sm"
                  className={cn(
                    'h-7 text-xs border-0',
                    rejectConfirmText === 'REJECT'
                      ? 'bg-red-500 hover:bg-red-600 text-white'
                      : 'bg-zinc-700 text-zinc-500 cursor-not-allowed'
                  )}
                  onClick={handleRejectConfirm}
                  disabled={rejectConfirmText !== 'REJECT' || rejectPending}
                >
                  {rejectPending ? <Spinner size="xs" /> : 'Confirm Reject'}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 text-xs text-zinc-400"
                  onClick={() => {
                    setShowRejectConfirm(false)
                    setRejectConfirmText('')
                  }}
                >
                  Cancel
                </Button>
              </div>
            )}
          </div>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-zinc-800 bg-zinc-900/50">
          {TABS.map(({ key, label }) => (
            <button
              key={key}
              className={cn(
                'px-4 py-3 text-sm font-medium transition-colors border-b-2 -mb-px',
                activeTab === key
                  ? 'text-zinc-100 border-amber-500'
                  : 'text-zinc-500 border-transparent hover:text-zinc-300'
              )}
              onClick={() => setActiveTab(key)}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-y-auto p-5">
          {activeTab === 'fitness' && <FitnessTab strategy={strategy} />}
          {activeTab === 'genome' && <GenomeTab strategy={strategy} />}
          {activeTab === 'history' && <HistoryTab strategy={strategy} />}
        </div>
      </div>
    </Modal>
  )
}
