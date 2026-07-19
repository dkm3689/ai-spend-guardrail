'use client'

import { useEffect, useState } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import Link from 'next/link'
import { supabase } from '@/lib/supabase'

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const [email, setEmail] = useState('')
  const [ready, setReady] = useState(false)

  useEffect(() => {
    // Skip Supabase auth when running locally without a real Supabase project
    const isLocalDev = process.env.NEXT_PUBLIC_SUPABASE_URL?.startsWith('http://localhost')
    if (isLocalDev) {
      setEmail('local-dev')
      setReady(true)
      return
    }
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (!session) {
        router.replace('/auth')
      } else {
        setEmail(session.user.email ?? '')
        setReady(true)
      }
    })
  }, [router])

  async function signOut() {
    await supabase.auth.signOut()
    router.replace('/auth')
  }

  if (!ready) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="w-5 h-5 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <aside className="w-56 bg-zinc-900 border-r border-zinc-800 flex flex-col shrink-0">
        <div className="px-5 py-5 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <span className="text-lg">🛡️</span>
            <span className="font-semibold text-sm text-zinc-100">Spend Guardrail</span>
          </div>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-1">
          <Link
            href="/dashboard"
            className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors ${
              pathname === '/dashboard'
                ? 'bg-indigo-600/20 text-indigo-400'
                : 'text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800'
            }`}
          >
            <span>📊</span> Projects
          </Link>
        </nav>

        <div className="px-3 py-4 border-t border-zinc-800">
          <div className="px-3 mb-2">
            <p className="text-xs text-zinc-500 truncate">{email}</p>
          </div>
          <button
            onClick={signOut}
            className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm
                       text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 transition-colors"
          >
            <span>↩</span> Sign out
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-y-auto">{children}</main>
    </div>
  )
}
