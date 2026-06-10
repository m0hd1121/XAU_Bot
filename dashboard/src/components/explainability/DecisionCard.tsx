'use client'

import { useState } from 'react'
import { cn } from '@/lib/utils'
import type { TradeDecision, DecisionType } from '@/types'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { ProgressBar } from '@/components/ui/ProgressBar'
import { JsonViewer } from '@/components/ui/JsonViewer'
import {
  ChevronDown,
  ChevronUp,
  Copy,
  Check,
  TrendingUp,
  TrendingDown,
  Shield,
  Brain,
  AlertTriangle,
  Clock,
  Hash,
  DollarSign,
  Activity,
} from 'lucide-react'

export interface DecisionCardProps {
  decision: TradeDecision
  expanded?: boolean
  onToggle?: () => void
  className?: string
}

// ── Badge colors per decision type ───────────────────────────────────────────

const DECISION_BADGE: Record<DecisionType, string> = {
  EXECUTE: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  REJECT: 'bg-red-500/15 text-red-400 border-red-500/30',
  DEFER: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
}

const DECISION_BORDER: Record<DecisionType, string> = {
  EXECUTE: 'border-l-emerald-500',
  REJECT: 'border-l-red-500',
  DEFER: 'border-l-amber-500',
}

const DECISION_LARGE_BADGE: Record<DecisionType, string> = {
  EXECUTE: 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/30 text-base font-bold px-4 py-1.5',
  REJECT: 'bg-red-500/10 text-red-300 border border-red-500/30 text-base font-bold px-4 py-1.5',
  DEFER: 'bg-amber-500/10 text-amber-300 border border-amber-500/30 text-base font-bold px-4 py-1.5',
}

// ── Rejection reason classifier ───────────────────────────────────────────────

type RejectCategory =
  | 'risk_manager'
  | 'psychology'
  | 'learning'
  | 'no_setup'
  | 'defer'
  | 'unknown'

function classifyRejectReason(reason: string): RejectCategory {
  const lower = reason.toLowerCase()
  if (lower.startsWith('risk_manager:') || lower.startsWith('risk:')) return 'risk_manager'
  if (lower.startsWith('psychology:') || lower.startsWith('psych:')) return 'psychology'
  if (lower.startsWith('learning:') || lower.startsWith('confidence:')) return 'learning'
  if (lower === 'no_setup' || lower.includes('no valid setup') || lower.includes('no setup')) return 'no_setup'
  if (lower.startsWith('defer')) return 'defer'
  return 'unknown'
}

function rejectCategoryLabel(cat: RejectCategory): string {
  switch (cat) {
    case 'risk_manager': return 'Risk Check Failed'
    case 'psychology': return 'Psychology Blocked'
    case 'learning': return 'Learning Insufficient Confidence'
    case 'no_setup': return 'No Valid Setup Found'
    case 'defer': return 'Deferred'
    default: return 'Rejected'
  }
}

function rejectCategoryIcon(cat: RejectCategory) {
  switch (cat) {
    case 'risk_manager': return <Shield className="w-4 h-4" />
    case 'psychology': return <Brain className="w-4 h-4" />
    case 'learning': return <Activity className="w-4 h-4" />
    case 'no_setup': return <AlertTriangle className="w-4 h-4" />
    default: return <AlertTriangle className="w-4 h-4" />
  }
}

// ── Timestamp formatter ───────────────────────────────────────────────────────

function formatTs(ts: number): string {
  return new Date(ts * 1000).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function formatTsShort(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

// ── KV pair row ───────────────────────────────────────────────────────────────

function KVRow({
  label,
  value,
  valueClass,
  mono,
}: {
  label: string
  value: React.ReactNode
  valueClass?: string
  mono?: boolean
}) {
  if (value === null || value === undefined || value === '') return null
  return (
    <div className="flex items-center justify-between gap-4 py-1 border-b border-zinc-800/60 last:border-0">
      <span className="text-zinc-500 text-xs flex-shrink-0">{label}</span>
      <span className={cn('text-xs text-right', mono && 'font-mono', valueClass ?? 'text-zinc-200')}>
        {value}
      </span>
    </div>
  )
}

// ── Section header ────────────────────────────────────────────────────────────

function SectionHeader({ icon, title }: { icon: React.ReactNode; title: string }) {
  return (
    <div className="flex items-center gap-2 mb-2 mt-4 first:mt-0">
      <span className="text-zinc-500">{icon}</span>
      <span className="text-zinc-400 text-xs font-semibold uppercase tracking-wider">{title}</span>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export function DecisionCard({
  decision,
  expanded = false,
  onToggle,
  className,
}: DecisionCardProps) {
  const [jsonExpanded, setJsonExpanded] = useState(false)
  const [copied, setCopied] = useState(false)

  const { explanation } = decision
  const direction = explanation.direction?.toUpperCase()
  const rejectCat = decision.decision === 'REJECT'
    ? classifyRejectReason(decision.reason)
    : null

  function handleCopyJson() {
    void navigator.clipboard.writeText(JSON.stringify(explanation, null, 2)).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  // ── Collapsed header ────────────────────────────────────────────────────────

  return (
    <div
      className={cn(
        'bg-zinc-900 border border-zinc-800 rounded-xl border-l-4 overflow-hidden transition-shadow hover:shadow-lg hover:shadow-zinc-950/50',
        DECISION_BORDER[decision.decision],
        className
      )}
    >
      {/* Always-visible collapsed bar */}
      <button
        className="w-full text-left px-4 py-3 flex items-start gap-3 hover:bg-zinc-800/30 transition-colors"
        onClick={onToggle}
        type="button"
      >
        {/* Badges row */}
        <div className="flex flex-wrap items-center gap-2 flex-1 min-w-0">
          {/* Decision type */}
          <span
            className={cn(
              'inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold border uppercase tracking-wide',
              DECISION_BADGE[decision.decision]
            )}
          >
            {decision.decision}
          </span>

          {/* Direction */}
          {direction && (
            <span
              className={cn(
                'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold border uppercase',
                direction === 'BUY'
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                  : 'bg-red-500/10 text-red-400 border-red-500/30'
              )}
            >
              {direction === 'BUY' ? (
                <TrendingUp className="w-3 h-3" />
              ) : (
                <TrendingDown className="w-3 h-3" />
              )}
              {direction}
            </span>
          )}

          {/* Timestamp */}
          <span className="text-zinc-500 text-[11px] font-mono">{formatTsShort(decision.timestamp)}</span>

          {/* Reason */}
          <span className="text-zinc-400 text-xs truncate flex-1 min-w-0">
            {decision.reason}
          </span>
        </div>

        {/* Expand toggle */}
        <div className="flex-shrink-0 mt-0.5 text-zinc-500">
          {expanded ? (
            <ChevronUp className="w-4 h-4" />
          ) : (
            <ChevronDown className="w-4 h-4" />
          )}
        </div>
      </button>

      {/* Compact meta row */}
      {!expanded && (
        <div className="px-4 pb-2.5 flex items-center gap-4 flex-wrap">
          {explanation.strategy_hash && (
            <span className="text-zinc-600 text-[11px] font-mono">
              Strategy: #{explanation.strategy_hash.slice(0, 8)}
            </span>
          )}
          {explanation.session && (
            <span className="text-zinc-600 text-[11px]">
              Session: {explanation.session}
            </span>
          )}
          {explanation.confidence_score != null && (
            <span className="text-zinc-600 text-[11px]">
              Confidence: {explanation.confidence_score.toFixed(2)}
            </span>
          )}
        </div>
      )}

      {/* ── Expanded detail panel ────────────────────────────────────────────── */}
      {expanded && (
        <div className="px-4 pb-4 border-t border-zinc-800 pt-4 space-y-1 animate-in slide-in-from-top-2 duration-150">

          {/* ── 1. Decision Summary ──────────────────────────────────────────── */}
          <SectionHeader icon={<Activity className="w-3.5 h-3.5" />} title="Decision Summary" />
          <div className="bg-zinc-800/40 rounded-lg p-3 space-y-0">
            <div className="flex items-center gap-3 mb-3">
              <span className={cn('inline-flex items-center rounded-lg', DECISION_LARGE_BADGE[decision.decision])}>
                {decision.decision}
              </span>
            </div>
            <KVRow label="Reason" value={decision.reason} />
            <KVRow label="Timestamp" value={formatTs(decision.timestamp)} />
            {decision.trade_id && (
              <KVRow label="Trade ID" value={decision.trade_id} mono />
            )}
            {explanation.strategy_hash && (
              <KVRow
                label="Strategy Hash"
                value={`#${explanation.strategy_hash.slice(0, 16)}`}
                mono
                valueClass="text-sky-400"
              />
            )}
          </div>

          {/* ── 2. Market Conditions ────────────────────────────────────────── */}
          <SectionHeader icon={<Shield className="w-3.5 h-3.5" />} title="Market Conditions" />
          <div className="bg-zinc-800/40 rounded-lg p-3 space-y-0">
            <KVRow label="Regime" value={explanation.regime} />
            {explanation.risk_score != null && (
              <KVRow
                label="Risk Score"
                value={explanation.risk_score.toFixed(3)}
                mono
                valueClass={
                  explanation.risk_score > 0.7
                    ? 'text-red-400'
                    : explanation.risk_score > 0.4
                    ? 'text-amber-400'
                    : 'text-emerald-400'
                }
              />
            )}
            <KVRow label="Session" value={explanation.session} />
            {explanation.consecutive_losses != null && (
              <KVRow
                label="Consecutive Losses"
                value={String(explanation.consecutive_losses)}
                mono
                valueClass={
                  (explanation.consecutive_losses as number) > 2
                    ? 'text-red-400 font-bold'
                    : 'text-zinc-200'
                }
              />
            )}
            {explanation.current_drawdown_pct != null && (
              <KVRow
                label="Current Drawdown"
                value={`${(explanation.current_drawdown_pct as number).toFixed(2)}%`}
                mono
                valueClass={
                  (explanation.current_drawdown_pct as number) > 5 ? 'text-red-400' : 'text-zinc-200'
                }
              />
            )}
            {explanation.account_equity != null && (
              <KVRow
                label="Account Equity"
                value={`$${(explanation.account_equity as number).toLocaleString('en-US', { minimumFractionDigits: 2 })}`}
                mono
              />
            )}
            {Array.isArray(explanation.fundamental_events) &&
              explanation.fundamental_events.length > 0 && (
                <div className="py-1 border-b border-zinc-800/60">
                  <span className="text-zinc-500 text-xs block mb-1">Fundamental Events</span>
                  <div className="space-y-0.5">
                    {explanation.fundamental_events.map((ev, i) => (
                      <div key={i} className="text-xs text-amber-400 font-mono bg-amber-500/5 rounded px-2 py-0.5">
                        {typeof ev === 'string' ? ev : JSON.stringify(ev)}
                      </div>
                    ))}
                  </div>
                </div>
              )}
          </div>

          {/* ── 3. Setup Quality ────────────────────────────────────────────── */}
          {direction && (
            <>
              <SectionHeader icon={<DollarSign className="w-3.5 h-3.5" />} title="Setup Quality" />
              <div className="bg-zinc-800/40 rounded-lg p-3 space-y-0">
                <KVRow
                  label="Direction"
                  value={direction}
                  valueClass={direction === 'BUY' ? 'text-emerald-400 font-semibold' : 'text-red-400 font-semibold'}
                />
                {explanation.entry_price != null && (
                  <KVRow label="Entry Price" value={explanation.entry_price.toFixed(2)} mono />
                )}
                {explanation.sl_price != null && (
                  <KVRow label="Stop Loss" value={explanation.sl_price.toFixed(2)} mono valueClass="text-red-400" />
                )}
                {explanation.tp1_price != null && (
                  <KVRow label="Take Profit 1" value={explanation.tp1_price.toFixed(2)} mono valueClass="text-emerald-400" />
                )}
                {explanation.tp2_price != null && (
                  <KVRow label="Take Profit 2" value={explanation.tp2_price.toFixed(2)} mono valueClass="text-emerald-300" />
                )}
                {explanation.lot_size != null && (
                  <KVRow label="Lot Size" value={String(explanation.lot_size)} mono />
                )}
                {explanation.quality_score != null && (
                  <div className="py-1 border-b border-zinc-800/60">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-zinc-500 text-xs">Quality Score</span>
                      <span className="text-zinc-200 text-xs font-mono">
                        {(explanation.quality_score as number).toFixed(2)}
                      </span>
                    </div>
                    <ProgressBar value={explanation.quality_score as number} max={1} />
                  </div>
                )}
                {explanation.confidence_score != null && (
                  <div className="py-1">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-zinc-500 text-xs">Confidence Score</span>
                      <span className="text-zinc-200 text-xs font-mono">
                        {(explanation.confidence_score as number).toFixed(2)}
                      </span>
                    </div>
                    <ProgressBar value={explanation.confidence_score as number} max={1} />
                  </div>
                )}
              </div>
            </>
          )}

          {/* ── 4. Why This Decision? ────────────────────────────────────────── */}
          <SectionHeader icon={<Brain className="w-3.5 h-3.5" />} title="Why This Decision?" />

          {decision.decision === 'EXECUTE' && (
            <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-lg p-3">
              <div className="flex items-start gap-2">
                <Check className="w-4 h-4 text-emerald-400 flex-shrink-0 mt-0.5" />
                <p className="text-emerald-200 text-xs leading-relaxed">
                  {explanation.why_executed ?? decision.reason}
                </p>
              </div>
            </div>
          )}

          {decision.decision === 'REJECT' && rejectCat && (
            <div className="bg-red-500/5 border border-red-500/20 rounded-lg p-3">
              <div className="flex items-start gap-2">
                <span className="text-red-400 flex-shrink-0 mt-0.5">
                  {rejectCategoryIcon(rejectCat)}
                </span>
                <div>
                  <p className="text-red-300 text-xs font-semibold mb-1">
                    {rejectCategoryLabel(rejectCat)}
                  </p>
                  <p className="text-red-200 text-xs leading-relaxed">
                    {rejectCat === 'no_setup'
                      ? 'No valid setup found by strategy engine. The current market conditions did not produce a qualifying entry signal.'
                      : rejectCat === 'risk_manager'
                      ? (explanation.risk_reason as string | undefined) ?? decision.reason
                      : rejectCat === 'psychology'
                      ? (explanation.psych_reason as string | undefined) ?? decision.reason
                      : rejectCat === 'learning'
                      ? `Learning engine confidence below threshold. ${decision.reason}`
                      : decision.reason}
                  </p>
                </div>
              </div>
            </div>
          )}

          {decision.decision === 'DEFER' && (
            <div className="bg-amber-500/5 border border-amber-500/20 rounded-lg p-3">
              <div className="flex items-start gap-2">
                <Clock className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
                <p className="text-amber-200 text-xs leading-relaxed">
                  Deferred due to risk or market conditions. {decision.reason}
                </p>
              </div>
            </div>
          )}

          {/* ── 5. Full Explanation (collapsible) ───────────────────────────── */}
          <div className="mt-3 pt-3 border-t border-zinc-800">
            <button
              type="button"
              onClick={() => setJsonExpanded((v) => !v)}
              className="flex items-center gap-2 text-zinc-500 hover:text-zinc-300 text-xs transition-colors"
            >
              {jsonExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
              <Hash className="w-3.5 h-3.5" />
              Full Explanation JSON
            </button>

            {jsonExpanded && (
              <div className="mt-2 animate-in slide-in-from-top-1 duration-100">
                <div className="flex items-center justify-end mb-1.5">
                  <button
                    type="button"
                    onClick={handleCopyJson}
                    className="flex items-center gap-1.5 text-zinc-500 hover:text-zinc-300 text-xs transition-colors"
                  >
                    {copied ? (
                      <>
                        <Check className="w-3.5 h-3.5 text-emerald-400" />
                        <span className="text-emerald-400">Copied</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3.5 h-3.5" />
                        Copy JSON
                      </>
                    )}
                  </button>
                </div>
                <JsonViewer data={explanation} />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
