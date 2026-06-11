'use client'

import { useState, type FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'
import { ApiError } from '@/lib/api'
import Spinner from '@/components/ui/Spinner'

export default function LoginPage() {
  const router = useRouter()
  const { login, isAuthenticated } = useAuth()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // If already authenticated, redirect immediately
  if (isAuthenticated) {
    router.replace('/dashboard')
    return null
  }

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (!username.trim() || !password) return

    setLoading(true)
    setError(null)

    try {
      await login({ username: username.trim(), password })
      router.replace('/dashboard')
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message)
      } else if (err instanceof TypeError) {
        // "Failed to fetch" (Chrome) or "Load failed" (Safari) = network error
        const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8443'
        setError(`Cannot reach API server at ${apiUrl} — check firewall/port.`)
      } else {
        setError(err instanceof Error ? err.message : 'An unexpected error occurred.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-4">
      {/* Background gradient */}
      <div
        className="absolute inset-0 pointer-events-none"
        aria-hidden="true"
        style={{
          background:
            'radial-gradient(ellipse 80% 60% at 50% -20%, rgba(245,158,11,0.08) 0%, transparent 60%)',
        }}
      />

      <div className="relative w-full max-w-sm">
        {/* Logo / Brand */}
        <div className="flex flex-col items-center mb-8 gap-3">
          <div className="w-14 h-14 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center">
            <span className="text-amber-500 font-black text-2xl font-mono select-none">
              X
            </span>
          </div>
          <div className="text-center">
            <h1 className="text-xl font-semibold text-zinc-100 tracking-tight">
              XAU Control Center
            </h1>
            <p className="text-sm text-zinc-500 mt-1">
              Institutional Trading Platform
            </p>
          </div>
        </div>

        {/* Card */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 shadow-2xl">
          <h2 className="text-sm font-medium text-zinc-400 mb-5 text-center uppercase tracking-wider">
            Sign in to your account
          </h2>

          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            {/* Username */}
            <div className="space-y-1.5">
              <label
                htmlFor="username"
                className="block text-xs font-medium text-zinc-400"
              >
                Username
              </label>
              <input
                id="username"
                type="text"
                autoComplete="username"
                autoFocus
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                disabled={loading}
                className="
                  w-full px-3 py-2.5 text-sm
                  bg-zinc-800 border border-zinc-700 rounded-lg
                  text-zinc-100 placeholder-zinc-500
                  focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500/50
                  disabled:opacity-50 disabled:cursor-not-allowed
                  transition-colors
                "
                placeholder="admin"
                required
              />
            </div>

            {/* Password */}
            <div className="space-y-1.5">
              <label
                htmlFor="password"
                className="block text-xs font-medium text-zinc-400"
              >
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={loading}
                className="
                  w-full px-3 py-2.5 text-sm
                  bg-zinc-800 border border-zinc-700 rounded-lg
                  text-zinc-100 placeholder-zinc-500
                  focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500/50
                  disabled:opacity-50 disabled:cursor-not-allowed
                  transition-colors
                "
                placeholder="••••••••"
                required
              />
            </div>

            {/* Error */}
            {error && (
              <div className="flex items-start gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
                <svg
                  className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"
                  />
                </svg>
                <p className="text-sm text-red-400">{error}</p>
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={loading || !username.trim() || !password}
              className="
                w-full flex items-center justify-center gap-2
                px-4 py-2.5 mt-2
                bg-amber-500 hover:bg-amber-400 active:bg-amber-600
                text-zinc-950 font-semibold text-sm rounded-lg
                focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:ring-offset-2 focus:ring-offset-zinc-900
                disabled:opacity-50 disabled:cursor-not-allowed
                transition-colors
              "
            >
              {loading ? (
                <>
                  <Spinner size="sm" color="dark" />
                  <span>Signing in…</span>
                </>
              ) : (
                'Sign In'
              )}
            </button>
          </form>
        </div>

        {/* Footer */}
        <p className="text-center text-xs text-zinc-600 mt-6">
          XAU/USD Algorithmic Trading &mdash; Restricted Access
        </p>
      </div>
    </div>
  )
}
