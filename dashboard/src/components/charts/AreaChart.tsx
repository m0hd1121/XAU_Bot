'use client'

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  type TooltipProps,
} from 'recharts'
import { cn } from '@/lib/utils'

interface AreaChartProps {
  data: Array<Record<string, unknown>>
  xKey: string
  yKey: string
  color?: string
  gradientFill?: boolean
  showGrid?: boolean
  height?: number
  formatX?: (v: unknown) => string
  formatY?: (v: unknown) => string
  label?: string
  className?: string
}

function CustomTooltip({ active, payload, label, formatY }: TooltipProps<number, string> & { formatY?: (v: unknown) => string }) {
  if (!active || !payload?.length) return null
  const value = payload[0]?.value
  return (
    <div className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 shadow-xl text-sm">
      <p className="text-zinc-400 mb-1">{label}</p>
      <p className="text-amber-400 font-mono font-medium">
        {formatY ? formatY(value) : String(value)}
      </p>
    </div>
  )
}

export default function AreaChartComponent({
  data,
  xKey,
  yKey,
  color = '#f59e0b',
  gradientFill = true,
  showGrid = true,
  height = 200,
  formatX,
  formatY,
  className,
}: AreaChartProps) {
  const gradientId = `gradient-${yKey}`

  return (
    <div className={cn('w-full', className)} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={color} stopOpacity={0.25} />
              <stop offset="95%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>

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
            content={<CustomTooltip formatY={formatY} />}
            cursor={{ stroke: '#52525b', strokeWidth: 1 }}
          />

          <Area
            type="monotone"
            dataKey={yKey}
            stroke={color}
            strokeWidth={2}
            fill={gradientFill ? `url(#${gradientId})` : 'none'}
            dot={false}
            activeDot={{ r: 4, fill: color, stroke: '#18181b', strokeWidth: 2 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
