/** Vérification ad hoc du port TypeScript de src/lib/transforms.ts contre les mêmes valeurs
 * calculées à la main que tests/js/test_transforms.js (qui teste la version dashboard.html de
 * ces mêmes fonctions) — à lancer avec `npx tsx scripts/transforms.selfcheck.ts`. Hors de `src/`
 * et donc hors de `tsc -b`/`vite build` : pas un test automatisé du projet (pas de harnais de
 * test frontend configuré), juste un script de vérification ponctuelle pour le port, gardé ici
 * pour pouvoir le relancer si `transforms.ts` est retouché. */
import { toHeikinAshi, toKagi, toLineBreak, toRangeBars } from '../src/lib/transforms'

let failures = 0
function check(name: string, actual: unknown, expected: unknown) {
  const a = JSON.stringify(actual)
  const e = JSON.stringify(expected)
  if (a === e) {
    console.log(`  ok — ${name}`)
  } else {
    failures++
    console.log(`  ÉCHEC — ${name}\n    attendu : ${e}\n    obtenu  : ${a}`)
  }
}
function approxCheck(name: string, actual: number, expected: number, places = 6) {
  const round = (v: number) => Math.round(v * 10 ** places) / 10 ** places
  check(name, round(actual), round(expected))
}

console.log('=== toHeikinAshi ===')
{
  const bars = [
    { date: 'd0', open: 10, high: 12, low: 9, close: 11 },
    { date: 'd1', open: 11, high: 13, low: 10, close: 12 },
  ]
  const ha = toHeikinAshi(bars)
  approxCheck('closeHA[0] = (10+12+9+11)/4', ha[0].close, 10.5)
  approxCheck('openHA[0] = (10+11)/2 (première barre)', ha[0].open, 10.5)
  approxCheck('highHA[0] = max(12, 10.5, 10.5)', ha[0].high, 12)
  approxCheck('lowHA[0] = min(9, 10.5, 10.5)', ha[0].low, 9)
  approxCheck('closeHA[1] = (11+13+10+12)/4', ha[1].close, 11.5)
  approxCheck('openHA[1] = (openHA0+closeHA0)/2', ha[1].open, 10.5)
  approxCheck('highHA[1] = max(13, 10.5, 11.5)', ha[1].high, 13)
  approxCheck('lowHA[1] = min(10, 10.5, 11.5)', ha[1].low, 10)
}

console.log('=== toLineBreak (n=3) ===')
{
  const closes = [10, 12, 11, 13, 9, 8, 7, 15]
  const bars = closes.map((c, i) => ({ date: 'd' + i, open: c, high: c, low: c, close: c }))
  const boxes = toLineBreak(bars, 3)
  check('nombre de briques', boxes.length, 7)
  check('directions successives', boxes.map((b) => b.dir), [1, 1, 1, -1, -1, -1, 1])
  check('brique 0 (initiale)', [boxes[0].open, boxes[0].close], [10, 10])
  check('brique 1 (extension haussière, 12>10)', [boxes[1].open, boxes[1].close], [10, 12])
  check('brique 3 (retournement : 9 < min des 3 dernières = 10)', [boxes[3].open, boxes[3].close], [13, 9])
  check('brique 6 (retournement : 15 > max des 3 dernières = 13)', [boxes[6].open, boxes[6].close], [7, 15])
}

console.log('=== toRangeBars (taille 1.5) ===')
{
  const closes = [100, 100.5, 101.2, 101.8, 99, 98.5, 102.5]
  const bars = closes.map((c, i) => ({ date: 'd' + i, open: c, high: c, low: c, close: c }))
  const boxes = toRangeBars(bars, 1.5)
  check('nombre de blocs', boxes.length, 4)
  approxCheck('bloc 0 : ouverture', boxes[0].open, 100)
  approxCheck('bloc 0 : clôture (100+1.5, haussier)', boxes[0].close, 101.5)
  check('bloc 0 : direction haussière', boxes[0].dir, 1)
  approxCheck('bloc 1 : clôture (101.5-1.5, baissier)', boxes[1].close, 100)
  check('bloc 1 : direction baissière', boxes[1].dir, -1)
  approxCheck('bloc 3 : clôture (98.5+1.5, haussier)', boxes[3].close, 100)
  check('bloc 3 : direction haussière', boxes[3].dir, 1)
}

console.log('=== toKagi (seuil = 2, montant fixe) ===')
{
  const closes = [100, 105, 103, 108, 102, 110]
  const bars = closes.map((c, i) => ({ date: 'd' + i, open: c, high: c, low: c, close: c }))
  const seg = toKagi(bars, 2, 'amount')
  check('nombre de segments', seg.length, 5)
  check('segment 0 : 100 -> 105, hausse, épais (initial)', [seg[0].from, seg[0].to, seg[0].dir, seg[0].thick], [100, 105, 1, true])
  check('segment 1 : 105 -> 103, baisse, encore épais', [seg[1].from, seg[1].to, seg[1].dir, seg[1].thick], [105, 103, -1, true])
  check("segment 2 : 103 -> 108, hausse, franchit l'épaule haute (105) : épais", [seg[2].from, seg[2].to, seg[2].dir, seg[2].thick], [103, 108, 1, true])
  check("segment 3 : 108 -> 102, baisse, franchit l'épaule basse (103) : devient FIN", [seg[3].from, seg[3].to, seg[3].dir, seg[3].thick], [108, 102, -1, false])
  check("segment 4 : 102 -> 110, hausse, franchit l'épaule haute (108) : redevient ÉPAIS", [seg[4].from, seg[4].to, seg[4].dir, seg[4].thick], [102, 110, 1, true])
}

console.log()
if (failures) {
  console.log(`❌ ${failures} échec(s)`)
  process.exit(1)
} else {
  console.log('✅ tous les tests passent')
}
