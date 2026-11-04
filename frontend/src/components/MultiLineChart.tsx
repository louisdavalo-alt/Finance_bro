import { createChart, LineSeries, type IChartApi, type ISeriesApi, type Time } from 'lightweight-charts'
import { useEffect, useRef } from 'react'

export interface LineSeriesSpec {
  label: string
  color: string
  points: { date: string; y: number | null }[]
}

/** Plusieurs séries superposées sur le même repère (même échelle de prix) — pour comparer des
 * indicateurs dont les unités diffèrent, les séries doivent déjà être normalisées avant
 * d'arriver ici (voir ComparePage : base 100 à la première valeur disponible, comme l'ancien
 * tableau de bord). Un point `y: null` crée un trou dans la ligne plutôt que de l'interpoler. */
export function MultiLineChart({ series, height = 380 }: { series: LineSeriesSpec[]; height?: number }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRefs = useRef<ISeriesApi<'Line'>[]>([])

  useEffect(() => {
    if (!containerRef.current) return
    const chart = createChart(containerRef.current, {
      height,
      layout: { background: { color: 'transparent' }, textColor: '#94a3b8' },
      grid: { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
      rightPriceScale: { borderColor: '#334155' },
      timeScale: { borderColor: '#334155' },
    })
    chartRef.current = chart

    const resize = () => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth })
    }
    resize()
    const observer = new ResizeObserver(resize)
    observer.observe(containerRef.current)

    return () => {
      observer.disconnect()
      chart.remove()
      seriesRefs.current = []
    }
  }, [height])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    seriesRefs.current.forEach((s) => chart.removeSeries(s))
    seriesRefs.current = series.map((spec) => {
      const line = chart.addSeries(LineSeries, { color: spec.color, lineWidth: 2 })
      line.setData(
        spec.points
          .filter((p) => p.y !== null && p.y !== undefined && Number.isFinite(p.y))
          .map((p) => ({ time: p.date as Time, value: p.y as number })),
      )
      return line
    })
    chart.timeScale().fitContent()
  }, [series])

  return <div ref={containerRef} />
}
