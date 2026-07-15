import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'AI Spend Guardrail',
  description: 'Real-time LLM budget management for devs and small teams',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
