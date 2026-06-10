'use client'

import { useCallback } from 'react'
import { useAllAgents, useControlAgent } from './useApi'
import type { AgentId, AgentState } from '@/types'

interface UseAgentsReturn {
  agents: AgentState[]
  loading: boolean
  error: Error | null
  pauseAgent: (id: AgentId) => Promise<void>
  resumeAgent: (id: AgentId) => Promise<void>
  stopAgent: (id: AgentId) => Promise<void>
  restartAgent: (id: AgentId) => Promise<void>
  isActionPending: boolean
}

/**
 * Combined hook for agent list + control operations.
 * Provides convenience methods that wrap the generic controlAgent mutation.
 */
export function useAgents(): UseAgentsReturn {
  const {
    data: agents,
    isLoading: loading,
    error,
  } = useAllAgents()

  const { mutateAsync: controlAgent, isPending: isActionPending } =
    useControlAgent()

  const pauseAgent = useCallback(
    (id: AgentId) => controlAgent({ id, command: 'pause' }),
    [controlAgent],
  )

  const resumeAgent = useCallback(
    (id: AgentId) => controlAgent({ id, command: 'resume' }),
    [controlAgent],
  )

  const stopAgent = useCallback(
    (id: AgentId) => controlAgent({ id, command: 'stop' }),
    [controlAgent],
  )

  const restartAgent = useCallback(
    (id: AgentId) => controlAgent({ id, command: 'restart' }),
    [controlAgent],
  )

  return {
    agents: agents ?? [],
    loading,
    error: error as Error | null,
    pauseAgent,
    resumeAgent,
    stopAgent,
    restartAgent,
    isActionPending,
  }
}
