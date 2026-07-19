import { supabase } from './supabase'

const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const IS_LOCAL_DEV = process.env.NEXT_PUBLIC_SUPABASE_URL?.startsWith('http://localhost')

async function headers() {
  if (IS_LOCAL_DEV) {
    return { 'Content-Type': 'application/json', Authorization: 'Bearer dev' }
  }
  const { data: { session } } = await supabase.auth.getSession()
  if (!session) throw new Error('Not authenticated')
  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${session.access_token}`,
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { ...init, headers: await headers() })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? 'Request failed')
  }
  return res.json()
}

export type Project = {
  id: string
  name: string
  budget_daily: number | null
  budget_monthly: number | null
  enforcement_mode: 'alert-only' | 'visible-downgrade' | 'hard-cap'
  telegram_chat_id: string | null
  daily_spend: number
  monthly_spend: number
  created_at: string
}

export type SpendPoint = { date: string; cost: number }

export type CoachData = {
  top_drivers: {
    model: string
    call_count: number
    total_cost: number
    avg_tokens: number
    pct_of_total: number
  }[]
  context_bloat:
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
  model_suggestions: {
    current_model: string
    suggested_model: string
    call_count: number
    avg_tokens: number
    actual_cost: number
    estimated_cost_with_suggestion: number
    estimated_savings_usd: number
    savings_pct: number
  }[]
}

export type RequestLog = {
  model: string
  input_tokens: number
  output_tokens: number
  cost: number
  was_downgraded: boolean
  was_blocked: boolean
  created_at: string
}

export const api = {
  projects: {
    list: () => req<Project[]>('/api/projects'),
    get: (id: string) => req<Project>(`/api/projects/${id}`),
    create: (data: Omit<Project, 'id' | 'daily_spend' | 'monthly_spend' | 'created_at'>) =>
      req<Project>('/api/projects', { method: 'POST', body: JSON.stringify(data) }),
    update: (id: string, data: Partial<Project>) =>
      req<Project>(`/api/projects/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  },
  spend: {
    history: (projectId: string, days = 7) =>
      req<SpendPoint[]>(`/api/projects/${projectId}/spend/history?days=${days}`),
  },
  keys: {
    create: (projectId: string, providerKey: string) =>
      req<{ proxy_key: string; warning: string }>(`/api/projects/${projectId}/keys`, {
        method: 'POST',
        body: JSON.stringify({ provider_key: providerKey }),
      }),
  },
  requests: {
    list: (projectId: string) => req<RequestLog[]>(`/api/projects/${projectId}/requests`),
  },
  coach: {
    get: (projectId: string, days = 30) =>
      req<CoachData>(`/api/projects/${projectId}/coach?days=${days}`),
  },
}
