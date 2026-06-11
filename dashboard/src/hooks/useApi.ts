'use client'

import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryResult,
  type UseMutationResult,
} from '@tanstack/react-query'
import { apiClient } from '@/lib/api'
import type {
  DashboardSnapshot,
  AgentId,
  AgentState,
  StrategyStatus,
  StrategyCandidate,
  MarketIntel,
  TradeDecision,
  TradeRecord,
  VPSStats,
} from '@/types'

// ─── Query key constants ──────────────────────────────────────────────────────

export const QUERY_KEYS = {
  dashboard: ['dashboard'] as const,
  allAgents: ['agents'] as const,
  agentStatus: (id: AgentId) => ['agents', id] as const,
  agentMetrics: (id: AgentId) => ['agents', id, 'metrics'] as const,
  strategies: (status?: StrategyStatus) => ['strategies', status ?? 'all'] as const,
  latestIntel: ['intel', 'latest'] as const,
  intelHistory: (limit?: number) => ['intel', 'history', limit] as const,
  recentDecisions: (limit?: number) => ['decisions', limit] as const,
  openTrades: ['trades', 'open'] as const,
  vpsStats: ['vps', 'stats'] as const,
  services: ['vps', 'services'] as const,
  analyticsOverview: ['analytics', 'overview'] as const,
  equityCurve: ['analytics', 'equity-curve'] as const,
  config: ['config'] as const,
  learningStats: ['learning', 'stats'] as const,
  botStatus: ['bot', 'status'] as const,
} as const

// ─── Query hooks ──────────────────────────────────────────────────────────────

export function useDashboard(): UseQueryResult<DashboardSnapshot> {
  return useQuery({
    queryKey: QUERY_KEYS.dashboard,
    queryFn: () => apiClient.getDashboard(),
    refetchInterval: 15_000,
    staleTime: 10_000,
  })
}

export function useAllAgents(): UseQueryResult<AgentState[]> {
  return useQuery({
    queryKey: QUERY_KEYS.allAgents,
    queryFn: () => apiClient.getAllAgentStatus(),
    select: (data) => Object.values(data),
    refetchInterval: 30_000,
    staleTime: 20_000,
  })
}

export function useAgentStatus(id: AgentId): UseQueryResult<AgentState> {
  return useQuery({
    queryKey: QUERY_KEYS.agentStatus(id),
    queryFn: () => apiClient.getAgentStatus(id),
    refetchInterval: 10_000,
    staleTime: 8_000,
  })
}

export function useStrategies(
  status?: StrategyStatus,
  limit?: number,
): UseQueryResult<StrategyCandidate[]> {
  return useQuery({
    queryKey: QUERY_KEYS.strategies(status),
    queryFn: () => apiClient.getStrategyCandidates(status, limit),
    staleTime: 30_000,
  })
}

export function useLatestIntel(): UseQueryResult<MarketIntel> {
  return useQuery({
    queryKey: QUERY_KEYS.latestIntel,
    queryFn: () => apiClient.getLatestIntel(),
    refetchInterval: 60_000,
    staleTime: 50_000,
  })
}

export function useRecentDecisions(
  limit = 50,
): UseQueryResult<TradeDecision[]> {
  return useQuery({
    queryKey: QUERY_KEYS.recentDecisions(limit),
    queryFn: () => apiClient.getRecentDecisions(limit),
    refetchInterval: 30_000,
    staleTime: 20_000,
  })
}

export function useOpenTrades(): UseQueryResult<TradeRecord[]> {
  return useQuery({
    queryKey: QUERY_KEYS.openTrades,
    queryFn: () => apiClient.getOpenTrades(),
    refetchInterval: 15_000,
    staleTime: 10_000,
  })
}

export function useVPSStats(): UseQueryResult<VPSStats> {
  return useQuery({
    queryKey: QUERY_KEYS.vpsStats,
    queryFn: () => apiClient.getVPSStats(),
    refetchInterval: 30_000,
    staleTime: 20_000,
  })
}

export function useBotStatus() {
  return useQuery({
    queryKey: QUERY_KEYS.botStatus,
    queryFn: () => apiClient.getBotStatus(),
    refetchInterval: 15_000,
    staleTime: 10_000,
  })
}

export function useAnalyticsOverview() {
  return useQuery({
    queryKey: QUERY_KEYS.analyticsOverview,
    queryFn: () => apiClient.getAnalyticsOverview(),
    staleTime: 60_000,
  })
}

export function useEquityCurve() {
  return useQuery({
    queryKey: QUERY_KEYS.equityCurve,
    queryFn: () => apiClient.getEquityCurve(),
    staleTime: 60_000,
  })
}

// ─── Mutation hooks ───────────────────────────────────────────────────────────

export function useControlAgent(): UseMutationResult<
  void,
  Error,
  { id: AgentId; command: 'start' | 'pause' | 'resume' | 'stop' | 'restart' }
> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, command }) => apiClient.controlAgent(id, command),
    onSuccess: (_data, { id }) => {
      void qc.invalidateQueries({ queryKey: QUERY_KEYS.agentStatus(id) })
      void qc.invalidateQueries({ queryKey: QUERY_KEYS.allAgents })
    },
  })
}

export function usePromoteStrategy(): UseMutationResult<void, Error, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (hash: string) => apiClient.promoteStrategy(hash),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['strategies'] })
    },
  })
}

export function useRejectStrategy(): UseMutationResult<void, Error, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (hash: string) => apiClient.rejectStrategy(hash),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['strategies'] })
    },
  })
}

export function useBotControl(): UseMutationResult<
  void,
  Error,
  'start' | 'stop' | 'restart' | 'pause' | 'resume' | 'emergency-stop'
> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (command) => {
      switch (command) {
        case 'start':
          return apiClient.startBot()
        case 'stop':
          return apiClient.stopBot()
        case 'restart':
          return apiClient.restartBot()
        case 'pause':
          return apiClient.pauseBot()
        case 'resume':
          return apiClient.resumeBot()
        case 'emergency-stop':
          return apiClient.emergencyStop()
      }
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: QUERY_KEYS.botStatus })
      void qc.invalidateQueries({ queryKey: QUERY_KEYS.dashboard })
    },
  })
}
