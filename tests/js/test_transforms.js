/* Tests unitaires purs (aucune dépendance npm) des fonctions de transformation OHLC du
 * tableau de bord (toHeikinAshi, toLineBreak, toRangeBars, toKagi) : extrait le <script> de
 * app/static/dashboard.html et l'exécute dans un bac à sable minimal (pas de vrai DOM, pas de
 * réseau), puis vérifie le résultat contre des valeurs calculées à la main.
 *
 * Lancer : node tests/js/test_transforms.js
 */
"use strict";
const vm = require("vm");
const fs = require("fs");
const path = require("path");
const assert = require("assert");

process.on("unhandledRejection", () => {}); // l'amorçage du tableau de bord tente un fetch("/health") au chargement ; sans réseau ici, c'est attendu et sans rapport avec ces tests

const html = fs.readFileSync(path.join(__dirname, "..", "..", "app", "static", "dashboard.html"), "utf8");
const js = html.match(/<script>([\s\S]*)<\/script>/)[1];

function fakeEl() {
  return {
    style: {}, dataset: {}, classList: { add() {}, remove() {} },
    addEventListener() {}, appendChild() {}, querySelector: () => null, querySelectorAll: () => [],
    setAttribute() {}, getAttribute: () => null,
  };
}
const sandbox = {
  console,
  document: {
    documentElement: { style: {} },
    querySelector: () => fakeEl(), querySelectorAll: () => [],
    getElementById: () => fakeEl(), createElement: () => fakeEl(),
    addEventListener() {},
  },
  getComputedStyle: () => ({ getPropertyValue: () => "#000000" }),
  fetch: () => Promise.reject(new Error("pas de réseau en test unitaire")),
  Intl, Math, JSON, Object, Array, Number, String, Date, Map, Set, Proxy,
  setTimeout, clearTimeout, devicePixelRatio: 1,
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(js, sandbox);

let failures = 0;
function check(name, actual, expected) {
  // Passage par JSON pour neutraliser l'artefact "cross-realm" du bac à sable vm (les tableaux
  // créés dans le contexte isolé ne sont pas des `Array` du point de vue de `assert` du process
  // hôte) — ceci ne change rien aux VALEURS comparées, seulement à leur représentation.
  const a = JSON.parse(JSON.stringify(actual));
  const e = JSON.parse(JSON.stringify(expected));
  try {
    assert.deepStrictEqual(a, e);
    console.log(`  ok — ${name}`);
  } catch (err) {
    failures++;
    console.log(`  ÉCHEC — ${name}`);
    console.log(`    attendu : ${JSON.stringify(e)}`);
    console.log(`    obtenu  : ${JSON.stringify(a)}`);
  }
}
function approxCheck(name, actual, expected, places = 6) {
  const round = (v) => Math.round(v * 10 ** places) / 10 ** places;
  check(name, round(actual), round(expected));
}

console.log("=== toHeikinAshi ===");
{
  const bars = [
    { date: "d0", open: 10, high: 12, low: 9, close: 11 },
    { date: "d1", open: 11, high: 13, low: 10, close: 12 },
  ];
  const ha = sandbox.toHeikinAshi(bars);
  approxCheck("closeHA[0] = (10+12+9+11)/4", ha[0].close, 10.5);
  approxCheck("openHA[0] = (10+11)/2 (première barre)", ha[0].open, 10.5);
  approxCheck("highHA[0] = max(12, 10.5, 10.5)", ha[0].high, 12);
  approxCheck("lowHA[0] = min(9, 10.5, 10.5)", ha[0].low, 9);
  approxCheck("closeHA[1] = (11+13+10+12)/4", ha[1].close, 11.5);
  approxCheck("openHA[1] = (openHA0+closeHA0)/2", ha[1].open, 10.5);
  approxCheck("highHA[1] = max(13, 10.5, 11.5)", ha[1].high, 13);
  approxCheck("lowHA[1] = min(10, 10.5, 11.5)", ha[1].low, 10);
}

console.log("=== toLineBreak (n=3) ===");
{
  const closes = [10, 12, 11, 13, 9, 8, 7, 15];
  const bars = closes.map((c, i) => ({ date: "d" + i, close: c }));
  const boxes = sandbox.toLineBreak(bars, 3);
  check("nombre de briques", boxes.length, 7);
  check("directions successives", boxes.map(b => b.dir), [1, 1, 1, -1, -1, -1, 1]);
  check("brique 0 (initiale)", [boxes[0].open, boxes[0].close], [10, 10]);
  check("brique 1 (extension haussière, 12>10)", [boxes[1].open, boxes[1].close], [10, 12]);
  check("brique 3 (retournement : 9 < min des 3 dernières = 10)", [boxes[3].open, boxes[3].close], [13, 9]);
  check("brique 6 (retournement : 15 > max des 3 dernières = 13)", [boxes[6].open, boxes[6].close], [7, 15]);
}

console.log("=== toRangeBars (taille 1.5) ===");
{
  const closes = [100, 100.5, 101.2, 101.8, 99, 98.5, 102.5];
  const bars = closes.map((c, i) => ({ date: "d" + i, close: c }));
  const boxes = sandbox.toRangeBars(bars, 1.5);
  check("nombre de blocs", boxes.length, 4);
  approxCheck("bloc 0 : ouverture", boxes[0].open, 100);
  approxCheck("bloc 0 : clôture (100+1.5, haussier)", boxes[0].close, 101.5);
  check("bloc 0 : direction haussière", boxes[0].dir, 1);
  approxCheck("bloc 1 : clôture (101.5-1.5, baissier)", boxes[1].close, 100);
  check("bloc 1 : direction baissière", boxes[1].dir, -1);
  approxCheck("bloc 3 : clôture (98.5+1.5, haussier)", boxes[3].close, 100);
  check("bloc 3 : direction haussière", boxes[3].dir, 1);
}

console.log("=== toKagi (seuil = 2, montant fixe) ===");
{
  const closes = [100, 105, 103, 108, 102, 110];
  const bars = closes.map((c, i) => ({ date: "d" + i, close: c }));
  const seg = sandbox.toKagi(bars, 2, "amount");
  check("nombre de segments", seg.length, 5);
  check("segment 0 : 100 -> 105, hausse, épais (initial)", [seg[0].from, seg[0].to, seg[0].dir, seg[0].thick], [100, 105, 1, true]);
  check("segment 1 : 105 -> 103, baisse, encore épais (pas d'épaule basse antérieure)", [seg[1].from, seg[1].to, seg[1].dir, seg[1].thick], [105, 103, -1, true]);
  check("segment 2 : 103 -> 108, hausse, franchit l'épaule haute (105) : épais", [seg[2].from, seg[2].to, seg[2].dir, seg[2].thick], [103, 108, 1, true]);
  check("segment 3 : 108 -> 102, baisse, franchit l'épaule basse (103) : devient FIN", [seg[3].from, seg[3].to, seg[3].dir, seg[3].thick], [108, 102, -1, false]);
  check("segment 4 : 102 -> 110, hausse, franchit l'épaule haute (108) : redevient ÉPAIS", [seg[4].from, seg[4].to, seg[4].dir, seg[4].thick], [102, 110, 1, true]);
}

console.log("=== formatage de la fiche cotation ===");
{
  // certains helpers sont des `const` (portée lexicale du script) : on les évalue dans le même contexte
  const ev = (expr) => vm.runInContext(expr, sandbox);
  check("fmtBig milliards", ev("fmtBig(153703000000)"), "153,703 Md");
  check("fmtBig millions", ev("fmtBig(2500000)"), "2,5 M");
  check("fmtBig valeur absente", ev("fmtBig(null)"), "—");
  check("fmtCompact millions (axe volume)", ev("fmtCompact(1234567)"), "1,2 M");
  check("fmtCompact milliers", ev("fmtCompact(2000)"), "2 k");
  check("axisLabel 1D = heure", ev('axisLabel("1D", "2026-09-28 17:14")'), "17:14");
  check("axisLabel 5D = jour + heure", ev('axisLabel("5D", "2026-09-28 17:14")'), "28/09 17:14");
  check("axisLabel période longue contient l'année", ev('axisLabel("1Y", "2026-09-28")').includes("2026"), true);
  check("bracketStamp date + heure", ev('bracketStamp("2026-09-28 17:14")'), "[28/09/2026 17:14]");
  check("bracketStamp date seule", ev('bracketStamp("2026-09-28")'), "[28/09/2026]");
  check("bracketStamp heure seule", ev('bracketStamp("16:22")'), "[16:22]");
  check("bracketStamp vide", ev('bracketStamp("")'), "");
  check("fmtPrice action (2 décimales fixes)", ev("fmtPrice(194)"), "194,00");
  check("fmtPrice paire de devises (4 décimales)", ev("fmtPrice(1.0812)"), "1,0812");
}

console.log();
if (failures) {
  console.log(`❌ ${failures} échec(s)`);
  process.exit(1);
} else {
  console.log("✅ tous les tests passent");
}
