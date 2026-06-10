'use client'

import { useState, useRef, useEffect } from 'react'
import { cn } from '@/lib/utils'
import { Spinner } from '@/components/ui/Spinner'
import { Check, AlertCircle } from 'lucide-react'

// ── Types ─────────────────────────────────────────────────────────────────────

export type ConfigValueType = 'boolean' | 'number' | 'integer' | 'string' | 'enum' | 'percentage'

export interface ConfigParam {
  path: string
  label: string
  description: string
  type: ConfigValueType
  defaultValue: unknown
  min?: number
  max?: number
  step?: number
  options?: { value: string | number; label: string }[]
  displayMultiplier?: number
}

export interface ConfigSectionProps {
  title: string
  params: ConfigParam[]
  values: Record<string, unknown>
  onChange: (path: string, value: unknown) => void
  onSave: (path: string, value: unknown) => Promise<void>
  pendingPaths?: Set<string>
  errorPaths?: Record<string, string>
}

// ── Toggle switch ─────────────────────────────────────────────────────────────

function Toggle({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        'relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-amber-500/30',
        checked ? 'bg-amber-500' : 'bg-zinc-600',
        disabled && 'opacity-50 cursor-not-allowed'
      )}
    >
      <span
        className={cn(
          'inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform',
          checked ? 'translate-x-4' : 'translate-x-1'
        )}
      />
    </button>
  )
}

// ── Slider + number input ─────────────────────────────────────────────────────

function SliderInput({
  value,
  min,
  max,
  step,
  onChange,
  disabled,
  displayValue,
  onDisplayChange,
}: {
  value: number
  min: number
  max: number
  step: number
  onChange: (v: number) => void
  disabled?: boolean
  displayValue: string
  onDisplayChange: (raw: string) => void
}) {
  return (
    <div className="flex items-center gap-2 w-48">
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className={cn(
          'flex-1 h-1.5 rounded-full appearance-none cursor-pointer',
          'bg-zinc-700 [&::-webkit-slider-thumb]:appearance-none',
          '[&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:h-3.5',
          '[&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-amber-400',
          '[&::-webkit-slider-thumb]:cursor-pointer',
          disabled && 'opacity-50 cursor-not-allowed'
        )}
      />
      <input
        type="number"
        value={displayValue}
        disabled={disabled}
        onChange={(e) => onDisplayChange(e.target.value)}
        className={cn(
          'w-16 text-right bg-zinc-800 border border-zinc-700 rounded px-2 py-0.5',
          'text-xs text-zinc-200 font-mono focus:outline-none focus:border-zinc-500',
          'focus:ring-1 focus:ring-zinc-500/30 transition-colors',
          disabled && 'opacity-50'
        )}
      />
    </div>
  )
}

// ── Select ────────────────────────────────────────────────────────────────────

function SelectInput({
  value,
  options,
  onChange,
  disabled,
}: {
  value: string | number
  options: { value: string | number; label: string }[]
  onChange: (v: string | number) => void
  disabled?: boolean
}) {
  return (
    <select
      value={String(value)}
      disabled={disabled}
      onChange={(e) => {
        const opt = options.find((o) => String(o.value) === e.target.value)
        if (opt) onChange(opt.value)
      }}
      className={cn(
        'bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-xs text-zinc-200',
        'focus:outline-none focus:border-zinc-500 focus:ring-1 focus:ring-zinc-500/30',
        'transition-colors min-w-[140px]',
        disabled && 'opacity-50 cursor-not-allowed'
      )}
    >
      {options.map((opt) => (
        <option key={String(opt.value)} value={String(opt.value)}>
          {opt.label}
        </option>
      ))}
    </select>
  )
}

// ── Text input ────────────────────────────────────────────────────────────────

function TextInput({
  value,
  onChange,
  disabled,
}: {
  value: string
  onChange: (v: string) => void
  disabled?: boolean
}) {
  return (
    <input
      type="text"
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
      className={cn(
        'bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-xs text-zinc-200',
        'focus:outline-none focus:border-zinc-500 focus:ring-1 focus:ring-zinc-500/30',
        'transition-colors min-w-[160px]',
        disabled && 'opacity-50'
      )}
    />
  )
}

// ── Save button per field ─────────────────────────────────────────────────────

type SaveState = 'idle' | 'saving' | 'saved' | 'error'

function FieldSaveButton({
  dirty,
  saveState,
  onSave,
}: {
  dirty: boolean
  saveState: SaveState
  onSave: () => void
}) {
  if (!dirty && saveState === 'idle') return null

  return (
    <button
      type="button"
      onClick={onSave}
      disabled={saveState === 'saving' || (!dirty && saveState === 'idle')}
      className={cn(
        'flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium transition-all',
        saveState === 'saved'
          ? 'text-emerald-400 bg-emerald-500/10 border border-emerald-500/20'
          : saveState === 'error'
          ? 'text-red-400 bg-red-500/10 border border-red-500/20'
          : 'text-zinc-400 bg-zinc-800 border border-zinc-700 hover:bg-zinc-700 hover:text-zinc-200',
        (saveState === 'saving') && 'opacity-70 cursor-not-allowed'
      )}
    >
      {saveState === 'saving' ? (
        <Spinner size="sm" />
      ) : saveState === 'saved' ? (
        <Check className="w-3 h-3" />
      ) : saveState === 'error' ? (
        <AlertCircle className="w-3 h-3" />
      ) : null}
      {saveState === 'saved' ? 'Saved' : saveState === 'error' ? 'Error' : 'Save'}
    </button>
  )
}

// ── Single param row ──────────────────────────────────────────────────────────

function ParamRow({
  param,
  currentValue,
  isPending,
  error,
  onChange,
  onSave,
}: {
  param: ConfigParam
  currentValue: unknown
  isPending: boolean
  error?: string
  onChange: (path: string, value: unknown) => void
  onSave: (path: string, value: unknown) => Promise<void>
}) {
  const [saveState, setSaveState] = useState<SaveState>('idle')
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Track if this field has been changed
  const isDirty = isPending

  // Display value logic for percentage
  const multiplier = param.displayMultiplier ?? 1
  const storedNumber = typeof currentValue === 'number' ? currentValue : Number(currentValue ?? param.defaultValue)
  const displayNumber = storedNumber * multiplier

  function handleSliderChange(raw: number) {
    // raw is in display units; convert back to stored
    const stored = raw / multiplier
    onChange(param.path, param.type === 'integer' ? Math.round(stored) : stored)
  }

  function handleSliderDisplayChange(rawStr: string) {
    const raw = parseFloat(rawStr)
    if (!isNaN(raw)) {
      const stored = raw / multiplier
      const clamped = Math.max(
        (param.min ?? -Infinity) / multiplier,
        Math.min((param.max ?? Infinity) / multiplier, stored)
      )
      onChange(param.path, param.type === 'integer' ? Math.round(clamped * multiplier) / multiplier : clamped)
    }
  }

  async function handleSave() {
    setSaveState('saving')
    try {
      await onSave(param.path, currentValue)
      setSaveState('saved')
      if (saveTimer.current) clearTimeout(saveTimer.current)
      saveTimer.current = setTimeout(() => setSaveState('idle'), 2500)
    } catch {
      setSaveState('error')
      if (saveTimer.current) clearTimeout(saveTimer.current)
      saveTimer.current = setTimeout(() => setSaveState('idle'), 3000)
    }
  }

  useEffect(() => {
    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current)
    }
  }, [])

  const hasRange = param.min !== undefined && param.max !== undefined
  const showSlider =
    (param.type === 'number' || param.type === 'integer' || param.type === 'percentage') && hasRange

  const displayMin = (param.min ?? 0) * multiplier
  const displayMax = (param.max ?? 100) * multiplier
  const displayStep = param.step !== undefined ? param.step * multiplier : param.type === 'integer' ? 1 : 0.01

  return (
    <div
      className={cn(
        'flex flex-col sm:flex-row sm:items-center gap-3 py-3 border-b border-zinc-800/50 last:border-0',
        isDirty && 'bg-amber-500/3 -mx-3 px-3 rounded-lg'
      )}
    >
      {/* Left: labels */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          {isDirty && (
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 flex-shrink-0" title="Unsaved change" />
          )}
          <span className="text-zinc-200 text-sm font-medium">{param.label}</span>
        </div>
        <code className="text-zinc-600 text-[10px] font-mono block mt-0.5">{param.path}</code>
        <p className="text-zinc-500 text-xs mt-0.5 leading-snug">{param.description}</p>
        {error && (
          <p className="text-red-400 text-xs mt-1 flex items-center gap-1">
            <AlertCircle className="w-3 h-3" />
            {error}
          </p>
        )}
      </div>

      {/* Right: control */}
      <div className="flex items-center gap-2 flex-shrink-0">
        {param.type === 'boolean' && (
          <Toggle
            checked={Boolean(currentValue ?? param.defaultValue)}
            onChange={(v) => onChange(param.path, v)}
          />
        )}

        {showSlider && (
          <SliderInput
            value={displayNumber}
            min={displayMin}
            max={displayMax}
            step={displayStep}
            onChange={handleSliderChange}
            displayValue={displayNumber.toFixed(
              param.type === 'integer' ? 0 : 2
            )}
            onDisplayChange={handleSliderDisplayChange}
          />
        )}

        {!showSlider && (param.type === 'number' || param.type === 'integer') && (
          <input
            type="number"
            value={String(currentValue ?? param.defaultValue ?? '')}
            min={param.min}
            max={param.max}
            step={param.step ?? (param.type === 'integer' ? 1 : 0.01)}
            onChange={(e) => {
              const v = param.type === 'integer'
                ? parseInt(e.target.value, 10)
                : parseFloat(e.target.value)
              if (!isNaN(v)) onChange(param.path, v)
            }}
            className={cn(
              'bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-xs text-zinc-200 font-mono',
              'focus:outline-none focus:border-zinc-500 focus:ring-1 focus:ring-zinc-500/30',
              'transition-colors w-28 text-right'
            )}
          />
        )}

        {param.type === 'enum' && param.options && (
          <SelectInput
            value={String(currentValue ?? param.defaultValue ?? '')}
            options={param.options}
            onChange={(v) => onChange(param.path, v)}
          />
        )}

        {param.type === 'string' && (
          <TextInput
            value={String(currentValue ?? param.defaultValue ?? '')}
            onChange={(v) => onChange(param.path, v)}
          />
        )}

        {/* Save button (not shown for boolean since it auto-saves) */}
        {param.type !== 'boolean' && (
          <FieldSaveButton dirty={isDirty} saveState={saveState} onSave={() => void handleSave()} />
        )}
        {param.type === 'boolean' && isDirty && (
          <FieldSaveButton dirty={isDirty} saveState={saveState} onSave={() => void handleSave()} />
        )}
      </div>
    </div>
  )
}

// ── Main section component ────────────────────────────────────────────────────

export function ConfigSection({
  title,
  params,
  values,
  onChange,
  onSave,
  pendingPaths = new Set(),
  errorPaths = {},
}: ConfigSectionProps) {
  return (
    <div>
      <h3 className="text-zinc-300 text-sm font-semibold mb-3">{title}</h3>
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
        {params.map((param) => (
          <ParamRow
            key={param.path}
            param={param}
            currentValue={values[param.path]}
            isPending={pendingPaths.has(param.path)}
            error={errorPaths[param.path]}
            onChange={onChange}
            onSave={onSave}
          />
        ))}
        {params.length === 0 && (
          <p className="text-zinc-600 text-sm text-center py-4">No parameters in this category</p>
        )}
      </div>
    </div>
  )
}
