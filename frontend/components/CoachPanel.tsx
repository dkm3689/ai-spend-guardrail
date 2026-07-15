'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'

type Driver = {
  model: string
  call_count: number
  total_cost: number
  avg_tokens: number
  pct_of_total: number
}

type ContextBloat =
  | { detected: false }
  | {
      detected: true
      growth_ratio: number
      avg_growth_pct: number
      requests_analyzed: number
      min_input_tokens: number
      max_input_tokens: number
      estimated_waste_usd: number
    }

type Suggestion = {
  current_model: string
  suggested_model: string
  call_count: number
  avg_tokens: number
  actual_cost: number
  estimated_cost_with_suggestion: number
  estimated_savings_usd: number
  savings_pct: number
}

type CoachData = {
  top_drivers: Driver[]
  context_bloat: ContextBloat
  model_suggestions: Suggestion[]
}

function shortModel(model: string) {
  return model.replace('claude-', '').replace(/-\d{8}$/, '')
}

// ── Top cost drivers ──────────────────────────────────────────────────────────

function TopDrivers({ drivers }: { drivers: Driver[] }) {
  if (!drivers.length) {
    return <Empty text="No requests yet" />
  }

  const maxCost = Math.max(...drivers.map((d) => d.total_cost))

  return (
    <div className="space-y-3">
      {drivers.map((d) => (
        <div key={d.model}>
          <div className="flex items-center justify-between text-xs mb-1">
            <span className="text-zinc-300 font-mono">{shortModel(d.model)}</span>
            <div className="flex items-center gap-3 text-zinc-500">
              <span>{d.call_count} calls</span>
              <span>~{d.avg_tokens.toLocaleString()} avg tokens</span>
              <span className="text-zinc-200 font-medium">${d.total_cost.toFixed(4)}</span>
            </div>
          </div>
          <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full bg-indigo-500 transition-all"
              style={{ width: `${(d.total_cost / maxCost) * 100}%` }}
            />
          </div>
          <p className="text-right text-xs text-zinc-600 mt-0.5">{d.pct_of_total}% of total spend</p>
        </div>
      ))}
    </div>
  )
}

// ── Context bloat ─────────────────────────────────────────────────────────────

function ContextBloatSection({ bloat }: { bloat: ContextBloat }) {
  if (!bloat.detected) {
    return <Empty text="No context bloat detected" green />
  }

  const b = bloat

  return (
    <div className="bg-yellow-500/8 border border-yellow-500/20 rounded-xl p-4">
      <div className="flex items-start gap-3">
        <span className="text-xl mt-0.5">⚠️</span>
        <div className="text-sm space-y-1">
          <p className="text-yellow-300 font-medium">Context bloat detected</p>
          <p className="text-zinc-400">
            {Math.round(b.growth_ratio * 100)}% of the last {b.requests_analyzed} calls show
            growing input context (+{b.avg_growth_pct}% per call on average).
          </p>
          <div className="flex gap-6 pt-1 text-xs text-zinc-500">
            <span>Min input: <strong className="text-zinc-300">{b.min_input_tokens.toLocaleString()} tk</strong></span>
            <span>Max input: <strong className="text-zinc-300">{b.max_input_tokens.toLocaleString()} tk</strong></span>
            <span>Est. waste: <strong className="text-yellow-400">${b.estimated_waste_usd.toFixed(4)}</strong></span>
          </div>
          <p className="text-zinc-600 text-xs pt-1">
            Fix: summarize earlier turns, use a sliding window, or trim system prompts between calls.
          </p>
        </div>
      </div>
    </div>
  )
}

// ── Model suggestions ─────────────────────────────────────────────────────────

function ModelSuggestions({ suggestions }: { suggestions: Suggestion[] }) {
  if (!suggestions.length) {
    return <Empty text="No cheaper alternatives found for your usage pattern" green />
  }

  return (
    <div className="space-y-3">
      {suggestions.map((s, i) => (
        <div key={i} className="bg-blue-500/8 border border-blue-500/20 rounded-xl p-4">
          <div className="flex items-start gap-3">
            <span className="text-xl mt-0.5">💡</span>
            <div className="flex-1 text-sm">
              <p className="text-blue-300 font-medium mb-1">
                {s.call_count} short calls on{' '}
                <span className="font-mono">{shortModel(s.current_model)}</span>
              </p>
              <p className="text-zinc-400 text-xs mb-2">
                Avg {s.avg_tokens.toLocaleString()} tokens — well within{' '}
                <span className="font-mono text-zinc-300">{shortModel(s.suggested_model)}</span>'s capability.
              </p>
              <div className="flex items-center gap-2">
                <div className="flex-1 bg-zinc-800 rounded-lg px-3 py-2 text-center">
                  <p className="text-xs text-zinc-500">Actual cost</p>
                  <p className="text-red-400 font-semibold">${s.actual_cost.toFixed(4)}</p>
                </div>
                <span className="text-zinc-600 text-lg">→</span>
                <div className="flex-1 bg-zinc-800 rounded-lg px-3 py-2 text-center">
                  <p className="text-xs text-zinc-500">With suggestion</p>
                  <p className="text-green-400 font-semibold">${s.estimated_cost_with_suggestion.toFixed(4)}</p>
                </div>
                <div className="flex-1 bg-green-500/10 border border-green-500/20 rounded-lg px-3 py-2 text-center">
                  <p className="text-xs text-zinc-500">Savings</p>
                  <p className="text-green-400 font-semibold">{s.savings_pct}%</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function Empty({ text, green }: { text: string; green?: boolean }) {
  return (
    <p className={`text-xs ${green ? 'text-green-500' : 'text-zinc-600'}`}>
      {green ? '✓ ' : ''}{text}
    </p>
  )
}

function Section({ title, icon, children }: { title: string; icon: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wider flex items-center gap-2 mb-3">
        <span>{icon}</span> {title}
      </h3>
      {children}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function CoachPanel({ projectId }: { projectId: string }) {
  const [data, setData] = useState<CoachData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.coach.get(projectId).then((d) => {
      setData(d)
      setLoading(false)
    })
  }, [projectId])

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6">
      <div className="flex items-center gap-2 mb-6">
        <span className="text-lg">🧠</span>
        <h2 className="text-sm font-medium text-zinc-100">Usage Coach</h2>
        <span className="ml-auto text-xs text-zinc-600">Last 30 days</span>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-10">
          <div className="w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : !data ? (
        <p className="text-xs text-zinc-600">Failed to load insights</p>
      ) : (
        <div className="space-y-8">
          <Section title="Top cost drivers" icon="💰">
            <TopDrivers drivers={data.top_drivers} />
          </Section>

          <Section title="Context bloat" icon="📈">
            <ContextBloatSection bloat={data.context_bloat} />
          </Section>

          <Section title="Model suggestions" icon="💡">
            <ModelSuggestions suggestions={data.model_suggestions} />
          </Section>
        </div>
      )}
    </div>
  )
}
