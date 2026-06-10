'use client'

import { cn } from '@/lib/utils'
import { MarketIntel, MarketRegime } from '@/types'
import { Badge } from '@/components/ui/Badge'
import { ProgressBar } from '@/components/ui/ProgressBar'
import { Spinner } from '@/components/ui/Spinner'
import { formatUnixTimestamp } from '@/lib/utils'
import {
  TrendingUp,
  TrendingDown,
  Minus,
  Clock,
  AlertTriangle,
} from 'lucide-react'

export interface Agent2IntelligenceProps {
  intel: MarketIntel | null
  loading?: boolean
  compact?: boolean
}

// ─── Regime color helpers ────────────────────────────────────────────────────

function regimeBg(regime: string): string {
  switch (regime) {
    case 'TRENDING_BULLISH': return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
    case 'TRENDING_BEARISH': return 'bg-red-500/10 text-red-400 border-red-500/20'
    case 'RANGING': return 'bg-sky-500/10 text-sky-400 border-sky-500/20'
    case 'HIGH_VOLATILITY': return 'bg-amber-500/10 text-amber-400 border-amber-500/20'
    default: return 'bg-zinc-700/50 text-zinc-400 border-zinc-700'
  }
}

function riskColor(score: number): 'emerald' | 'amber' | 'red' {
  if (score > 0.75) return 'red'
  if (score > 0.4) return 'amber'
  return 'emerald'
}

function riskTextColor(score: number): string {
  if (score > 0.75) return 'text-red-400'
  if (score > 0.4) return 'text-amber-400'
  return 'text-emerald-400'
}

function TrendIcon({ trend }: { trend: string }) {
  const lower = trend?.toLowerCase() ?? ''
  if (lower.includes('bull') || lower.includes('up')) {
    return <TrendingUp className="w-4 h-4 text-emerald-400" />
  }
  if (lower.includes('bear') || lower.includes('down')) {
    return <TrendingDown className="w-4 h-4 text-red-400" />
  }
  return <Minus className="w-4 h-4 text-zinc-400" />
}

// ─── Compact mode ────────────────────────────────────────────────────────────

function CompactView({ intel }: { intel: MarketIntel }) {
  return (
    <div className="flex items-center gap-3 flex-wrap">
      <span
        className={cn(
          'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border',
          regimeBg(intel.regime)
        )}
      >
        {intel.regime.replace(/_/g, ' ')}
      </span>
      <span className={cn('text-xs font-mono', riskTextColor(intel.risk_score))}>
        Risk {intel.risk_score.toFixed(2)}
      </span>
      <span className="inline-flex items-center gap-1 text-xs text-zinc-400 bg-zinc-800 px-2 py-0.5 rounded-full">
        {intel.session}
      </span>
      <span className="inline-flex items-center gap-1 text-xs text-zinc-500">
        <Clock className="w-3 h-3" />
        {formatUnixTimestamp(intel.timestamp)}
      </span>
    </div>
  )
}

// ─── Full mode ───────────────────────────────────────────────────────────────

function FullView({ intel }: { intel: MarketIntel }) {
  const technical = intel.technical ?? {}
  const fundamental = intel.fundamental ?? {}

  // Extract key technical notes
  const techNotes: string[] = []
  if (technical.atr != null) techNotes.push(`ATR: ${Number(technical.atr).toFixed(4)}`)
  if (technical.volatility_pct != null) techNotes.push(`Volatility: ${Number(technical.volatility_pct).toFixed(2)}%`)
  if (technical.bos_count != null) techNotes.push(`BOS events: ${technical.bos_count}`)
  if (technical.choch_count != null) techNotes.push(`CHoCH events: ${technical.choch_count}`)
  if (technical.sd_zones != null) techNotes.push(`S/D zones: ${technical.sd_zones}`)

  // Upcoming high-impact events within 4 hours
  const upcomingEvents = (fundamental.upcoming_events as Array<Record<string, unknown>> | undefined) ?? []
  const nowSec = Date.now() / 1000
  const highImpactSoon = upcomingEvents.filter((ev) => {
    const evTime = ev.time as number | undefined
    const impact = (ev.impact as string | undefined) ?? ''
    return evTime != null &&
      evTime > nowSec &&
      evTime - nowSec <= 4 * 3600 &&
      impact.toLowerCase() === 'high'
  })

  return (
    <div className="space-y-3">
      {/* Regime + risk row */}
      <div className="flex items-center gap-3 flex-wrap">
        <span
          className={cn(
            'inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-medium border',
            regimeBg(intel.regime)
          )}
        >
          <TrendIcon trend={intel.trend} />
          {intel.regime.replace(/_/g, ' ')}
        </span>
        <span className="text-zinc-500 text-xs">{intel.session}</span>
        <span className="text-zinc-500 text-xs ml-auto">
          {formatUnixTimestamp(intel.timestamp)}
        </span>
      </div>

      {/* Risk score bar */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs text-zinc-500">Risk Score</span>
          <span className={cn('text-xs font-mono font-semibold', riskTextColor(intel.risk_score))}>
            {intel.risk_score.toFixed(2)}
          </span>
        </div>
        <ProgressBar
          value={intel.risk_score * 100}
          max={100}
          color={riskColor(intel.risk_score)}
          size="sm"
        />
      </div>

      {/* Confidence */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-zinc-500">Confidence</span>
        <span className="text-xs font-mono text-zinc-300">
          {(intel.confidence * 100).toFixed(1)}%
        </span>
      </div>

      {/* Technical notes */}
      {techNotes.length > 0 && (
        <ul className="space-y-0.5">
          {techNotes.map((note) => (
            <li key={note} className="text-xs text-zinc-400 flex items-start gap-1.5">
              <span className="text-zinc-600 mt-0.5">•</span>
              {note}
            </li>
          ))}
        </ul>
      )}

      {/* Upcoming high-impact event */}
      {highImpactSoon.length > 0 && (
        <div className="flex items-start gap-2 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2">
          <AlertTriangle className="w-3.5 h-3.5 text-amber-400 flex-shrink-0 mt-0.5" />
          <div>
            <span className="text-xs font-medium text-amber-400">High-impact event soon</span>
            {highImpactSoon.slice(0, 2).map((ev, i) => (
              <p key={i} className="text-xs text-zinc-400 mt-0.5">
                {ev.name as string} — {ev.currency as string}
              </p>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Main component ──────────────────────────────────────────────────────────

export function Agent2Intelligence({ intel, loading = false, compact = false }: Agent2IntelligenceProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-4">
        <Spinner size="sm" />
      </div>
    )
  }

  if (!intel) {
    return (
      <div className="flex items-center gap-2 text-zinc-500 text-sm">
        <Minus className="w-4 h-4" />
        No intelligence data available
      </div>
    )
  }

  if (compact) {
    return <CompactView intel={intel} />
  }

  return <FullView intel={intel} />
}
