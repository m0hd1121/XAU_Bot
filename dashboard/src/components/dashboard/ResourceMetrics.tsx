'use client'

import { VPSStats } from '@/types'
import { cn } from '@/lib/utils'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card'
import { ProgressBar } from '@/components/ui/ProgressBar'
import { Server } from 'lucide-react'

interface ResourceMetricsProps {
  stats: VPSStats | null
  loading: boolean
}

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const parts: string[] = []
  if (d > 0) parts.push(`${d}d`)
  if (h > 0) parts.push(`${h}h`)
  parts.push(`${m}m`)
  return parts.join(' ')
}

function getProgressColor(pct: number): 'emerald' | 'amber' | 'red' {
  if (pct > 80) return 'red'
  if (pct > 60) return 'amber'
  return 'emerald'
}

function ShimmerBar() {
  return (
    <div className="space-y-2">
      <div className="flex justify-between">
        <div className="shimmer h-3 w-16 rounded" />
        <div className="shimmer h-3 w-10 rounded" />
      </div>
      <div className="shimmer h-2 w-full rounded-full" />
    </div>
  )
}

export function ResourceMetrics({ stats, loading }: ResourceMetricsProps) {
  if (loading) {
    return (
      <Card className="bg-zinc-900 border border-zinc-800 rounded-xl h-full">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium text-zinc-400 flex items-center gap-2">
            <Server className="w-4 h-4" />
            VPS Resources
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <ShimmerBar />
          <ShimmerBar />
          <ShimmerBar />
          <div className="shimmer h-4 w-32 rounded mt-2" />
        </CardContent>
      </Card>
    )
  }

  if (!stats) {
    return (
      <Card className="bg-zinc-900 border border-zinc-800 rounded-xl h-full">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium text-zinc-400 flex items-center gap-2">
            <Server className="w-4 h-4" />
            VPS Resources
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center justify-center py-8 text-zinc-600">
            <Server className="w-8 h-8 mb-2" />
            <p className="text-sm">Resource data unavailable</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  const metrics = [
    { label: 'CPU', value: stats.cpu_pct },
    { label: 'Memory', value: stats.memory_pct },
    { label: 'Disk', value: stats.disk_pct },
  ]

  return (
    <Card className="bg-zinc-900 border border-zinc-800 rounded-xl h-full">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium text-zinc-400 flex items-center gap-2">
          <Server className="w-4 h-4" />
          VPS Resources
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {metrics.map(({ label, value }) => {
          const color = getProgressColor(value)
          const textColor =
            color === 'red'
              ? 'text-red-400'
              : color === 'amber'
              ? 'text-amber-400'
              : 'text-emerald-400'

          return (
            <div key={label} className="space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-zinc-400 text-xs font-medium">{label}</span>
                <span className={cn('text-xs font-mono font-semibold', textColor)}>
                  {value.toFixed(1)}%
                </span>
              </div>
              <ProgressBar
                value={value}
                max={100}
                color={color}
                size="sm"
              />
            </div>
          )
        })}

        {/* Uptime */}
        <div className="pt-2 border-t border-zinc-800">
          <div className="flex items-center justify-between">
            <span className="text-zinc-500 text-xs">Uptime</span>
            <span className="text-zinc-300 text-xs font-mono">
              {formatUptime(stats.uptime_seconds)}
            </span>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
