'use client'

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react'
import { wsClient } from '@/lib/ws'
import type { WSMessage, DashboardSnapshot, BotStatus } from '@/types'

// ─── Context types ────────────────────────────────────────────────────────────

type WSConnectionState = 'disconnected' | 'connecting' | 'connected' | 'reconnecting'

interface WebSocketContextValue {
  connectionState: WSConnectionState
  lastMessage: WSMessage | null
  dashboard: DashboardSnapshot | null
  botStatus: BotStatus | null
  subscribe: (handler: (msg: WSMessage) => void) => () => void
}

const WebSocketContext = createContext<WebSocketContextValue | null>(null)

// ─── Provider ─────────────────────────────────────────────────────────────────

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const [connectionState, setConnectionState] = useState<WSConnectionState>('disconnected')
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null)
  const [dashboard, setDashboard] = useState<DashboardSnapshot | null>(null)
  const [botStatus, setBotStatus] = useState<BotStatus | null>(null)
  const handlersRef = useRef<Set<(msg: WSMessage) => void>>(new Set())

  useEffect(() => {
    const handler = (msg: WSMessage) => {
      // Handle internal state-change synthetic messages from wsClient
      if (msg.type === 'error' && typeof msg.message === 'string') {
        if (msg.message === 'ws:connected') {
          setConnectionState('connected')
          return
        }
        if (msg.message === 'ws:disconnected') {
          setConnectionState('disconnected')
          return
        }
        if (msg.message === 'ws:reconnecting') {
          setConnectionState('reconnecting')
          return
        }
      }

      setLastMessage(msg)

      // Update derived state from message types
      if (msg.type === 'dashboard' && msg.data) {
        setDashboard(msg.data as DashboardSnapshot)
        setBotStatus((msg.data as DashboardSnapshot).bot_status)
      } else if (msg.type === 'bot_status' && msg.data) {
        setBotStatus(msg.data as BotStatus)
      }

      // Forward to external subscribers
      handlersRef.current.forEach((h) => {
        try {
          h(msg)
        } catch (err) {
          console.error('[WebSocketContext] subscriber error:', err)
        }
      })
    }

    wsClient.onMessage(handler)
    // Sync initial state
    setConnectionState(wsClient.state as WSConnectionState)

    return () => {
      wsClient.off(handler)
    }
  }, [])

  const subscribe = useCallback((handler: (msg: WSMessage) => void) => {
    handlersRef.current.add(handler)
    return () => {
      handlersRef.current.delete(handler)
    }
  }, [])

  const value: WebSocketContextValue = {
    connectionState,
    lastMessage,
    dashboard,
    botStatus,
    subscribe,
  }

  return (
    <WebSocketContext.Provider value={value}>
      {children}
    </WebSocketContext.Provider>
  )
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useWebSocketContext(): WebSocketContextValue {
  const ctx = useContext(WebSocketContext)
  if (!ctx) {
    throw new Error('useWebSocketContext must be used inside <WebSocketProvider>')
  }
  return ctx
}
