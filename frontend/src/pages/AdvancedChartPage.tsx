import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { api, apiErrorMessage } from '../api/client'
import { CandlestickChart } from '../components/CandlestickChart'
import { Card, ErrorNote, Placeholder, Spinner } from '../components/ui'
import { WatchlistButton } from '../components/WatchlistButton'
import { boxesToBars, kagiToBars, toHeikinAshi, toKagi, toLineBreak, toRangeBars } from '../lib/transforms'

type RepType = 'candlestick' | 'heikinashi' | 'linebreak' | 'range' | 'kagi'
const REP_LABELS: Record<RepType, string> = {
  candlestick: 'Bougies japonaises',
  heikinashi: 'Heikin Ashi',
  linebreak: 'Line Break',
  range: 'Range bars',
  kagi: 'Kagi',
}

type Period = '6mo' | '1y' | '2y' | '5y' | 'max'
const PERIODS: { value: Period; label: string }[] = [
  { value: '6mo', label: '6 mois' },
  { value: '1y', label: '1 an' },
  { value: '2y', label: '2 ans' },
  { value: '5y', label: '5 ans' },
  { value: 'max', label: 'Historique complet' },
]

export default function AdvancedChartPage() {
  const [params, setParams] = useSearchParams()
  const code = params.get('code') ?? ''
  const [submittedCode, setSubmittedCode] = useState(code || null)
  const [period, setPeriod] = useState<Period>('1y')
  const [rep, setRep] = useState<RepType>('candlestick')
  const [lineBreakN, setLineBreakN] = useState(3)
  const [rangeSize, setRangeSize] = useState(1)
  const [kagiAmount, setKagiAmount] = useState(4)
  const [kagiType, setKagiType] = useState<'amount' | 'percent'>('amount')

  const ohlc = useQuery({
    queryKey: ['ohlc-adv', submittedCode, period],
    enabled: !!submittedCode,
    queryFn: async () => {
      const { data, error } = await api.GET('/ohlc/{indicator_code}', {
        params: { path: { indicator_code: submittedCode! }, query: { period } },
      })
      if (error) throw error
      return data
    },
  })

  const kagiSegments = useMemo(() => {
    if (rep !== 'kagi' || !ohlc.data) return []
    return toKagi(ohlc.data, kagiAmount, kagiType)
  }, [rep, ohlc.data, kagiAmount, kagiType])

  const displayBars = useMemo(() => {
    if (!ohlc.data) return []
    switch (rep) {
      case 'candlestick':
        return ohlc.data
      case 'heikinashi':
        return toHeikinAshi(ohlc.data)
      case 'linebreak':
        return boxesToBars(toLineBreak(ohlc.data, lineBreakN))
      case 'range':
        return boxesToBars(toRangeBars(ohlc.data, rangeSize))
      case 'kagi':
        return kagiToBars(kagiSegments)
    }
  }, [rep, ohlc.data, lineBreakN, rangeSize, kagiSegments])

  function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setParams(code ? { code } : {})
    setSubmittedCode(code || null)
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold text-slate-100">Graphiques avancés</h1>
      <p className="max-w-3xl text-sm text-slate-400">
        Représentations alternatives de l'historique quotidien — utiles pour filtrer le bruit (Heikin Ashi), ignorer le
        temps au profit du seul mouvement de prix (Line Break, Range bars), ou repérer les retournements significatifs
        (Kagi). Aucune n'a de valeur prédictive en soi : ce sont des lectures différentes des mêmes données.
      </p>

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
        <Card>
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <select
              value={rep}
              onChange={(e) => setRep(e.target.value as RepType)}
              className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
            >
              {Object.entries(REP_LABELS).map(([v, label]) => (
                <option key={v} value={v}>
                  {label}
                </option>
              ))}
            </select>
            <select
              value={period}
              onChange={(e) => setPeriod(e.target.value as Period)}
              className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
            >
              {PERIODS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>

            {rep === 'linebreak' && (
              <label className="flex items-center gap-2 text-sm text-slate-300">
                Lignes :
                <input
                  type="number"
                  min={2}
                  max={10}
                  value={lineBreakN}
                  onChange={(e) => setLineBreakN(Math.max(2, parseInt(e.target.value, 10) || 3))}
                  className="w-16 rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
                />
              </label>
            )}
            {rep === 'range' && (
              <label className="flex items-center gap-2 text-sm text-slate-300">
                Taille de bloc :
                <input
                  type="number"
                  min={0.001}
                  step={0.01}
                  value={rangeSize}
                  onChange={(e) => setRangeSize(Math.max(0.001, parseFloat(e.target.value) || 1))}
                  className="w-20 rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
                />
              </label>
            )}
            {rep === 'kagi' && (
              <label className="flex items-center gap-2 text-sm text-slate-300">
                Seuil :
                <input
                  type="number"
                  min={0.001}
                  step={0.01}
                  value={kagiAmount}
                  onChange={(e) => setKagiAmount(Math.max(0.001, parseFloat(e.target.value) || 1))}
                  className="w-20 rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
                />
                <select
                  value={kagiType}
                  onChange={(e) => setKagiType(e.target.value as 'amount' | 'percent')}
                  className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
                >
                  <option value="amount">montant</option>
                  <option value="percent">%</option>
                </select>
              </label>
            )}
          </div>

          {ohlc.isLoading && (
            <div className="flex items-center gap-2 text-slate-400">
              <Spinner /> Chargement de l'historique…
            </div>
          )}
          {ohlc.error && <ErrorNote>{apiErrorMessage(ohlc.error)}</ErrorNote>}
          {ohlc.data && displayBars.length === 0 && (
            <Placeholder>Pas assez de données pour cette transformation avec ces paramètres.</Placeholder>
          )}
          {ohlc.data && displayBars.length > 0 && (
            <>
              <CandlestickChart bars={displayBars} showVolume={rep === 'candlestick'} height={420} />
              <p className="mt-2 text-xs text-slate-500">
                {displayBars.length} {rep === 'candlestick' ? 'barres' : 'segments'} — {displayBars[0].date} →{' '}
                {displayBars[displayBars.length - 1].date}
              </p>
            </>
          )}

          {rep === 'kagi' && kagiSegments.length > 0 && (
            <div className="mt-4 border-t border-slate-800 pt-3">
              <p className="mb-2 text-xs text-slate-500">
                Épaisseur de chaque mouvement (perdue dans le rendu en bougies ci-dessus, faute d'épaisseur de trait
                variable par point dans la librairie de graphique) — <b>épais / yang</b> : franchit l'épaule
                antérieure dans le même sens ; <b>fin / yin</b> : simple retournement.
              </p>
              <div className="flex max-h-40 flex-wrap gap-x-4 gap-y-1 overflow-y-auto text-xs">
                {kagiSegments.map((s, i) => (
                  <span key={i} className="font-mono tabular-nums text-slate-400">
                    {s.date} {s.from.toFixed(2)}→{s.to.toFixed(2)}{' '}
                    <span className={s.thick ? 'text-emerald-400' : 'text-slate-500'}>
                      {s.thick ? '●épais' : '○fin'}
                    </span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </Card>
      )}
    </div>
  )
}
