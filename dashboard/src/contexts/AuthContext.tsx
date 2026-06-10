'use client'

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from 'react'
import { apiClient } from '@/lib/api'
import { wsClient } from '@/lib/ws'
import type { UserProfile, LoginRequest, AuthTokens } from '@/types'

// ─── Context types ────────────────────────────────────────────────────────────

interface AuthContextValue {
  user: UserProfile | null
  token: string | null
  isAuthenticated: boolean
  loading: boolean
  login: (req: LoginRequest) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

// ─── Provider ─────────────────────────────────────────────────────────────────

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const logout = useCallback(() => {
    apiClient.clearToken()
    wsClient.disconnect()
    setUser(null)
    setToken(null)
  }, [])

  // On mount: restore session from localStorage
  useEffect(() => {
    const stored = apiClient.getAccessToken()
    if (!stored) {
      setLoading(false)
      return
    }

    setToken(stored)

    // 8-second deadline — if the API is unreachable, clear the token and show login
    const deadline = new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error('auth_timeout')), 8_000),
    )

    Promise.race([apiClient.getMe(), deadline])
      .then((profile) => {
        setUser(profile)
        wsClient.connect(stored)
      })
      .catch(() => {
        apiClient.clearToken()
        setToken(null)
      })
      .finally(() => setLoading(false))
  }, [])

  // Listen for auth:expired event dispatched by ApiClient on failed refresh
  useEffect(() => {
    const handler = () => logout()
    window.addEventListener('auth:expired', handler)
    return () => window.removeEventListener('auth:expired', handler)
  }, [logout])

  const login = useCallback(async (req: LoginRequest): Promise<void> => {
    const tokens: AuthTokens = await apiClient.login(req)
    const accessToken = tokens.access_token
    setToken(accessToken)

    // Fetch profile immediately after login
    const profile = await apiClient.getMe()
    setUser(profile)

    // Open WebSocket connection
    wsClient.connect(accessToken)
  }, [])

  const value: AuthContextValue = {
    user,
    token,
    isAuthenticated: !!user && !!token,
    loading,
    login,
    logout,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth must be used inside <AuthProvider>')
  }
  return ctx
}
