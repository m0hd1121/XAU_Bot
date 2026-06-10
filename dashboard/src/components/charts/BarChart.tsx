'use client'

import {
  BarChart as RechartsBarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
  ResponsiveContainer,
  type TooltipProps,
} from 'recharts'
import { cn } from '@/lib/utils'

interface BarChartProps {
  data: object[]
  xKey: string
  yKey: string
  color?: string
  colorByValue?: boolean   // green if positive, red if negative
  height?: number
  showGrid?: boolean
  formatX?: (v: unknown) => string
  formatY?: (v: unknown) => string
  className?: string
  radius?: number
}

function CustomTooltip({
  active,
  payload,
  label,
  formatY,
}: TooltipProps<number, string> & { formatY?: (v: unknown) => string }) {
  if (!active || !payload?.length) return null
  const value = payload[0]?.value
  return (
    <div className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 shadow-xl text-sm">
      <p className="text-zinc-400 mb-1">{label}</p>
      <p className="font-mono font-medium text-amber-400">
        {formatY ? formatY(value) : String(value)}
      </p>
    </div>
  )
}

export function BarChart({
  data,
  xKey,
  yKey,
  color = '#f59e0b',
  colorByValue = false,
  height = 200,
  showGrid = true,
  formatX,
  formatY,
  className,
  radius = 4,
}: BarChartProps) {
  return (
    <div className={cn('w-full', className)} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <RechartsBarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
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
            interval={0}
          />

          <YAxis
            tickFormatter={formatY}
            tick={{ fill: '#71717a', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={60}
          />

          <Tooltip
            content={<CustomTooltip formatY={formatY} />}
            cursor={{ fill: '#3f3f46', fillOpacity: 0.4 }}
          />

          <Bar dataKey={yKey} radius={[radius, radius, 0, 0]}>
            {data.map((entry, index) => {
              const val = (entry as Record<string, unknown>)[yKey]
              const barColor = colorByValue
                ? typeof val === 'number' && val >= 0
                  ? '#10b981'
                  : '#ef4444'
                : color
              return <Cell key={`cell-${index}`} fill={barColor} />
            })}
          </Bar>
        </RechartsBarChart>
      </ResponsiveContainer>
    </div>
  )
}

export default BarChart
