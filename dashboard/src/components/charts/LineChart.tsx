'use client'

import {
  LineChart as RechartsLineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  type TooltipProps,
} from 'recharts'
import { cn } from '@/lib/utils'

export interface LineConfig {
  key: string
  color: string
  label: string
  dashed?: boolean
}

interface LineChartProps {
  data: Array<Record<string, unknown>>
  xKey: string
  lines: LineConfig[]
  height?: number
  showGrid?: boolean
  showLegend?: boolean
  formatX?: (v: unknown) => string
  formatY?: (v: unknown) => string
  className?: string
}

function CustomTooltip({
  active,
  payload,
  label,
  lines,
  formatY,
}: TooltipProps<number, string> & { lines: LineConfig[]; formatY?: (v: unknown) => string }) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 shadow-xl text-sm space-y-1">
      <p className="text-zinc-400 text-xs mb-2">{label}</p>
      {payload.map((entry) => {
        const lineConfig = lines.find((l) => l.key === entry.dataKey)
        return (
          <div key={entry.dataKey} className="flex items-center gap-2">
            <span
              className="inline-block w-2.5 h-2.5 rounded-full flex-shrink-0"
              style={{ background: entry.color }}
            />
            <span className="text-zinc-300">{lineConfig?.label ?? entry.dataKey}:</span>
            <span className="font-mono font-medium" style={{ color: entry.color }}>
              {formatY ? formatY(entry.value) : entry.value?.toFixed(3)}
            </span>
          </div>
        )
      })}
    </div>
  )
}

export function LineChart({
  data,
  xKey,
  lines,
  height = 200,
  showGrid = true,
  showLegend = false,
  formatX,
  formatY,
  className,
}: LineChartProps) {
  return (
    <div className={cn('w-full', className)} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <RechartsLineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          {showGrid && (
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="#3f3f46"
              vertical={false}
            />
          )}

          <XAxis
            dataKey={xKey}
            tickFormatter={formatX}
            tick={{ fill: '#71717a', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            interval="preserveStartEnd"
          />

          <YAxis
            tickFormatter={formatY}
            tick={{ fill: '#71717a', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={60}
          />

          <Tooltip
            content={<CustomTooltip lines={lines} formatY={formatY} />}
            cursor={{ stroke: '#52525b', strokeWidth: 1 }}
          />

          {showLegend && (
            <Legend
              wrapperStyle={{ fontSize: 12, color: '#a1a1aa', paddingTop: 8 }}
            />
          )}

          {lines.map((line) => (
            <Line
              key={line.key}
              type="monotone"
              dataKey={line.key}
              stroke={line.color}
              strokeWidth={2}
              strokeDasharray={line.dashed ? '4 4' : undefined}
              dot={false}
              activeDot={{ r: 4, stroke: '#18181b', strokeWidth: 2 }}
            />
          ))}
        </RechartsLineChart>
      </ResponsiveContainer>
    </div>
  )
}

export default LineChart
