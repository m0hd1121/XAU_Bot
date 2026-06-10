'use client'

import { useMemo } from 'react'
import { cn } from '@/lib/utils'
import { AgentState } from '@/types'
import { ValidationPipeline, PipelineStep } from '@/components/agents/ValidationPipeline'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card'
import { SparkLine } from '@/components/charts/SparkLine'
import { Dna, FlaskConical, BarChart2, Shuffle, Eye, Rocket } from 'lucide-react'

interface Agent1ResearchProps {
  agent: AgentState | null
  className?: string
}

const PIPELINE_STEP_ICONS: Record<string, React.ReactNode> = {
  genome_generation: <Dna className="w-4 h-4" />,
  backtesting: <BarChart2 className="w-4 h-4" />,
  walk_forward: <Shuffle className="w-4 h-4" />,
  monte_carlo: <FlaskConical className="w-4 h-4" />,
  shadow_mode: <Eye className="w-4 h-4" />,
  production: <Rocket className="w-4 h-4" />,
}

function buildPipelineSteps(metrics: AgentState['metrics']): PipelineStep[] {
  const pipelineRaw = metrics.pipeline as Record<string, unknown> | undefined

  if (!pipelineRaw) {
    // Default all-pending pipeline when no active validation
    return [
      { id: 'genome_generation', label: 'Genome Generation', status: 'idle' },
      { id: 'backtesting', label: 'Backtesting', status: 'idle' },
      { id: 'walk_forward', label: 'Walk-Forward', status: 'idle' },
      { id: 'monte_carlo', label: 'Monte Carlo', status: 'idle' },
      { id: 'shadow_mode', label: 'Shadow Mode', status: 'idle' },
      { id: 'production', label: 'Production', status: 'idle' },
    ]
  }

  const stepOrder = ['genome_generation', 'backtesting', 'walk_forward', 'monte_carlo', 'shadow_mode', 'production']
  const stepLabels: Record<string, string> = {
    genome_generation: 'Genome Generation',
    backtesting: 'Backtesting',
    walk_forward: 'Walk-Forward',
    monte_carlo: 'Monte Carlo',
    shadow_mode: 'Shadow Mode',
    production: 'Production',
  }

  return stepOrder.map((id) => {
    const raw = pipelineRaw[id] as Record<string, unknown> | undefined
    const rawStatus = raw?.status as string | undefined
    let status: PipelineStep['status'] = 'pending'

    if (rawStatus === 'done' || rawStatus === 'passed') status = 'passed'
    else if (rawStatus === 'running' || rawStatus === 'active') status = 'running'
    else if (rawStatus === 'failed') status = 'failed'
    else if (rawStatus === 'pending') status = 'pending'
    else if (!rawStatus) status = 'idle'

    const details = raw?.details as string | undefined
    const progress = raw?.progress as number | undefined

    return { id, label: stepLabels[id], status, details, progress }
  })
}

export function Agent1Research({ agent, className }: Agent1ResearchProps) {
  const metrics = agent?.metrics ?? {}

  const steps = useMemo(() => buildPipelineSteps(metrics), [metrics])

  const hasActiveValidation = steps.some((s) => s.status === 'running')
  const currentGenome = metrics.current_genome as string | undefined

  const generationHistory = useMemo(() => {
    const raw = metrics.generation_history as Array<{ generation: number; best_score: number }> | undefined
    if (!raw || !Array.isArray(raw)) return []
    return raw.map((pt) => pt.best_score ?? 0)
  }, [metrics])

  return (
    <div className={cn('space-y-4', className)}>
      {/* Pipeline card */}
      <Card className="bg-zinc-900 border border-zinc-800 rounded-xl">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-medium text-zinc-300 flex items-center gap-2">
              <FlaskConical className="w-4 h-4 text-sky-400" />
              Validation Pipeline
            </CardTitle>
            {!hasActiveValidation && (
              <span className="text-xs text-zinc-500 italic">Idle — waiting for next cycle</span>
            )}
            {hasActiveValidation && currentGenome && (
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-zinc-500">Active:</span>
                <code className="font-mono text-xs text-sky-400 bg-sky-500/10 px-1.5 py-0.5 rounded">
                  {currentGenome.slice(0, 8)}
                </code>
              </div>
            )}
          </div>
        </CardHeader>
        <CardContent className="pt-0">
          <ValidationPipeline
            steps={steps}
            currentGenome={hasActiveValidation ? currentGenome : undefined}
            className="border-0 p-0"
          />
        </CardContent>
      </Card>

      {/* Generation history sparkline */}
      {generationHistory.length > 0 && (
        <Card className="bg-zinc-900 border border-zinc-800 rounded-xl">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-zinc-400 flex items-center gap-2">
              <BarChart2 className="w-4 h-4" />
              Best Composite Score — Generation History
            </CardTitle>
          </CardHeader>
          <CardContent>
            <SparkLine
              data={generationHistory}
              height={56}
              color="#34d399"
              className="w-full"
            />
            <div className="flex items-center justify-between mt-1">
              <span className="text-[10px] text-zinc-600">
                Gen 1
              </span>
              <span className="text-[10px] text-zinc-600">
                Gen {generationHistory.length}
              </span>
            </div>
          </CardContent>
        </Card>
      )}

      {generationHistory.length === 0 && (
        <Card className="bg-zinc-900 border border-zinc-800 rounded-xl">
          <CardContent className="py-6 flex items-center justify-center">
            <p className="text-zinc-600 text-sm">No generation history yet</p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
