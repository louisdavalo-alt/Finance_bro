import type { ReactNode } from 'react'

export function Card({ title, children, className = '' }: { title?: string; children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-lg border border-slate-800 bg-slate-900/40 p-4 ${className}`}>
      {title && <h3 className="mb-3 text-sm font-semibold text-slate-300">{title}</h3>}
      {children}
    </div>
  )
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return <p className="rounded-md border border-red-900/50 bg-red-950/30 px-3 py-2 text-sm text-red-300">{children}</p>
}

export function Placeholder({ children }: { children: ReactNode }) {
  return <p className="py-4 text-sm text-slate-500">{children}</p>
}

export function Delta({ value, suffix = ' %' }: { value: number | null | undefined; suffix?: string }) {
  if (value === null || value === undefined) return <span className="text-slate-500">—</span>
  const cls = value > 0 ? 'text-emerald-400' : value < 0 ? 'text-red-400' : 'text-slate-400'
  const sign = value > 0 ? '+' : ''
  return (
    <span className={`font-mono tabular-nums ${cls}`}>
      {sign}
      {value.toFixed(2)}
      {suffix}
    </span>
  )
}

export function Num({ value, digits = 2 }: { value: number | null | undefined; digits?: number }) {
  if (value === null || value === undefined) return <span className="text-slate-500">—</span>
  return <span className="font-mono tabular-nums">{value.toFixed(digits)}</span>
}

export function Spinner() {
  return <div className="h-4 w-4 animate-spin rounded-full border-2 border-slate-600 border-t-sky-400" />
}
