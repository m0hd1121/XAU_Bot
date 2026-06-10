'use client'

import { useWebSocketContext } from '@/contexts/WebSocketContext'
import type { DashboardSnapshot, BotStatus, WSMessage } from '@/types'

interface UseWebSocketReturn {
  state: 'disconnected' | 'connecting' | 'connected' | 'reconnecting'
  lastMessage: WSMessage | null
  dashboard: DashboardSnapshot | null
  botStatus: BotStatus | null
}

/**
 * Convenience hook that exposes WebSocket connection state and the latest
 * dashboard/bot-status snapshots received over the live feed.
 */
export function useWebSocket(): UseWebSocketReturn {
  const { connectionState, lastMessage, dashboard, botStatus } =
    useWebSocketContext()

  return {
    state: connectionState,
    lastMessage,
    dashboard,
    botStatus,
  }
}
