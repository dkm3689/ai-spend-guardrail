'use client'

import { useEffect, useState } from 'react'
import { api, type Project } from '@/lib/api'
import ProjectCard from '@/components/ProjectCard'

const MODES = ['alert-only', 'visible-downgrade', 'hard-cap'] as const

export default function DashboardPage() {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({
    name: '',
    budget_daily: '',
    budget_monthly: '',
    enforcement_mode: 'alert-only' as Project['enforcement_mode'],
    telegram_chat_id: '',
  })
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    api.projects.list().then((data) => {
      setProjects(data)
      setLoading(false)
    })
  }, [])

  async function createProject(e: React.FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    const project = await api.projects.create({
      name: form.name,
      budget_daily: form.budget_daily ? Number(form.budget_daily) : null,
      budget_monthly: form.budget_monthly ? Number(form.budget_monthly) : null,
      enforcement_mode: form.enforcement_mode,
      telegram_chat_id: form.telegram_chat_id || null,
    })
    setProjects((prev) => [project, ...prev])
    setShowForm(false)
    setForm({ name: '', budget_daily: '', budget_monthly: '', enforcement_mode: 'alert-only', telegram_chat_id: '' })
    setSubmitting(false)
  }

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">Projects</h1>
          <p className="text-sm text-zinc-500 mt-0.5">Each project gets its own proxy key and budget</p>
        </div>
        <button
          onClick={() => setShowForm(true)}
          className="bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium
                     px-4 py-2 rounded-lg transition-colors"
        >
          + New project
        </button>
      </div>

      {/* New project form */}
      {showForm && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 mb-6">
          <h2 className="text-base font-medium text-zinc-100 mb-4">New project</h2>
          <form onSubmit={createProject} className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <label>Project name</label>
              <input
                placeholder="my-agent"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                required
              />
            </div>
            <div>
              <label>Daily budget ($) — optional</label>
              <input
                type="number"
                step="0.01"
                min="0"
                placeholder="5.00"
                value={form.budget_daily}
                onChange={(e) => setForm((f) => ({ ...f, budget_daily: e.target.value }))}
              />
            </div>
            <div>
              <label>Monthly budget ($) — optional</label>
              <input
                type="number"
                step="0.01"
                min="0"
                placeholder="50.00"
                value={form.budget_monthly}
                onChange={(e) => setForm((f) => ({ ...f, budget_monthly: e.target.value }))}
              />
            </div>
            <div>
              <label>Enforcement mode</label>
              <select
                value={form.enforcement_mode}
                onChange={(e) => setForm((f) => ({ ...f, enforcement_mode: e.target.value as Project['enforcement_mode'] }))}
              >
                {MODES.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
            <div>
              <label>Telegram chat ID — optional</label>
              <input
                placeholder="-100123456789"
                value={form.telegram_chat_id}
                onChange={(e) => setForm((f) => ({ ...f, telegram_chat_id: e.target.value }))}
              />
            </div>
            <div className="col-span-2 flex gap-3 pt-2">
              <button
                type="submit"
                disabled={submitting}
                className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white
                           text-sm font-medium px-4 py-2 rounded-lg transition-colors"
              >
                {submitting ? 'Creating…' : 'Create project'}
              </button>
              <button
                type="button"
                onClick={() => setShowForm(false)}
                className="text-sm text-zinc-400 hover:text-zinc-200 px-4 py-2 transition-colors"
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Project grid */}
      {loading ? (
        <div className="flex items-center justify-center py-24">
          <div className="w-5 h-5 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : projects.length === 0 ? (
        <div className="text-center py-24 text-zinc-600">
          <p className="text-4xl mb-3">📭</p>
          <p className="text-sm">No projects yet. Create one to get your proxy key.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {projects.map((p) => <ProjectCard key={p.id} project={p} />)}
        </div>
      )}
    </div>
  )
}
