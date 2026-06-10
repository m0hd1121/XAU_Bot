'use client'

import React, { useState, useCallback } from 'react'
import { Copy, Check, ChevronRight, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'

interface JsonViewerProps {
  data: unknown
  collapsed?: boolean
  maxHeight?: string
  className?: string
}

// ─── Token colorizer ──────────────────────────────────────────────────────────

function JsonValue({ value, depth = 0 }: { value: unknown; depth?: number }) {
  const [open, setOpen] = useState(depth < 2)

  if (value === null) {
    return <span className="text-zinc-500 font-mono text-xs">null</span>
  }
  if (typeof value === 'boolean') {
    return (
      <span className="text-red-400 font-mono text-xs">
        {value ? 'true' : 'false'}
      </span>
    )
  }
  if (typeof value === 'number') {
    return <span className="text-sky-400 font-mono text-xs">{String(value)}</span>
  }
  if (typeof value === 'string') {
    return (
      <span className="text-emerald-400 font-mono text-xs">
        &quot;{value}&quot;
      </span>
    )
  }
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <span className="text-zinc-400 font-mono text-xs">[]</span>
    }
    return (
      <span>
        <button
          onClick={() => setOpen((o) => !o)}
          className="inline-flex items-center text-zinc-400 hover:text-zinc-200 transition-colors"
        >
          {open ? (
            <ChevronDown className="w-3 h-3" />
          ) : (
            <ChevronRight className="w-3 h-3" />
          )}
          <span className="font-mono text-xs text-zinc-400">
            [{!open && `${value.length} items`}
          </span>
        </button>
        {open ? (
          <span className="block pl-4 border-l border-zinc-800 ml-1">
            {value.map((item, i) => (
              <span key={i} className="block">
                <span className="text-zinc-600 font-mono text-xs mr-1">{i}:</span>
                <JsonValue value={item} depth={depth + 1} />
                {i < value.length - 1 && (
                  <span className="text-zinc-600">,</span>
                )}
              </span>
            ))}
            <span className="font-mono text-xs text-zinc-400">]</span>
          </span>
        ) : (
          <span className="font-mono text-xs text-zinc-400">]</span>
        )}
      </span>
    )
  }
  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
    if (entries.length === 0) {
      return <span className="text-zinc-400 font-mono text-xs">{'{}'}</span>
    }
    return (
      <span>
        <button
          onClick={() => setOpen((o) => !o)}
          className="inline-flex items-center text-zinc-400 hover:text-zinc-200 transition-colors"
        >
          {open ? (
            <ChevronDown className="w-3 h-3" />
          ) : (
            <ChevronRight className="w-3 h-3" />
          )}
          <span className="font-mono text-xs text-zinc-400">
            {'{'}
            {!open && `${entries.length} keys`}
          </span>
        </button>
        {open ? (
          <span className="block pl-4 border-l border-zinc-800 ml-1">
            {entries.map(([k, v], i) => (
              <span key={k} className="block">
                <span className="text-amber-400 font-mono text-xs">&quot;{k}&quot;</span>
                <span className="text-zinc-500 font-mono text-xs">: </span>
                <JsonValue value={v} depth={depth + 1} />
                {i < entries.length - 1 && (
                  <span className="text-zinc-600">,</span>
                )}
              </span>
            ))}
            <span className="font-mono text-xs text-zinc-400">{'}'}</span>
          </span>
        ) : (
          <span className="font-mono text-xs text-zinc-400">{'}'}</span>
        )}
      </span>
    )
  }
  return (
    <span className="text-zinc-400 font-mono text-xs">{String(value)}</span>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function JsonViewer({
  data,
  maxHeight = '400px',
  className,
}: JsonViewerProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(() => {
    const json = JSON.stringify(data, null, 2)
    navigator.clipboard.writeText(json).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }, [data])

  return (
    <div
      className={cn(
        'relative bg-zinc-950 border border-zinc-800 rounded-xl overflow-hidden',
        className,
      )}
    >
      {/* Copy button */}
      <button
        onClick={handleCopy}
        className="absolute top-2 right-2 z-10 flex items-center gap-1 px-2 py-1 rounded-md bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-zinc-200 transition-colors text-[10px]"
        title="Copy JSON"
      >
        {copied ? (
          <Check className="w-3 h-3 text-emerald-400" />
        ) : (
          <Copy className="w-3 h-3" />
        )}
        {copied ? 'Copied' : 'Copy'}
      </button>

      {/* Content */}
      <div
        className="p-4 overflow-auto"
        style={{ maxHeight }}
      >
        <JsonValue value={data} depth={0} />
      </div>
    </div>
  )
}

export { JsonViewer }
