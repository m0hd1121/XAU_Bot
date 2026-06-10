'use client'

import { useState, useCallback, useMemo } from 'react'
import { Bell, AlertTriangle, TrendingUp, Server, BotOff, Activity, Shield, RefreshCw } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import PageHeader from '@/components/ui/PageHeader'
import Button from '@/components/ui/Button'
import Badge from '@/components/ui/Badge'
import Card, { CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { NotificationsPanel, type Notification } from '@/components/notifications/NotificationsPanel'
import { apiClient } from '@/lib/api'
import { cn } from '@/lib/utils'

// ─── Preferences ─────────────────────────────────────────────────────────────

interface NotificationPrefs {
  tradeExecuted: boolean
  tradeRejected: boolean
  strategyPromoted: boolean
  strategyValidated: boolean
  agentDown: boolean
  highRiskScore: boolean
  vpsResourceWarning: boolean
  dailyPnLSummary: boolean
  killSwitchTriggered: boolean
  riskScoreThreshold: number
  cpuThreshold: number
  dailyLossThreshold: number
}

const DEFAULT_PREFS: NotificationPrefs = {
  tradeExecuted: true,
  tradeRejected: false,
  strategyPromoted: true,
  strategyValidated: true,
  agentDown: true,
  highRiskScore: true,
  vpsResourceWarning: true,
  dailyPnLSummary: false,
  killSwitchTriggered: true,
  riskScoreThreshold: 0.75,
  cpuThreshold: 85,
  dailyLossThreshold: 2.0,
}

function loadPrefs(): NotificationPrefs {
  try {
    const raw = localStorage.getItem('xau_notification_prefs')
    if (raw) return { ...DEFAULT_PREFS, ...JSON.parse(raw) }
  } catch { /* ignore */ }
  return DEFAULT_PREFS
}

function savePrefs(prefs: NotificationPrefs) {
  localStorage.setItem('xau_notification_prefs', JSON.stringify(prefs))
}

// ─── Notification generation from live data ───────────────────────────────────

function useNotifications() {
  const { data: decisions } = useQuery({
    queryKey: ['decisions', 50],
    queryFn: () => apiClient.getRecentDecisions(50),
    refetchInterval: 30_000,
  })
  const { data: agents } = useQuery({
    queryKey: ['agents'],
    queryFn: () => apiClient.getAllAgentStatus(),
    refetchInterval: 30_000,
  })
  const { data: strategies } = useQuery({
    queryKey: ['strategies', 'all'],
    queryFn: () => apiClient.getStrategyCandidates(undefined, 20),
    refetchInterval: 60_000,
  })
  const { data: vps } = useQuery({
    queryKey: ['vps', 'stats'],
    queryFn: () => apiClient.getVPSStats(),
    refetchInterval: 30_000,
  })

  return useMemo<Notification[]>(() => {
    const items: Notification[] = []

    // Trade decisions → notifications
    if (decisions) {
      decisions.slice(0, 20).forEach((d) => {
        if (d.decision === 'EXECUTE') {
          items.push({
            id: `trade-exec-${d.id}`,
            type: 'trade',
            severity: 'info',
            title: `Trade Executed: ${d.explanation?.direction ?? '?'}`,
            message: `${d.explanation?.direction ?? ''} @ ${d.explanation?.entry_price?.toFixed(2) ?? '?'} — Strategy ${(d.strategy_id ?? '').slice(0, 8)}`,
            timestamp: d.timestamp,
            read: false,
          })
        }
      })
    }

    // Agent down
    if (agents) {
      Object.values(agents).forEach((a) => {
        if (a.status === 'error' || a.status === 'stopped') {
          items.push({
            id: `agent-down-${a.agent_id}`,
            type: 'agent',
            severity: a.status === 'error' ? 'critical' : 'warning',
            title: `${a.agent_id.charAt(0).toUpperCase()}${a.agent_id.slice(1)} is ${a.status}`,
            message: `Agent last heartbeat: ${new Date(a.last_heartbeat * 1000).toLocaleString()}`,
            timestamp: Date.now() / 1000,
            read: false,
          })
        }
      })
    }

    // Strategy promoted
    if (strategies) {
      strategies.filter((s) => s.status === 'promoted').slice(0, 3).forEach((s) => {
        items.push({
          id: `strategy-promoted-${s.genome_hash}`,
          type: 'strategy',
          severity: 'info',
          title: 'Strategy Promoted to Live',
          message: `Hash ${s.genome_hash.slice(0, 8)} — Score ${s.fitness.composite_score?.toFixed(3) ?? '?'}, PF ${s.fitness.profit_factor?.toFixed(2) ?? '?'}`,
          timestamp: s.created_at,
          read: false,
        })
      })
    }

    // VPS resource warnings
    if (vps) {
      if (vps.cpu_pct > 85) {
        items.push({
          id: 'vps-cpu-warn',
          type: 'vps',
          severity: 'warning',
          title: 'High CPU Usage',
          message: `VPS CPU at ${vps.cpu_pct.toFixed(1)}% — consider reducing agent workload`,
          timestamp: Date.now() / 1000,
          read: false,
        })
      }
      if (vps.disk_pct > 90) {
        items.push({
          id: 'vps-disk-warn',
          type: 'vps',
          severity: 'critical',
          title: 'Disk Space Critical',
          message: `VPS disk at ${vps.disk_pct.toFixed(1)}% — clean up logs or reports`,
          timestamp: Date.now() / 1000,
          read: false,
        })
      }
    }

    // Sort newest first
    return items.sort((a, b) => b.timestamp - a.timestamp)
  }, [decisions, agents, strategies, vps])
}

// ─── Toggle row ───────────────────────────────────────────────────────────────

function ToggleRow({
  label,
  description,
  checked,
  onChange,
}: {
  label: string
  description?: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <div className="flex items-start justify-between gap-4 py-3 border-b border-zinc-800 last:border-0">
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-zinc-200">{label}</p>
        {description && <p className="text-xs text-zinc-500 mt-0.5">{description}</p>}
      </div>
      <button
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={cn(
          'relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200',
          checked ? 'bg-amber-500' : 'bg-zinc-700',
        )}
      >
        <span
          className={cn(
            'pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow transform ring-0 transition duration-200 ease-in-out',
            checked ? 'translate-x-5' : 'translate-x-0',
          )}
        />
      </button>
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

const FILTER_TYPES = [
  { id: 'all',       label: 'All' },
  { id: 'trade',     label: 'Trading' },
  { id: 'strategy',  label: 'Strategy' },
  { id: 'risk',      label: 'Risk' },
  { id: 'vps',       label: 'VPS' },
  { id: 'agent',     label: 'Agents' },
  { id: 'system',    label: 'System' },
] as const

export default function NotificationsPage() {
  const rawNotifications = useNotifications()
  const [readIds, setReadIds] = useState<Set<string>>(new Set())
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set())
  const [filterType, setFilterType] = useState<string>('all')
  const [prefs, setPrefs] = useState<NotificationPrefs>(loadPrefs)

  const notifications = useMemo(() => {
    return rawNotifications
      .filter((n) => !dismissedIds.has(n.id))
      .filter((n) => filterType === 'all' || n.type === filterType)
      .map((n) => ({ ...n, read: readIds.has(n.id) }))
  }, [rawNotifications, dismissedIds, filterType, readIds])

  const handleMarkRead = useCallback((id: string) => {
    setReadIds((prev) => new Set(Array.from(prev).concat(id)))
  }, [])

  const handleMarkAllRead = useCallback(() => {
    setReadIds(new Set(notifications.map((n) => n.id)))
  }, [notifications])

  const handleDismiss = useCallback((id: string) => {
    setDismissedIds((prev) => new Set(Array.from(prev).concat(id)))
  }, [])

  const updatePref = <K extends keyof NotificationPrefs>(key: K, value: NotificationPrefs[K]) => {
    setPrefs((prev) => {
      const next = { ...prev, [key]: value }
      savePrefs(next)
      return next
    })
  }

  const unreadCount = notifications.filter((n) => !n.read).length

  return (
    <div className="p-6 space-y-6">
      <PageHeader
        title="Notifications Center"
        subtitle="System alerts, trading events, and agent activity"
        badge={unreadCount > 0 ? { text: `${unreadCount} unread`, variant: 'warning' } : undefined}
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={handleMarkAllRead}
            iconLeft={<RefreshCw size={14} />}
          >
            Mark all read
          </Button>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* ── Notifications feed ────────────────────────────────── */}
        <div className="lg:col-span-3 space-y-4">
          {/* Filter bar */}
          <div className="flex flex-wrap gap-1">
            {FILTER_TYPES.map((t) => (
              <button
                key={t.id}
                onClick={() => setFilterType(t.id)}
                className={cn(
                  'px-3 py-1.5 rounded-lg text-sm font-medium transition-colors border',
                  filterType === t.id
                    ? 'bg-amber-500/20 text-amber-400 border-amber-500/30'
                    : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 border-transparent',
                )}
              >
                {t.label}
              </button>
            ))}
          </div>

          <NotificationsPanel
            notifications={notifications}
            onMarkRead={handleMarkRead}
            onMarkAllRead={handleMarkAllRead}
            onDismiss={handleDismiss}
            maxHeight="600px"
          />
        </div>

        {/* ── Preferences ──────────────────────────────────────── */}
        <div className="lg:col-span-2 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Bell size={16} className="text-amber-400" />
                Notification Settings
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-0">
              <p className="text-xs text-zinc-500 mb-3">
                Preferences are saved locally in your browser.
              </p>

              <ToggleRow
                label="Trade Executed"
                description="Notify when Agent 3 places a trade"
                checked={prefs.tradeExecuted}
                onChange={(v) => updatePref('tradeExecuted', v)}
              />
              <ToggleRow
                label="Trade Rejected (daily summary)"
                description="Batch summary of rejected setups"
                checked={prefs.tradeRejected}
                onChange={(v) => updatePref('tradeRejected', v)}
              />
              <ToggleRow
                label="Strategy Promoted"
                description="When a new strategy goes live"
                checked={prefs.strategyPromoted}
                onChange={(v) => updatePref('strategyPromoted', v)}
              />
              <ToggleRow
                label="Strategy Validated"
                description="When a strategy passes all validation stages"
                checked={prefs.strategyValidated}
                onChange={(v) => updatePref('strategyValidated', v)}
              />
              <ToggleRow
                label="Agent Down Alert"
                description="Immediate alert when any agent stops or errors"
                checked={prefs.agentDown}
                onChange={(v) => updatePref('agentDown', v)}
              />
              <ToggleRow
                label="High Risk Score Warning"
                description="Alert when Agent 2 risk score exceeds threshold"
                checked={prefs.highRiskScore}
                onChange={(v) => updatePref('highRiskScore', v)}
              />
              <ToggleRow
                label="VPS Resource Warning"
                description="CPU or disk usage exceeds threshold"
                checked={prefs.vpsResourceWarning}
                onChange={(v) => updatePref('vpsResourceWarning', v)}
              />
              <ToggleRow
                label="Kill Switch Triggered"
                description="When max drawdown kill switch activates"
                checked={prefs.killSwitchTriggered}
                onChange={(v) => updatePref('killSwitchTriggered', v)}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Shield size={16} className="text-amber-400" />
                Alert Thresholds
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <div className="flex justify-between mb-1">
                  <label className="text-sm text-zinc-300">Risk Score Threshold</label>
                  <span className="text-sm font-mono text-amber-400">{prefs.riskScoreThreshold.toFixed(2)}</span>
                </div>
                <input
                  type="range"
                  min={0.5} max={1.0} step={0.05}
                  value={prefs.riskScoreThreshold}
                  onChange={(e) => updatePref('riskScoreThreshold', Number(e.target.value))}
                  className="w-full accent-amber-500"
                />
                <p className="text-xs text-zinc-600 mt-1">Alert when Agent 2 risk score exceeds this value</p>
              </div>

              <div>
                <div className="flex justify-between mb-1">
                  <label className="text-sm text-zinc-300">CPU Usage Threshold</label>
                  <span className="text-sm font-mono text-amber-400">{prefs.cpuThreshold}%</span>
                </div>
                <input
                  type="range"
                  min={60} max={100} step={5}
                  value={prefs.cpuThreshold}
                  onChange={(e) => updatePref('cpuThreshold', Number(e.target.value))}
                  className="w-full accent-amber-500"
                />
              </div>

              <div>
                <div className="flex justify-between mb-1">
                  <label className="text-sm text-zinc-300">Daily Loss Alert</label>
                  <span className="text-sm font-mono text-amber-400">{prefs.dailyLossThreshold.toFixed(1)}%</span>
                </div>
                <input
                  type="range"
                  min={0.5} max={5.0} step={0.5}
                  value={prefs.dailyLossThreshold}
                  onChange={(e) => updatePref('dailyLossThreshold', Number(e.target.value))}
                  className="w-full accent-amber-500"
                />
                <p className="text-xs text-zinc-600 mt-1">Alert when daily loss exceeds this % of equity</p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
