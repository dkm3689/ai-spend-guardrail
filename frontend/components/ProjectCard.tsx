import Link from 'next/link'
import type { Project } from '@/lib/api'
import EnforcementBadge from './EnforcementBadge'

function SpendBar({ spend, budget, label }: { spend: number; budget: number | null; label: string }) {
  if (!budget) return null
  const pct = Math.min((spend / budget) * 100, 100)
  const color = pct >= 100 ? 'bg-red-500' : pct >= 80 ? 'bg-yellow-500' : 'bg-indigo-500'

  return (
    <div>
      <div className="flex justify-between text-xs text-zinc-500 mb-1">
        <span>{label}</span>
        <span>${spend.toFixed(4)} / ${budget.toFixed(2)}</span>
      </div>
      <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

export default function ProjectCard({ project }: { project: Project }) {
  return (
    <Link href={`/dashboard/${project.id}`}>
      <div className="bg-zinc-900 border border-zinc-800 hover:border-zinc-700 rounded-2xl p-5
                      transition-colors cursor-pointer group">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h3 className="font-medium text-zinc-100 group-hover:text-white transition-colors">
              {project.name}
            </h3>
            <p className="text-xs text-zinc-600 mt-0.5">
              {new Date(project.created_at).toLocaleDateString()}
            </p>
          </div>
          <EnforcementBadge mode={project.enforcement_mode} />
        </div>

        <div className="space-y-3">
          <SpendBar spend={project.daily_spend} budget={project.budget_daily} label="Today" />
          <SpendBar spend={project.monthly_spend} budget={project.budget_monthly} label="This month" />

          {!project.budget_daily && !project.budget_monthly && (
            <p className="text-xs text-zinc-600">No budget set</p>
          )}
        </div>
      </div>
    </Link>
  )
}
