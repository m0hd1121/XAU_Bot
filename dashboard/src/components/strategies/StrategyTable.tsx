'use client'

import { useState, useMemo } from 'react'
import { cn } from '@/lib/utils'
import type { StrategyCandidate } from '@/types'
import { Button } from '@/components/ui/Button'
import { Spinner } from '@/components/ui/Spinner'
import { StrategyDetail } from '@/components/strategies/StrategyDetail'
import {
  Crown,
  ChevronUp,
  ChevronDown,
  ChevronsUpDown,
  Eye,
  CheckCircle,
  XCircle,
} from 'lucide-react'

export interface StrategyTableProps {
  strategies: StrategyCandidate[]
  loading?: boolean
  onPromote?: (hash: string) => void
  onReject?: (hash: string) => void
  onView?: (strategy: StrategyCandidate) => void
  promotePending?: boolean
  rejectPending?: boolean
}

// ─── Status badge ─────────────────────────────────────────────────────────────

type SortKey =
  | 'id'
  | 'generation'
  | 'status'
  | 'composite_score'
  | 'expectancy'
  | 'profit_factor'
  | 'win_rate'
  | 'max_drawdown_pct'
  | 'total_trades'
  | 'created_at'

type SortDir = 'asc' | 'desc'

const STATUS_STYLES: Record<
  string,
  { className: string; label: string; bg?: string }
> = {
  pending: {
    label: 'Pending',
    className: 'bg-zinc-800 text-zinc-400 border-zinc-700',
  },
  validating: {
    label: 'Validating',
    className: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  },
  validated: {
    label: 'Validated',
    className: 'bg-sky-500/10 text-sky-400 border-sky-500/20',
  },
  shadow: {
    label: 'Shadow',
    className: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20',
    bg: 'bg-indigo-500/5',
  },
  promoted: {
    label: 'Promoted',
    className: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    bg: 'bg-emerald-500/5',
  },
  rejected: {
    label: 'Rejected',
    className: 'bg-red-500/10 text-red-400 border-red-500/20',
    bg: 'bg-red-500/5',
  },
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function timeAgo(ts: number): string {
  const diff = Math.floor(Date.now() / 1000 - ts)
  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

function ScoreBar({ value }: { value: number | undefined | null }) {
  if (value == null) return <span className="text-zinc-600">—</span>
  const pct = Math.max(0, Math.min(1, value)) * 100
  const color =
    value >= 0.7 ? 'bg-emerald-500' : value >= 0.4 ? 'bg-amber-500' : 'bg-red-500'
  return (
    <div className="flex items-center gap-2">
      <span className="text-zinc-200 font-mono text-xs w-10 text-right">
        {value.toFixed(3)}
      </span>
      <div className="flex-1 bg-zinc-800 rounded-full h-1.5 w-14 overflow-hidden">
        <div
          className={cn('h-full rounded-full', color)}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

// ─── Sort icon ────────────────────────────────────────────────────────────────

function SortIcon({
  column,
  sortKey,
  sortDir,
}: {
  column: SortKey
  sortKey: SortKey
  sortDir: SortDir
}) {
  if (sortKey !== column) return <ChevronsUpDown className="w-3 h-3 text-zinc-600" />
  return sortDir === 'asc' ? (
    <ChevronUp className="w-3 h-3 text-amber-400" />
  ) : (
    <ChevronDown className="w-3 h-3 text-amber-400" />
  )
}

// ─── Skeleton row ─────────────────────────────────────────────────────────────

function SkeletonRow() {
  return (
    <tr className="animate-pulse">
      {Array.from({ length: 11 }).map((_, i) => (
        <td key={i} className="px-3 py-3">
          <div className="h-3 bg-zinc-800 rounded w-full" />
        </td>
      ))}
    </tr>
  )
}

const PAGE_SIZE = 25

// ─── Main ─────────────────────────────────────────────────────────────────────

export function StrategyTable({
  strategies,
  loading = false,
  onPromote,
  onReject,
  onView,
  promotePending = false,
  rejectPending = false,
}: StrategyTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>('created_at')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [page, setPage] = useState(0)
  const [selectedStrategy, setSelectedStrategy] = useState<StrategyCandidate | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [pendingHash, setPendingHash] = useState<string | null>(null)

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
    setPage(0)
  }

  const sorted = useMemo(() => {
    const arr = [...strategies]
    arr.sort((a, b) => {
      let av: number | string | undefined
      let bv: number | string | undefined
      switch (sortKey) {
        case 'id': av = a.id; bv = b.id; break
        case 'generation': av = a.generation; bv = b.generation; break
        case 'status': av = a.status; bv = b.status; break
        case 'composite_score': av = a.fitness.composite_score ?? -1; bv = b.fitness.composite_score ?? -1; break
        case 'expectancy': av = a.fitness.expectancy ?? -999; bv = b.fitness.expectancy ?? -999; break
        case 'profit_factor': av = a.fitness.profit_factor ?? 0; bv = b.fitness.profit_factor ?? 0; break
        case 'win_rate': av = a.fitness.win_rate ?? 0; bv = b.fitness.win_rate ?? 0; break
        case 'max_drawdown_pct': av = a.fitness.max_drawdown_pct ?? 0; bv = b.fitness.max_drawdown_pct ?? 0; break
        case 'total_trades': av = a.fitness.total_trades ?? 0; bv = b.fitness.total_trades ?? 0; break
        case 'created_at': av = a.created_at; bv = b.created_at; break
        default: av = a.created_at; bv = b.created_at
      }
      if (typeof av === 'string' && typeof bv === 'string') {
        return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av)
      }
      const an = av as number
      const bn = bv as number
      return sortDir === 'asc' ? an - bn : bn - an
    })
    return arr
  }, [strategies, sortKey, sortDir])

  const totalPages = Math.ceil(sorted.length / PAGE_SIZE)
  const paginated = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  function openDetail(s: StrategyCandidate) {
    setSelectedStrategy(s)
    setDetailOpen(true)
    onView?.(s)
  }

  async function handlePromote(hash: string) {
    setPendingHash(hash)
    try {
      await Promise.resolve(onPromote?.(hash))
    } finally {
      setPendingHash(null)
    }
  }

  async function handleReject(hash: string) {
    setPendingHash(hash)
    try {
      await Promise.resolve(onReject?.(hash))
    } finally {
      setPendingHash(null)
    }
  }

  const colHeader = (label: string, key: SortKey) => (
    <th
      className="px-3 py-2.5 text-left text-zinc-500 text-[11px] font-medium uppercase tracking-wider cursor-pointer hover:text-zinc-300 transition-colors whitespace-nowrap"
      onClick={() => handleSort(key)}
    >
      <div className="flex items-center gap-1">
        {label}
        <SortIcon column={key} sortKey={sortKey} sortDir={sortDir} />
      </div>
    </th>
  )

  return (
    <>
      <div className="overflow-x-auto rounded-xl border border-zinc-800">
        <table className="w-full text-sm border-collapse">
          <thead className="bg-zinc-900 border-b border-zinc-800">
            <tr>
              {colHeader('#', 'id')}
              <th className="px-3 py-2.5 text-left text-zinc-500 text-[11px] font-medium uppercase tracking-wider">Hash</th>
              {colHeader('Gen', 'generation')}
              {colHeader('Status', 'status')}
              {colHeader('Score', 'composite_score')}
              {colHeader('Expectancy', 'expectancy')}
              {colHeader('PF', 'profit_factor')}
              {colHeader('Win%', 'win_rate')}
              {colHeader('MaxDD', 'max_drawdown_pct')}
              {colHeader('Trades', 'total_trades')}
              {colHeader('Created', 'created_at')}
              <th className="px-3 py-2.5 text-left text-zinc-500 text-[11px] font-medium uppercase tracking-wider">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/60">
            {loading &&
              Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} />)}
            {!loading && paginated.length === 0 && (
              <tr>
                <td colSpan={12} className="text-center py-10 text-zinc-600 text-sm">
                  No strategies found
                </td>
              </tr>
            )}
            {!loading &&
              paginated.map((s) => {
                const statusCfg = STATUS_BADGE_ROW[s.status]
                const rowBg =
                  s.status === 'promoted'
                    ? 'bg-emerald-500/5 hover:bg-emerald-500/10'
                    : s.status === 'rejected'
                    ? 'bg-red-500/5 hover:bg-red-500/10'
                    : s.status === 'shadow'
                    ? 'bg-indigo-500/5 hover:bg-indigo-500/10'
                    : 'hover:bg-zinc-800/40'
                const isThisPending = pendingHash === s.genome_hash

                return (
                  <tr
                    key={s.id}
                    className={cn(
                      'cursor-pointer transition-colors',
                      rowBg
                    )}
                    onClick={() => openDetail(s)}
                  >
                    <td className="px-3 py-2.5 text-zinc-500 text-xs font-mono">{s.id}</td>
                    <td className="px-3 py-2.5">
                      <span className="font-mono text-amber-400 text-xs">
                        {s.genome_hash.slice(0, 8)}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-zinc-400 text-xs font-mono">{s.generation}</td>
                    <td className="px-3 py-2.5">
                      <span
                        className={cn(
                          'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium border',
                          statusCfg.className
                        )}
                      >
                        {s.status === 'promoted' && <Crown className="w-2.5 h-2.5" />}
                        {s.status === 'validating' && <Spinner size="xs" />}
                        {statusCfg.label}
                      </span>
                    </td>
                    <td className="px-3 py-2.5">
                      <ScoreBar value={s.fitness.composite_score} />
                    </td>
                    <td className="px-3 py-2.5 text-zinc-300 text-xs font-mono">
                      {s.fitness.expectancy != null
                        ? `$${s.fitness.expectancy.toFixed(2)}`
                        : '—'}
                    </td>
                    <td className="px-3 py-2.5 text-zinc-300 text-xs font-mono">
                      {s.fitness.profit_factor != null
                        ? `${s.fitness.profit_factor.toFixed(2)}x`
                        : '—'}
                    </td>
                    <td className="px-3 py-2.5 text-zinc-300 text-xs font-mono">
                      {s.fitness.win_rate != null
                        ? `${(s.fitness.win_rate * 100).toFixed(0)}%`
                        : '—'}
                    </td>
                    <td className="px-3 py-2.5 text-zinc-300 text-xs font-mono">
                      {s.fitness.max_drawdown_pct != null
                        ? `${(s.fitness.max_drawdown_pct * 100).toFixed(1)}%`
                        : '—'}
                    </td>
                    <td className="px-3 py-2.5 text-zinc-400 text-xs font-mono">
                      {s.fitness.total_trades ?? '—'}
                    </td>
                    <td className="px-3 py-2.5 text-zinc-500 text-xs">
                      {timeAgo(s.created_at)}
                    </td>
                    <td
                      className="px-3 py-2.5"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <div className="flex items-center gap-1">
                        {/* Promote */}
                        {(s.status === 'validated' || s.status === 'shadow') && onPromote && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 w-6 p-0 text-emerald-500 hover:bg-emerald-500/10 hover:text-emerald-400"
                            onClick={() => handlePromote(s.genome_hash)}
                            disabled={isThisPending || promotePending}
                            title="Promote"
                          >
                            {isThisPending && promotePending ? (
                              <Spinner size="xs" />
                            ) : (
                              <Crown className="w-3.5 h-3.5" />
                            )}
                          </Button>
                        )}
                        {/* Reject */}
                        {s.status !== 'promoted' && s.status !== 'rejected' && onReject && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 w-6 p-0 text-red-500 hover:bg-red-500/10 hover:text-red-400"
                            onClick={() => handleReject(s.genome_hash)}
                            disabled={isThisPending || rejectPending}
                            title="Reject"
                          >
                            {isThisPending && rejectPending ? (
                              <Spinner size="xs" />
                            ) : (
                              <XCircle className="w-3.5 h-3.5" />
                            )}
                          </Button>
                        )}
                        {/* View */}
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 w-6 p-0 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300"
                          onClick={() => openDetail(s)}
                          title="View details"
                        >
                          <Eye className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                )
              })}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-3">
          <span className="text-zinc-500 text-xs">
            Showing {page * PAGE_SIZE + 1}–
            {Math.min((page + 1) * PAGE_SIZE, sorted.length)} of {sorted.length}
          </span>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-xs text-zinc-400 hover:text-zinc-200"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
            >
              Prev
            </Button>
            {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
              const pageNum =
                totalPages <= 7
                  ? i
                  : page < 4
                  ? i
                  : page > totalPages - 4
                  ? totalPages - 7 + i
                  : page - 3 + i
              return (
                <Button
                  key={pageNum}
                  variant="ghost"
                  size="sm"
                  className={cn(
                    'h-7 w-7 p-0 text-xs',
                    pageNum === page
                      ? 'bg-amber-500/20 text-amber-400'
                      : 'text-zinc-500 hover:text-zinc-200'
                  )}
                  onClick={() => setPage(pageNum)}
                >
                  {pageNum + 1}
                </Button>
              )
            })}
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-xs text-zinc-400 hover:text-zinc-200"
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page === totalPages - 1}
            >
              Next
            </Button>
          </div>
        </div>
      )}

      {/* Detail modal */}
      <StrategyDetail
        strategy={selectedStrategy}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        onPromote={onPromote ? (hash) => { void handlePromote(hash) } : undefined}
        onReject={onReject ? (hash) => { void handleReject(hash) } : undefined}
        promotePending={promotePending || (pendingHash === selectedStrategy?.genome_hash && promotePending)}
        rejectPending={rejectPending || (pendingHash === selectedStrategy?.genome_hash && rejectPending)}
      />
    </>
  )
}

// ─── Status badge config for rows ────────────────────────────────────────────
// (Defined after component to keep code organized)

const STATUS_BADGE_ROW: Record<
  string,
  { className: string; label: string }
> = {
  pending: { label: 'Pending', className: 'bg-zinc-800 text-zinc-400 border-zinc-700' },
  validating: { label: 'Validating', className: 'bg-amber-500/10 text-amber-400 border-amber-500/20' },
  validated: { label: 'Validated', className: 'bg-sky-500/10 text-sky-400 border-sky-500/20' },
  shadow: { label: 'Shadow', className: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20' },
  promoted: { label: 'Promoted', className: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' },
  rejected: { label: 'Rejected', className: 'bg-red-500/10 text-red-400 border-red-500/20' },
}
