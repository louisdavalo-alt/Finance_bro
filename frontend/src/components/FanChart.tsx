import { useEffect, useRef } from 'react'

/** Éventail Monte Carlo (bootstrap par blocs) : bande 5–95 %, bande 25–75 % (plus sombre),
 * ligne médiane, repère à 0 %, jour par jour sur l'horizon de simulation. Port direct de
 * `drawMonteCarloFan` dans `app/static/dashboard.html` — en Canvas plutôt qu'avec
 * lightweight-charts, qui n'a pas de notion native de "bande entre deux courbes" (seulement une
 * zone colorée jusqu'à UNE valeur de base fixe, pas jusqu'à une autre série). */
export function FanChart({
  fan,
  horizonDays,
  height = 260,
}: {
  fan: Record<string, number[]>
  horizonDays: number
  height?: number
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const container = containerRef.current
    const canvas = canvasRef.current
    if (!container || !canvas) return

    function draw() {
      const w = container!.clientWidth
      const dpr = window.devicePixelRatio || 1
      canvas!.width = w * dpr
      canvas!.height = height * dpr
      canvas!.style.width = `${w}px`
      canvas!.style.height = `${height}px`
      const ctx = canvas!.getContext('2d')
      if (!ctx) return
      ctx.scale(dpr, dpr)
      ctx.clearRect(0, 0, w, height)

      const allVals = [...fan['5'], ...fan['95'], 0]
      let lo = Math.min(...allVals)
      let hi = Math.max(...allVals)
      const pad = (hi - lo) * 0.08 || 1
      lo -= pad
      hi += pad

      const L = 48
      const R = 12
      const T = 10
      const B = 24
      const x = (i: number) => L + (i / (horizonDays - 1)) * (w - L - R)
      const y = (v: number) => T + (1 - (v - lo) / (hi - lo)) * (height - T - B)

      // grille horizontale + axe des valeurs
      ctx.strokeStyle = '#334155'
      ctx.fillStyle = '#64748b'
      ctx.font = '11px ui-monospace, monospace'
      ctx.textAlign = 'right'
      ctx.textBaseline = 'middle'
      const steps = 4
      for (let i = 0; i <= steps; i++) {
        const v = lo + ((hi - lo) * i) / steps
        const yy = y(v)
        ctx.beginPath()
        ctx.moveTo(L, yy)
        ctx.lineTo(w - R, yy)
        ctx.globalAlpha = 0.5
        ctx.stroke()
        ctx.globalAlpha = 1
        ctx.fillText(`${v.toFixed(0)} %`, L - 6, yy)
      }

      const band = (lowKey: string, highKey: string, alpha: number) => {
        ctx!.beginPath()
        for (let i = 0; i < horizonDays; i++) {
          const px = x(i)
          const py = y(fan[highKey][i])
          i === 0 ? ctx!.moveTo(px, py) : ctx!.lineTo(px, py)
        }
        for (let i = horizonDays - 1; i >= 0; i--) ctx!.lineTo(x(i), y(fan[lowKey][i]))
        ctx!.closePath()
        ctx!.fillStyle = '#38bdf8'
        ctx!.globalAlpha = alpha
        ctx!.fill()
        ctx!.globalAlpha = 1
      }
      band('5', '95', 0.12)
      band('25', '75', 0.26)

      // ligne médiane
      ctx.beginPath()
      ctx.strokeStyle = '#38bdf8'
      ctx.lineWidth = 1.8
      for (let i = 0; i < horizonDays; i++) {
        const px = x(i)
        const py = y(fan['50'][i])
        i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py)
      }
      ctx.stroke()

      // repère à 0 %
      if (lo < 0 && hi > 0) {
        ctx.beginPath()
        ctx.strokeStyle = '#64748b'
        ctx.setLineDash([3, 3])
        ctx.lineWidth = 1
        ctx.moveTo(L, y(0))
        ctx.lineTo(w - R, y(0))
        ctx.stroke()
        ctx.setLineDash([])
      }
    }

    draw()
    const observer = new ResizeObserver(draw)
    observer.observe(container)
    return () => observer.disconnect()
  }, [fan, horizonDays, height])

  return (
    <div ref={containerRef} style={{ height }}>
      <canvas ref={canvasRef} />
    </div>
  )
}
