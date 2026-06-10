'use client'

import { useState, useMemo, useCallback, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Search,
  Download,
  RotateCcw,
  Save,
  X,
  ChevronRight,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { apiClient } from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { Spinner } from '@/components/ui/Spinner'
import { ConfigSection, type ConfigParam } from '@/components/config/ConfigSection'

// ── Toast ─────────────────────────────────────────────────────────────────────

interface Toast {
  id: number
  message: string
  type: 'success' | 'error'
}

let toastId = 0

function ToastContainer({
  toasts,
  onRemove,
}: {
  toasts: Toast[]
  onRemove: (id: number) => void
}) {
  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={cn(
            'flex items-center gap-2 px-4 py-2.5 rounded-xl shadow-lg text-sm font-medium',
            'animate-in slide-in-from-bottom-2 duration-200',
            t.type === 'success'
              ? 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-300'
              : 'bg-red-500/10 border border-red-500/30 text-red-300'
          )}
        >
          <span className="flex-1">{t.message}</span>
          <button
            type="button"
            onClick={() => onRemove(t.id)}
            className="text-current opacity-60 hover:opacity-100"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      ))}
    </div>
  )
}

// ── Confirm modal ─────────────────────────────────────────────────────────────

function ConfirmModal({
  open,
  title,
  message,
  onConfirm,
  onCancel,
}: {
  open: boolean
  title: string
  message: string
  onConfirm: () => void
  onCancel: () => void
}) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/80 backdrop-blur-sm">
      <div className="bg-zinc-900 border border-zinc-700 rounded-2xl p-6 w-full max-w-sm shadow-2xl">
        <h3 className="text-zinc-100 text-base font-semibold mb-2">{title}</h3>
        <p className="text-zinc-400 text-sm mb-5 leading-relaxed">{message}</p>
        <div className="flex gap-2 justify-end">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 rounded-lg text-sm text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="px-4 py-2 rounded-lg text-sm bg-red-500/10 text-red-400 border border-red-500/30 hover:bg-red-500/20 transition-colors font-medium"
          >
            Confirm Reset
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Config categories ─────────────────────────────────────────────────────────

type CategoryId =
  | 'bot'
  | 'risk'
  | 'market_structure'
  | 'strategy'
  | 'sessions'
  | 'execution'
  | 'psychology'
  | 'learning'
  | 'agent1'
  | 'agent2'
  | 'agent3'
  | 'broker'
  | 'backtest'
  | 'logging'

const CATEGORIES: { id: CategoryId; label: string }[] = [
  { id: 'bot', label: 'Bot Core' },
  { id: 'risk', label: 'Risk Management' },
  { id: 'market_structure', label: 'Market Structure' },
  { id: 'strategy', label: 'Strategy' },
  { id: 'sessions', label: 'Sessions' },
  { id: 'execution', label: 'Execution' },
  { id: 'psychology', label: 'Psychology' },
  { id: 'learning', label: 'Learning Engine' },
  { id: 'agent1', label: 'Agent 1' },
  { id: 'agent2', label: 'Agent 2' },
  { id: 'agent3', label: 'Agent 3' },
  { id: 'broker', label: 'Broker' },
  { id: 'backtest', label: 'Backtesting' },
  { id: 'logging', label: 'Logging' },
]

// ── Parameter definitions ─────────────────────────────────────────────────────

const PARAMS: Record<CategoryId, ConfigParam[]> = {
  bot: [
    {
      path: 'bot.mode',
      label: 'Trading Mode',
      description: 'Operational mode: backtest feeds historical CSV, paper uses simulated orders, live routes to broker',
      type: 'enum',
      defaultValue: 'paper',
      options: [
        { value: 'backtest', label: 'Backtest' },
        { value: 'paper', label: 'Paper' },
        { value: 'live', label: 'Live' },
      ],
    },
    {
      path: 'bot.symbol',
      label: 'Trading Symbol',
      description: 'The instrument symbol (e.g. XAUUSD!, GC=F)',
      type: 'string',
      defaultValue: 'XAUUSD!',
    },
    {
      path: 'bot.timeframe',
      label: 'Primary Timeframe',
      description: 'Base timeframe for the strategy engine (e.g. 5m, 15m, 1h)',
      type: 'string',
      defaultValue: '5m',
    },
    {
      path: 'bot.htf_timeframe',
      label: 'Higher Timeframe',
      description: 'Higher timeframe used for bias detection (e.g. 1h, 4h)',
      type: 'string',
      defaultValue: '1h',
    },
  ],
  risk: [
    {
      path: 'risk.initial_capital',
      label: 'Initial Capital ($)',
      description: 'Starting account balance for paper/backtest modes',
      type: 'number',
      defaultValue: 10000,
      min: 1000,
      max: 1000000,
      step: 1000,
    },
    {
      path: 'risk.risk_per_trade',
      label: 'Risk Per Trade (%)',
      description: 'Fraction of capital risked per trade (stored as decimal, displayed as %)',
      type: 'percentage',
      defaultValue: 0.01,
      min: 0.001,
      max: 0.05,
      step: 0.001,
      displayMultiplier: 100,
    },
    {
      path: 'risk.max_risk_per_trade',
      label: 'Max Risk Per Trade (%)',
      description: 'Hard cap on risk per trade regardless of volatility scaling',
      type: 'percentage',
      defaultValue: 0.02,
      min: 0.001,
      max: 0.1,
      step: 0.001,
      displayMultiplier: 100,
    },
    {
      path: 'risk.daily_loss_limit',
      label: 'Daily Loss Limit (%)',
      description: 'Halt trading for the day if daily loss exceeds this percentage',
      type: 'percentage',
      defaultValue: 0.03,
      min: 0.005,
      max: 0.2,
      step: 0.005,
      displayMultiplier: 100,
    },
    {
      path: 'risk.max_drawdown_kill',
      label: 'Kill Switch Drawdown (%)',
      description: 'Emergency stop: halt all trading when drawdown reaches this level',
      type: 'percentage',
      defaultValue: 0.1,
      min: 0.01,
      max: 0.5,
      step: 0.01,
      displayMultiplier: 100,
    },
    {
      path: 'risk.min_reward_to_risk',
      label: 'Min Reward:Risk',
      description: 'Minimum R:R ratio required to take a trade',
      type: 'number',
      defaultValue: 1.5,
      min: 1.0,
      max: 5.0,
      step: 0.1,
    },
    {
      path: 'risk.max_open_trades',
      label: 'Max Open Trades',
      description: 'Maximum number of concurrent open positions',
      type: 'integer',
      defaultValue: 3,
      min: 1,
      max: 10,
    },
    {
      path: 'risk.volatility_lookback',
      label: 'Volatility Lookback (candles)',
      description: 'Number of candles used for ATR-based volatility calculation',
      type: 'integer',
      defaultValue: 20,
      min: 5,
      max: 100,
    },
    {
      path: 'risk.volatility_scale_factor',
      label: 'Volatility Scale Factor',
      description: 'Multiplier applied to ATR for dynamic position sizing',
      type: 'number',
      defaultValue: 1.0,
      min: 0.1,
      max: 5.0,
      step: 0.1,
    },
  ],
  market_structure: [
    {
      path: 'market_structure.swing_lookback',
      label: 'Swing Lookback',
      description: 'Candles to look back for swing high/low detection (3 for 5M, 5+ for 1H)',
      type: 'integer',
      defaultValue: 3,
      min: 1,
      max: 20,
    },
    {
      path: 'market_structure.bos_sensitivity',
      label: 'BOS Sensitivity',
      description: 'Minimum % move required to confirm a Break of Structure',
      type: 'number',
      defaultValue: 0.001,
      min: 0.0001,
      max: 0.01,
      step: 0.0001,
    },
    {
      path: 'market_structure.fvg_min_size_pips',
      label: 'FVG Minimum Size (pips)',
      description: 'Minimum gap size in pips to register a Fair Value Gap',
      type: 'number',
      defaultValue: 3.0,
      min: 0.5,
      max: 20.0,
      step: 0.5,
    },
    {
      path: 'market_structure.order_block_lookback',
      label: 'Order Block Lookback',
      description: 'Number of candles to scan for order block identification',
      type: 'integer',
      defaultValue: 10,
      min: 3,
      max: 50,
    },
  ],
  strategy: [
    {
      path: 'strategy.require_htf_bias',
      label: 'Require HTF Bias',
      description: 'Only take trades that align with the higher timeframe trend direction',
      type: 'boolean',
      defaultValue: true,
    },
    {
      path: 'strategy.require_session_window',
      label: 'Require Session Window',
      description: 'Only trade during defined session windows (London, NY, Asia)',
      type: 'boolean',
      defaultValue: true,
    },
    {
      path: 'strategy.entry_type',
      label: 'Entry Type',
      description: 'How orders are placed: market fills immediately, limit waits for pullback',
      type: 'enum',
      defaultValue: 'limit',
      options: [
        { value: 'market', label: 'Market' },
        { value: 'limit', label: 'Limit' },
      ],
    },
    {
      path: 'strategy.sl_buffer_pips',
      label: 'SL Buffer (pips)',
      description: 'Extra pips added beyond the structural stop loss level',
      type: 'number',
      defaultValue: 3.0,
      min: 0,
      max: 20,
      step: 0.5,
    },
    {
      path: 'strategy.partial_tp_pct',
      label: 'Partial TP Close (%)',
      description: 'Percentage of position to close at TP1 (remainder trails to TP2)',
      type: 'percentage',
      defaultValue: 0.5,
      min: 0.1,
      max: 0.9,
      step: 0.05,
      displayMultiplier: 100,
    },
    {
      path: 'strategy.tp1_rr',
      label: 'TP1 R:R',
      description: 'Reward:risk ratio for the first take profit target',
      type: 'number',
      defaultValue: 1.5,
      min: 1.0,
      max: 5.0,
      step: 0.1,
    },
    {
      path: 'strategy.tp2_rr',
      label: 'TP2 R:R',
      description: 'Reward:risk ratio for the second (runner) take profit target',
      type: 'number',
      defaultValue: 3.0,
      min: 1.0,
      max: 10.0,
      step: 0.5,
    },
    {
      path: 'strategy.use_break_even',
      label: 'Use Break Even',
      description: 'Move stop loss to entry price once TP1 is hit',
      type: 'boolean',
      defaultValue: true,
    },
    {
      path: 'strategy.trail_after_be',
      label: 'Trail After BE',
      description: 'Activate trailing stop loss once stop is moved to break even',
      type: 'boolean',
      defaultValue: false,
    },
  ],
  sessions: [
    {
      path: 'sessions.london.enabled',
      label: 'London Session',
      description: 'Enable trading during London market hours',
      type: 'boolean',
      defaultValue: true,
    },
    {
      path: 'sessions.new_york.enabled',
      label: 'New York Session',
      description: 'Enable trading during New York market hours',
      type: 'boolean',
      defaultValue: true,
    },
    {
      path: 'sessions.overlap.enabled',
      label: 'London/NY Overlap',
      description: 'Enable trading during London–New York overlap (highest liquidity)',
      type: 'boolean',
      defaultValue: true,
    },
    {
      path: 'sessions.asia.enabled',
      label: 'Asia Session',
      description: 'Enable trading during Asian market hours',
      type: 'boolean',
      defaultValue: false,
    },
  ],
  execution: [
    {
      path: 'execution.slippage_pips',
      label: 'Slippage (pips)',
      description: 'Maximum acceptable slippage when filling orders',
      type: 'number',
      defaultValue: 2.0,
      min: 0,
      max: 10,
      step: 0.5,
    },
    {
      path: 'execution.max_spread_pips',
      label: 'Max Spread (pips)',
      description: 'Refuse orders if spread exceeds this threshold',
      type: 'number',
      defaultValue: 5.0,
      min: 1,
      max: 20,
      step: 0.5,
    },
    {
      path: 'execution.retry_on_failure',
      label: 'Retry on Failure',
      description: 'Automatically retry order submission on transient broker errors',
      type: 'boolean',
      defaultValue: true,
    },
    {
      path: 'execution.max_retries',
      label: 'Max Retries',
      description: 'Number of order retry attempts before giving up',
      type: 'integer',
      defaultValue: 3,
      min: 1,
      max: 10,
    },
  ],
  psychology: [
    {
      path: 'psychology.max_consecutive_losses',
      label: 'Max Consecutive Losses',
      description: 'Stop trading after this many consecutive losses until next session',
      type: 'integer',
      defaultValue: 3,
      min: 1,
      max: 10,
    },
    {
      path: 'psychology.loss_streak_size_reduction',
      label: 'Loss Streak Size Reduction',
      description: 'Multiply position size by this factor during a losing streak',
      type: 'percentage',
      defaultValue: 0.5,
      min: 0.1,
      max: 1.0,
      step: 0.05,
      displayMultiplier: 100,
    },
    {
      path: 'psychology.cooldown_candles_after_loss',
      label: 'Cooldown After Loss (candles)',
      description: 'Number of candles to skip trading after a loss',
      type: 'integer',
      defaultValue: 3,
      min: 0,
      max: 50,
    },
    {
      path: 'psychology.min_setup_quality_score',
      label: 'Min Setup Quality Score',
      description: 'Minimum quality score (0–1) required to pass the psychology filter',
      type: 'number',
      defaultValue: 0.6,
      min: 0.1,
      max: 1.0,
      step: 0.05,
    },
    {
      path: 'psychology.max_trades_per_session',
      label: 'Max Trades Per Session',
      description: 'Hard cap on the number of trades allowed per session window',
      type: 'integer',
      defaultValue: 5,
      min: 1,
      max: 10,
    },
    {
      path: 'psychology.revenge_trade_detection',
      label: 'Revenge Trade Detection',
      description: 'Block trades that exhibit revenge trading patterns after a loss',
      type: 'boolean',
      defaultValue: true,
    },
  ],
  learning: [
    {
      path: 'learning.enabled',
      label: 'Enable Learning Engine',
      description: 'Enable the self-learning module (adds a confidence_score gate to entries)',
      type: 'boolean',
      defaultValue: false,
    },
    {
      path: 'learning.analysis_every_n_trades',
      label: 'Analyze Every N Trades',
      description: 'Run pattern analysis after every N completed trades',
      type: 'integer',
      defaultValue: 10,
      min: 1,
      max: 100,
    },
    {
      path: 'learning.min_trades_before_update',
      label: 'Min Trades Before Update',
      description: 'Minimum completed trades required before updating learned thresholds',
      type: 'integer',
      defaultValue: 20,
      min: 5,
      max: 500,
    },
    {
      path: 'learning.adaptive_threshold',
      label: 'Adaptive Threshold',
      description: 'Automatically adjust confidence threshold based on recent performance',
      type: 'boolean',
      defaultValue: true,
    },
    {
      path: 'learning.min_confidence_threshold',
      label: 'Min Confidence Threshold',
      description: 'Minimum learning confidence score required to allow trade execution',
      type: 'number',
      defaultValue: 0.5,
      min: 0.0,
      max: 1.0,
      step: 0.05,
    },
    {
      path: 'learning.min_pattern_samples',
      label: 'Min Pattern Samples',
      description: 'Minimum sample count before a pattern is considered statistically valid',
      type: 'integer',
      defaultValue: 15,
      min: 3,
      max: 200,
    },
  ],
  agent1: [
    {
      path: 'agents.agent1.population_size',
      label: 'Population Size',
      description: 'Number of strategy genomes per evolutionary generation',
      type: 'integer',
      defaultValue: 50,
      min: 10,
      max: 100,
    },
    {
      path: 'agents.agent1.shadow_mode_bars',
      label: 'Shadow Mode Bars',
      description: 'Candles to run in shadow (paper) mode before promoting a strategy',
      type: 'integer',
      defaultValue: 500,
      min: 50,
      max: 2000,
    },
    {
      path: 'agents.agent1.auto_promote',
      label: 'Auto-Promote Strategies',
      description: 'Automatically promote validated strategies without manual approval',
      type: 'boolean',
      defaultValue: false,
    },
    {
      path: 'agents.agent1.evolution_sleep_seconds',
      label: 'Evolution Sleep (seconds)',
      description: 'Pause between evolution cycles to avoid resource overload',
      type: 'integer',
      defaultValue: 60,
      min: 30,
      max: 600,
    },
  ],
  agent2: [
    {
      path: 'agents.agent2.cycle_interval_seconds',
      label: 'Analysis Interval (seconds)',
      description: 'How often Agent 2 refreshes market intelligence and regime detection',
      type: 'integer',
      defaultValue: 60,
      min: 30,
      max: 300,
    },
    {
      path: 'agents.agent2.economic_calendar',
      label: 'Enable Economic Calendar',
      description: 'Include fundamental event data in risk scoring',
      type: 'boolean',
      defaultValue: true,
    },
    {
      path: 'agents.agent2.risk_score_halt_threshold',
      label: 'Risk Halt Threshold',
      description: 'If Agent 2 risk score exceeds this value, Agent 3 halts new trades',
      type: 'number',
      defaultValue: 0.75,
      min: 0.5,
      max: 1.0,
      step: 0.05,
    },
  ],
  agent3: [
    {
      path: 'agents.agent3.cycle_interval_seconds',
      label: 'Trading Cycle (seconds)',
      description: 'How often Agent 3 polls for new trade opportunities',
      type: 'integer',
      defaultValue: 30,
      min: 10,
      max: 120,
    },
    {
      path: 'agents.agent3.require_agent2_intel',
      label: 'Require Agent 2 Intel',
      description: 'Gate trades on fresh market intelligence from Agent 2',
      type: 'boolean',
      defaultValue: true,
    },
    {
      path: 'agents.agent3.intel_max_age_seconds',
      label: 'Intel Max Age (seconds)',
      description: 'Maximum age of Agent 2 intel before Agent 3 considers it stale',
      type: 'integer',
      defaultValue: 300,
      min: 60,
      max: 900,
    },
  ],
  broker: [
    {
      path: 'broker.type',
      label: 'Broker Type',
      description: 'Which broker adapter to use for order execution',
      type: 'enum',
      defaultValue: 'paper',
      options: [
        { value: 'paper', label: 'Paper' },
        { value: 'dwx', label: 'DWX (MT5 Bridge)' },
        { value: 'metaapi', label: 'MetaAPI' },
        { value: 'oanda', label: 'OANDA' },
      ],
    },
    {
      path: 'broker.dwx.magic',
      label: 'DWX Magic Number',
      description: 'MT5 magic number — must match the EA input settings',
      type: 'integer',
      defaultValue: 88888,
    },
    {
      path: 'broker.dwx.deviation',
      label: 'DWX Deviation',
      description: 'Maximum price deviation in points for market orders (EA requires 50)',
      type: 'integer',
      defaultValue: 50,
      min: 1,
      max: 200,
    },
  ],
  backtest: [
    {
      path: 'backtest.start_date',
      label: 'Start Date',
      description: 'Backtest start date in YYYY-MM-DD format',
      type: 'string',
      defaultValue: '2024-01-01',
    },
    {
      path: 'backtest.end_date',
      label: 'End Date',
      description: 'Backtest end date in YYYY-MM-DD format',
      type: 'string',
      defaultValue: '2024-12-31',
    },
    {
      path: 'backtest.commission_per_lot',
      label: 'Commission Per Lot ($)',
      description: 'Trading commission per standard lot for P&L accuracy',
      type: 'number',
      defaultValue: 7.0,
      min: 0,
      max: 50,
      step: 0.5,
    },
    {
      path: 'backtest.spread_pips',
      label: 'Spread (pips)',
      description: 'Simulated spread applied to all backtest orders',
      type: 'number',
      defaultValue: 2.5,
      min: 0.5,
      max: 10,
      step: 0.5,
    },
  ],
  logging: [
    {
      path: 'logging.level',
      label: 'Log Level',
      description: 'Minimum log level to capture (DEBUG captures everything)',
      type: 'enum',
      defaultValue: 'INFO',
      options: [
        { value: 'DEBUG', label: 'DEBUG' },
        { value: 'INFO', label: 'INFO' },
        { value: 'WARNING', label: 'WARNING' },
        { value: 'ERROR', label: 'ERROR' },
      ],
    },
    {
      path: 'logging.file_rotation_mb',
      label: 'Log File Rotation (MB)',
      description: 'Rotate log file when it exceeds this size',
      type: 'integer',
      defaultValue: 10,
      min: 1,
      max: 100,
    },
    {
      path: 'logging.max_files',
      label: 'Max Log Files',
      description: 'Maximum number of rotated log files to keep',
      type: 'integer',
      defaultValue: 5,
      min: 1,
      max: 20,
    },
  ],
}

// ── All params flat list (for search) ─────────────────────────────────────────

const ALL_PARAMS: (ConfigParam & { categoryId: CategoryId })[] = CATEGORIES.flatMap((cat) =>
  (PARAMS[cat.id] ?? []).map((p) => ({ ...p, categoryId: cat.id }))
)

// ── Unsaved banner ────────────────────────────────────────────────────────────

function UnsavedBanner({
  count,
  onSaveAll,
  onDiscard,
  saving,
}: {
  count: number
  onSaveAll: () => void
  onDiscard: () => void
  saving: boolean
}) {
  if (count === 0) return null
  return (
    <div className="sticky top-0 z-20 bg-amber-500/10 border border-amber-500/30 rounded-xl px-4 py-2.5 flex items-center gap-3 backdrop-blur-sm">
      <span className="w-2 h-2 rounded-full bg-amber-400 flex-shrink-0" />
      <span className="text-amber-300 text-xs flex-1">
        {count} unsaved change{count !== 1 ? 's' : ''}
      </span>
      <button
        type="button"
        onClick={onDiscard}
        className="text-zinc-400 hover:text-zinc-200 text-xs transition-colors px-2"
      >
        Discard
      </button>
      <button
        type="button"
        onClick={onSaveAll}
        disabled={saving}
        className={cn(
          'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium',
          'bg-amber-500 text-zinc-900 hover:bg-amber-400 transition-colors',
          saving && 'opacity-70 cursor-not-allowed'
        )}
      >
        {saving ? <Spinner size="sm" /> : <Save className="w-3.5 h-3.5" />}
        Save All
      </button>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ConfigPage() {
  const queryClient = useQueryClient()
  const [activeCategory, setActiveCategory] = useState<CategoryId>('bot')
  const [search, setSearch] = useState('')
  const [pendingValues, setPendingValues] = useState<Record<string, unknown>>({})
  const [pendingPaths, setPendingPaths] = useState<Set<string>>(new Set())
  const [errorPaths, setErrorPaths] = useState<Record<string, string>>({})
  const [savingAll, setSavingAll] = useState(false)
  const [toasts, setToasts] = useState<Toast[]>([])
  const [showResetModal, setShowResetModal] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  const { data: remoteConfig = {}, isLoading } = useQuery<Record<string, unknown>>({
    queryKey: ['config'],
    queryFn: () => apiClient.getConfig(),
    staleTime: 60_000,
  })

  // Merged values: remote + pending overrides
  const mergedValues = useMemo(() => {
    return { ...remoteConfig, ...pendingValues }
  }, [remoteConfig, pendingValues])

  function addToast(message: string, type: 'success' | 'error') {
    const id = ++toastId
    setToasts((prev) => [...prev, { id, message, type }])
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id))
    }, 4000)
  }

  function removeToast(id: number) {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }

  const handleChange = useCallback((path: string, value: unknown) => {
    setPendingValues((prev) => ({ ...prev, [path]: value }))
    setPendingPaths((prev) => new Set(prev).add(path))
    setErrorPaths((prev) => {
      const next = { ...prev }
      delete next[path]
      return next
    })
  }, [])

  const handleSave = useCallback(async (path: string, value: unknown) => {
    await apiClient.updateConfigField(path, value)
    setPendingPaths((prev) => {
      const next = new Set(prev)
      next.delete(path)
      return next
    })
    setPendingValues((prev) => {
      const next = { ...prev }
      delete next[path]
      return next
    })
    void queryClient.invalidateQueries({ queryKey: ['config'] })
    addToast(`Saved ${path}`, 'success')
  }, [queryClient])

  async function handleSaveAll() {
    setSavingAll(true)
    const entries = Array.from(pendingPaths)
    let errors = 0
    for (const path of entries) {
      try {
        await apiClient.updateConfigField(path, mergedValues[path])
        setPendingPaths((prev) => {
          const next = new Set(prev)
          next.delete(path)
          return next
        })
      } catch {
        errors++
        setErrorPaths((prev) => ({ ...prev, [path]: 'Save failed' }))
      }
    }
    setPendingValues({})
    setSavingAll(false)
    void queryClient.invalidateQueries({ queryKey: ['config'] })
    if (errors === 0) {
      addToast(`Saved ${entries.length} field${entries.length !== 1 ? 's' : ''}`, 'success')
    } else {
      addToast(`${errors} field${errors !== 1 ? 's' : ''} failed to save`, 'error')
    }
  }

  function handleDiscard() {
    setPendingValues({})
    setPendingPaths(new Set())
    setErrorPaths({})
  }

  function handleExport() {
    const config = mergedValues
    const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    const date = new Date().toISOString().split('T')[0]
    a.href = url
    a.download = `xau-config-${date}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  function handleResetDefaults() {
    // Apply all default values as pending changes
    const defaults: Record<string, unknown> = {}
    const paths = new Set<string>()
    ALL_PARAMS.forEach((p) => {
      defaults[p.path] = p.defaultValue
      paths.add(p.path)
    })
    setPendingValues(defaults)
    setPendingPaths(paths)
    setShowResetModal(false)
    addToast('Default values loaded — review and save to apply', 'success')
  }

  // Search mode: show all matching params across categories
  const isSearching = search.trim().length > 0
  const searchResults = useMemo(() => {
    if (!isSearching) return []
    const q = search.toLowerCase()
    return ALL_PARAMS.filter(
      (p) =>
        p.label.toLowerCase().includes(q) ||
        p.path.toLowerCase().includes(q) ||
        p.description.toLowerCase().includes(q)
    )
  }, [search, isSearching])

  const activeCategoryParams = PARAMS[activeCategory] ?? []

  return (
    <div className="min-h-screen bg-zinc-950 p-4">

      {/* Page header */}
      <div className="flex flex-col sm:flex-row sm:items-start gap-4 mb-4">
        <div className="flex-1">
          <h1 className="text-lg font-semibold text-zinc-100">Configuration Center</h1>
          <p className="text-zinc-500 text-xs mt-0.5">
            All platform parameters — changes sync instantly
          </p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-500 pointer-events-none" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search parameters…"
              className={cn(
                'bg-zinc-800 border border-zinc-700 rounded-lg pl-8 pr-3 py-1.5 text-xs text-zinc-200',
                'placeholder-zinc-600 focus:outline-none focus:border-zinc-500',
                'focus:ring-1 focus:ring-zinc-500/30 transition-colors w-48'
              )}
            />
          </div>
          <button
            type="button"
            onClick={handleExport}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-zinc-400 bg-zinc-800 border border-zinc-700 hover:bg-zinc-700 hover:text-zinc-200 transition-colors"
          >
            <Download className="w-3.5 h-3.5" />
            Export
          </button>
          <button
            type="button"
            onClick={() => setShowResetModal(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-red-400 bg-red-500/10 border border-red-500/20 hover:bg-red-500/20 transition-colors"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Reset
          </button>
        </div>
      </div>

      {/* Unsaved banner */}
      <div className="mb-4">
        <UnsavedBanner
          count={pendingPaths.size}
          onSaveAll={() => void handleSaveAll()}
          onDiscard={handleDiscard}
          saving={savingAll}
        />
      </div>

      {/* Loading state */}
      {isLoading && (
        <div className="flex items-center justify-center py-20">
          <Spinner size="md" />
          <span className="ml-3 text-zinc-500 text-sm">Loading configuration…</span>
        </div>
      )}

      {!isLoading && (
        <div className="flex gap-4">

          {/* Sidebar — desktop */}
          <aside className="hidden lg:flex flex-col w-52 flex-shrink-0 gap-1">
            {CATEGORIES.map((cat) => {
              const pendingInCat = (PARAMS[cat.id] ?? []).filter((p) =>
                pendingPaths.has(p.path)
              ).length
              return (
                <button
                  key={cat.id}
                  type="button"
                  onClick={() => setActiveCategory(cat.id)}
                  className={cn(
                    'flex items-center justify-between px-3 py-2 rounded-lg text-xs font-medium text-left transition-colors',
                    activeCategory === cat.id
                      ? 'bg-zinc-800 text-zinc-100'
                      : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-900'
                  )}
                >
                  <span>{cat.label}</span>
                  {pendingInCat > 0 && (
                    <span className="w-4 h-4 rounded-full bg-amber-500 text-zinc-900 text-[9px] font-bold flex items-center justify-center flex-shrink-0">
                      {pendingInCat}
                    </span>
                  )}
                </button>
              )
            })}
          </aside>

          {/* Mobile: category tabs */}
          <div className="lg:hidden w-full">
            <button
              type="button"
              onClick={() => setMobileMenuOpen((v) => !v)}
              className="flex items-center gap-2 w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-2.5 text-xs text-zinc-300 mb-3"
            >
              <span className="flex-1 text-left font-medium">
                {CATEGORIES.find((c) => c.id === activeCategory)?.label ?? 'Category'}
              </span>
              <ChevronRight className={cn('w-4 h-4 transition-transform', mobileMenuOpen && 'rotate-90')} />
            </button>
            {mobileMenuOpen && (
              <div className="grid grid-cols-2 gap-1 mb-3">
                {CATEGORIES.map((cat) => (
                  <button
                    key={cat.id}
                    type="button"
                    onClick={() => {
                      setActiveCategory(cat.id)
                      setMobileMenuOpen(false)
                    }}
                    className={cn(
                      'px-3 py-2 rounded-lg text-xs font-medium text-left transition-colors',
                      activeCategory === cat.id
                        ? 'bg-zinc-700 text-zinc-100'
                        : 'bg-zinc-900 text-zinc-400 hover:text-zinc-200'
                    )}
                  >
                    {cat.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Main content */}
          <div className="flex-1 min-w-0 space-y-6">
            {isSearching ? (
              <>
                <div className="text-zinc-500 text-xs mb-2">
                  {searchResults.length} parameter{searchResults.length !== 1 ? 's' : ''} matching &ldquo;{search}&rdquo;
                </div>
                {searchResults.length === 0 ? (
                  <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-12 flex flex-col items-center text-zinc-600">
                    <Search className="w-8 h-8 mb-2" />
                    <p className="text-sm">No parameters found</p>
                  </div>
                ) : (
                  <ConfigSection
                    title="Search Results"
                    params={searchResults}
                    values={mergedValues}
                    onChange={handleChange}
                    onSave={handleSave}
                    pendingPaths={pendingPaths}
                    errorPaths={errorPaths}
                  />
                )}
              </>
            ) : (
              <ConfigSection
                title={CATEGORIES.find((c) => c.id === activeCategory)?.label ?? ''}
                params={activeCategoryParams}
                values={mergedValues}
                onChange={handleChange}
                onSave={handleSave}
                pendingPaths={pendingPaths}
                errorPaths={errorPaths}
              />
            )}
          </div>
        </div>
      )}

      {/* Reset confirm modal */}
      <ConfirmModal
        open={showResetModal}
        title="Reset to Defaults?"
        message="This will stage all parameters at their default values. You will need to save to apply the changes. This cannot be undone."
        onConfirm={handleResetDefaults}
        onCancel={() => setShowResetModal(false)}
      />

      {/* Toasts */}
      <ToastContainer toasts={toasts} onRemove={removeToast} />
    </div>
  )
}
