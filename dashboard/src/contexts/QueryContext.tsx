'use client'

import React from 'react'
import {
  QueryClient,
  QueryClientProvider,
  QueryCache,
  MutationCache,
} from '@tanstack/react-query'
import { ApiError } from '@/lib/api'

function makeQueryClient(): QueryClient {
  return new QueryClient({
    queryCache: new QueryCache({
      onError: (error, query) => {
        if (error instanceof ApiError && error.status === 401) {
          // Auth errors are handled by ApiClient; no need to log here
          return
        }
        if (query.meta?.suppressError) return
        console.error(`[Query "${String(query.queryKey[0])}"] Error:`, error)
      },
    }),
    mutationCache: new MutationCache({
      onError: (error) => {
        if (error instanceof ApiError && error.status === 401) return
        console.error('[Mutation] Error:', error)
      },
    }),
    defaultOptions: {
      queries: {
        // Don't retry on 4xx client errors
        retry: (failureCount, error) => {
          if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
            return false
          }
          return failureCount < 2
        },
        refetchOnWindowFocus: false,
        staleTime: 10_000, // 10s default
      },
      mutations: {
        retry: false,
      },
    },
  })
}

// Singleton pattern for Next.js: create once outside of component tree
// so it isn't re-created on every render during SSR hydration
let browserQueryClient: QueryClient | undefined

function getQueryClient(): QueryClient {
  if (typeof window === 'undefined') {
    // Server: always make a new QueryClient
    return makeQueryClient()
  }
  if (!browserQueryClient) {
    browserQueryClient = makeQueryClient()
  }
  return browserQueryClient
}

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const queryClient = getQueryClient()
  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}
