'use client'

import {
  LineChart,
  Line,
  ResponsiveContainer,
  Tooltip,
} from 'recharts'
import { cn } from '@/lib/utils'

interface SparkLineProps {
  data: number[]
  color?: string
  height?: number
  width?: number
  showTooltip?: boolean
  className?: string
}

export function SparkLine({
  data,
  color = '#f59e0b',
  height = 40,
  showTooltip = false,
  className,
}: SparkLineProps) {
  const chartData = data.map((value, index) => ({ index, value }))

  // Determine if the trend is positive (last > first)
  const trend = data.length >= 2
    ? data[data.length - 1] > data[0]
      ? '#10b981'   // emerald
      : '#ef4444'   // red
    : color

  const finalColor = color === 'trend' ? trend : color

  return (
    <div className={cn('inline-block', className)} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData}>
          {showTooltip && (
            <Tooltip
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null
                return (
                  <div className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs font-mono text-amber-400">
                    {payload[0]?.value?.toFixed(4)}
                  </div>
                )
              }}
            />
          )}
          <Line
            type="monotone"
            dataKey="value"
            stroke={finalColor}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export default SparkLine
