import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { api, apiErrorMessage } from '../api/client'
import { CandlestickChart } from '../components/CandlestickChart'
import { Card, ErrorNote, Placeholder, Spinner } from '../components/ui'
import { WatchlistButton } from '../components/WatchlistButton'

type RangeKey = '1D' | '5D' | '1M' | '3M' | '1Y' | '5Y' | 'YTD' | 'MAX'
const RANGES: RangeKey[] = ['1D', '5D', '1M', '3M', '1Y', '5Y', 'YTD', 'MAX']

const nf2 = new Intl.NumberFormat('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const nf4 = new Intl.NumberFormat('fr-FR', { minimumFractionDigits: 4, maximumFractionDigits: 4 })
const nf0 = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 })

function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return digits === 0 ? nf0.format(v) : nf2.format(v)
}

/** Comme la fiche de cotation Euronext : 4 décimales pour un prix sous 10 (devises, petites
 * valeurs), 2 sinon. */
function fmtPrice(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return Math.abs(v) < 10 ? nf4.format(v) : nf2.format(v)
}

function fmtBig(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  const a = Math.abs(v)
  if (a >= 1e12) return `${fmtNum(v / 1e12, 2)} Bn`
  if (a >= 1e9) return `${fmtNum(v / 1e9, 2)} Md`
  if (a >= 1e6) return `${fmtNum(v / 1e6, 2)} M`
  return fmtNum(v, 0)
}

/** "2026-09-28 17:14" -> "[28/09/2026 17:14]" ; "2026-09-28" -> "[28/09/2026]" ; "16:22" -> "[16:22]". */
function bracketStamp(s?: string | null): string {
  if (!s) return ''
  if (s.length <= 5) return `[${s}]`
  const d = `${s.slice(8, 10)}/${s.slice(5, 7)}/${s.slice(0, 4)}`
  return s.length > 10 ? `[${d} ${s.slice(11, 16)}]` : `[${d}]`
}

type QuoteSummary = NonNullable<ReturnType<typeof useQuoteData>['data']>

function useQuoteData(code: string | null) {
  return useQuery({
    queryKey: ['quote', code],
    enabled: !!code,
    queryFn: async () => {
      const { data, error } = await api.GET('/quote/{indicator_code}', { params: { path: { indicator_code: code! } } })
      if (error) throw error
      return data
    },
  })
}

function quoteRows(q: QuoteSummary): [string, string, string][] {
  const chg = q.change ?? null
  const chgLabel =
    chg === null
      ? '—'
      : `${chg > 0 ? '+' : ''}${fmtPrice(chg)} (${chg > 0 ? '+' : ''}${fmtNum(q.change_pct, 2)} %)`
  return [
    ['Devise', q.currency ?? '—', ''],
    ['Dernier traité', fmtPrice(q.last), bracketStamp(q.last_time)],
    ['Variation', chgLabel, ''],
    ['Clôture veille', fmtPrice(q.previous_close), ''],
    ['Volume', fmtNum(q.volume, 0), bracketStamp(q.last_time)],
    ['Capitaux (approx.)', fmtNum(q.turnover, 0), ''],
    ['VWAP (approx.)', fmtPrice(q.vwap), ''],
    ['Ouvert', fmtPrice(q.open), ''],
    ['Haut', fmtPrice(q.high), bracketStamp(q.high_time)],
    ['Bas', fmtPrice(q.low), bracketStamp(q.low_time)],
    ['52 semaines', `${fmtPrice(q.week52_low)}  —  ${fmtPrice(q.week52_high)}`, ''],
    ['Capitalisation', fmtBig(q.market_cap), ''],
  ]
}

export default function QuotePage() {
  const [params, setParams] = useSearchParams()
  const code = params.get('code') ?? ''
  const [range, setRange] = useState<RangeKey>('1D')
  const [submittedCode, setSubmittedCode] = useState(code || null)

  const quote = useQuoteData(submittedCode)

  const chart = useQuery({
    queryKey: ['chart', submittedCode, range],
    enabled: !!submittedCode,
    queryFn: async () => {
      const { data, error } = await api.GET('/chart/{indicator_code}', {
        params: { path: { indicator_code: submittedCode! }, query: { range } },
      })
      if (error) throw error
      return data
    },
  })

  function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setParams(code ? { code } : {})
    setSubmittedCode(code || null)
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold text-slate-100">Fiche de cotation</h1>

      <form onSubmit={onSubmit} className="flex flex-wrap items-center gap-3">
        <input
          value={code}
          onChange={(e) => setParams({ code: e.target.value })}
          placeholder="Code (ex. DE_DAX, USA_APPLE)…"
          className="w-56 rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 placeholder:text-slate-500 focus:border-sky-500 focus:outline-none"
        />
        <button type="submit" className="rounded-md bg-sky-500 px-4 py-1.5 text-sm font-medium text-slate-950 hover:bg-sky-400">
          Afficher
        </button>
        {submittedCode && <WatchlistButton code={submittedCode} />}
      </form>

      {!submittedCode && <Placeholder>Saisis un code d'indicateur de marché pour commencer (voir l'onglet Indicateurs).</Placeholder>}

      {submittedCode && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[340px_1fr] lg:items-start">
          <Card title={submittedCode}>
            {quote.isLoading && <Spinner />}
            {quote.error && <ErrorNote>{apiErrorMessage(quote.error)}</ErrorNote>}
            {quote.data && (
              <>
                <div className="flex flex-col divide-y divide-slate-800">
                  {quoteRows(quote.data).map(([label, value, stamp]) => (
                    <div key={label} className="flex items-baseline justify-between gap-3 py-1.5 text-sm">
                      <span className="text-slate-400">{label}</span>
                      <span className="flex items-baseline gap-1.5 text-right">
                        <span className="font-mono tabular-nums text-slate-100">{value}</span>
                        {stamp && <span className="font-mono text-xs text-slate-500">{stamp}</span>}
                      </span>
                    </div>
                  ))}
                </div>
                <p className="mt-3 text-xs leading-relaxed text-slate-500">
                  {quote.data.intraday
                    ? 'VWAP et capitaux : approximation calculée sur des barres de 5 minutes. '
                    : 'Pas de données intraday : valeurs de la dernière séance quotidienne (VWAP et capitaux indisponibles). '}
                  Non disponibles via Yahoo Finance : nombre de transactions, seuils de réservation, clôture de
                  valorisation. Source : Yahoo Finance (peut être différée) — mis à jour {bracketStamp(quote.data.last_time)}.
                </p>
              </>
            )}
          </Card>

          <Card>
            <div className="mb-3 flex flex-wrap gap-1">
              {RANGES.map((r) => (
                <button
                  key={r}
                  onClick={() => setRange(r)}
                  className={`rounded-md px-2.5 py-1 text-xs font-medium ${
                    range === r ? 'bg-sky-500/20 text-sky-300' : 'text-slate-400 hover:bg-slate-800'
                  }`}
                >
                  {r}
                </button>
              ))}
            </div>
            {chart.isLoading && (
              <div className="flex items-center gap-2 text-slate-400">
                <Spinner /> Chargement du graphique…
              </div>
            )}
            {chart.error && <ErrorNote>{apiErrorMessage(chart.error)}</ErrorNote>}
            {chart.data && chart.data.length > 0 && (
              <>
                <CandlestickChart bars={chart.data} showVolume height={380} />
                <p className="mt-2 text-xs text-slate-500">
                  {chart.data.length} barres — {chart.data[0].date} → {chart.data[chart.data.length - 1].date}
                </p>
              </>
            )}
          </Card>
        </div>
      )}
    </div>
  )
}
