'use client'

import { cn } from '@/lib/utils'
import { Spinner } from '@/components/ui/Spinner'
import {
  CheckCircle2,
  XCircle,
  Circle,
  AlertCircle,
} from 'lucide-react'

export interface PipelineStep {
  id: string
  label: string
  status: 'idle' | 'running' | 'passed' | 'failed' | 'pending'
  details?: string
  progress?: number
}

export interface ValidationPipelineProps {
  steps: PipelineStep[]
  currentGenome?: string
  className?: string
}

function StepIcon({ status }: { status: PipelineStep['status'] }) {
  switch (status) {
    case 'passed':
      return <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0" />
    case 'failed':
      return <XCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
    case 'running':
      return <Spinner size="sm" className="flex-shrink-0" />
    case 'pending':
      return <Circle className="w-5 h-5 text-zinc-600 flex-shrink-0" />
    case 'idle':
    default:
      return <AlertCircle className="w-5 h-5 text-zinc-700 flex-shrink-0" />
  }
}

function stepCircleBg(status: PipelineStep['status']): string {
  switch (status) {
    case 'passed': return 'bg-emerald-500/15 border-emerald-500/40'
    case 'failed': return 'bg-red-500/15 border-red-500/40'
    case 'running': return 'bg-sky-500/15 border-sky-500/40'
    case 'pending': return 'bg-zinc-800 border-zinc-700'
    case 'idle':
    default: return 'bg-zinc-900 border-zinc-800'
  }
}

function connectorColor(leftStatus: PipelineStep['status'], rightStatus: PipelineStep['status']): string {
  if (leftStatus === 'failed') return 'border-red-700'
  if (leftStatus === 'passed') return 'border-emerald-600'
  return 'border-zinc-700 border-dashed'
}

export function ValidationPipeline({ steps, currentGenome, className }: ValidationPipelineProps) {
  if (!steps || steps.length === 0) {
    return (
      <div className={cn('bg-zinc-900 border border-zinc-800 rounded-xl p-5', className)}>
        <p className="text-zinc-500 text-sm text-center">Idle — waiting for next cycle</p>
      </div>
    )
  }

  return (
    <div className={cn('bg-zinc-900 border border-zinc-800 rounded-xl p-5', className)}>
      {currentGenome && (
        <div className="mb-4 flex items-center gap-2">
          <span className="text-zinc-500 text-xs">Validating genome:</span>
          <code className="font-mono text-xs text-sky-400 bg-sky-500/10 px-2 py-0.5 rounded">
            {currentGenome.slice(0, 8)}
          </code>
        </div>
      )}

      {/* Horizontal layout (md+) */}
      <div className="hidden md:flex items-start gap-0">
        {steps.map((step, i) => (
          <div key={step.id} className="flex items-start flex-1 min-w-0">
            {/* Step node */}
            <div className="flex flex-col items-center flex-1 min-w-0">
              <div
                className={cn(
                  'w-10 h-10 rounded-full border-2 flex items-center justify-center',
                  stepCircleBg(step.status)
                )}
              >
                <StepIcon status={step.status} />
              </div>
              <span
                className={cn(
                  'mt-2 text-xs font-medium text-center leading-tight px-1 truncate w-full',
                  step.status === 'passed' ? 'text-emerald-400' :
                  step.status === 'failed' ? 'text-red-400' :
                  step.status === 'running' ? 'text-sky-400' :
                  'text-zinc-500'
                )}
              >
                {step.label}
              </span>
              {step.details && (
                <span className="mt-0.5 text-[10px] text-zinc-600 text-center leading-tight px-1">
                  {step.details}
                </span>
              )}
              {step.progress != null && step.status === 'running' && (
                <div className="mt-1.5 w-full px-2">
                  <div className="h-1 bg-zinc-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-sky-500 rounded-full transition-all"
                      style={{ width: `${Math.min(100, Math.max(0, step.progress))}%` }}
                    />
                  </div>
                  <span className="text-[10px] text-zinc-600 mt-0.5 text-center block">
                    {step.progress.toFixed(0)}%
                  </span>
                </div>
              )}
            </div>

            {/* Connector line (not after last step) */}
            {i < steps.length - 1 && (
              <div className="flex items-center pt-5 flex-shrink-0 w-6">
                <div
                  className={cn(
                    'w-6 h-px border-t-2',
                    connectorColor(step.status, steps[i + 1].status)
                  )}
                />
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Vertical layout (mobile) */}
      <div className="flex flex-col gap-0 md:hidden">
        {steps.map((step, i) => (
          <div key={step.id} className="flex flex-col">
            <div className="flex items-start gap-3">
              <div className="flex flex-col items-center">
                <div
                  className={cn(
                    'w-9 h-9 rounded-full border-2 flex items-center justify-center flex-shrink-0',
                    stepCircleBg(step.status)
                  )}
                >
                  <StepIcon status={step.status} />
                </div>
                {i < steps.length - 1 && (
                  <div
                    className={cn(
                      'w-px flex-1 min-h-[20px] border-l-2 mt-1',
                      step.status === 'passed' ? 'border-emerald-600' :
                      step.status === 'failed' ? 'border-red-700' :
                      'border-zinc-700 border-dashed'
                    )}
                  />
                )}
              </div>
              <div className="flex-1 pb-4 min-w-0">
                <span
                  className={cn(
                    'text-sm font-medium',
                    step.status === 'passed' ? 'text-emerald-400' :
                    step.status === 'failed' ? 'text-red-400' :
                    step.status === 'running' ? 'text-sky-400' :
                    'text-zinc-500'
                  )}
                >
                  {step.label}
                </span>
                {step.details && (
                  <p className="text-xs text-zinc-600 mt-0.5">{step.details}</p>
                )}
                {step.progress != null && step.status === 'running' && (
                  <div className="mt-1.5">
                    <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-sky-500 rounded-full transition-all"
                        style={{ width: `${Math.min(100, Math.max(0, step.progress))}%` }}
                      />
                    </div>
                    <span className="text-[10px] text-zinc-600 mt-0.5 block">
                      {step.progress.toFixed(0)}%
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
