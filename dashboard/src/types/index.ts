// ─── Auth ────────────────────────────────────────────────────────────────────
export interface LoginRequest { username: string; password: string }
export interface AuthTokens { access_token: string; refresh_token: string; token_type: string }
export interface UserProfile { id: number; username: string; email: string; role: string }

// ─── Agent ───────────────────────────────────────────────────────────────────
export type AgentId = 'agent1' | 'agent2' | 'agent3'
export type AgentStatus = 'running' | 'stopped' | 'paused' | 'error' | 'starting'

export interface AgentMetrics {
  cycle_count?: number
  error_count?: number
  last_cycle_ms?: number
  cpu_pct?: number
  mem_mb?: number
  uptime_seconds?: number
  // Agent 1
  generation?: number
  best_score?: number
  population_size?: number
  validated_count?: number
  rejected_count?: number
  promoted_count?: number
  trade_feedback_count?: number
  // Agent 2
  risk_score?: number
  regime?: string
  // Agent 3
  open_trades_count?: number
  consecutive_losses?: number
  last_trade_direction?: string
  last_trade_entry?: number
  [key: string]: unknown
}

export interface AgentState {
  agent_id: AgentId
  status: AgentStatus
  current_task: string
  last_heartbeat: number
  uptime_seconds: number
  metrics: AgentMetrics
}

// ─── Strategy ────────────────────────────────────────────────────────────────
export type StrategyStatus = 'pending' | 'validating' | 'validated' | 'rejected' | 'shadow' | 'promoted'

export interface StrategyFitness {
  composite_score?: number
  expectancy?: number
  profit_factor?: number
  sharpe_ratio?: number
  sortino_ratio?: number
  max_drawdown_pct?: number
  win_rate?: number
  total_trades?: number
  stability_score?: number
  recovery_factor?: number
  passed_minimum?: boolean
  rejection_reason?: string
}

export interface StrategyCandidate {
  id: number
  genome_hash: string
  status: StrategyStatus
  fitness: StrategyFitness
  generation: number
  created_at: number
  notes: string
}

// ─── Market Intelligence ─────────────────────────────────────────────────────
export type MarketRegime = 'TRENDING_BULLISH' | 'TRENDING_BEARISH' | 'RANGING' | 'HIGH_VOLATILITY' | 'UNCERTAIN' | 'UNKNOWN'

export interface MarketIntel {
  timestamp: number
  regime: MarketRegime | string
  trend: string
  risk_score: number
  confidence: number
  technical: Record<string, unknown>
  fundamental: Record<string, unknown>
  session: string
}

// ─── Trade Decision ───────────────────────────────────────────────────────────
export type DecisionType = 'EXECUTE' | 'REJECT' | 'DEFER'

export interface TradeDecision {
  id: number
  timestamp: number
  decision: DecisionType
  reason: string
  trade_id?: string
  strategy_id?: string
  explanation: {
    strategy_hash?: string
    regime?: string
    risk_score?: number
    quality_score?: number
    direction?: string
    entry_price?: number
    sl_price?: number
    tp1_price?: number
    tp2_price?: number
    lot_size?: number
    session?: string
    why_executed?: string
    risk_reason?: string
    psych_reason?: string
    confidence_score?: number
    fundamental_events?: unknown[]
    consecutive_losses?: number
    account_equity?: number
    current_drawdown_pct?: number
    [key: string]: unknown
  }
}

// ─── Dashboard / Bot ─────────────────────────────────────────────────────────
export type BotMode = 'backtest' | 'paper' | 'live'

export interface BotStatus {
  running: boolean
  mode: BotMode | string
  emergency_stopped: boolean
  uptime_seconds: number
  paused?: boolean
  current_session?: string
  learning_enabled?: boolean
  maintenance_mode?: boolean
  pid?: number | null
}

export interface AccountInfo {
  balance: number
  equity: number
  margin_level?: number
  floating_pnl: number
  daily_pnl: number
  weekly_pnl: number
  monthly_pnl: number
  open_positions?: number
  total_trades_today?: number
}

export interface TradeRecord {
  id: string | number
  symbol: string
  direction: 'long' | 'short' | 'BUY' | 'SELL'
  lots: number
  entry_price: number
  current_price?: number
  sl_price?: number
  tp1_price?: number
  tp2_price?: number
  pnl?: number
  pnl_r?: number
  open_time?: string
  close_time?: string
  state?: string
  close_reason?: string
  outcome?: 'WIN' | 'LOSS' | 'BE'
}

export interface DashboardSnapshot {
  bot_status: BotStatus
  account_info: AccountInfo
  open_trades: TradeRecord[]
  timestamp: number
}

// ─── VPS ─────────────────────────────────────────────────────────────────────
export interface VPSStats {
  cpu_pct: number
  memory_pct: number
  disk_pct: number
  network_mb_in?: number
  network_mb_out?: number
  uptime_seconds: number
  load_avg?: number[]
}

export interface ServiceStatus {
  name: string
  status: 'active' | 'inactive' | 'failed' | 'unknown'
  pid?: number
  uptime?: string
  memory_mb?: number
}

// ─── Logs ────────────────────────────────────────────────────────────────────
export type LogLevel = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL'

export interface LogEntry {
  id?: number
  timestamp: string
  level: LogLevel
  source: string
  message: string
  extra?: Record<string, unknown>
}

// ─── WebSocket ───────────────────────────────────────────────────────────────
export type WSMessageType = 'dashboard' | 'bot_status' | 'trade_update' | 'log' | 'pong' | 'error'

export interface WSMessage {
  type: WSMessageType
  data?: unknown
  message?: string
}

// ─── Analytics ───────────────────────────────────────────────────────────────
export interface EquityPoint { timestamp: string; equity: number; drawdown?: number }
export interface DailyReturn { date: string; pnl: number; pct: number }

export interface AnalyticsOverview {
  total_return_pct: number
  total_pnl: number
  win_rate: number
  profit_factor: number
  sharpe_ratio: number
  max_drawdown_pct: number
  total_trades: number
  avg_rr: number
  expectancy: number
  best_trade: number
  worst_trade: number
  avg_win: number
  avg_loss: number
}
