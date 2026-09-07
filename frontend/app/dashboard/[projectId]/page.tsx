'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { api, type Project, type SpendPoint } from '@/lib/api'
import SpendChart from '@/components/SpendChart'
import EnforcementBadge from '@/components/EnforcementBadge'
import CoachPanel from '@/components/CoachPanel'

const MODES = ['alert-only', 'visible-downgrade', 'hard-cap'] as const
const DAYS_OPTIONS = [7, 14, 30] as const

export default function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const router = useRouter()

  const [project, setProject] = useState<Project | null>(null)
  const [history, setHistory] = useState<SpendPoint[]>([])
  const [days, setDays] = useState<7 | 14 | 30>(7)
  const [loading, setLoading] = useState(true)

  // Edit form state
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({ name: '', budget_daily: '', budget_monthly: '', enforcement_mode: 'alert-only' as Project['enforcement_mode'], telegram_chat_id: '' })
  const [saving, setSaving] = useState(false)

  // API key generation
  const [showKeyModal, setShowKeyModal] = useState(false)
  const [keyMode, setKeyMode] = useState<'stored' | 'agent'>('agent')
  const [providerKey, setProviderKey] = useState('')
  const [generatedKey, setGeneratedKey] = useState('')
  const [generatedKeyMode, setGeneratedKeyMode] = useState<'stored' | 'agent'>('agent')
  const [generatingKey, setGeneratingKey] = useState(false)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    Promise.all([
      api.projects.get(projectId),
      api.spend.history(projectId, days),
    ]).then(([proj, hist]) => {
      setProject(proj)
      setHistory(hist)
      setForm({
        name: proj.name,
        budget_daily: proj.budget_daily?.toString() ?? '',
        budget_monthly: proj.budget_monthly?.toString() ?? '',
        enforcement_mode: proj.enforcement_mode,
        telegram_chat_id: proj.telegram_chat_id ?? '',
      })
      setLoading(false)
    })
  }, [projectId, days])

  async function saveProject(e: React.FormEvent) {
    e.preventDefault()
    if (!project) return
    setSaving(true)
    const updated = await api.projects.update(projectId, {
      name: form.name,
      budget_daily: form.budget_daily ? Number(form.budget_daily) : null,
      budget_monthly: form.budget_monthly ? Number(form.budget_monthly) : null,
      enforcement_mode: form.enforcement_mode,
      telegram_chat_id: form.telegram_chat_id || null,
    })
    setProject((p) => p ? { ...p, ...updated } : p)
    setEditing(false)
    setSaving(false)
  }

  async function generateKey(e: React.FormEvent) {
    e.preventDefault()
    setGeneratingKey(true)
    const result = await api.keys.create(projectId, {
      key_mode: keyMode,
      ...(keyMode === 'stored' ? { provider_key: providerKey } : {}),
    })
    setGeneratedKey(result.proxy_key)
    setGeneratedKeyMode(result.key_mode as 'stored' | 'agent')
    setProviderKey('')
    setGeneratingKey(false)
  }

  function copyKey() {
    navigator.clipboard.writeText(generatedKey)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="w-5 h-5 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  if (!project) return null

  const budget = project.budget_daily || project.budget_monthly
  const spend = project.budget_daily ? project.daily_spend : project.monthly_spend
  const spendPct = budget ? Math.min((spend / budget) * 100, 100) : 0

  return (
    <div className="p-8 max-w-4xl mx-auto">
      {/* Breadcrumb */}
      <Link href="/dashboard" className="text-sm text-zinc-500 hover:text-zinc-300 transition-colors mb-6 inline-block">
        ← Projects
      </Link>

      {/* Header */}
      <div className="flex items-start justify-between mb-8">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <h1 className="text-2xl font-semibold text-zinc-100">{project.name}</h1>
            <EnforcementBadge mode={project.enforcement_mode} />
          </div>
          <p className="text-sm text-zinc-500">
            Created {new Date(project.created_at).toLocaleDateString()}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowKeyModal(true)}
            className="text-sm border border-zinc-700 text-zinc-300 hover:text-zinc-100
                       hover:border-zinc-600 px-3 py-1.5 rounded-lg transition-colors"
          >
            Generate key
          </button>
          <button
            onClick={() => setEditing(!editing)}
            className="text-sm bg-indigo-600 hover:bg-indigo-500 text-white
                       px-3 py-1.5 rounded-lg transition-colors"
          >
            {editing ? 'Cancel' : 'Edit'}
          </button>
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        <StatCard label="Today's spend" value={`$${project.daily_spend.toFixed(4)}`} sub={project.budget_daily ? `of $${project.budget_daily} daily` : 'No daily budget'} />
        <StatCard label="Monthly spend" value={`$${project.monthly_spend.toFixed(4)}`} sub={project.budget_monthly ? `of $${project.budget_monthly} monthly` : 'No monthly budget'} />
        <StatCard
          label="Budget used"
          value={budget ? `${spendPct.toFixed(1)}%` : '—'}
          sub={budget ? undefined : 'Set a budget to track'}
          accent={spendPct >= 80}
        />
      </div>

      {/* Spend chart */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-medium text-zinc-100">Spend history</h2>
          <div className="flex gap-1">
            {DAYS_OPTIONS.map((d) => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`text-xs px-2.5 py-1 rounded-md transition-colors ${
                  days === d
                    ? 'bg-indigo-600/30 text-indigo-400'
                    : 'text-zinc-500 hover:text-zinc-300'
                }`}
              >
                {d}d
              </button>
            ))}
          </div>
        </div>
        <SpendChart data={history} />
      </div>

      {/* Usage Coach */}
      <CoachPanel projectId={projectId} />

      {/* Edit form */}
      {editing && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 mb-6">
          <h2 className="text-sm font-medium text-zinc-100 mb-4">Edit project</h2>
          <form onSubmit={saveProject} className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <label>Project name</label>
              <input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} required />
            </div>
            <div>
              <label>Daily budget ($)</label>
              <input type="number" step="0.01" min="0" placeholder="5.00" value={form.budget_daily}
                onChange={(e) => setForm((f) => ({ ...f, budget_daily: e.target.value }))} />
            </div>
            <div>
              <label>Monthly budget ($)</label>
              <input type="number" step="0.01" min="0" placeholder="50.00" value={form.budget_monthly}
                onChange={(e) => setForm((f) => ({ ...f, budget_monthly: e.target.value }))} />
            </div>
            <div>
              <label>Enforcement mode</label>
              <select value={form.enforcement_mode} onChange={(e) => setForm((f) => ({ ...f, enforcement_mode: e.target.value as Project['enforcement_mode'] }))}>
                {MODES.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
            <div>
              <label>Telegram chat ID</label>
              <input placeholder="-100123456789" value={form.telegram_chat_id}
                onChange={(e) => setForm((f) => ({ ...f, telegram_chat_id: e.target.value }))} />
            </div>
            <div className="col-span-2 pt-2">
              <button type="submit" disabled={saving}
                className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors">
                {saving ? 'Saving…' : 'Save changes'}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* How to use */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 mt-6">
        <h2 className="text-sm font-medium text-zinc-100 mb-3">How to use</h2>

        {/* Agent mode instructions */}
        <div className="mb-4">
          <p className="text-xs font-medium text-zinc-400 mb-1">Agent mode (recommended)</p>
          <p className="text-xs text-zinc-500 mb-2">
            Run the agent on your server, then point your app at it:
          </p>
          <pre className="bg-zinc-950 border border-zinc-800 rounded-lg p-4 text-xs text-zinc-300 overflow-x-auto">{`# 1. Start the agent on your server
ANTHROPIC_API_KEY=sk-ant-...
GUARDRAIL_PROJECT_KEY=sk-guard-...
GUARDRAIL_URL=https://your-proxy.railway.app
python agent/agent.py

# 2. Point your app at the local agent
client = anthropic.Anthropic(
    api_key="sk-guard-...",   # proxy key from dashboard
    base_url="http://localhost:8002",
)`}</pre>
        </div>

        {/* Stored mode instructions */}
        <div>
          <p className="text-xs font-medium text-zinc-400 mb-1">Stored mode</p>
          <p className="text-xs text-zinc-500 mb-2">
            No agent needed — point directly at the proxy:
          </p>
          <pre className="bg-zinc-950 border border-zinc-800 rounded-lg p-4 text-xs text-zinc-300 overflow-x-auto">{`client = anthropic.Anthropic(
    api_key="sk-guard-...",   # proxy key from dashboard
    base_url="https://your-proxy.railway.app",
)`}</pre>
        </div>
      </div>

      {/* Generate key modal */}
      {showKeyModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 px-4">
          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 w-full max-w-md">
            <h2 className="text-base font-medium text-zinc-100 mb-1">Generate proxy key</h2>

            {generatedKey ? (
              <div>
                <p className="text-xs text-zinc-500 mb-4">
                  {generatedKeyMode === 'agent'
                    ? 'Run the Guardrail Agent on your server and paste this key into its .env file.'
                    : 'Your Anthropic key is encrypted at rest. Save this proxy key — it won\'t be shown again.'}
                </p>
                <label>Proxy key — save this now</label>
                <div className="flex gap-2 mt-1">
                  <input readOnly value={generatedKey} className="font-mono text-xs" />
                  <button onClick={copyKey}
                    className="shrink-0 bg-zinc-700 hover:bg-zinc-600 text-zinc-200 text-xs px-3 py-2 rounded-lg transition-colors">
                    {copied ? '✓' : 'Copy'}
                  </button>
                </div>
                {generatedKeyMode === 'agent' && (
                  <div className="mt-3 bg-zinc-800 rounded-lg p-3 text-xs text-zinc-400 font-mono">
                    GUARDRAIL_PROJECT_KEY={generatedKey}
                  </div>
                )}
                <button onClick={() => { setShowKeyModal(false); setGeneratedKey('') }}
                  className="mt-4 w-full text-sm text-zinc-400 hover:text-zinc-200 py-2 transition-colors">
                  Done
                </button>
              </div>
            ) : (
              <form onSubmit={generateKey}>
                {/* Mode selector */}
                <div className="flex bg-zinc-800 rounded-lg p-1 mb-4 mt-3">
                  {(['agent', 'stored'] as const).map((m) => (
                    <button
                      key={m}
                      type="button"
                      onClick={() => setKeyMode(m)}
                      className={`flex-1 py-1.5 rounded-md text-xs font-medium transition-colors ${
                        keyMode === m
                          ? 'bg-zinc-700 text-zinc-100'
                          : 'text-zinc-500 hover:text-zinc-300'
                      }`}
                    >
                      {m === 'agent' ? '🔒 Agent mode (recommended)' : '🗝️ Stored mode'}
                    </button>
                  ))}
                </div>

                {keyMode === 'agent' ? (
                  <p className="text-xs text-zinc-500 mb-4">
                    Your Anthropic key stays on your own server. The Guardrail Agent runs locally,
                    checks budget with us, and calls Anthropic directly — your key never leaves your infrastructure.
                  </p>
                ) : (
                  <>
                    <p className="text-xs text-zinc-500 mb-3">
                      Your Anthropic key is encrypted (AES-256) before storage and never logged.
                    </p>
                    <label>Your Anthropic API key</label>
                    <input type="password" placeholder="sk-ant-..." value={providerKey}
                      onChange={(e) => setProviderKey(e.target.value)} required={keyMode === 'stored'} />
                  </>
                )}

                <div className="flex gap-3 mt-4">
                  <button type="submit" disabled={generatingKey}
                    className="flex-1 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm font-medium py-2 rounded-lg transition-colors">
                    {generatingKey ? 'Generating…' : 'Generate key'}
                  </button>
                  <button type="button" onClick={() => setShowKeyModal(false)}
                    className="text-sm text-zinc-400 hover:text-zinc-200 px-4 py-2 transition-colors">
                    Cancel
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function StatCard({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: boolean }) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
      <p className="text-xs text-zinc-500 mb-1">{label}</p>
      <p className={`text-2xl font-semibold ${accent ? 'text-yellow-400' : 'text-zinc-100'}`}>{value}</p>
      {sub && <p className="text-xs text-zinc-600 mt-0.5">{sub}</p>}
    </div>
  )
}
