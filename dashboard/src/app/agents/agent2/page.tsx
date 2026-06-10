'use client'

import { useState, useEffect, useRef, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { cn, formatUnixTimestamp, formatUnixTime } from '@/lib/utils'
import { apiClient } from '@/lib/api'
import type { AgentState, MarketIntel, LogEntry, LogLevel } from '@/types'
import { AgentControlBar } from '@/components/agents/AgentControlBar'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Spinner } from '@/components/ui/Spinner'
import { ProgressBar } from '@/components/ui/ProgressBar'
import { PageHeader } from '@/components/ui/PageHeader'
import { Tabs } from '@/components/ui/Tabs'
import { JsonViewer } from '@/components/ui/JsonViewer'
import { LineChart } from '@/components/charts/LineChart'
import { BarChart } from '@/components/charts/BarChart'
import {
  TrendingUp,
  TrendingDown,
  Minus,
  AlertTriangle,
  Clock,
  Globe,
  Layers,
  Activity,
  ChevronDown,
  ChevronUp,
  Shield,
  Zap,
  Save,
  CheckCircle,
  Info,
  Filter,
  Terminal,
} from 'lucide-react'

// ─── Constants & helpers ──────────────────────────────────────────────────────

type MarketRegime = 'TRENDING_BULLISH' | 'TRENDING_BEARISH' | 'RANGING' | 'HIGH_VOLATILITY' | 'UNCERTAIN' | 'UNKNOWN'

function regimeClasses(regime: string): { bg: string; text: string; border: string } {
  switch (regime) {
    case 'TRENDING_BULLISH':
      return { bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/20' }
    case 'TRENDING_BEARISH':
      return { bg: 'bg-red-500/10', text: 'text-red-400', border: 'border-red-500/20' }
    case 'RANGING':
      return { bg: 'bg-sky-500/10', text: 'text-sky-400', border: 'border-sky-500/20' }
    case 'HIGH_VOLATILITY':
      return { bg: 'bg-amber-500/10', text: 'text-amber-400', border: 'border-amber-500/20' }
    default:
      return { bg: 'bg-zinc-700/50', text: 'text-zinc-400', border: 'border-zinc-700' }
  }
}

function riskColor(score: number): 'emerald' | 'amber' | 'red' {
  if (score > 0.75) return 'red'
  if (score > 0.4) return 'amber'
  return 'emerald'
}

function riskTextClass(score: number): string {
  if (score > 0.75) return 'text-red-400'
  if (score > 0.4) return 'text-amber-400'
  return 'text-emerald-400'
}

function TrendIcon({ trend }: { trend: string }) {
  const lower = trend?.toLowerCase() ?? ''
  if (lower.includes('bull') || lower.includes('up')) {
    return <TrendingUp className="w-5 h-5 text-emerald-400" />
  }
  if (lower.includes('bear') || lower.includes('down')) {
    return <TrendingDown className="w-5 h-5 text-red-400" />
  }
  return <Minus className="w-5 h-5 text-zinc-400" />
}

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h > 0) return `${h}h ${m}m`
  return `${m}m ${Math.floor(seconds % 60)}s`
}

function impactBadge(impact: string): string {
  switch (impact?.toLowerCase()) {
    case 'high': return 'bg-red-500/10 text-red-400 border-red-500/20'
    case 'medium':
    case 'med': return 'bg-amber-500/10 text-amber-400 border-amber-500/20'
    default: return 'bg-zinc-800 text-zinc-500 border-zinc-700'
  }
}

const LOG_LEVELS: LogLevel[] = ['DEBUG', 'INFO', 'WARNING', 'ERROR']

function logLevelColor(level: LogLevel): string {
  switch (level) {
    case 'ERROR':
    case 'CRITICAL': return 'text-red-400'
    case 'WARNING': return 'text-amber-400'
    case 'DEBUG': return 'text-zinc-500'
    default: return 'text-zinc-300'
  }
}

function Tooltip({ text, children }: { text: string; children: React.ReactNode }) {
  return (
    <div className="relative group inline-flex items-center">
      {children}
      <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-56 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-zinc-300 shadow-xl opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity z-50 text-left">
        {text}
      </div>
    </div>
  )
}

// ─── Regime Hero Card ─────────────────────────────────────────────────────────

function RegimeHeroCard({ intel }: { intel: MarketIntel }) {
  const rc = regimeClasses(intel.regime)
  const rs = intel.risk_score

  return (
    <Card className={cn('border rounded-xl', rc.bg, rc.border)}>
      <CardContent className="p-6">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
          {/* Regime name + trend */}
          <div className="flex items-center gap-4">
            <div className={cn('w-14 h-14 rounded-2xl flex items-center justify-center border-2', rc.bg, rc.border)}>
              <TrendIcon trend={intel.trend} />
            </div>
            <div>
              <p className="text-xs text-zinc-500 uppercase tracking-wider mb-1">Market Regime</p>
              <h2 className={cn('text-2xl font-bold tracking-tight', rc.text)}>
                {intel.regime.replace(/_/g, ' ')}
              </h2>
              <p className="text-sm text-zinc-400 mt-0.5">
                Trend: {intel.trend || '—'}
              </p>
            </div>
          </div>

          {/* Metrics row */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {/* Risk score */}
            <div className="min-w-[100px]">
              <p className="text-xs text-zinc-500 mb-1">Risk Score</p>
              <p className={cn('text-2xl font-mono font-bold', riskTextClass(rs))}>
                {rs.toFixed(2)}
              </p>
              <div className="mt-1.5">
                <ProgressBar value={rs * 100} max={100} color={riskColor(rs)} size="sm" />
              </div>
            </div>

            {/* Confidence */}
            <div>
              <p className="text-xs text-zinc-500 mb-1">Confidence</p>
              <p className="text-2xl font-mono font-bold text-zinc-200">
                {(intel.confidence * 100).toFixed(0)}
                <span className="text-base text-zinc-500">%</span>
              </p>
            </div>

            {/* Session */}
            <div>
              <p className="text-xs text-zinc-500 mb-1">Session</p>
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-zinc-800 border border-zinc-700 text-sm text-zinc-200 font-medium">
                <Globe className="w-3.5 h-3.5 text-zinc-400" />
                {intel.session || '—'}
              </span>
            </div>

            {/* Last update */}
            <div>
              <p className="text-xs text-zinc-500 mb-1">Last Update</p>
              <p className="text-xs text-zinc-300 font-mono">
                {formatUnixTimestamp(intel.timestamp)}
              </p>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// ─── Analysis cards ───────────────────────────────────────────────────────────

function TechnicalCard({ technical }: { technical: Record<string, unknown> }) {
  return (
    <Card className="bg-zinc-900 border border-zinc-800 rounded-xl h-full">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium text-zinc-300 flex items-center gap-2">
          <Activity className="w-4 h-4 text-sky-400" />
          Technical Analysis
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2.5">
        {[
          { label: 'ATR', value: technical.atr != null ? Number(technical.atr).toFixed(4) : '—' },
          { label: 'Volatility %', value: technical.volatility_pct != null ? `${Number(technical.volatility_pct).toFixed(2)}%` : '—' },
          { label: 'Active S/D Zones', value: technical.sd_zones ?? '—' },
          { label: 'BOS Events', value: technical.bos_count ?? '—' },
          { label: 'CHoCH Events', value: technical.choch_count ?? '—' },
          { label: 'Swing Highs/Lows', value: technical.swing_count != null ? String(technical.swing_count) : '—' },
        ].map(({ label, value }) => (
          <div key={label} className="flex items-center justify-between py-1 border-b border-zinc-800/50 last:border-0">
            <span className="text-xs text-zinc-500">{label}</span>
            <span className="text-xs font-mono text-zinc-200">{String(value)}</span>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

function FundamentalCard({ fundamental }: { fundamental: Record<string, unknown> }) {
  const events = (fundamental.upcoming_events as Array<Record<string, unknown>> | undefined) ?? []
  const sentiment = fundamental.sentiment as string | undefined

  return (
    <Card className="bg-zinc-900 border border-zinc-800 rounded-xl h-full">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium text-zinc-300 flex items-center gap-2">
          <Globe className="w-4 h-4 text-amber-400" />
          Fundamental Analysis
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {sentiment && (
          <div className="flex items-center justify-between py-1">
            <span className="text-xs text-zinc-500">Sentiment</span>
            <span className="text-xs text-zinc-200">{sentiment}</span>
          </div>
        )}
        <div>
          <p className="text-xs text-zinc-500 mb-2">Upcoming Events</p>
          {events.length === 0 && (
            <p className="text-xs text-zinc-600 italic">No upcoming events</p>
          )}
          <div className="space-y-1.5 max-h-48 overflow-y-auto">
            {events.slice(0, 8).map((ev, i) => {
              const evTime = ev.time as number | undefined
              const impact = (ev.impact as string | undefined) ?? 'low'
              return (
                <div key={i} className="flex items-start gap-2 bg-zinc-800/50 rounded-lg px-2.5 py-2">
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-zinc-200 truncate">{ev.name as string ?? 'Unknown'}</p>
                    <div className="flex items-center gap-2 mt-0.5">
                      {evTime && (
                        <span className="text-[10px] text-zinc-500">
                          {formatUnixTime(evTime)}
                        </span>
                      )}
                      {Boolean(ev.currency) && (
                        <span className="text-[10px] text-zinc-600">{ev.currency as string}</span>
                      )}
                    </div>
                  </div>
                  <span className={cn('inline-flex px-1.5 py-0.5 rounded text-[10px] font-medium border flex-shrink-0', impactBadge(impact))}>
                    {impact.toUpperCase()}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function SessionCard({ intel }: { intel: MarketIntel }) {
  const technical = intel.technical ?? {}
  const sessionWeight = technical.session_weight as number | undefined
  const nextSession = technical.next_session as string | undefined
  const nextSessionIn = technical.next_session_in_seconds as number | undefined

  return (
    <Card className="bg-zinc-900 border border-zinc-800 rounded-xl h-full">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium text-zinc-300 flex items-center gap-2">
          <Clock className="w-4 h-4 text-purple-400" />
          Session Analysis
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-col items-center py-4">
          <div className="w-16 h-16 rounded-full bg-purple-500/10 border-2 border-purple-500/30 flex items-center justify-center mb-3">
            <Globe className="w-6 h-6 text-purple-400" />
          </div>
          <p className="text-lg font-bold text-zinc-100">{intel.session || '—'}</p>
          <p className="text-xs text-zinc-500 mt-0.5">Current Session</p>
        </div>

        {sessionWeight != null && (
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-zinc-500">Session Weight</span>
              <span className="text-xs font-mono text-zinc-200">{sessionWeight.toFixed(2)}x</span>
            </div>
            <ProgressBar
              value={Math.min(100, sessionWeight * 50)}
              max={100}
              color="emerald"
              size="sm"
            />
          </div>
        )}

        {nextSession && (
          <div className="pt-2 border-t border-zinc-800">
            <p className="text-xs text-zinc-500 mb-1">Next Session</p>
            <div className="flex items-center justify-between">
              <span className="text-sm text-zinc-200">{nextSession}</span>
              {nextSessionIn != null && (
                <span className="text-xs text-zinc-500 font-mono">
                  in {formatUptime(nextSessionIn)}
                </span>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ─── Risk Alerts ──────────────────────────────────────────────────────────────

function RiskAlerts({ intel }: { intel: MarketIntel }) {
  const rs = intel.risk_score
  if (rs <= 0.7) return null

  return (
    <div className="space-y-3">
      {rs > 0.75 && (
        <div className="flex items-center gap-3 bg-amber-500/10 border border-amber-500/30 rounded-xl px-4 py-3">
          <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0" />
          <div>
            <p className="text-sm font-semibold text-amber-400">Trading HALTED by Agent 2</p>
            <p className="text-xs text-zinc-400 mt-0.5">
              Risk score {rs.toFixed(2)} exceeds halt threshold (0.75). New trade entries are blocked until risk normalises.
            </p>
          </div>
        </div>
      )}
      {rs > 0.7 && rs <= 0.75 && (
        <div className="flex items-center gap-3 bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3">
          <Shield className="w-5 h-5 text-red-400 flex-shrink-0" />
          <p className="text-sm text-red-400 font-medium">
            Risk warning: score {rs.toFixed(2)} — approaching halt threshold
          </p>
        </div>
      )}
    </div>
  )
}

// ─── Intelligence Tab ─────────────────────────────────────────────────────────

function IntelligenceTab({ agent }: { agent: AgentState | undefined }) {
  const [techExpanded, setTechExpanded] = useState(false)

  const { data: intel, isLoading } = useQuery({
    queryKey: ['intel', 'latest'],
    queryFn: () => apiClient.getLatestIntel(),
    refetchInterval: 60_000,
  })

  if (isLoading || !agent) {
    return (
      <div className="flex items-center justify-center py-16">
        <Spinner />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Status + control row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-1">
          <AgentControlBar
            agentId="agent2"
            status={agent.status}
            onCommand={async (cmd) => { await apiClient.controlAgent('agent2', cmd) }}
          />
        </div>
        <Card className="lg:col-span-2 bg-zinc-900 border border-zinc-800 rounded-xl">
          <CardContent className="p-4 space-y-1">
            <p className="text-xs text-zinc-500 uppercase tracking-wider">Current Task</p>
            <p className="text-sm font-medium text-zinc-200">
              {agent.current_task || 'Idle'}
            </p>
            <div className="grid grid-cols-3 gap-3 pt-2">
              <div>
                <p className="text-[10px] text-zinc-600">Uptime</p>
                <p className="text-xs font-mono text-zinc-300 mt-0.5">{formatUptime(agent.uptime_seconds)}</p>
              </div>
              <div>
                <p className="text-[10px] text-zinc-600">Cycles</p>
                <p className="text-xs font-mono text-zinc-300 mt-0.5">
                  {(agent.metrics.cycle_count as number | undefined)?.toLocaleString() ?? '—'}
                </p>
              </div>
              <div>
                <p className="text-[10px] text-zinc-600">Errors</p>
                <p className={cn(
                  'text-xs font-mono mt-0.5',
                  (agent.metrics.error_count as number | undefined ?? 0) > 0 ? 'text-red-400' : 'text-zinc-300'
                )}>
                  {(agent.metrics.error_count as number | undefined) ?? 0}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Risk alerts */}
      {intel && <RiskAlerts intel={intel} />}

      {/* Regime hero */}
      {intel && <RegimeHeroCard intel={intel} />}

      {/* Analysis row */}
      {intel && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <TechnicalCard technical={intel.technical ?? {}} />
          <FundamentalCard fundamental={intel.fundamental ?? {}} />
          <SessionCard intel={intel} />
        </div>
      )}

      {/* Raw data (collapsible) */}
      {intel && (
        <Card className="bg-zinc-900 border border-zinc-800 rounded-xl">
          <button
            className="w-full flex items-center justify-between px-4 py-3"
            onClick={() => setTechExpanded((v) => !v)}
          >
            <span className="text-sm font-medium text-zinc-400 flex items-center gap-2">
              <Layers className="w-4 h-4" />
              Raw Technical & Fundamental Data
            </span>
            {techExpanded ? (
              <ChevronUp className="w-4 h-4 text-zinc-500" />
            ) : (
              <ChevronDown className="w-4 h-4 text-zinc-500" />
            )}
          </button>
          {techExpanded && (
            <CardContent className="pt-0 space-y-4">
              <div>
                <p className="text-xs text-zinc-500 uppercase tracking-wider mb-2">Technical</p>
                <JsonViewer data={intel.technical} />
              </div>
              <div>
                <p className="text-xs text-zinc-500 uppercase tracking-wider mb-2">Fundamental</p>
                <JsonViewer data={intel.fundamental} />
              </div>
            </CardContent>
          )}
        </Card>
      )}

      {!intel && !isLoading && (
        <Card className="bg-zinc-900 border border-zinc-800 rounded-xl">
          <CardContent className="py-12 flex flex-col items-center justify-center text-zinc-600">
            <Activity className="w-10 h-10 mb-3 opacity-30" />
            <p>No intelligence data available yet</p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// ─── History Tab ──────────────────────────────────────────────────────────────

const ALL_REGIMES = ['ALL', 'TRENDING_BULLISH', 'TRENDING_BEARISH', 'RANGING', 'HIGH_VOLATILITY', 'UNCERTAIN'] as const
type RegimeFilter = typeof ALL_REGIMES[number]

function HistoryTab() {
  const [regimeFilter, setRegimeFilter] = useState<RegimeFilter>('ALL')

  const { data: history, isLoading } = useQuery({
    queryKey: ['intel', 'history'],
    queryFn: () => apiClient.getIntelHistory(20),
    refetchInterval: 60_000,
    staleTime: 30_000,
  })

  const filtered = useMemo(() => {
    if (!history) return []
    if (regimeFilter === 'ALL') return history
    return history.filter((h) => h.regime === regimeFilter)
  }, [history, regimeFilter])

  // Risk score over time for LineChart
  const riskOverTime = useMemo(() => {
    if (!history) return []
    return [...history]
      .sort((a, b) => a.timestamp - b.timestamp)
      .map((h) => ({
        time: new Date(h.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        risk: h.risk_score,
      }))
  }, [history])

  // Regime counts for BarChart
  const regimeCounts = useMemo(() => {
    if (!history) return []
    const counts: Record<string, number> = {}
    history.forEach((h) => {
      counts[h.regime] = (counts[h.regime] ?? 0) + 1
    })
    return Object.entries(counts).map(([regime, count]) => ({
      regime: regime.replace(/_/g, ' ').replace(/TRENDING /, ''),
      count,
    }))
  }, [history])

  return (
    <div className="space-y-6">
      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="bg-zinc-900 border border-zinc-800 rounded-xl">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-zinc-400">Risk Score — Last 24h</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="flex items-center justify-center h-40"><Spinner /></div>
            ) : (
              <LineChart
                data={riskOverTime}
                xKey="time"
                yKey="risk"
                height={160}
                color="#f59e0b"
                yDomain={[0, 1]}
              />
            )}
          </CardContent>
        </Card>

        <Card className="bg-zinc-900 border border-zinc-800 rounded-xl">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-zinc-400">Regime Distribution</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="flex items-center justify-center h-40"><Spinner /></div>
            ) : (
              <BarChart
                data={regimeCounts}
                xKey="regime"
                yKey="count"
                height={160}
                color="#38bdf8"
              />
            )}
          </CardContent>
        </Card>
      </div>

      {/* Filter */}
      <div className="flex items-center gap-2 flex-wrap">
        <Filter className="w-3.5 h-3.5 text-zinc-500" />
        {ALL_REGIMES.map((r) => (
          <button
            key={r}
            onClick={() => setRegimeFilter(r)}
            className={cn(
              'px-2.5 py-1 rounded-full text-xs font-medium border transition-colors',
              regimeFilter === r
                ? 'bg-sky-500/20 text-sky-400 border-sky-500/30'
                : 'text-zinc-500 border-zinc-700 hover:text-zinc-300 hover:border-zinc-600'
            )}
          >
            {r === 'ALL' ? 'All' : r.replace(/_/g, ' ')}
          </button>
        ))}
      </div>

      {/* Timeline table */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-zinc-800">
              <th className="text-left py-2 px-3 text-zinc-500 font-medium">Timestamp</th>
              <th className="text-left py-2 px-3 text-zinc-500 font-medium">Regime</th>
              <th className="text-left py-2 px-3 text-zinc-500 font-medium w-32">Risk Score</th>
              <th className="text-left py-2 px-3 text-zinc-500 font-medium">Session</th>
              <th className="text-right py-2 px-3 text-zinc-500 font-medium">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={5} className="py-8 text-center">
                  <Spinner size="sm" className="mx-auto" />
                </td>
              </tr>
            )}
            {!isLoading && filtered.length === 0 && (
              <tr>
                <td colSpan={5} className="py-8 text-center text-zinc-600">No history data</td>
              </tr>
            )}
            {filtered.map((h, i) => {
              const rc = regimeClasses(h.regime)
              return (
                <tr key={i} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                  <td className="py-2 px-3 font-mono text-zinc-400">
                    {formatUnixTimestamp(h.timestamp)}
                  </td>
                  <td className="py-2 px-3">
                    <span className={cn('inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium border', rc.bg, rc.text, rc.border)}>
                      {h.regime.replace(/_/g, ' ')}
                    </span>
                  </td>
                  <td className="py-2 px-3">
                    <div className="flex items-center gap-2">
                      <div className="flex-1">
                        <ProgressBar value={h.risk_score * 100} max={100} color={riskColor(h.risk_score)} size="sm" />
                      </div>
                      <span className={cn('font-mono text-[10px] w-8 text-right', riskTextClass(h.risk_score))}>
                        {h.risk_score.toFixed(2)}
                      </span>
                    </div>
                  </td>
                  <td className="py-2 px-3 text-zinc-400">{h.session}</td>
                  <td className="py-2 px-3 text-right font-mono text-zinc-300">
                    {(h.confidence * 100).toFixed(1)}%
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ─── Config Tab ───────────────────────────────────────────────────────────────

interface Agent2ConfigParam {
  key: string
  label: string
  description: string
  type: 'toggle' | 'slider' | 'number' | 'multiselect'
  min?: number
  max?: number
  step?: number
  options?: string[]
}

const AGENT2_CONFIG_PARAMS: Agent2ConfigParam[] = [
  { key: 'agents.agent2.update_interval_seconds', label: 'Analysis Cycle Interval (seconds)', description: 'How often Agent 2 refreshes market intelligence.', type: 'slider', min: 30, max: 300, step: 10 },
  { key: 'agents.agent2.enable_economic_calendar', label: 'Enable Economic Calendar', description: 'Monitor economic calendar events and add to risk assessment.', type: 'toggle' },
  { key: 'agents.agent2.risk_halt_threshold', label: 'Risk Score Halt Threshold', description: 'Risk score above which Agent 2 halts new trade entries (0.5–1.0).', type: 'slider', min: 0.5, max: 1.0, step: 0.01 },
  { key: 'agents.agent2.high_impact_event_risk', label: 'High-Impact Event Risk Addition', description: 'Risk score added when a high-impact economic event is imminent.', type: 'slider', min: 0.1, max: 0.5, step: 0.01 },
  { key: 'agents.agent2.analysis_timeframes', label: 'Analysis Timeframes', description: 'Timeframes used in technical analysis (multi-select).', type: 'multiselect', options: ['1M', '5M', '15M', '1H', '4H'] },
  { key: 'agents.agent2.regime_detection_sensitivity', label: 'Regime Detection Sensitivity', description: 'Sensitivity multiplier for regime change detection (higher = more reactive).', type: 'slider', min: 0.1, max: 2.0, step: 0.1 },
  { key: 'agents.agent2.liquidity_threshold_pct', label: 'Liquidity Threshold %', description: 'Minimum spread/liquidity threshold as a percent.', type: 'slider', min: 0.01, max: 1.0, step: 0.01 },
  { key: 'agents.agent2.volatility_multiplier', label: 'Volatility Multiplier (HIGH_VOLATILITY)', description: 'ATR multiplier threshold for classifying market as HIGH_VOLATILITY.', type: 'slider', min: 1.0, max: 5.0, step: 0.1 },
  { key: 'agents.agent2.session_weight_london', label: 'Session Weight — London', description: 'Quality multiplier for trades during the London session.', type: 'slider', min: 0.1, max: 2.0, step: 0.1 },
  { key: 'agents.agent2.session_weight_ny', label: 'Session Weight — New York', description: 'Quality multiplier for trades during the NY session.', type: 'slider', min: 0.1, max: 2.0, step: 0.1 },
  { key: 'agents.agent2.session_weight_overlap', label: 'Session Weight — Overlap', description: 'Quality multiplier for trades during the London/NY overlap.', type: 'slider', min: 0.1, max: 2.0, step: 0.1 },
  { key: 'agents.agent2.session_weight_asian', label: 'Session Weight — Asian', description: 'Quality multiplier for trades during the Asian session.', type: 'slider', min: 0.1, max: 2.0, step: 0.1 },
]

const TIMEFRAME_OPTIONS = ['1M', '5M', '15M', '1H', '4H']

function Agent2ConfigTab() {
  const queryClient = useQueryClient()
  const [values, setValues] = useState<Record<string, unknown>>({})
  const [savedKeys, setSavedKeys] = useState<Set<string>>(new Set())

  const { data: config, isLoading: configLoading } = useQuery({
    queryKey: ['config'],
    queryFn: () => apiClient.getConfig(),
    staleTime: 30_000,
  })

  useEffect(() => {
    if (!config) return
    const initial: Record<string, unknown> = {}
    AGENT2_CONFIG_PARAMS.forEach(({ key }) => {
      const parts = key.split('.')
      let cur: unknown = config
      for (const p of parts) {
        if (cur && typeof cur === 'object' && !Array.isArray(cur)) {
          cur = (cur as Record<string, unknown>)[p]
        } else {
          cur = undefined
          break
        }
      }
      if (cur !== undefined) initial[key] = cur
    })
    setValues(initial)
  }, [config])

  const saveMutation = useMutation({
    mutationFn: ({ path, value }: { path: string; value: unknown }) =>
      apiClient.updateConfigField(path, value),
    onSuccess: (_, { path }) => {
      setSavedKeys((prev) => new Set(prev).add(path))
      setTimeout(() => {
        setSavedKeys((prev) => {
          const next = new Set(prev)
          next.delete(path)
          return next
        })
      }, 2000)
      queryClient.invalidateQueries({ queryKey: ['config'] })
    },
  })

  function handleSave(key: string) {
    saveMutation.mutate({ path: key, value: values[key] })
  }

  function toggleTimeframe(tf: string) {
    const key = 'agents.agent2.analysis_timeframes'
    const current = (values[key] as string[] | undefined) ?? []
    const next = current.includes(tf)
      ? current.filter((t) => t !== tf)
      : [...current, tf]
    setValues((prev) => ({ ...prev, [key]: next }))
  }

  if (configLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Spinner />
      </div>
    )
  }

  return (
    <div className="space-y-3 max-w-2xl">
      {AGENT2_CONFIG_PARAMS.map((param) => {
        const val = values[param.key]
        const isSaved = savedKeys.has(param.key)

        return (
          <Card key={param.key} className="bg-zinc-900 border border-zinc-800 rounded-xl">
            <CardContent className="p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-sm font-medium text-zinc-200">{param.label}</span>
                    <Tooltip text={param.description}>
                      <Info className="w-3.5 h-3.5 text-zinc-600 cursor-help" />
                    </Tooltip>
                  </div>
                  <p className="text-xs text-zinc-500">{param.description}</p>

                  {param.type === 'toggle' && (
                    <div className="mt-3 flex items-center gap-3">
                      <button
                        onClick={() => setValues((prev) => ({ ...prev, [param.key]: !prev[param.key] }))}
                        className={cn(
                          'relative inline-flex h-6 w-11 items-center rounded-full transition-colors border',
                          val ? 'bg-emerald-500 border-emerald-500' : 'bg-zinc-700 border-zinc-600'
                        )}
                      >
                        <span className={cn('inline-block h-4 w-4 rounded-full bg-white transition-transform mx-1', val ? 'translate-x-5' : 'translate-x-0')} />
                      </button>
                      <span className="text-xs text-zinc-400">{val ? 'Enabled' : 'Disabled'}</span>
                    </div>
                  )}

                  {param.type === 'slider' && (
                    <div className="mt-3 space-y-2">
                      <div className="flex items-center gap-3">
                        <input
                          type="range"
                          min={param.min}
                          max={param.max}
                          step={param.step}
                          value={val as number ?? param.min}
                          onChange={(e) => setValues((prev) => ({ ...prev, [param.key]: Number(e.target.value) }))}
                          className="flex-1 h-1.5 bg-zinc-700 rounded-full appearance-none cursor-pointer accent-sky-500"
                        />
                        <input
                          type="number"
                          min={param.min}
                          max={param.max}
                          step={param.step}
                          value={val as number ?? param.min}
                          onChange={(e) => setValues((prev) => ({ ...prev, [param.key]: Number(e.target.value) }))}
                          className="w-20 bg-zinc-800 border border-zinc-700 rounded-lg px-2 py-1 text-xs text-zinc-200 text-right font-mono"
                        />
                      </div>
                      <div className="flex justify-between text-[10px] text-zinc-600">
                        <span>{param.min}</span>
                        <span>{param.max}</span>
                      </div>
                    </div>
                  )}

                  {param.type === 'multiselect' && (
                    <div className="mt-3 flex items-center gap-2 flex-wrap">
                      {TIMEFRAME_OPTIONS.map((tf) => {
                        const selected = ((val as string[] | undefined) ?? []).includes(tf)
                        return (
                          <button
                            key={tf}
                            onClick={() => toggleTimeframe(tf)}
                            className={cn(
                              'px-2.5 py-1 rounded-lg text-xs font-medium border transition-colors',
                              selected
                                ? 'bg-sky-500/20 text-sky-400 border-sky-500/30'
                                : 'bg-zinc-800 text-zinc-500 border-zinc-700 hover:text-zinc-300'
                            )}
                          >
                            {tf}
                          </button>
                        )
                      })}
                    </div>
                  )}
                </div>

                <Button
                  size="sm"
                  onClick={() => handleSave(param.key)}
                  disabled={saveMutation.isPending}
                  className={cn(
                    'h-8 text-xs flex-shrink-0 mt-0.5',
                    isSaved
                      ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                      : 'bg-zinc-800 text-zinc-300 border border-zinc-700 hover:bg-zinc-700'
                  )}
                >
                  {saveMutation.isPending && saveMutation.variables?.path === param.key ? (
                    <Spinner size="xs" />
                  ) : isSaved ? (
                    <>
                      <CheckCircle className="w-3 h-3 mr-1" />
                      Saved
                    </>
                  ) : (
                    <>
                      <Save className="w-3 h-3 mr-1" />
                      Save
                    </>
                  )}
                </Button>
              </div>
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}

// ─── Logs Tab ─────────────────────────────────────────────────────────────────

function LogsTab({ agentType }: { agentType: string }) {
  const [filterLevel, setFilterLevel] = useState<LogLevel | 'ALL'>('ALL')
  const [autoScroll, setAutoScroll] = useState(true)
  const [displayLogs, setDisplayLogs] = useState<LogEntry[]>([])
  const logEndRef = useRef<HTMLDivElement>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['logs', agentType],
    queryFn: () => apiClient.getLogs({ type: agentType, limit: 50 }),
    refetchInterval: 5_000,
  })

  useEffect(() => {
    if (data?.logs) {
      const filtered = filterLevel === 'ALL'
        ? data.logs
        : data.logs.filter((l) => l.level === filterLevel)
      setDisplayLogs(filtered)
    }
  }, [data, filterLevel])

  useEffect(() => {
    if (autoScroll && logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [displayLogs, autoScroll])

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-1.5">
          <Filter className="w-3.5 h-3.5 text-zinc-500" />
          <div className="flex items-center gap-1">
            {(['ALL', ...LOG_LEVELS] as Array<LogLevel | 'ALL'>).map((level) => (
              <button
                key={level}
                onClick={() => setFilterLevel(level)}
                className={cn(
                  'px-2.5 py-0.5 rounded-full text-xs font-medium transition-colors',
                  filterLevel === level
                    ? 'bg-sky-500/20 text-sky-400 border border-sky-500/30'
                    : 'text-zinc-500 hover:text-zinc-300 border border-transparent'
                )}
              >
                {level}
              </button>
            ))}
          </div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <label className="flex items-center gap-1.5 cursor-pointer">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
              className="w-3 h-3 accent-sky-500"
            />
            <span className="text-xs text-zinc-400">Auto-scroll</span>
          </label>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs text-zinc-500 hover:text-zinc-300"
            onClick={() => setDisplayLogs([])}
          >
            Clear
          </Button>
        </div>
      </div>

      <div className="bg-zinc-950 border border-zinc-800 rounded-xl overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-2 border-b border-zinc-800 bg-zinc-900">
          <Terminal className="w-3.5 h-3.5 text-zinc-500" />
          <span className="text-xs text-zinc-500 font-mono">agent2.log</span>
          {isLoading && <Spinner size="xs" className="ml-auto" />}
        </div>
        <div className="h-96 overflow-y-auto p-3 font-mono text-xs space-y-0.5">
          {displayLogs.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-zinc-600">
              <Terminal className="w-8 h-8 mb-2 opacity-30" />
              <p>{isLoading ? 'Loading logs…' : 'No log entries'}</p>
            </div>
          )}
          {displayLogs.map((log, i) => (
            <div key={log.id ?? i} className="flex items-start gap-2 py-0.5 hover:bg-zinc-900/50 rounded px-1">
              <span className="text-zinc-600 flex-shrink-0 w-[140px] truncate">{log.timestamp}</span>
              <span className={cn('flex-shrink-0 w-16', logLevelColor(log.level))}>{log.level}</span>
              <span className="text-zinc-300 break-all">{log.message}</span>
            </div>
          ))}
          <div ref={logEndRef} />
        </div>
      </div>
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

const TABS = [
  { id: 'intelligence', label: 'Live Intelligence' },
  { id: 'history', label: 'Intel History' },
  { id: 'config', label: 'Configuration' },
  { id: 'logs', label: 'Live Logs' },
]

export default function Agent2Page() {
  const [activeTab, setActiveTab] = useState('intelligence')

  const { data: agentData, isLoading } = useQuery({
    queryKey: ['agent', 'agent2'],
    queryFn: () => apiClient.getAgentStatus('agent2'),
    refetchInterval: 10_000,
  })

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-6">
        <PageHeader
          title="Agent 2 — Market Intelligence"
          subtitle="Regime detection, technical analysis, fundamental event monitoring and risk assessment"
          icon={<Activity className="w-5 h-5 text-amber-400" />}
        />

        <Tabs
          tabs={TABS}
          active={activeTab}
          onChange={setActiveTab}
        />

        <div>
          {activeTab === 'intelligence' && (
            <IntelligenceTab agent={agentData} />
          )}
          {activeTab === 'history' && (
            <HistoryTab />
          )}
          {activeTab === 'config' && (
            <Agent2ConfigTab />
          )}
          {activeTab === 'logs' && (
            <LogsTab agentType="agent2" />
          )}
        </div>
      </div>
    </div>
  )
}
