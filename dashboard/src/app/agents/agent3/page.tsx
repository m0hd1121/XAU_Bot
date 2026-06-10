'use client'

import { useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { cn } from '@/lib/utils'
import { apiClient } from '@/lib/api'
import type {
  TradeDecision,
  TradeRecord,
  AgentState,
  LogEntry,
} from '@/types'
import { PageHeader } from '@/components/ui/PageHeader'
import { MetricTile } from '@/components/ui/MetricTile'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Spinner } from '@/components/ui/Spinner'
import { Modal } from '@/components/ui/Modal'
import { JsonViewer } from '@/components/ui/JsonViewer'
import { DataTable } from '@/components/ui/DataTable'
import { AgentControlBar } from '@/components/agents/AgentControlBar'
import Link from 'next/link'
import {
  AlertTriangle,
  ExternalLink,
  X,
  Edit2,
  Save,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Shield,
  Activity,
} from 'lucide-react'

// ─── Format helpers ───────────────────────────────────────────────────────────

function fmtUSD(v: number | undefined | null): string {
  if (v == null) return '—'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(v)
}

function fmtPct(v: number | undefined | null, decimals = 2): string {
  if (v == null) return '—'
  const signed = v >= 0 ? `+${(v * 100).toFixed(decimals)}%` : `${(v * 100).toFixed(decimals)}%`
  return signed
}

function fmtNum(v: number | undefined | null, decimals = 2): string {
  if (v == null) return '—'
  return v.toFixed(decimals)
}

function timeAgo(ts: string | number | undefined): string {
  if (!ts) return '—'
  const date = typeof ts === 'string' ? new Date(ts) : new Date((ts as number) * 1000)
  const diff = Math.floor((Date.now() - date.getTime()) / 1000)
  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

function formatDateTime(ts: string | number | undefined): string {
  if (!ts) return '—'
  const date = typeof ts === 'string' ? new Date(ts) : new Date((ts as number) * 1000)
  return date.toLocaleString()
}

function pnlClass(v: number | undefined | null): string {
  if (v == null) return 'text-zinc-400'
  return v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-zinc-400'
}

// ─── Decision badge ───────────────────────────────────────────────────────────

function DecisionBadge({ decision }: { decision: 'EXECUTE' | 'REJECT' | 'DEFER' }) {
  const cfg = {
    EXECUTE: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    REJECT: 'bg-red-500/10 text-red-400 border-red-500/20',
    DEFER: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  }[decision]
  return (
    <span
      className={cn(
        'inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border',
        cfg
      )}
    >
      {decision}
    </span>
  )
}

// ─── Direction badge ──────────────────────────────────────────────────────────

function DirectionBadge({ direction }: { direction: string | undefined }) {
  if (!direction) return <span className="text-zinc-600">—</span>
  const upper = direction.toUpperCase()
  const isBuy = upper === 'BUY' || upper === 'LONG'
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold border',
        isBuy
          ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
          : 'bg-red-500/10 text-red-400 border-red-500/20'
      )}
    >
      {isBuy ? <TrendingUp className="w-2.5 h-2.5" /> : <TrendingDown className="w-2.5 h-2.5" />}
      {upper}
    </span>
  )
}

// ─── Outcome badge ────────────────────────────────────────────────────────────

function OutcomeBadge({ outcome }: { outcome: string | undefined }) {
  if (!outcome) return <span className="text-zinc-600">—</span>
  const cfg =
    outcome === 'WIN'
      ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
      : outcome === 'LOSS'
      ? 'bg-red-500/10 text-red-400 border-red-500/20'
      : 'bg-zinc-800 text-zinc-400 border-zinc-700'
  return (
    <span className={cn('inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold border', cfg)}>
      {outcome}
    </span>
  )
}

// ─── Decision explanation modal ───────────────────────────────────────────────

function DecisionModal({
  decision,
  open,
  onClose,
}: {
  decision: TradeDecision | null
  open: boolean
  onClose: () => void
}) {
  if (!decision) return null
  const exp = decision.explanation
  return (
    <Modal open={open} onClose={onClose} size="lg">
      <div className="bg-zinc-950 border border-zinc-800 rounded-xl overflow-hidden max-h-[90vh] flex flex-col">
        <div className="bg-zinc-900 border-b border-zinc-800 px-5 py-4 flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <DecisionBadge decision={decision.decision} />
              {exp.direction && <DirectionBadge direction={exp.direction} />}
              <span className="text-zinc-500 text-xs">
                {formatDateTime(decision.timestamp)}
              </span>
            </div>
            <p className="text-zinc-300 text-sm mt-1">{decision.reason}</p>
          </div>
          <button
            className="text-zinc-500 hover:text-zinc-200 transition-colors flex-shrink-0"
            onClick={onClose}
          >
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="overflow-y-auto flex-1 p-5 space-y-4">
          {/* Key metrics */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {exp.entry_price != null && (
              <MetricTile label="Entry" value={fmtNum(exp.entry_price, 2)} />
            )}
            {exp.sl_price != null && (
              <MetricTile label="Stop Loss" value={fmtNum(exp.sl_price, 2)} />
            )}
            {exp.tp1_price != null && (
              <MetricTile label="TP1" value={fmtNum(exp.tp1_price, 2)} />
            )}
            {exp.tp2_price != null && (
              <MetricTile label="TP2" value={fmtNum(exp.tp2_price, 2)} />
            )}
            {exp.lot_size != null && (
              <MetricTile label="Lot Size" value={String(exp.lot_size)} />
            )}
            {exp.risk_score != null && (
              <MetricTile
                label="Risk Score"
                value={fmtNum(exp.risk_score, 2)}
                valueClassName={exp.risk_score > 0.7 ? 'text-red-400' : 'text-zinc-100'}
              />
            )}
            {exp.quality_score != null && (
              <MetricTile label="Quality Score" value={fmtNum(exp.quality_score, 2)} />
            )}
            {exp.confidence_score != null && (
              <MetricTile label="Confidence" value={fmtPct(exp.confidence_score, 0)} />
            )}
            {exp.consecutive_losses != null && (
              <MetricTile
                label="Consec. Losses"
                value={String(exp.consecutive_losses)}
                valueClassName={exp.consecutive_losses > 2 ? 'text-red-400' : 'text-zinc-100'}
              />
            )}
            {exp.current_drawdown_pct != null && (
              <MetricTile
                label="Drawdown"
                value={fmtPct(exp.current_drawdown_pct, 1)}
                valueClassName="text-red-400"
              />
            )}
          </div>

          {/* Text reasons */}
          {exp.why_executed && (
            <div>
              <p className="text-zinc-500 text-xs font-medium mb-1">Why Executed</p>
              <p className="text-zinc-300 text-sm bg-emerald-500/5 border border-emerald-500/10 rounded-lg px-3 py-2">
                {exp.why_executed}
              </p>
            </div>
          )}
          {exp.risk_reason && (
            <div>
              <p className="text-zinc-500 text-xs font-medium mb-1">Risk Reason</p>
              <p className="text-zinc-300 text-sm bg-amber-500/5 border border-amber-500/10 rounded-lg px-3 py-2">
                {exp.risk_reason}
              </p>
            </div>
          )}
          {exp.psych_reason && (
            <div>
              <p className="text-zinc-500 text-xs font-medium mb-1">Psychology Filter</p>
              <p className="text-zinc-300 text-sm bg-red-500/5 border border-red-500/10 rounded-lg px-3 py-2">
                {exp.psych_reason}
              </p>
            </div>
          )}

          {/* Full explanation JSON */}
          <div>
            <p className="text-zinc-500 text-xs font-medium mb-2">Full Explanation</p>
            <JsonViewer data={exp as Record<string, unknown>} />
          </div>
        </div>
      </div>
    </Modal>
  )
}

// ─── Tab 1: Trading Dashboard ─────────────────────────────────────────────────

function TradingDashboardTab({
  agentState,
  decisions,
  openTrades,
  closedTrades,
  isPending,
  onCommand,
  onEmergencyStop,
}: {
  agentState: AgentState | null
  decisions: TradeDecision[]
  openTrades: TradeRecord[]
  closedTrades: TradeRecord[]
  isPending: boolean
  onCommand: (cmd: 'pause' | 'resume' | 'stop' | 'restart') => Promise<void>
  onEmergencyStop: () => void
}) {
  const [selectedDecision, setSelectedDecision] = useState<TradeDecision | null>(null)
  const [modalOpen, setModalOpen] = useState(false)

  const metrics = agentState?.metrics ?? {}
  const account = (metrics as { account?: { balance?: number; equity?: number; daily_pnl?: number; weekly_pnl?: number; monthly_pnl?: number; floating_pnl?: number } }).account

  // Try to extract PnL from decisions or metrics
  const dailyPnl = (metrics as { daily_pnl?: number }).daily_pnl ?? account?.daily_pnl ?? null
  const weeklyPnl = (metrics as { weekly_pnl?: number }).weekly_pnl ?? account?.weekly_pnl ?? null
  const monthlyPnl = (metrics as { monthly_pnl?: number }).monthly_pnl ?? account?.monthly_pnl ?? null
  const floatingPnl = (metrics as { floating_pnl?: number }).floating_pnl ?? account?.floating_pnl ?? null

  const openCount = metrics.open_trades_count ?? openTrades.length
  const maxTrades = (metrics as { max_open_trades?: number }).max_open_trades ?? 2
  const consecLosses = metrics.consecutive_losses ?? 0
  const activeStrategyHash = (metrics as { active_strategy_hash?: string }).active_strategy_hash
  const drawdownPct = (metrics as { current_drawdown_pct?: number }).current_drawdown_pct ?? null

  function openDecisionModal(d: TradeDecision) {
    setSelectedDecision(d)
    setModalOpen(true)
  }

  return (
    <div className="space-y-6">
      {/* Control row */}
      {agentState && (
        <div className="space-y-3">
          <AgentControlBar
            agentId="agent3"
            status={agentState.status}
            onCommand={onCommand}
            isPending={isPending}
          />
        </div>
      )}

      {/* P&L overview */}
      <div>
        <p className="text-zinc-500 text-xs font-medium uppercase tracking-wider mb-3">
          P&amp;L Overview
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <MetricTile
            label="Daily P&L"
            value={fmtUSD(dailyPnl)}
            valueClassName={pnlClass(dailyPnl)}
          />
          <MetricTile
            label="Weekly P&L"
            value={fmtUSD(weeklyPnl)}
            valueClassName={pnlClass(weeklyPnl)}
          />
          <MetricTile
            label="Monthly P&L"
            value={fmtUSD(monthlyPnl)}
            valueClassName={pnlClass(monthlyPnl)}
          />
          <MetricTile
            label="Floating P&L"
            value={fmtUSD(floatingPnl)}
            valueClassName={cn('text-lg font-bold', pnlClass(floatingPnl))}
          />
        </div>
      </div>

      {/* Trading stats */}
      <div>
        <p className="text-zinc-500 text-xs font-medium uppercase tracking-wider mb-3">
          Trading Stats
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <MetricTile
            label="Open Trades"
            value={`${openCount} / ${maxTrades}`}
          />
          <MetricTile
            label="Consecutive Losses"
            value={String(consecLosses)}
            valueClassName={consecLosses >= 3 ? 'text-red-400' : consecLosses > 0 ? 'text-amber-400' : 'text-zinc-100'}
          />
          <MetricTile
            label="Active Strategy"
            value={activeStrategyHash ? activeStrategyHash.slice(0, 8) : '—'}
            valueClassName="font-mono text-amber-400"
          />
          <MetricTile
            label="Drawdown"
            value={drawdownPct != null ? `${(drawdownPct * 100).toFixed(2)}%` : '—'}
            valueClassName={
              drawdownPct != null && drawdownPct > 0.1
                ? 'text-red-400'
                : drawdownPct != null && drawdownPct > 0.05
                ? 'text-amber-400'
                : 'text-zinc-100'
            }
          />
        </div>
      </div>

      {/* Open positions */}
      <Card className="bg-zinc-900 border border-zinc-800 rounded-xl">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium text-zinc-300 flex items-center gap-2">
            <Activity className="w-4 h-4 text-emerald-400" />
            Open Positions
            {openTrades.length > 0 && (
              <span className="ml-1.5 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[10px] px-1.5 py-0.5 rounded-full font-medium">
                {openTrades.length}
              </span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {openTrades.length === 0 ? (
            <div className="py-8 text-center text-zinc-600">
              <Activity className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">No open positions — agent is watching markets</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-800">
                    {['Symbol', 'Dir', 'Lots', 'Entry', 'Current', 'SL', 'TP1', 'Float PnL', 'PnL(R)', 'Actions'].map(
                      (h) => (
                        <th
                          key={h}
                          className="px-2 py-2 text-left text-zinc-500 text-[11px] font-medium uppercase tracking-wider whitespace-nowrap"
                        >
                          {h}
                        </th>
                      )
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/50">
                  {openTrades.map((t) => (
                    <tr key={t.id} className="hover:bg-zinc-800/30 transition-colors">
                      <td className="px-2 py-2.5 text-zinc-100 text-xs font-mono font-medium">
                        {t.symbol}
                      </td>
                      <td className="px-2 py-2.5">
                        <DirectionBadge direction={t.direction} />
                      </td>
                      <td className="px-2 py-2.5 text-zinc-300 text-xs font-mono">{t.lots}</td>
                      <td className="px-2 py-2.5 text-zinc-300 text-xs font-mono">
                        {fmtNum(t.entry_price, 2)}
                      </td>
                      <td className="px-2 py-2.5 text-zinc-300 text-xs font-mono">
                        {t.current_price != null ? fmtNum(t.current_price, 2) : '—'}
                      </td>
                      <td className="px-2 py-2.5 text-red-400 text-xs font-mono">
                        {t.sl_price != null ? fmtNum(t.sl_price, 2) : '—'}
                      </td>
                      <td className="px-2 py-2.5 text-emerald-400 text-xs font-mono">
                        {t.tp1_price != null ? fmtNum(t.tp1_price, 2) : '—'}
                      </td>
                      <td
                        className={cn('px-2 py-2.5 text-xs font-mono font-medium', pnlClass(t.pnl))}
                      >
                        {t.pnl != null ? fmtUSD(t.pnl) : '—'}
                      </td>
                      <td
                        className={cn('px-2 py-2.5 text-xs font-mono', pnlClass(t.pnl_r))}
                      >
                        {t.pnl_r != null ? `${t.pnl_r > 0 ? '+' : ''}${t.pnl_r.toFixed(2)}R` : '—'}
                      </td>
                      <td className="px-2 py-2.5">
                        <div className="flex items-center gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 px-2 text-[10px] text-red-400 hover:bg-red-500/10 hover:text-red-300"
                          >
                            Close
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 px-2 text-[10px] text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
                          >
                            <Edit2 className="w-3 h-3" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Recent decisions */}
      <Card className="bg-zinc-900 border border-zinc-800 rounded-xl">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-medium text-zinc-300">
              Recent Decisions
            </CardTitle>
            <a
              href="/explainability"
              className="flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              View All
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>
        </CardHeader>
        <CardContent>
          {decisions.length === 0 ? (
            <p className="text-zinc-600 text-sm py-4 text-center">No recent decisions</p>
          ) : (
            <div className="space-y-2">
              {decisions.slice(0, 10).map((d) => (
                <button
                  key={d.id}
                  className="w-full text-left bg-zinc-800/40 hover:bg-zinc-800 transition-colors rounded-lg px-3 py-2"
                  onClick={() => openDecisionModal(d)}
                >
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-zinc-500 text-[11px] font-mono">
                      {formatDateTime(d.timestamp)}
                    </span>
                    <DecisionBadge decision={d.decision} />
                    {d.explanation.direction && (
                      <DirectionBadge direction={d.explanation.direction} />
                    )}
                  </div>
                  <p className="text-zinc-400 text-xs mt-0.5 truncate">{d.reason}</p>
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Recent closed trades */}
      <Card className="bg-zinc-900 border border-zinc-800 rounded-xl">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium text-zinc-300">
            Recent Closed Trades
          </CardTitle>
        </CardHeader>
        <CardContent>
          {closedTrades.length === 0 ? (
            <p className="text-zinc-600 text-sm py-4 text-center">No recent closed trades</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-800">
                    {['Opened', 'Closed', 'Dir', 'Lots', 'Entry', 'Exit', 'P&L', 'Outcome'].map(
                      (h) => (
                        <th
                          key={h}
                          className="px-2 py-2 text-left text-zinc-500 text-[11px] font-medium uppercase tracking-wider whitespace-nowrap"
                        >
                          {h}
                        </th>
                      )
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/50">
                  {closedTrades.slice(0, 10).map((t) => (
                    <tr key={t.id} className="hover:bg-zinc-800/30 transition-colors">
                      <td className="px-2 py-2 text-zinc-500 text-xs">
                        {t.open_time ? timeAgo(t.open_time) : '—'}
                      </td>
                      <td className="px-2 py-2 text-zinc-500 text-xs">
                        {t.close_time ? timeAgo(t.close_time) : '—'}
                      </td>
                      <td className="px-2 py-2">
                        <DirectionBadge direction={t.direction} />
                      </td>
                      <td className="px-2 py-2 text-zinc-400 text-xs font-mono">{t.lots}</td>
                      <td className="px-2 py-2 text-zinc-300 text-xs font-mono">
                        {fmtNum(t.entry_price, 2)}
                      </td>
                      <td className="px-2 py-2 text-zinc-300 text-xs font-mono">
                        {t.current_price != null ? fmtNum(t.current_price, 2) : '—'}
                      </td>
                      <td className={cn('px-2 py-2 text-xs font-mono font-medium', pnlClass(t.pnl))}>
                        {t.pnl != null ? fmtUSD(t.pnl) : '—'}
                      </td>
                      <td className="px-2 py-2">
                        <OutcomeBadge outcome={t.outcome} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Decision modal */}
      <DecisionModal
        decision={selectedDecision}
        open={modalOpen}
        onClose={() => setModalOpen(false)}
      />
    </div>
  )
}

// ─── Tab 2: Risk Configuration ────────────────────────────────────────────────

interface RiskConfig {
  risk_per_trade: number
  max_risk_per_trade: number
  daily_loss_limit: number
  max_drawdown_kill: number
  min_rr: number
  max_open_trades: number
  max_consecutive_losses: number
  loss_streak_reduction: number
  cooldown_candles: number
  confidence_threshold: number
  min_quality_score: number
  max_trades_per_session: number
  revenge_trade_detection: boolean
}

const RISK_DEFAULTS: RiskConfig = {
  risk_per_trade: 0.01,
  max_risk_per_trade: 0.02,
  daily_loss_limit: 0.03,
  max_drawdown_kill: 0.10,
  min_rr: 2.0,
  max_open_trades: 2,
  max_consecutive_losses: 3,
  loss_streak_reduction: 0.5,
  cooldown_candles: 5,
  confidence_threshold: 0.6,
  min_quality_score: 0.6,
  max_trades_per_session: 2,
  revenge_trade_detection: true,
}

interface RiskParam {
  key: keyof RiskConfig
  label: string
  description: string
  type: 'range' | 'toggle'
  min?: number
  max?: number
  step?: number
  format?: (v: number) => string
}

const RISK_PARAMS: RiskParam[] = [
  {
    key: 'risk_per_trade',
    label: 'Risk Per Trade',
    description: 'Fraction of equity risked per trade. Lower values mean more conservative position sizing.',
    type: 'range',
    min: 0.005,
    max: 0.02,
    step: 0.001,
    format: (v) => `${(v * 100).toFixed(1)}%`,
  },
  {
    key: 'max_risk_per_trade',
    label: 'Max Risk Per Trade (Hard Cap)',
    description: 'Absolute maximum risk regardless of strategy recommendation.',
    type: 'range',
    min: 0.01,
    max: 0.05,
    step: 0.005,
    format: (v) => `${(v * 100).toFixed(1)}%`,
  },
  {
    key: 'daily_loss_limit',
    label: 'Daily Loss Limit',
    description: 'Maximum daily drawdown allowed before trading halts for the day.',
    type: 'range',
    min: 0.01,
    max: 0.10,
    step: 0.005,
    format: (v) => `${(v * 100).toFixed(1)}%`,
  },
  {
    key: 'max_drawdown_kill',
    label: 'Max Drawdown Kill Switch',
    description: 'Agent stops all trading and waits for manual review when this drawdown is reached.',
    type: 'range',
    min: 0.05,
    max: 0.25,
    step: 0.01,
    format: (v) => `${(v * 100).toFixed(1)}%`,
  },
  {
    key: 'min_rr',
    label: 'Min Reward : Risk Ratio',
    description: 'Minimum acceptable R:R for entering a trade.',
    type: 'range',
    min: 1.0,
    max: 4.0,
    step: 0.1,
    format: (v) => `${v.toFixed(1)}R`,
  },
  {
    key: 'max_open_trades',
    label: 'Max Open Trades',
    description: 'Maximum number of concurrent open positions.',
    type: 'range',
    min: 1,
    max: 5,
    step: 1,
    format: (v) => String(v),
  },
  {
    key: 'max_consecutive_losses',
    label: 'Max Consecutive Losses',
    description: 'After this many consecutive losses, the agent reduces position size.',
    type: 'range',
    min: 2,
    max: 6,
    step: 1,
    format: (v) => String(v),
  },
  {
    key: 'loss_streak_reduction',
    label: 'Loss Streak Size Reduction',
    description: 'Multiplier applied to lot size after consecutive losses. 0.5 = half size.',
    type: 'range',
    min: 0.25,
    max: 1.0,
    step: 0.05,
    format: (v) => `${(v * 100).toFixed(0)}%`,
  },
  {
    key: 'cooldown_candles',
    label: 'Cooldown Candles After Loss',
    description: 'Number of candles the agent must wait after a loss before re-entering.',
    type: 'range',
    min: 2,
    max: 20,
    step: 1,
    format: (v) => String(v),
  },
  {
    key: 'confidence_threshold',
    label: 'Entry Confidence Threshold',
    description: 'Minimum confidence score from learning engine required to enter.',
    type: 'range',
    min: 0.3,
    max: 0.9,
    step: 0.05,
    format: (v) => `${(v * 100).toFixed(0)}%`,
  },
  {
    key: 'min_quality_score',
    label: 'Min Setup Quality Score',
    description: 'Minimum strategy quality score required to execute a trade.',
    type: 'range',
    min: 0.3,
    max: 0.9,
    step: 0.05,
    format: (v) => `${(v * 100).toFixed(0)}%`,
  },
  {
    key: 'max_trades_per_session',
    label: 'Max Trades Per Session',
    description: 'Maximum trades allowed per trading session (London, NY, etc.).',
    type: 'range',
    min: 1,
    max: 5,
    step: 1,
    format: (v) => String(v),
  },
  {
    key: 'revenge_trade_detection',
    label: 'Revenge Trade Detection',
    description: 'Block trades that meet revenge-trading patterns (entered immediately after a loss).',
    type: 'toggle',
  },
]

function RiskConfigTab({
  agentState,
}: {
  agentState: AgentState | null
}) {
  const queryClient = useQueryClient()
  const [config, setConfig] = useState<RiskConfig>(RISK_DEFAULTS)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const metrics = agentState?.metrics ?? {}
  const equity = (metrics as { equity?: number }).equity ?? null
  const drawdown = (metrics as { current_drawdown_pct?: number }).current_drawdown_pct ?? null
  const killSwitchActive = (metrics as { kill_switch_active?: boolean }).kill_switch_active ?? false
  const tradingHalted = (metrics as { trading_halted?: boolean }).trading_halted ?? false

  async function handleSave() {
    setSaving(true)
    try {
      await apiClient.updateConfigField('risk', config)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } finally {
      setSaving(false)
    }
  }

  function updateField(key: keyof RiskConfig, value: number | boolean) {
    setConfig((c) => ({ ...c, [key]: value }))
  }

  return (
    <div className="space-y-6">
      {/* Read-only status */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricTile
          label="Account Equity"
          value={fmtUSD(equity)}
        />
        <MetricTile
          label="Current Drawdown"
          value={drawdown != null ? `${(drawdown * 100).toFixed(2)}%` : '—'}
          valueClassName={
            drawdown != null && drawdown > 0.1 ? 'text-red-400' : 'text-zinc-100'
          }
        />
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-3">
          <p className="text-zinc-500 text-[10px] uppercase tracking-wider mb-1">Kill Switch</p>
          <span
            className={cn(
              'inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-semibold border',
              killSwitchActive
                ? 'bg-red-500/10 text-red-400 border-red-500/20'
                : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
            )}
          >
            <span
              className={cn(
                'w-1.5 h-1.5 rounded-full',
                killSwitchActive ? 'bg-red-400' : 'bg-emerald-400'
              )}
            />
            {killSwitchActive ? 'ACTIVE' : 'NORMAL'}
          </span>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-3">
          <p className="text-zinc-500 text-[10px] uppercase tracking-wider mb-1">Trading</p>
          <span
            className={cn(
              'inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-semibold border',
              tradingHalted
                ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
            )}
          >
            {tradingHalted ? 'HALTED' : 'ACTIVE'}
          </span>
        </div>
      </div>

      {/* Parameters */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {RISK_PARAMS.map((param) => {
          const val = config[param.key]
          return (
            <div
              key={param.key}
              className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-2"
            >
              <div className="flex items-center justify-between gap-2">
                <label className="text-zinc-200 text-sm font-medium">{param.label}</label>
                {param.type === 'range' && (
                  <span className="text-amber-400 font-mono text-sm font-semibold">
                    {param.format ? param.format(val as number) : String(val)}
                  </span>
                )}
              </div>

              {param.type === 'range' && (
                <input
                  type="range"
                  min={param.min}
                  max={param.max}
                  step={param.step}
                  value={val as number}
                  onChange={(e) => updateField(param.key, Number(e.target.value))}
                  className="w-full accent-amber-500"
                />
              )}

              {param.type === 'toggle' && (
                <button
                  className={cn(
                    'relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none',
                    val ? 'bg-emerald-500' : 'bg-zinc-700'
                  )}
                  onClick={() => updateField(param.key, !val)}
                >
                  <span
                    className={cn(
                      'inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform',
                      val ? 'translate-x-6' : 'translate-x-1'
                    )}
                  />
                </button>
              )}

              <p className="text-zinc-600 text-xs leading-relaxed">{param.description}</p>
            </div>
          )
        })}
      </div>

      {/* Save button */}
      <div className="flex justify-end">
        <Button
          className={cn(
            'h-10 px-6 font-medium',
            saved
              ? 'bg-emerald-500 hover:bg-emerald-600 text-white border-0'
              : 'bg-amber-500 hover:bg-amber-600 text-zinc-950 border-0'
          )}
          onClick={handleSave}
          disabled={saving}
        >
          {saving ? (
            <Spinner size="sm" />
          ) : saved ? (
            <>
              <Shield className="w-4 h-4 mr-1.5" />
              Saved
            </>
          ) : (
            <>
              <Save className="w-4 h-4 mr-1.5" />
              Save Risk Configuration
            </>
          )}
        </Button>
      </div>
    </div>
  )
}

// ─── Tab 3: Execution Log ─────────────────────────────────────────────────────

type DecisionTypeFilter = 'all' | 'EXECUTE' | 'REJECT' | 'DEFER'
type DateRangeFilter = 'today' | 'week' | 'month' | 'all'

function ExecutionLogTab({ decisions }: { decisions: TradeDecision[] }) {
  const [typeFilter, setTypeFilter] = useState<DecisionTypeFilter>('all')
  const [reasonSearch, setReasonSearch] = useState('')
  const [dateRange, setDateRange] = useState<DateRangeFilter>('all')
  const [page, setPage] = useState(0)
  const [selectedDecision, setSelectedDecision] = useState<TradeDecision | null>(null)
  const [modalOpen, setModalOpen] = useState(false)

  const PAGE_SIZE = 20

  const now = Date.now() / 1000
  const rangeMap: Record<DateRangeFilter, number> = {
    today: 86400,
    week: 7 * 86400,
    month: 30 * 86400,
    all: Infinity,
  }

  const filtered = decisions.filter((d) => {
    if (typeFilter !== 'all' && d.decision !== typeFilter) return false
    if (reasonSearch.trim() && !d.reason.toLowerCase().includes(reasonSearch.toLowerCase()))
      return false
    if (dateRange !== 'all' && now - d.timestamp > rangeMap[dateRange]) return false
    return true
  })

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE)
  const paginated = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  function openModal(d: TradeDecision) {
    setSelectedDecision(d)
    setModalOpen(true)
  }

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          {(['all', 'EXECUTE', 'REJECT', 'DEFER'] as DecisionTypeFilter[]).map((f) => (
            <button
              key={f}
              className={cn(
                'px-3 py-1 rounded-full text-xs font-medium border transition-colors',
                typeFilter === f
                  ? f === 'EXECUTE'
                    ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                    : f === 'REJECT'
                    ? 'bg-red-500/20 text-red-400 border-red-500/30'
                    : f === 'DEFER'
                    ? 'bg-amber-500/20 text-amber-400 border-amber-500/30'
                    : 'bg-zinc-700 text-zinc-100 border-zinc-600'
                  : 'bg-zinc-900 text-zinc-400 border-zinc-800 hover:border-zinc-600 hover:text-zinc-200'
              )}
              onClick={() => {
                setTypeFilter(f)
                setPage(0)
              }}
            >
              {f === 'all' ? 'All' : f}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <input
            type="text"
            placeholder="Search reason…"
            value={reasonSearch}
            onChange={(e) => {
              setReasonSearch(e.target.value)
              setPage(0)
            }}
            className="flex-1 max-w-xs bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500"
          />
          <div className="flex items-center gap-1">
            {(['today', 'week', 'month', 'all'] as DateRangeFilter[]).map((r) => (
              <button
                key={r}
                className={cn(
                  'px-2.5 py-1 rounded text-xs font-medium transition-colors',
                  dateRange === r
                    ? 'bg-zinc-700 text-zinc-100'
                    : 'text-zinc-500 hover:text-zinc-300'
                )}
                onClick={() => {
                  setDateRange(r)
                  setPage(0)
                }}
              >
                {r === 'today' ? 'Today' : r === 'week' ? 'Week' : r === 'month' ? 'Month' : 'All'}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-zinc-800">
        <table className="w-full text-sm">
          <thead className="bg-zinc-900 border-b border-zinc-800">
            <tr>
              {['Timestamp', 'Decision', 'Direction', 'Reason', 'Quality', 'Confidence', 'Regime'].map((h) => (
                <th key={h} className="px-3 py-2.5 text-left text-zinc-500 text-[11px] font-medium uppercase tracking-wider whitespace-nowrap">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/60">
            {paginated.length === 0 ? (
              <tr>
                <td colSpan={7} className="text-center py-8 text-zinc-600 text-sm">
                  No decisions match your filters
                </td>
              </tr>
            ) : (
              paginated.map((d) => (
                <tr
                  key={d.id}
                  className="hover:bg-zinc-800/40 cursor-pointer transition-colors"
                  onClick={() => openModal(d)}
                >
                  <td className="px-3 py-2.5 text-zinc-500 text-xs font-mono whitespace-nowrap">
                    {formatDateTime(d.timestamp)}
                  </td>
                  <td className="px-3 py-2.5">
                    <DecisionBadge decision={d.decision} />
                  </td>
                  <td className="px-3 py-2.5">
                    <DirectionBadge direction={d.explanation.direction} />
                  </td>
                  <td className="px-3 py-2.5 text-zinc-400 text-xs max-w-[200px] truncate">
                    {d.reason}
                  </td>
                  <td className="px-3 py-2.5 text-zinc-300 text-xs font-mono">
                    {d.explanation.quality_score != null
                      ? fmtNum(d.explanation.quality_score, 2)
                      : '—'}
                  </td>
                  <td className="px-3 py-2.5 text-zinc-300 text-xs font-mono">
                    {d.explanation.confidence_score != null
                      ? `${(d.explanation.confidence_score * 100).toFixed(0)}%`
                      : '—'}
                  </td>
                  <td className="px-3 py-2.5 text-zinc-400 text-xs">
                    {d.explanation.regime ?? '—'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <span className="text-zinc-500 text-xs">
            {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, filtered.length)} of {filtered.length}
          </span>
          <div className="flex gap-1">
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-xs text-zinc-400"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
            >
              Prev
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-xs text-zinc-400"
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page === totalPages - 1}
            >
              Next
            </Button>
          </div>
        </div>
      )}

      <DecisionModal
        decision={selectedDecision}
        open={modalOpen}
        onClose={() => setModalOpen(false)}
      />
    </div>
  )
}

// ─── Tab 4: Trade History ─────────────────────────────────────────────────────

type DirectionFilter = 'all' | 'BUY' | 'SELL'
type OutcomeFilter = 'all' | 'WIN' | 'LOSS' | 'BE'

function TradeHistoryTab() {
  const [dirFilter, setDirFilter] = useState<DirectionFilter>('all')
  const [outcomeFilter, setOutcomeFilter] = useState<OutcomeFilter>('all')
  const [dateRange, setDateRange] = useState<DateRangeFilter>('all')
  const [page, setPage] = useState(0)

  const PAGE_SIZE = 25

  const { data, isLoading } = useQuery({
    queryKey: ['trades', 'history', page, dirFilter, outcomeFilter, dateRange],
    queryFn: () => apiClient.getTradeHistory(page + 1, PAGE_SIZE),
  })

  const trades = data?.trades ?? []
  const total = data?.total ?? 0
  const totalPages = Math.ceil(total / PAGE_SIZE)

  const filtered = trades.filter((t) => {
    const dir = t.direction.toUpperCase()
    if (dirFilter !== 'all' && dir !== dirFilter && !(dirFilter === 'BUY' && dir === 'LONG') && !(dirFilter === 'SELL' && dir === 'SHORT')) return false
    if (outcomeFilter !== 'all' && t.outcome !== outcomeFilter) return false
    return true
  })

  const wins = trades.filter((t) => t.outcome === 'WIN').length
  const losses = trades.filter((t) => t.outcome === 'LOSS').length
  const totalPnl = trades.reduce((sum, t) => sum + (t.pnl ?? 0), 0)

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <Spinner />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricTile label="Total Closed" value={String(total)} />
        <MetricTile
          label="Wins"
          value={String(wins)}
          valueClassName="text-emerald-400"
        />
        <MetricTile
          label="Losses"
          value={String(losses)}
          valueClassName="text-red-400"
        />
        <MetricTile
          label="Total P&L"
          value={fmtUSD(totalPnl)}
          valueClassName={pnlClass(totalPnl)}
        />
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-1">
          {(['all', 'BUY', 'SELL'] as DirectionFilter[]).map((f) => (
            <button
              key={f}
              className={cn(
                'px-2.5 py-1 rounded-full text-xs font-medium border transition-colors',
                dirFilter === f
                  ? 'bg-zinc-700 text-zinc-100 border-zinc-600'
                  : 'bg-zinc-900 text-zinc-400 border-zinc-800 hover:border-zinc-600 hover:text-zinc-200'
              )}
              onClick={() => {
                setDirFilter(f)
                setPage(0)
              }}
            >
              {f === 'all' ? 'All Dir' : f}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1">
          {(['all', 'WIN', 'LOSS', 'BE'] as OutcomeFilter[]).map((f) => (
            <button
              key={f}
              className={cn(
                'px-2.5 py-1 rounded-full text-xs font-medium border transition-colors',
                outcomeFilter === f
                  ? f === 'WIN'
                    ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                    : f === 'LOSS'
                    ? 'bg-red-500/20 text-red-400 border-red-500/30'
                    : 'bg-zinc-700 text-zinc-100 border-zinc-600'
                  : 'bg-zinc-900 text-zinc-400 border-zinc-800 hover:border-zinc-600 hover:text-zinc-200'
              )}
              onClick={() => {
                setOutcomeFilter(f)
                setPage(0)
              }}
            >
              {f === 'all' ? 'All Outcomes' : f}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1 ml-auto">
          {(['today', 'week', 'month', 'all'] as DateRangeFilter[]).map((r) => (
            <button
              key={r}
              className={cn(
                'px-2.5 py-1 rounded text-xs font-medium transition-colors',
                dateRange === r ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'
              )}
              onClick={() => {
                setDateRange(r)
                setPage(0)
              }}
            >
              {r === 'today' ? 'Today' : r === 'week' ? 'Week' : r === 'month' ? 'Month' : 'All'}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-zinc-800">
        <table className="w-full text-sm">
          <thead className="bg-zinc-900 border-b border-zinc-800">
            <tr>
              {['ID', 'Opened', 'Symbol', 'Dir', 'Lots', 'Entry', 'Exit', 'P&L($)', 'P&L(R)', 'Outcome', 'Reason'].map((h) => (
                <th key={h} className="px-3 py-2.5 text-left text-zinc-500 text-[11px] font-medium uppercase tracking-wider whitespace-nowrap">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/60">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={11} className="text-center py-8 text-zinc-600 text-sm">
                  No trade history
                </td>
              </tr>
            ) : (
              filtered.map((t) => (
                <tr key={t.id} className="hover:bg-zinc-800/30 transition-colors">
                  <td className="px-3 py-2.5 text-zinc-600 text-xs font-mono">{t.id}</td>
                  <td className="px-3 py-2.5 text-zinc-500 text-xs whitespace-nowrap">
                    {t.open_time ? timeAgo(t.open_time) : '—'}
                  </td>
                  <td className="px-3 py-2.5 text-zinc-200 text-xs font-mono font-medium">{t.symbol}</td>
                  <td className="px-3 py-2.5">
                    <DirectionBadge direction={t.direction} />
                  </td>
                  <td className="px-3 py-2.5 text-zinc-400 text-xs font-mono">{t.lots}</td>
                  <td className="px-3 py-2.5 text-zinc-300 text-xs font-mono">{fmtNum(t.entry_price, 2)}</td>
                  <td className="px-3 py-2.5 text-zinc-300 text-xs font-mono">
                    {t.current_price != null ? fmtNum(t.current_price, 2) : '—'}
                  </td>
                  <td className={cn('px-3 py-2.5 text-xs font-mono font-medium', pnlClass(t.pnl))}>
                    {t.pnl != null ? fmtUSD(t.pnl) : '—'}
                  </td>
                  <td className={cn('px-3 py-2.5 text-xs font-mono', pnlClass(t.pnl_r))}>
                    {t.pnl_r != null ? `${t.pnl_r > 0 ? '+' : ''}${t.pnl_r.toFixed(2)}R` : '—'}
                  </td>
                  <td className="px-3 py-2.5">
                    <OutcomeBadge outcome={t.outcome} />
                  </td>
                  <td className="px-3 py-2.5 text-zinc-500 text-xs truncate max-w-[120px]">
                    {t.close_reason ?? '—'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <span className="text-zinc-500 text-xs">
            Page {page + 1} of {totalPages} ({total} total)
          </span>
          <div className="flex gap-1">
            <Button variant="ghost" size="sm" className="h-7 px-2 text-xs text-zinc-400" onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0}>
              Prev
            </Button>
            <Button variant="ghost" size="sm" className="h-7 px-2 text-xs text-zinc-400" onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))} disabled={page === totalPages - 1}>
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Tab 5: Live Logs ─────────────────────────────────────────────────────────

function LiveLogsTab() {
  const { data, isLoading } = useQuery({
    queryKey: ['logs', 'agent3'],
    queryFn: () => apiClient.getLogs({ type: 'agent3', limit: 50 }),
    refetchInterval: 5_000,
  })

  const logs = data?.logs ?? []

  const levelStyles: Record<string, string> = {
    DEBUG: 'text-zinc-600',
    INFO: 'text-zinc-400',
    WARNING: 'text-amber-400',
    ERROR: 'text-red-400',
    CRITICAL: 'text-red-500 font-bold',
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-zinc-500 text-xs">Auto-refreshes every 5 seconds</p>
        {isLoading && <Spinner size="sm" />}
      </div>
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
        <div className="overflow-x-auto max-h-[600px] overflow-y-auto">
          <table className="w-full text-xs font-mono">
            <thead className="bg-zinc-950 border-b border-zinc-800 sticky top-0">
              <tr>
                <th className="px-3 py-2 text-left text-zinc-600 font-medium">Timestamp</th>
                <th className="px-3 py-2 text-left text-zinc-600 font-medium">Level</th>
                <th className="px-3 py-2 text-left text-zinc-600 font-medium">Source</th>
                <th className="px-3 py-2 text-left text-zinc-600 font-medium">Message</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/30">
              {isLoading && logs.length === 0 ? (
                <tr>
                  <td colSpan={4} className="py-8 text-center text-zinc-600">
                    Loading logs…
                  </td>
                </tr>
              ) : logs.length === 0 ? (
                <tr>
                  <td colSpan={4} className="py-8 text-center text-zinc-600">
                    No logs yet
                  </td>
                </tr>
              ) : (
                logs.map((log, i) => (
                  <tr key={`${log.timestamp}-${i}`} className="hover:bg-zinc-800/20">
                    <td className="px-3 py-1.5 text-zinc-600 whitespace-nowrap">
                      {log.timestamp}
                    </td>
                    <td
                      className={cn(
                        'px-3 py-1.5 w-20 whitespace-nowrap',
                        levelStyles[log.level] ?? 'text-zinc-400'
                      )}
                    >
                      {log.level}
                    </td>
                    <td className="px-3 py-1.5 text-zinc-600 whitespace-nowrap max-w-[120px] truncate">
                      {log.source}
                    </td>
                    <td className="px-3 py-1.5 text-zinc-300 break-all">{log.message}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

type ActiveTab = 'dashboard' | 'risk' | 'log' | 'history' | 'logs'

const TABS: { key: ActiveTab; label: string }[] = [
  { key: 'dashboard', label: 'Trading Dashboard' },
  { key: 'risk', label: 'Risk Configuration' },
  { key: 'log', label: 'Execution Log' },
  { key: 'history', label: 'Trade History' },
  { key: 'logs', label: 'Live Logs' },
]

export default function Agent3Page() {
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState<ActiveTab>('dashboard')

  // ── Data ────────────────────────────────────────────────────────────────

  const { data: agentState } = useQuery({
    queryKey: ['agent', 'agent3'],
    queryFn: () => apiClient.getAgentStatus('agent3'),
    refetchInterval: 10_000,
  })

  const { data: decisions = [], isLoading: loadingDecisions } = useQuery({
    queryKey: ['decisions', 'recent', 100],
    queryFn: () => apiClient.getRecentDecisions(100),
    refetchInterval: 15_000,
  })

  const { data: openTrades = [] } = useQuery({
    queryKey: ['trades', 'open'],
    queryFn: () => apiClient.getOpenTrades(),
    refetchInterval: 10_000,
  })

  const { data: historyData } = useQuery({
    queryKey: ['trades', 'history', 1, 10],
    queryFn: () => apiClient.getTradeHistory(1, 10),
  })

  const closedTrades = historyData?.trades ?? []

  // ── Mutations ────────────────────────────────────────────────────────────

  const controlMutation = useMutation({
    mutationFn: (cmd: 'pause' | 'resume' | 'stop' | 'restart') =>
      apiClient.controlAgent('agent3', cmd),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['agent', 'agent3'] })
    },
  })

  const handleCommand = useCallback(
    async (cmd: 'pause' | 'resume' | 'stop' | 'restart') => {
      await controlMutation.mutateAsync(cmd)
    },
    [controlMutation]
  )

  function handleEmergencyStop() {
    if (
      window.confirm(
        'EMERGENCY STOP: This will immediately halt Agent 3. All open positions will remain open. Continue?'
      )
    ) {
      controlMutation.mutate('stop')
    }
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="max-w-[1400px] mx-auto px-4 py-6 space-y-6">
        {/* Page header */}
        <PageHeader
          title="Agent 3 — Live Trader"
          subtitle="Manages trade execution, position sizing, and real-time risk management"
          badge={
            agentState && (
              <span
                className={cn(
                  'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border',
                  agentState.status === 'running'
                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                    : agentState.status === 'paused'
                    ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                    : 'bg-red-500/10 text-red-400 border-red-500/20'
                )}
              >
                <span
                  className={cn(
                    'w-1.5 h-1.5 rounded-full',
                    agentState.status === 'running'
                      ? 'bg-emerald-400 animate-pulse'
                      : agentState.status === 'paused'
                      ? 'bg-amber-400'
                      : 'bg-red-400'
                  )}
                />
                {agentState.status.charAt(0).toUpperCase() + agentState.status.slice(1)}
              </span>
            )
          }
        />

        {/* Tabs */}
        <div className="flex border-b border-zinc-800 overflow-x-auto">
          {TABS.map(({ key, label }) => (
            <button
              key={key}
              className={cn(
                'px-4 py-3 text-sm font-medium transition-colors border-b-2 -mb-px whitespace-nowrap',
                activeTab === key
                  ? 'text-zinc-100 border-amber-500'
                  : 'text-zinc-500 border-transparent hover:text-zinc-300 hover:border-zinc-700'
              )}
              onClick={() => setActiveTab(key)}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div>
          {activeTab === 'dashboard' && (
            <TradingDashboardTab
              agentState={agentState ?? null}
              decisions={decisions}
              openTrades={openTrades}
              closedTrades={closedTrades}
              isPending={controlMutation.isPending}
              onCommand={handleCommand}
              onEmergencyStop={handleEmergencyStop}
            />
          )}
          {activeTab === 'risk' && (
            <RiskConfigTab agentState={agentState ?? null} />
          )}
          {activeTab === 'log' && (
            <ExecutionLogTab decisions={decisions} />
          )}
          {activeTab === 'history' && <TradeHistoryTab />}
          {activeTab === 'logs' && <LiveLogsTab />}
        </div>
      </div>
    </div>
  )
}
