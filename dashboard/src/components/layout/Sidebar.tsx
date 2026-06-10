'use client'

import React, { useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  LayoutDashboard,
  Bot,
  BarChart3,
  Activity,
  Eye,
  Settings,
  ScrollText,
  Bell,
  FlaskConical,
  Brain,
  TrendingUp,
  MessageSquare,
  Shield,
  ChevronDown,
  ChevronRight,
  PanelLeftClose,
  PanelLeftOpen,
  LogOut,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuth } from '@/contexts/AuthContext'

// ─── Nav item types ───────────────────────────────────────────────────────────

interface NavChild {
  icon: React.ElementType
  label: string
  href: string
}

interface NavItem {
  icon: React.ElementType
  label: string
  href: string
  children?: NavChild[]
}

const NAV_ITEMS: NavItem[] = [
  { icon: LayoutDashboard, label: 'Dashboard', href: '/dashboard' },
  {
    icon: Bot,
    label: 'Agents',
    href: '/agents',
    children: [
      { icon: FlaskConical, label: 'Agent 1 — Research', href: '/agents/agent1' },
      { icon: Brain, label: 'Agent 2 — Intel', href: '/agents/agent2' },
      { icon: TrendingUp, label: 'Agent 3 — Trader', href: '/agents/agent3' },
    ],
  },
  { icon: BarChart3, label: 'Strategies', href: '/strategies' },
  { icon: Activity, label: 'Activity', href: '/activity' },
  { icon: Eye, label: 'Explainability', href: '/explainability' },
  { icon: Settings, label: 'Configuration', href: '/config' },
  { icon: ScrollText, label: 'Logs', href: '/logs' },
  { icon: Bell, label: 'Notifications', href: '/notifications' },
  { icon: Brain, label: 'Learning', href: '/learning' },
  { icon: MessageSquare, label: 'Communication', href: '/communication' },
  { icon: Shield, label: 'Admin', href: '/admin' },
]

// ─── Props ────────────────────────────────────────────────────────────────────

interface SidebarProps {
  collapsed: boolean
  onToggle: () => void
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const pathname = usePathname()
  const { user, logout } = useAuth()
  const [agentsExpanded, setAgentsExpanded] = useState(
    pathname.startsWith('/agents'),
  )

  function isActive(href: string): boolean {
    if (href === '/dashboard') return pathname === '/dashboard'
    return pathname.startsWith(href)
  }

  return (
    <aside
      className={cn(
        'flex flex-col h-full bg-zinc-900 border-r border-zinc-800 transition-all duration-300 flex-shrink-0 z-20',
        collapsed ? 'w-16' : 'w-60',
      )}
    >
      {/* ── Logo ─────────────────────────────────────────────────────── */}
      <div
        className={cn(
          'flex items-center border-b border-zinc-800 flex-shrink-0',
          collapsed ? 'h-14 justify-center px-0' : 'h-14 gap-2.5 px-4',
        )}
      >
        <div className="w-8 h-8 rounded-lg bg-amber-500/15 border border-amber-500/30 flex items-center justify-center flex-shrink-0">
          <span className="text-amber-500 font-black text-base font-mono select-none leading-none">
            X
          </span>
        </div>
        {!collapsed && (
          <span className="text-zinc-100 font-semibold text-sm tracking-tight truncate">
            XAU Bot
          </span>
        )}
      </div>

      {/* ── Navigation ───────────────────────────────────────────────── */}
      <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-0.5">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon
          const active = isActive(item.href)
          const hasChildren = !!item.children?.length
          const expanded = hasChildren && agentsExpanded && !collapsed

          if (hasChildren) {
            return (
              <div key={item.href}>
                {/* Parent item */}
                <button
                  onClick={() => {
                    if (!collapsed) setAgentsExpanded((v) => !v)
                  }}
                  className={cn(
                    'w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-sm transition-colors duration-150',
                    active
                      ? 'bg-amber-500/10 text-amber-400 border-r-2 border-amber-500'
                      : 'text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800',
                    collapsed && 'justify-center',
                  )}
                  title={collapsed ? item.label : undefined}
                >
                  <Icon className="w-4 h-4 flex-shrink-0" />
                  {!collapsed && (
                    <>
                      <span className="flex-1 text-left">{item.label}</span>
                      {expanded ? (
                        <ChevronDown className="w-3.5 h-3.5 text-zinc-500" />
                      ) : (
                        <ChevronRight className="w-3.5 h-3.5 text-zinc-500" />
                      )}
                    </>
                  )}
                </button>

                {/* Children */}
                {expanded && (
                  <div className="mt-0.5 ml-3 pl-3 border-l border-zinc-800 space-y-0.5">
                    {item.children!.map((child) => {
                      const ChildIcon = child.icon
                      const childActive = pathname === child.href
                      return (
                        <Link
                          key={child.href}
                          href={child.href}
                          className={cn(
                            'flex items-center gap-2 px-2 py-1.5 rounded-md text-xs transition-colors duration-150',
                            childActive
                              ? 'bg-amber-500/10 text-amber-400'
                              : 'text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800',
                          )}
                        >
                          <ChildIcon className="w-3.5 h-3.5 flex-shrink-0" />
                          <span className="truncate">{child.label}</span>
                        </Link>
                      )
                    })}
                  </div>
                )}
              </div>
            )
          }

          return (
            <Link
              key={item.href}
              href={item.href}
              title={collapsed ? item.label : undefined}
              className={cn(
                'flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-sm transition-colors duration-150',
                active
                  ? 'bg-amber-500/10 text-amber-400 border-r-2 border-amber-500'
                  : 'text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800',
                collapsed && 'justify-center',
              )}
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {!collapsed && <span className="truncate">{item.label}</span>}
            </Link>
          )
        })}
      </nav>

      {/* ── User + collapse toggle ────────────────────────────────────── */}
      <div className="flex-shrink-0 border-t border-zinc-800 p-2 space-y-1">
        {/* User avatar */}
        {!collapsed && user && (
          <div className="flex items-center gap-2.5 px-2 py-1.5 rounded-lg">
            <div className="w-7 h-7 rounded-full bg-amber-500/20 border border-amber-500/30 flex items-center justify-center flex-shrink-0">
              <span className="text-amber-400 text-xs font-semibold uppercase">
                {user.username.charAt(0)}
              </span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-zinc-300 text-xs font-medium truncate">
                {user.username}
              </p>
              <p className="text-zinc-600 text-[10px] truncate capitalize">
                {user.role}
              </p>
            </div>
            <button
              onClick={logout}
              title="Sign out"
              className="text-zinc-600 hover:text-zinc-300 transition-colors p-0.5"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* Collapse toggle */}
        <button
          onClick={onToggle}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className={cn(
            'flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-sm w-full',
            'text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 transition-colors duration-150',
            collapsed && 'justify-center',
          )}
        >
          {collapsed ? (
            <PanelLeftOpen className="w-4 h-4 flex-shrink-0" />
          ) : (
            <>
              <PanelLeftClose className="w-4 h-4 flex-shrink-0" />
              <span className="text-xs">Collapse</span>
            </>
          )}
        </button>
      </div>
    </aside>
  )
}
