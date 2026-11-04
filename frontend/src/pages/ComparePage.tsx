import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'

import { api, apiErrorMessage } from '../api/client'
import { Card, ErrorNote, Placeholder, Spinner } from '../components/ui'
import { MultiLineChart, type LineSeriesSpec } from '../components/MultiLineChart'

const PALETTE = ['#D4A73A', '#3FB68B', '#7AA7D9', '#E0645A', '#B389D9']
const MAX_COMPARE = 5

type Freq = 'D' | 'W' | 'M' | 'Q' | 'A'
const FREQ_LABELS: Record<Freq, string> = { D: 'Quotidien', W: 'Hebdo', M: 'Mensuel', Q: 'Trimestriel', A: 'Annuel' }

export default function ComparePage() {
  const [selected, setSelected] = useState<string[]>([])
  const [filter, setFilter] = useState('')
  const [freq, setFreq] = useState<Freq>('M')

  const indicators = useQuery({
    queryKey: ['indicators'],
    queryFn: async () => {
      const { data, error } = await api.GET('/indicators')
      if (error) throw error
      return data
    },
  })

  const panel = useQuery({
    queryKey: ['panel', selected, freq],
    enabled: selected.length >= 2,
    queryFn: async () => {
      const { data, error } = await api.GET('/panel', { params: { query: { codes: selected.join(','), freq } } })
      if (error) throw error
      return data
    },
  })

  const series = useMemo<LineSeriesSpec[]>(() => {
    if (!panel.data) return []
    // Rebasé à 100 sur la première valeur disponible de chaque série — les unités des
    // indicateurs comparés diffèrent (indice, %, devise...), seule l'évolution relative a du
    // sens à superposer. Même logique que l'ancien tableau de bord (renderCompare).
    return selected.map((code, i) => {
      const raw = panel.data!.rows.map((r) => ({ date: String(r.date), y: r[code] as number | null | undefined }))
      const base = raw.find((p) => p.y !== null && p.y !== undefined)?.y ?? null
      const points = raw.map((p) => ({
        date: p.date,
        y: base !== null && p.y !== null && p.y !== undefined ? (p.y / base) * 100 : null,
      }))
      return { label: code, color: PALETTE[i % PALETTE.length], points }
    })
  }, [panel.data, selected])

  const candidates = useMemo(() => {
    if (!indicators.data) return []
    const q = filter.trim().toLowerCase()
    return indicators.data
      .filter((row) => !selected.includes(row.code))
      .filter((row) => !q || row.code.toLowerCase().includes(q) || row.country.toLowerCase().includes(q))
      .slice(0, 8)
  }, [indicators.data, filter, selected])

  function add(code: string) {
    if (selected.length >= MAX_COMPARE || selected.includes(code)) return
    setSelected([...selected, code])
    setFilter('')
  }
  function remove(code: string) {
    setSelected(selected.filter((c) => c !== code))
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold text-slate-100">Comparer</h1>
      <p className="max-w-3xl text-sm text-slate-400">
        Superpose jusqu'à {MAX_COMPARE} indicateurs (macro ou marché, pays différents compris), alignés sans biais de
        look-ahead et rebasés à 100 sur leur première valeur commune — pour comparer des évolutions, pas des niveaux.
      </p>

      <Card>
        <div className="flex flex-wrap gap-2">
          {selected.map((code, i) => (
            <span
              key={code}
              className="flex items-center gap-1.5 rounded-full border border-slate-700 bg-slate-800/60 px-3 py-1 text-xs"
            >
              <span className="h-2 w-2 rounded-full" style={{ background: PALETTE[i % PALETTE.length] }} />
              {code}
              <button onClick={() => remove(code)} aria-label="Retirer" className="text-slate-500 hover:text-slate-200">
                ×
              </button>
            </span>
          ))}
          {selected.length === 0 && <Placeholder>Ajoute au moins deux indicateurs ci-dessous pour les superposer.</Placeholder>}
        </div>

        {selected.length < MAX_COMPARE && (
          <div className="mt-3">
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Rechercher un indicateur à ajouter (code ou pays)…"
              className="w-72 rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 placeholder:text-slate-500 focus:border-sky-500 focus:outline-none"
            />
            {filter && candidates.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-2">
                {candidates.map((row) => (
                  <button
                    key={row.code}
                    onClick={() => add(row.code)}
                    className="rounded-md border border-slate-700 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-800"
                  >
                    {row.code} <span className="text-slate-500">({row.country})</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="mt-3 flex overflow-hidden rounded-md border border-slate-700" style={{ width: 'fit-content' }}>
          {(Object.keys(FREQ_LABELS) as Freq[]).map((f) => (
            <button
              key={f}
              onClick={() => setFreq(f)}
              className={`px-3 py-1.5 text-sm ${freq === f ? 'bg-sky-500/20 text-sky-300' : 'text-slate-400 hover:bg-slate-800'}`}
            >
              {FREQ_LABELS[f]}
            </button>
          ))}
        </div>
      </Card>

      {selected.length >= 2 && (
        <Card>
          {panel.isLoading && (
            <div className="flex items-center gap-2 text-slate-400">
              <Spinner /> Chargement…
            </div>
          )}
          {panel.error && <ErrorNote>{apiErrorMessage(panel.error)}</ErrorNote>}
          {series.length > 0 && panel.data && (
            <>
              <MultiLineChart series={series} />
              <div className="mt-3 flex flex-wrap gap-4 text-xs text-slate-400">
                {series.map((s) => (
                  <span key={s.label} className="flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full" style={{ background: s.color }} />
                    {s.label}
                  </span>
                ))}
              </div>
            </>
          )}
        </Card>
      )}
    </div>
  )
}
