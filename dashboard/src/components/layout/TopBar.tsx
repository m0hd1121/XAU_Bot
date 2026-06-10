'use client'

import React, { useEffect, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { Sun, Moon, LogOut, ChevronDown } from 'lucide-react'
import { useAuth } from '@/contexts/AuthContext'
import { useWebSocket } from '@/hooks/useWebSocket'
import { cn } from '@/lib/utils'

// ─── Page title map ───────────────────────────────────────────────────────────

function getPageTitle(pathname: string): string {
  if (pathname === '/dashboard') return 'Dashboard'
  if (pathname.startsWith('/agents/agent1')) return 'Agent 1 — Research'
  if (pathname.startsWith('/agents/agent2')) return 'Agent 2 — Intelligence'
  if (pathname.startsWith('/agents/agent3')) return 'Agent 3 — Trader'
  if (pathname.startsWith('/agents')) return 'Agents'
  if (pathname.startsWith('/strategies')) return 'Strategies'
  if (pathname.startsWith('/activity')) return 'Activity'
  if (pathname.startsWith('/explainability')) return 'Explainability'
  if (pathname.startsWith('/config')) return 'Configuration'
  if (pathname.startsWith('/logs')) return 'Logs'
  if (pathname.startsWith('/notifications')) return 'Notifications'
  return 'XAU Control Center'
}

// ─── WS indicator ─────────────────────────────────────────────────────────────

type WSState = 'disconnected' | 'connecting' | 'connected' | 'reconnecting'

function WSIndicator({ state }: { state: WSState }) {
  const config: Record<WSState, { dot: string; label: string; pulse: boolean }> = {
    connected: {
      dot: 'bg-emerald-500',
      label: 'Live',
      pulse: true,
    },
    reconnecting: {
      dot: 'bg-amber-400',
      label: 'Reconnecting',
      pulse: true,
    },
    connecting: {
      dot: 'bg-amber-400',
      label: 'Connecting',
      pulse: true,
    },
    disconnected: {
      dot: 'bg-zinc-500',
      label: 'Offline',
      pulse: false,
    },
  }

  const { dot, label, pulse } = config[state]

  return (
    <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-zinc-800 border border-zinc-700">
      <span
        className={cn('w-1.5 h-1.5 rounded-full flex-shrink-0', dot, pulse && 'animate-pulse')}
      />
      <span className="text-xs text-zinc-400 font-medium">{label}</span>
    </div>
  )
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function TopBar() {
  const pathname = usePathname()
  const router = useRouter()
  const { user, logout } = useAuth()
  const { state: wsState } = useWebSocket()

  const [isDark, setIsDark] = useState(true)
  const [userMenuOpen, setUserMenuOpen] = useState(false)

  // Sync theme on mount
  useEffect(() => {
    const dark = document.documentElement.classList.contains('dark')
    setIsDark(dark)
  }, [])

  function toggleTheme() {
    const html = document.documentElement
    const willBeDark = !isDark
    html.classList.toggle('dark', willBeDark)
    html.classList.toggle('light', !willBeDark)
    setIsDark(willBeDark)
    if (typeof window !== 'undefined') {
      window.localStorage.setItem('theme', willBeDark ? 'dark' : 'light')
    }
  }

  function handleLogout() {
    logout()
    router.push('/login')
  }

  const pageTitle = getPageTitle(pathname)

  return (
    <header className="flex-shrink-0 h-12 bg-zinc-900 border-b border-zinc-800 flex items-center px-4 gap-4 z-10">
      {/* Page title */}
      <div className="flex-1 min-w-0">
        <h2 className="text-sm font-medium text-zinc-200 truncate">{pageTitle}</h2>
      </div>

      {/* Right controls */}
      <div className="flex items-center gap-2">
        {/* WS indicator */}
        <WSIndicator state={wsState} />

        {/* Theme toggle */}
        <button
          onClick={toggleTheme}
          title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
          className="w-7 h-7 flex items-center justify-center rounded-lg text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
        >
          {isDark ? <Sun className="w-3.5 h-3.5" /> : <Moon className="w-3.5 h-3.5" />}
        </button>

        {/* User menu */}
        <div className="relative">
          <button
            onClick={() => setUserMenuOpen((v) => !v)}
            className="flex items-center gap-1.5 px-2 py-1 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
          >
            <div className="w-5 h-5 rounded-full bg-amber-500/20 border border-amber-500/30 flex items-center justify-center">
              <span className="text-amber-400 text-[10px] font-bold uppercase">
                {user?.username?.charAt(0) ?? 'U'}
              </span>
            </div>
            <span className="text-xs font-medium hidden sm:block">{user?.username}</span>
            <ChevronDown className="w-3 h-3" />
          </button>

          {userMenuOpen && (
            <>
              {/* Backdrop */}
              <div
                className="fixed inset-0 z-10"
                onClick={() => setUserMenuOpen(false)}
              />
              {/* Dropdown */}
              <div className="absolute right-0 top-full mt-1 w-44 bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl z-20 overflow-hidden">
                <div className="px-3 py-2 border-b border-zinc-800">
                  <p className="text-xs font-medium text-zinc-300">{user?.username}</p>
                  <p className="text-[10px] text-zinc-600 capitalize">{user?.role}</p>
                </div>
                <button
                  onClick={() => {
                    setUserMenuOpen(false)
                    handleLogout()
                  }}
                  className="w-full flex items-center gap-2 px-3 py-2 text-xs text-zinc-400 hover:text-red-400 hover:bg-zinc-800 transition-colors"
                >
                  <LogOut className="w-3.5 h-3.5" />
                  Sign out
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  )
}
