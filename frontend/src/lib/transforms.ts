/** Transformations OHLC pures — Heikin Ashi, Kagi, Line Break, Range.
 *
 * Port direct des fonctions `toHeikinAshi`/`toLineBreak`/`toRangeBars`/`toKagi` de
 * `app/static/dashboard.html` (voir ce fichier pour les commentaires détaillés sur chaque
 * algorithme), déjà vérifiées contre des valeurs calculées à la main dans
 * `tests/js/test_transforms.js`. Aucune de ces fonctions ne touche au DOM ni au réseau : elles
 * prennent un tableau de barres {date,open,high,low,close,volume} et renvoient un nouveau
 * tableau — gardées identiques ici pour que les deux implémentations ne divergent pas.
 */

export interface Bar {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume?: number | null
}

export interface Box {
  date: string
  open: number
  close: number
  dir: 1 | -1
}

export interface KagiSegment {
  date: string
  from: number
  to: number
  dir: 1 | -1
  thick: boolean
}

/** Heikin Ashi : bougies lissées.
 *   close_HA = (open+high+low+close)/4
 *   open_HA  = (open_HA[i-1] + close_HA[i-1]) / 2   (première barre : (open+close)/2)
 *   high_HA  = max(high, open_HA, close_HA)
 *   low_HA   = min(low, open_HA, close_HA)
 */
export function toHeikinAshi(bars: Bar[]): Bar[] {
  const out: Bar[] = []
  let prevOpenHA: number | null = null
  let prevCloseHA: number | null = null
  bars.forEach((b, i) => {
    const closeHA = (b.open + b.high + b.low + b.close) / 4
    const openHA = i === 0 ? (b.open + b.close) / 2 : (prevOpenHA! + prevCloseHA!) / 2
    const highHA = Math.max(b.high, openHA, closeHA)
    const lowHA = Math.min(b.low, openHA, closeHA)
    out.push({ date: b.date, open: openHA, high: highHA, low: lowHA, close: closeHA })
    prevOpenHA = openHA
    prevCloseHA = closeHA
  })
  return out
}

/** Line Break à N lignes (par défaut 3). Chaque brique compare la clôture courante aux
 * extrêmes (min/max des ouvertures ET clôtures) des N briques précédentes dans la direction en
 * cours : un nouveau bloc dans le même sens s'ajoute dès que la clôture dépasse la clôture de la
 * dernière brique ; un retournement n'a lieu que si la clôture franchit l'extrême opposé des N
 * dernières briques (pas seulement la précédente) — c'est ce qui distingue le "N-line break" du
 * simple "3 pas". Opère sur les clôtures uniquement.
 */
export function toLineBreak(bars: Bar[], n = 3): Box[] {
  if (!bars.length) return []
  const boxes: Box[] = [{ open: bars[0].close, close: bars[0].close, dir: 1, date: bars[0].date }]
  for (let i = 1; i < bars.length; i++) {
    const c = bars[i].close
    const last = boxes[boxes.length - 1]
    const window_ = boxes.slice(-n)
    if (last.dir === 1) {
      if (c > last.close) {
        boxes.push({ open: last.close, close: c, dir: 1, date: bars[i].date })
      } else if (c < Math.min(...window_.map((b) => Math.min(b.open, b.close)))) {
        boxes.push({ open: last.close, close: c, dir: -1, date: bars[i].date })
      }
    } else {
      if (c < last.close) {
        boxes.push({ open: last.close, close: c, dir: -1, date: bars[i].date })
      } else if (c > Math.max(...window_.map((b) => Math.max(b.open, b.close)))) {
        boxes.push({ open: last.close, close: c, dir: 1, date: bars[i].date })
      }
    }
  }
  return boxes
}

/** Range bars (variante Renko à taille de bloc fixe, en unité de prix — pas en temps). Chaque
 * bloc se ferme dès que l'amplitude (plus haut - plus bas) atteint `rangeSize` depuis son
 * ouverture ; le bloc suivant repart de la clôture du précédent. `rangeSize` doit être positif
 * et dans l'unité du prix affiché.
 */
export function toRangeBars(bars: Bar[], rangeSize: number): Box[] {
  if (!bars.length || !(rangeSize > 0)) return []
  const out: Box[] = []
  let open = bars[0].close
  let high = open
  let low = open
  for (let i = 1; i < bars.length; i++) {
    const c = bars[i].close
    high = Math.max(high, c)
    low = Math.min(low, c)
    if (high - low >= rangeSize) {
      const dir: 1 | -1 = c >= open ? 1 : -1
      const close = dir === 1 ? open + rangeSize : open - rangeSize
      out.push({ open, close, dir, date: bars[i].date })
      open = close
      high = close
      low = close
    }
  }
  return out
}

/** Kagi. `reversal` est le seuil de retournement (montant fixe si `reversalType==="amount"`,
 * pourcentage du prix courant si `"percent"`). Une ligne reste fine (yin) tant que le prix ne
 * dépasse pas la précédente "épaule" haute, et devient épaisse (yang) dès qu'il la franchit —
 * symétriquement pour les épaules basses en cas de baisse. L'épaisseur ne change donc PAS à
 * chaque simple retournement, seulement au franchissement d'une épaule antérieure.
 */
export function toKagi(bars: Bar[], reversal: number, reversalType: 'amount' | 'percent' = 'amount'): KagiSegment[] {
  const closes = bars.map((b) => b.close)
  if (closes.length < 2) return []
  const revAmt = (price: number) => (reversalType === 'percent' ? (Math.abs(price) * reversal) / 100 : reversal)

  let dir: 1 | -1 = closes[1] >= closes[0] ? 1 : -1
  let extreme = dir === 1 ? Math.max(closes[0], closes[1]) : Math.min(closes[0], closes[1])
  let thick = true
  let highShoulder = -Infinity
  let lowShoulder = Infinity
  const segments: KagiSegment[] = [{ from: closes[0], to: extreme, dir, thick, date: bars[1].date }]

  for (let i = 2; i < closes.length; i++) {
    const c = closes[i]
    const cur = segments[segments.length - 1]
    if (dir === 1) {
      if (c >= extreme) {
        extreme = c
        if (extreme > highShoulder) thick = true
        cur.to = extreme
        cur.thick = thick
        cur.date = bars[i].date
      } else if (extreme - c >= revAmt(extreme)) {
        highShoulder = extreme
        dir = -1
        if (Number.isFinite(lowShoulder) && c < lowShoulder) thick = false
        segments.push({ from: extreme, to: c, dir, thick, date: bars[i].date })
        extreme = c
      }
    } else {
      if (c <= extreme) {
        extreme = c
        if (extreme < lowShoulder) thick = false
        cur.to = extreme
        cur.thick = thick
        cur.date = bars[i].date
      } else if (c - extreme >= revAmt(extreme)) {
        lowShoulder = extreme
        dir = 1
        if (Number.isFinite(highShoulder) && c > highShoulder) thick = true
        segments.push({ from: extreme, to: c, dir, thick, date: bars[i].date })
        extreme = c
      }
    }
  }
  return segments
}

/** Boîtes (Line Break / Range) -> forme Bar, pour les afficher avec `CandlestickChart` : un
 * corps plein sans mèche (high=max(open,close), low=min(open,close)) rend exactement le même
 * rectangle que `drawBoxSeries` dans l'ancien tableau de bord. `dir` coïncide toujours avec
 * `close >= open` pour ces deux transformations (vérifié par construction dans `toLineBreak`/
 * `toRangeBars`), donc la coloration haussier/baissier automatique de `CandlestickChart` (basée
 * sur open/close) reproduit exactement celle de `drawBoxSeries` (basée sur `dir`), sans code de
 * couleur spécifique à ajouter. */
export function boxesToBars(boxes: Box[]): Bar[] {
  return boxes.map((b) => ({
    date: b.date,
    open: b.open,
    close: b.close,
    high: Math.max(b.open, b.close),
    low: Math.min(b.open, b.close),
  }))
}

/** Segments Kagi -> forme Bar (open=from, close=to), pour les afficher avec `CandlestickChart`
 * comme un enchaînement de mouvements colorés haussier/baissier. L'épaisseur fine/épaisse
 * (yin/yang) n'a pas d'équivalent direct dans un graphique en bougies : elle est affichée à part,
 * en liste, par `AdvancedChartPage` (voir `KagiLegend`) plutôt que perdue silencieusement. */
export function kagiToBars(segments: KagiSegment[]): Bar[] {
  return segments.map((s) => ({
    date: s.date,
    open: s.from,
    close: s.to,
    high: Math.max(s.from, s.to),
    low: Math.min(s.from, s.to),
  }))
}
