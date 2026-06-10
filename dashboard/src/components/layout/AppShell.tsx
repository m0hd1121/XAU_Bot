'use client'

import React, { useState, useEffect } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'
import Sidebar from './Sidebar'
import TopBar from './TopBar'
import Spinner from '@/components/ui/Spinner'

const PUBLIC_PATHS = ['/login']
const SIDEBAR_STORAGE_KEY = 'sidebar_collapsed'

interface AppShellProps {
  children: React.ReactNode
}

export default function AppShell({ children }: AppShellProps) {
  const pathname = usePathname()
  const router = useRouter()
  const { isAuthenticated, loading } = useAuth()

  const [collapsed, setCollapsed] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false
    return window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === 'true'
  })

  const isPublicPath = PUBLIC_PATHS.some((p) => pathname.startsWith(p))

  // Persist sidebar state
  useEffect(() => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(SIDEBAR_STORAGE_KEY, String(collapsed))
    }
  }, [collapsed])

  // Guard protected routes
  useEffect(() => {
    if (loading) return
    if (!isAuthenticated && !isPublicPath) {
      router.push('/login')
    }
  }, [isAuthenticated, loading, isPublicPath, router])

  // While auth state is resolving, show full-screen spinner (only on protected paths)
  if (loading && !isPublicPath) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <Spinner size="lg" />
          <p className="text-zinc-500 text-sm">Connecting…</p>
        </div>
      </div>
    )
  }

  // Public pages (login) — render without shell
  if (isPublicPath || !isAuthenticated) {
    return <>{children}</>
  }

  return (
    <div className="flex h-screen overflow-hidden bg-zinc-950">
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed((c) => !c)} />

      <div className="flex flex-1 flex-col min-w-0 overflow-hidden">
        <TopBar />
        <main className="flex-1 overflow-y-auto">
          {children}
        </main>
      </div>
    </div>
  )
}
