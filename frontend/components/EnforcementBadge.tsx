type Mode = 'alert-only' | 'visible-downgrade' | 'hard-cap'

const styles: Record<Mode, string> = {
  'alert-only':        'bg-blue-500/10 text-blue-400 border-blue-500/20',
  'visible-downgrade': 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
  'hard-cap':          'bg-red-500/10 text-red-400 border-red-500/20',
}

export default function EnforcementBadge({ mode }: { mode: Mode }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium border ${styles[mode]}`}>
      {mode}
    </span>
  )
}
