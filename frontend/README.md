# Finance Bro — frontend

React + TypeScript + Vite. Remplace progressivement `app/static/dashboard.html` (toujours servi
tel quel par l'API en attendant que chaque onglet soit porté ici).

## Stack

- **React 19 + TypeScript + Vite** — build et dev server.
- **TanStack Query** — cache/chargement des appels à l'API FastAPI (`useQuery`), gère lui-même le
  statut de chargement/erreur/revalidation.
- **openapi-fetch + openapi-typescript** — client HTTP **entièrement typé**, généré depuis
  `/openapi.json` de l'API (`app/schemas.py` côté backend). Aucun type écrit à la main pour les
  réponses de l'API : s'il manque un champ ou que le backend change de forme, `tsc` le signale à
  la compilation, pas en production.
- **Tailwind CSS v4** (via `@tailwindcss/vite`, pas de `tailwind.config.js` à maintenir).
- **lightweight-charts** (TradingView) — graphiques financiers (chandeliers), pas une lib de
  charting générique détournée de son usage.
- **React Router** — navigation entre les sections (Indicateurs / Prévision / Portefeuille, à
  étendre au fur et à mesure : Sentiment, Modèles, Paper trading…).

## Démarrer en développement

Deux serveurs en parallèle :

```bash
# Terminal 1 : l'API (depuis la racine du projet)
.venv/bin/uvicorn app.api:app --reload --port 8100

# Terminal 2 : le frontend
cd frontend
npm install   # une seule fois
npm run dev   # http://localhost:5173
```

Le serveur de dev Vite proxifie `/api/*` vers `http://127.0.0.1:8100` (voir `vite.config.ts`) :
pas de CORS à gérer, et c'est transparent pour le code (`src/api/client.ts` utilise toujours la
base `/api`).

## Régénérer les types depuis l'API

Après toute modification d'un modèle dans `app/schemas.py` (ou d'un endpoint) côté backend,
**avec l'API lancée** :

```bash
npm run gen:api
```

Régénère `src/api/schema.d.ts`. Ce fichier est généré — ne pas l'éditer à la main (il est écrasé
au prochain `gen:api`).

## Build de production

```bash
npm run build   # tsc -b && vite build -> dist/
```

Deux façons de le déployer, à choisir plus tard selon ce qui s'intègre le mieux à la suite :
1. Servir `dist/` par FastAPI lui-même (comme `dashboard.html` aujourd'hui) — un seul processus,
   une seule origine, pas de CORS en prod non plus.
2. Un serveur statique séparé (nginx, Caddy) devant l'API — plus proche d'un déploiement "SPA +
   API" classique, utile si le frontend doit un jour être servi par un CDN.

## Structure

```
src/
  api/
    schema.d.ts   généré — types de toutes les requêtes/réponses de l'API
    client.ts     client openapi-fetch typé + aide à l'extraction des messages d'erreur
  components/
    ui.tsx                briques communes (Card, Delta, ErrorNote, Spinner…)
    CandlestickChart.tsx   graphique OHLC (lightweight-charts)
  hooks/
    useWatchlist.ts      liste de suivi personnelle (localStorage), lecture/ajout/retrait
  pages/
    IndicatorsPage.tsx   catalogue des indicateurs collectés (point d'entrée)
    ForecastPage.tsx     GARCH/XGBoost/régime/options/modèles court/moyen/long terme/Kronos pour un indicateur
    PortfolioPage.tsx    constructeur de portefeuille + évaluation Monte Carlo
  App.tsx     layout + navigation + routes
  main.tsx    QueryClientProvider + BrowserRouter
```

## Ce qui reste à porter depuis `dashboard.html`

- ✅ Fiche de cotation (`/quote` + `/chart`, page `QuotePage.tsx`) — tableau façon Euronext +
  `CandlestickChart` (bougies + volume, toutes les plages 1D→MAX).
- ✅ Graphiques avancés (`/ohlc`, page `AdvancedChartPage.tsx`) — Heikin Ashi, Line Break, Range
  bars, Kagi. Transformations portées en TypeScript dans `src/lib/transforms.ts` (vérifiées
  contre les mêmes valeurs calculées à la main que `tests/js/test_transforms.js` — voir
  `scripts/transforms.selfcheck.ts`, `npx tsx scripts/transforms.selfcheck.ts`). Rendues avec
  `CandlestickChart` en mode "corps plein" (Line Break/Range/Kagi n'ont pas de mèche) ; Kagi
  n'a pas d'équivalent d'épaisseur de trait variable dans lightweight-charts, donc l'information
  épais/fin (yang/yin) est listée à part sous le graphique plutôt que perdue.
- ✅ Panneau macro aligné (`/panel`, page `ComparePage.tsx`, onglet « Comparer ») — jusqu'à 5
  indicateurs superposés, rebasés à 100 sur leur première valeur commune, via `MultiLineChart`
  (lightweight-charts, plusieurs `LineSeries`). Rapport de décalage de publication (`/lag-report`,
  page `QualityPage.tsx`, onglet « Qualité ») — tableau triable par colonne.
- ✅ Fan chart de Monte Carlo (`FanChart.tsx`, dans `PortfolioPage.tsx`) — port direct de
  `drawMonteCarloFan` (bande 5–95 %, bande 25–75 % plus sombre, ligne médiane, repère à 0 %),
  en Canvas plutôt qu'avec lightweight-charts (pas de notion native de bande entre deux courbes).

Toutes les vues prévues pour le portage (fiche de cotation, graphiques
avancés, panneau comparatif, qualité, fan chart) sont désormais portées.

## Liste de suivi (watchlist)

`src/hooks/useWatchlist.ts` gère une liste de codes suivis, stockée dans `localStorage` du
navigateur (clé `finance-bro:watchlist`) — pas de compte ni de backend : c'est un outil personnel
sur un seul poste, donc pas de synchronisation entre appareils pour l'instant (si un jour plusieurs
postes doivent partager la même liste, migrer ce hook vers un petit endpoint `/watchlist` +
stockage DuckDB serait direct, même forme que `ohlcv_cache.py`). Le hook expose `list`,
`isWatched(code)`, `add`/`remove`/`toggle(code)`, et se tient à jour entre tous les composants
montés (y compris entre onglets du navigateur) via un événement maison en plus de l'événement
`storage` natif.

- `WatchlistButton` (`src/components/WatchlistButton.tsx`) — bouton texte « ☆ Ajouter à ma liste
  de suivi » / « ★ Dans ma liste de suivi » (bascule), posé sur les pages où une action de marché
  est sélectionnée pour consultation : `QuotePage`, `ForecastPage`, `AdvancedChartPage`.
- `WatchlistStar` — simple étoile cliquable, utilisée dans `IndicatorsPage` (le tableau
  principal) comme première colonne de chaque ligne `yfinance`, pour ajouter/retirer sans quitter
  le tableau.
- `IndicatorsPage` affiche aussi une case « ★ Ma liste de suivi (n) » à côté du filtre texte
  existant, qui restreint le tableau aux seuls codes suivis.

## Modèles court, moyen et long terme (non-IA)

`ForecastPage.tsx` affiche, à côté de GARCH/XGBoost/régime/options, une carte « Modèles court
terme (non-IA) » listant les cinq modèles de `app/forecast/short_term/` (HAR-RV, ARIMA, filtre de
Kalman, Ornstein-Uhlenbeck, retournement) — rendement attendu et écart-type sur l'horizon choisi,
ou le message d'erreur du modèle le cas échéant (`short_term_models`/`short_term_errors` côté
API). À horizon « ~1 mois » uniquement (sélecteur en haut de l'onglet), deux cartes
supplémentaires apparaissent, de la même forme :

- « Modèles moyen terme (non-IA) » : les six modèles de `app/forecast/medium_term/` (Momentum
  12-1, TSMOM, Markov switching, Fama-French 5 + momentum, PEAD, VAR titre/marché).
- « Modèles long terme (non-IA) » : les six modèles de `app/forecast/long_term/` (CAPE de
  Shiller, rendement du dividende, Gordon/DDM, prime de risque implicite, facteurs
  value/profitabilité, cointégration/VECM).

Les trois cartes sont absentes (sauf la première) à horizon « ~1 semaine », où ces modèles ne
tournent pas côté API, et partagent le même composant interne `ModelResultsTable` ;
`SHORT_TERM_MODEL_LABELS`/`MEDIUM_TERM_MODEL_LABELS`/`LONG_TERM_MODEL_LABELS` dans
`ForecastPage.tsx` mappent chaque clé de modèle (`HorizonModel.name` côté backend, ou le nom de
la tâche réseau pour les modèles moyen/long terme réseau) à son libellé d'affichage.

## Rechercher une action absente du catalogue

`MarketSearchPanel` (`src/components/MarketSearchPanel.tsx`), affiché en haut d'`IndicatorsPage`,
permet de chercher une action qui n'est PAS dans le tableau (le catalogue statique de
`registry.py` côté backend) :

1. Recherche libre (`GET /market-search`) — nom ou symbole, auprès de Yahoo Finance.
2. « Charger » un résultat affiche un aperçu en direct (cotation + mini graphique,
   `GET /market-lookup/{symbol}` et `/market-lookup/{symbol}/ohlc`) — rien n'est encore persisté.
3. Deux choix depuis cet aperçu :
   - **Ajouter à la bibliothèque active** (`POST /market-activate`) — le ticker est déclaré côté
     backend, son historique complet est rapatrié dans le cache, et il apparaît aussitôt dans le
     tableau principal (invalidation de la requête `indicators`).
   - **Juste observer** — referme l'aperçu sans rien enregistrer.

Reste, côté frontend :

- Les futures couches de l'architecture Finance Bro (sentiment, modèles, verdicts, paper trading)
  n'ont pas encore d'endpoint API — à ajouter aux deux en parallèle au fur et à mesure.


### Ensemble pondéré par backtest

La page Prévision a une carte « Ensemble pondéré par backtest » (`GET /ensemble/{code}`) : bouton à la demande (le backtest walk-forward prend environ une minute), choix Hedge / 1/erreur, tableau poids + CRPS, hit ratio, IC, Sharpe déflaté par modèle.
