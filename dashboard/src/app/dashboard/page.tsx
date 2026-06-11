'use client'

import { useState } from 'react'
import PageHeader from '@/components/ui/PageHeader'
import MetricTile from '@/components/ui/MetricTile'
import Card, { CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import StatusDot from '@/components/ui/StatusDot'
import Badge from '@/components/ui/Badge'
import Button from '@/components/ui/Button'
import { useDashboard, useEquityCurve, useBotControl } from '@/hooks/useApi'
import { useWebSocket } from '@/hooks/useWebSocket'
import { formatCurrency, formatDuration, pnlColor } from '@/lib/utils'
import AreaChartComponent from '@/components/charts/AreaChart'
import { ApiError } from '@/lib/api'
import { Play, Square, RotateCcw, AlertTriangle, Pause, PlayCircle } from 'lucide-react'

export default function DashboardPage() {
  const { data: snapshot, isLoading, refetch: refetchDashboard } = useDashboard()
  const { dashboard: liveDashboard, state: wsState } = useWebSocket()
  const { data: equityCurve } = useEquityCurve()
  const botControl = useBotControl()
  const [botError, setBotError] = useState<string | null>(null)

  // Prefer live WS data over polled data
  const data = liveDashboard ?? snapshot

  const account = data?.account_info
  const botStatus = data?.bot_status
  const openTrades = data?.open_trades ?? []

  const wsConnected = wsState === 'connected'
  const loading = isLoading && !data

  async function handleBot(command: 'start' | 'stop' | 'restart' | 'pause' | 'resume' | 'emergency-stop') {
    setBotError(null)
    try {
      await botControl.mutateAsync(command)
      void refetchDashboard()
    } catch (err) {
      if (err instanceof ApiError) {
        setBotError(err.message)
      } else if (err instanceof Error) {
        setBotError(err.message)
      } else {
        setBotError('Command failed')
      }
    }
  }

  return (
    <div className="p-6 space-y-6">
      <PageHeader
        title="Dashboard"
        subtitle="Real-time trading overview"
        badge={{
          text: wsConnected ? 'Live' : wsState === 'reconnecting' ? 'Reconnecting' : 'Polling',
          variant: wsConnected ? 'success' : wsState === 'reconnecting' ? 'warning' : 'default',
        }}
        actions={
          botStatus ? (
            <div className="flex items-center gap-2">
              <StatusDot
                status={
                  botStatus.emergency_stopped
                    ? 'error'
                    : botStatus.running
                    ? 'running'
                    : 'stopped'
                }
                label={
                  botStatus.emergency_stopped
                    ? 'Emergency Stop'
                    : botStatus.running
                    ? `Running — ${botStatus.mode}`
                    : 'Stopped'
                }
              />
            </div>
          ) : undefined
        }
      />

      {/* Account metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricTile
          label="Balance"
          value={account ? formatCurrency(account.balance) : '—'}
          loading={loading}
          size="md"
        />
        <MetricTile
          label="Equity"
          value={account ? formatCurrency(account.equity) : '—'}
          loading={loading}
          size="md"
        />
        <MetricTile
          label="Daily P&L"
          value={account ? formatCurrency(account.daily_pnl) : '—'}
          change={account?.daily_pnl}
          colorize
          loading={loading}
          size="md"
        />
        <MetricTile
          label="Floating P&L"
          value={account ? formatCurrency(account.floating_pnl) : '—'}
          colorize
          change={account?.floating_pnl}
          loading={loading}
          size="md"
        />
      </div>

      {/* Secondary metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricTile
          label="Weekly P&L"
          value={account ? formatCurrency(account.weekly_pnl) : '—'}
          change={account?.weekly_pnl}
          colorize
          loading={loading}
          size="sm"
        />
        <MetricTile
          label="Monthly P&L"
          value={account ? formatCurrency(account.monthly_pnl) : '—'}
          change={account?.monthly_pnl}
          colorize
          loading={loading}
          size="sm"
        />
        <MetricTile
          label="Open Positions"
          value={String(account?.open_positions ?? openTrades.length)}
          loading={loading}
          size="sm"
        />
        <MetricTile
          label="Uptime"
          value={botStatus ? formatDuration(botStatus.uptime_seconds) : '—'}
          loading={loading}
          size="sm"
        />
      </div>

      {/* Equity curve */}
      {equityCurve && equityCurve.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Equity Curve</CardTitle>
          </CardHeader>
          <CardContent>
            <AreaChartComponent
              data={equityCurve}
              xKey="timestamp"
              yKey="equity"
              height={220}
              formatY={(v) => formatCurrency(Number(v))}
              gradientFill
            />
          </CardContent>
        </Card>
      )}

      {/* Open trades */}
      <Card>
        <CardHeader>
          <CardTitle>
            Open Trades
            {openTrades.length > 0 && (
              <Badge variant="info" size="sm" className="ml-2">
                {openTrades.length}
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-10 shimmer rounded-lg" />
              ))}
            </div>
          ) : openTrades.length === 0 ? (
            <p className="text-zinc-500 text-sm py-4 text-center">No open positions</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-800">
                    {['Symbol', 'Direction', 'Lots', 'Entry', 'P&L'].map((h) => (
                      <th
                        key={h}
                        className="text-left text-xs text-zinc-500 font-medium pb-2 pr-4"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/50">
                  {openTrades.map((trade) => {
                    const pnl = trade.pnl ?? 0
                    const isBuy =
                      trade.direction === 'long' || trade.direction === 'BUY'
                    return (
                      <tr
                        key={trade.id}
                        className="hover:bg-zinc-800/30 transition-colors"
                      >
                        <td className="py-2 pr-4 font-mono text-zinc-200">
                          {trade.symbol}
                        </td>
                        <td className="py-2 pr-4">
                          <Badge
                            variant={isBuy ? 'success' : 'danger'}
                            size="sm"
                          >
                            {isBuy ? 'BUY' : 'SELL'}
                          </Badge>
                        </td>
                        <td className="py-2 pr-4 text-right font-mono text-zinc-300">
                          {trade.lots.toFixed(2)}
                        </td>
                        <td className="py-2 pr-4 text-right font-mono text-zinc-300">
                          {trade.entry_price.toFixed(2)}
                        </td>
                        <td
                          className={`py-2 text-right font-mono font-medium ${pnlColor(pnl)}`}
                        >
                          {formatCurrency(pnl)}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Bot control */}
      <Card>
        <CardHeader>
          <CardTitle>Bot Control</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-center gap-3">
            {botStatus?.running ? (
              <>
                <Button
                  variant="destructive"
                  size="sm"
                  iconLeft={<Square size={13} />}
                  loading={botControl.isPending}
                  onClick={() => void handleBot('stop')}
                >
                  Stop
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  iconLeft={<RotateCcw size={13} />}
                  loading={botControl.isPending}
                  onClick={() => void handleBot('restart')}
                >
                  Restart
                </Button>
                {botStatus.paused ? (
                  <Button
                    variant="outline"
                    size="sm"
                    iconLeft={<PlayCircle size={13} />}
                    loading={botControl.isPending}
                    onClick={() => void handleBot('resume')}
                  >
                    Resume
                  </Button>
                ) : (
                  <Button
                    variant="outline"
                    size="sm"
                    iconLeft={<Pause size={13} />}
                    loading={botControl.isPending}
                    onClick={() => void handleBot('pause')}
                  >
                    Pause
                  </Button>
                )}
              </>
            ) : (
              <Button
                variant="primary"
                size="sm"
                iconLeft={<Play size={13} />}
                loading={botControl.isPending}
                onClick={() => void handleBot('start')}
              >
                Start Bot
              </Button>
            )}

            {botStatus?.emergency_stopped && (
              <span className="flex items-center gap-1.5 text-xs text-red-400">
                <AlertTriangle size={13} />
                Emergency stopped — clear via admin
              </span>
            )}

            {botError && (
              <span className="flex items-center gap-1.5 text-xs text-red-400 max-w-xs">
                <AlertTriangle size={13} className="flex-shrink-0" />
                <span className="truncate">{botError}</span>
              </span>
            )}
          </div>

          {/* Bot info row */}
          {botStatus && (
            <div className="mt-4 pt-4 border-t border-zinc-800 grid grid-cols-2 md:grid-cols-4 gap-3">
              <MetricTile label="Mode" value={String(botStatus.mode).toUpperCase()} size="sm" />
              <MetricTile label="Uptime" value={formatDuration(botStatus.uptime_seconds)} size="sm" />
              <MetricTile
                label="Status"
                value={
                  botStatus.emergency_stopped
                    ? 'EMERGENCY STOP'
                    : botStatus.paused
                    ? 'PAUSED'
                    : botStatus.running
                    ? 'RUNNING'
                    : 'STOPPED'
                }
                size="sm"
                valueClassName={
                  botStatus.emergency_stopped
                    ? 'text-red-400'
                    : botStatus.paused
                    ? 'text-amber-400'
                    : botStatus.running
                    ? 'text-emerald-400'
                    : 'text-zinc-500'
                }
              />
              <MetricTile
                label="Learning"
                value={botStatus.learning_enabled ? 'Enabled' : 'Disabled'}
                size="sm"
              />
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
