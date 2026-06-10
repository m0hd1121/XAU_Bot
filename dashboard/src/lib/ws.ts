import type { WSMessage } from '@/types'

type WSState = 'disconnected' | 'connecting' | 'connected' | 'reconnecting'
type MessageHandler = (msg: WSMessage) => void

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8443'

const INITIAL_RECONNECT_DELAY = 1_000   // 1s
const MAX_RECONNECT_DELAY    = 30_000   // 30s
const PING_INTERVAL          = 20_000   // 20s

class WSClient {
  private socket: WebSocket | null = null
  private handlers: Set<MessageHandler> = new Set()
  private _state: WSState = 'disconnected'
  private reconnectDelay = INITIAL_RECONNECT_DELAY
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private pingTimer: ReturnType<typeof setInterval> | null = null
  private _token: string | null = null
  private _explicitDisconnect = false

  // ── State ──────────────────────────────────────────────────────────────

  get state(): WSState {
    return this._state
  }

  private setState(s: WSState): void {
    this._state = s
    // Notify any state-change handlers via a synthetic message
    if (s === 'connected' || s === 'disconnected' || s === 'reconnecting') {
      this.emit({ type: 'error', message: `ws:${s}` })
    }
  }

  // ── Connection ──────────────────────────────────────────────────────────

  connect(token: string): void {
    this._token = token
    this._explicitDisconnect = false

    if (
      this.socket &&
      (this.socket.readyState === WebSocket.OPEN ||
        this.socket.readyState === WebSocket.CONNECTING)
    ) {
      return
    }

    this.openSocket()
  }

  disconnect(): void {
    this._explicitDisconnect = true
    this.clearTimers()
    if (this.socket) {
      this.socket.close(1000, 'Client disconnect')
      this.socket = null
    }
    this._state = 'disconnected'
  }

  private openSocket(): void {
    if (!this._token) return

    this._state = 'connecting'

    // Derive ws/wss URL from API base URL
    const wsBase = BASE_URL
      .replace(/^https:\/\//, 'wss://')
      .replace(/^http:\/\//, 'ws://')
      .replace(/\/$/, '')

    const url = `${wsBase}/api/v1/ws/live`

    try {
      this.socket = new WebSocket(url)
    } catch (err) {
      console.error('[WSClient] Failed to create WebSocket:', err)
      this.scheduleReconnect()
      return
    }

    this.socket.onopen = () => {
      this._state = 'connected'
      this.reconnectDelay = INITIAL_RECONNECT_DELAY

      // Send auth frame immediately on open
      this.send({ type: 'auth', token: this._token! })

      // Start keepalive ping
      this.pingTimer = setInterval(() => {
        this.send({ type: 'ping' })
      }, PING_INTERVAL)
    }

    this.socket.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data as string) as WSMessage
        this.emit(msg)
      } catch {
        // non-JSON message — ignore
      }
    }

    this.socket.onerror = (err) => {
      console.error('[WSClient] WebSocket error:', err)
    }

    this.socket.onclose = (ev) => {
      this.clearPing()
      this._state = 'disconnected'

      if (!this._explicitDisconnect) {
        console.warn(`[WSClient] Connection closed (code ${ev.code}). Reconnecting…`)
        this.setState('reconnecting')
        this.scheduleReconnect()
      }
    }
  }

  private scheduleReconnect(): void {
    if (this._explicitDisconnect) return

    this.clearReconnectTimer()
    const delay = this.reconnectDelay
    this.reconnectDelay = Math.min(delay * 2, MAX_RECONNECT_DELAY)

    this.reconnectTimer = setTimeout(() => {
      if (!this._explicitDisconnect) {
        this.openSocket()
      }
    }, delay)
  }

  // ── Sending ────────────────────────────────────────────────────────────

  private send(payload: Record<string, unknown>): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(payload))
    }
  }

  // ── Listeners ──────────────────────────────────────────────────────────

  onMessage(handler: MessageHandler): void {
    this.handlers.add(handler)
  }

  off(handler: MessageHandler): void {
    this.handlers.delete(handler)
  }

  private emit(msg: WSMessage): void {
    this.handlers.forEach((h) => {
      try {
        h(msg)
      } catch (err) {
        console.error('[WSClient] Handler error:', err)
      }
    })
  }

  // ── Cleanup ────────────────────────────────────────────────────────────

  private clearTimers(): void {
    this.clearReconnectTimer()
    this.clearPing()
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }

  private clearPing(): void {
    if (this.pingTimer !== null) {
      clearInterval(this.pingTimer)
      this.pingTimer = null
    }
  }
}

// ─── Singleton export ─────────────────────────────────────────────────────────

export const wsClient = new WSClient()
