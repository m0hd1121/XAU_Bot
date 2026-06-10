import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

/**
 * Merge Tailwind CSS classes with clsx + tailwind-merge.
 * Use this for all dynamic className construction.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}

/**
 * Format a number as USD currency.
 */
export function formatCurrency(
  value: number | null | undefined,
  options?: Intl.NumberFormatOptions,
): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    ...options,
  }).format(value)
}

/**
 * Format a number as a compact currency (e.g. $1.23K).
 */
export function formatCurrencyCompact(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    notation: 'compact',
    maximumFractionDigits: 2,
  }).format(value)
}

/**
 * Format a number as a percentage string.
 */
export function formatPercent(value: number, decimals = 2): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(decimals)}%`
}

/**
 * Format a Unix timestamp (seconds) to a locale string.
 */
export function formatUnixTimestamp(ts: number): string {
  return new Date(ts * 1000).toLocaleString()
}

/**
 * Format a Unix timestamp (seconds) to a locale time string.
 */
export function formatUnixTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString()
}

/**
 * Format a Unix timestamp (seconds) to a locale date string.
 */
export function formatUnixDate(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString()
}

/**
 * Format an ISO timestamp string.
 */
export function formatISOTimestamp(iso: string): string {
  return new Date(iso).toLocaleString()
}

/**
 * Format seconds into a human-readable duration string (e.g. "2h 34m 12s").
 */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return '—'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h}h ${m}m ${s}s`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

/**
 * Format bytes to a human-readable string.
 */
export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

/**
 * Clamp a number between min and max.
 */
export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}

/**
 * Truncate a string to a max length, appending "…" if truncated.
 */
export function truncate(str: string, maxLength: number): string {
  if (str.length <= maxLength) return str
  return str.slice(0, maxLength - 1) + '…'
}

/**
 * Capitalize the first letter of a string.
 */
export function capitalize(str: string): string {
  if (!str) return ''
  return str.charAt(0).toUpperCase() + str.slice(1).toLowerCase()
}

/**
 * Convert a snake_case or SCREAMING_SNAKE_CASE string to Title Case.
 */
export function snakeToTitle(str: string): string {
  return str
    .toLowerCase()
    .split('_')
    .map((word) => capitalize(word))
    .join(' ')
}

/**
 * Safely parse JSON without throwing.
 */
export function safeJsonParse<T>(json: string, fallback: T): T {
  try {
    return JSON.parse(json) as T
  } catch {
    return fallback
  }
}

/**
 * Deep-clone an object via JSON round-trip.
 */
export function deepClone<T>(obj: T): T {
  return JSON.parse(JSON.stringify(obj)) as T
}

/**
 * Return a color class based on a PnL value.
 */
export function pnlColor(value: number): string {
  if (value > 0) return 'text-emerald-400'
  if (value < 0) return 'text-red-400'
  return 'text-zinc-400'
}

/**
 * Return a Tailwind color class for an agent status.
 */
export function agentStatusColor(status: string): string {
  switch (status) {
    case 'running': return 'text-emerald-400'
    case 'paused': return 'text-amber-400'
    case 'error': return 'text-red-400'
    case 'stopped': return 'text-zinc-400'
    default: return 'text-zinc-400'
  }
}

/**
 * Debounce a function.
 */
export function debounce<T extends (...args: unknown[]) => unknown>(
  fn: T,
  delay: number,
): (...args: Parameters<T>) => void {
  let timer: ReturnType<typeof setTimeout>
  return (...args: Parameters<T>) => {
    clearTimeout(timer)
    timer = setTimeout(() => fn(...args), delay)
  }
}

/**
 * Get a nested value from an object by dot-path (e.g. "a.b.c").
 */
export function getByPath(obj: Record<string, unknown>, path: string): unknown {
  return path.split('.').reduce<unknown>((acc, key) => {
    if (acc && typeof acc === 'object' && !Array.isArray(acc)) {
      return (acc as Record<string, unknown>)[key]
    }
    return undefined
  }, obj)
}
