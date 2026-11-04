import {
  CandlestickSeries,
  createChart,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts'
import { useEffect, useRef } from 'react'

export interface Bar {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume?: number | null
}

/** `date` est soit une date seule ("2026-01-02", séries quotidiennes/hebdo) soit une date+heure
 * ("2026-01-02 09:05", séries intraday 1D/5D — voir `app/quote.py::frame_to_bars`).
 * lightweight-charts accepte une chaîne "YYYY-MM-DD" telle quelle pour une série quotidienne,
 * mais a besoin d'un timestamp numérique pour placer un point à une heure précise. */
function toChartTime(date: string): Time {
  if (date.length > 10) {
    return (Math.floor(new Date(date.replace(' ', 'T')).getTime() / 1000)) as UTCTimestamp
  }
  return date as Time
}

/** Chandelier TradingView lightweight-charts — fait pour exactement ce cas d'usage (OHLC
 * financier), plutôt qu'une lib de charting générique. Le graphique se redimensionne avec son
 * conteneur et se détruit proprement au démontage. Volume optionnel, en histogramme sous les
 * bougies (`showVolume`), coloré comme la bougie du jour. */
export function CandlestickChart({
  bars,
  height = 320,
  showVolume = false,
}: {
  bars: Bar[]
  height?: number
  showVolume?: boolean
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)

  useEffect(() => {
    if (!containerRef.current) return
    const chart = createChart(containerRef.current, {
      height,
      layout: { background: { color: 'transparent' }, textColor: '#94a3b8' },
      grid: { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
      rightPriceScale: { borderColor: '#334155' },
      timeScale: { borderColor: '#334155' },
    })
    const series = chart.addSeries(CandlestickSeries, {
      upColor: '#22c55e', downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#22c55e', wickDownColor: '#ef4444',
    })
    chartRef.current = chart
    seriesRef.current = series

    if (showVolume) {
      const volumeSeries = chart.addSeries(HistogramSeries, {
        priceFormat: { type: 'volume' },
        priceScaleId: 'volume',
      })
      chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } })
      volumeSeriesRef.current = volumeSeries
    }

    const resize = () => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth })
    }
    resize()
    const observer = new ResizeObserver(resize)
    observer.observe(containerRef.current)

    return () => {
      observer.disconnect()
      chart.remove()
      volumeSeriesRef.current = null
    }
  }, [height, showVolume])

  useEffect(() => {
    if (!seriesRef.current) return
    seriesRef.current.setData(
      bars.map((b) => ({ time: toChartTime(b.date), open: b.open, high: b.high, low: b.low, close: b.close })),
    )
    if (volumeSeriesRef.current) {
      volumeSeriesRef.current.setData(
        bars.map((b) => ({
          time: toChartTime(b.date),
          value: b.volume ?? 0,
          color: b.close >= b.open ? 'rgba(34, 197, 94, 0.5)' : 'rgba(239, 68, 68, 0.5)',
        })),
      )
    }
    chartRef.current?.timeScale().fitContent()
  }, [bars])

  return <div ref={containerRef} />
}
