'use client'

import { useState } from 'react'
import {
  Shield,
  User,
  Database,
  Download,
  Trash2,
  RefreshCw,
  Server,
  CheckCircle,
  AlertTriangle,
} from 'lucide-react'
import { useQuery, useMutation } from '@tanstack/react-query'
import PageHeader from '@/components/ui/PageHeader'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import Button from '@/components/ui/Button'
import Badge, { type BadgeVariant } from '@/components/ui/Badge'
import Spinner from '@/components/ui/Spinner'
import MetricTile from '@/components/ui/MetricTile'
import { apiClient } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { cn } from '@/lib/utils'

// ─── Types ────────────────────────────────────────────────────────────────────

interface BackupInfo {
  filename: string
  size_mb?: number
  created_at?: number
}

// ─── Health check row ─────────────────────────────────────────────────────────

function HealthRow({ label, endpoint }: { label: string; endpoint: string }) {
  const { isLoading, isError } = useQuery({
    queryKey: ['health-check', endpoint],
    queryFn: () => apiClient.get<unknown>(endpoint),
    retry: 1,
    staleTime: 30_000,
    refetchInterval: 60_000,
  })

  return (
    <div className="flex items-center justify-between py-2 border-b border-zinc-800 last:border-0">
      <span className="text-sm text-zinc-300">{label}</span>
      {isLoading ? (
        <Spinner size="xs" />
      ) : isError ? (
        <Badge variant="danger" size="sm">Unreachable</Badge>
      ) : (
        <Badge variant="success" size="sm">Online</Badge>
      )}
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function AdminPage() {
  const { user } = useAuth()
  const [backupMsg, setBackupMsg] = useState<string | null>(null)

  const { data: me, isLoading: meLoading } = useQuery({
    queryKey: ['me'],
    queryFn: () => apiClient.getMe(),
  })

  const {
    data: backupsData,
    isLoading: backupsLoading,
    refetch: refetchBackups,
  } = useQuery({
    queryKey: ['backups'],
    queryFn: () => apiClient.get<{ backups: BackupInfo[]; total: number }>('/api/v1/backups'),
  })

  const createMutation = useMutation({
    mutationFn: (includeLogs: boolean) =>
      apiClient.post<{ filename: string; size_mb: number }>('/api/v1/backups/create', {
        include_logs: includeLogs,
      }),
    onSuccess: (data) => {
      setBackupMsg(`Created: ${data.filename} (${data.size_mb?.toFixed(1)} MB)`)
      void refetchBackups()
      setTimeout(() => setBackupMsg(null), 5000)
    },
    onError: () => {
      setBackupMsg('Backup failed')
      setTimeout(() => setBackupMsg(null), 4000)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (name: string) => apiClient.del<void>(`/api/v1/backups/${name}`),
    onSuccess: () => void refetchBackups(),
  })

  const roleBadge: BadgeVariant =
    me?.role === 'admin' ? 'warning' : 'default'

  const backups = backupsData?.backups ?? []
  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? ''

  return (
    <div className="p-6 space-y-6">
      <PageHeader
        title="Administrative Controls"
        subtitle="User management, backup & restore, system health"
        icon={<Shield className="w-5 h-5 text-red-400" />}
        badge={me ? { text: me.role, variant: roleBadge } : undefined}
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* ── Current user ───────────────────────────────────── */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <User className="w-4 h-4 text-amber-400" />
              Current User
            </CardTitle>
          </CardHeader>
          <CardContent>
            {meLoading ? (
              <div className="flex justify-center py-6">
                <Spinner />
              </div>
            ) : me ? (
              <div className="space-y-4">
                {/* Avatar row */}
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-full bg-amber-500/20 border border-amber-500/30 flex items-center justify-center flex-shrink-0">
                    <span className="text-amber-400 text-lg font-bold uppercase">
                      {me.username.charAt(0)}
                    </span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-zinc-100 font-semibold">{me.username}</p>
                    <p className="text-zinc-500 text-sm truncate">{me.email}</p>
                  </div>
                  <Badge variant={roleBadge}>{me.role}</Badge>
                </div>

                {/* Details table */}
                <div className="pt-3 border-t border-zinc-800 space-y-0">
                  {[
                    { label: 'User ID',  value: String(me.id) },
                    { label: 'Username', value: me.username },
                    { label: 'Email',    value: me.email },
                    { label: 'Role',     value: me.role },
                  ].map(({ label, value }) => (
                    <div
                      key={label}
                      className="flex items-center justify-between py-1.5 border-b border-zinc-800 last:border-0"
                    >
                      <span className="text-xs text-zinc-500">{label}</span>
                      <span className="text-xs font-mono text-zinc-300">{value}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-zinc-500 text-sm text-center py-6">
                Not available
              </p>
            )}
          </CardContent>
        </Card>

        {/* ── API Health ─────────────────────────────────────── */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Server className="w-4 h-4 text-amber-400" />
              API Health
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-0">
              <HealthRow label="Backend API"       endpoint="/api/v1/health" />
              <HealthRow label="Auth Service"      endpoint="/api/v1/auth/me" />
              <HealthRow label="Dashboard Snapshot" endpoint="/api/v1/dashboard/snapshot" />
              <HealthRow label="Agents"            endpoint="/api/v1/agents/status" />
              <HealthRow label="VPS Stats"         endpoint="/api/v1/vps/stats" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ── Backups ──────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <CardTitle className="flex items-center gap-2 text-sm">
              <Database className="w-4 h-4 text-amber-400" />
              Backups
              {backupsLoading && <Spinner size="xs" />}
              {backups.length > 0 && (
                <span className="text-xs text-zinc-500">({backups.length} archives)</span>
              )}
            </CardTitle>
            <div className="flex items-center gap-2 flex-wrap">
              {backupMsg && (
                <span
                  className={cn(
                    'flex items-center gap-1 text-xs',
                    backupMsg.startsWith('Created') ? 'text-emerald-400' : 'text-red-400',
                  )}
                >
                  {backupMsg.startsWith('Created') ? (
                    <CheckCircle className="w-3 h-3" />
                  ) : (
                    <AlertTriangle className="w-3 h-3" />
                  )}
                  {backupMsg}
                </span>
              )}
              <Button
                variant="outline"
                size="sm"
                onClick={() => createMutation.mutate(false)}
                loading={createMutation.isPending}
                iconLeft={<Database size={13} />}
              >
                Create Backup
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => void refetchBackups()}
                iconLeft={<RefreshCw size={13} />}
              >
                Refresh
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {backupsLoading ? (
            <div className="flex justify-center py-6">
              <Spinner />
            </div>
          ) : backups.length > 0 ? (
            <div className="space-y-2">
              {backups.map((b) => (
                <div
                  key={b.filename}
                  className="flex items-center gap-3 p-3 rounded-lg bg-zinc-800/50 border border-zinc-800"
                >
                  <Database className="w-4 h-4 text-zinc-500 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-mono text-zinc-300 truncate">{b.filename}</p>
                    <p className="text-[10px] text-zinc-600 mt-0.5">
                      {b.size_mb != null ? `${b.size_mb.toFixed(1)} MB` : ''}
                      {b.created_at != null
                        ? `${b.size_mb != null ? ' · ' : ''}${new Date(b.created_at * 1000).toLocaleString()}`
                        : ''}
                    </p>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <a
                      href={`${apiBase}/api/v1/backups/download/${encodeURIComponent(b.filename)}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="p-1.5 rounded text-zinc-500 hover:text-zinc-200 hover:bg-zinc-700 transition-colors"
                      title="Download"
                    >
                      <Download className="w-3.5 h-3.5" />
                    </a>
                    <button
                      onClick={() => deleteMutation.mutate(b.filename)}
                      disabled={deleteMutation.isPending}
                      className="p-1.5 rounded text-zinc-600 hover:text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-50"
                      title="Delete"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 space-y-2">
              <Database className="w-8 h-8 text-zinc-700 mx-auto" />
              <p className="text-sm text-zinc-500">No backups found</p>
              <p className="text-xs text-zinc-600">
                Click &quot;Create Backup&quot; to snapshot the database and config
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Quick stats ──────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <MetricTile
          label="Total Backups"
          value={backupsLoading ? '…' : String(backups.length)}
          icon={<Database className="w-4 h-4" />}
          loading={backupsLoading}
        />
        <MetricTile
          label="Logged-in User"
          value={me?.username ?? '—'}
          loading={meLoading}
          icon={<User className="w-4 h-4" />}
        />
        <MetricTile
          label="Role"
          value={me?.role ?? '—'}
          loading={meLoading}
          icon={<Shield className="w-4 h-4" />}
          valueClassName={me?.role === 'admin' ? 'text-amber-400' : undefined}
        />
        <MetricTile
          label="Latest Backup"
          value={
            backups[0]?.created_at != null
              ? new Date(backups[0].created_at * 1000).toLocaleDateString()
              : '—'
          }
          loading={backupsLoading}
          icon={<CheckCircle className="w-4 h-4" />}
        />
      </div>
    </div>
  )
}
