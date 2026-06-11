import type {
  LoginRequest,
  AuthTokens,
  UserProfile,
  DashboardSnapshot,
  BotStatus,
  AgentId,
  AgentState,
  StrategyStatus,
  StrategyCandidate,
  MarketIntel,
  TradeDecision,
  TradeRecord,
  AnalyticsOverview,
  EquityPoint,
  VPSStats,
  ServiceStatus,
  LogEntry,
} from '@/types'

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8443'

// ─── Error type ──────────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly detail?: unknown,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

// ─── Storage helpers ─────────────────────────────────────────────────────────

const STORAGE_KEYS = {
  ACCESS_TOKEN: 'xau_access_token',
  REFRESH_TOKEN: 'xau_refresh_token',
} as const

function readStorage(key: string): string | null {
  if (typeof window === 'undefined') return null
  return window.localStorage.getItem(key)
}

function writeStorage(key: string, value: string): void {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(key, value)
}

function removeStorage(key: string): void {
  if (typeof window === 'undefined') return
  window.localStorage.removeItem(key)
}

// ─── Core client ─────────────────────────────────────────────────────────────

class ApiClient {
  private _accessToken: string | null = null
  private _refreshing = false

  constructor(private readonly baseUrl: string) {}

  // ── Token management ────────────────────────────────────────────────────

  setToken(token: string): void {
    this._accessToken = token
    writeStorage(STORAGE_KEYS.ACCESS_TOKEN, token)
  }

  setRefreshToken(token: string): void {
    writeStorage(STORAGE_KEYS.REFRESH_TOKEN, token)
  }

  clearToken(): void {
    this._accessToken = null
    removeStorage(STORAGE_KEYS.ACCESS_TOKEN)
    removeStorage(STORAGE_KEYS.REFRESH_TOKEN)
  }

  getAccessToken(): string | null {
    if (this._accessToken) return this._accessToken
    const stored = readStorage(STORAGE_KEYS.ACCESS_TOKEN)
    if (stored) this._accessToken = stored
    return stored
  }

  getRefreshToken(): string | null {
    return readStorage(STORAGE_KEYS.REFRESH_TOKEN)
  }

  // ── Low-level fetch ──────────────────────────────────────────────────────

  private buildHeaders(extra?: Record<string, string>): Record<string, string> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...extra,
    }
    const token = this.getAccessToken()
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }
    return headers
  }

  private async parseError(res: Response): Promise<ApiError> {
    let detail: unknown
    let message = `HTTP ${res.status}`
    try {
      const body = await res.json()
      detail = body
      if (typeof body?.detail === 'string') {
        message = body.detail
      } else if (typeof body?.message === 'string') {
        message = body.message
      }
    } catch {
      // ignore
    }
    return new ApiError(res.status, message, detail)
  }

  private async fetchWithAuth<T>(
    path: string,
    init: RequestInit,
    isRetry = false,
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`
    const res = await fetch(url, {
      ...init,
      headers: this.buildHeaders(init.headers as Record<string, string>),
    })

    if (res.status === 401 && !isRetry && !this._refreshing) {
      // Attempt token refresh
      const refreshed = await this.tryRefresh()
      if (refreshed) {
        return this.fetchWithAuth<T>(path, init, true)
      }
      // Refresh failed — fire event and throw
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('auth:expired'))
      }
      throw new ApiError(401, 'Session expired. Please log in again.')
    }

    if (!res.ok) {
      throw await this.parseError(res)
    }

    // Handle empty responses (204 No Content, etc.)
    const contentType = res.headers.get('content-type') ?? ''
    if (res.status === 204 || !contentType.includes('application/json')) {
      return undefined as unknown as T
    }

    return res.json() as Promise<T>
  }

  private async tryRefresh(): Promise<boolean> {
    const refreshToken = this.getRefreshToken()
    if (!refreshToken) return false
    this._refreshing = true
    try {
      const url = `${this.baseUrl}/api/v1/auth/refresh`
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      })
      if (!res.ok) return false
      const tokens: AuthTokens = await res.json()
      this.setToken(tokens.access_token)
      if (tokens.refresh_token) {
        this.setRefreshToken(tokens.refresh_token)
      }
      return true
    } catch {
      return false
    } finally {
      this._refreshing = false
    }
  }

  // ── HTTP verbs ──────────────────────────────────────────────────────────

  async get<T>(path: string, params?: Record<string, unknown>): Promise<T> {
    let url = path
    if (params && Object.keys(params).length > 0) {
      const qs = new URLSearchParams(
        Object.entries(params)
          .filter(([, v]) => v !== undefined && v !== null)
          .map(([k, v]) => [k, String(v)]),
      ).toString()
      url = `${path}?${qs}`
    }
    return this.fetchWithAuth<T>(url, { method: 'GET' })
  }

  async post<T>(path: string, body?: unknown): Promise<T> {
    return this.fetchWithAuth<T>(path, {
      method: 'POST',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  }

  async put<T>(path: string, body?: unknown): Promise<T> {
    return this.fetchWithAuth<T>(path, {
      method: 'PUT',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  }

  async del<T>(path: string): Promise<T> {
    return this.fetchWithAuth<T>(path, { method: 'DELETE' })
  }

  // ── Auth ────────────────────────────────────────────────────────────────

  async login(req: LoginRequest): Promise<AuthTokens> {
    const url = `${this.baseUrl}/api/v1/auth/login`
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: req.username, password: req.password }),
    })
    if (!res.ok) {
      throw await this.parseError(res)
    }
    const tokens: AuthTokens = await res.json()
    this.setToken(tokens.access_token)
    if (tokens.refresh_token) {
      this.setRefreshToken(tokens.refresh_token)
    }
    return tokens
  }

  async getMe(): Promise<UserProfile> {
    return this.get<UserProfile>('/api/v1/auth/me')
  }

  // ── Dashboard ───────────────────────────────────────────────────────────

  async getDashboard(): Promise<DashboardSnapshot> {
    return this.get<DashboardSnapshot>('/api/v1/dashboard/snapshot')
  }

  // ── Bot control ─────────────────────────────────────────────────────────

  async getBotStatus(): Promise<BotStatus> {
    return this.get<BotStatus>('/api/v1/bot/status')
  }

  async startBot(): Promise<void> {
    const r = await this.post<{ success: boolean; message?: string }>('/api/v1/bot/start')
    if (r && !r.success) throw new ApiError(422, r.message ?? 'Bot failed to start')
  }

  async stopBot(): Promise<void> {
    const r = await this.post<{ success: boolean; message?: string }>('/api/v1/bot/stop')
    if (r && !r.success) throw new ApiError(422, r.message ?? 'Bot failed to stop')
  }

  async restartBot(): Promise<void> {
    const r = await this.post<{ success: boolean; message?: string }>('/api/v1/bot/restart')
    if (r && !r.success) throw new ApiError(422, r.message ?? 'Bot failed to restart')
  }

  async pauseBot(): Promise<void> {
    return this.post<void>('/api/v1/bot/pause')
  }

  async resumeBot(): Promise<void> {
    return this.post<void>('/api/v1/bot/resume')
  }

  async emergencyStop(): Promise<void> {
    return this.post<void>('/api/v1/bot/emergency-stop')
  }

  // ── Agents ──────────────────────────────────────────────────────────────

  async getAllAgentStatus(): Promise<Record<string, AgentState>> {
    return this.get<Record<string, AgentState>>('/api/v1/agents/status')
  }

  async getAgentStatus(id: AgentId): Promise<AgentState> {
    return this.get<AgentState>(`/api/v1/agents/${id}/status`)
  }

  async getAgentMetrics(id: AgentId): Promise<Record<string, unknown>> {
    return this.get<Record<string, unknown>>(`/api/v1/agents/${id}/metrics`)
  }

  async controlAgent(
    id: AgentId,
    command: 'start' | 'pause' | 'resume' | 'stop' | 'restart',
  ): Promise<void> {
    return this.post<void>(`/api/v1/agents/${id}/${command}`)
  }

  // ── Strategies ──────────────────────────────────────────────────────────

  async getStrategyCandidates(
    status?: StrategyStatus,
    limit?: number,
  ): Promise<StrategyCandidate[]> {
    return this.get<StrategyCandidate[]>('/api/v1/agents/strategies/candidates', { status, limit })
  }

  async getValidatedStrategies(limit?: number): Promise<StrategyCandidate[]> {
    return this.get<StrategyCandidate[]>('/api/v1/agents/strategies/validated', { limit })
  }

  async promoteStrategy(hash: string): Promise<void> {
    return this.post<void>(`/api/v1/agents/strategies/${hash}/promote`)
  }

  async rejectStrategy(hash: string): Promise<void> {
    return this.post<void>(`/api/v1/agents/strategies/${hash}/reject`)
  }

  // ── Market Intel ────────────────────────────────────────────────────────

  async getLatestIntel(): Promise<MarketIntel> {
    return this.get<MarketIntel>('/api/v1/agents/intelligence/latest')
  }

  async getIntelHistory(limit?: number): Promise<MarketIntel[]> {
    return this.get<MarketIntel[]>('/api/v1/agents/intelligence/history', { limit })
  }

  // ── Trade Decisions ─────────────────────────────────────────────────────

  async getRecentDecisions(limit?: number): Promise<TradeDecision[]> {
    return this.get<TradeDecision[]>('/api/v1/agents/decisions/recent', { limit })
  }

  // ── Trades ──────────────────────────────────────────────────────────────

  async getOpenTrades(): Promise<TradeRecord[]> {
    return this.get<TradeRecord[]>('/api/v1/trades/open')
  }

  async getTradeHistory(
    page?: number,
    limit?: number,
  ): Promise<{ trades: TradeRecord[]; total: number }> {
    return this.get<{ trades: TradeRecord[]; total: number }>(
      '/api/v1/trades/history',
      { page, limit },
    )
  }

  // ── Analytics ───────────────────────────────────────────────────────────

  async getAnalyticsOverview(): Promise<AnalyticsOverview> {
    return this.get<AnalyticsOverview>('/api/v1/analytics/overview')
  }

  async getEquityCurve(): Promise<EquityPoint[]> {
    return this.get<EquityPoint[]>('/api/v1/analytics/equity-curve')
  }

  // ── VPS ─────────────────────────────────────────────────────────────────

  async getVPSStats(): Promise<VPSStats> {
    return this.get<VPSStats>('/api/v1/vps/stats')
  }

  async getServices(): Promise<ServiceStatus[]> {
    return this.get<ServiceStatus[]>('/api/v1/vps/services')
  }

  // ── Logs ────────────────────────────────────────────────────────────────

  async getLogs(params: {
    type?: string
    level?: string
    search?: string
    page?: number
    limit?: number
  }): Promise<{ logs: LogEntry[]; total: number }> {
    const { limit, ...rest } = params
    return this.get<{ logs: LogEntry[]; total: number }>('/api/v1/logs', {
      ...rest,
      ...(limit !== undefined ? { page_size: limit } : {}),
    })
  }

  // ── Config ──────────────────────────────────────────────────────────────

  async getConfig(): Promise<Record<string, unknown>> {
    return this.get<Record<string, unknown>>('/api/v1/config/raw')
  }

  async updateConfigField(path: string, value: unknown): Promise<void> {
    return this.put<void>('/api/v1/config/field', { path, value })
  }

  // ── Learning ────────────────────────────────────────────────────────────

  async getLearningStats(): Promise<Record<string, unknown>> {
    return this.get<Record<string, unknown>>('/api/v1/learning/stats')
  }

  async getLearningEvents(limit?: number): Promise<unknown[]> {
    return this.get<unknown[]>('/api/v1/learning/events', { limit })
  }
}

// ─── Singleton export ─────────────────────────────────────────────────────────

export const apiClient = new ApiClient(BASE_URL)
